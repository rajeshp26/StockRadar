# who_wrote_corrupt.py
# READ-ONLY, SMALL. Ties divergent portfolio_snapshots rows to the job_id
# writer that produced them. Uses bisect over pre-sorted ledger sums (fast).
from __future__ import annotations

import sys
from bisect import bisect_right
from collections import Counter, defaultdict
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


def d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


# ---- ledger: pre-sorted cumulative sums per account for O(log n) lookup ----
flows = page("portfolio_transactions",
             "account_id, transaction_date, net_cash_amount, activity_type")
flows = [f for f in flows
         if (f.get("activity_type") or "") in ("MoneyMovement", "BonusPayment")]
tmp: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
for f in flows:
    tmp[f["account_id"]].append(
        (d(f["transaction_date"]), Decimal(str(f.get("net_cash_amount") or 0))))

LED_DATES: dict[int, list[date]] = {}
LED_CUM: dict[int, list[Decimal]] = {}
for aid, rows in tmp.items():
    rows.sort()
    dates = [r[0] for r in rows]
    cum: list[Decimal] = []
    run = Decimal("0")
    for _dt, amt in rows:
        run += amt
        cum.append(run)
    LED_DATES[aid] = dates
    LED_CUM[aid] = cum


def ledger_as_of(aid: int, when: date) -> Decimal:
    dates = LED_DATES.get(aid)
    if not dates:
        return Decimal("0")
    i = bisect_right(dates, when)
    return LED_CUM[aid][i - 1] if i else Decimal("0")


snaps = page("portfolio_snapshots",
             "account_id, snapshot_date, net_deposits, total_value, job_id")

print("=== Account 7 rows around first divergence (2021-06-09) ===")
a7 = sorted([s for s in snaps if s["account_id"] == 7],
            key=lambda s: d(s["snapshot_date"]))
print(f"{'date':<12} {'stored ND':>12} {'ledger ND':>12} {'gap':>10}  job_id")
for s in a7:
    sd = d(s["snapshot_date"])
    if date(2021, 6, 1) <= sd <= date(2021, 6, 20):
        nd = Decimal(str(s["net_deposits"] or 0))
        led = ledger_as_of(7, sd)
        print(f"{sd.isoformat():<12} {float(nd):>12,.2f} {float(led):>12,.2f} "
              f"{float(nd-led):>+10,.2f}  {s.get('job_id')}")

# Divergence rate by job_id family across ALL accounts.
div_by_job = Counter()
tot_by_job = Counter()
for s in snaps:
    aid = s["account_id"]
    sd = d(s["snapshot_date"])
    nd = Decimal(str(s["net_deposits"] or 0))
    fam = (s.get("job_id") or "NULL")
    fam_key = fam.split("_")[0] + "_*" if "_" in fam else fam
    tot_by_job[fam_key] += 1
    if nd != ledger_as_of(aid, sd):
        div_by_job[fam_key] += 1

print("\n=== Divergence rate by job_id family (all accounts) ===")
print(f"{'family':<14} {'rows':>8} {'divergent':>10} {'rate':>7}")
for fam in sorted(tot_by_job, key=lambda f: -tot_by_job[f]):
    t = tot_by_job[fam]
    b = div_by_job[fam]
    print(f"{fam:<14} {t:>8} {b:>10} {b/t*100:>6.1f}%")
