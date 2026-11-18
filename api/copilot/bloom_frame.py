# -*- coding: utf-8 -*-
"""Shared Bloom parent targeting for framed Data Center pages.

Other-menu links navigate inside the reporting iframe, so document.referrer
becomes this app and cannot name the Bloom parent. location.ancestorOrigins
can. A top-level window never asks for a token.
"""

from __future__ import annotations


_SCRIPT = """\
function bloomFrameTargets() {
  // In-iframe menu clicks make document.referrer this app, not Bloom.
  // A top-level window stays locked. Framed windows prefer allowlisted
  // ancestorOrigins, then ask every allowlisted Bloom origin.
  if (window.parent === window) return [];
  const preferred = [];
  try {
    const ancestors = location.ancestorOrigins;
    if (ancestors && typeof ancestors.length === "number") {
      for (let i = 0; i < ancestors.length; i += 1) {
        const origin = ancestors[i];
        if (typeof origin === "string" && bloomParents.has(origin) && preferred.indexOf(origin) === -1) {
          preferred.push(origin);
        }
      }
    }
  } catch (err) {}
  const targets = preferred.slice();
  bloomParents.forEach(function (origin) {
    if (targets.indexOf(origin) === -1) targets.push(origin);
  });
  return targets;
}

function parentOrigin() {
  const targets = bloomFrameTargets();
  return targets.length ? targets[0] : "";
}
"""


def bloom_frame_script(*, indent: str = "") -> str:
    """JavaScript for bloomFrameTargets() and parentOrigin().

    The surrounding script must already define `bloomParents` as a Set of
    allowlisted origins. Framed pages put matching ancestorOrigins first, then
    include every allowlisted origin. A top-level window gets an empty list.
    """
    if not indent:
        return _SCRIPT
    return "\n".join(indent + line if line else line for line in _SCRIPT.splitlines())
