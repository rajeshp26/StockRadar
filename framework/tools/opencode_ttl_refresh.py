"""Keep an OpenCode location lease fresh so the TTL sweeper never fires.

WHY THIS EXISTS
The location layer stamps an absolute `expiresAt` once, at registration, and never
renews it (its refresh listener requires a `location` field that durable events do
not carry). A sweeper running every minute then calls
`interrupt(id, {reason: "inactivity"})` on every **active** execution at an expired
location. The result is that any step running longer than the ~60 minute TTL is
killed mid-flight and reported as "Step interrupted" / "Tool execution interrupted".

WHAT THIS DOES
Evicts the location's cached services on a timer, well before the TTL expires. The
next use of the location re-registers it, which re-stamps `expiresAt` and starts a
fresh window. Eviction disposes cached services; it does not interrupt running work.

EVIDENCE (see framework/docs/OPENCODE_SESSION_INTERRUPTION_ROOT_CAUSE_ANALYSIS.md)
  - verified: evicting a location mid-tool returns success and the in-flight tool
    runs to completion
  - verified: an idle evicted location disappears from the loaded set; a busy one
    reappears immediately, i.e. it re-registered
  - inferred: re-registration re-stamps expiresAt. The API does not expose expiry,
    so the reset itself is not directly measurable.

WHAT THIS DOES NOT DO
It does not fix the underlying defect, and it is not a substitute for an upstream
fix. If the sweeper fires before a refresh lands, the step still dies. Keep the
interval comfortably below 60 minutes.

Usage
  python framework/tools/opencode_ttl_refresh.py                 # every 45 min, this directory
  python framework/tools/opencode_ttl_refresh.py --once          # single refresh, then exit
  python framework/tools/opencode_ttl_refresh.py --interval 1800 # every 30 min
  python framework/tools/opencode_ttl_refresh.py --locations C:\\work\\a C:\\work\\b

Exit codes: 0 refreshed ok (or --once succeeded) | 2 could not reach a usable CLI
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

# The stale `opencode.EXE` shim on PATH lacks the `api` subcommand entirely; these
# are the locations that actually ship a CLI with it.
CANDIDATES = (
    r"C:\nvm4w\nodejs\node_modules\@opencode\cli\bin\opencode.exe",
    "/usr/local/bin/opencode",
    "/usr/bin/opencode",
)

# This process runs as a loop with no user watching it, so every child it spawns must be
# console-free. On Windows a child created without CREATE_NO_WINDOW is given a new console when
# its parent owns none, which shows up as a console window appearing and vanishing on the
# desktop. The telemetry plugin had the same defect on a 60-second timer (patch 08); this is the
# 45-minute one. Zero elsewhere, where the flag does not exist and there is no console to hide.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def resolve_cli(explicit: str) -> str | None:
    """Return a CLI path that understands `api`, or None."""
    seen: list[str] = []
    for cand in ([explicit] if explicit else []) + list(CANDIDATES):
        if cand and os.path.isfile(cand):
            seen.append(cand)
    for cand in seen:
        try:
            r = subprocess.run(
                [cand, "api", "get", "/api/info"],
                capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and "version" in r.stdout:
            return cand
    # Last resort: PATH, but only if it advertises the api subcommand.
    onpath = shutil.which("opencode")
    if onpath and onpath not in seen:
        try:
            r = subprocess.run(
                [onpath, "api", "get", "/api/info"],
                capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW,
            )
            if r.returncode == 0:
                return onpath
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def refresh(exe: str, location: str) -> bool:
    body = json.dumps({"location": {"directory": location}})
    try:
        r = subprocess.run(
            [exe, "api", "delete", "/api/debug/location", "--data", body],
            capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  refresh error: {exc}", flush=True)
        return False
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    if r.returncode == 0:
        print(f"  [{stamp}] refreshed lease for {location}", flush=True)
        return True
    print(f"  [{stamp}] refresh failed rc={r.returncode} "
          f"{r.stderr.strip()[:160]!r}", flush=True)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=45 * 60,
                    help="seconds between refreshes (default 2700 = 45 min)")
    ap.add_argument("--locations", nargs="*", default=None,
                    help="directories to keep fresh (default: cwd)")
    ap.add_argument("--once", action="store_true", help="refresh once and exit")
    ap.add_argument("--exe", default="", help="path to the opencode CLI")
    args = ap.parse_args()

    if args.interval >= 3600:
        print("refusing an interval >= the 60 minute TTL; the sweeper would still fire",
              file=sys.stderr)
        return 2

    exe = resolve_cli(args.exe)
    if not exe:
        print("UNVERIFIABLE: no opencode CLI with the `api` subcommand found",
              file=sys.stderr)
        return 2
    print(f"cli: {exe}")

    locations = args.locations or [os.getcwd()]
    print(f"interval: {args.interval}s   locations: {locations}")

    if args.once:
        ok = all([refresh(exe, loc) for loc in locations])
        return 0 if ok else 2

    while True:
        for loc in locations:
            refresh(exe, loc)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
