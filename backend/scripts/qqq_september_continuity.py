# qqq_september_continuity.py
# READ-ONLY. QQQ (etf, id 379) rows across 2026-09-01..2026-10-18, plus the
# distinct-company counts at key dates. Determines whether ETF writing was
# continuous through 2026-09-30 (deploy/backfill explanation) or stopped at
# the 2026-09-04 regression commit.
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

QQQ, SPY = 379, 61

for cid, tk in ((QQQ, "QQQ"), (SPY, "SPY")):
    rows = (supabase.table("price_history")
            .select("price_date, close_price")
            .eq("company_id", cid)
            .gte("price_date", "2026-09-01")
            .order("price_date").execute().data or [])
    print(f"\n=== {tk} rows since 2026-09-01: {len(rows)} ===")
    dates = [str(r["price_date"])[:10] for r in rows]
    # weekday coverage in September
    import datetime as _dt
    sep_days = [d for d in dates if d.startswith("2026-09")]
    print(f"  September rows: {len(sep_days)}")
    print(f"  first={dates[0] if dates else '-'}  last={dates[-1] if dates else '-'}")
    print(f"  Sep dates: {sep_days}")
    # weekdays in Sept with NO row
    missing = []
    d0 = _dt.date(2026, 9, 1)
    have = set(dates)
    while d0 <= _dt.date(2026, 9, 30):
        if d0.weekday() < 5 and d0.isoformat() not in have:
            missing.append(d0.isoformat())
        d0 += _dt.timedelta(days=1)
    print(f"  Sept weekdays MISSING: {missing}")

# distinct companies at exact dates (etf vs stock)
print("\n=== distinct companies with a row on key dates ===")
cos = (supabase.table("companies")
       .select("company_id, security_type").execute().data or [])
st = {c["company_id"]: (c.get("security_type") or "stock") for c in cos}
for dt in ("2026-09-30", "2026-10-01", "2026-10-16"):
    r = (supabase.table("price_history").select("company_id")
         .eq("price_date", dt).limit(5000).execute().data or [])
    ids = {x["company_id"] for x in r}
    n_etf = sum(1 for i in ids if st.get(i) == "etf")
    n_stk = sum(1 for i in ids if st.get(i) == "stock")
    print(f"  {dt}: {len(ids)} companies (etf {n_etf}, stock {n_stk})")
