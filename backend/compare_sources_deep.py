"""Deep dive: compare defeatbeta vs yfinance for companies that have both sources on any dates."""
import os
os.environ["ENVIRONMENT"] = "development"
from database import supabase as client

# Check specific companies that have defeatbeta data close to yfinance dates
# Look at the 13 companies with defeatbeta data
db_cos = set()
for r in (client.table("price_history").select("company_id").eq("data_source", "defeatbeta").execute().data or []):
    db_cos.add(r["company_id"])
for r in (client.table("price_history").select("company_id").eq("data_source", "defeat_beta").execute().data or []):
    db_cos.add(r["company_id"])

print(f"Companies with defeatbeta data: {len(db_cos)}")

# Get ticker symbols and compare defeatbeta vs yfinance closest dates
for cid in sorted(db_cos):
    co = client.table("companies").select("ticker_symbol, company_name, exchange").eq("company_id", cid).execute()
    sym = co.data[0]["ticker_symbol"] if co.data else "?"
    name = co.data[0]["company_name"][:30] if co.data else "?"
    exch = co.data[0]["exchange"] if co.data else "?"
    
    # Get the last defeatbeta entry
    db_last = client.table("price_history").select("price_date, close_price").eq("company_id", cid).in_("data_source", ["defeatbeta", "defeat_beta"]).order("price_date", desc=True).limit(1).execute()
    
    # Get the last yfinance entry
    yf_last = client.table("price_history").select("price_date, close_price").eq("company_id", cid).eq("data_source", "yfinance").order("price_date", desc=True).limit(1).execute()
    
    db_date = db_last.data[0]["price_date"] if db_last.data else "N/A"
    db_price = float(db_last.data[0]["close_price"]) if db_last.data else 0
    yf_date = yf_last.data[0]["price_date"] if yf_last.data else "N/A"
    yf_price = float(yf_last.data[0]["close_price"]) if yf_last.data else 0
    
    # Find the closest date where both have data
    # Get all defeatbeta dates for this company
    db_dates = set()
    for r in (client.table("price_history").select("price_date").eq("company_id", cid).in_("data_source", ["defeatbeta", "defeat_beta"]).execute().data or []):
        db_dates.add(r["price_date"])
    yf_dates = set()
    for r in (client.table("price_history").select("price_date").eq("company_id", cid).eq("data_source", "yfinance").execute().data or []):
        yf_dates.add(r["price_date"])
    
    # Find nearest dates for comparison
    ratio_str = "N/A"
    overlap = db_dates & yf_dates
    if overlap:
        # Direct comparison on same date
        overlap_date = sorted(overlap)[-1]
        db_p = float(client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", overlap_date).in_("data_source", ["defeatbeta", "defeat_beta"]).execute().data[0]["close_price"])
        yf_p = float(client.table("price_history").select("close_price").eq("company_id", cid).eq("price_date", overlap_date).eq("data_source", "yfinance").execute().data[0]["close_price"])
        ratio_str = f"{db_p/yf_p:.2f}x" if yf_p else "N/A"
        flag = " <<<" if (db_p/yf_p < 0.8 or db_p/yf_p > 1.2) else ""
        ratio_str += flag
    else:
        # Compare last defeatbeta with closest yfinance
        if db_last.data and yf_last.data:
            # Simple comparison of values
            if db_price and yf_price:
                ratio_str = f"{db_price/yf_price:.2f}x" if yf_price else "N/A"
                flag = " <<<" if (db_price/yf_price < 0.8 or db_price/yf_price > 1.2) else ""
                ratio_str += flag
    ratio_str = f"{db_price/yf_price:.2f}x" if yf_price else "N/A"
    flag = " <<<" if (db_price and yf_price and (db_price/yf_price < 0.8 or db_price/yf_price > 1.2)) else ""
    
    print(f"  {sym:8s} ({exch:5s}) DB[${db_price:>8.2f} @ {db_date}] vs YF[${yf_price:>8.2f} @ {yf_date}] -> {db_price/yf_price:.2f}x{flag}" if yf_price else f"  {sym:8s} ({exch:5s}) DB[${db_price:>8.2f} @ {db_date}] vs YF[no data]")
