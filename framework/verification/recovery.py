#!/usr/bin/env python3
"""Recovery state manager - durable execution state for session recovery.

Implements ARIS-inspired recovery patterns. Enables resumption from
durable state rather than conversational archaeology.

Usage:
    python3 framework/verification/recovery.py checkpoint --task-id TASK-ID
    python3 framework/verification/recovery.py save --task-id TASK-ID --json '{...}'
    python3 framework/verification/recovery.py restore --task-id TASK-ID
    python3 framework/verification/recovery.py last-known-good --task-id TASK-ID
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


def recovery_dir() -> Path:
    return _state_root() / "recovery"


def checkpoint_path(task_id: str) -> Path:
    return recovery_dir() / f"{task_id}_checkpoint.json"


def last_known_good_path(task_id: str) -> Path:
    return recovery_dir() / f"{task_id}_last_known_good.json"


def save_checkpoint(task_id: str, state: dict) -> dict:
    """Save a recovery checkpoint for a task.
    
    The checkpoint captures the complete execution state:
    - task contract
    - current phase
    - gate results
    - claims and evidence
    - open findings
    - review suspicions
    - next legal action
    """
    checkpoint = {
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "version": "1.0"
    }
    
    p = checkpoint_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(checkpoint, indent=2))
    
    return checkpoint


def load_checkpoint(task_id: str) -> dict | None:
    """Load the recovery checkpoint for a task."""
    p = checkpoint_path(task_id)
    if not p.exists():
        return None
    
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def save_last_known_good(task_id: str, state: dict) -> dict:
    """Save a last-known-good state (post-verification)."""
    lkg = {
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "version": "1.0"
    }
    
    p = last_known_good_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lkg, indent=2))
    
    return lkg


def load_last_known_good(task_id: str) -> dict | None:
    """Load the last-known-good state for a task."""
    p = last_known_good_path(task_id)
    if not p.exists():
        return None
    
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def restore_from_checkpoint(task_id: str) -> dict:
    """Restore execution state from checkpoint.
    
    Returns the state needed to resume:
    - task contract
    - current gate
    - outstanding claims
    - open findings
    - next legal action
    """
    checkpoint = load_checkpoint(task_id)
    if not checkpoint:
        return {"error": f"No checkpoint found for task {task_id}"}
    
    lkg = load_last_known_good(task_id)
    
    return {
        "task_id": task_id,
        "checkpoint": checkpoint,
        "last_known_good": lkg,
        "can_resume": True,
        "resume_from": checkpoint["state"].get("current_phase", "unknown")
    }


def record_gate_result(task_id: str, gate: str, result: dict) -> dict:
    """Record a gate result in the checkpoint."""
    checkpoint = load_checkpoint(task_id) or {"task_id": task_id, "state": {}}
    
    if "gate_results" not in checkpoint["state"]:
        checkpoint["state"]["gate_results"] = {}
    
    checkpoint["state"]["gate_results"][gate] = {
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return save_checkpoint(task_id, checkpoint["state"])


def record_claim(task_id: str, claim_id: str, claim_data: dict) -> dict:
    """Record a claim in the checkpoint."""
    checkpoint = load_checkpoint(task_id) or {"task_id": task_id, "state": {}}
    
    if "claims" not in checkpoint["state"]:
        checkpoint["state"]["claims"] = []
    
    checkpoint["state"]["claims"].append({
        "claim_id": claim_id,
        "data": claim_data,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    })
    
    return save_checkpoint(task_id, checkpoint["state"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Recovery state manager")
    sub = ap.add_subparsers(dest="cmd", required=True)
    
    # checkpoint
    cp = sub.add_parser("checkpoint")
    cp.add_argument("--task-id", required=True)
    
    # save
    sv = sub.add_parser("save")
    sv.add_argument("--task-id", required=True)
    sv.add_argument("--json", default="")
    sv.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    
    # restore
    rs = sub.add_parser("restore")
    rs.add_argument("--task-id", required=True)
    
    # last-known-good
    lkg = sub.add_parser("last-known-good")
    lkg.add_argument("--task-id", required=True)
    
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    if a.cmd == "save" and not getattr(a, "json", ""):
        ap.error("--json or --json-file is required for save")
    
    if a.cmd == "checkpoint":
        # Just show current checkpoint
        checkpoint = load_checkpoint(a.task_id)
        if checkpoint:
            print(json.dumps(checkpoint, indent=2))
        else:
            print(json.dumps({"error": f"No checkpoint for task {a.task_id}"}))
        sys.exit(0)
    
    elif a.cmd == "save":
        try:
            state = json.loads(a.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad json: {e}"}))
            sys.exit(1)
        result = save_checkpoint(a.task_id, state)
        print(json.dumps({"status": "saved", "task_id": a.task_id}))
        sys.exit(0)
    
    elif a.cmd == "restore":
        result = restore_from_checkpoint(a.task_id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if "error" not in result else 1)
    
    elif a.cmd == "last-known-good":
        lkg_state = load_last_known_good(a.task_id)
        if lkg_state:
            print(json.dumps(lkg_state, indent=2))
        else:
            print(json.dumps({"error": f"No last-known-good for task {a.task_id}"}))
        sys.exit(0)
