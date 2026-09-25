#!/usr/bin/env python3
"""Retro ledger. Append-only record of defect escapes and the framework changes they caused.

Two jobs the individual retrospective cannot do:

1. RECURRENCE. The same (injection_phase, defect_class, escaped_checkpoint) appearing twice
   means the first fix did not work. A framework that files the same finding repeatedly is
   generating paperwork, not learning. Second occurrence escalates to human.

2. UNVERIFIED FIXES. A retro that recommends a change and never lands it is a wish. Every
   entry carries `fix_landed` and `fix_verified_by` (a command + exit code). An entry with a
   recommendation and no landed fix past its due date is reported as debt.

Exit codes:
  0  ledger consistent
  1  recurrence detected at or beyond threshold, or a fix claimed without verification
  3  ledger empty or unreadable (nothing to conclude — never a pass)
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

RECURRENCE_THRESHOLD = 2   # 2nd occurrence of the same signature escalates


def _state_root() -> Path:
    try:
        r = subprocess.run(["python3", "framework/adapters/gsd_state.py", "state-root"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return Path(".planning")


def ledger_path() -> Path:
    return _state_root() / "retro" / "ledger.jsonl"


def load() -> list[dict]:
    p = ledger_path()
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARN: ledger line {i} is not valid JSON — skipped", file=sys.stderr)
    return out


def signature(e: dict) -> str:
    """What makes two escapes 'the same gap'. Deliberately excludes the task id and the
    human-written description: the same structural gap in different words is still the same
    gap, and matching on prose would let a rephrase hide a recurrence."""
    return "|".join([
        e.get("injected_at", "?"),
        e.get("defect_class", "?"),
        (e.get("primary_gap") or "?"),
        ",".join(sorted(e.get("routing_gaps", []) + e.get("containment_misses", []))) or "?",
    ])


def append(entry: dict) -> str:
    required = ["task_id", "injected_at", "caught_at", "defect_class", "primary_gap",
                "fix_target", "fix_landed"]
    missing = [k for k in required if k not in entry]
    if missing:
        print(json.dumps({"error": "incomplete retro entry", "missing": missing}),
              file=sys.stderr)
        sys.exit(1)
    if entry["fix_target"] != "none_human_judgement" and not entry.get("fix_landed"):
        entry.setdefault("debt_opened", date.today().isoformat())
    entry["signature"] = signature(entry)
    entry.setdefault("recorded_at", datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"))

    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return str(p)


def analyse() -> dict:
    entries = load()
    if not entries:
        return {"status": "empty", "entries": 0,
                "note": "no retrospectives recorded — nothing to conclude"}

    sigs = Counter(signature(e) for e in entries)
    recurring = {s: n for s, n in sigs.items() if n >= RECURRENCE_THRESHOLD}

    by_target = Counter(e.get("fix_target", "?") for e in entries)
    by_phase = Counter(e.get("injected_at", "?") for e in entries)
    by_gap = Counter(e.get("primary_gap", "?") for e in entries)

    # A fix claimed as landed must name how it was proven.
    unverified = [{"task_id": e.get("task_id"), "fix_target": e.get("fix_target")}
                  for e in entries
                  if e.get("fix_landed") and not e.get("fix_verified_by")]

    open_debt = [{"task_id": e.get("task_id"), "fix_target": e.get("fix_target"),
                  "opened": e.get("debt_opened")}
                 for e in entries
                 if e.get("fix_target") != "none_human_judgement" and not e.get("fix_landed")]

    # Recurrence detail: which tasks, so the escalation is actionable rather than a count.
    detail = defaultdict(list)
    for e in entries:
        s = signature(e)
        if s in recurring:
            detail[s].append({"task_id": e.get("task_id"),
                              "fix_target": e.get("fix_target"),
                              "fix_landed": e.get("fix_landed"),
                              "recorded_at": e.get("recorded_at")})

    judgement_rate = by_target.get("none_human_judgement", 0) / len(entries)

    return {
        "status": "recurrence" if recurring else ("unverified_fix" if unverified else "ok"),
        "entries": len(entries),
        "recurring_signatures": [
            {"signature": s, "occurrences": n, "history": detail[s]}
            for s, n in sorted(recurring.items(), key=lambda kv: -kv[1])
        ],
        "unverified_fixes": unverified,
        "open_fix_debt": open_debt,
        "by_injection_phase": dict(by_phase),
        "by_primary_gap": dict(by_gap),
        "by_fix_target": dict(by_target),
        # High judgement rate is a signal, not a failure: it can mean the framework has
        # reached the limit of what checks can express. Reported so the trend is visible.
        "human_judgement_rate": round(judgement_rate, 3),
        "escalate": bool(recurring) or bool(unverified),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Retro ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyse")
    sub.add_parser("path")
    ad = sub.add_parser("append")
    ad.add_argument("--json", default="")
    ad.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    if a.cmd == "append" and not getattr(a, "json", ""):
        ap.error("--json or --json-file is required for append")

    if a.cmd == "path":
        print(ledger_path()); sys.exit(0)
    if a.cmd == "append":
        try:
            entry = json.loads(a.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad json: {e}"}), file=sys.stderr); sys.exit(1)
        print(append(entry)); sys.exit(0)

    out = analyse()
    print(json.dumps(out, indent=2))
    if out["status"] == "empty":
        sys.exit(3)
    sys.exit(1 if out["escalate"] else 0)
