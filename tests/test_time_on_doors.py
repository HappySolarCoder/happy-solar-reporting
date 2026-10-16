# -*- coding: utf-8 -*-

"""FMA time on doors: first counted knock to last counted knock."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from time_on_doors import (  # noqa: E402
    aggregate_time_on_doors,
    format_time_on_doors,
    knock_actor_id,
    time_on_doors_table,
)

DAILY_PATH = API / "daily_update.py"
RAYDAR_PATH = API / "metrics" / "raydar_doors_knocked.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def at(hour: int, minute: int = 0, day: int = 16) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


class TimeOnDoorsAggregationTests(unittest.TestCase):
    def test_span_is_last_knock_minus_first_knock(self):
        rows = aggregate_time_on_doors(
            [
                ("fma-1", at(17, 12)),
                ("fma-1", at(13, 0)),
                ("fma-1", at(15, 30)),
            ]
        )
        rec = rows["fma-1"]
        self.assertEqual(rec["knocks"], 3)
        self.assertEqual(rec["seconds"], 4 * 3600 + 12 * 60)
        self.assertEqual(rec["duration"], "4h 12m")
        self.assertEqual(rec["first_dispositionedAt"], at(13, 0).isoformat())
        self.assertEqual(rec["last_dispositionedAt"], at(17, 12).isoformat())
        self.assertEqual(rec["timestamps_missing"], 0)

    def test_one_knock_is_zero_duration(self):
        moment = at(14, 5)
        rows = aggregate_time_on_doors([("fma-1", moment)])
        rec = rows["fma-1"]
        self.assertEqual(rec["knocks"], 1)
        self.assertEqual(rec["seconds"], 0)
        self.assertEqual(rec["duration"], "0h 00m")
        self.assertEqual(rec["first_dispositionedAt"], moment.isoformat())
        self.assertEqual(rec["last_dispositionedAt"], moment.isoformat())

    def test_no_knocks_is_empty(self):
        self.assertEqual(aggregate_time_on_doors([]), {})

    def test_same_instant_knocks_are_zero_duration(self):
        moment = at(9, 0)
        rec = aggregate_time_on_doors([("fma-1", moment), ("fma-1", moment)])["fma-1"]
        self.assertEqual(rec["knocks"], 2)
        self.assertEqual(rec["seconds"], 0)
        self.assertEqual(rec["duration"], "0h 00m")

    def test_missing_timestamp_does_not_invent_a_clock(self):
        rows = aggregate_time_on_doors(
            [
                ("fma-1", at(12, 0)),
                ("fma-1", None),
                ("fma-1", "not-a-timestamp"),
                ("fma-1", at(12, 45)),
            ]
        )
        rec = rows["fma-1"]
        self.assertEqual(rec["knocks"], 4)
        self.assertEqual(rec["timestamps_missing"], 2)
        self.assertEqual(rec["seconds"], 45 * 60)
        self.assertEqual(rec["duration"], "0h 45m")

    def test_all_missing_timestamps_have_no_duration(self):
        rec = aggregate_time_on_doors([("fma-1", None), ("fma-1", "")])["fma-1"]
        self.assertEqual(rec["knocks"], 2)
        self.assertIsNone(rec["seconds"])
        self.assertEqual(rec["duration"], "—")
        self.assertIsNone(rec["first_dispositionedAt"])
        self.assertIsNone(rec["last_dispositionedAt"])

    def test_iso_strings_and_multi_day_hours(self):
        start = "2026-10-16T13:00:00Z"
        end = "2026-10-17T15:15:00+00:00"
        rec = aggregate_time_on_doors([("fma-1", start), ("fma-1", end)])["fma-1"]
        self.assertEqual(rec["seconds"], 26 * 3600 + 15 * 60)
        self.assertEqual(rec["duration"], "26h 15m")

    def test_sorts_by_time_then_knocks_then_actor(self):
        rows = aggregate_time_on_doors(
            [
                ("b", at(10, 0)),
                ("b", at(12, 0)),
                ("a", at(10, 0)),
                ("a", at(12, 0)),
                ("a", at(11, 0)),
                ("c", at(9, 0)),
                ("c", at(15, 0)),
            ]
        )
        self.assertEqual(list(rows), ["c", "a", "b"])
        self.assertEqual(rows["c"]["seconds"], 6 * 3600)
        self.assertEqual(rows["a"]["knocks"], 3)
        self.assertEqual(rows["b"]["knocks"], 2)

    def test_actor_uses_history_user_then_claimed_by(self):
        self.assertEqual(
            knock_actor_id(
                {
                    "claimedBy": "claimed-1",
                    "dispositionHistory": [{"userId": "hist-1"}],
                }
            ),
            "hist-1",
        )
        self.assertEqual(
            knock_actor_id({"claimedBy": "claimed-1", "dispositionHistory": []}),
            "claimed-1",
        )
        self.assertEqual(
            knock_actor_id({"claimedBy": "claimed-1", "dispositionHistory": [{"userId": ""}]}),
            "claimed-1",
        )
        self.assertIsNone(knock_actor_id({}))
        self.assertIsNone(knock_actor_id(None))

    def test_duration_format_floors_minutes(self):
        self.assertEqual(format_time_on_doors(4 * 3600 + 12 * 60), "4h 12m")
        self.assertEqual(format_time_on_doors(0), "0h 00m")
        self.assertEqual(format_time_on_doors(59), "0h 00m")
        self.assertEqual(format_time_on_doors(60), "0h 01m")
        self.assertEqual(format_time_on_doors(None), "—")
        self.assertEqual(format_time_on_doors(-5), "0h 00m")

    def test_table_merges_same_display_name_and_sorts_by_time(self):
        by_actor = aggregate_time_on_doors(
            [
                ("id-a", at(13, 0)),
                ("id-a", at(14, 0)),
                ("id-b", at(14, 30)),
                ("id-b", at(16, 12)),
                ("id-c", at(9, 0)),
            ]
        )
        names = {"id-a": "Sam Rivera", "id-b": "Sam Rivera", "id-c": "Ada Cole"}
        table = time_on_doors_table(by_actor, names)
        self.assertEqual([row["name"] for row in table], ["Sam Rivera", "Ada Cole"])
        sam = table[0]
        self.assertEqual(sam["knocks"], 4)
        self.assertEqual(sam["seconds"], 3 * 3600 + 12 * 60)
        self.assertEqual(sam["duration"], "3h 12m")
        self.assertEqual(sam["first_dispositionedAt"], at(13, 0).isoformat())
        self.assertEqual(sam["last_dispositionedAt"], at(16, 12).isoformat())
        ada = table[1]
        self.assertEqual(ada["knocks"], 1)
        self.assertEqual(ada["duration"], "0h 00m")
        self.assertEqual(ada["name"], "Ada Cole")

    def test_table_tie_breaks_knocks_then_name(self):
        by_actor = {
            "1": {
                "knocks": 2,
                "seconds": 3600,
                "first_dispositionedAt": at(10, 0).isoformat(),
                "last_dispositionedAt": at(11, 0).isoformat(),
            },
            "2": {
                "knocks": 5,
                "seconds": 3600,
                "first_dispositionedAt": at(12, 0).isoformat(),
                "last_dispositionedAt": at(13, 0).isoformat(),
            },
            "3": {
                "knocks": 5,
                "seconds": 3600,
                "first_dispositionedAt": at(8, 0).isoformat(),
                "last_dispositionedAt": at(9, 0).isoformat(),
            },
        }
        names = {"1": "Cara", "2": "Blake", "3": "Avery"}
        table = time_on_doors_table(by_actor, names)
        self.assertEqual([row["name"] for row in table], ["Avery", "Blake", "Cara"])

    def test_unknown_actor_keeps_id_as_name(self):
        by_actor = aggregate_time_on_doors([("raw-id", at(10, 0))])
        table = time_on_doors_table(by_actor, {})
        self.assertEqual(table[0]["name"], "raw-id")
        self.assertEqual(table[0]["duration"], "0h 00m")


class DailyDashboardTimeOnDoorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.daily = load_module("daily_update_time_on_doors", DAILY_PATH)
        cls.raydar_src = RAYDAR_PATH.read_text(encoding="utf-8")

    def test_activity_card_renders_time_on_doors_beside_knocks(self):
        html = self.daily.HTML
        knocks = html.find('id="tblKnocks"')
        time_on = html.find('id="tblTimeOnDoors"')
        powerline = html.find('id="tblPowerline"')
        self.assertGreater(knocks, -1)
        self.assertLess(knocks, time_on)
        self.assertLess(time_on, powerline)
        self.assertIn("FMA Time on Doors", html)
        self.assertIn("First door knocked to last door knocked", html)
        self.assertIn("Door Knocks by Raydar User", html)
        self.assertIn("Powerline Calls by User", html)
        self.assertIn("Sales (GHL)", html)
        self.assertIn("Opportunities Created", html)
        self.assertIn("/api/metrics/raydar_doors_knocked?", html)
        self.assertIn("knocks?.time_on_doors", html)
        self.assertIn(">Time on doors<", html)
        self.assertIn(">Knocks<", html)
        self.assertIn("No rows", html)
        self.assertIn('class="card span-6 accent-raydar"', html)
        self.assertIn('class="card span-6 accent-powerline"', html)
        self.assertIn("time on doors descending, then knocks, then name", html)

    def test_raydar_payload_uses_counted_knocks_only(self):
        src = self.raydar_src
        self.assertIn("observe_door_knock", src)
        self.assertIn("time_on_doors_by_actor", src)
        self.assertIn('"time_on_doors": time_on_doors_table(time_by_actor, users)', src)
        knock_gate = src.find("if not counts_as_knock:")
        observe = src.find("observe_door_knock(door_spans, k, d.get(MetricContract.time_field))")
        adjust = src.find("manual_knock_adjustments")
        self.assertGreater(knock_gate, -1)
        self.assertLess(knock_gate, observe)
        self.assertLess(observe, adjust)


if __name__ == "__main__":
    unittest.main()
