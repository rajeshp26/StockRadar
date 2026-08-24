"""Check Supabase database for financial data gaps."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
os.environ['PYTHONIOENCODING'] = 'utf-8'

import json

from database import supabase


def q(query_label, table, select_str="*", filters=None, order_col=None, desc=True, limit_val=None):
    print(f"\n{'='*70}")
    print(f"[QUERY] {query_label}")
    print(f"{'='*70}")
    try:
        qb = supabase.table(table).select(select_str)
        if filters:
            for col, op, val in filters:
                qb = qb.filter(col, op, val)
        if order_col:
            qb = qb.order(order_col, desc=desc)
        if limit_val:
            qb = qb.limit(limit_val)
        result = qb.execute()
        data = result.data
        print(f"[OK] Rows returned: {len(data)}")
        if data:
            print(json.dumps(data, indent=2, default=str))
        else:
            print("[WARN] No data found")
        return data
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


# 1. Scheduler State
q("SCHEDULER STATE - last run, next due, status", "scheduler_state", limit_val=50)

# 2. Scheduler Run History
q("SCHEDULER RUN HISTORY - recent executions", "scheduler_run_history", limit_val=30)

# 3a. Price History
print(f"\n{'='*70}")
print("[QUERY] PRICE HISTORY - advanced stats")
print(f"{'='*70}")
try:
    r = supabase.table("price_history").select("price_date").order("price_date", desc=True).limit(1).execute()
    if r.data:
        print(f"[OK] Latest price_date: {r.data[0]['price_date']}")
    else:
        print("[WARN] No price_history data")

    r2 = supabase.table("price_history").select("company_id").execute()
    if r2.data:
        companies = set(d['company_id'] for d in r2.data if d.get('company_id'))
        print(f"[OK] Distinct companies with price data: {len(companies)}")
    else:
        print("[WARN] No price_history data")
except Exception as e:
    print(f"[ERROR] {e}")

# 4. Income Statements
print(f"\n{'='*70}")
print("[QUERY] INCOME STATEMENTS - latest annual & quarterly")
print(f"{'='*70}")
try:
    ra = supabase.table("income_statements").select("fiscal_year").is_("fiscal_quarter", "null").order("fiscal_year", desc=True).limit(5).execute()
    if ra.data:
        print("[OK] Latest annual fiscal years:")
        for row in ra.data:
            print(f"     FY{row['fiscal_year']}")
    else:
        print("[WARN] No annual data (null check)")

    rq = supabase.table("income_statements").select("fiscal_year,fiscal_quarter").not_.is_("fiscal_quarter", "null").order("fiscal_year", desc=True).order("fiscal_quarter", desc=True).limit(5).execute()
    if rq.data:
        print("[OK] Latest quarterly data:")
        for row in rq.data:
            print(f"     FY{row['fiscal_year']} Q{row['fiscal_quarter']}")
    else:
        print("[WARN] No quarterly data")
except Exception as e:
    print(f"[ERROR] {e}")

# 5. Balance Sheets
print(f"\n{'='*70}")
print("[QUERY] BALANCE SHEETS - latest annual & quarterly")
print(f"{'='*70}")
try:
    ra = supabase.table("balance_sheets").select("fiscal_year").is_("fiscal_quarter", "null").order("fiscal_year", desc=True).limit(5).execute()
    if ra.data:
        print("[OK] Latest annual fiscal years:")
        for row in ra.data:
            print(f"     FY{row['fiscal_year']}")
    else:
        print("[WARN] No annual data (null check)")

    rq = supabase.table("balance_sheets").select("fiscal_year,fiscal_quarter").not_.is_("fiscal_quarter", "null").order("fiscal_year", desc=True).order("fiscal_quarter", desc=True).limit(5).execute()
    if rq.data:
        print("[OK] Latest quarterly data:")
        for row in rq.data:
            print(f"     FY{row['fiscal_year']} Q{row['fiscal_quarter']}")
    else:
        print("[WARN] No quarterly data")
except Exception as e:
    print(f"[ERROR] {e}")

# 6. Cash Flow Statements
print(f"\n{'='*70}")
print("[QUERY] CASH FLOW STATEMENTS - latest annual & quarterly")
print(f"{'='*70}")
try:
    ra = supabase.table("cash_flow_statements").select("fiscal_year").is_("fiscal_quarter", "null").order("fiscal_year", desc=True).limit(5).execute()
    if ra.data:
        print("[OK] Latest annual fiscal years:")
        for row in ra.data:
            print(f"     FY{row['fiscal_year']}")
    else:
        print("[WARN] No annual data (null check)")

    rq = supabase.table("cash_flow_statements").select("fiscal_year,fiscal_quarter").not_.is_("fiscal_quarter", "null").order("fiscal_year", desc=True).order("fiscal_quarter", desc=True).limit(5).execute()
    if rq.data:
        print("[OK] Latest quarterly data:")
        for row in rq.data:
            print(f"     FY{row['fiscal_year']} Q{row['fiscal_quarter']}")
    else:
        print("[WARN] No quarterly data")
except Exception as e:
    print(f"[ERROR] {e}")

# 7. Earnings — most recent announcement_date (not earnings_date)
print(f"\n{'='*70}")
print("[QUERY] EARNINGS - most recent announcement_date")
print(f"{'='*70}")
try:
    ra = supabase.table("earnings").select("announcement_date,period_end_date,fiscal_year,fiscal_quarter,company_id").order("announcement_date", desc=True).limit(10).execute()
    if ra.data:
        for row in ra.data:
            print(f"     {row}")
    else:
        print("[WARN] No earnings data")

    # Also check what columns exist with a limit 1
    r1 = supabase.table("earnings").select("*").limit(1).execute()
    if r1.data:
        print(f"\n[OK] Earnings columns: {list(r1.data[0].keys())}")
except Exception as e:
    print(f"[ERROR] {e}")

# 8. Dividend History
q("DIVIDEND HISTORY - most recent ex_dividend_date", "dividend_history", select_str="ex_dividend_date,company_id", order_col="ex_dividend_date", desc=True, limit_val=10)

# 9. Financial Ratios
q("FINANCIAL RATIOS - most recent fiscal_year", "financial_ratios", select_str="fiscal_year,company_id", order_col="fiscal_year", desc=True, limit_val=10)

# 10. Current Market Data
print(f"\n{'='*70}")
print("[QUERY] CURRENT MARKET DATA - sample rows + columns")
print(f"{'='*70}")
try:
    r1 = supabase.table("current_market_data").select("*").limit(3).execute()
    if r1.data:
        print("[OK] Sample rows:")
        for row in r1.data:
            print(f"     {row}")
        print(f"\n[OK] Columns: {list(r1.data[0].keys())}")
    else:
        print("[WARN] No data")
except Exception as e:
    print(f"[ERROR] {e}")

# 11. Data Quality Events
print(f"\n{'='*70}")
print("[QUERY] DATA QUALITY EVENTS - sample rows + columns")
print(f"{'='*70}")
try:
    r1 = supabase.table("data_quality_events").select("*").limit(20).execute()
    if r1.data:
        print("[OK] Sample rows:")
        for row in r1.data:
            print(f"     {row}")
    else:
        print("[WARN] No data")
except Exception as e:
    print(f"[ERROR] {e}")

# 12. Companies - count
print(f"\n{'='*70}")
print("[QUERY] COMPANIES - count + columns")
print(f"{'='*70}")
try:
    r_all = supabase.table("companies").select("*").execute()
    if r_all.data:
        total = len(r_all.data)
        print(f"[OK] Total companies: {total}")
        print(f"\n[OK] Columns: {list(r_all.data[0].keys())}")
        # Check what status-like fields exist
        for key in r_all.data[0].keys():
            if 'status' in key.lower() or 'active' in key.lower() or 'type' in key.lower() or 'sector' in key.lower():
                vals = set(d.get(key) for d in r_all.data if d.get(key))
                print(f"     {key}: {vals}")
    else:
        print("[WARN] No companies found")
except Exception as e:
    print(f"[ERROR] {e}")

# Summary
print(f"\n{'='*70}")
print("GAP ANALYSIS SUMMARY")
print(f"{'='*70}")
print("Reference date: June 2026")
print()

try:
    checks = [
        ('scheduler_state', 'updated_at', 'datetime'),
        ('scheduler_run_history', 'planned_at', 'datetime'),
        ('price_history', 'price_date', 'date'),
        ('earnings', 'announcement_date', 'date'),
        ('dividend_history', 'ex_dividend_date', 'date'),
        ('current_market_data', 'updated_at', 'datetime'),
        ('income_statements', 'fiscal_year', 'year'),
        ('balance_sheets', 'fiscal_year', 'year'),
        ('cash_flow_statements', 'fiscal_year', 'year'),
        ('financial_ratios', 'fiscal_year', 'year'),
    ]
    for table, col, ctype in checks:
        try:
            r = supabase.table(table).select(col).order(col, desc=True).limit(1).execute()
            if r.data and r.data[0].get(col):
                latest = r.data[0][col]
                print(f"  {table:30s} latest {col:20s}= {latest}")
            else:
                # Try created_at as fallback
                try:
                    r2 = supabase.table(table).select("created_at").order("created_at", desc=True).limit(1).execute()
                    if r2.data and r2.data[0].get("created_at"):
                        latest = r2.data[0]["created_at"]
                        print(f"  {table:30s} latest created_at        = {latest}")
                    else:
                        print(f"  {table:30s} NO DATA")
                except:
                    print(f"  {table:30s} NO DATA")
        except Exception as e:
            print(f"  {table:30s} ERROR: {e}")
except Exception as e:
    print(f"[ERROR] in summary: {e}")

print("\n[DONE] Check complete")
