"""Remove validate.py suite fixtures that leaked into the LIVE claim ledger.

Why this exists
---------------
The live claim ledger is the store of record, and its contract is append-only: a
claim is superseded by a later record, never deleted. The one thing that is not a
claim is a record a *harness* wrote by mistake when it thought it was writing to a
disposable store. Those are not project conclusions and cannot be superseded into
anything truthful -- each one names a validation task (V22-*/V24-*/V26-*/V28-*) that
does not exist, and the EVIDENCE_STALE_REUSE / EVIDENCE_ARTIFACT_MISSING checks then
fail forever, which makes `bash framework/gates/g14_integrity.sh` refuse completion.

What happened
-------------
The four suites in framework/validate.py that exercise the ledger (`_suite_22`,
`_suite_24`, `_suite_26`, `_suite_28`) each copy `framework/` into a temp dir and
create a `.planning/` beside it, then drive the ledger with
`cd '<temp>' && python3 framework/claims/ledger.py append ...`. That isolation is
CWD-relative: `locate.find_config()` walks up from the working directory, so whether
the append lands in the copy or in the live repo depends on where the temp dir ends
up and on the ambient environment. On 2026-10-12 three runs deposited 24 identical
fixture records into the live ledger instead of the copy.

Matching rule (deliberately narrow)
----------------------------------
A line is removed only when BOTH its claim_id and its task_id are on the fixture
lists below. The lists are constants, not inference: nothing is guessed about what
looks like a fixture, and any store that cannot be parsed is refused rather than
rewritten. A copy of the store is written before it is touched.

Usage:
  python framework/tools/prune_suite_fixtures.py            # dry run (default)
  python framework/tools/prune_suite_fixtures.py --apply    # back up, then rewrite
  python framework/tools/prune_suite_fixtures.py --ledger <path> --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO_ROOT / ".planning" / "claims" / "ledger.jsonl"

# Claim ids the fixture sets use, and the task ids they are recorded under. A record
# must match both lists to be removed -- the intersection is what makes this auditable
# line by line instead of a heuristic over store contents.
FIXTURE_CLAIM_IDS = (
    "CLM-900", "CLM-912", "CLM-922", "CLM-926", "CLM-927", "CLM-928",
    "CLM-960", "CLM-961", "CLM-962", "CLM-999",
)
FIXTURE_TASK_IDS = (
    "V22-001", "V22-999",
    "V24-003",
    "V26-003", "V26-007", "V26-008", "V26-009",
    "V28-001", "V28-002", "V28-003",
)


def is_fixture(rec: dict) -> bool:
    return (str(rec.get("claim_id")) in FIXTURE_CLAIM_IDS
            and str(rec.get("task_id")) in FIXTURE_TASK_IDS)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="remove validate.py suite fixture records from a claim ledger")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER),
                    help="ledger to prune (default: the live one)")
    ap.add_argument("--apply", action="store_true",
                    help="rewrite the ledger (default is a dry run)")
    a = ap.parse_args()

    path = Path(a.ledger)
    if not path.exists():
        print(f"LEDGER_MISSING  {path}", file=sys.stderr)
        return 2

    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    dropped: list[tuple[int, dict]] = []
    for n, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rec = json.loads(stripped)
        except json.JSONDecodeError as e:
            # Refuse rather than drop bytes: a store this tool cannot read is not a
            # store this tool is allowed to rewrite.
            print(f"NOT_JSON  line {n}: {e}", file=sys.stderr)
            return 2
        if is_fixture(rec):
            dropped.append((n, rec))
        else:
            keep.append(line)

    print(f"{path}")
    print(f"  lines                       : {len(lines)}")
    print(f"  fixture records to remove   : {len(dropped)}")
    print(f"  records kept                : {len(keep)}")
    for n, rec in dropped:
        print(f"    line {n:<4} {rec.get('claim_id')}  {rec.get('task_id')}  "
              f"{rec.get('statement')!r}")

    if not a.apply:
        print("dry run -- pass --apply to write the pruned ledger")
        return 0
    if not dropped:
        print("nothing to remove")
        return 0

    backup = path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    path.write_text("\n".join(str(x) for x in keep) + "\n", encoding="utf-8", newline="\n")
    print(f"  backup                      : {backup}")
    print(f"  rewrote                     : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
