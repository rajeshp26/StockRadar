# call_real_get_net_deposits.py
# READ-ONLY. Calls the app's OWN portfolio_repo.get_net_deposits(aid, date)
# and compares it to (a) an independent SQL-side sum of the same filter and
# (b) the value actually stored in portfolio_snapshots. Decides whether the
# divergence originates in the repository function, the row builder, or the
# stored legacy data.
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402
from infrastructure.repositories.portfolio_repository import (  # noqa: E402
    PortfolioRepository,
)

TODAY = date(2026, 10, 18)
repo = PortfolioRepository(supabase)

print(f"{'acct':>5} {'repo.get_net_deposits':>22} {'stored snapshot':>16} "
      f"{'delta':>12}")
print("=" * 60)
stored_tot = Decimal("0")
repo_tot = Decimal("0")
for aid in (7, 8, 9):
    fn_val = repo.get_net_deposits(aid, TODAY)

    # independent raw sum straight from Supabase (same filter, no Decimal path)
    rows = (supabase.table("portfolio_transactions")
            .select("net_cash_amount")
            .eq("account_id", aid)
            .in_("activity_type", ["MoneyMovement", "BonusPayment"])
            .lte("transaction_date", TODAY.isoformat())
            .execute().data or [])
    raw = sum(Decimal(str(r.get("net_cash_amount") or 0)) for r in rows)

    snap = (supabase.table("portfolio_snapshots")
            .select("net_deposits, snapshot_date")
            .eq("account_id", aid)
            .order("snapshot_date", desc=True).limit(1).execute().data)
    snap_val = Decimal(str(snap[0]["net_deposits"])) if snap else Decimal("0")

    flag = "" if fn_val == raw else "  <-- FUNCTION != RAW SUM"
    print(f"{aid:>5} {float(fn_val):>22,.2f} {float(snap_val):>16,.2f} "
          f"{float(snap_val-fn_val):>+12,.2f}{flag}")
    print(f"      (raw Supabase sum = {float(raw):,.2f})")
    repo_tot += fn_val
    stored_tot += snap_val

print("=" * 60)
print(f"{'SUM':>5} {float(repo_tot):>22,.2f} {float(stored_tot):>16,.2f} "
      f"{float(stored_tot-repo_tot):>+12,.2f}")
print(f"\nrepo total vs ledger target 68,760.09 -> delta "
      f"{float(repo_tot) - 68760.09:+,.2f}")
