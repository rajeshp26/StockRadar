#!/usr/bin/env python3
"""Full verification for the agentic framework implementation.

Offline (default): unit tests + config consistency + framework MCP server
handshake (all inside the test suite).
Live (--live): also boots the real Context7 and Playwright MCP servers via
npx and performs an initialize/tools/list handshake with each.

Exit code 0 only if everything run has passed."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(cmd, **kw):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, **kw).returncode


def main() -> int:
    live = "--live" in sys.argv
    rc = 0
    rc |= run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    for demo in ["demo_support.py", "demo_research.py"]:
        print(f"\n--- example: {demo} ---")
        rc |= run([sys.executable, f"examples/{demo}"])
    if live:
        print("\n--- live MCP handshake checks (npx) ---")
        rc |= run([sys.executable, "scripts/live_mcp_check.py"])
    else:
        print("\n(live MCP checks skipped; rerun with --live)")
    print("\nVERIFY:", "PASS" if rc == 0 else "FAIL")
    return rc


if __name__ == "__main__":
    sys.exit(main())
