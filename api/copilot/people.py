# -*- coding: utf-8 -*-
"""Rep and office slices. Company performance is open; this only picks the named row."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

OFFICE_LABELS = {
    "buffalo": "Buffalo",
    "rochester": "Rochester",
    "syracuse": "Syracuse",
    "virtual": "Virtual",
}
_SKIP = frozenset({"", "none", "null", "n/a", "unassigned", "unknown"})
_COUNT_FIELDS = ("sales", "created", "ran", "sits", "demo_ran")


@dataclass(frozen=True)
class Rep:
    name: str
    kind: str
    sales: int | None = None
    created: int | None = None
    ran: int | None = None
    sits: int | None = None
    demo_ran: int | None = None
    ghl_user_id: str | None = None
    email: str | None = None
    aliases: tuple[str, ...] = ()
    roster_names: tuple[str, ...] = ()


def asks_about_self(text: str) -> bool:
    """'my demos' and 'do I have' are the asker. 'our' and 'we' are the company."""
    return bool(
        re.search(
            r"\b(?:my|mine|myself)\b|\b(?:do|did|have|has|am)\s+i\b|\bi\s+have\b",
            text or "",
            re.I,
        )
    )


def asks_marketing_spend(text: str) -> bool:
    """Inbound CAC, Lead Locker spend, cost per lead, and the other spend figures.

    Bare 'inbound' is a lead source, not spend.
    """
    return bool(
        re.search(
            r"\b(?:inbound\s+cac|lead\s*locker|cost[-\s]?per[-\s]?lead|\bcpl\b|"
            r"marketing\s+spend|ad\s+spend|meta\s+spend|\bspend\b|\bcac\b|\btac\b)\b",
            text or "",
            re.I,
        )
    )


def count_subject(text: str) -> str | None:
    """'how many demos / appointments / sales' asks for a count. A rate question does not."""
    raw = text or ""
    if not re.search(r"\bhow many\b", raw, re.I):
        return None
    if re.search(r"\bdemo[\s-]?rate\b|\bdemorate\b|\bdemo\s*(?:%|percentage|percent|pct)\b", raw, re.I):
        return None
    if re.search(r"\bdemos?\b|\bsits?\b", raw, re.I):
        return "demos"
    if re.search(r"\bappointments?\b|\bran\b", raw, re.I):
        return "appointments"
    if re.search(r"\bsales?\b", raw, re.I):
        return "sales"
    return None


def self_query(identity) -> str | None:
    """Name to match when the asker says 'my' and no user id or email matched.

    Bloom's token may carry an optional signed name. Otherwise the subject slug
    is the only identity this app receives (user_evan → evan).
    """
    named = str(getattr(identity, "display_name", None) or "").strip()
    if named:
        return named
    actor = str(getattr(identity, "actor_id", "") or "")
    if actor.startswith("bloom:"):
        actor = actor[6:]
    actor = re.sub(r"(?i)^user[_-]", "", actor)
    actor = actor.replace("_", " ").replace("-", " ").strip()
    if not actor or actor == "settings_admin":
        return None
    if re.fullmatch(r"[A-Za-z]+(?:\s+[A-Za-z]+)*", actor) is None:
        return None
    return actor


def _parts(name: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", (name or "").casefold()) if part]


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _better_name(current: str, candidate: str) -> bool:
    if not current:
        return True
    if candidate == current:
        return False
    current_score = (0 if current == current.lower() else 1, len(current))
    candidate_score = (0 if candidate == candidate.lower() else 1, len(candidate))
    return candidate_score > current_score


def reps_from_bundle(bundle: dict | None) -> list[Rep]:
    found: list[Rep] = []
    for row in (bundle or {}).get("reps") or []:
        if not isinstance(row, dict):
            continue
        name = " ".join(str(row.get("name") or "").split())
        if not name or name.casefold() in _SKIP:
            continue
        kind = str(row.get("kind") or "rep").strip().lower() or "rep"
        ghl_user_id = " ".join(str(row.get("ghl_user_id") or "").split()) or None
        email = " ".join(str(row.get("email") or "").split()) or None
        alias_values = []
        if isinstance(row.get("full_name"), str):
            alias_values.append(row.get("full_name"))
        raw_aliases = row.get("aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        if isinstance(raw_aliases, (list, tuple)):
            alias_values.extend(raw_aliases)
        aliases: list[str] = []
        for raw in alias_values:
            alias = " ".join(str(raw or "").split())
            if alias and alias.casefold() not in {item.casefold() for item in aliases} and alias.casefold() != name.casefold():
                aliases.append(alias)
        roster_values = row.get("roster_names") or []
        if isinstance(roster_values, str):
            roster_values = [roster_values]
        roster_names: list[str] = []
        if isinstance(roster_values, (list, tuple)):
            for raw in roster_values:
                label = " ".join(str(raw or "").split())
                if label and label.casefold() not in {item.casefold() for item in roster_names}:
                    roster_names.append(label)
        found.append(
            Rep(
                name=name,
                kind=kind,
                sales=_as_int(row.get("sales")),
                created=_as_int(row.get("created")),
                ran=_as_int(row.get("ran")),
                sits=_as_int(row.get("sits")),
                demo_ran=_as_int(row.get("demo_ran")),
                ghl_user_id=ghl_user_id,
                email=email,
                aliases=tuple(aliases),
                roster_names=tuple(roster_names),
            )
        )
    return found


def offices_from_bundle(bundle: dict | None) -> dict[str, dict[str, int | None]]:
    raw = (bundle or {}).get("offices") or {}
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, int | None]] = {}
    for key, row in raw.items():
        label = OFFICE_LABELS.get(str(key).strip().casefold())
        if label is None or not isinstance(row, dict):
            continue
        cleaned[label] = {field: _as_int(row.get(field)) for field in _COUNT_FIELDS}
    return cleaned


def _score(query: str, rep: Rep) -> int:
    asked = _parts(query)
    named = _parts(rep.name)
    if not asked or not named:
        return 0
    if asked == named:
        return 100
    if len(asked) == 1:
        token = asked[0]
        if token == named[-1]:
            return 80
        if len(named) > 1 and token == named[0]:
            return 70
        if len(token) >= 4 and any(part.startswith(token) for part in named):
            return 60
        return 0
    if all(any(part == token or (len(token) >= 4 and part.startswith(token)) for part in named) for token in asked):
        return 90
    return 0


def _last_token(name: str) -> str:
    parts = _parts(name)
    return parts[-1] if parts else ""


def _role_payload(rep: Rep) -> dict[str, Any]:
    return {
        "kind": rep.kind,
        "name": rep.name,
        "sales": rep.sales,
        "created": rep.created,
        "ran": rep.ran,
        "sits": rep.sits,
        "demo_ran": rep.demo_ran,
    }


def _fuller_name(reps: list[Rep]) -> str:
    return max((rep.name for rep in reps), key=lambda name: (len(_parts(name)), len(name)))


def _applied(
    rep: Rep,
    roles: list[Rep] | None = None,
    label: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    group = roles or [rep]
    if len(group) < 2:
        result = {"status": "applied", "label": label or rep.name, "kind": rep.kind, "rep": rep}
    else:
        primary = next((item for item in group if item.kind == "closer" and item.sits is not None), None)
        if primary is None:
            primary = next((item for item in group if item.sits is not None), group[0])
        kinds = {item.kind for item in group}
        result = {
            "status": "applied",
            "label": _fuller_name(group),
            "kind": "both" if len(kinds) > 1 else primary.kind,
            "primary_kind": primary.kind,
            "rep": primary,
            "roles": [_role_payload(item) for item in group],
        }
    if reason:
        result["reason"] = reason
    return result


def _same_person(left: Rep, right: Rep) -> bool:
    """Closer identity is assignedTo. Setter identity is the resolved roster user id."""
    user_id = (left.ghl_user_id or "").strip()
    other = (right.ghl_user_id or "").strip()
    return bool(user_id) and user_id == other


def _person_key(rep: Rep) -> str:
    user_id = (rep.ghl_user_id or "").strip()
    if user_id:
        return "id:" + user_id
    return "row:" + rep.kind + ":" + rep.name.casefold()


def _group_people(reps: list[Rep]) -> list[list[Rep]]:
    groups: list[list[Rep]] = []
    for rep in reps:
        key = _person_key(rep)
        for group in groups:
            if _person_key(group[0]) == key:
                group.append(rep)
                break
        else:
            groups.append([rep])
    return groups


def _identity_partner(rep: Rep, reps: list[Rep]) -> Rep | None:
    """The other role only when both rows resolved to the same person."""
    if rep.kind not in {"setter", "closer"} or not (rep.ghl_user_id or "").strip():
        return None
    others = [
        other
        for other in reps
        if other is not rep and other.kind in {"setter", "closer"} and other.kind != rep.kind and _same_person(rep, other)
    ]
    if len(others) == 1:
        return others[0]
    return None


def _speak_name(rep: Rep) -> str:
    if len(_parts(rep.name)) == 1 and len(rep.aliases) == 1:
        return rep.aliases[0]
    return rep.name


def _option_label(rep: Rep, group: list[Rep]) -> str:
    spoken = _speak_name(rep)
    names = [_speak_name(item).casefold() for item in group]
    if names.count(spoken.casefold()) > 1:
        role = "setter" if rep.kind == "setter" else "closer" if rep.kind == "closer" else rep.kind
        return f"{spoken} the {role}"
    return spoken


def _display_query(query: str) -> str:
    parts = [part for part in (query or "").split() if part]
    shown = []
    for part in parts:
        shown.append(part[:1].upper() + part[1:] if part else part)
    return " ".join(shown)


def _ambiguous(query: str, reps: list[Rep]) -> dict[str, Any]:
    options = [_option_label(rep, reps) for rep in reps]
    unique: list[str] = []
    for option in options:
        if option not in unique:
            unique.append(option)
    if len(unique) == 1 and len(reps) > 1:
        unique = [f"{unique[0]} ({reps[0].kind})", f"{unique[0]} ({reps[1].kind})"]
    listed = " or ".join(unique) if len(unique) == 2 else ", ".join(unique[:-1]) + ", or " + unique[-1]
    return {
        "status": "ambiguous",
        "label": query,
        "options": unique,
        "reason": f"I'm not sure if you mean {listed}. Which rep did you mean?",
    }


def _roster_listed(rep: Rep) -> list[str]:
    """Names the roster listed for this row, including a last-name-only display name."""
    names: list[str] = []
    seen: set[str] = set()
    for raw in (*rep.roster_names, *rep.aliases):
        label = " ".join(str(raw or "").split())
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        names.append(label)
    return names


def _pick_roster_name(options: list[str], last: str) -> str:
    exact = [name for name in options if len(_parts(name)) == 2 and _last_token(name) == last]
    if len(exact) == 1:
        return exact[0]
    return min(options, key=lambda name: (len(_parts(name)), len(name)))


def _ambiguous_names(query: str, options: list[str]) -> dict[str, Any]:
    unique: list[str] = []
    for option in options:
        if option not in unique:
            unique.append(option)
    listed = " or ".join(unique) if len(unique) == 2 else ", ".join(unique[:-1]) + ", or " + unique[-1]
    return {
        "status": "ambiguous",
        "label": query,
        "options": unique,
        "reason": f"I'm not sure if you mean {listed}. Which rep did you mean?",
    }


def _mismatched_first_name(query: str, rep: Rep) -> tuple[str | None, str | None, list[str] | None]:
    """Label and caveat when a last-name row's roster name disagrees with the question.

    No roster metadata keeps the asked name and adds no caveat. A roster first
    name that differs still uses that person's number, under the roster name.
    Several different roster first names are ambiguous. A roster record with no
    first name keeps the last-name label and the standard caveat.
    """
    shown = _display_query(query)
    asked = _parts(shown)
    if len(asked) < 2 or _last_token(shown) != _last_token(rep.name):
        return None, None, None
    listed = _roster_listed(rep)
    if not listed:
        if len(asked) > len(_parts(rep.name)):
            return shown, None, None
        return None, None, None
    with_first = [name for name in listed if len(_parts(name)) >= 2]
    if not with_first:
        return rep.name, f"I couldn't confirm {shown}, so this is {rep.name}", None
    by_first: dict[str, list[str]] = {}
    for name in with_first:
        by_first.setdefault(_parts(name)[0], []).append(name)
    if asked[0] in by_first:
        return _pick_roster_name(by_first[asked[0]], asked[-1]), None, None
    if len(by_first) == 1:
        chosen = _pick_roster_name(with_first, asked[-1])
        return (
            chosen,
            f"I don't see a {shown}, so this is {chosen}. If you meant someone else, let me know.",
            None,
        )
    options = [_pick_roster_name(names, asked[-1]) for names in by_first.values()]
    return None, None, options


def _resolve(query: str, winners: list[Rep], reps: list[Rep], *, prefer_query: bool = False) -> dict[str, Any]:
    """One person, including both roles when the ids match. Different people stay apart."""
    groups = _group_people(winners)
    if len(groups) > 1:
        return _ambiguous(query, [group[0] for group in groups])
    group = list(groups[0])
    label = None
    reason = None
    if prefer_query:
        label, reason, options = _mismatched_first_name(query, group[0])
        if options:
            return _ambiguous_names(query, options)
    partner = _identity_partner(group[0], reps)
    if partner is not None and partner not in group:
        group.append(partner)
    if len(group) == 1 and label is None:
        shown = _display_query(query)
        matched_alias = next((alias for alias in group[0].aliases if _parts(alias) == _parts(shown)), "")
        if matched_alias and len(_parts(matched_alias)) > len(_parts(group[0].name)):
            label = matched_alias
    applied = _applied(group[0], group, label=label, reason=reason)
    if reason and len(group) > 1:
        spoken = str(applied.get("label") or "")
        shown = _display_query(query)
        spoken_first = _parts(spoken)[:1]
        asked_first = _parts(shown)[:1]
        if spoken and spoken_first != asked_first:
            if reason.startswith("I don't see a "):
                applied["reason"] = (
                    f"I don't see a {shown}, so this is {spoken}. If you meant someone else, let me know."
                )
            elif reason.startswith("I couldn't confirm "):
                applied["reason"] = f"I couldn't confirm {shown}, so this is {spoken}"
    return applied


def _exact_reps(query: str, reps: list[Rep]) -> list[Rep]:
    asked = _parts(query)
    found = []
    for rep in reps:
        names = [rep.name, *rep.aliases]
        if any(_parts(name) == asked for name in names):
            found.append(rep)
    return found


def _last_name_rows(query: str, reps: list[Rep]) -> list[Rep]:
    """Setter rows store a last name. A full-name query can match that one row."""
    asked = _parts(query)
    if len(asked) < 2:
        return []
    last = asked[-1]
    return [
        rep
        for rep in reps
        if _last_token(rep.name) == last and (len(_parts(rep.name)) == 1 or _parts(rep.name) == asked)
    ]


def match_rep(query: str, reps: list[Rep]) -> dict[str, Any]:
    """One rep, or an ambiguity the reply can name. Missing stays unresolved.

    A full name resolves to a setter's last-name row when that last name is unique.
    A shared last name is one person only when the closer user id and the setter
    identity are the same. Otherwise the reply names the options.
    """
    asked = _parts(query)
    if not asked:
        return {"status": "missing", "label": query}
    if len(asked) == 1:
        last_hits = [rep for rep in reps if _last_token(rep.name) == asked[0]]
        if len(_group_people(last_hits)) > 1:
            return _ambiguous(query, [group[0] for group in _group_people(last_hits)])
    exact = _exact_reps(query, reps)
    if exact:
        return _resolve(query, exact, reps)
    last_rows = _last_name_rows(query, reps)
    if last_rows:
        return _resolve(query, last_rows, reps, prefer_query=True)
    scored = [(_score(query, rep), rep) for rep in reps]
    scored = [(score, rep) for score, rep in scored if score > 0]
    if not scored:
        return {"status": "missing", "label": query}
    best = max(score for score, _rep in scored)
    winners = [rep for score, rep in scored if score == best]
    return _resolve(query, winners, reps)


def match_signed_in(claims: dict | None, reps: list[Rep]) -> dict[str, Any]:
    """Who is asking. GHL user id, then email, then the signed name.

    The user id matches the closer on the opportunity (assignedTo). Email matches
    the GHL user email. The name matches closers and setters.
    """
    claims = claims or {}
    user_id = str(claims.get("ghl_user_id") or "").strip()
    if user_id:
        hits = [rep for rep in reps if rep.kind == "closer" and rep.ghl_user_id == user_id]
        if len(hits) == 1:
            return _applied(hits[0])
        if len(hits) > 1:
            return match_rep(hits[0].name, hits)
    email = str(claims.get("email") or "").strip().casefold()
    if email and "@" in email:
        hits = [rep for rep in reps if rep.kind == "closer" and (rep.email or "").casefold() == email]
        if len(hits) == 1:
            return _applied(hits[0])
        if len(hits) > 1:
            return match_rep(hits[0].name, hits)
    name = str(claims.get("name") or "").strip()
    if name:
        return match_rep(name, reps)
    return {"status": "missing", "label": name or "you"}


def match_office(query: str, offices: dict[str, dict[str, int | None]]) -> dict[str, Any]:
    label = OFFICE_LABELS.get((query or "").strip().casefold(), query)
    row = offices.get(label)
    if row is None:
        return {"status": "missing", "label": label}
    return {"status": "applied", "label": label, "kind": "office", "office": row}


def slice_counts(rep: Rep | None = None, office: dict | None = None) -> dict[str, int | None]:
    if rep is not None:
        return {field: getattr(rep, field) for field in _COUNT_FIELDS}
    return {field: (office or {}).get(field) for field in _COUNT_FIELDS}


def apply_counts(bundle: dict, counts: dict[str, int | None]) -> dict:
    """Replace the company totals with one rep or office. Missing demos stay missing."""
    scoped = dict(bundle)
    for field in ("sales", "created", "ran"):
        if counts.get(field) is not None:
            scoped[field] = counts[field]
    if counts.get("sits") is None:
        scoped["sits"] = None
        scoped["demo_ran"] = None
        scoped["demo_counts_missing"] = True
    else:
        scoped["sits"] = counts["sits"]
        scoped["demo_ran"] = counts["demo_ran"] if counts.get("demo_ran") is not None else counts.get("ran")
        scoped["demo_counts_missing"] = False
    for key in (
        "sales_by_source",
        "ran_by_source",
        "created_by_source",
        "sit_by_source",
        "demo_ran_by_source",
    ):
        scoped[key] = {}
    return scoped


def roster_rows_from_breakdowns(
    *,
    sales: dict | None = None,
    ran: dict | None = None,
    created: dict | None = None,
    demo: dict | None = None,
    owner_profiles: list[dict[str, Any]] | None = None,
    setter_profiles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Closer rows from owner maps, setter rows from last-name maps. Totals are untouched."""
    index: dict[tuple[str, str], dict[str, Any]] = {}

    def add(name: Any, kind: str, field: str, value: Any) -> None:
        label = " ".join(str(name or "").split())
        if not label or label.casefold() in _SKIP:
            return
        amount = _as_int(value)
        if amount is None:
            return
        key = (kind, label.casefold())
        row = index.get(key)
        if row is None:
            row = {"name": label, "kind": kind, "sales": None, "created": None, "ran": None, "sits": None, "demo_ran": None}
            index[key] = row
        elif _better_name(row["name"], label):
            row["name"] = label
        row[field] = amount

    sales_b = (sales or {}).get("breakdowns") or {}
    ran_b = (ran or {}).get("breakdowns") or {}
    created_b = (created or {}).get("breakdowns") or {}
    demo_b = (demo or {}).get("breakdowns") or {}
    for name, value in (sales_b.get("sales_by_owner") or {}).items():
        add(name, "closer", "sales", value)
    for name, value in (sales_b.get("sales_by_setter_last_name") or {}).items():
        add(name, "setter", "sales", value)
    for name, value in (ran_b.get("ran_by_owner") or {}).items():
        add(name, "closer", "ran", value)
    for name, value in (ran_b.get("ran_by_setter_last_name") or {}).items():
        add(name, "setter", "ran", value)
    for name, value in (created_b.get("created_by_owner") or {}).items():
        add(name, "closer", "created", value)
    for name, value in (created_b.get("created_by_setter_last_name") or {}).items():
        add(name, "setter", "created", value)
    for name, value in (demo_b.get("sit_by_owner") or {}).items():
        add(name, "closer", "sits", value)
    for name, value in (demo_b.get("ran_by_owner") or {}).items():
        add(name, "closer", "demo_ran", value)
    for name, value in (demo_b.get("sit_by_setter_last_name") or {}).items():
        add(name, "setter", "sits", value)
    for name, value in (demo_b.get("ran_by_setter_last_name") or {}).items():
        add(name, "setter", "demo_ran", value)
    profiles: dict[str, list[dict[str, Any]]] = {}
    for profile in owner_profiles or []:
        if not isinstance(profile, dict):
            continue
        label = " ".join(str(profile.get("name") or "").split())
        if not label:
            continue
        profiles.setdefault(label.casefold(), []).append(profile)
    rows = list(index.values())
    for row in rows:
        if row["kind"] == "closer" and row.get("demo_ran") is not None and row.get("sits") is None:
            row["sits"] = 0
        if row["kind"] != "closer":
            continue
        hits = profiles.get(str(row["name"]).casefold()) or []
        ids = {str(hit.get("ghl_user_id") or "").strip() for hit in hits if str(hit.get("ghl_user_id") or "").strip()}
        emails = {str(hit.get("email") or "").strip() for hit in hits if str(hit.get("email") or "").strip()}
        if len(ids) == 1:
            row["ghl_user_id"] = next(iter(ids))
        if len(emails) == 1:
            row["email"] = next(iter(emails))
    by_last: dict[str, list[dict[str, Any]]] = {}
    for profile in setter_profiles or []:
        if not isinstance(profile, dict):
            continue
        last = " ".join(str(profile.get("last_name") or "").split())
        if not last:
            continue
        by_last.setdefault(last.casefold(), []).append(profile)
    for row in rows:
        if row["kind"] != "setter":
            continue
        hits = by_last.get(str(row["name"]).casefold()) or []
        aliases: list[str] = []
        roster_names: list[str] = []
        ids: set[str] = set()
        emails: set[str] = set()
        for hit in hits:
            full = " ".join(str(hit.get("full_name") or "").split())
            if full and full.casefold() not in {item.casefold() for item in roster_names}:
                roster_names.append(full)
            if full and full.casefold() != str(row["name"]).casefold() and full not in aliases:
                aliases.append(full)
            user_id = str(hit.get("ghl_user_id") or "").strip()
            email = str(hit.get("email") or "").strip()
            if user_id:
                ids.add(user_id)
            if email:
                emails.add(email)
        if roster_names:
            row["roster_names"] = roster_names
        if aliases:
            row["aliases"] = aliases
        if len(ids) == 1:
            row["ghl_user_id"] = next(iter(ids))
        if len(emails) == 1:
            row["email"] = next(iter(emails))
    return rows


def office_rows_from_breakdowns(
    *,
    sales: dict | None = None,
    ran: dict | None = None,
    created: dict | None = None,
    demo: dict | None = None,
) -> dict[str, dict[str, int | None]]:
    offices: dict[str, dict[str, int | None]] = {}

    def add(label: Any, field: str, value: Any) -> None:
        key = OFFICE_LABELS.get(str(label or "").strip().casefold())
        if key is None:
            return
        amount = _as_int(value)
        if amount is None:
            return
        row = offices.setdefault(
            key,
            {"sales": None, "created": None, "ran": None, "sits": None, "demo_ran": None},
        )
        row[field] = amount

    sales_b = (sales or {}).get("breakdowns") or {}
    ran_b = (ran or {}).get("breakdowns") or {}
    created_b = (created or {}).get("breakdowns") or {}
    demo_b = (demo or {}).get("breakdowns") or {}
    for name, value in (sales_b.get("sales_by_pipeline") or {}).items():
        add(name, "sales", value)
    for name, value in (ran_b.get("ran_by_pipeline") or {}).items():
        add(name, "ran", value)
    for name, value in (created_b.get("created_by_pipeline") or {}).items():
        add(name, "created", value)
    for name, value in (demo_b.get("sit_by_pipeline") or {}).items():
        add(name, "sits", value)
    for name, value in (demo_b.get("ran_by_pipeline") or {}).items():
        add(name, "demo_ran", value)
    return offices
