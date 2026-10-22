# prove_gap_equals_withdrawals.py
# READ-ONLY. Two proofs:
#  A) The stored net_deposits gap for each account equals EXACTLY the sum of
#     negative MoneyMovement flows the replay engine's `net_cash > 0` guard
#     skips. If gap == skipped_negatives for every account, the mechanism is
#     proven arithmetically, not just by code reading.
#  B) Whether SPY/QQQ are held (and thus in the price-refresh universe).
from __future__ import annotations

import sys
from collections import defaultdict
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


print("=== A) gap vs sum of skipped negative flows ===")
flows = page("portfolio_transactions",
             "account_id, net_cash_amount, activity_type")
pos: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
neg: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
net: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
for f in flows:
    if (f.get("activity_type") or "") not in ("MoneyMovement", "BonusPayment"):
        continue
    amt = Decimal(str(f.get("net_cash_amount") or 0))
    aid = f["account_id"]
    net[aid] += amt
    if amt > 0:
        pos[aid] += amt
    else:
        neg[aid] += amt

snaps = page("portfolio_snapshots",
             "account_id, snapshot_date, net_deposits, job_id")
latest: dict[int, Decimal] = {}
for s in snaps:
    aid = s["account_id"]
    sd = str(s["snapshot_date"])[:10]
    if aid not in latest or sd > latest.get("_d_" + str(aid), ""):  # placeholder
        pass
# simpler: track by date string per account
last_date: dict[int, str] = {}
for s in snaps:
    aid = s["account_id"]
    sd = str(s["snapshot_date"])[:10]
    if aid not in last_date or sd > last_date[aid]:
        last_date[aid] = sd
        latest[aid] = Decimal(str(s["net_deposits"] or 0))

print(f"{'acct':>5} {'stored':>12} {'net ledger':>12} {'gap':>11} "
      f"{'sum(neg)':>11} {'MATCH':>7}")
print("=" * 62)
for aid in sorted(set(net) | set(latest)):
    stored = latest.get(aid, Decimal("0"))
    n = net.get(aid, Decimal("0"))
    gap = stored - n
    skipped = abs(neg.get(aid, Decimal("0")))
    match = "YES" if gap == skipped else ("n/a" if gap == 0 else "NO")
    print(f"{aid:>5} {float(stored):>12,.2f} {float(n):>12,.2f} "
          f"{float(gap):>+11,.2f} {float(skipped):>11,.2f} {match:>7}")

print("\n=== B) Is SPY/QQQ held? (price-refresh universe) ===")
cos = page("companies", "company_id, ticker_symbol")
watch = {c["company_id"]: c["ticker_symbol"] for c in cos
         if c.get("ticker_symbol") in ("SPY", "QQQ")}
print(f"watch: {watch}")
holdings = page("portfolio_holdings", "account_id, company_id, quantity")
held_ids = {h["company_id"] for h in holdings
            if Decimal(str(h.get("quantity") or 0)) > 0}
print(f"distinct held company_ids: {len(held_ids)}")
for cid, tk in watch.items():
    print(f"  {tk} (id {cid}): held={cid in held_ids}")

# held tickers sample + price freshness of a couple of held names for contrast
tick = {c["company_id"]: c["ticker_symbol"] for c in cos}
held_ticks = sorted(tick.get(c, "?") for c in held_ids)
print(f"held tickers (first 30): {held_ticks[:30]}")
