#!/usr/bin/env python3
"""Evidence level -- must this task produce a verification artifact, or may it have none?

WHY THIS EXISTS
===============
g_tool_utilization (G-T1) judges tool evidence inside verification artifacts. When there
are no artifacts at all it used to report SKIP/pass, which made "nothing to check" read as
"checked and clean" -- the single most dangerous shape a gate verdict can take. It now
reports a non-judgement (exit 4), which is honest but still not strict: for an L2+ task, or
any task with a real-stack criterion, *no artifact* is a FAILURE, not an absence.

A gate cannot know that on its own -- it needs the plan's declared depth. This module is the
deterministic derivation of that depth from the plan, kept separate so both the gate and the
test harness read one implementation.

DERIVATION (deliberately mechanical, no judgement)
  required if complexity is L2, L3 or L4
  required if any acceptance criterion is tagged integration, e2e, browser or data-invariant
  optional otherwise (L0/L1 with only unit/static/manual/contract criteria)
  optional when the plan declares neither -- an absent declaration is not evidence of depth,
           and inventing one would make the gate fail plans that never claimed depth

WHAT THIS DOES NOT PROVE
========================
It proves the plan DECLARED a depth that requires evidence. It does not prove the artifact is
any good; G-T1 and the verifier do that.

Usage:
  python3 framework/tools/evidence_level.py PLAN.md [--root DIR] [--json]
Exit: 0 always when the plan is readable (the answer is in the output)
      2 BLOCKED when the plan cannot be read
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REAL_STACK_TAGS = ("integration", "e2e", "browser", "data-invariant")
DEEP = ("L2", "L3", "L4")

CRIT_RE = re.compile(r"^AC-\d+\s+\[([A-Za-z0-9-]+)\]", re.I)
COMPLEXITY_RE = re.compile(r"^complexity:[ \t]*([Ll][0-4])\b")


def derive(text):
    text = text.replace("\r", "")

    complexity = None
    for line in text.split("\n"):
        m = COMPLEXITY_RE.match(line)
        if m:
            complexity = m.group(1).upper()
            break

    tags = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        m = CRIT_RE.match(stripped[1:].strip())
        if m:
            tags.append(m.group(1).lower())

    real = [t for t in tags if t in REAL_STACK_TAGS]
    reasons = []
    if complexity in DEEP:
        reasons.append("complexity %s" % complexity)
    if real:
        reasons.append("real-stack criterion tags: %s" % ", ".join(sorted(set(real))))

    return {
        "required": bool(reasons),
        "reason": "; ".join(reasons) if reasons else
                  ("no L2+ complexity and no real-stack criterion"
                   if complexity or tags else "plan declares neither complexity nor criteria"),
        "complexity": complexity,
        "real_stack_tags": sorted(set(real)),
        "tags": tags,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="does this plan require verification evidence?")
    ap.add_argument("plan")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    path = a.plan
    if not os.path.isfile(path):
        print("[evidence_level] BLOCKED plan not readable: %s" % path)
        return 2
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("[evidence_level] BLOCKED %s" % exc)
        return 2

    result = derive(text)
    if a.json:
        print(json.dumps(result))
    else:
        print("REQUIRED %s" % result["reason"] if result["required"]
              else "OPTIONAL %s" % result["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
