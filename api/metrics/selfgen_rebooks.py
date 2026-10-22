# -*- coding: utf-8 -*-

"""Consultant Self Gen rebook credits (Evan, 2026-10-21).

When a solar consultant rebooks their own old appointment through the GHL
Happy Solar Booking Hub, the GHL workflow "Consultant Self Gen Rebook" revives
the dead opportunity in place (stage -> New Appointment, owner -> consultant)
and stamps the opportunity fields Self Gen Rebook Date, Rebooked By, Rebook
Setter Last Name, Prior Stage and Prior Owner. ghl-firestore-sync-v2 writes one
permanent doc per (opportunity, rebook date) to ``ghl_selfgen_rebooks_v1`` and
opens a fresh appointment cycle on the opportunity.

A log doc earns one Self Gen opp for the consultant, dated its rebook date
(America/New_York), when all of these hold:

- the contact's Lead Gen Source is Self Gen and Sweeper/Rehash Last Name is
  blank (contact and opportunity);
- the Rebook Setter Last Name equals the rebooking consultant's last name;
- the prior stage was DQ'ed / DQ'd, No Sit, No Show (incl. No Show/Pre-cancelled),
  Cancelled, or Needs Rebook / Reschedule Needed / Needs Reschedule. Sold and
  Sale Cancelled never qualify. A prior stage that is not a Demo-*, Sold, Sale
  Cancelled or New Appointment also qualifies when the ended cycle's outcome
  was No Sit;
- at least 14 days between the last appointment before the rebook and the
  rebook date;
- at most one credit per contact per calendar month, and none when another
  opportunity for the contact was created in that month (it already counts
  through createdAt).

Rebook credits are Self Gen only. They never change Opportunities Created
``result`` or ``sample_rows``. Reads only; single-field queries only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

REBOOK_COLLECTION = "ghl_selfgen_rebooks_v1"
OPP_COLLECTION = "ghl_opportunities_v2"
LEAD_GEN_SOURCE_CF_ID = "hd5QqHEOVSsPom5bJ32P"
SETTER_LAST_NAME_CONTACT_CF_ID = "Eq4NLTSkJ56KTxbxypuE"
MIN_DAYS_SINCE_LAST_APPOINTMENT = 14

SELF_GEN_LEAD_SOURCES = frozenset({"self gen", "selfgen", "self-gen", "self generated", "self-generated"})

# Approved dead stages, folded (see stage_key). Pipeline spellings:
# Buffalo/Rochester/Virtual "DQ'ed", Syracuse "DQ'd"; "No Show/Pre-cancelled",
# Syracuse "No Show/Pre-Cancel"; "Reschedule Needed", Syracuse "Needs Reschedule".
DEAD_STAGE_KEYS = frozenset(
    {
        "dqed", "dqd", "dq", "disqualified",
        "no sit",
        "no show", "no show pre cancelled", "no show pre canceled", "no show pre cancel",
        "cancelled", "canceled", "pre cancelled", "pre canceled",
        "needs rebook", "rebook needed", "reschedule needed", "needs reschedule",
    }
)
NEVER_STAGE_PREFIXES = ("sold", "sale cancelled", "sale canceled")
NOT_DEAD_FOR_NO_SIT_PREFIXES = ("demo", "new appointment", "sold", "sale cancelled", "sale canceled")


def compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def fold(value: Any) -> str:
    return compact(value).casefold()


def stage_key(name: Any) -> str:
    text = fold(name).replace("\u2019", "'").replace("'", "")
    for ch in "/-_":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def last_name(person: Any) -> str:
    parts = fold(person).split(" ")
    tail = parts[-1] if parts else ""
    return "" if tail in ("", "unassigned", "none", "unknown", "null") else tail


def prior_stage_qualifies(stage_name: Any, prior_dispo: Any) -> tuple[bool, str]:
    key = stage_key(stage_name)
    if not key:
        return (fold(prior_dispo) == "no sit", "no_sit_outcome" if fold(prior_dispo) == "no sit" else "prior_stage_unknown")
    if key.startswith(NEVER_STAGE_PREFIXES):
        return False, "prior_stage_sold"
    if key in DEAD_STAGE_KEYS:
        return True, "dead_stage"
    if fold(prior_dispo) == "no sit" and not key.startswith(NOT_DEAD_FOR_NO_SIT_PREFIXES):
        return True, "no_sit_outcome"
    return False, "prior_stage_not_dead"


def as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def parse_ymd(value: Any) -> date | None:
    try:
        return date.fromisoformat(compact(value)[:10])
    except ValueError:
        return None


def custom_field(record: dict | None, field_id: str) -> Any:
    if not isinstance(record, dict):
        return None
    for cf in record.get("customFields") or []:
        if isinstance(cf, dict) and cf.get("id") == field_id:
            for key in ("value", "fieldValueString", "fieldValue"):
                if cf.get(key) not in (None, ""):
                    return cf.get(key)
    return None


def days_since_last_appointment(log: dict, opp: dict | None, rebook_day: date) -> int | None:
    stored = log.get("daysSinceLastAppointment")
    if isinstance(stored, (int, float)):
        return int(stored)
    last = as_utc(log.get("lastAppointmentBeforeRebookAt")) or as_utc(log.get("priorAppointmentOccurredAt"))
    if last is None and isinstance(opp, dict):
        last = as_utc(opp.get("createdAt"))
    if last is None:
        return None
    return (rebook_day - last.astimezone(NY).date()).days


def roster_spelling(name: str, roster_names: Iterable[str]) -> str:
    """'Zach Maecker' -> 'Zachary Maecker' when exactly one roster name has the
    same last name and a first name that starts with (or is the start of) it."""
    first = fold(name).split(" ")[0] if fold(name) else ""
    want_last = last_name(name)
    hits = set()
    for cand in roster_names:
        parts = fold(cand).split(" ")
        if len(parts) < 2 or last_name(cand) != want_last:
            continue
        if parts[0].startswith(first) or first.startswith(parts[0]):
            hits.add(compact(cand))
    return hits.pop() if len(hits) == 1 else name


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


@dataclass
class RebookResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)
    logs_scanned: int = 0

    def skip(self, reason: str) -> None:
        self.excluded[reason] = self.excluded.get(reason, 0) + 1


def _chunks(values: list[str], size: int = 30) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def load_rebook_logs(db: Any, start_day: date, end_day_exclusive: date) -> list[dict[str, Any]]:
    """Log docs with rebookDate in [start_day, end_day_exclusive). One range filter."""
    out = []
    for snap in (
        db.collection(REBOOK_COLLECTION)
        .where("rebookDate", ">=", start_day.isoformat())
        .where("rebookDate", "<", end_day_exclusive.isoformat())
        .stream()
    ):
        d = snap.to_dict() or {}
        d.setdefault("_id", snap.id)
        out.append(d)
    return out


def load_docs(db: Any, collection: str, ids: Iterable[str]) -> dict[str, dict]:
    wanted = sorted({compact(i) for i in ids if compact(i)})
    found: dict[str, dict] = {}
    refs = [db.collection(collection).document(i) for i in wanted]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if snap.exists:
                found[snap.id] = snap.to_dict() or {}
    return found


def other_opps_created_in_month(db: Any, contact_id: str, opp_id: str, day: date) -> bool:
    for snap in db.collection(OPP_COLLECTION).where("contactId", "==", contact_id).stream():
        if snap.id == opp_id:
            continue
        d = snap.to_dict() or {}
        if compact(d.get("id")) == opp_id:
            continue
        created = as_utc(d.get("createdAt"))
        if created and month_key(created.astimezone(NY).date()) == month_key(day):
            return True
    return False


def load_rebook_credits(
    db: Any,
    start_local: datetime,
    end_local: datetime,
    *,
    load_contacts: Callable[[Any, list[str]], dict[str, dict]],
    owner_name: Callable[[str, str], str],
    pipeline_name: Callable[[Any], str],
    pipeline_ok: Callable[[str], bool],
    sweeper_last_name: Callable[[dict | None, dict | None], str],
    bucket_of: Callable[[str], str] | None = None,
    already_credited_contact_ids: set[str] | None = None,
    roster_names: Iterable[str] | None = None,
) -> RebookResult:
    """Eligible rebook credits whose rebook date falls in [start_local, end_local).

    The month cap looks back to the first of start_local's month so a week
    window cannot hand out a second credit in the same calendar month.
    """
    result = RebookResult()
    start_day = start_local.astimezone(NY).date()
    end_day = end_local.astimezone(NY).date()
    if end_local.astimezone(NY).time() != datetime.min.time():
        end_day += timedelta(days=1)
    scan_from = start_day.replace(day=1)
    logs = load_rebook_logs(db, scan_from, end_day)
    result.logs_scanned = len(logs)
    if not logs:
        return result

    opps = load_docs(db, OPP_COLLECTION, (l.get("opportunityId") for l in logs))
    contacts = load_contacts(db, [compact(l.get("contactId")) for l in logs if compact(l.get("contactId"))])
    credited_month: set[tuple[str, str]] = set()
    already = {compact(c) for c in (already_credited_contact_ids or set())}

    for log in sorted(logs, key=lambda l: (compact(l.get("rebookDate")), compact(l.get("_id")))):
        day = parse_ymd(log.get("rebookDate"))
        if day is None:
            result.skip("bad_rebook_date")
            continue
        in_window = start_day <= day < end_day
        opp_id = compact(log.get("opportunityId"))
        opp = opps.get(opp_id)
        cid = compact(log.get("contactId") or (opp or {}).get("contactId"))
        contact = contacts.get(cid)

        def skip(reason: str) -> None:
            if in_window:
                result.skip(reason)

        if not opp or not cid:
            skip("missing_opportunity_or_contact")
            continue
        if fold(custom_field(contact, LEAD_GEN_SOURCE_CF_ID)) not in SELF_GEN_LEAD_SOURCES:
            skip("lead_gen_source_not_self_gen")
            continue
        if sweeper_last_name(contact, opp):
            skip("sweeper_rehash_filled")
            continue
        ok, why = prior_stage_qualifies(log.get("priorStageName") or log.get("priorStageField"), log.get("priorDispositionValue"))
        if not ok:
            skip(why)
            continue
        gap = days_since_last_appointment(log, opp, day)
        if gap is None or gap < MIN_DAYS_SINCE_LAST_APPOINTMENT:
            skip("last_appointment_under_14_days")
            continue
        # The consultant is Rebooked By (the appointment's assigned user). The
        # opp owner after the workflow gives the roster spelling when it is the
        # same person; if the workflow could not move the owner, Rebooked By wins.
        owner_id = compact(log.get("rebookedByUserId"))
        rebooked_by = compact(log.get("rebookedBy"))
        owner_from_id = owner_name(owner_id, rebooked_by) if owner_id else ""
        if rebooked_by and last_name(owner_from_id) != last_name(rebooked_by):
            owner, owner_id = roster_spelling(rebooked_by, roster_names or ()), ""
        else:
            owner = owner_from_id or rebooked_by
        setter = compact(log.get("rebookSetterLastName")) or compact(custom_field(contact, SETTER_LAST_NAME_CONTACT_CF_ID))
        consultant_last = last_name(owner)
        if not setter or not consultant_last or fold(setter) != consultant_last:
            skip("setter_not_consultant")
            continue
        pname = pipeline_name(opp.get("pipelineId") or log.get("pipelineId"))
        if not pipeline_ok(pname):
            skip("pipeline_out_of_scope")
            continue
        key = (cid, month_key(day))
        if key in credited_month:
            skip("already_credited_this_month")
            continue
        if in_window and cid in already:
            credited_month.add(key)
            skip("contact_already_self_gen_in_window")
            continue
        if other_opps_created_in_month(db, cid, opp_id, day):
            credited_month.add(key)
            skip("other_opportunity_created_this_month")
            continue
        credited_month.add(key)
        if not in_window:
            continue
        effective = as_utc(log.get("effectiveAt")) or datetime(day.year, day.month, day.day, 12, tzinfo=NY).astimezone(timezone.utc)
        result.rows.append(
            {
                "opportunityId": opp_id,
                "rebookId": compact(log.get("_id")) or f"{opp_id}_{day.isoformat()}",
                "rebookCredit": True,
                "rebookDate": day.isoformat(),
                "contactId": cid,
                "contactLastName": (contact or {}).get("lastName"),
                "createdAt": effective.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "pipeline": pname,
                "pipelineId": compact(opp.get("pipelineId")) or None,
                "pipelineStageId": compact(opp.get("pipelineStageId")) or None,
                "owner": owner or "unassigned",
                "ownerId": owner_id or None,
                "setterLastName": setter[:1].upper() + setter[1:] if setter else setter,
                "leadGenSource": "Self Gen",
                "sweeperRehashLastName": None,
                "leadGenBucket": bucket_of(pname) if bucket_of else "Self Gen",
                "priorStageName": log.get("priorStageName") or log.get("priorStageField"),
                "daysSinceLastAppointment": gap,
            }
        )
    return result
