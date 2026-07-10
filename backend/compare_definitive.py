"""
Compare yfinance (queried fresh) vs DB prices for the exact same dates.
This doesn't rely on defeatbeta SDK - it compares the STORED data against yfinance directly.
"""
import os
os.environ["ENVIRONMENT"] = "development"
import yfinance as yf
import pandas as pd
pd.set_option('display.max_rows', 100)
pd.set_option('display.width', 300)

from database import supabase as client

tickers = [("RY", 2808), ("TD", 2225), ("ENB", 1341), ("SHOP", 1117), ("AAPL", 69)]

for sym, cid in tickers:
    print(f"\n{'='*80}")
    print(f"  {sym} (cid={cid})")
    print(f"{'='*80}")
    
    # Get ALL DB entries for this company, grouped by data_source
    db_rows = client.table("price_history").select("price_date, close_price, data_source").eq("company_id", cid).order("price_date").execute()
    
    db_defeatbeta = {r["price_date"]: float(r["close_price"]) for r in (db_rows.data or []) if r.get("data_source") in ("defeatbeta", "defeat_beta")}
    db_yfinance = {r["price_date"]: float(r["close_price"]) for r in (db_rows.data or []) if r.get("data_source") == "yfinance"}
    
    print(f"  DefeatBeta entries: {len(db_defeatbeta)} dates, YFinance entries: {len(db_yfinance)} dates")
    
    # Get yfinance data
    t = yf.Ticker(sym)
    hist = t.history(period="6mo", auto_adjust=True)
    
    # For each defeatbeta date, check what yfinance says
    print(f"\n  {'Date':<12s} {'DB(DBeta)':<12s} {'DB(YF)':<12s} {'YF direct':<12s} {'Diff':<8s}")
    print(f"  {'-'*56}")
    
    mismatches = 0
    total = 0
    for dt_str in sorted(set(list(db_defeatbeta.keys()) + list(db_yfinance.keys()))):
        db_db = db_defeatbeta.get(dt_str)
        db_yf = db_yfinance.get(dt_str)
        
        # Get yfinance value for this date (convert tz-aware index to naive date)
        hist_dates = {d.date(): float(hist.loc[d, "Close"]) for d in hist.index}
        yf_close = hist_dates.get(pd.Timestamp(dt_str).date())
        
        # Determine the "real" value to compare against
        real = yf_close or db_yf or db_db
        
        if db_db is not None and yf_close is not None:
            diff = (db_db - yf_close) / yf_close * 100
            if abs(diff) > 10:
                flag = f" <<< {diff:+.1f}%"
                mismatches += 1
            else:
                flag = ""
            total += 1
            print(f"  {dt_str:<12s} ${db_db:<9.2f} {'$'+str(db_yf or ''):<12s} ${yf_close:<9.2f} {flag}")
        elif db_db is not None and yf_close is None and db_yf is not None:
            # Both DB sources exist but yfinance direct doesn't have this date
            diff = (db_db - db_yf) / db_yf * 100
            if abs(diff) > 10:
                flag = f" <<< {diff:+.1f}%"
                mismatches += 1
            else:
                flag = ""
            total += 1
            print(f"  {dt_str:<12s} ${db_db:<9.2f} ${db_yf:<9.2f} {'N/A':<12s} DB(DBeta) vs DB(YF): {flag}")
        elif db_db is not None:
            print(f"  {dt_str:<12s} ${db_db:<9.2f} {'N/A':<12s} {'N/A':<12s}")
        elif db_yf is not None and yf_close is not None:
            diff = (db_yf - yf_close) / yf_close * 100
            flag = f" <<< {diff:+.1f}%" if abs(diff) > 10 else ""
            print(f"  {dt_str:<12s} {'N/A':<12s} ${db_yf:<9.2f} ${yf_close:<9.2f} {flag}")
    
    pct = mismatches / total * 100 if total else 0
    print(f"\n  DefeatBeta vs yFinance mismatches (>10% diff): {mismatches}/{total} ({pct:.1f}%)")
