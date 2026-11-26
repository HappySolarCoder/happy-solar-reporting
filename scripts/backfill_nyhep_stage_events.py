# -*- coding: utf-8 -*-
"""Rebuild nyhep_empower_stage_events from stored NYHEP snapshots.

Dry-run is the default. It prints counts and does not write.

    python scripts/backfill_nyhep_stage_events.py --fixture tests/fixtures/nyhep_stage_events.json
    python scripts/backfill_nyhep_stage_events.py --local-dir ./nyhep-exports --dry-run
    python scripts/backfill_nyhep_stage_events.py --write

--write is explicit. Do not pass it against production unless that write has
been approved. This script never prints NYHEP_INGEST_SECRET.

Snapshot documents do not carry program, project type, or the To-Do workflow
step. --local-dir points at folders named by snapshot id. Each folder may
hold EnrollmentList.xlsx and ToDoList.xlsx. Those columns fill the missing
fields before the events are derived.

Snapshot order is the date in the id, then am, then pm, then eod.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree
ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from metrics.nyhep_stage_events import (  # noqa: E402
    COLLECTION,
    fold_snapshots,
    format_summary,
    summarize,
)


_SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_ENROLLMENT_FILE = "EnrollmentList.xlsx"
_TODO_FILE = "ToDoList.xlsx"
_EXCEL_EPOCH = date(1899, 12, 30)
_BUILTIN_DATE_FORMATS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _norm_header(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("#", " number ").split())


def _header_map(headers: list[str]) -> dict[str, int]:
    return {_norm_header(header): index for index, header in enumerate(headers)}


def _cell(row: list[str], mapping: dict[str, int], *names: str) -> str:
    for name in names:
        index = mapping.get(_norm_header(name))
        if index is not None and index < len(row):
            return str(row[index] or "").strip()
    return ""


def _column_index(ref: str) -> int | None:
    letters = []
    for char in ref:
        if char.isalpha():
            letters.append(char)
        else:
            break
    if not letters:
        return None
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - 64)
    return index - 1


def _looks_like_date_format(code: str) -> bool:
    lowered = code.lower()
    if any(token in lowered for token in ("yy", "dd")):
        return True
    return "m" in lowered and "d" in lowered and "y" in lowered


def as_mdy(value: object) -> str:
    """Calendar date as M/D/YYYY. Excel serials and datetimes are converted."""
    text = str(value or "").strip()
    if not text:
        return ""
    matched = _MDY.match(text)
    if matched:
        month, day, year = (int(part) for part in matched.groups())
        return f"{month}/{day}/{year}"
    matched = _ISO_DATE.match(text)
    if matched:
        year, month, day = (int(part) for part in matched.groups())
        return f"{month}/{day}/{year}"
    try:
        serial = float(text)
    except ValueError:
        return text
    if serial < 1 or serial > 80000:
        return text
    parsed = _EXCEL_EPOCH + timedelta(days=int(serial))
    if not 1990 <= parsed.year <= 2100:
        return text
    return f"{parsed.month}/{parsed.day}/{parsed.year}"


def projects_from_tables(enrollment_rows: list[list[str]], todo_rows: list[list[str]] | None) -> list[dict]:
    """Join an Enrollment List sheet to a To-Do List sheet on enrollment number."""
    if not enrollment_rows:
        return []
    mapping = _header_map(enrollment_rows[0])
    todos: dict[str, dict[str, str]] = {}
    if todo_rows:
        todo_map = _header_map(todo_rows[0])
        for row in todo_rows[1:]:
            enroll_id = _cell(row, todo_map, "Enrollment Number", "Enrollment", "Enroll number")
            if not enroll_id:
                continue
            todos[enroll_id] = {
                "step": _cell(row, todo_map, "Workflow Step", "Step"),
                "step_status": _cell(row, todo_map, "Workflow Step Status", "Step Status"),
                "due": _cell(row, todo_map, "Due Date", "Due"),
            }
    projects = []
    for row in enrollment_rows[1:]:
        enroll_id = _cell(row, mapping, "Enrollment Number", "Enrollment", "Enroll number")
        if not enroll_id:
            continue
        todo = todos.get(enroll_id)
        project = {
            "id": enroll_id,
            "customer": _cell(row, mapping, "Customer", "Customer Name"),
            "city": _cell(row, mapping, "City"),
            "county": _cell(row, mapping, "County"),
            "enrolled": as_mdy(_cell(row, mapping, "Enrolled", "Enrollment Date", "Date Enrolled")),
            "status": _cell(row, mapping, "Status", "Enrollment Status"),
            "step": _cell(row, mapping, "Workflow Step", "Step"),
            "stepStatus": _cell(row, mapping, "Step Status"),
            "due": as_mdy(_cell(row, mapping, "Due", "Due Date")),
            "tier": _cell(row, mapping, "Tier"),
            "installer": _cell(row, mapping, "Installer"),
            "program": _cell(row, mapping, "Program"),
            "projectType": _cell(row, mapping, "Project Type"),
            "onTodo": todo is not None,
        }
        if todo is not None:
            project["todoStep"] = todo["step"]
            if todo["step_status"]:
                project["stepStatus"] = todo["step_status"]
            if todo["due"]:
                project["due"] = as_mdy(todo["due"])
        projects.append(project)
    return projects


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall(f"{{{_SHEET_NS}}}si"):
        runs = item.findall(f"{{{_SHEET_NS}}}r")
        if runs:
            parts = []
            for run in runs:
                for node in run.findall(f"{{{_SHEET_NS}}}t"):
                    parts.append(node.text or "")
            strings.append("".join(parts))
            continue
        strings.append("".join(node.text or "" for node in item.findall(f"{{{_SHEET_NS}}}t")))
    return strings


def _date_style_indexes(book: zipfile.ZipFile) -> set[int]:
    if "xl/styles.xml" not in book.namelist():
        return set()
    root = ElementTree.fromstring(book.read("xl/styles.xml"))
    custom: dict[int, str] = {}
    for num in root.findall(f"{{{_SHEET_NS}}}numFmts/{{{_SHEET_NS}}}numFmt"):
        try:
            custom[int(num.get("numFmtId") or 0)] = num.get("formatCode") or ""
        except ValueError:
            continue
    date_ids = set(_BUILTIN_DATE_FORMATS)
    for fmt_id, code in custom.items():
        if _looks_like_date_format(code):
            date_ids.add(fmt_id)
    indexes = set()
    for index, xf in enumerate(root.findall(f"{{{_SHEET_NS}}}cellXfs/{{{_SHEET_NS}}}xf")):
        try:
            fmt_id = int(xf.get("numFmtId") or 0)
        except ValueError:
            continue
        if fmt_id in date_ids:
            indexes.add(index)
    return indexes


def _cell_text(cell: ElementTree.Element, shared: list[str], date_styles: set[int]) -> str:
    inline = cell.find(f"{{{_SHEET_NS}}}is")
    if inline is not None:
        return "".join(node.text or "" for node in inline.iter(f"{{{_SHEET_NS}}}t"))
    value = cell.find(f"{{{_SHEET_NS}}}v")
    raw = "" if value is None or value.text is None else value.text
    if cell.get("t") == "s":
        try:
            index = int(raw)
        except ValueError:
            return ""
        return shared[index] if 0 <= index < len(shared) else ""
    style = cell.get("s")
    try:
        style_index = int(style) if style is not None else None
    except ValueError:
        style_index = None
    if style_index is not None and style_index in date_styles:
        return as_mdy(raw)
    return raw


def read_xlsx(path: Path) -> list[list[str]]:
    """Read the first worksheet, including shared strings and sparse cells."""
    with zipfile.ZipFile(path) as book:
        shared = _shared_strings(book)
        date_styles = _date_style_indexes(book)
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in book.namelist():
            sheets = sorted(
                name for name in book.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            if not sheets:
                return []
            sheet_name = sheets[0]
        sheet = ElementTree.fromstring(book.read(sheet_name))
    rows = []
    for row in sheet.findall(f".//{{{_SHEET_NS}}}sheetData/{{{_SHEET_NS}}}row"):
        values: dict[int, str] = {}
        next_index = 0
        for cell in row.findall(f"{{{_SHEET_NS}}}c"):
            index = _column_index(cell.get("r") or "")
            if index is None:
                index = next_index
            values[index] = _cell_text(cell, shared, date_styles)
            next_index = index + 1
        if not values:
            rows.append([])
            continue
        rows.append([values.get(index, "") for index in range(max(values) + 1)])
    return rows


def snapshots_from_local_dir(folder: Path) -> list[dict]:
    snapshots = []
    if not folder.is_dir():
        return snapshots
    for child in sorted(path for path in folder.iterdir() if path.is_dir()):
        enrollment = child / _ENROLLMENT_FILE
        if not enrollment.is_file():
            continue
        todo_path = child / _TODO_FILE
        todo_rows = read_xlsx(todo_path) if todo_path.is_file() else None
        checked = child / "checkedAt.txt"
        data_path = child / "data.json"
        if checked.is_file():
            checked_at = checked.read_text(encoding="utf-8").strip()
        elif data_path.is_file():
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            checked_at = str(payload.get("checkedAt") or "").strip() if isinstance(payload, dict) else ""
        else:
            checked_at = ""
        snapshots.append(
            {
                "snapshot": child.name,
                "checkedAt": checked_at or child.name,
                "projects": projects_from_tables(read_xlsx(enrollment), todo_rows),
            }
        )
    return snapshots


def _overlay(base: list[dict], extra: list[dict]) -> list[dict]:
    by_id = {str(row.get("snapshot") or ""): row for row in extra}
    if not base:
        return extra
    merged = []
    for row in base:
        snapshot_id = str(row.get("snapshot") or "")
        incoming = by_id.get(snapshot_id)
        if incoming is None:
            merged.append(row)
            continue
        projects = []
        extras = {str(item.get("id") or ""): item for item in incoming.get("projects") or []}
        for project in row.get("projects") or []:
            item = dict(project)
            extra_project = extras.get(str(item.get("id") or ""))
            if extra_project:
                for field in ("program", "projectType", "todoStep", "onTodo", "stepStatus", "due", "enrolled"):
                    if field in extra_project and extra_project.get(field) not in ("", None):
                        item[field] = extra_project[field]
            projects.append(item)
        merged.append({**row, "projects": projects})
    return merged


def load_snapshots(fixture: str | None, local_dir: str | None) -> list[dict]:
    base: list[dict] = []
    if fixture:
        payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        base = payload.get("snapshots") if isinstance(payload, dict) else payload
        if not isinstance(base, list):
            raise SystemExit("fixture must be a list of snapshots or {snapshots: [...]}")
    extra = snapshots_from_local_dir(Path(local_dir)) if local_dir else []
    return _overlay(base, extra)


def write_events(events: dict[str, dict]) -> None:
    from empower_portal_ingest import get_db

    db = get_db()
    batch = db.batch()
    pending = 0
    for doc_id, body in events.items():
        batch.set(db.collection(COLLECTION).document(doc_id), body)
        pending += 1
        if pending == 400:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run NYHEP stage events unless --write is set.")
    parser.add_argument("--fixture", help="JSON snapshots. Does not read Firestore.")
    parser.add_argument("--local-dir", help="Snapshot folders with EnrollmentList.xlsx and ToDoList.xlsx.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print counts and do not write. This is the default.")
    mode.add_argument("--write", action="store_true", help="Write event documents. Dry-run is the default.")
    args = parser.parse_args(argv)
    if not args.fixture and not args.local_dir and not args.write:
        parser.error("pass --fixture, --local-dir, or --write")
    if args.fixture or not args.write:
        snapshots = load_snapshots(args.fixture, args.local_dir)
    else:
        from empower_portal_ingest import SNAPSHOT_COLLECTION, get_db

        db = get_db()
        snapshots = []
        for snap in db.collection(SNAPSHOT_COLLECTION).stream():
            data = snap.to_dict() or {}
            if isinstance(data, dict):
                data["snapshot"] = data.get("snapshot") or snap.id
                snapshots.append(data)
        if args.local_dir:
            snapshots = _overlay(snapshots, snapshots_from_local_dir(Path(args.local_dir)))
    events = fold_snapshots(snapshots)
    summary = summarize(events, snapshots)
    sys.stdout.write(format_summary(summary))
    if args.write:
        write_events(events)
        sys.stdout.write(f"wrote {len(events)}\n")
    else:
        sys.stdout.write("dry-run\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
