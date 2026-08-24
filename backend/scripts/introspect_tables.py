"""Introspect all Supabase tables relevant to portfolio events migration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase

TABLES = [
    "companies",
    "portfolio_transactions",
    "portfolio_holdings",
    "portfolio_snapshots",
    "portfolio_dividends",
    "portfolio_cash_activity",
    "portfolio_accounts",
    "accounts",
    "portfolio_events",
    "security_master",
    "fx_rate_history",
    "portfolio_brokerages",
    "portfolio_performance",
    "portfolio_import_history",
]

for table in TABLES:
    try:
        r = supabase.table(table).select("*").limit(3).execute()
        if r.data and len(r.data) > 0:
            columns = list(r.data[0].keys())
            print(f"\n{'='*80}")
            print(f"TABLE: {table}")
            print(f"{'='*80}")
            print(f"  Columns ({len(columns)}): {columns}")
            print(f"  Sample row: {r.data[0]}")
        elif r.data and len(r.data) == 0:
            # Table exists but is empty — get columns via a different approach
            print(f"\n{'='*80}")
            print(f"TABLE: {table}")
            print(f"{'='*80}")
            print("  Table exists but has 0 rows")
        else:
            print(f"\n{'='*80}")
            print(f"TABLE: {table}")
            print(f"{'='*80}")
            print("  ERROR: No data returned")
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"TABLE: {table}")
        print(f"{'='*80}")
        print(f"  ERROR: {e}")
