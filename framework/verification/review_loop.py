#!/usr/bin/env python3
"""Review loop manager - bounded review/fix/re-review cycles.

Implements ARIS-style bounded review loops with MAX_ROUNDS.
Prevents infinite review cycles while ensuring findings are addressed.

Usage:
    python3 framework/verification/review_loop.py start --task-id TASK-ID
    python3 framework/verification/review_loop.py record-round --task-id TASK-ID --round N --findings N
    python3 framework/verification/review_loop.py check --task-id TASK-ID
    python3 framework/verification/review_loop.py complete --task-id TASK-ID
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bounded loop configuration
MAX_ROUNDS = 4  # From ARIS pattern
MIN_FINDINGS_TO_CONTINUE = 1  # Stop when fewer findings than this


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


def review_state_path() -> Path:
    return _state_root() / "verification" / "review_state.json"


def load_state() -> dict:
    p = review_state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def save_state(state: dict):
    p = review_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def start_review(task_id: str) -> dict:
    """Initialize a review loop for a task."""
    state = load_state()
    
    if task_id in state and state[task_id].get("status") == "IN_PROGRESS":
        return {"error": f"Review loop already in progress for {task_id}"}
    
    state[task_id] = {
        "task_id": task_id,
        "status": "IN_PROGRESS",
        "current_round": 0,
        "max_rounds": MAX_ROUNDS,
        "rounds": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "final_disposition": None
    }
    
    save_state(state)
    return state[task_id]


def record_round(task_id: str, round_num: int, findings_count: int, 
                 finding_details: list[dict] = None) -> dict:
    """Record a review round's results."""
    state = load_state()
    
    if task_id not in state:
        return {"error": f"No review loop found for {task_id}"}
    
    task_state = state[task_id]
    
    if task_state["status"] != "IN_PROGRESS":
        return {"error": f"Review loop for {task_id} is not in progress"}
    
    # Record the round
    round_record = {
        "round": round_num,
        "findings_count": findings_count,
        "findings": finding_details or [],
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    
    task_state["rounds"].append(round_record)
    task_state["current_round"] = round_num
    
    # Check stopping conditions
    should_stop = False
    stop_reason = None
    
    if round_num >= MAX_ROUNDS:
        should_stop = True
        stop_reason = "MAX_ROUNDS_REACHED"
    elif findings_count < MIN_FINDINGS_TO_CONTINUE:
        should_stop = True
        stop_reason = "NO_SIGNIFICANT_FINDINGS"
    
    if should_stop:
        task_state["status"] = "COMPLETED"
        task_state["completed_at"] = datetime.now(timezone.utc).isoformat()
        task_state["final_disposition"] = stop_reason
    
    save_state(state)
    return task_state


def check_review(task_id: str) -> dict:
    """Check the current state of a review loop."""
    state = load_state()
    
    if task_id not in state:
        return {"exists": False, "task_id": task_id}
    
    task_state = state[task_id]
    
    # Calculate if more rounds are allowed
    can_continue = (
        task_state["status"] == "IN_PROGRESS" and
        task_state["current_round"] < MAX_ROUNDS
    )
    
    return {
        "exists": True,
        "task_id": task_id,
        "status": task_state["status"],
        "current_round": task_state["current_round"],
        "max_rounds": MAX_ROUNDS,
        "can_continue": can_continue,
        "rounds_completed": len(task_state["rounds"]),
        "final_disposition": task_state.get("final_disposition")
    }


def complete_review(task_id: str, disposition: str) -> dict:
    """Manually complete a review loop with a disposition."""
    state = load_state()
    
    if task_id not in state:
        return {"error": f"No review loop found for {task_id}"}
    
    task_state = state[task_id]
    task_state["status"] = "COMPLETED"
    task_state["completed_at"] = datetime.now(timezone.utc).isoformat()
    task_state["final_disposition"] = disposition
    
    save_state(state)
    return task_state


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Review loop manager")
    sub = ap.add_subparsers(dest="cmd", required=True)
    
    # start
    st = sub.add_parser("start")
    st.add_argument("--task-id", required=True)
    
    # record-round
    rr = sub.add_parser("record-round")
    rr.add_argument("--task-id", required=True)
    rr.add_argument("--round", type=int, required=True)
    rr.add_argument("--findings", type=int, required=True)
    rr.add_argument("--finding-details", type=str, help="JSON array of finding details")
    
    # check
    ck = sub.add_parser("check")
    ck.add_argument("--task-id", required=True)
    
    # complete
    cp = sub.add_parser("complete")
    cp.add_argument("--task-id", required=True)
    cp.add_argument("--disposition", required=True)
    
    a = ap.parse_args()
    
    if a.cmd == "start":
        result = start_review(a.task_id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if "error" not in result else 1)
    
    elif a.cmd == "record-round":
        finding_details = None
        if a.finding_details:
            try:
                finding_details = json.loads(a.finding_details)
            except json.JSONDecodeError:
                print(json.dumps({"error": "invalid finding-details JSON"}))
                sys.exit(1)
        result = record_round(a.task_id, a.round, a.findings, finding_details)
        print(json.dumps(result, indent=2))
        sys.exit(0 if "error" not in result else 1)
    
    elif a.cmd == "check":
        result = check_review(a.task_id)
        print(json.dumps(result, indent=2))
        sys.exit(0)
    
    elif a.cmd == "complete":
        result = complete_review(a.task_id, a.disposition)
        print(json.dumps(result, indent=2))
        sys.exit(0 if "error" not in result else 1)
