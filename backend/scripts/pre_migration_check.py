#!/usr/bin/env python3
"""Check DB state before CIK migration.
Uses project's config pattern (no hardcoded credentials).
"""
import sys

sys.path.insert(0, '.')

from database import supabase


def main():
    print("=== CHECKING OLD CIKs ===")
    old_ciks = ['0001173334', '0001325920', '0000872323']

    for cik in old_ciks:
        r = supabase.table('institutional_investors').select('*').eq('cik', cik).execute()
        if r.data:
            inv = r.data[0]
            # Count holdings
            h = supabase.table('institutional_holdings').select('holding_id').eq('investor_id', inv['investor_id']).execute()
            print(f"CIK {cik}: ID={inv['investor_id']}, Name={inv['investor_name']}, Last={inv.get('last_filed_period', 'None')}, Holdings={len(h.data)}")
        else:
            print(f"CIK {cik}: NOT FOUND")

    print("\n=== CHECKING NEW CIKs ===")
    new_ciks = ['0001549575', '0001418814', '0001406950']

    for cik in new_ciks:
        r = supabase.table('institutional_investors').select('*').eq('cik', cik).execute()
        if r.data:
            inv = r.data[0]
            h = supabase.table('institutional_holdings').select('holding_id').eq('investor_id', inv['investor_id']).execute()
            print(f"CIK {cik}: ID={inv['investor_id']}, Name={inv['investor_name']} ⚠️ EXISTS! (Holdings={len(h.data)})")
        else:
            print(f"CIK {cik}: NOT FOUND (safe to migrate)")

if __name__ == "__main__":
    main()
