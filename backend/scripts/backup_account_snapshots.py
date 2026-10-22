"""READ-ONLY backup of portfolio_snapshots rows before a rebuild.

Serialises every column the rebuild rewrites, including holdings_json, to a JSON
file so the pre-rebuild state is restorable and auditable. Nothing is written to
the database; the only output is the JSON file.

Usage:
    python scripts/backup_account_snapshots.py --account-id 7 --out C:\\path\\backup_7.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_SCRIPTS = _BACKEND / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

import rebuild_account_snapshots as ras  # noqa: E402

COLUMNS = (
    "account_id, snapshot_date, total_value, holdings_market_value, cost_basis, "
    "cash_balance, net_deposits, holdings_json, job_id, computed_at, data_quality_flag"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account-id", type=int, required=True)
    ap.add_argument("--out", type=str, required=True)
    args = ap.parse_args()

    rows = ras.fetch_all_rows(
        "portfolio_snapshots", COLUMNS,
        eq_col="account_id", eq_val=args.account_id, order_col="snapshot_date",
    )
    payload = {"account_id": args.account_id, "row_count": len(rows), "rows": rows}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(f"backed up {len(rows)} rows for account {args.account_id} -> {out} "
          f"({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
