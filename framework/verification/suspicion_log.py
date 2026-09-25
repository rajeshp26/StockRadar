#!/usr/bin/env python3
"""Reviewer suspicion log - persistent reviewer memory across review rounds.

Inspired by ARIS reviewer memory patterns. Tracks concerns that reviewers
have about evidence, claims, or verification results. Suspicions persist
across review rounds and must be explicitly resolved or escalated.

Usage:
    python3 framework/verification/suspicion_log.py add --json '{...}'
    python3 framework/verification/suspicion_log.py resolve --id SUSP-NNN
    python3 framework/verification/suspicion_log.py list [--status open|resolved|escalated]
    python3 framework/verification/suspicion_log.py check --task-id TASK-ID
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _state_root() -> Path:
    """Resolve the GSD state root."""
    try:
        r = subprocess.run(["python3", "framework/adapters/gsd_state.py", "state-root"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return Path(".planning")


def suspicion_log_path() -> Path:
    return _state_root() / "verification" / "suspicion_log.jsonl"


def load() -> list[dict]:
    p = suspicion_log_path()
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
            print(f"WARN: suspicion log line {i} is not valid JSON -- skipped", file=sys.stderr)
    return out


def _next_suspicion_id(records: list[dict]) -> str:
    """SUSP-NNN continuing the highest existing number."""
    highest = 0
    for r in records:
        sid = str(r.get("suspicion_id") or "")
        if sid.startswith("SUSP-"):
            try:
                highest = max(highest, int(sid[5:]))
            except ValueError:
                continue
    return f"SUSP-{highest + 1:03d}"


def add(entry: dict) -> str:
    """Add a new suspicion to the log."""
    records = load()
    
    if "suspicion_id" not in entry:
        entry["suspicion_id"] = _next_suspicion_id(records)
    
    # Set defaults
    entry["status"] = entry.get("status", "OPEN")
    entry["created"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    entry["resolved_by"] = entry.get("resolved_by")
    entry["resolution_evidence"] = entry.get("resolution_evidence")
    
    # Validate
    required = ["suspicion_id", "task_id", "reviewer", "suspicion", "evidence_requested"]
    for k in required:
        if not entry.get(k):
            print(json.dumps({"error": f"missing required field: {k}"}))
            sys.exit(1)
    
    if entry["status"] not in ("OPEN", "RESOLVED", "ESCALATED"):
        print(json.dumps({"error": f"invalid status: {entry['status']}"}))
        sys.exit(1)
    
    # Append
    p = suspicion_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    
    return entry["suspicion_id"]


def resolve(suspicion_id: str, resolved_by: str, resolution_evidence: str) -> bool:
    """Resolve an open suspicion."""
    records = load()
    updated = False
    
    for r in records:
        if r.get("suspicion_id") == suspicion_id and r.get("status") == "OPEN":
            r["status"] = "RESOLVED"
            r["resolved_by"] = resolved_by
            r["resolution_evidence"] = resolution_evidence
            r["resolved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            updated = True
    
    if not updated:
        return False
    
    # Rewrite the file
    p = suspicion_log_path()
    with p.open("w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    
    return True


def list_suspicions(status_filter: str = None, task_id: str = None) -> list[dict]:
    """List suspicions with optional filtering."""
    records = load()
    
    if status_filter:
        records = [r for r in records if r.get("status") == status_filter.upper()]
    
    if task_id:
        records = [r for r in records if r.get("task_id") == task_id]
    
    return records


def check_task(task_id: str) -> dict:
    """Check if a task has open suspicions that block completion."""
    records = load()
    open_suspicions = [r for r in records if r.get("task_id") == task_id and r.get("status") == "OPEN"]
    
    return {
        "task_id": task_id,
        "open_count": len(open_suspicions),
        "suspicions": open_suspicions,
        "blocks_completion": len(open_suspicions) > 0
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Reviewer suspicion log")
    sub = ap.add_subparsers(dest="cmd", required=True)
    
    # add
    ad = sub.add_parser("add")
    ad.add_argument("--json", default="")
    ad.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    
    # resolve
    rs = sub.add_parser("resolve")
    rs.add_argument("--id", required=True)
    rs.add_argument("--resolved-by", required=True)
    rs.add_argument("--resolution-evidence", required=True)
    
    # list
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=["open", "resolved", "escalated"])
    ls.add_argument("--task-id")
    
    # check
    ck = sub.add_parser("check")
    ck.add_argument("--task-id", required=True)
    
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    if a.cmd == "add" and not getattr(a, "json", ""):
        ap.error("--json or --json-file is required for add")
    
    if a.cmd == "add":
        try:
            entry = json.loads(a.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad json: {e}"}))
            sys.exit(1)
        sid = add(entry)
        print(json.dumps({"suspicion_id": sid}))
        sys.exit(0)
    
    elif a.cmd == "resolve":
        success = resolve(a.id, a.resolved_by, a.resolution_evidence)
        if success:
            print(json.dumps({"status": "resolved", "suspicion_id": a.id}))
        else:
            print(json.dumps({"error": f"suspicion {a.id} not found or not OPEN"}))
            sys.exit(1)
    
    elif a.cmd == "list":
        results = list_suspicions(a.status, a.task_id)
        print(json.dumps(results, indent=2))
        sys.exit(0)
    
    elif a.cmd == "check":
        result = check_task(a.task_id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if not result["blocks_completion"] else 1)
