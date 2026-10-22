# etf_pre_seed_appends.py
# READ-ONLY. Were ETF prices appended by the scheduler BEFORE the 2026-10-01
# bulk seed? If yes (through ~09-30), the old process was writing ETFs until
# it was replaced at the 10-01 redeploy -- dating when the ETF early-return
# regression first started executing.
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

ph = supabase.table("price_history")

cos = []
start = 0
while True:
    part = (supabase.table("companies")
            .select("company_id, ticker_symbol, security_type")
            .range(start, start + 999).execute().data or [])
    cos.extend(part)
    if len(part) < 1000:
        break
    start += 1000
etf_ids = [c["company_id"] for c in cos
           if (c.get("security_type") or "stock") == "etf"]
tick = {c["company_id"]: c.get("ticker_symbol") for c in cos}

# ETF rows created BEFORE the 2026-10-01 seed
n_before = (ph.select("price_date", count="exact")
            .lt("created_at", "2026-10-01T00:00:00")
            .in_("company_id", etf_ids).execute()).count
print(f"ETF rows created BEFORE 2026-10-01: {n_before}")

# most recent ETF rows by created_at (pre-seed) -- were they daily appends?
recent = (ph.select("company_id, price_date, created_at")
          .lt("created_at", "2026-10-01T00:00:00")
          .in_("company_id", etf_ids)
          .order("created_at", desc=True).limit(15).execute().data or [])
print("\n15 most recent pre-seed ETF writes:")
for r in recent:
    print(f"  {tick.get(r['company_id'], r['company_id'])}: "
          f"price_date={str(r['price_date'])[:10]} "
          f"created_at={str(r['created_at'])[:19]}")

# distinct ETF created_at dates in September (pre-seed) -- daily cadence?
sep = (ph.select("created_at")
       .lt("created_at", "2026-10-01T00:00:00")
       .gte("created_at", "2026-09-01T00:00:00")
       .in_("company_id", etf_ids)
       .limit(5000).execute().data or [])
from collections import Counter  # noqa: E402
days = Counter(str(r["created_at"])[:10] for r in sep)
print(f"\npre-seed ETF rows created in Sep 2026: {len(sep)}")
print("  by creation day:", dict(sorted(days.items())))
