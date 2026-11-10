# -*- coding: utf-8 -*-

"""Half-hour Eastern knock buckets for the Daily Dashboard chart."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from time_on_doors import (  # noqa: E402
    aggregate_time_on_doors,
    knock_time_chart,
    time_on_doors_table,
)

DAILY_PATH = API / "daily_update.py"
RAYDAR_PATH = METRICS / "raydar_doors_knocked.py"
DASH = "\u2013"


def utc(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def series_map(chart: dict) -> dict[str, list[int]]:
    return {row["name"]: list(row["counts"]) for row in chart["series"]}


def repeat(actor: str, moment: datetime, count: int) -> list[tuple[str, datetime]]:
    return [(actor, moment.replace(second=index % 60)) for index in range(count)]


class KnockTimeBucketTests(unittest.TestCase):
    def test_summer_and_winter_clocks_are_eastern_and_not_cumulative(self):
        names = {"bo": "Bo Hill", "ada": "Ada Cole"}
        summer = (
            repeat("bo", utc(2026, 7, 16, 19, 5), 20)
            + repeat("bo", utc(2026, 7, 16, 19, 35), 30)
            + repeat("ada", utc(2026, 7, 16, 21, 5), 2)
        )
        chart = knock_time_chart(summer, names)
        self.assertEqual(chart["timezone"], "America/New_York")
        self.assertEqual(chart["bucket_minutes"], 30)
        self.assertEqual(
            [bucket["label"] for bucket in chart["buckets"]],
            [
                f"3:00{DASH}3:30 PM",
                f"3:30{DASH}4:00 PM",
                f"4:00{DASH}4:30 PM",
                f"4:30{DASH}5:00 PM",
                f"5:00{DASH}5:30 PM",
            ],
        )
        self.assertTrue(chart["buckets"][0]["start"].endswith("-04:00"))
        counts = series_map(chart)
        # 20 then 30, not a running total of 50. The quiet hours are zeros.
        self.assertEqual(counts["Bo Hill"], [20, 30, 0, 0, 0])
        self.assertEqual(counts["Ada Cole"], [0, 0, 0, 0, 2])
        self.assertEqual(sum(counts["Bo Hill"]), 50)
        self.assertNotEqual(counts["Bo Hill"][-1], 50)

        winter = knock_time_chart([("bo", utc(2026, 1, 15, 20, 10))], names)
        self.assertEqual(winter["buckets"][0]["label"], f"3:00{DASH}3:30 PM")
        self.assertTrue(winter["buckets"][0]["start"].endswith("-05:00"))
        self.assertEqual(series_map(winter)["Bo Hill"], [1])

    def test_exact_boundary_starts_the_next_bucket(self):
        chart = knock_time_chart(
            [
                ("bo", utc(2026, 7, 16, 19, 29, 59)),
                ("bo", utc(2026, 7, 16, 19, 30, 0)),
            ],
            {"bo": "Bo Hill"},
        )
        self.assertEqual(
            [bucket["label"] for bucket in chart["buckets"]],
            [f"3:00{DASH}3:30 PM", f"3:30{DASH}4:00 PM"],
        )
        self.assertEqual(series_map(chart)["Bo Hill"], [1, 1])

    def test_spring_forward_skips_the_missing_hour(self):
        # 2026-03-08: 1:50 AM EST and 3:10 AM EDT. 2:00–3:00 AM does not exist.
        chart = knock_time_chart(
            [
                ("bo", utc(2026, 3, 8, 6, 50)),
                ("bo", utc(2026, 3, 8, 6, 55)),
                ("ada", utc(2026, 3, 8, 7, 10)),
            ],
            {"bo": "Bo Hill", "ada": "Ada Cole"},
        )
        labels = [bucket["label"] for bucket in chart["buckets"]]
        self.assertEqual(labels, [f"1:30{DASH}2:00 AM", f"3:00{DASH}3:30 AM"])
        self.assertNotIn(f"2:00{DASH}2:30 AM", labels)
        self.assertNotIn(f"2:30{DASH}3:00 AM", labels)
        self.assertTrue(chart["buckets"][0]["start"].endswith("-05:00"))
        self.assertTrue(chart["buckets"][1]["start"].endswith("-04:00"))
        counts = series_map(chart)
        self.assertEqual(counts["Bo Hill"], [2, 0])
        self.assertEqual(counts["Ada Cole"], [0, 1])

    def test_fall_back_keeps_both_hours_and_zero_fills_between_fmas(self):
        # 2026-11-01: 1:00–2:00 AM happens twice. Each occurrence is its own bucket.
        chart = knock_time_chart(
            [
                ("bo", utc(2026, 11, 1, 5, 10)),
                ("bo", utc(2026, 11, 1, 5, 40)),
                ("bo", utc(2026, 11, 1, 6, 10)),
                ("ada", utc(2026, 11, 1, 6, 50)),
            ],
            {"bo": "Bo Hill", "ada": "Ada Cole"},
        )
        self.assertEqual(
            [bucket["label"] for bucket in chart["buckets"]],
            [
                f"1:00{DASH}1:30 AM EDT",
                f"1:30{DASH}2:00 AM EDT",
                f"1:00{DASH}1:30 AM EST",
                f"1:30{DASH}2:00 AM EST",
            ],
        )
        self.assertTrue(chart["buckets"][0]["start"].endswith("-04:00"))
        self.assertTrue(chart["buckets"][2]["start"].endswith("-05:00"))
        counts = series_map(chart)
        self.assertEqual(counts["Bo Hill"], [1, 1, 1, 0])
        self.assertEqual(counts["Ada Cole"], [0, 0, 0, 1])
        self.assertEqual(sum(counts["Bo Hill"]), 3)

    def test_same_display_name_merges_and_sort_matches_time_on_doors(self):
        events = [
            ("id-a", utc(2026, 7, 16, 13, 0)),
            ("id-b", utc(2026, 7, 16, 18, 0)),
            ("id-c", utc(2026, 7, 16, 14, 0)),
        ]
        names = {"id-a": "Sam Rivera", "id-b": "Sam Rivera", "id-c": "Ada Cole"}
        chart = knock_time_chart(events, names)
        table = time_on_doors_table(aggregate_time_on_doors(events), names)
        self.assertEqual([row["name"] for row in chart["series"]], [row["name"] for row in table])
        self.assertEqual([row["name"] for row in table], ["Sam Rivera", "Ada Cole"])
        counts = series_map(chart)
        self.assertEqual(sum(counts["Sam Rivera"]), 2)
        self.assertEqual(sum(counts["Ada Cole"]), 1)
        self.assertTrue(any(value == 0 for value in counts["Ada Cole"]))

    def test_two_calendar_days_do_not_share_a_clock_bucket(self):
        chart = knock_time_chart(
            [
                ("bo", utc(2026, 7, 16, 19, 5)),
                ("bo", utc(2026, 7, 17, 19, 5)),
            ],
            {"bo": "Bo Hill"},
        )
        labels = [bucket["label"] for bucket in chart["buckets"]]
        counts = series_map(chart)["Bo Hill"]
        self.assertTrue(labels[0].startswith(f"Jul 16, 3:00{DASH}3:30 PM"))
        self.assertTrue(labels[-1].startswith(f"Jul 17, 3:00{DASH}3:30 PM"))
        self.assertEqual(counts[0], 1)
        self.assertEqual(counts[-1], 1)
        self.assertGreater(len(counts), 2)
        self.assertIn(0, counts)
        self.assertEqual(sum(counts), 2)

    def test_missing_timestamp_does_not_invent_a_bucket(self):
        chart = knock_time_chart([("bo", None), ("bo", "")])
        self.assertEqual(chart["buckets"], [])
        self.assertEqual(chart["series"], [{"name": "bo", "counts": []}])
        self.assertEqual(knock_time_chart([]), {
            "timezone": "America/New_York",
            "bucket_minutes": 30,
            "buckets": [],
            "series": [],
        })


def _load(name: str, path: Path):
    if "google.cloud" not in sys.modules:
        cloud = types.ModuleType("google.cloud")
        cloud.firestore = MagicMock()
        google_mod = sys.modules.get("google") or types.ModuleType("google")
        google_mod.cloud = cloud
        oauth2 = types.ModuleType("google.oauth2")
        oauth2.service_account = MagicMock()
        sys.modules["google"] = google_mod
        sys.modules["google.cloud"] = cloud
        sys.modules["google.cloud.firestore"] = cloud.firestore
        sys.modules["google.oauth2"] = oauth2
        sys.modules["google.oauth2.service_account"] = oauth2.service_account
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Snap:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Col:
    def __init__(self, docs: list[_Snap]):
        self.docs = docs
        self.ops: list[tuple] = []

    def where(self, *args, **_kwargs):
        self.ops.append(("where", args))
        return self

    def order_by(self, *args, **_kwargs):
        self.ops.append(("order_by", args))
        return self

    def limit(self, count: int):
        return _Col(self.docs[:count])

    def stream(self):
        return iter(self.docs)


class _Db:
    def __init__(self, collections: dict[str, list[_Snap]]):
        self.collections = {name: _Col(docs) for name, docs in collections.items()}

    def collection(self, name: str):
        return self.collections.setdefault(name, _Col([]))


class RaydarChartPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(METRICS) not in sys.path:
            sys.path.insert(0, str(METRICS))
        cls.doors = _load("raydar_doors_knocked_time_chart", RAYDAR_PATH)
        cls.daily = _load("daily_update_knock_time_chart", DAILY_PATH)

    def test_payload_reuses_counted_knocks_from_the_same_read(self):
        later = utc(2026, 7, 16, 21, 5)
        leads = [
            _Snap(
                "kept",
                {
                    "dispositionedAt": later,
                    "claimedBy": "bo",
                    "dispositionHistory": [
                        {"userId": "bo", "disposition": "Not Home", "timestamp": later},
                        {"userId": "bo", "disposition": "Go Back", "timestamp": utc(2026, 7, 16, 19, 40)},
                        {"userId": "bo", "disposition": "Not Home", "timestamp": utc(2026, 7, 16, 19, 6)},
                        {"userId": "bo", "disposition": "Not Home", "timestamp": utc(2026, 7, 16, 19, 5)},
                    ],
                },
            ),
            _Snap(
                "ada",
                {
                    "dispositionedAt": utc(2026, 7, 16, 19, 10),
                    "claimedBy": "ada",
                    "dispositionHistory": [
                        {"userId": "ada", "disposition": "Not Home", "timestamp": utc(2026, 7, 16, 19, 10)},
                    ],
                },
            ),
            _Snap(
                "shade",
                {
                    "dispositionedAt": utc(2026, 7, 16, 19, 20),
                    "claimedBy": "bo",
                    "dispositionHistory": [
                        {"userId": "bo", "disposition": "Shade DQ", "timestamp": utc(2026, 7, 16, 19, 20)},
                    ],
                },
            ),
            _Snap(
                "solar",
                {
                    "dispositionedAt": utc(2026, 7, 16, 20, 0),
                    "claimedBy": "ada",
                    "dispositionHistory": [
                        {"userId": "ada", "disposition": "Already Has Solar", "timestamp": utc(2026, 7, 16, 20, 0)},
                    ],
                },
            ),
        ]
        dispositions = [
            _Snap("not-home", {"name": "Not Home", "countsAsDoorKnock": True}),
            _Snap("go-back", {"name": "Go Back", "countsAsDoorKnock": True}),
            _Snap("shade-dq", {"name": "Shade DQ", "countsAsDoorKnock": False}),
            _Snap("has-solar", {"name": "Has Solar", "countsAsDoorKnock": False}),
            _Snap("already-has-solar", {"name": "Already Has Solar", "countsAsDoorKnock": False}),
        ]
        db = _Db(
            {
                "raydar_leads_v1": leads,
                "raydar_users_v1": [
                    _Snap("bo", {"name": "Bo Hill"}),
                    _Snap("ada", {"name": "Ada Cole"}),
                ],
                "raydar_dispositions_v1": dispositions,
            }
        )
        payload = self.doors.build_payload(db, 2026, 7, start="2026-07-16", end="2026-07-16")
        self.assertEqual(payload["breakdowns"]["knocks_by_actor"], {"bo": 3, "ada": 1})
        chart = payload["knocks_by_time"]
        counts = series_map(chart)
        self.assertEqual(counts["Bo Hill"], [1, 1, 0, 0, 1])
        self.assertEqual(counts["Ada Cole"], [1, 0, 0, 0, 0])
        self.assertEqual(sum(counts["Bo Hill"]), 3)
        self.assertEqual(chart["buckets"][0]["label"], f"3:00{DASH}3:30 PM")
        self.assertEqual(
            set(db.collections),
            # The counts-only events mirror is read once (absent here, so it adds nothing).
            {"raydar_leads_v1", "raydar_users_v1", "raydar_dispositions_v1", "raydar_field_knock_events_v1"},
        )
        wheres = [op for op in db.collections["raydar_leads_v1"].ops if op[0] == "where"]
        self.assertEqual(len(wheres), 2)
        self.assertEqual(wheres[1][1][2] - wheres[0][1][2], timedelta(days=1 + 45))

        src = RAYDAR_PATH.read_text(encoding="utf-8")
        self.assertLess(src.find("door_knock_times.append"), src.find("manual_knock_adjustments"))
        self.assertIn("knock_time_chart(door_knock_times, users)", src)

    def test_chart_sits_directly_under_time_on_doors(self):
        html = self.daily.HTML
        time_on = html.find('id="tblTimeOnDoors"')
        chart = html.find('id="knockTimeChart"')
        powerline = html.find('id="tblPowerline"')
        self.assertGreater(time_on, -1)
        self.assertLess(time_on, chart)
        self.assertLess(chart, powerline)
        self.assertIn("FMA Knocks by Time", html)
        self.assertIn("knocks?.knocks_by_time", html)
        self.assertIn("renderKnockTimeChart", html)
        self.assertIn("KNOCK_LINE_COLORS", html)
        self.assertIn("30-minute block, Eastern Time", html)
        self.assertIn('class="card span-12 accent-raydar"', html)


if __name__ == "__main__":
    unittest.main()
