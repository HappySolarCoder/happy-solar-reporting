# -*- coding: utf-8 -*-

"""Shared exclusion for Apple App Review data in Raydar.

Production Raydar has one demo setter for App Review: team TEST, with
testData/isTestAccount set, territory TEST-appreview-territory, and leads
TEST-appreview-lead-1 through 8 (source test-appreview). The reviewer may
log knocks on those leads.

One helper decides what to drop. Metric code calls it while reading the
Raydar leads, users, and knocks it already loads. It does not start another
collection scan.

A record is test data when any of these is true:
- isTestAccount or testData is true, including nested testData.isTestAccount
  and testData.testData. True, "true", 1, "1", and "yes" count (case-insensitive).
- team is "test" ignoring case and whitespace
- id, leadId, territoryId, territory, or userId starts with "TEST-appreview-"
- source is "test-appreview" ignoring case and whitespace

Knocks by that setter drop too: a lead is excluded when the lead itself
matches, or when a related user id (userId, claimedBy, assignedTo, setterId,
or dispositionHistory[].userId) is a test user. Setter averages and
leaderboards leave that setter out of the denominator.
"""

from __future__ import annotations

from typing import Any

TEST_ID_PREFIX = "TEST-appreview-"
TEST_SOURCE = "test-appreview"
TEST_TEAM = "TEST"

_ID_FIELDS = ("id", "leadId", "territoryId", "userId", "territory")
_RELATED_USER_FIELDS = ("userId", "claimedBy", "assignedTo", "setterId")
_TRUE_FLAG_STRINGS = frozenset({"true", "1", "yes"})


def _flag_is_true(value: Any) -> bool:
    if value is True:
        return True
    if type(value) is int and value == 1:
        return True
    if isinstance(value, str) and value.strip().casefold() in _TRUE_FLAG_STRINGS:
        return True
    return False


def _compact_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(value.split()).casefold()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def has_test_id_prefix(value: Any) -> bool:
    text = _text(value)
    return bool(text) and text.startswith(TEST_ID_PREFIX)


def user_record_keys(doc_id: Any, data: dict[str, Any] | None) -> set[str]:
    """Ids a Raydar user is stored under. Same keys the name maps already use."""

    record = data or {}
    keys: set[str] = set()
    for value in (doc_id, record.get("id"), record.get("userId")):
        text = _text(value)
        if text:
            keys.add(text)
    return keys


def is_raydar_test_record(record: Any, doc_id: Any = None) -> bool:
    """True when this lead, user, knock, or territory is App Review test data."""

    data = record if isinstance(record, dict) else {}
    if _flag_is_true(data.get("isTestAccount")):
        return True

    test_data = data.get("testData")
    if _flag_is_true(test_data):
        return True
    if isinstance(test_data, dict) and (
        _flag_is_true(test_data.get("isTestAccount")) or _flag_is_true(test_data.get("testData"))
    ):
        return True

    if _compact_label(data.get("team")) == _compact_label(TEST_TEAM):
        return True

    if has_test_id_prefix(doc_id):
        return True
    for field in _ID_FIELDS:
        if has_test_id_prefix(data.get(field)):
            return True

    if _compact_label(data.get("source")) == _compact_label(TEST_SOURCE):
        return True
    return False


def related_user_ids(record: Any) -> set[str]:
    """User ids on a lead or knock. History entries are the people who knocked it."""

    if not isinstance(record, dict):
        return set()
    found: set[str] = set()
    for field in _RELATED_USER_FIELDS:
        text = _text(record.get(field))
        if text:
            found.add(text)
    history = record.get("dispositionHistory")
    if isinstance(history, list):
        for entry in history:
            if not isinstance(entry, dict):
                continue
            text = _text(entry.get("userId"))
            if text:
                found.add(text)
    return found


def is_excluded_raydar_record(
    record: Any,
    doc_id: Any = None,
    test_user_ids: set[str] | None = None,
) -> bool:
    """Drop the record, or a knock whose related user is the TEST setter."""

    if is_raydar_test_record(record, doc_id=doc_id):
        return True
    known = test_user_ids or set()
    for user_id in related_user_ids(record):
        if has_test_id_prefix(user_id) or user_id in known:
            return True
    return False


def setter_excluded_from_metrics(row: Any, test_user_ids: set[str] | None = None) -> bool:
    """True when this setter must stay out of averages and leaderboards."""

    if is_raydar_test_record(row):
        return True
    if not isinstance(row, dict):
        return False
    known = test_user_ids or set()
    for field in ("raydar_user_id", "userId"):
        user_id = _text(row.get(field))
        if not user_id:
            continue
        if has_test_id_prefix(user_id) or user_id in known:
            return True
    return False


def average_knocks_per_setter(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    test_user_ids: set[str] | None = None,
) -> float | None:
    """Team average of knocks per setter. The TEST setter is not in the denominator."""

    kept = [row for row in rows if not setter_excluded_from_metrics(row, test_user_ids)]
    if not kept:
        return None
    total = sum(int(row.get("knocks") or 0) for row in kept)
    return total / len(kept)
