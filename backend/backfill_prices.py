"""
Backfill price_history for companies that had data on 2026-05-29 or 2026-06-18.
Uses YFinanceProvider with auto_adjust=True (now fixed).
"""
import os
os.environ["ENVIRONMENT"] = "development"
import asyncio
import logging
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from database import supabase as client
from providers.yfinance_provider import YFinanceProvider
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# These are the 5 tickers from accounts 10,11,12 that need fixing
TICKERS = {
    "RY": 2808,
    "TD": 2225,
    "ENB": 1341,
    "SHOP": 1117,
    "AAPL": 69,
}

yf_prov = YFinanceProvider()

REQUIRED_DAYS = 40  # match scheduler lookback

def compress_daily_to_monthly_eom(rows):
    """Keep only the last available price_date per year-month."""
    by_month = {}
    for r in rows:
        ym = r["price_date"].strftime("%Y-%m")
        if ym not in by_month or r["price_date"] > by_month[ym]["price_date"]:
            by_month[ym] = r
    return sorted(by_month.values(), key=lambda x: x["price_date"])

async def backfill_one(symbol, company_id):
    logger.info(f"Backfilling {symbol} (company_id={company_id})...")
    
    # Fetch with fixed auto_adjust=True
    df = yf_prov.get_price_history_df(symbol)
    if df is None or df.empty:
        logger.warning(f"No data for {symbol}")
        return 0
    
    # Build daily rows
    daily = []
    for _, r in df.iterrows():
        dt = pd.to_datetime(r.get("price_date"))
        if pd.isna(dt):
            continue
        daily.append({
            "company_id": company_id,
            "price_date": dt.date(),
            "open_price": float(r.get("open_price", 0)),
            "close_price": float(r.get("close_price", 0)),
            "high_price": float(r.get("high_price", 0)),
            "low_price": float(r.get("low_price", 0)),
            "volume": int(r.get("volume", 0)),
            "data_source": "yfinance",
        })
    
    # Filter to last REQUIRED_DAYS
    cutoff = date.today() - timedelta(days=REQUIRED_DAYS)
    daily = [r for r in daily if r["price_date"] >= cutoff]
    
    # Compress to monthly EOM
    monthly = compress_daily_to_monthly_eom(daily)
    
    # Upsert
    for row in monthly:
        row_str = {k: str(v) if isinstance(v, date) else v for k, v in row.items()}
        existing = client.table("price_history").select("company_id").eq("company_id", company_id).eq("price_date", str(row["price_date"])).execute()
        if existing.data:
            client.table("price_history").update(row_str).eq("company_id", company_id).eq("price_date", str(row["price_date"])).execute()
        else:
            client.table("price_history").insert(row_str).execute()
    
    for m in monthly:
        logger.info(f"  {symbol} {m['price_date']}: close=${m['close_price']:.2f}")
    
    return len(monthly)

async def main():
    total = 0
    for sym, cid in TICKERS.items():
        n = await backfill_one(sym, cid)
        total += n
    logger.info(f"Done. {total} monthly rows backfilled.")
    
    # Verify no more bad Jun 18 data
    for d in ["2026-05-29", "2026-06-18"]:
        resp = client.table("price_history").select("company_id, close_price").eq("price_date", d).execute()
        if resp.data:
            logger.warning(f"WARNING: {len(resp.data)} rows still exist for {d}")
        else:
            logger.info(f"Verified: no rows for {d}")

asyncio.run(main())
