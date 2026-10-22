# price_history_seed_boundary.py
# READ-ONLY. Confirms when price_history rows were created, table-wide:
#  - min(created_at): is the whole table born on 2026-10-01 (bulk seed)?
#  - counts before / during / after the 2026-10-01 01:48-01:50 UTC window
#  - SPY Sept rows' created_at (same bulk batch as QQQ?)
# If history through 09-30 was seeded in one batch on 10-01 and only stock
# rows append daily afterwards, the SPY/QQQ freeze is explained by the
# (a) seed cutoff at 09-30 plus (b) the ETF early-return blocking appends.
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

# 1. Earliest created_at in the whole table
earliest = (ph.select("created_at")
            .order("created_at").limit(1).execute().data or [])
print("min(created_at):", earliest[0]["created_at"] if earliest else "?")

# 2. Row counts by creation period
c_before = (ph.select("created_at", count="exact")
            .lt("created_at", "2026-10-01T00:00:00").execute()).count
c_seed = (ph.select("created_at", count="exact")
          .gte("created_at", "2026-10-01T01:40:00")
          .lte("created_at", "2026-10-01T02:00:00").execute()).count
c_after = (ph.select("created_at", count="exact")
           .gte("created_at", "2026-10-02T00:00:00").execute()).count
c_total = (ph.select("created_at", count="exact").execute()).count

print(f"rows created BEFORE 2026-10-01        : {c_before}")
print(f"rows created in seed window 01:40-02:00: {c_seed}")
print(f"rows created on/after 2026-10-02      : {c_after}")
print(f"total rows                            : {c_total}")

# 3. What dates do rows created AFTER the seed cover? (append phase)
#    max price_date among rows created >= 10-02, etf vs stock via company map
cos_rows = []
start = 0
while True:
    part = (supabase.table("companies")
            .select("company_id, security_type")
            .range(start, start + 999).execute().data or [])
    cos_rows.extend(part)
    if len(part) < 1000:
        break
    start += 1000
st = {c["company_id"]: (c.get("security_type") or "stock") for c in cos_rows}

# rows created after the seed, latest 2000, grouped by security type
appended = (ph.select("company_id, price_date")
            .gte("created_at", "2026-10-02T00:00:00")
            .order("price_date", desc=True)
            .limit(2000).execute().data or [])
etf_max = max((str(r["price_date"])[:10] for r in appended
               if st.get(r["company_id"]) == "etf"), default="(none)")
stk_max = max((str(r["price_date"])[:10] for r in appended
               if st.get(r["company_id"]) == "stock"), default="(none)")
etf_n = sum(1 for r in appended if st.get(r["company_id"]) == "etf")
stk_n = sum(1 for r in appended if st.get(r["company_id"]) == "stock")
print(f"\nrows created after seed (latest 2000): "
      f"etf={etf_n} (max price_date {etf_max}), "
      f"stock={stk_n} (max price_date {stk_max})")

# 4. SPY Sept rows created_at (same batch as QQQ?)
spy = (ph.select("price_date, created_at")
       .eq("company_id", 61)
       .gte("price_date", "2026-09-01").lte("price_date", "2026-09-30")
       .order("price_date").execute().data or [])
created_set = {str(r["created_at"]) for r in spy}
print(f"\nSPY Sept rows: {len(spy)}  distinct created_at: {created_set}")

# 5. Any ETF rows created after the seed at all?
etf_ids = [c["company_id"] for c in cos_rows
           if (c.get("security_type") or "stock") == "etf"]
etf_after = (ph.select("company_id", count="exact")
             .gte("created_at", "2026-10-02T00:00:00")
             .in_("company_id", etf_ids).execute()).count
print(f"ETF rows created on/after 2026-10-02: {etf_after}")
