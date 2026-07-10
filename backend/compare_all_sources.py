"""Compare defeatbeta vs yfinance prices across ALL stocks to see if data is consistently wrong."""
import os
os.environ["ENVIRONMENT"] = "development"
from database import supabase as client
from datetime import date

# Find companies that have BOTH defeatbeta and yfinance data on the same date
# Check May 28 (a Thursday, so both should have valid data if correct)
target_date = "2026-05-28"

resp = client.table("price_history").select("company_id, close_price, data_source").eq("price_date", target_date).execute()

# Group by company
companies = {}
for r in (resp.data or []):
    cid = r["company_id"]
    if cid not in companies:
        companies[cid] = {}
    companies[cid][r.get("data_source", "unknown")] = float(r["close_price"])

# Find companies with both sources
both = {cid: sources for cid, sources in companies.items() if "yfinance" in sources and "defeatbeta" in sources}

# Or also check 'defeat_beta' variant
both2 = {}
for cid, sources in companies.items():
    sources_flat = {}
    for k, v in sources.items():
        norm_key = "defeatbeta" if k in ("defeatbeta", "defeat_beta") else k
        sources_flat[norm_key] = v
    if "yfinance" in sources_flat and "defeatbeta" in sources_flat:
        both2[cid] = sources_flat

print(f"\nCompanies with BOTH defeatbeta AND yfinance data on {target_date}: {len(both2)}")

if both2:
    print(f"\n{'CID':>6s} {'DefeatBeta':>12s} {'YFinance':>12s} {'Ratio':>8s}")
    mismatches = 0
    for cid, sources in sorted(both2.items()):
        db = sources["defeatbeta"]
        yf = sources["yfinance"]
        ratio = db / yf if yf else 0
        flag = " <<<" if (ratio < 0.8 or ratio > 1.2) else ""
        if ratio < 0.8 or ratio > 1.2:
            mismatches += 1
        print(f"{cid:>6d} ${db:>9.2f} ${yf:>9.2f} {ratio:>7.2f}x{flag}")
    
    print(f"\nMismatches (ratio < 0.8 or > 1.2): {mismatches}/{len(both2)}")
    
    # Show some ticker symbols for mismatches
    if mismatches > 0:
        print("\nSample mismatch tickers:")
        for cid, sources in sorted(both2.items()):
            db = sources["defeatbeta"]
            yf = sources["yfinance"]
            ratio = db / yf if yf else 0
            if ratio < 0.8 or ratio > 1.2:
                co = client.table("companies").select("ticker_symbol, company_name, exchange").eq("company_id", cid).execute()
                if co.data:
                    print(f"  {co.data[0]['ticker_symbol']:8s} ({co.data[0]['company_name'][:40]:40s}) {co.data[0]['exchange']:6s}  DB=${db:.2f} YF=${yf:.2f} ratio={ratio:.2f}x")

# Also check: how many companies have ANY defeatbeta data vs yfinance data
db_count = client.table("price_history").select("data_source", count="exact").eq("data_source", "defeatbeta").execute()
db_count2 = client.table("price_history").select("data_source", count="exact").eq("data_source", "defeat_beta").execute()
yf_count = client.table("price_history").select("data_source", count="exact").eq("data_source", "yfinance").execute()

db_total = (db_count.count if hasattr(db_count, 'count') else 0) + (db_count2.count if hasattr(db_count2, 'count') else 0)
yf_total = yf_count.count if hasattr(yf_count, 'count') else 0
print(f"\nTotal rows: defeatbeta={db_total}, yfinance={yf_total}")

# Distinct companies per source
db_cos = set()
for r in (client.table("price_history").select("company_id").eq("data_source", "defeatbeta").execute().data or []):
    db_cos.add(r["company_id"])
for r in (client.table("price_history").select("company_id").eq("data_source", "defeat_beta").execute().data or []):
    db_cos.add(r["company_id"])
yf_cos = set(r["company_id"] for r in (client.table("price_history").select("company_id").eq("data_source", "yfinance").execute().data or []))
print(f"Companies with defeatbeta: {len(db_cos)}, Companies with yfinance: {len(yf_cos)}")
