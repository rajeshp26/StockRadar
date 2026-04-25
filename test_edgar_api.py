#!/usr/bin/env python3
"""
Test script to verify edgartools API behavior for 13F filings.
Run in WSL: source ~/venv_stockerpro/bin/activate && python test_edgar_api.py
"""

import sys
print("=" * 60)
print("EDGARTOOLS API TEST SCRIPT")
print("=" * 60)

from edgar import set_identity
set_identity("StockerPro Test rajeshp01@gmail.com")

from edgar import get_filings, Company

# Test CIK for Warren Buffett (Berkshire Hathaway)
TEST_CIK = "0001067983"
TEST_TICKER = "BAC"  # Bank of America - common stock in 13F filings

print("\n[1] Testing: get_filings(form='13F-HR')")
print("-" * 40)
filings = get_filings(form="13F-HR")
print(f"  Type: {type(filings)}")
print(f"  len(filings): {len(filings)}")
print(f"  empty: {filings.empty}")

print("\n[2] Testing: filter(cik=cik)")
print("-" * 40)
filtered = filings.filter(cik=TEST_CIK)
print(f"  Type: {type(filtered)}")
print(f"  len(filtered): {len(filtered)}")
print(f"  empty: {filtered.empty}")

print("\n[3] Testing: .latest() with default n=1")
print("-" * 40)
latest_1 = filtered.latest()
print(f"  Type of latest(): {type(latest_1)}")
print(f"  Is Filing object: {type(latest_1).__name__}")
try:
    print(f"  len(latest_1): {len(latest_1)}")
except TypeError as e:
    print(f"  ERROR: {e}")
    print("  ^ Confirms: .latest() returns single Filing, not collection")

print("\n[4] Testing: .latest(n) with n > 1")
print("-" * 40)
latest_20 = filtered.latest(20)
print(f"  Type of latest(20): {type(latest_20)}")
try:
    print(f"  len(latest_20): {len(latest_20)}")
except TypeError as e:
    print(f"  ERROR: {e}")
    print("  ^ Confirms: .latest(n) also returns Filing when collection has 1 item")

print("\n[5] Testing: .head(n)")
print("-" * 40)
head_20 = filtered.head(20)
print(f"  Type of head(20): {type(head_20)}")
try:
    print(f"  len(head_20): {len(head_20)}")
except TypeError as e:
    print(f"  ERROR: {e}")

print("\n[6] Testing: .data attribute")
print("-" * 40)
# Get the collection before calling latest()
print(f"  hasattr(filtered, 'data'): {hasattr(filtered, 'data')}")
print(f"  hasattr(filtered.latest(), 'data'): {hasattr(filtered.latest(), 'data')}")

# Try latest(20) - might still be single Filing
print("\n[7] Testing: iterating filtered collection")
print("-" * 40)
print(f"  Iterating over filtered (len={len(filtered)}):")
for i, f in enumerate(filtered):
    print(f"    [{i}] {f.company} - {f.filing_date}")
# Store for next test
filing_0 = None
for i, f in enumerate(filtered):
    print(f"    [{i}] {f.company} - {f.filing_date}")
    filing_0 = f
    break  # Just get first

print("\n[8] Testing: filing.obj() for 13F-HR")
print("-" * 40)
if filing_0 is None:
    print("  ERROR: No filing found")
    sys.exit(1)
try:
    thirteenf = filing_0.obj()
    print(f"  Type: {type(thirteenf)}")
    print(f"  management_company_name: {thirteenf.management_company_name}")
    print(f"  total_value: ${thirteenf.total_value:,}")
    print(f"  total_holdings: {thirteenf.total_holdings}")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

print("\n[9] Testing: thirteenf.holdings")
print("-" * 40)
holdings = thirteenf.holdings
print(f"  Type: {type(holdings)}")
print(f"  shape: {holdings.shape}")
print(f"  columns: {list(holdings.columns)}")

print("\n[10] Finding stock in holdings")
print("-" * 40)
stock_holding = holdings[holdings['Ticker'] == TEST_TICKER]
print(f"  Found {len(stock_holding)} row(s) for {TEST_TICKER}")
if not stock_holding.empty:
    row = stock_holding.iloc[0]
    shares = row.get('sharesPrnAmount')
    value = row.get('value')
    print(f"  shares (SharesPrnAmount): {shares}")
    print(f"  value (in $000s): ${value:,}" if value else f"  value: {value}")
    print(f"  Class: {row.get('Class')}")
    print(f"  Cusip: {row.get('Cusip')}")
else:
    # Check other columns
    print("  Stock not found. Checking by issuer name...")
    bac_by_name = holdings[holdings['Issuer'].str.contains('BANK', case=False, na=False)]
    print(f"  Found {len(bac_by_name)} rows with 'BANK' in name")
    if not bac_by_name.empty:
        print(f"    Sample: {bac_by_name.iloc[0].get('Issuer')}")

print("\n[11] Testing: Company class approach")
print("-" * 40)
try:
    company = Company(TEST_CIK)
    print(f"  Type: {type(company)}")
    print(f"  Company name: {company.name}")
    print(f"  cik: {company.cik}")
    
    company_filings = company.get_filings(form="13F-HR")
    print(f"  Type of company_filings: {type(company_filings)}")
    print(f"  len(company_filings): {len(company_filings)}")
    
    if len(company_filings) > 0:
        c_filing = company_filings[0]
        print(f"  Latest filing date: {c_filing.filing_date}")
        print(f"  Latest period: {c_filing.period_of_report}")
        c_thirteenf = c_filing.obj()
        print(f"  ThirteenF total_holdings: {c_thirteenf.total_holdings}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n[12] Testing: previous quarter")
print("-" * 40)
if len(filtered) > 1:
    prev_filing = filtered[1].obj()
    prev_holdings = prev_filing.holdings
    prev_stock = prev_holdings[prev_holdings['Ticker'] == TEST_TICKER]
    print(f"  Previous quarter: {prev_filing.period_of_report}")
    print(f"  Found {len(prev_stock)} row(s) for {TEST_TICKER}")
else:
    print("  Only 1 filing available")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETED SUCCESSFULLY")
print("=" * 60)