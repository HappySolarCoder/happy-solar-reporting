#!/usr/bin/env python3
"""Prefer a production Bloom goal when a demo login shares the FMA's name.

The Lead Gen FMA dashboard matches Bloom goals by display name. The demo
login demo-fma-existing is also named Steven Emerson and is listed before
the production user, so the first match showed 16 demos instead of 15.
"""
from pathlib import Path

path = Path("api/fma_dashboard.py")
text = path.read_text(encoding="utf-8")
old = """    for (const goal of personGoals) {
      const metric = String(goal.settings_metric || '');
      if (!metric || goal.target == null) continue;
      const name = normGoalName(goal.name);"""
new = """    // A demo login can share a production FMA's display name. Keep the
    // production goal. A name that exists only on a demo login still fills in.
    const chosen = {};
    for (const goal of personGoals) {
      const metric = String(goal.settings_metric || '');
      const name = normGoalName(goal.name);
      if (!metric || goal.target == null || !name) continue;
      const key = name + '\\n' + metric;
      const current = chosen[key];
      const demo = String(goal.assignee_user_id || '').startsWith('demo-');
      if (!current || (String(current.assignee_user_id || '').startsWith('demo-') && !demo)) chosen[key] = goal;
    }
    for (const goal of Object.values(chosen)) {
      const metric = String(goal.settings_metric || '');
      const name = normGoalName(goal.name);"""

marker = "String(goal.assignee_user_id || '').startsWith('demo-')"
if marker in text and "const chosen = {}" in text:
    print("already applied")
    raise SystemExit(0)
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one merge loop, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("applied")
