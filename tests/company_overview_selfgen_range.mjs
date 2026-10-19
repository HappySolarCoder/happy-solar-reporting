import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(path.join(root, "api", "ops_overview_script.txt"), "utf8");
const start = src.indexOf("  function sumKeys");
const end = src.indexOf("  function visibleNames");
if (start < 0 || end < start) throw new Error("company overview channel helpers were not found");
const body = src.slice(start, end);
if (!body.includes("function selfGenPack") || !body.includes("function minusMoved") || !body.includes("function channelsFrom")) {
  throw new Error("extracted slice is missing selfGenPack, minusMoved, or channelsFrom");
}

const api = new Function(`
  const SELF_KEYS = ["Self Gen", "self gen", "selfgen", "SelfGen"];
  const INBOUND_KEYS = ["Inbound"];
  const THREE_PL_KEYS = ["3PL"];
  const DOOR_KEYS = ["Doors"];
  let pageFilters = null;
  let snapshot = null;
  let channelGoals = null;
  function filters() {
    return pageFilters || { start: "", end: "", territory: "All", source: "All" };
  }
  ${body}
  function setState(state) {
    pageFilters = state.pageFilters;
    snapshot = state.snapshot;
    channelGoals = state.channelGoals;
  }
  return { selfGenPack, minusMoved, channelsFrom, channelGoalsMatch, numText, setState };
`)();

assert.match(
  src,
  /\/api\/metrics\/channel_goals\?year=" \+ encodeURIComponent\(ym\[0\] \|\| ""\) \+ "&month=" \+ encodeURIComponent\(String\(Number\(ym\[1\] \|\| 0\)\)\) \+ "&start=" \+ encodeURIComponent\(pageFilters\.start\) \+ "&end=" \+ encodeURIComponent\(pageFilters\.end\)/
);
assert.match(src, /Actual for the selected dates \/ monthly goal/);
assert.doesNotMatch(src, /chart-note">Actual \/ monthly goal/);

function quad(stats) {
  return [stats.created, stats.ran, stats.demos, stats.sales];
}

function snapshotFrom(createdLead, ranLead, sitLead, salesLead) {
  return {
    created: { result: 50, breakdowns: { created_by_lead_gen_source: createdLead } },
    ran: { result: 40, breakdowns: {} },
    demo: {
      ran_count: 40,
      sit_count: 20,
      breakdowns: { ran_by_lead_gen_source: ranLead, sit_by_lead_gen_source: sitLead },
    },
    sales: { result: 10, breakdowns: { sales_by_lead_gen_source: salesLead } },
  };
}

const weekSnapshot = snapshotFrom(
  { Doors: 23, "Self Gen": 13, Inbound: 3, "3PL": 3 },
  { Doors: 36, "Self Gen": 8, Inbound: 2, "3PL": 3 },
  { Doors: 14, "Self Gen": 7, Inbound: 2, "3PL": 3 },
  { Doors: 6, "Self Gen": 5, Inbound: 0, "3PL": 2 }
);
const weekFilters = { start: "2026-10-12", end: "2026-10-18", territory: "All", source: "All" };

api.setState({
  pageFilters: weekFilters,
  snapshot: weekSnapshot,
  channelGoals: {
    start: "2026-10-12",
    end: "2026-10-18",
    self_gen: { appointments: 12, ran: 8, demos: 7, sales: 5, moved_from: {} },
  },
});
let stats = api.channelsFrom(weekSnapshot);
assert.deepEqual(quad(stats["Self gen"]), [12, 8, 7, 5]);
assert.deepEqual(quad(stats.Doors), [23, 36, 14, 6]);
assert.notEqual(stats["Self gen"].created, 13);

function monthGoals() {
  return {
    start: "2026-10-01",
    end: "2026-10-31",
    self_gen: {
      appointments: 24,
      ran: 17,
      demos: 10,
      sales: 6,
      moved_from: { Doors: { appointments: 1, ran: 1, demos: 1, sales: 1 } },
    },
  };
}

for (const channelGoals of [monthGoals(), { self_gen: monthGoals().self_gen }]) {
  api.setState({ pageFilters: weekFilters, snapshot: weekSnapshot, channelGoals });
  assert.equal(api.selfGenPack(), null);
  stats = api.channelsFrom(weekSnapshot);
  assert.deepEqual(quad(stats.Doors), [23, 36, 14, 6]);
  assert.deepEqual(quad(stats["Self gen"]), [null, null, null, null]);
  assert.equal(api.numText(stats["Self gen"].created), "—");
  assert.notEqual(stats["Self gen"].created, 24);
}

api.setState({ pageFilters: weekFilters, snapshot: weekSnapshot, channelGoals: null });
assert.equal(api.selfGenPack(), null);
stats = api.channelsFrom(weekSnapshot);
assert.deepEqual(quad(stats.Doors), [23, 36, 14, 6]);
assert.equal(api.numText(stats["Self gen"].created), "—");

api.setState({
  pageFilters: { start: "2026-10-12", end: "2026-10-18", territory: "All", source: "Doors" },
  snapshot: weekSnapshot,
  channelGoals: monthGoals(),
});
stats = api.channelsFrom(weekSnapshot);
assert.deepEqual(quad(stats["Self gen"]), [13, 8, 7, 5]);
assert.deepEqual(quad(stats.Doors), [23, 36, 14, 6]);

const mtdRows = [];
for (let i = 0; i < 23; i += 1) {
  mtdRows.push({ opportunityId: "sg" + i, leadGenSource: "Self Gen", setterLastName: "x", owner: "Y Z" });
}
mtdRows.push({
  opportunityId: "beatrice",
  leadGenSource: "Self Gen",
  setterLastName: "Sauriol",
  owner: "Jeff Salas",
  sweeperRehashLastName: "Diamond",
});
mtdRows.push({
  opportunityId: "override",
  leadGenSource: "Doors",
  setterLastName: "Frazier",
  owner: "Allen Frazier",
});

const counted = spawnSync("python3", ["-c", `
import json, sys
from pathlib import Path
root = Path(${JSON.stringify(root)})
sys.path[:0] = [str(root / "api"), str(root / "api" / "metrics")]
from channel_goals import filled, self_gen_reason
rows = json.loads(sys.stdin.read())
seen = set()
n = 0
for row in rows:
    oid = str(row.get("opportunityId") or "")
    if not oid or oid in seen:
        continue
    seen.add(oid)
    if filled(row.get("sweeperRehashLastName")):
        continue
    if self_gen_reason(row.get("leadGenSource"), row.get("setterLastName"), row.get("owner")):
        n += 1
print(n)
`], { input: JSON.stringify(mtdRows), encoding: "utf8" });
if (counted.status !== 0) throw new Error(counted.stderr || counted.stdout);
const selfGenCreated = Number(counted.stdout.trim());
assert.equal(selfGenCreated, 24);

const mtdSnapshot = snapshotFrom(
  { Doors: 66, "Self Gen": 25 },
  { Doors: 71, "Self Gen": 18 },
  { Doors: 32, "Self Gen": 11 },
  { Doors: 13, "Self Gen": 7 }
);
api.setState({
  pageFilters: { start: "2026-10-01", end: "2026-10-18", territory: "All", source: "All" },
  snapshot: mtdSnapshot,
  channelGoals: {
    start: "2026-10-01",
    end: "2026-10-18",
    self_gen: {
      appointments: selfGenCreated,
      ran: 17,
      demos: 10,
      sales: 6,
      moved_from: { Doors: { appointments: 1, ran: 1, demos: 1, sales: 1 } },
    },
  },
});
stats = api.channelsFrom(mtdSnapshot);
assert.equal(stats["Self gen"].created, selfGenCreated);
assert.deepEqual(quad(stats["Self gen"]), [24, 17, 10, 6]);
assert.notEqual(stats["Self gen"].created, 25);
assert.deepEqual(quad(stats.Doors), [65, 70, 31, 12]);

console.log("company overview self gen range ok");
