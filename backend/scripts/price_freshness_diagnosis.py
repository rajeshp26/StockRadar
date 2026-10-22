# price_freshness_diagnosis.py
# READ-ONLY. Answers: why does price_history stop at 2026-09-30 when the
# price_ingestion scheduler reports success every minute?
#  1. Globally freshest price rows (which companies, what date).
#  2. Freshness of SPY vs QQQ vs a sample of held tickers.
#  3. Whether 2026-09-30 is a hard boundary across the whole table.
#  4. dead_letter job signal (170 company_refresh dead letters).
from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

TODAY = date(2026, 10, 18)


def d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


# 1. Freshest rows overall
freshest = (supabase.table("price_history")
            .select("company_id, price_date")
            .order("price_date", desc=True).limit(30).execute().data or [])
cos = {c["company_id"]: c.get("ticker_symbol")
       for c in (supabase.table("companies")
                 .select("company_id, ticker_symbol").execute().data or [])}
print("=== 1. Freshest 30 price_history rows (global) ===")
dates = Counter(str(r["price_date"])[:10] for r in freshest)
for dt, n in sorted(dates.items(), reverse=True):
    print(f"   {dt}: {n} rows in top-30")
max_date = max(str(r["price_date"])[:10] for r in freshest) if freshest else "?"
print(f"   GLOBAL MAX price_date = {max_date}  (stale {(TODAY-d(max_date)).days}d)")

# 2. Freshness for SPY/QQQ + held sample
print("\n=== 2. Per-company freshness ===")
watch_ids = {61: "SPY", 379: "QQQ"}
# add a few held names for contrast
sample = [cid for cid, t in cos.items() if t in
          ("AAPL", "MSFT", "NVDA", "SHOP", "TSLA")][:5]
targets = dict(watch_ids)
for cid in sample:
    targets[cid] = cos.get(cid, str(cid))
for cid, tk in sorted(targets.items(), key=lambda x: x[1]):
    rows = (supabase.table("price_history").select("price_date")
            .eq("company_id", cid).order("price_date", desc=True)
            .limit(1).execute().data or [])
    if not rows:
        print(f"   {tk:<6} NO ROWS")
        continue
    last = d(rows[0]["price_date"])
    print(f"   {tk:<6} last={last}  stale={(TODAY-last).days}d")

# 3. Is 2026-09-30 a hard boundary? Count rows after it.
print("\n=== 3. Rows after 2026-09-30 (whole table) ===")
after = (supabase.table("price_history")
         .select("price_date", count="exact")
         .gt("price_date", "2026-09-30").execute())
print(f"   rows with price_date > 2026-09-30: {after.count}")
on_or_before = (supabase.table("price_history")
                .select("company_id", count="exact")
                .lte("price_date", "2026-09-30").execute())
print(f"   rows with price_date <= 2026-09-30: {on_or_before.count}")

# distinct companies that have ANY row after 2026-09-30
after_rows = (supabase.table("price_history")
              .select("company_id")
              .gt("price_date", "2026-09-30")
              .limit(1000).execute().data or [])
cos_after = {r["company_id"] for r in after_rows}
print(f"   distinct companies with rows after 2026-09-30: {len(cos_after)}")
if cos_after:
    print(f"      tickers: {sorted(cos.get(c, str(c)) for c in cos_after)[:40]}")

# 4. dead_letter signal
print("\n=== 4. company_refresh dead_letter jobs (recent 5) ===")
dl = (supabase.table("jobs")
      .select("id, job_type, status, created_at, error, last_error")
      .eq("status", "dead_letter")
      .order("created_at", desc=True).limit(5).execute().data or [])
for j in dl:
    err = j.get("error") or j.get("last_error")
    print(f"   {j.get('created_at')} [{j.get('job_type')}] {str(err)[:160]}")
