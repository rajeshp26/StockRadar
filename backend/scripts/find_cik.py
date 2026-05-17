#!/usr/bin/env python3
"""Find correct CIKs for investors"""
import sys
sys.path.insert(0, '.')

from edgar import set_identity, Company, find
from datetime import datetime

set_identity("StockerPro backfill script rajeshp01@gmail.com")

# Search for correct entities
searches = [
    ("Mohnish Pabrai", "Pabrai"),
    ("Mason Morfit", "ValueAct"),
    ("Bill Nygren", "Harris Associates"),
]

for name, search_term in searches:
    print(f"\n=== Searching for {name} with term '{search_term}' ===")
    try:
        results = find(search_term)
        if results:
            for r in results[:5]:
                print(f"  CIK: {r.cik}, Name: {r.name}")
        else:
            print("  No results found")
    except Exception as e:
        print(f"  Error: {e}")
