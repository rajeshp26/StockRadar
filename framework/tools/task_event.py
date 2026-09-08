"""Plain-arg lifecycle event emitter for supervised delegated tasks.

Wrapper around `gsd_state.py task-event` that builds the --json payload with
json.dumps, so PowerShell 5.1 can never mangle quoted JSON (the
BLOCKER_INVALID_JSON / TASK_INVALID_JSON failure mode that froze T-05's
successor attempts).

Usage (worker-facing - safe under PowerShell 5.1):
  python framework/tools/task_event.py --id T-07 --state ACK
  python framework/tools/task_event.py --id T-07 --state STARTED --detail "..."
  python framework/tools/task_event.py --id T-07 --state PROGRESS --checkpoint "execution_context" --detail "..."
  python framework/tools/task_event.py --id T-07 --state BLOCKED --detail "..."
  python framework/tools/task_event.py --id T-07 --state FAILED --failure-class AGENT_FAILURE --detail "..."
  python framework/tools/task_event.py --id T-07 --state COMPLETED --detail "..."
"""
import argparse
import json
import subprocess
import sys

ADAPTER = [sys.executable, "framework/adapters/gsd_state.py"]
LEGAL = ("ACK", "STARTED", "PROGRESS", "BLOCKED", "FAILED", "COMPLETED")


def main() -> int:
    ap = argparse.ArgumentParser(description="emit a task lifecycle event")
    ap.add_argument("--id", required=True, help="task id, e.g. T-07")
    ap.add_argument("--state", required=True, choices=LEGAL)
    ap.add_argument("--checkpoint", default="", help="named checkpoint reached")
    ap.add_argument("--detail", default="", help="free-form note")
    ap.add_argument("--emitter", default="", help="override emitter (defaults to contract agent)")
    ap.add_argument("--failure-class", default="", help="required for FAILED")
    a = ap.parse_args()

    payload = {"state": a.state}
    if a.checkpoint:
        payload["checkpoint"] = a.checkpoint
    if a.detail:
        payload["detail"] = a.detail
    if a.emitter:
        payload["emitter"] = a.emitter
    if a.failure_class:
        payload["failure_class"] = a.failure_class.upper()

    p = subprocess.run(
        [*ADAPTER, "task-event", "--id", a.id, "--json", json.dumps(payload)],
        capture_output=True,
        text=True,
    )
    if p.stdout:
        sys.stdout.write(p.stdout)
    if p.stderr:
        sys.stderr.write(p.stderr)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())