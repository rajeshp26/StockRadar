#!/usr/bin/env python3
"""Shortcut debt harvester.

Every deliberate simplification marked with a `shortcut:` comment is a debt
item. This collects them into one ledger so a deferral cannot quietly become
permanent.

Marker convention (see `framework/opencode/rules/shortcut-debt.md`):

    shortcut: <the limit>, <when to upgrade>

Legacy `ponytail:` markers are also recognised. A marker that names no upgrade
trigger is `no-trigger`: it has a ceiling but no trigger to revisit it, which is
how a deferral silently rots.

Read-only. The ledger of record is the retrospective ledger's `accepted` tier
(`framework/retro/ledger.py`); this tool is an input to it, never a second debt
store.

Exit codes:
    0  every marker names an upgrade trigger (or there are none)
    1  at least one marker has no trigger
    2  usage / scan error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# A comment prefix (#, //, /*) immediately followed by the marker word.
MARKER_RE = re.compile(r"(?:#|//|/\*)\s*(?P<kind>shortcut|ponytail):\s*(?P<body>.*)")
# ERE form for git grep (POSIX classes only).
GIT_PATTERN = r"(#|//|/\*)[[:space:]]*(shortcut|ponytail):"

# Directories the pure-Python fallback never descends into. The git path uses
# the repository's own .gitignore instead.
DEFAULT_IGNORES = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
    "dist", "build", "out", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".next", ".nuxt", ".tox", ".idea", ".vscode", "target", "vendor",
})


def _split_marker(body: str):
    """Return (ceiling, upgrade, has_trigger) from the text after the marker."""
    text = body.strip()
    for terminator in ("*/", "-->"):
        if text.endswith(terminator):
            text = text[: -len(terminator)].rstrip()
    if "," in text:
        ceiling, _, upgrade = text.partition(",")
        ceiling, upgrade = ceiling.strip(), upgrade.strip()
    else:
        ceiling, upgrade = text, ""
    return ceiling, upgrade, bool(upgrade)


def _row(path: str, line_no: int, text: str):
    match = MARKER_RE.search(text)
    if not match:
        return None
    ceiling, upgrade, has_trigger = _split_marker(match.group("body"))
    if not ceiling:
        # A bare marker with no ceiling is prose, not a deferral.
        return None
    return {
        "file": path,
        "line": line_no,
        "kind": match.group("kind"),
        "ceiling": ceiling,
        "upgrade": upgrade,
        "has_trigger": has_trigger,
    }


def _scan_git(root: Path):
    """Scan via `git grep` so the repository's .gitignore is honoured.

    Returns a list of (path, line, text) tuples, or None when git cannot be
    used (no git, not a work tree) so the caller falls back to a tree walk.
    """
    try:
        check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root), capture_output=True, text=True,
        )
        if check.returncode != 0:
            return None
        proc = subprocess.run(
            ["git", "grep", "--no-index", "--exclude-standard", "-nI",
             "-E", GIT_PATTERN, "--", "."],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except (OSError, ValueError):
        return None
    if proc.returncode not in (0, 1):  # 0 = matches, 1 = none, else error
        return None
    rows = []
    for line in proc.stdout.splitlines():
        head = re.match(r"(?P<path>[^:]*?):(?P<line>\d+):(?P<text>.*)$", line)
        if head:
            rows.append((head.group("path"), int(head.group("line")), head.group("text")))
    return rows


def _scan_walk(root: Path):
    """Best-effort fallback when git is unavailable. No .gitignore parsing."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORES]
        for name in filenames:
            file_path = Path(dirpath) / name
            try:
                data = file_path.read_bytes()
            except OSError:
                continue
            if b"\x00" in data[:1024]:
                continue  # binary
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            rel = file_path.relative_to(root).as_posix()
            for line_no, line in enumerate(text.splitlines(), 1):
                if MARKER_RE.search(line):
                    rows.append((rel, line_no, line))
    return rows


def harvest(root) -> list:
    root = Path(root).resolve()
    rows = _scan_git(root)
    if rows is None:
        rows = _scan_walk(root)
    markers = []
    for path, line_no, text in rows:
        row = _row(path, line_no, text)
        if row:
            markers.append(row)
    markers.sort(key=lambda r: (r["file"], r["line"]))
    return markers


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Harvest shortcut: debt markers.")
    parser.add_argument("--root", default=".", help="directory to scan (default: cwd)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    markers = harvest(root)
    no_trigger = [m for m in markers if not m["has_trigger"]]

    if args.json:
        print(json.dumps(
            {"count": len(markers), "no_trigger": len(no_trigger), "markers": markers},
            indent=2,
        ))
    elif not markers:
        print("No shortcut debt. Clean ledger.")
    else:
        for m in markers:
            upgrade = m["upgrade"] if m["has_trigger"] else "MISSING"
            print(f'{m["file"]}:{m["line"]}  ceiling="{m["ceiling"]}"  upgrade="{upgrade}"')
        print(f"{len(markers)} markers, {len(no_trigger)} with no trigger.")

    return 1 if no_trigger else 0


if __name__ == "__main__":
    sys.exit(main())
