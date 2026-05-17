#!/usr/bin/env python3
"""Check if pending investors have SEC filings"""
import sys
sys.path.insert(0, '.')

from edgar import Company, set_identity
from datetime import datetime

set_identity("StockerPro backfill script rajeshp01@gmail.com")

# Updated with verified CIKs (May 2026) - 13F-HR Only
investors = [
    ("0001549575", "Mohnish Pabrai (Dalal Street LLC)"),
    ("0001418814", "Mason Morfit (ValueAct Holdings)"),
    ("0001406950", "Bill Nygren (Harris Associates)"),
]

for name, (cik, desc) in investors:
    print(f"\n=== Checking {name} (CIK: {cik}) ===")
    try:
        company = Company(cik)
        print(f"SEC Name: {company.name}")
        filings = company.get_filings()
        
        # Check for 13F-HR
        f13f = filings.filter(form="13F-HR")
        print(f"13F-HR filings: {len(f13f) if f13f else 0}")
        
        if f13f and len(f13f) > 0:
            print("  Recent filings:")
            for f in list(f13f)[:5]:
                print(f"    - {f.filing_date}: {f.accession_number}")
        else:
            print("  ⚠️  No 13F-HR filings found!")
            
        # Check for NPORT-P (mutual fund format)
        nport = filings.filter(form="NPORT-P")
        print(f"NPORT-P filings: {len(nport) if nport else 0}")
        
    except Exception as e:
        print(f"Error: {e}")
