# -*- coding: utf-8 -*-

"""Consultant Self Gen rebook credits (Evan, 2026-10-21).

When a solar consultant rebooks their own old appointment through the GHL
Happy Solar Booking Hub, the GHL workflow "Consultant Self Gen Rebook" revives
the dead opportunity in place (stage -> New Appointment; GHL cannot move the
owner, so it stays the old rep) and stamps the opportunity fields Self Gen Rebook Date, Rebooked By, Rebook
Setter Last Name, Prior Stage and Prior Owner. ghl-firestore-sync-v2 writes one
permanent doc per (opportunity, rebook date) to ``ghl_selfgen_rebooks_v1`` and
opens a fresh appointment cycle on the opportunity.

A log doc earns one Self Gen opp for the consultant, dated its rebook date
(America/New_York), when all of these hold:

- the contact's Lead Gen Source is Self Gen and Sweeper/Rehash Last Name is
  blank (contact and opportunity);
- the Rebook Setter Last Name equals the rebooking consultant's last name. The
  consultant is Rebooked By (resolved to a GHL user by the sync), then the
  owner; see ``rebook_consultant``;
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

Owner revivals (Evan, 2026-10-30; Rueben Hand, opp gF5OLCLjhDNuEn0cZn0i,
2026-10-28). A consultant who books his own old opportunity outside the Booking
Hub (opp page, personal Self Gen calendar) gets no log doc, so the same credit is
also read from ``ghl_opportunity_stage_history_v1``: a ``stage_transition`` into
New Appointment, dated its effectiveAt (America/New_York), earns one Self Gen
opp for the owner when

- the owner did not change in the move (fromAssignedTo == toAssignedTo);
- Sweeper/Rehash Last Name is blank (contact and opportunity), so swept or
  rehashed work stays Sweeper/Rehash only;
- the prior stage is an approved dead stage above, or any stage of the
  Inbound/Lead Locker or Rehash pipelines. Sweeper pipeline stages, Sold, Sale
  Cancelled, Demo-* and Rescheduled never qualify;
- no Booking Hub log exists for the opportunity in the month (those rules
  decide it; a revival never rescues a rejected log);
- the opportunity was not created in that month, and its last appointment
  before the revival (else its createdAt) is 14+ days earlier;
- the same per-contact monthly caps apply.

The contact's original Lead Gen Source and Setter Last Name are not checked for
revivals: the owner booked it himself. The credit is the owner's Self Gen
appointment only, never a demo, ran or sale.

Rebook credits are Self Gen only. They never change Opportunities Created
``result`` or ``sample_rows``. Reads only; single-field queries only.
"""

from __future__ import annotations

import time
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
STAGE_HISTORY_COLLECTION = "ghl_opportunity_stage_history_v1"
PIPELINE_COLLECTION = "ghl_pipelines_v2"
OWNER_REVIVAL = "owner_revival"
BOOKING_HUB = "booking_hub"
REVIVAL_TARGET_STAGE_KEY = "new appointment"
HOLDING_PIPELINE_KEYS = frozenset({"inbound lead locker", "rehash"})
SWEEPER_PIPELINE_KEY = "sweeper"
REVIVAL_CACHE_SECONDS = 600
_REVIVAL_CACHE: dict[tuple, tuple[float, Any, list[dict[str, Any]]]] = {}

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


REBOOKED_BY_RESOLVED = "rebooked_by_name"


def same_person(a: Any, b: Any) -> bool:
    """Same last name and compatible first names ('Zach' / 'Zachary')."""
    if not last_name(a) or last_name(a) != last_name(b):
        return False
    fa, fb = fold(a).split(" ")[0], fold(b).split(" ")[0]
    return fa.startswith(fb) or fb.startswith(fa)


def rebook_consultant(
    log: dict, opp: dict | None, owner_name: Callable[[str, str], str], roster_names: Iterable[str]
) -> tuple[str, str]:
    """(consultant name, GHL user id) credited for a rebook.

    The workflow cannot move the opp owner, so the consultant is Rebooked By
    ({{appointment.user.name}}, the Booking Hub appointment's user):

    1. ``rebookedByUserId`` when the sync resolved it from Rebooked By
       (``rebookedByUserIdSource == "rebooked_by_name"``);
    2. otherwise Rebooked By itself. A stored id (an owner fallback, or a log
       written before the sync resolved names) only lends its roster spelling
       when it is the same person (``same_person``);
    3. Rebooked By empty: the stored id, then the owner at revive, then the
       opp's current owner.
    """
    uid = compact(log.get("rebookedByUserId"))
    rebooked_by = compact(log.get("rebookedBy"))
    if uid and rebooked_by and compact(log.get("rebookedByUserIdSource")) == REBOOKED_BY_RESOLVED:
        return owner_name(uid, rebooked_by) or rebooked_by, uid
    if rebooked_by:
        from_id = owner_name(uid, rebooked_by) if uid else ""
        if from_id and same_person(from_id, rebooked_by):
            return from_id, uid
        return roster_spelling(rebooked_by, roster_names), ""
    for candidate in (uid, compact(log.get("ownerAtRebook")), compact((opp or {}).get("assignedTo"))):
        if candidate:
            return owner_name(candidate, ""), candidate
    return "", ""


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


def ny_midnight_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=NY).astimezone(timezone.utc)


def base_opportunity_id(value: Any) -> str:
    """Real opp id for a cycle-view row ('<id>~cycle<n>' or cycleOf, see cycle_view.py)."""
    text = compact(value)
    base, sep, n = text.rpartition("~cycle")
    return base if sep and n.isdigit() else text


def _db_cache_key(db: Any) -> tuple:
    project, database = getattr(db, "project", None), getattr(db, "_database", None)
    if isinstance(project, str) and project:
        return ("firestore", project, str(database or ""))
    return ("object", id(db))


def load_owner_revivals(db: Any, start_day: date, end_day_exclusive: date) -> list[dict[str, Any]]:
    """Stage moves into New Appointment with effectiveAt in [start_day, end_day_exclusive) ET.

    One single-field range query on effectiveAt; cached REVIVAL_CACHE_SECONDS
    per Firestore database and window so the Sales Dashboard, channel goals and
    Bloom share one read on a warm instance.
    """
    key = (_db_cache_key(db), start_day.isoformat(), end_day_exclusive.isoformat())
    hit = _REVIVAL_CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < REVIVAL_CACHE_SECONDS and (key[0][0] == "firestore" or hit[1] is db):
        return [dict(r) for r in hit[2]]
    out: list[dict[str, Any]] = []
    for snap in (
        db.collection(STAGE_HISTORY_COLLECTION)
        .where("effectiveAt", ">=", ny_midnight_utc(start_day))
        .where("effectiveAt", "<", ny_midnight_utc(end_day_exclusive))
        .stream()
    ):
        d = snap.to_dict() or {}
        if compact(d.get("changeType")) != "stage_transition":
            continue
        if stage_key(d.get("toStageName")) != REVIVAL_TARGET_STAGE_KEY or not compact(d.get("fromStageId") or d.get("fromStageName")):
            continue
        at = as_utc(d.get("effectiveAt"))
        opp_id = base_opportunity_id(d.get("cycleOf") or d.get("opportunityId"))
        if at is None or not opp_id:
            continue
        day = at.astimezone(NY).date()
        out.append(
            {
                "_id": f"{opp_id}_{day.isoformat()}_{OWNER_REVIVAL}",
                "source": OWNER_REVIVAL,
                "opportunityId": opp_id,
                "contactId": compact(d.get("contactId")),
                "pipelineId": compact(d.get("pipelineId")),
                "rebookDate": day.isoformat(),
                "effectiveAt": at,
                "priorStageId": compact(d.get("fromStageId")),
                "priorStageName": compact(d.get("fromStageName")),
                "priorOwnerId": compact(d.get("fromAssignedTo")),
                "ownerAtRebook": compact(d.get("toAssignedTo")),
            }
        )
    if len(_REVIVAL_CACHE) > 32:
        _REVIVAL_CACHE.clear()
    _REVIVAL_CACHE[key] = (now, db if key[0][0] == "object" else None, [dict(r) for r in out])
    return out


def load_stage_pipelines(db: Any) -> dict[str, str]:
    """Stage id -> pipeline name, from ghl_pipelines_v2 (about 10 docs)."""
    out: dict[str, str] = {}
    for snap in db.collection(PIPELINE_COLLECTION).stream():
        d = snap.to_dict() or {}
        pname = compact(d.get("name"))
        for st in d.get("stages") or []:
            if isinstance(st, dict) and compact(st.get("id")):
                out[compact(st.get("id"))] = pname
    return out


def revival_prior_qualifies(log: dict, stage_pipelines: dict[str, str]) -> tuple[bool, str]:
    pkey = stage_key(stage_pipelines.get(compact(log.get("priorStageId")), ""))
    if pkey.startswith(SWEEPER_PIPELINE_KEY):
        return False, "prior_sweeper_pipeline"
    if pkey in HOLDING_PIPELINE_KEYS:
        return True, "holding_pipeline"
    return prior_stage_qualifies(log.get("priorStageName"), None)


def revival_gap_days(opp: dict, revived_at: datetime) -> int | None:
    """Days from the last appointment before the revival (else createdAt) to it."""
    last = as_utc(opp.get("appointmentOccurredAt"))
    if last is None or last >= revived_at:
        last = as_utc(opp.get("createdAt"))
    if last is None:
        return None
    return (revived_at.astimezone(NY).date() - last.astimezone(NY).date()).days


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
    hub_logs = load_rebook_logs(db, scan_from, end_day)
    for l in hub_logs:
        l.setdefault("source", BOOKING_HUB)
    hub_opps = {base_opportunity_id(l.get("opportunityId")) for l in hub_logs}
    candidates = [r for r in load_owner_revivals(db, scan_from, end_day) if compact(r.get("opportunityId")) not in hub_opps]
    result.logs_scanned = len(hub_logs) + len(candidates)

    revivals: list[dict[str, Any]] = []
    if candidates:
        stage_pipelines = load_stage_pipelines(db)
        for r in candidates:  # cheap filters before any opp/contact read
            in_window = start_day <= (parse_ymd(r.get("rebookDate")) or scan_from) < end_day
            ok, why = revival_prior_qualifies(r, stage_pipelines)
            if ok and not r.get("ownerAtRebook"):
                ok, why = False, "revival_owner_missing"
            elif ok and r.get("priorOwnerId") and r.get("priorOwnerId") != r.get("ownerAtRebook"):
                ok, why = False, "revival_owner_changed"
            if ok:
                revivals.append(r)
            elif in_window:
                result.skip(why)
    logs = hub_logs + revivals
    if not logs:
        return result

    opps = load_docs(db, OPP_COLLECTION, (l.get("opportunityId") for l in logs))
    contacts = load_contacts(db, [compact(l.get("contactId")) for l in logs if compact(l.get("contactId"))])
    credited_month: set[tuple[str, str]] = set()
    already = {compact(c) for c in (already_credited_contact_ids or set())}

    def order(l: dict) -> tuple:
        return (compact(l.get("rebookDate")), l.get("source") == OWNER_REVIVAL, compact(l.get("_id")))

    for log in sorted(logs, key=order):
        day = parse_ymd(log.get("rebookDate"))
        if day is None:
            result.skip("bad_rebook_date")
            continue
        in_window = start_day <= day < end_day
        is_revival = log.get("source") == OWNER_REVIVAL
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
        if is_revival:
            if sweeper_last_name(contact, opp):
                skip("sweeper_rehash_filled")
                continue
            created = as_utc(opp.get("createdAt"))
            if created and month_key(created.astimezone(NY).date()) == month_key(day):
                skip("revival_opportunity_created_this_month")
                continue
            gap = revival_gap_days(opp, as_utc(log.get("effectiveAt")) or ny_midnight_utc(day))
            if gap is None or gap < MIN_DAYS_SINCE_LAST_APPOINTMENT:
                skip("last_appointment_under_14_days")
                continue
            owner_id = compact(log.get("ownerAtRebook"))
            owner = compact(owner_name(owner_id, ""))
            if not owner or owner.casefold().startswith("unknown") or not last_name(owner):
                skip("revival_owner_unknown")
                continue
            setter = last_name(owner)
            pname = pipeline_name(log.get("pipelineId") or opp.get("pipelineId"))
        else:
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
            owner, owner_id = rebook_consultant(log, opp, owner_name, roster_names or ())
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
                "pipelineId": (compact(log.get("pipelineId")) if is_revival else compact(opp.get("pipelineId"))) or None,
                "pipelineStageId": compact(opp.get("pipelineStageId")) or None,
                "owner": owner or "unassigned",
                "ownerId": owner_id or None,
                "setterLastName": setter[:1].upper() + setter[1:] if setter else setter,
                "leadGenSource": "Self Gen",
                "sweeperRehashLastName": None,
                "leadGenBucket": bucket_of(pname) if bucket_of else "Self Gen",
                "priorStageName": log.get("priorStageName") or log.get("priorStageField"),
                "daysSinceLastAppointment": gap,
                "rebookSource": OWNER_REVIVAL if is_revival else BOOKING_HUB,
            }
        )
    return result
