#!/usr/bin/env python3
r"""Prove the telemetry collector is ALIVE, not merely configured.

WHY THIS EXISTS
===============
`framework/validate.py` asserts the plugin is declared and its path exists. Both were true
for five weeks while the plugin never loaded: `opencode.json` registered

    "file://framework/opencode/plugin/telemetry.ts"

and the host parsed `framework` as the URL *host*, resolving it to `\\framework\...`. The
watcher failed with EUNKNOWN, the plugin was never loaded, and `records.jsonl` stopped
growing on 2026-10-12. Existence of a file is not liveness; a recent heartbeat is.

WHAT COUNTS AS ALIVE
====================
The collector appends a record on `session.created`, every 60s, and on idle/deletion
[VERIFIED: framework/opencode/plugin/telemetry.ts:125-132,186,512]. Records carry no
top-level emit timestamp, so the honest liveness signal is the file's modification time: a
live collector rewrites it continuously. A record's `started_at` is the SESSION start and
would read as fresh for a session that has been dead for days -- it is not used.

EXIT CODES
==========
  0  PASS           heartbeat within --max-age-s
  1  FAIL           declared but never wrote, or the last write is older than the budget
  2  BLOCKED        the records file exists but cannot be read/parsed
  4  NOT_APPLICABLE no telemetry collector declared, so there is nothing to observe

Nothing here can return 0 by accident: an absent declaration is 4, and an absent file under a
declaration is 1. That is the difference between "not configured" and "configured and dead".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DISCOVERY = (
    ".opencode/plugins/telemetry.ts", ".opencode/plugins/telemetry.js",
    ".opencode/plugin/telemetry.ts", ".opencode/plugin/telemetry.js",
)


def declared(root: Path) -> bool:
    """Is a telemetry collector wired at all: in the config array or a discovery dir?"""
    cfg_path = root / "opencode.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    if any("telemetry" in str(x) for x in (cfg.get("plugin") or [])):
        return True
    return any((root / p).exists() for p in DISCOVERY)


def last_record(path: Path) -> dict | None:
    """Parse the newest parseable record. Returns None when the file holds none."""
    newest = None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            newest = row
    return newest


def evaluate(root: Path, records: Path, max_age_s: int, now: float | None = None) -> tuple[int, str]:
    """The ladder. Pure enough to drive from a test with a fixed clock."""
    now = time.time() if now is None else now
    if not declared(root):
        return 4, "NOT_APPLICABLE: no telemetry collector declared"
    if not records.exists():
        return 1, ("FAIL: collector declared but %s does not exist -- it has never written, "
                   "so it is configured and dead" % records)
    try:
        age = now - records.stat().st_mtime
    except OSError as exc:
        return 2, "BLOCKED: cannot stat %s (%s)" % (records, exc)
    row = last_record(records)
    if row is None:
        return 2, "BLOCKED: %s holds no parseable record" % records
    if age > max_age_s:
        return 1, ("FAIL: newest record is %.0fs old (budget %ds) -- a collector that loaded "
                   "would have appended a heartbeat" % (age, max_age_s))
    kind = row.get("kind") or "?"
    session = row.get("session_id") or "?"
    return 0, "PASS: heartbeat %s for %s, %.0fs old (budget %ds)" % (kind, session, age, max_age_s)


# ─── self-test ───────────────────────────────────────────────────────────────────────────

def _fixture(tmp: Path, *, wire: bool, records: str | None, age_s: float = 0.0) -> Path:
    root = tmp / "repo"
    (root / ".planning" / "telemetry").mkdir(parents=True)
    cfg = {"plugin": ["telemetry"] if wire else []}
    (root / "opencode.json").write_text(json.dumps(cfg), encoding="utf-8")
    path = root / ".planning" / "telemetry" / "records.jsonl"
    if records is not None:
        path.write_text(records, encoding="utf-8")
        stamp = time.time() - age_s
        os.utime(path, (stamp, stamp))
    return root


def self_test() -> int:
    cases: list[tuple[str, dict, int]] = [
        ("fresh heartbeat -> PASS", dict(wire=True, records='{"kind":"heartbeat"}\n', age_s=5), 0),
        ("stale heartbeat -> FAIL", dict(wire=True, records='{"kind":"heartbeat"}\n', age_s=5000), 1),
        ("declared but never wrote -> FAIL", dict(wire=True, records=None), 1),
        ("nothing declared -> NOT_APPLICABLE", dict(wire=False, records='{"kind":"heartbeat"}\n'), 4),
        ("unparseable records -> BLOCKED", dict(wire=True, records="not json\n"), 2),
        ("wire via discovery dir -> evaluated", dict(wire=False, records=None), 4),
    ]
    failures = 0
    for label, kwargs, want in cases:
        with tempfile.TemporaryDirectory() as td:
            root = _fixture(Path(td), **kwargs)
            got, detail = evaluate(
                root, root / ".planning" / "telemetry" / "records.jsonl", 900
            )
        ok = got == want
        failures += 0 if ok else 1
        print("  %s  %-42s got=%d want=%d" % ("PASS" if ok else "FAIL", label, got, want))

    # The discovery route must count as declared, or a bridged install reads NOT_APPLICABLE.
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(Path(td), wire=False, records='{"kind":"heartbeat"}\n', age_s=1)
        bridge = root / ".opencode" / "plugins" / "telemetry.js"
        bridge.parent.mkdir(parents=True)
        bridge.write_text("module.exports = {}\n", encoding="utf-8")
        got, detail = evaluate(root, root / ".planning" / "telemetry" / "records.jsonl", 900)
        ok = got == 0
        failures += 0 if ok else 1
        print("  %s  %-42s got=%d want=0" % ("PASS" if ok else "FAIL",
                                             "bridge counts as declared", got))

    print("\nselftest: %d/%d pass" % (len(cases) + 1 - failures, len(cases) + 1))
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--records", default=None)
    ap.add_argument("--max-age-s", type=int, default=900)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    root = Path(args.root).resolve()
    records = Path(args.records) if args.records else root / ".planning" / "telemetry" / "records.jsonl"
    code, detail = evaluate(root, records, args.max_age_s)
    print(detail)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
