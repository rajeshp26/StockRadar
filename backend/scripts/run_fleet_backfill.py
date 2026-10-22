"""Fleet price-history backfill — resumable, logged, and honest about outcomes.

WHY A WRAPPER
-------------
2,925 of 3,122 companies hold zero price_history rows because two writer defects
(the YFinance short-circuit and the tz-aware comparison) starved the table. Both
are fixed; the fleet now needs populating. That is hours of network work, so it
must survive interruption, be resumable, and leave a durable record.

WHAT IT DOES
------------
Repeatedly invokes the existing `backfill_benchmark_prices.py --all-missing`
(which selects companies with zero history) in bounded batches, so progress is
committed incrementally and a crash loses at most one batch. Each batch appends a
JSON line to the progress log, so the run is auditable and restartable.

It does NOT reimplement any write logic: selection and writing stay in the one
reviewed script, this only drives it and records what happened.

Run:
  python scripts/run_fleet_backfill.py --batch 40 --max-batches 200
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKFILL = HERE / "backfill_benchmark_prices.py"
LOG = HERE.parent / "fleet_backfill_progress.jsonl"


def _run_batch(batch_size: int) -> tuple[int, str]:
    """Run one batch; return (returncode, combined output)."""
    cmd = [
        sys.executable, str(BACKFILL),
        "--all-missing", "--limit", str(batch_size), "--force-bootstrap",
        "--concurrency", "4",
    ]
    proc = subprocess.run(
        cmd, cwd=str(HERE.parent), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _parse_summary(out: str) -> dict[str, int]:
    """Pull the ok/no-data/errors counts out of the batch summary line."""
    for line in out.splitlines():
        if "SUMMARY:" in line:
            tail = line.split("SUMMARY:", 1)[1]
            nums: dict[str, int] = {}
            for part in tail.split("|")[0].split(","):
                part = part.strip()
                if not part:
                    continue
                n, _, label = part.partition(" ")
                try:
                    nums[label.strip()] = int(n)
                except ValueError:
                    continue
            return nums
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=40,
                    help="Companies per batch (default 40)")
    ap.add_argument("--max-batches", type=int, default=500,
                    help="Stop after this many batches (safety cap)")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="Seconds between batches (be polite to providers)")
    args = ap.parse_args()

    total_ok = total_none = total_err = 0
    batches = 0
    started = time.time()

    for i in range(args.max_batches):
        # Stop when a batch selects nothing -- the zero-history set is exhausted.
        rc, out = _run_batch(args.batch)
        counts = _parse_summary(out)
        selected = counts.get("ok", 0) + counts.get("no-data", 0)

        batch_id = i + 1
        rec = {
            "batch": batch_id,
            "at": datetime.utcnow().isoformat(),
            "returncode": rc,
            "counts": counts,
            "elapsed_s": round(time.time() - started, 1),
        }
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

        total_ok += counts.get("ok", 0)
        total_none += counts.get("no-data", 0)
        total_err += counts.get("errors", 0)
        batches += 1

        print(f"[batch {batch_id}] rc={rc} counts={counts} "
              f"running_total ok={total_ok} none={total_none} err={total_err}",
              flush=True)

        if selected == 0 and counts.get("errors", 0) == 0:
            print("No companies selected -- zero-history set exhausted. Stopping.",
                  flush=True)
            break
        if rc != 0 and counts.get("errors", 0) == 0 and selected == 0:
            # A non-zero rc with nothing selected and no recorded errors means the
            # script could not run (bad path, import error). Stop rather than spin.
            print("Batch failed without a summary; stopping. Last output tail:",
                  flush=True)
            print("\n".join(out.splitlines()[-15:]), flush=True)
            break
        time.sleep(args.sleep)

    print("=" * 60, flush=True)
    print(f"FLEET BACKFILL DONE: batches={batches} ok={total_ok} "
          f"no-data={total_none} errors={total_err} "
          f"elapsed={round(time.time() - started, 1)}s", flush=True)
    print(f"progress log: {LOG}", flush=True)
    return 0 if total_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
