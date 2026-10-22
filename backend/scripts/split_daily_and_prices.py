# split_daily_and_prices.py
# READ-ONLY. (1) Splits daily_* snapshot rows into gap vs non-gap and measures
# divergence for each, to prove the gap path shares the replay-engine bug.
# (2) Audits SPY/QQQ price_history coverage and staleness (targeted query).
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


flows = page("portfolio_transactions",
             "account_id, transaction_date, net_cash_amount, activity_type")
flows = [f for f in flows
         if (f.get("activity_type") or "") in ("MoneyMovement", "BonusPayment")]
tmp: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
for f in flows:
    tmp[f["account_id"]].append(
        (d(f["transaction_date"]), Decimal(str(f.get("net_cash_amount") or 0))))
LED_DATES, LED_CUM = {}, {}
for aid, rows in tmp.items():
    rows.sort()
    LED_DATES[aid] = [r[0] for r in rows]
    cum, run = [], Decimal("0")
    for _dt, amt in rows:
        run += amt
        cum.append(run)
    LED_CUM[aid] = cum


def ledger_as_of(aid: int, when: date) -> Decimal:
    dates = LED_DATES.get(aid)
    if not dates:
        return Decimal("0")
    i = bisect_right(dates, when)
    return LED_CUM[aid][i - 1] if i else Decimal("0")


snaps = page("portfolio_snapshots",
             "account_id, snapshot_date, net_deposits, job_id")

buckets = Counter()
div = Counter()
for s in snaps:
    jid = s.get("job_id") or "NULL"
    if jid.startswith("daily_gap_"):
        fam = "daily_gap_*"
    elif jid.startswith("daily_"):
        fam = "daily_<today>_*"
    elif jid.startswith("rebuild_"):
        fam = "rebuild_*"
    else:
        fam = jid.split("_")[0] + "_*" if "_" in jid else jid
    buckets[fam] += 1
    nd = Decimal(str(s["net_deposits"] or 0))
    if nd != ledger_as_of(s["account_id"], d(s["snapshot_date"])):
        div[fam] += 1

print("=== Divergence by writer sub-path ===")
print(f"{'writer':<20} {'rows':>7} {'divergent':>10} {'rate':>7}")
for fam in sorted(buckets, key=lambda f: -buckets[f]):
    t, b = buckets[fam], div[fam]
    print(f"{fam:<20} {t:>7} {b:>10} {b/t*100:>6.1f}%")

# ---- price history: SPY/QQQ only ----
print("\n=== SPY/QQQ price_history coverage ===")
cos = page("companies", "company_id, ticker_symbol")
watch = {c["company_id"]: c["ticker_symbol"] for c in cos
         if c.get("ticker_symbol") in ("SPY", "QQQ")}
TODAY = date(2026, 10, 18)
for cid, tk in sorted(watch.items(), key=lambda x: x[1]):
    rows: list[dict] = []
    start = 0
    while True:
        part = (supabase.table("price_history").select("price_date")
                .eq("company_id", cid).order("price_date")
                .range(start, start + 999).execute().data or [])
        rows.extend(part)
        if len(part) < 1000:
            break
        start += 1000
    ds = [d(r["price_date"]) for r in rows]
    gaps = [(ds[i - 1], ds[i]) for i in range(1, len(ds))
            if (ds[i] - ds[i - 1]).days > 4]
    print(f"{tk}: rows={len(ds)} first={ds[0]} last={ds[-1]} "
          f"stale_days={(TODAY-ds[-1]).days} gaps>4d={len(gaps)}")
    for a, b in gaps[-5:]:
        print(f"    gap: {a} -> {b} ({(b-a).days}d)")
