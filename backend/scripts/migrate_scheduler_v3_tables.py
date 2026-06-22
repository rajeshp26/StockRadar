"""
Apply v3 scheduler control-plane tables to Supabase.

Usage:
    python scripts/migrate_scheduler_v3_tables.py

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from environment.
"""

import os
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from database import supabase


SQL = Path(__file__).with_suffix(".sql").read_text()


def run():
    print("Applying v3 scheduler tables...")
    # Supabase's Python client doesn't support raw SQL via the REST API.
    # Use the management API or psql instead.
    #
    # Option A: Execute via supabase Python client (only works for simple statements)
    # Option B: Print SQL for manual execution via Supabase Dashboard SQL Editor
    # Option C: Use psql if SUPABASE_DATABASE_URL is configured
    #
    # We attempt option C first, then fall back to printing.

    pg_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if pg_url:
        import subprocess
        result = subprocess.run(
            ["psql", pg_url],
            input=SQL.encode(),
            capture_output=True,
        )
        if result.returncode == 0:
            print("Migration applied successfully via psql.")
        else:
            print(f"psql failed (rc={result.returncode}):")
            print(result.stderr.decode())
            print("\nFalling back to SQL print mode.\n")
            print(SQL)
    else:
        print("=" * 60)
        print("No SUPABASE_DATABASE_URL/DATABASE_URL found in environment.")
        print()
        print("Run this SQL in your Supabase Dashboard SQL Editor:")
        print("=" * 60)
        print()
        print(SQL)


if __name__ == "__main__":
    run()
