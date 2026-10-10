/**
 * Rules checks for the Mystery Trip contest board (ClickUp 86bccr3du).
 * Feeds are small hand-built samples. Nothing here calls the network.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "api", "mystery_trip_logic.txt"), "utf8");
// Same realm as the asserts, so arrays compare with deepEqual.
const MT = new Function(`${source}\nreturn MysteryTrip;`)();

const goals = (rows) => rows.map(([name, role, metric, target, id]) => ({
  name, role, metric, target, assignee_user_id: id || `user_${name.replace(/\W/g, "").toLowerCase()}`,
}));

function feed(over = {}) {
  return {
    loaded: true,
    steakDemos: {},
    salesBySetter: {},
    salesByOwner: {},
    cancelByOwner: [],
    goals: [],
    ...over,
  };
}

// Windows never pass today, the Steak Dinner deadline, or Dec 23.
{
  assert.deepEqual(JSON.parse(JSON.stringify(MT.windowsFor("2026-10-08"))), [
    { id: "2026-10", start: "2026-10-01", end: "2026-10-08", steakEnd: "2026-10-08" },
  ]);
  const late = JSON.parse(JSON.stringify(MT.windowsFor("2026-12-30")));
  assert.equal(late.length, 3);
  assert.deepEqual(late[0], { id: "2026-10", start: "2026-10-01", end: "2026-10-31", steakEnd: "2026-10-24" });
  assert.deepEqual(late[2], { id: "2026-12", start: "2026-12-01", end: "2026-12-23", steakEnd: "2026-12-23" });
  assert.equal(MT.windowsFor("2026-09-30").length, 0);
}

// Name matching: Zach and Zachary match, Mark and Marcus do not, last names ignore punctuation.
{
  assert.equal(MT.countForName({ "Zachary Maecker": 2 }, "Zach Maecker"), 2);
  assert.equal(MT.countForName({ "Marcus Fino": 3 }, "Mark Fino"), 0);
  assert.equal(MT.countForLastName({ "O'Connell": 4, Emerson: 1 }, "OConnell"), 4);
  assert.equal(MT.countForLastName({ emerson: 2 }, "Emerson"), 2);
}

// FMA: Bloom demo goal wins, the standard 15 applies otherwise, demo-* goals are ignored.
{
  const out = MT.buildFma({
    today: "2026-10-08",
    roster: [
      { name: "Steven Emerson", setterLastName: "Emerson" },
      { name: "Jordan Meehan", setterLastName: "Meehan" },
    ],
    feeds: {
      "2026-10": feed({
        steakDemos: { Emerson: 16, Meehan: 4 },
        salesBySetter: { Emerson: 3 },
        goals: goals([
          ["Steven Emerson", "fma", "demos", 16],
          ["Steven Emerson", "fma", "demos", 99, "demo-fma-existing"],
        ]),
      }),
    },
    credits: [],
  });
  const steven = out.find((p) => p.name === "Steven Emerson");
  const jordan = out.find((p) => p.name === "Jordan Meehan");
  assert.equal(steven.months[0].requirement, 16);
  assert.equal(steven.months[0].requirementSource, "bloom");
  assert.equal(steven.months[0].status, "hit");
  assert.equal(steven.months[1].status, "upcoming");
  assert.equal(steven.trip, "in-reach");
  assert.equal(steven.totalSales, 3);
  assert.equal(jordan.months[0].requirement, 15);
  assert.equal(jordan.months[0].requirementSource, "standard");
  assert.equal(jordan.months[0].status, "live");
  assert.equal(jordan.months[0].daysLeft, 17); // Oct 8 through Oct 24
}

// FMA: missed after the deadline, trip at 2 months, flight at 3, plus one needs 24 sales and the trip.
{
  const roster = [{ name: "Bo Hill", setterLastName: "Hill" }];
  const base = {
    "2026-10": feed({ steakDemos: { Hill: 15 }, salesBySetter: { Hill: 9 } }),
    "2026-11": feed({ steakDemos: { Hill: 14 }, salesBySetter: { Hill: 8 } }),
    "2026-12": feed({ steakDemos: { Hill: 15 }, salesBySetter: { Hill: 7 } }),
  };
  const [bo] = MT.buildFma({ today: "2026-12-24", roster, feeds: base, credits: [] });
  assert.deepEqual(bo.months.map((m) => m.status), ["hit", "missed", "hit"]);
  assert.equal(bo.trip, "earned");
  assert.equal(bo.flight, "missed");
  assert.equal(bo.totalSales, 24);
  assert.equal(bo.plusOne, "earned");

  // One recruiting credit turns the missed month into a qualifying month for the flight.
  const [credited] = MT.buildFma({
    today: "2026-12-24", roster, feeds: base,
    credits: [{ recruiter: "Bo Hill", recruit: "New Rep", month: "2026-11" }],
  });
  assert.equal(credited.flight, "earned");
  assert.equal(credited.creditMonthsUsed, 1);

  // Credits never replace the 24-sale plus one rule.
  const short = { ...base, "2026-12": feed({ steakDemos: { Hill: 15 }, salesBySetter: { Hill: 1 } }) };
  const [noPlus] = MT.buildFma({ today: "2026-12-24", roster, feeds: short, credits: [{ recruiter: "Bo Hill", recruit: "A", month: "2026-10" }] });
  assert.equal(noPlus.plusOne, "missed");

  // Demos after the deadline are not in the feed window; the month stays missed.
  const [late] = MT.buildFma({ today: "2026-10-26", roster, feeds: { "2026-10": feed({ steakDemos: { Hill: 14 } }) }, credits: [] });
  assert.equal(late.months[0].status, "missed");
}

// FMA board leaves out people with a closer or manager sales goal.
{
  const out = MT.buildFma({
    today: "2026-10-08",
    roster: [{ name: "Rueben Hand", setterLastName: "Hand" }, { name: "Bo Hill", setterLastName: "Hill" }],
    feeds: { "2026-10": feed({ goals: goals([["Rueben Hand", "closer", "sales", 15]]) }) },
    credits: [],
  });
  assert.deepEqual(out.map((p) => p.name), ["Bo Hill"]);
}

// Closers: Bloom sales goal per month, given-name match, cancellation plus one.
{
  const feeds = {
    "2026-10": feed({
      salesByOwner: { "Zachary Maecker": 15, "Brooke Simpson": 2, "Pat Newman": 1 },
      cancelByOwner: [
        { label: "Zach Maecker", sold_date_total: 15, cancelled: 3, cancellation_rate: 20 },
        { label: "Brooke Simpson", sold_date_total: 2, cancelled: 1, cancellation_rate: 50 },
      ],
      goals: goals([
        ["Zach Maecker", "closer", "sales", 15],
        ["Brooke Simpson", "manager", "sales", 12],
        ["Morgan West", "closer", "sales", 8, "demo-closer-trainee"],
      ]),
    }),
  };
  const out = MT.buildClosers({ today: "2026-10-20", feeds, credits: [] });
  const names = out.map((p) => p.name).sort();
  assert.deepEqual(names, ["Brooke Simpson", "Pat Newman", "Zach Maecker"]);
  const zach = out.find((p) => p.name === "Zach Maecker");
  assert.equal(zach.months[0].sales, 15);
  assert.equal(zach.months[0].status, "hit");
  assert.equal(zach.months[0].cancelRate, 20);
  assert.equal(zach.plusOne, "in-reach");
  const brooke = out.find((p) => p.name === "Brooke Simpson");
  assert.equal(brooke.months[0].status, "live");
  assert.equal(brooke.plusOne, "at-risk");
  const pat = out.find((p) => p.name === "Pat Newman");
  assert.equal(pat.months[0].status, "no-goal-yet");
  assert.equal(pat.months[0].goal, null);

  // A finished month at 30% or more ends the plus one. Exactly 30% is not under 30%.
  const done = MT.buildClosers({
    today: "2026-11-02",
    feeds: {
      "2026-10": feed({
        salesByOwner: { "Zach Maecker": 10 },
        cancelByOwner: [{ label: "Zach Maecker", sold_date_total: 10, cancelled: 3 }],
        goals: goals([["Zach Maecker", "closer", "sales", 10]]),
      }),
      "2026-11": feed({ goals: goals([["Zach Maecker", "closer", "sales", 10]]) }),
    },
    credits: [],
  });
  assert.equal(done[0].months[0].cancelRate, 30);
  assert.equal(done[0].plusOne, "missed");
  assert.equal(done[0].months[0].status, "hit");
}

// Closer trip and flight after the contest.
{
  const month = (sales, goal) => feed({
    salesByOwner: { "Allen Frazier": sales },
    cancelByOwner: [{ label: "Allen Frazier", sold_date_total: sales, cancelled: 0 }],
    goals: goals([["Allen Frazier", "closer", "sales", goal]]),
  });
  const [allen] = MT.buildClosers({
    today: "2026-12-24",
    feeds: { "2026-10": month(7, 7), "2026-11": month(8, 7), "2026-12": month(6, 7) },
    credits: [],
  });
  assert.equal(allen.trip, "earned");
  assert.equal(allen.flight, "missed");
  assert.equal(allen.plusOne, "earned");
}

// Board order, traveler lookup, and the route.
{
  const people = MT.buildFma({
    today: "2026-10-08",
    roster: [{ name: "A One", setterLastName: "One" }, { name: "B Two", setterLastName: "Two" }],
    feeds: { "2026-10": feed({ steakDemos: { Two: 9, One: 3 } }) },
    credits: [],
  });
  assert.deepEqual(MT.sortBoard(people).map((p) => p.name), ["B Two", "A One"]);
  assert.equal(MT.findTraveler(people, "b two").name, "B Two");
  assert.equal(MT.findTraveler(people, "Nobody"), null);
  assert.equal(MT.contestProgress("2026-10-01"), 0);
  assert.equal(MT.contestProgress("2026-12-23"), 1);
  assert.equal(MT.daysLeftInContest("2026-12-23"), 1);
  assert.equal(MT.shortDate("2026-10-24"), "Oct 24");
}

console.log("mystery trip rules ok");

// Bloom role gate: FMA path keeps role fma, Closers path keeps role closer (Solar Consultant).
{
  const accounts = [
    { name: "Zachary Maecker", role: "fma" },
    { name: "Steven Emerson", role: "closer" },
    { name: "Pat Lee", role: "closer" },
  ];
  assert.equal(MT.bloomRoleFor("Zach Maecker", accounts), "fma");
  assert.equal(MT.bloomRoleFor("steven  emerson", accounts), "closer");
  assert.equal(MT.bloomRoleFor("No Account", accounts), "");
  const fma = MT.keepBloomRole([{ name: "Zach Maecker" }, { name: "Pat Lee" }, { name: "No Account" }], accounts, "fma");
  assert.deepEqual(fma.map((p) => p.name), ["Zach Maecker"]);
  const closers = MT.keepBloomRole([{ name: "Steven Emerson" }, { name: "Zachary Maecker" }], accounts, "closer");
  assert.deepEqual(closers.map((p) => p.name), ["Steven Emerson"]);
  // Two accounts with one name and different roles: no match, like the portal's tie rule.
  assert.equal(MT.bloomRoleFor("Sam Ray", [{ name: "Sam Ray", role: "fma" }, { name: "Sam Ray", role: "closer" }]), "");
}
