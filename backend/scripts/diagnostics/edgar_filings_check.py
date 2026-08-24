#!/usr/bin/env python3
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
import warnings
warnings.filterwarnings("ignore")

from edgar import set_identity, get_filings
set_identity("Test rajeshp01@gmail.com")

# Test with date range
cik = "0001067983"

# Try: get recent filings with specific date range
# 13F is quarterly, so filter by year
for year in [2025, 2024, 2023, 2022, 2021]:
    try:
        filings = get_filings(year=year, form="13F-HR").filter(cik=cik)
        filing_list = list(filings)
        print(f"Year {year}: {len(filing_list)} filings")
        if filing_list:
            print(f"  Latest: {filing_list[0].filing_date}")
    except Exception as e:
        print(f"Year {year}: Error - {e}")