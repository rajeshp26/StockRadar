# ticker_freshness.py
# READ-ONLY. Per-ticker last price_date via direct eq queries (no truncation).
# Answers: is SPY/QQQ staleness specific to them, or do all held tickers stop
# at 2026-09-30? Also maps the 144 companies that DO have fresh rows.
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

TODAY = "2026-10-18"


def d(v) -> str:
    return str(v)[:10]


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


# full company map (paginated, no truncation)
cos = page("companies", "company_id, ticker_symbol, company_name")
tick = {c["company_id"]: (c.get("ticker_symbol") or "?") for c in cos}
rev: dict[str, int] = {}
for cid, t in tick.items():
    rev.setdefault(t, cid)

# held set
holdings = page("portfolio_holdings", "company_id, quantity")
from decimal import Decimal  # noqa: E402
held = {h["company_id"] for h in holdings
        if Decimal(str(h.get("quantity") or 0)) > 0}


def last_price(cid: int) -> str | None:
    rows = (supabase.table("price_history").select("price_date")
            .eq("company_id", cid).order("price_date", desc=True)
            .limit(1).execute().data or [])
    return d(rows[0]["price_date"]) if rows else None


print("=== Per-ticker freshness (direct queries) ===")
print(f"{'ticker':<8} {'held':<6} {'last_price':>12} {'stale_d':>8}")
for tk in ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "SHOP", "AMZN",
           "GOOGL", "META", "JPM", "COST", "VFV", "VEQT", "ZAG", "XUU"]:
    cid = rev.get(tk)
    if cid is None:
        print(f"{tk:<8} {'-':<6} {'(not in companies)':>12}")
        continue
    lp = last_price(cid)
    if lp is None:
        print(f"{tk:<8} {str(cid in held):<6} {'(no prices)':>12}")
        continue
    stale = (date_ := __import__("datetime").date.fromisoformat(TODAY)
             - __import__("datetime").date.fromisoformat(lp)).days
    print(f"{tk:<8} {str(cid in held):<6} {lp:>12} {stale:>8}")

# Which companies have rows after 2026-09-30?
after = (supabase.table("price_history").select("company_id")
         .gt("price_date", "2026-09-30").limit(2000).execute().data or [])
fresh_ids = {r["company_id"] for r in after}
fresh_ticks = sorted(tick.get(c, f"id{c}") for c in fresh_ids)
print(f"\n=== {len(fresh_ids)} companies with price after 2026-09-30 ===")
print(f"  {fresh_ticks}")

fresh_held = sorted(t for t in fresh_ticks
                    if rev.get(t) in held)
print(f"\n  of which HELD: {len(fresh_held)} -> {fresh_held}")

# Stale held companies: held but last price <= 2026-09-30
stale_held = []
for cid in sorted(held):
    lp = last_price(cid)
    if lp and lp <= "2026-09-30":
        stale_held.append((tick.get(cid, str(cid)), lp))
print(f"\n  HELD companies whose last price <= 2026-09-30: {len(stale_held)}")
print(f"    {stale_held[:40]}")

# jobs table columns (discover schema for dead_letter inspection)
j1 = (supabase.table("jobs").select("*").limit(1).execute().data or [])
if j1:
    print(f"\n=== jobs columns ===\n  {sorted(j1[0].keys())}")
