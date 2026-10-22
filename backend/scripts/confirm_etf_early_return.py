# confirm_etf_early_return.py
# READ-ONLY. Confirms the ETF-vs-stock split explains the price freeze:
#  1. security_type for the stale cluster vs the fresh cluster.
#  2. Cross-tab: every company, security_type vs has-price-after-2026-09-30.
# If ALL non-stock securities are frozen and ALL stocks are fresh, the
# `if not is_stock: return` early-exit at market_data_scheduler.py:554 is proven.
from __future__ import annotations

import sys
from collections import Counter, defaultdict
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


cos = page("companies", "company_id, ticker_symbol, security_type")
print(f"companies: {len(cos)}")
st_counts = Counter((c.get("security_type") or "NULL") for c in cos)
print("security_type distribution:", dict(st_counts))

# companies with any price after 2026-09-30
after_rows = (supabase.table("price_history").select("company_id")
              .gt("price_date", "2026-09-30").limit(5000).execute().data or [])
fresh_ids = {r["company_id"] for r in after_rows}
print(f"companies with price > 2026-09-30: {len(fresh_ids)}")

# Cross-tab security_type x fresh/frozen
xtab: dict[str, Counter] = defaultdict(Counter)
tick = {c["company_id"]: (c.get("ticker_symbol") or "?") for c in cos}
st_of = {c["company_id"]: (c.get("security_type") or "NULL") for c in cos}
for c in cos:
    cid = c["company_id"]
    st = c.get("security_type") or "NULL"
    fresh = "FRESH" if cid in fresh_ids else "FROZEN"
    xtab[st][fresh] += 1

print("\n=== security_type x price freshness (after 2026-09-30) ===")
print(f"{'security_type':<14} {'FRESH':>7} {'FROZEN':>8} {'fresh%':>8}")
for st, cnt in sorted(xtab.items(), key=lambda x: -sum(x[1].values())):
    tot = cnt["FRESH"] + cnt["FROZEN"]
    pct = cnt["FRESH"] / tot * 100 if tot else 0
    print(f"{st:<14} {cnt['FRESH']:>7} {cnt['FROZEN']:>8} {pct:>7.1f}%")

# Sample: non-stock companies (should all be frozen)
nonstock = [c for c in cos if (c.get("security_type") or "stock") != "stock"]
ns_fresh = [c for c in nonstock if c["company_id"] in fresh_ids]
print(f"\nnon-stock companies: {len(nonstock)}, of which FRESH: {len(ns_fresh)}")
if ns_fresh:
    print(f"  fresh non-stocks: {sorted(c['ticker_symbol'] for c in ns_fresh)}")

# The stale cluster specifically
print("\n=== stale cluster security_type ===")
for tk in ("SPY", "QQQ", "NVDA", "NVDY", "CONY", "QYLD", "TSLY", "QDTE",
           "SVOL", "WEED", "CRF", "DGS", "AAPL", "MSFT", "TSLA", "SHOP"):
    m = [c for c in cos if c.get("ticker_symbol") == tk]
    if not m:
        print(f"  {tk:<6} (not in companies)")
        continue
    c = m[0]
    fresh = "FRESH" if c["company_id"] in fresh_ids else "FROZEN"
    print(f"  {tk:<6} security_type={c.get('security_type')!r:<12} {fresh}")
