# qqq_insert_times.py
# READ-ONLY. Checks WHEN September ETF rows were actually ingested, using
# price_history's own audit columns. Distinguishes:
#  - created_at ~= price_date per row  -> daily scheduler writes through 09-30
#    (so the ETF early-return only started executing ~09-30/10-01)
#  - all Sept rows created_at clustered on one day -> bulk backfill wrote them.
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

# discover columns first
probe = (supabase.table("price_history").select("*")
         .eq("company_id", 379).limit(1).execute().data or [])
if not probe:
    print("no rows for company 379")
    raise SystemExit(0)
cols = sorted(probe[0].keys())
print("price_history columns:", cols)

audit_cols = [c for c in cols if c in (
    "created_at", "updated_at", "ingested_at", "fetched_at", "inserted_at",
    "last_updated", "source_updated_at", "loaded_at",
)]
print("audit columns present:", audit_cols)

rows = (supabase.table("price_history")
        .select("price_date, close_price, " + ", ".join(audit_cols))
        .eq("company_id", 379)
        .gte("price_date", "2026-09-01")
        .order("price_date")
        .execute().data or [])

print(f"\n=== QQQ (id 379) Sept rows: {len(rows)} ===")
for r in rows:
    extra = "  ".join(f"{c}={r.get(c)}" for c in audit_cols)
    print(f"  price_date={str(r['price_date'])[:10]}  {extra}")

# also compare a stock (AAPL 69) around the same window for contrast
stock = (supabase.table("price_history")
         .select("price_date, " + ", ".join(audit_cols))
         .eq("company_id", 69)
         .gte("price_date", "2026-09-25")
         .order("price_date")
         .execute().data or [])
print(f"\n=== AAPL (id 69) rows since 09-25: {len(stock)} ===")
for r in stock:
    extra = "  ".join(f"{c}={r.get(c)}" for c in audit_cols)
    print(f"  price_date={str(r['price_date'])[:10]}  {extra}")
