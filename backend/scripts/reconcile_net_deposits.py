# reconcile_net_deposits.py
# READ-ONLY. Reconciles net_deposits per account between:
#   (a) the transaction ledger (MoneyMovement + BonusPayment, what the live
#       /portfolio/performance endpoint computes), and
#   (b) the stored portfolio_snapshots.net_deposits column.
# Also flags implausible total_value jumps in the stored snapshots.
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402


def page(table: str, cols: str, batch: int = 1000) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        part = (supabase.table(table).select(cols)
                .range(start, start + batch - 1).execute().data or [])
        rows.extend(part)
        if len(part) < batch:
            break
        start += batch
    return rows


# (a) ledger
led = page("portfolio_transactions",
           "account_id, transaction_date, net_cash_amount, currency, activity_type")
led_by_acct: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
for t in led:
    if (t.get("activity_type") or "") in ("MoneyMovement", "BonusPayment"):
        led_by_acct[t["account_id"]] += Decimal(str(t.get("net_cash_amount") or 0))

# (b) snapshots (latest row per account)
snaps = page("portfolio_snapshots",
             "account_id, snapshot_date, net_deposits, total_value")
latest: dict[int, tuple[str, Decimal, Decimal]] = {}
for s in snaps:
    d = str(s["snapshot_date"])[:10]
    aid = s["account_id"]
    if aid not in latest or d > latest[aid][0]:
        latest[aid] = (d, Decimal(str(s["net_deposits"] or 0)),
                       Decimal(str(s["total_value"] or 0)))

print(f"{'acct':>5} {'ledger net_dep':>16} {'snapshot net_dep':>18} {'delta':>12}")
print("=" * 55)
tot_led = Decimal("0")
tot_snap = Decimal("0")
for aid in sorted(set(led_by_acct) | set(latest)):
    l = led_by_acct.get(aid, Decimal("0"))
    s = latest.get(aid, (None, Decimal("0"), Decimal("0")))[1]
    tot_led += l
    tot_snap += s
    print(f"{aid:>5} {float(l):>16,.2f} {float(s):>18,.2f} {float(s-l):>+12,.2f}")
print("=" * 55)
print(f"{'TOT':>5} {float(tot_led):>16,.2f} {float(tot_snap):>18,.2f} "
      f"{float(tot_snap-tot_led):>+12,.2f}")

# total_value implausibility scan on stored snapshots (aggregate per date)
val_by_date: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
nd_by_date: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
for s in snaps:
    d = str(s["snapshot_date"])[:10]
    val_by_date[d] += Decimal(str(s["total_value"] or 0))
    nd_by_date[d] += Decimal(str(s["net_deposits"] or 0))

print("\nStored snapshots: total_value vs net_deposits (aggregate per date)")
print(f"{'date':<12} {'total_value':>14} {'net_deposits':>14} {'gain%':>9}")
print("=" * 54)
prev = None
for d in sorted(val_by_date):
    tv, nd = val_by_date[d], nd_by_date[d]
    gain = (float(tv - nd) / float(nd) * 100) if nd else 0.0
    # print only quarter ends + any date with |gain| > 100%
    if d.endswith(("03-31", "06-30", "09-30", "12-31")) or abs(gain) > 100:
        print(f"{d:<12} {float(tv):>14,.2f} {float(nd):>14,.2f} {gain:>+8.1f}%")
