"""Check yfinance output vs what's in DB for specific dates."""
import os
os.environ["ENVIRONMENT"] = "development"
import yfinance as yf
import pandas as pd
pd.set_option('display.max_columns', 10)
pd.set_option('display.width', 200)

from database import supabase as client

tickers = [
    ("RY", 2808),
    ("TD", 2225),
    ("ENB", 1341),
    ("SHOP", 1117),
    ("AAPL", 69),
]

target_dates = ["2026-05-21", "2026-05-22", "2026-05-28", "2026-05-29", "2026-05-30", "2026-06-22", "2026-06-23"]

for sym, cid in tickers:
    print(f"\n=== {sym} ===")
    
    # YFinance with period="max" (what get_price_history_df does)
    t = yf.Ticker(sym)
    hist = t.history(period="max", auto_adjust=True)
    
    print(f"  yfinance date range: {hist.index[0]} to {hist.index[-1]}")
    
    for d in target_dates:
        # yfinance result
        dt = pd.Timestamp(d)
        if dt in hist.index:
            yf_close = float(hist.loc[dt, "Close"])
        else:
            yf_close = None
        
        # DB result
        db_resp = client.table("price_history").select("close_price, data_source").eq("company_id", cid).eq("price_date", d).execute()
        if db_resp.data:
            db_close = float(db_resp.data[0]["close_price"])
            db_source = db_resp.data[0].get("data_source")
        else:
            db_close = None
            db_source = "NONE"
        
        match = "✓" if (yf_close and db_close and abs(yf_close - db_close) / max(yf_close, db_close) < 0.05) else "✗"
        print(f"  {d}: yf=${yf_close}  db=${db_close} [{db_source}] {match}")
    
    # Also show the last Friday of May
    print(f"  May weekdays from yfinance:")
    may_data = hist[(hist.index >= '2026-05-01') & (hist.index <= '2026-05-31')]
    for idx, row in may_data.iterrows():
        print(f"    {idx.date()}: Close=${float(row['Close']):.2f} (weekday={idx.dayofweek})")
