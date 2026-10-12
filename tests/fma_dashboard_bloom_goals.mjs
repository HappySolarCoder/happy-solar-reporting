import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(path.join(root, "api", "fma_dashboard.py"), "utf8");
const start = src.indexOf("  function normGoalName");
const end = src.indexOf("  function getSetterRange");
if (start < 0 || end < start) throw new Error("FMA dashboard goal merge was not found");
const { mergeBloomPersonGoals } = new Function(`${src.slice(start, end)}\nreturn { mergeBloomPersonGoals };`)();

function goal(id, name, metric, target) {
  return { assignee_user_id: id, name, settings_metric: metric, target };
}

const roster = [
  { person_key: "setter:steven_emerson", display_name: "Steven Emerson", ghl_setter_last_name: "Emerson" },
  { person_key: "setter:bo_hill", display_name: "Bo Hill", ghl_setter_last_name: "Hill" },
  { person_key: "setter:marissa_mancini", display_name: "Marissa Mancini", ghl_setter_last_name: "Mancini" },
  { person_key: "setter:sawyer_vermeesch", display_name: "Sawyer Vermeesch", ghl_setter_last_name: "Vermeesch" },
  { person_key: "setter:jordan_meehan", display_name: "Jordan Meehan", ghl_setter_last_name: "Meehan" },
];

function value(rows, personKey, metric) {
  const row = rows.find((item) => item.person_key === personKey && item.metric === metric);
  return row ? row.value : null;
}

const october = [];
mergeBloomPersonGoals(october, roster, [
  goal("demo-fma-existing", "Steven Emerson", "demos_goal", 16),
  goal("user_edc0244abd1750d479", "Steven Emerson", "demos_goal", 15),
  goal("demo-fma-existing", "Steven Emerson", "doors_goal", 1800),
  goal("user_edc0244abd1750d479", "Steven Emerson", "doors_goal", 1900),
  goal("demo-fma-existing", "Steven Emerson", "appts_goal", 35),
  goal("user_edc0244abd1750d479", "Steven Emerson", "appts_goal", 35),
  goal("user_47d3956ed0fd2d8774", "Bo Hill", "demos_goal", 15),
  goal("user_949c20adfb4527b4b8", "Marissa Mancini", "demos_goal", 15),
  goal("user_d031c93c1372d54102", "Sawyer Vermeesch", "demos_goal", 15),
  goal("user_6f25629cc20d758905", "Jordan Meehan", "demos_goal", 15),
]);

assert.equal(value(october, "setter:steven_emerson", "demos_goal"), 15);
assert.equal(value(october, "setter:steven_emerson", "doors_goal"), 1900);
assert.equal(value(october, "setter:steven_emerson", "appts_goal"), 35);
assert.equal(value(october, "setter:bo_hill", "demos_goal"), 15);
assert.equal(value(october, "setter:marissa_mancini", "demos_goal"), 15);
assert.equal(value(october, "setter:sawyer_vermeesch", "demos_goal"), 15);
assert.equal(value(october, "setter:jordan_meehan", "demos_goal"), 15);

const productionFirst = [];
mergeBloomPersonGoals(productionFirst, roster, [
  goal("user_edc0244abd1750d479", "Steven Emerson", "demos_goal", 15),
  goal("demo-fma-existing", "Steven Emerson", "demos_goal", 16),
]);
assert.equal(value(productionFirst, "setter:steven_emerson", "demos_goal"), 15);

const preset = [{ person_key: "setter:steven_emerson", metric: "demos_goal", value: 12 }];
mergeBloomPersonGoals(preset, roster, [
  goal("demo-fma-existing", "Steven Emerson", "demos_goal", 16),
  goal("user_edc0244abd1750d479", "Steven Emerson", "demos_goal", 15),
]);
assert.equal(preset.length, 1);
assert.equal(preset[0].value, 12);

const demoOnly = [];
mergeBloomPersonGoals(demoOnly, roster, [goal("demo-fma-existing", "Steven Emerson", "demos_goal", 16)]);
assert.equal(value(demoOnly, "setter:steven_emerson", "demos_goal"), 16);

console.log("fma dashboard bloom goals ok");
