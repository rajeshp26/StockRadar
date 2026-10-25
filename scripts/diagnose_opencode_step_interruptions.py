"""Detect OpenCode steps interrupted at the LocationActivity eviction wall.

Read-only. Reports aborted assistant steps whose duration clusters just past
3600 s (the hardcoded LocationActivity TTL), which is the signature of the
`reason: "inactivity"` eviction described in
docs/OPENCODE_SESSION_INTERRUPTION_ROOT_CAUSE_ANALYSIS.md.

Exit codes:
  0  no step interrupted at the eviction wall  -> fix appears effective
  1  at least one step interrupted at the wall -> defect still present
  2  could not verify (store missing/unreadable) -> treat as unverified, never a pass

Usage:
  python scripts/diagnose_opencode_step_interruptions.py
  python scripts/diagnose_opencode_step_interruptions.py --db <path> --limit 4000
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sqlite3
import sys

TTL_SECONDS = 3600.0
# Sweep granularity is 1 minute; allow registration offset + sweep + jitter.
WALL_LOW = 3600.0
WALL_HIGH = 3960.0


def default_db() -> pathlib.Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = pathlib.Path(local) / "opencode" / "opencode.db"
        if p.is_file():
            return p
    share = os.environ.get("XDG_DATA_HOME")
    if share:
        p = pathlib.Path(share) / "opencode" / "opencode.db"
        if p.is_file():
            return p
    return pathlib.Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def fmt_duration(seconds: float) -> str:
    return f"{seconds / 60:.1f}m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="", help="path to opencode.db")
    ap.add_argument("--limit", type=int, default=4000,
                    help="how many recent assistant messages to scan")
    args = ap.parse_args()

    db = pathlib.Path(args.db) if args.db else default_db()
    print(f"store: {db}")
    if not db.is_file():
        print(f"UNVERIFIABLE: no session store at {db}", file=sys.stderr)
        return 2

    try:
        con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT session_id, seq, time_created, data FROM session_message "
            "WHERE type='assistant' ORDER BY time_created DESC LIMIT ?",
            (args.limit,),
        ).fetchall()
        con.close()
    except sqlite3.Error as exc:
        print(f"UNVERIFIABLE: cannot read store: {exc}", file=sys.stderr)
        return 2

    interrupted = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except (TypeError, json.JSONDecodeError):
            continue
        err = data.get("error")
        if not isinstance(err, dict):
            continue
        if err.get("message") != "Step interrupted":
            continue
        created = (data.get("time") or {}).get("created") or r["time_created"]
        completed = (data.get("time") or {}).get("completed")
        if not isinstance(created, (int, float)) or not isinstance(completed, (int, float)):
            continue
        seconds = (completed - created) / 1000.0
        interrupted.append((created, seconds, r["session_id"], r["seq"]))

    if not interrupted:
        print(f"scanned {len(rows)} assistant messages: no 'Step interrupted' found")
        print("RESULT: PASS (nothing to measure)")
        return 0

    interrupted.sort()
    at_wall = [x for x in interrupted if WALL_LOW <= x[1] <= WALL_HIGH]

    print(f"scanned {len(rows)} assistant messages")
    print(f"'Step interrupted' events: {len(interrupted)}")
    print(f"  at the eviction wall [{WALL_LOW:.0f}s, {WALL_HIGH:.0f}s]: {len(at_wall)}")
    print(f"  below the wall (user/superseded-class): {len(interrupted) - len(at_wall)}")

    if at_wall:
        print("\nrecent wall hits:")
        for created, seconds, session, seq in at_wall[-10:]:
            when = dt.datetime.fromtimestamp(created / 1000, dt.timezone.utc)
            print(f"  {when:%Y-%m-%d %H:%M}Z  dur={fmt_duration(seconds):>7}  "
                  f"session={session[:16]}  seq={seq}")
        print("\nRESULT: FAIL - steps are still being interrupted at the ~60 minute wall")
        return 1

    print("\nRESULT: PASS - no interruption at the eviction wall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
