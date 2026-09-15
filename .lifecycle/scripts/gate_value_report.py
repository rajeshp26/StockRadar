#!/usr/bin/env python3
"""
gate_value_report.py — the counterweight to retro/ledger.py.

Self-optimization roadmap, Tier 1 #3: `retrospective` only ever tightens the
framework (adds or sharpens a check). Nothing measured whether an EXISTING
gate or checklist item is pulling its weight. Left alone, that is a one-way
ratchet — exactly the failure mode Rule 2 ("rigorous in reasoning but
proportional in execution") exists to prevent at the feature level, just not
previously enforced at the framework level over time.

This script reads every gate ledger entry under `features/*/gates/*.md`
across the repo (or a `--window` most-recent subset of features) and reports,
per gate id:

  - times certified
  - verdict breakdown (PASS / FAIL / CONDITIONAL / NOT_APPLICABLE)
  - "pruning candidate": a gate with zero non-PASS verdicts across the
    configured window (`config.yml` `gate_value.prune_candidate_threshold`)
    never actually blocked anything in that window. That does not mean it is
    useless — it may be a floor nobody has hit yet, or it may be doing
    exactly its job by deterring bad work before it's submitted. It means
    the gate is a *candidate* for a human to look at, nothing more. Pruning
    still requires Reviewer concurrence (config.yml `gate_value.never_prune_without`).

Ledger entries are parsed with the same field convention `lifecycle-validate.py`
uses (front-matter-style `Key: value` lines), since gate ledgers are plain
Markdown, not JSON.

Usage:
    gate_value_report.py [--root .] [--config .lifecycle/config.yml] [--json]

Exit code is always 0 — this is a report, not a gate. Pair it with the
existing §12.5 preventive-control-improvement-rate check at the same review
cadence (see config.yml `gate_value.review_cadence`).
"""
import sys
import os
import re
import glob
import json
import argparse

try:
    import yaml
except ImportError:
    yaml = None

GATE_RE = re.compile(r"^Gate:\s*(\S+)", re.M)
VERDICT_RE = re.compile(r"^Verdict:\s*([A-Z_]+)", re.M)


def load_config(path):
    if yaml is None or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def find_gate_files(root, window_features):
    feature_dirs = sorted(
        glob.glob(os.path.join(root, "features", "*")),
        key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
        reverse=True,
    )
    if window_features:
        feature_dirs = feature_dirs[:window_features]
    files = []
    for fd in feature_dirs:
        files.extend(glob.glob(os.path.join(fd, "gates", "*.md")))
    return files


def parse_gate_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    gate_match = GATE_RE.search(text)
    verdict_match = VERDICT_RE.search(text)
    gate_id = gate_match.group(1) if gate_match else os.path.splitext(os.path.basename(path))[0]
    verdict = verdict_match.group(1) if verdict_match else "UNKNOWN"
    return gate_id, verdict


def build_report(files, threshold):
    per_gate = {}
    for f in files:
        gate_id, verdict = parse_gate_file(f)
        entry = per_gate.setdefault(gate_id, {"PASS": 0, "FAIL": 0, "CONDITIONAL": 0,
                                               "NOT_APPLICABLE": 0, "UNKNOWN": 0, "total": 0,
                                               "files": []})
        entry[verdict] = entry.get(verdict, 0) + 1
        entry["total"] += 1
        entry["files"].append(f)

    report = []
    for gate_id, counts in sorted(per_gate.items()):
        non_pass = counts["total"] - counts["PASS"] - counts["NOT_APPLICABLE"]
        report.append({
            "gate": gate_id,
            "total_certifications": counts["total"],
            "verdicts": {k: v for k, v in counts.items() if k not in ("total", "files")},
            "non_pass_count": non_pass,
            "prune_candidate": non_pass <= threshold and counts["total"] > 0,
        })
    return report


def main():
    p = argparse.ArgumentParser(description="Gate-value / pruning-candidate report")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=os.path.join(".lifecycle", "config.yml"))
    p.add_argument("--window", type=int, default=None,
                    help="override config.yml gate_value.window_features")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    config = load_config(args.config)
    gv_config = config.get("gate_value", {})
    if not gv_config.get("enabled", True):
        print("gate_value_report: gate_value.enabled is false in config.yml — nothing to report")
        return 0

    window = args.window if args.window is not None else gv_config.get("window_features")
    threshold = gv_config.get("prune_candidate_threshold", 0)

    files = find_gate_files(args.root, window)
    if not files:
        print("gate_value_report: no gate ledger entries found under features/*/gates/")
        return 0

    report = build_report(files, threshold)
    candidates = [r["gate"] for r in report if r["prune_candidate"]]

    if args.json:
        print(json.dumps({
            "window_features": window,
            "threshold": threshold,
            "gates": report,
            "prune_candidates": candidates,
        }, indent=2))
    else:
        print(f"Gate value report — window={window or 'all'} features, "
              f"prune_candidate_threshold={threshold}\n")
        print(f"{'Gate':<8} {'Total':<7} {'PASS':<6} {'FAIL':<6} {'COND':<6} {'N/A':<6} Prune candidate?")
        print("-" * 70)
        for r in report:
            v = r["verdicts"]
            flag = "YES — review with Reviewer before removing" if r["prune_candidate"] else ""
            print(f"{r['gate']:<8} {r['total_certifications']:<7} "
                  f"{v.get('PASS', 0):<6} {v.get('FAIL', 0):<6} "
                  f"{v.get('CONDITIONAL', 0):<6} {v.get('NOT_APPLICABLE', 0):<6} {flag}")
        print()
        if candidates:
            print(f"Pruning candidates this window: {candidates}")
            print(gv_config.get("never_prune_without",
                                 "Do not remove without recorded Reviewer concurrence."))
        else:
            print("No pruning candidates this window.")

    return 0


if __name__ == "__main__":
    sys.exit(main())