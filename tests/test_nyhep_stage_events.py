# -*- coding: utf-8 -*-

"""NYHEP stage events: ingest idempotency, export lag, and the reference backfill."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(API))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

from metrics import nyhep_stage_events as stage
from test_empower_portal import INGEST_SECRET, FakeDb, ingest
from unittest.mock import patch
import os


def project(
    enroll_id,
    customer,
    status,
    step,
    step_status="",
    on_todo=False,
    todo="",
    program="EmPower+",
    due="",
    enrolled="11/1/2026",
):
    row = {
        "id": enroll_id,
        "customer": customer,
        "status": status,
        "step": step,
        "stepStatus": step_status,
        "onTodo": on_todo,
        "program": program,
        "projectType": "Residential",
        "due": due,
        "enrolled": enrolled,
        "city": "Buffalo",
    }
    if on_todo:
        row["todoStep"] = todo or step
    return row


def reference_snapshots():
    """Four checks whose folded events match the agreed reference counts."""
    steady = [
        project("E01", "Ada Marin", "Open", "Final Project Review", "In Review", due="12/31/2026"),
        project("E02", "Ben Ortiz", "Open", "Contractor Assignment", "Pending"),
        project("E04", "Cara Nguyen", "Open", "Assessment Review", "Waiting"),
        project("E05", "Drew Patel", "Open", "Funding Allocations", "Pending"),
        project("E06", "Eve Brooks", "Open", "Final Technical Review", "In Review"),
        project("E07", "Finn Cole", "Open", "Installation Review", "Pending"),
        project("E08", "Gia Holt", "Open", "Payment", "Pending"),
        project(
            "E10",
            "Ivy Nguyen",
            "Open",
            "Workscope Review",
            "New",
            on_todo=True,
            todo="Workscope Submission",
        ),
        project(
            "E11",
            "Jules Park",
            "Open",
            "Enrollment Acceptance",
            "Pending",
            on_todo=True,
            program="Comfort Home",
        ),
        project(
            "E12",
            "Kai Reed",
            "Open",
            "Workscope Submission",
            "New",
            on_todo=True,
            program="REA",
            due="12/1/2026",
        ),
    ]
    early_only = [
        project("E03", "Lena Ortiz", "Open", "Assessment Submission", "Submitted"),
        project("E09", "Mo Ali", "Open", "Install Started", "Active"),
        project("E13", "Nia Brooks", "Open", "Workscope Submission", "New", on_todo=True, due="12/20/2026"),
        project("E14", "Omar Diaz", "Open", "Enrollment Acceptance", "New", on_todo=True),
        project("E15", "Pia Shah", "Open", "Enrollment Acceptance", "Pending", on_todo=True),
        project("E16", "Quinn Hale", "Open", "Create an Enrollment", "Draft"),
    ]
    later = [
        project("E03", "Lena Ortiz", "Open", "Provisional Approval", "In Review"),
        project("E09", "Mo Ali", "Closed", "Funding Allocations", "Complete"),
        project("E13", "Nia Brooks", "Open", "Install Started", "Active"),
        project("E14", "Omar Diaz", "Open", "Enrollment Acceptance", "Submitted", on_todo=True),
        project(
            "E15",
            "Pia Shah",
            "Open",
            "Final Project Submission",
            "New",
            on_todo=True,
            due="1/15/2027",
        ),
        project("E16", "Quinn Hale", "Open", "Install Started", "Active"),
    ]
    late = [
        project("E17", "Rhea Kim", "Open", "Enrollment Acceptance", "New", on_todo=True),
        project("E18", "Sam Ito", "Open", "Workscope Submission", "New", on_todo=True, due="12/20/2026"),
        project("E19", "Tess Cole", "Open", "Final Project Submission", "New", on_todo=True, due="1/15/2027"),
        project("E20", "Uma Shah", "Open", "Assessment Started", "Active"),
        project("E21", "Vic Lane", "Open", "Install Started", "Active"),
        project("E22", "Wynn Park", "Open", "Create an Enrollment", "New", on_todo=True),
    ]
    first = steady + early_only
    rest = steady + later
    return [
        {"snapshot": "2026-11-17_pm", "checkedAt": "Tue Nov 17, 2:31 PM Phoenix", "projects": first},
        {"snapshot": "2026-11-17_eod", "checkedAt": "Tue Nov 17, 8:05 PM Phoenix", "projects": rest},
        {"snapshot": "2026-11-18_am", "checkedAt": "Wed Nov 18, 8:10 AM Phoenix", "projects": rest},
        {"snapshot": "2026-11-25_pm", "checkedAt": "Wed Nov 25, 4:00 PM Phoenix", "projects": rest + late},
    ]


def _post(db, payload):
    from test_empower_portal import invoke

    raw = json.dumps(payload).encode("utf-8")
    headers = {"X-Webhook-Secret": INGEST_SECRET, "Content-Length": str(len(raw))}
    with patch.dict(os.environ, {"NYHEP_INGEST_SECRET": INGEST_SECRET}):
        with patch.object(ingest, "get_db", return_value=db):
            return invoke(ingest, "POST", "/api/empower_portal_ingest", headers, raw)


class StageEventTests(unittest.TestCase):
    def test_reingest_keeps_the_same_keys(self):
        db = FakeDb()
        payload = {
            "snapshot": "2026-11-18_am",
            "checkedAt": "Wed Nov 18, 9:00 AM Phoenix",
            "projects": [
                project("E-1", "Ada Marin", "Open", "Workscope Review", "In Review"),
                project(
                    "E-2",
                    "Ben Ortiz",
                    "Open",
                    "Workscope Review",
                    "New",
                    on_todo=True,
                    todo="Workscope Submission",
                ),
            ],
            "changes": [],
            "history": [],
        }
        changed = {
            **payload,
            "projects": [
                payload["projects"][0],
                project("E-2", "Ben Ortiz", "Open", "Workscope Submission", "New", on_todo=True),
            ],
        }
        self.assertEqual(_post(db, payload)[0], 200)
        self.assertEqual(_post(db, payload)[0], 200)
        keys = [key[1] for key in db.docs if key[0] == stage.COLLECTION]
        self.assertEqual(len(keys), 2)
        self.assertEqual(len(set(keys)), 2)
        open_queries = [row for row in db.queries if row[0] == stage.COLLECTION and row[1] == "ended_at"]
        self.assertEqual(len(open_queries), 2)
        self.assertNotIn("stageHistory", db.docs[(ingest.LATEST_COLLECTION, ingest.LATEST_DOC_ID)])
        before = len([key for key in db.docs if key[0] == stage.COLLECTION])
        self.assertEqual(_post(db, changed)[0], 200)
        after = [key[1] for key in db.docs if key[0] == stage.COLLECTION]
        self.assertEqual(len(after), before + 1)
        ended = [
            doc
            for key, doc in db.docs.items()
            if key[0] == stage.COLLECTION and doc.get("enrollment_id") == "E-2" and doc.get("ended_at")
        ]
        self.assertEqual(len(ended), 1)
        current = [
            doc
            for key, doc in db.docs.items()
            if key[0] == stage.COLLECTION and doc.get("enrollment_id") == "E-2" and doc.get("ended_at") is None
        ]
        self.assertEqual(current[0]["owner_side"], "ours")
        self.assertEqual(ended[0]["owner_side"], "unknown")
        self.assertEqual(ended[0]["todo_stage"], "Workscope Submission")
        self.assertNotIn("todo_stage", current[0])

    def test_export_lag_is_unknown_owner(self):
        events = stage.fold_snapshots(
            [
                {
                    "snapshot": "2026-11-18_am",
                    "checkedAt": "Wed Nov 18, 9:00 AM Phoenix",
                    "projects": [
                        project(
                            "E-2",
                            "Ben Ortiz",
                            "Open",
                            "Workscope Review",
                            "New",
                            on_todo=True,
                            todo="Workscope Submission",
                        )
                    ],
                }
            ]
        )
        body = next(iter(events.values()))
        self.assertEqual(body["owner_side"], "unknown")
        self.assertEqual(body["stage"], "Workscope Review")
        self.assertEqual(body["todo_stage"], "Workscope Submission")
        self.assertEqual(body["step_status"], "New")
        self.assertFalse(body["first_seen_is_start"])

    def test_missing_enrollment_ends_its_open_event(self):
        snaps = [
            {
                "snapshot": "2026-11-17_pm",
                "checkedAt": "Tue Nov 17, 2:31 PM Phoenix",
                "projects": [project("E-9", "Mo Ali", "Open", "Install Started", "Active")],
            },
            {
                "snapshot": "2026-11-17_eod",
                "checkedAt": "Tue Nov 17, 8:05 PM Phoenix",
                "projects": [],
            },
        ]
        events = stage.fold_snapshots(snaps)
        self.assertEqual(len(events), 1)
        body = next(iter(events.values()))
        self.assertIsNotNone(body["ended_at"])
        self.assertEqual(stage.summarize(events, snaps)["current"], 0)
        self.assertEqual(stage.summarize(events, snaps)["ended"], 1)

    def test_business_day_flags(self):
        self.assertEqual(stage.business_days(date(2026, 11, 13), date(2026, 11, 16)), 1)
        self.assertEqual(stage.business_days(date(2026, 11, 17), date(2026, 11, 25)), 6)
        self.assertEqual(stage.business_days(date(2026, 11, 18), date(2026, 11, 25)), 5)
        long_review = {
            "stage": "Final Project Review",
            "first_seen_at": "2026-11-17T14:31:00-07:00",
            "enrollment_status": "Open",
            "on_todo": False,
            "due_date": "",
        }
        short_review = {
            "stage": "Final Project Review",
            "first_seen_at": "2026-11-18T08:10:00-07:00",
            "enrollment_status": "Open",
            "on_todo": False,
            "due_date": "",
        }
        workscope = {
            "stage": "Workscope Submission",
            "first_seen_at": "2026-11-25T16:00:00-07:00",
            "enrollment_status": "Open",
            "on_todo": False,
            "due_date": "",
        }
        as_of = date(2026, 11, 25)
        self.assertIn("Final Project Review >5 business days", stage.stage_flags(long_review, {}, as_of))
        self.assertNotIn("Final Project Review >5 business days", stage.stage_flags(short_review, {}, as_of))
        flags = stage.stage_flags(workscope, {"enrolled": "9/1/2026", "due": ""}, as_of)
        self.assertIn("Workscope Submission >30 days from enrollment", flags)
        flagged = stage.stage_flags(
            {
                "stage": "Final Project Submission",
                "first_seen_at": "2026-11-25T16:00:00-07:00",
                "due_date": "",
            },
            {"enrolled": "8/1/2026", "due": ""},
            as_of,
        )
        self.assertIn("Final Project Submission >75 days from enrollment", flagged)
        self.assertEqual(
            stage.stage_flags(workscope, {"enrolled": "9/1/2026", "due": "12/1/2026"}, as_of),
            [],
        )

    def test_reference_backfill_counts_and_second_run(self):
        snaps = reference_snapshots()
        first = stage.fold_snapshots(snaps)
        second = stage.fold_snapshots(snaps)
        self.assertEqual(first, second)
        summary = stage.summarize(first, snaps)
        self.assertEqual(summary["observations"], 70)
        self.assertEqual(summary["enrollments"], 22)
        self.assertEqual(summary["events"], 28)
        self.assertEqual(summary["current"], 22)
        self.assertEqual(summary["ended"], 6)
        self.assertEqual(summary["unique_keys"], 28)
        self.assertEqual(summary["owner_side"], {"ours": 12, "program": 9, "unknown": 1})
        self.assertEqual(summary["programs"], {"EmPower+": 20, "Comfort Home": 1, "REA": 1})
        self.assertEqual(summary["with_program"], 8)
        self.assertEqual(summary["flags"]["Final Project Review >5 business days"], 1)
        self.assertEqual(summary["flags"]["Workscope Review >5 business days"], 0)
        latest = snaps[-1]
        open_events = {
            body["enrollment_id"]: (doc_id, body)
            for doc_id, body in first.items()
            if body.get("ended_at") is None
        }
        _open, changed = stage.apply_snapshot(
            open_events, latest["projects"], latest["snapshot"], latest["checkedAt"]
        )
        self.assertEqual(changed, [])
        shown = stage.with_program_rows(list(first.values()), latest["projects"], date(2026, 11, 25))
        fpr = next(row for row in shown if row["id"] == "E01")
        self.assertTrue(fpr["since"].startswith("since at least "))
        self.assertIn("Final Project Review >5 business days", fpr["flag"])

    def test_backfill_dry_run_script_matches_and_does_not_write(self):
        snaps = reference_snapshots()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snaps.json"
            path.write_text(json.dumps({"snapshots": snaps}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "backfill_nyhep_stage_events.py"), "--fixture", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = completed.stdout
        self.assertIn("observations 70", output)
        self.assertIn("enrollments 22", output)
        self.assertIn("events 28", output)
        self.assertIn("current 22", output)
        self.assertIn("ended 6", output)
        self.assertIn("unique_keys 28", output)
        self.assertIn("owner_side ours 12", output)
        self.assertIn("owner_side program 9", output)
        self.assertIn("owner_side unknown 1", output)
        self.assertIn("program EmPower+ 20", output)
        self.assertIn("program Comfort Home 1", output)
        self.assertIn("program REA 1", output)
        self.assertIn("with_program 8", output)
        self.assertIn("flag Final Project Review >5 business days 1", output)
        self.assertIn("dry-run", output)
        self.assertNotIn("wrote ", output)
        self.assertNotIn("NYHEP_INGEST_SECRET", output)

    def test_local_workbook_sets_program_and_todo_step(self):
        import backfill_nyhep_stage_events as backfill

        enrollment = [
            ["Enrollment Number", "Customer", "Status", "Workflow Step", "Step Status", "Program", "Project Type"],
            ["1175812", "Ada Marin", "Open", "Workscope Review", "In Review", "EmPower+", "Residential"],
        ]
        todo = [
            ["Enrollment Number", "Workflow Step", "Step Status"],
            ["1175812", "Workscope Submission", "New"],
        ]
        projects = backfill.projects_from_tables(enrollment, todo)
        self.assertEqual(projects[0]["program"], "EmPower+")
        self.assertEqual(projects[0]["projectType"], "Residential")
        self.assertTrue(projects[0]["onTodo"])
        self.assertEqual(projects[0]["todoStep"], "Workscope Submission")
        self.assertEqual(projects[0]["stepStatus"], "New")
        self.assertEqual(projects[0]["step"], "Workscope Review")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-11-18_am"
            folder.mkdir()
            _write_xlsx(folder / "EnrollmentList.xlsx", enrollment)
            _write_xlsx(folder / "ToDoList.xlsx", todo)
            (folder / "checkedAt.txt").write_text("Wed Nov 18, 9:00 AM Phoenix\n", encoding="utf-8")
            snaps = backfill.snapshots_from_local_dir(Path(tmp))
        self.assertEqual(snaps[0]["projects"][0]["todoStep"], "Workscope Submission")
        self.assertEqual(snaps[0]["checkedAt"], "Wed Nov 18, 9:00 AM Phoenix")

    def test_shared_string_workbook_dry_run_is_stable(self):
        import backfill_nyhep_stage_events as backfill

        enrolled_serial = (date(2026, 9, 1) - date(1899, 12, 30)).days
        due_serial = (date(2026, 11, 20) - date(1899, 12, 30)).days
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_export(
                root / "2026-11-17_pm",
                step="Workscope Review",
                enrolled_serial=enrolled_serial,
                due_serial=due_serial,
                checked_at="Tue Nov 17, 2:31 PM Phoenix",
            )
            _write_export(
                root / "2026-11-18_am",
                step="Final Project Review",
                enrolled_serial=enrolled_serial,
                due_serial=due_serial,
                checked_at="Wed Nov 18, 8:10 AM Phoenix",
            )
            parsed = backfill.snapshots_from_local_dir(root)
            by_id = {row["snapshot"]: row for row in parsed}
            first = by_id["2026-11-17_pm"]["projects"][0]
            self.assertEqual(first["id"], "1170001")
            self.assertEqual(first["customer"], "Ada Marin")
            self.assertEqual(first["status"], "Open")
            self.assertEqual(first["step"], "Workscope Review")
            self.assertEqual(first["todoStep"], "Workscope Submission")
            self.assertEqual(first["stepStatus"], "New")
            self.assertEqual(first["enrolled"], "9/1/2026")
            self.assertEqual(first["due"], "11/20/2026")
            self.assertEqual(by_id["2026-11-17_pm"]["checkedAt"], "Tue Nov 17, 2:31 PM Phoenix")
            self.assertEqual(by_id["2026-11-18_am"]["projects"][0]["step"], "Final Project Review")
            outputs = []
            for _ in range(2):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "backfill_nyhep_stage_events.py"),
                        "--local-dir",
                        str(root),
                        "--dry-run",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertNotIn("unrecognized arguments", completed.stderr)
                self.assertIn("dry-run", completed.stdout)
                self.assertNotIn("wrote ", completed.stdout)
                self.assertNotIn("NYHEP_INGEST_SECRET", completed.stdout)
                outputs.append(completed.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn("observations 2", outputs[0])
        self.assertIn("enrollments 1", outputs[0])
        self.assertIn("events 2", outputs[0])
        self.assertNotIn("observations 0", outputs[0])


def _write_export(folder: Path, step: str, enrolled_serial: int, due_serial: int, checked_at: str) -> None:
    """One NYHEP-shaped export: shared strings, a skipped empty cell, and date serials."""
    folder.mkdir()
    (folder / "data.json").write_text(json.dumps({"checkedAt": checked_at}), encoding="utf-8")
    headers = [
        "Enrollment Number",
        "Customer",
        "Notes",
        "Status",
        "Workflow Step",
        "Enrollment Date",
        "Program",
        "Project Type",
    ]
    # Notes (column C) is omitted from the data row, the way Excel drops an empty cell.
    enrollment_cells = {
        "A": "1170001",
        "B": "Ada Marin",
        "D": "Open",
        "E": step,
        "F": str(enrolled_serial),
        "G": "EmPower+",
        "H": "Residential",
    }
    _write_shared_sheet(
        folder / "EnrollmentList.xlsx",
        headers,
        enrollment_cells,
        date_columns={"F"},
    )
    _write_shared_sheet(
        folder / "ToDoList.xlsx",
        ["Enrollment Number", "Workflow Step", "Workflow Step Status", "Due Date"],
        {
            "A": "1170001",
            "B": "Workscope Submission",
            "C": "New",
            "D": str(due_serial),
        },
        date_columns={"D"},
        rich_headers={"Workflow Step Status": ("Workflow Step ", "Status")},
    )


def _col_letter(index: int) -> str:
    letters = ""
    number = index + 1
    while number:
        number, rem = divmod(number - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _write_shared_sheet(
    path: Path,
    headers: list[str],
    data_cells: dict[str, str],
    date_columns: set[str],
    rich_headers: dict[str, tuple[str, str]] | None = None,
) -> None:
    rich_headers = rich_headers or {}
    strings: list[str] = []
    index_of: dict[str, int] = {}

    def share(value: str) -> int:
        if value not in index_of:
            index_of[value] = len(strings)
            strings.append(value)
        return index_of[value]

    for header in headers:
        if header not in rich_headers:
            share(header)
    for value in data_cells.values():
        if not value.isdigit():
            share(value)
    shared_xml = []
    for text in strings:
        if text in rich_headers:
            left, right = rich_headers[text]
            shared_xml.append(f"<si><r><t>{escape(left)}</t></r><r><t>{escape(right)}</t></r></si>")
        else:
            shared_xml.append(f"<si><t>{escape(text)}</t></si>")
    # Rich headers are not in `strings` yet. Add them so the header cell can point at the rich item.
    for header, parts in rich_headers.items():
        if header not in index_of:
            index_of[header] = len(strings)
            strings.append(header)
            left, right = parts
            shared_xml.append(f"<si><r><t>{escape(left)}</t></r><r><t>{escape(right)}</t></r></si>")

    def header_cells() -> str:
        cells = []
        for index, header in enumerate(headers):
            ref = f"{_col_letter(index)}1"
            cells.append(f'<c r="{ref}" t="s"><v>{index_of[header]}</v></c>')
        return "".join(cells)

    def data_row() -> str:
        cells = []
        for column, value in data_cells.items():
            ref = f"{column}2"
            if column in date_columns:
                cells.append(f'<c r="{ref}" s="1"><v>{value}</v></c>')
            elif value.isdigit() and value not in index_of:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{index_of[value]}</v></c>')
        return "".join(cells)

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData><row r=\"1\">{header_cells()}</row><row r=\"2\">{data_row()}</row></sheetData></worksheet>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>'
    )
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{''.join(shared_xml)}</sst>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/sharedStrings.xml", shared)
        book.writestr("xl/styles.xml", styles)
        book.writestr("xl/worksheets/sheet1.xml", sheet)


def _write_xlsx(path: Path, rows: list[list[str]]) -> None:
    sheet_rows = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            col = chr(64 + c_idx)
            cells.append(
                f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/worksheets/sheet1.xml", sheet)


class PortalTimelineTests(unittest.TestCase):
    def test_view_hides_a_first_sighting_as_since_at_least(self):
        from metrics.empower_portal_metrics import build_portal_view

        snaps = reference_snapshots()
        events = list(stage.fold_snapshots(snaps).values())
        view = build_portal_view(snaps[-1], events)
        row = next(item for item in view["withProgram"] if item["id"] == "E01")
        self.assertTrue(row["sinceAtLeast"])
        self.assertIn("since at least Nov 17, 2026", row["since"])
        enrollment = next(item for item in view["enrollments"] if item["id"] == "E03")
        self.assertGreaterEqual(len(enrollment["timeline"]), 2)
        self.assertTrue(any(item["current"] for item in enrollment["timeline"]))
        encoded = json.dumps(view).lower()
        self.assertNotIn("phone", encoded)
        self.assertNotIn("email", encoded)


if __name__ == "__main__":
    unittest.main()
