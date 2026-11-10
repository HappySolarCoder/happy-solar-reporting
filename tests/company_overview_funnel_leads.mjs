import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(path.join(root, "api", "ops_overview_script.txt"), "utf8");

function sliceBetween(startMarker, endMarker) {
  const start = src.indexOf(startMarker);
  const end = src.indexOf(endMarker);
  if (start < 0 || end < start) throw new Error(`missing slice ${startMarker} -> ${endMarker}`);
  return src.slice(start, end);
}

const leadFns = sliceBetween("  function leadCount", "  function fillStage");
const rateFn = sliceBetween("  function rateText", "  function numText");
const numFn = sliceBetween("  function numText", "  function daysInMonth");
const matchFn = sliceBetween("  function channelGoalsMatch", "  function selfGenPack");
const stageFns = sliceBetween("  function stageButton", "  async function monthRow");
const escFn = sliceBetween("  function esc", "  function nyToday");

if (!leadFns.includes("channelGoals.leads")) {
  throw new Error("funnel lead count must read channelGoals.leads");
}
if (leadFns.includes("Facebook") || leadFns.includes("fetch(")) {
  throw new Error("funnel lead count must not reimplement the lead query");
}

const api = new Function(`
  let pageFilters = null;
  let channelGoals = null;
  function filters() {
    return pageFilters || { start: "", end: "", territory: "All", source: "All" };
  }
  ${escFn}
  ${rateFn}
  ${numFn}
  ${matchFn}
  ${leadFns}
  ${stageFns}
  function setState(state) {
    pageFilters = state.pageFilters;
    channelGoals = state.channelGoals;
  }
  return { leadCount, withLeads, oppOfLeadsText, historyStages, setState };
`)();

const week = { start: "2026-10-12", end: "2026-10-18", territory: "All", source: "All" };
const goals = {
  start: "2026-10-12",
  end: "2026-10-18",
  leads: { Inbound: 12, "3PL": 4 },
};

api.setState({ pageFilters: week, channelGoals: goals });
assert.equal(api.leadCount("Inbound"), 12);
assert.equal(api.leadCount("3PL"), 4);
for (const skipped of ["Company", "Doors", "Self gen", "Sweeper", "Self Gen"]) {
  assert.equal(api.leadCount(skipped), null, skipped);
}
const inboundStats = { created: 3, ran: 4, demos: 2, sales: 1 };
const withInbound = api.withLeads("Inbound", inboundStats);
assert.equal(withInbound.leads, 12);
assert.equal(withInbound.created, 3);
assert.equal(api.withLeads("Doors", inboundStats), inboundStats);
assert.equal(api.oppOfLeadsText(3, 12, "All"), "25.0% of leads");
assert.equal(api.oppOfLeadsText(3, 12, "Buffalo"), "");
assert.equal(api.oppOfLeadsText(3, 0, "All"), "");
assert.equal(api.oppOfLeadsText(null, 12, "All"), "");

api.setState({
  pageFilters: week,
  channelGoals: { start: "2026-10-01", end: "2026-10-31", leads: { Inbound: 30, "3PL": 108 } },
});
assert.equal(api.leadCount("Inbound"), null);
assert.equal(api.leadCount("3PL"), null);
assert.equal(api.withLeads("3PL", inboundStats).leads, null);

api.setState({ pageFilters: week, channelGoals: null });
assert.equal(api.leadCount("Inbound"), null);

api.setState({
  pageFilters: week,
  channelGoals: { start: week.start, end: week.end, leads: { Inbound: null, "3PL": 0 } },
});
assert.equal(api.leadCount("Inbound"), null);
assert.equal(api.leadCount("3PL"), 0);

api.setState({ pageFilters: week, channelGoals: goals });
const companyStages = api.historyStages("Company", { created: 3, ran: 4, demos: 2, sales: 1 }, "All");
assert.equal(companyStages.includes(">Leads</span>"), false);
assert.equal(
  companyStages.startsWith(
    '<div class="compact-stage" style="--inset:0%;--next:4%;--stage-color:#125975"><span>Opportunities created</span><strong>3</strong><small>Created in selected period</small></div>'
  ),
  true
);
assert.equal(companyStages.includes("--inset:12%;--next:16%;--stage-color:#104d48"), true);
assert.equal(companyStages.includes("--inset:16%"), false);

const inboundStages = api.historyStages("Inbound", { created: 3, ran: 4, demos: 2, sales: 1, leads: 12 }, "All");
assert.ok(inboundStages.indexOf(">Leads</span>") >= 0);
assert.ok(inboundStages.indexOf(">Leads</span>") < inboundStages.indexOf(">Opportunities created</span>"));
assert.equal(
  inboundStages.includes(
    '<div class="compact-stage" style="--inset:0%;--next:4%;--stage-color:#187090"><span>Leads</span><strong>12</strong><small>Created in selected period</small></div>'
  ),
  true
);
assert.equal(
  inboundStages.includes(
    '<div class="compact-stage" style="--inset:4%;--next:8%;--stage-color:#125975"><span>Opportunities created</span><strong>3</strong><small>Created in selected period · 25.0% of leads</small></div>'
  ),
  true
);
assert.equal(inboundStages.includes("--inset:16%;--next:20%;--stage-color:#104d48"), true);

const filtered = api.historyStages("3PL", { created: 1, ran: 1, demos: 0, sales: 0, leads: 4 }, "Buffalo");
assert.equal(filtered.includes(">Leads</span>"), true);
assert.equal(filtered.includes("of leads"), false);
assert.equal(filtered.includes("<strong>4</strong>"), true);

const doors = api.historyStages("Doors", { created: 8, ran: 5, demos: 2, sales: 1 }, "All");
assert.equal(doors.includes(">Leads</span>"), false);
assert.equal(doors.includes("Created in selected period</small>"), true);

console.log("company overview funnel leads ok");
