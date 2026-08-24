"""
One-time migration: backfill shares_change and shares_change_pct
for all existing institutional_holdings rows.

Logic per row:
  - Find the previous quarter's row for the same (investor_id, company_id)
  - shares_change     = current.shares_held - prev.shares_held
  - shares_change_pct = (shares_change / prev.shares_held) * 100
  - change_type       = new | increased | decreased | held | sold

Run once:
    python migrations/backfill_holdings_changes.py

Safe to re-run: only updates rows where shares_change IS NULL.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import supabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def _change_type(shares_change: int, prev_shares: int) -> str:
    if prev_shares == 0:
        return "new"
    if shares_change == 0:
        return "held"
    pct = abs(shares_change / prev_shares) * 100
    if pct < 1.0:
        return "held"
    return "increased" if shares_change > 0 else "decreased"


def backfill() -> None:
    logger.info("Fetching all holdings ordered by investor, company, quarter...")

    # Fetch all rows — ordered so we can do a single-pass diff
    result = supabase.table("institutional_holdings").select(
        "holding_id, investor_id, company_id, quarter_end_date, "
        "shares_held, shares_change"
    ).order("investor_id").order("company_id").order("quarter_end_date").execute()

    rows = result.data or []
    logger.info("Total rows: %d", len(rows))

    updates = []
    prev: dict | None = None

    for row in rows:
        # Skip rows already backfilled
        if row["shares_change"] is not None:
            prev = row
            continue

        same_series = (
            prev is not None
            and prev["investor_id"] == row["investor_id"]
            and prev["company_id"] == row["company_id"]
        )

        if not same_series:
            # First filing for this (investor, company) pair — it's a new position
            updates.append({
                "holding_id": row["holding_id"],
                "shares_change": 0,
                "shares_change_pct": 0.0,
                "change_type": "new",
            })
        else:
            prev_shares = prev["shares_held"] or 0
            curr_shares = row["shares_held"] or 0
            delta = curr_shares - prev_shares
            pct = round((delta / prev_shares) * 100, 4) if prev_shares else 0.0
            ctype = _change_type(delta, prev_shares)
            updates.append({
                "holding_id": row["holding_id"],
                "shares_change": delta,
                "shares_change_pct": pct,
                "change_type": ctype,
            })

        prev = row

    logger.info("Rows needing update: %d", len(updates))

    # Batch upsert in chunks
    updated = 0
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i : i + BATCH_SIZE]
        for item in batch:
            hid = item.pop("holding_id")
            supabase.table("institutional_holdings").update(item).eq(
                "holding_id", hid
            ).execute()
            item["holding_id"] = hid  # restore for logging
        updated += len(batch)
        logger.info("  Updated %d / %d", updated, len(updates))

    logger.info("✅ Backfill complete. %d rows updated.", updated)


if __name__ == "__main__":
    backfill()
