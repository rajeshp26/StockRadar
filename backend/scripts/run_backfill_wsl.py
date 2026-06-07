"""
Helper to run phase7_backfill.py in WSL for all portfolio stocks.
Fetches portfolio company IDs, then invokes the backfill.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase


async def main():
    # Get all unique company_ids from portfolio_holdings
    resp = supabase.table("portfolio_holdings").select("company_id").execute()
    ids = sorted({r["company_id"] for r in (resp.data or [])})
    print(f"Found {len(ids)} portfolio companies: {ids}")

    if not ids:
        print("No portfolio companies found — nothing to backfill.")
        return

    # Build the wsl command
    ids_str = " ".join(str(i) for i in ids)
    wsl_cmd = (
        f'wsl bash -c "source ~/venv_stockerpro/bin/activate'
        f' && cd /mnt/c/Project/StockerPro/StockerPro/backend'
        f' && python scripts/phase7_backfill.py --company-id {ids_str} --concurrency 3"'
    )
    print(f"Running: {wsl_cmd}")
    result = subprocess.run(
        ["wsl", "bash", "-c",
         f"source ~/venv_stockerpro/bin/activate"
         f" && cd /mnt/c/Project/StockerPro/StockerPro/backend"
         f" && python scripts/phase7_backfill.py --company-id {ids_str} --concurrency 3"],
        capture_output=True, text=True
    )
    print(result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
    print(f"\nExit code: {result.returncode}")


if __name__ == "__main__":
    asyncio.run(main())
