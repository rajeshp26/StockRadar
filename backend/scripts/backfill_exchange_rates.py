"""
One-time backfill of historical FX rates into the exchange_rates table.

Runs before Phase 5 (snapshot rebuild) to ensure historical snapshots
can be reconstructed with correct period-appropriate rates.

Extended-range note: for accounts created after this backfill runs,
the snapshot builder will fail to find rates for dates before the backfill
range. Re-run this script periodically with an updated --start, or extend
the daily scheduler to fetch on demand for missing dates.

Usage:
    python scripts/backfill_exchange_rates.py --start 2020-01-01 --pairs USD/CAD CAD/USD
"""

import argparse
import sys
from datetime import date
from decimal import Decimal
import math
import logging

sys.path.insert(0, ".")

import pandas as pd
import yfinance as yf

from database import supabase
from shared.time_utils import now_utc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 250


def backfill_pair(base: str, target: str, start: date, end: date) -> int:
    """Download history for an FX pair and upsert into exchange_rates."""
    symbol = f"{base}{target}=X"
    df = yf.download(symbol, start=start.isoformat(), end=end.isoformat(),
                     auto_adjust=False, progress=False)
    if df is None or df.empty:
        return 0

    close_series = df["Close"]
    if isinstance(close_series, pd.DataFrame):
        close_series = close_series.iloc[:, 0]

    rows = []
    for idx, row in close_series.items():
        rate_date = idx.date() if hasattr(idx, "date") else idx
        close = row
        if isinstance(close, pd.Series):
            close = close.iloc[0]
        if close is None or (isinstance(close, float) and math.isnan(close)):
            continue
        rows.append({
            "base_currency": base,
            "target_currency": target,
            "rate": str(Decimal(str(round(float(close), 8)))),
            "rate_date": rate_date.isoformat(),
            "source": "yfinance",
            "fetched_at": now_utc().isoformat(),
        })

    count = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        supabase.table("exchange_rates").upsert(
            batch,
            on_conflict="base_currency,target_currency,rate_date",
        ).execute()
        count += len(batch)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--pairs", nargs="+", default=["USD/CAD", "CAD/USD"])
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = now_utc().date()

    for pair in args.pairs:
        base, target = pair.split("/")
        n = backfill_pair(base.upper(), target.upper(), start, end)
        logger.info("Backfilled %d rows for %s", n, pair)
