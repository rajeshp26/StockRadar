#!/usr/bin/env python3
"""
Cleanup Super Investors Database

Deletes all institutional holdings and investors records.
Run before backfill to ensure clean slate.
"""
import sys

sys.path.insert(0, ".")

from database import supabase


def cleanup():
    """Clear all super investor data from database."""
    print("Deleting institutional_holdings...")
    holdings_result = supabase.table("institutional_holdings").delete().neq("holding_id", 0).execute()
    print(f"  Deleted holdings: {holdings_result}")

    print("Deleting institutional_investors...")
    investors_result = supabase.table("institutional_investors").delete().neq("investor_id", 0).execute()
    print(f"  Deleted investors: {investors_result}")

    print("Cleanup complete!")


if __name__ == "__main__":
    cleanup()
