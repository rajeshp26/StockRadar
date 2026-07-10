import os
os.environ["ENVIRONMENT"] = "development"
from database import supabase as client
from datetime import date

# Check all tickers in accounts 10,11,12 for bad Jun 18 data
tickers = [2808, 2225, 1341, 1117, 69]  # RY, TD, ENB, SHOP, AAPL
print("Bad price data on 2026-06-18 vs adjacent days:")
print(f"{'Symbol':>8s} {'May 30':>10s} {'Jun 18 (BAD)':>14s} {'Live CMD':>10s} {'Ratio':>8s}")
for cid in tickers:
    # Get company symbol
    co = client.table("companies").select("ticker_symbol").eq("company_id", cid).execute()
    sym = co.data[0]["ticker_symbol"] if co.data else "?"
    
    # May 30 price
    may30 = client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", "2026-05-30").execute()
    may30_px = float(may30.data[0]["close_price"]) if may30.data else 0
    
    # Jun 18 price (the bad one)
    jun18 = client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", "2026-06-18").execute()
    jun18_px = float(jun18.data[0]["close_price"]) if jun18.data else 0
    
    # Live current_market_data
    cmd = client.table("current_market_data").select("current_price").eq("company_id", cid).execute()
    live_px = float(cmd.data[0]["current_price"]) if cmd.data else 0
    
    ratio = jun18_px / may30_px if may30_px else 0
    print(f"{sym:>8s} ${may30_px:>7.2f} ${jun18_px:>10.2f} ${live_px:>7.2f} {ratio:>7.2f}x")

# Also check the 2026-05-29 spikes (another bad date)
print(f"\nSpike check on 2026-05-29:")
for cid in tickers:
    co = client.table("companies").select("ticker_symbol").eq("company_id", cid).execute()
    sym = co.data[0]["ticker_symbol"] if co.data else "?"
    may28 = client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", "2026-05-28").execute()
    may29 = client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", "2026-05-29").execute()
    may30 = client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", "2026-05-30").execute()
    p28 = float(may28.data[0]["close_price"]) if may28.data else 0
    p29 = float(may29.data[0]["close_price"]) if may29.data else 0
    p30 = float(may30.data[0]["close_price"]) if may30.data else 0
    print(f"  {sym}: May 28={p28:.2f}  May 29={p29:.2f}  May 30={p30:.2f}  (May 29 spike={p29/p28:.2f}x)" if p28 else f"  {sym}: N/A")

# Count how many companies have Jun 18 price data vs total
all_ph_jun18 = client.table("price_history").select("company_id").eq("price_date", "2026-06-18").execute()
print(f"\nTotal companies with price on 2026-06-18: {len(all_ph_jun18.data)}")

# Show a sample of Jun 18 prices vs adjacent to assess scale of corruption
sample = client.table("price_history").select("company_id, close_price").eq("price_date", "2026-06-18").limit(20).execute()
print("\nSample of Jun 18 prices:")
for s in sample.data or []:
    co = client.table("companies").select("ticker_symbol").eq("company_id", s["company_id"]).execute()
    sym = co.data[0]["ticker_symbol"] if co.data else "?"
    print(f"  {sym:8s} (cid={s['company_id']}): ${s['close_price']}")
