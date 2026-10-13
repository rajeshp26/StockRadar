#!/usr/bin/env python3
"""Scenario matrix generator -- DID-017.

A weak model forgets cases. This script supplies the breadth deterministically; the model only
supplies judgement per row. For every real-stack acceptance criterion in the plan it emits one row
per real-data shape in the manifest, per universal perturbation, and per conditional perturbation
whose keyword appears in the criterion text. Each row must end as `test:<name>` (a test that
exists) or `NA: <reason, four words or more>`; system_test_lint.py (rule ST08) refuses
unresolved rows, so the matrix cannot be skipped.

Usage: python3 framework/testing/scenario_matrix.py --plan PLAN.md [--root .] [--out FILE]
Re-running keeps the resolutions of rows that still exist.
Exit 0 written | 2 BLOCKED
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _lint_mod():
    spec = importlib.util.spec_from_file_location("stl_for_matrix",
                                                  os.path.join(HERE, "system_test_lint.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build(plan, root):
    stl = _lint_mod()
    policy = stl.load_policy(root)
    acs, _ = stl.plan_acs(plan)
    need = {a: v for a, v in acs.items() if v[0] in stl.REAL_TAGS}
    shapes = []
    mp = os.path.join(root, policy["data_manifest"])
    if os.path.isfile(mp):
        for e in json.load(open(mp, encoding="utf-8-sig")).get("datasets", []):
            shapes += [s for s in (e.get("shapes") or []) if s not in shapes]
    rows = []
    for a, (_tag, text) in need.items():
        if shapes:
            for s in shapes:
                rows.append((a, "shape:" + s, "exercise the criterion on real data of this shape"))
        else:
            rows.append((a, "shape:UNKNOWN", "manifest has no shapes yet: profile the real data "
                         "first, then regenerate"))
        for p in policy.get("universal_perturbations", []):
            rows.append((a, "break:" + p["name"], p.get("hint", "")))
        for p in policy.get("conditional_perturbations", []):
            if re.search(p["when"], text, re.I):
                rows.append((a, "break:" + p["name"], p.get("hint", "")))
    return rows, need


def old_resolutions(path):
    out = {}
    if os.path.isfile(path):
        for ln in open(path, encoding="utf-8-sig").read().replace("\r", "").split("\n"):
            if re.match(r"^\|\s*M-\d+", ln):
                c = [x.strip() for x in ln.strip().strip("|").split("|")]
                if len(c) >= 4 and c[3] != "[ ]":
                    out[(c[1], c[2])] = c[3]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        rows, need = build(a.plan, a.root)
    except (OSError, ValueError, KeyError) as exc:
        print("[scenario_matrix] BLOCKED %s" % exc)
        return 2
    out = a.out or re.sub(r"\.md$", "", a.plan) + ".SYSTEM-MATRIX.md"
    keep = old_resolutions(out)
    lines = ["# System-test scenario matrix", "",
             "Resolve every row: `test:<test function or title>` (the test must exist) or",
             "`NA: <why this scenario cannot apply, four words or more>`. Unresolved rows fail the lint.",
             "", "| id | criterion | scenario | resolution |", "|---|---|---|---|"]
    for i, (ac, label, hint) in enumerate(rows, 1):
        res = keep.get((ac, label), "[ ]")
        lines.append("| M-%03d | %s | %s | %s |" % (i, ac, label, res))
    lines += ["", "Hints:"] + ["- %s: %s" % (l, h) for _a, l, h in rows if h][:40]
    open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("[scenario_matrix] wrote %s: %d row(s) for %d criterion(s)" % (out, len(rows), len(need)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
