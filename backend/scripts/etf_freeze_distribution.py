# etf_freeze_distribution.py
# READ-ONLY, v2. Distinguishes uniform vs staggered ETF freeze.
# v1 bug: .limit(100000) was silently capped server-side to ~1000 rows, so
# ordered-desc only the newest (stock) rows came back. v2 pages with range().
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402


def page(table: str, cols: str, batch: int = 1000, gt: str | None = None) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        q = supabase.table(table).select(cols)
        if gt:
            q = q.gt("price_date", gt)
        part = q.range(start, start + batch - 1).execute().data or []
        rows.extend(part)
        if len(part) < batch:
            break
        start += batch
    return rows


cos = page("companies", "company_id, ticker_symbol, security_type")
st_of = {c["company_id"]: (c.get("security_type") or "stock") for c in cos}
tick = {c["company_id"]: (c.get("ticker_symbol") or "?") for c in cos}

# page price_history for rows after 2026-08-01 (covers the freeze window)
ph = page("price_history", "company_id, price_date", batch=1000, gt="2026-08-01")
print(f"price rows since 2026-08-01: {len(ph)}")

last: dict[int, str] = {}
for r in ph:
    cid = r["company_id"]
    dt = str(r["price_date"])[:10]
    if cid not in last or dt > last[cid]:
        last[cid] = dt

etf_last = {c: d for c, d in last.items() if st_of.get(c) == "etf"}
stk_last = {c: d for c, d in last.items() if st_of.get(c) == "stock"}
print(f"companies seen: {len(last)}  (etf {len(etf_last)}, stock {len(stk_last)})")

print("\n=== ETF last-price date distribution ===")
for dt, n in sorted(Counter(etf_last.values()).items(), reverse=True)[:25]:
    print(f"  {dt}: {n} ETFs")

print("\n=== STOCK last-price date distribution (top 8) ===")
for dt, n in sorted(Counter(stk_last.values()).items(), reverse=True)[:8]:
    print(f"  {dt}: {n} stocks")

after = [(tick.get(c, str(c)), d) for c, d in etf_last.items() if d > "2026-09-30"]
print(f"\nETFs with a price after 2026-09-30: {len(after)}")

window = sorted(set(d for d in etf_last.values()
                     if "2026-09-04" <= d <= "2026-09-30"))
print(f"distinct ETF last-dates in 09-04..09-30: {window}")
early = sorted((tick.get(c, str(c)), d) for c, d in etf_last.items()
               if d < "2026-09-30")
print(f"ETFs last-priced BEFORE 2026-09-30: {len(early)}")
print(f"  {early[:40]}")
