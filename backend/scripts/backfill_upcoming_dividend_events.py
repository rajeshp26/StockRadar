"""
One-time backfill: populate upcoming_dividend_events from dividend_history.

For each company with >= 4 dividend_history rows, runs the prediction
algorithm (avg_gap + frequency bands + relativedelta) and upserts a
'predicted' row into upcoming_dividend_events.

Skips companies where the predicted next date is already in the past
(suspended or slow-to-report payers — the scheduler will pick those up
from providers).

Safe to re-run: upserts via UNIQUE(company_id, data_source).

Run once:
    python scripts/backfill_upcoming_dividend_events.py
"""
import sys
import logging
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("backfill_upcoming")


def _as_date(v):
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(v) if isinstance(v, str) else date.fromtimestamp(v / 1000) if v else None
    except (ValueError, TypeError):
        return None


def predict_next_ex_date(company_id: int) -> date | None:
    """Mirror of estimate_next_ex_date() from market_data_scheduler.py."""
    today = date.today()
    resp = (
        supabase.table("dividend_history")
        .select("ex_dividend_date, dividend_amount, dividend_type")
        .eq("company_id", company_id)
        .not_.is_("dividend_amount", "null")
        .lte("ex_dividend_date", today.isoformat())
        .order("ex_dividend_date", desc=True)
        .limit(8)
        .execute()
    )
    rows = resp.data or []
    if len(rows) < 4:
        return None

    regular = [r for r in rows if r.get("dividend_type", "regular") != "special"]
    if len(regular) < 4:
        regular = rows[:4]

    sorted_dates = sorted(_as_date(r["ex_dividend_date"]) for r in regular)
    sorted_dates = [d for d in sorted_dates if d is not None]
    if len(sorted_dates) < 4:
        return None

    gaps = [(b - a).days for a, b in zip(sorted_dates, sorted_dates[1:]) if (b - a).days > 0]
    if not gaps:
        return None

    avg_gap = sum(gaps) / len(gaps)
    last_ex = sorted_dates[-1]

    if avg_gap <= 35:
        next_date = last_ex + timedelta(days=round(avg_gap))
    elif avg_gap <= 100:
        months = round(avg_gap / 30.44)
        next_date = last_ex + relativedelta(months=months)
    elif avg_gap <= 200:
        next_date = last_ex + relativedelta(months=6)
    else:
        next_date = last_ex + relativedelta(years=1)

    if next_date < today:
        return None
    return next_date


def main():
    logger.info("Starting backfill of upcoming_dividend_events from dividend_history")

    # Paginate to avoid PostgREST's 1000-row default limit (table has 13k+ rows)
    all_cids: set = set()
    start = 0
    page_size = 1000
    while True:
        page = supabase.from_("dividend_history").select("company_id").range(start, start + page_size - 1).execute()
        if not page.data:
            break
        for r in page.data:
            all_cids.add(r["company_id"])
        if len(page.data) < page_size:
            break
        start += page_size
    all_cids = sorted(all_cids)
    logger.info("Found %d companies with dividend_history", len(all_cids))

    predicted_count = 0
    skipped_past = 0
    skipped_insufficient = 0
    errors = []

    for i, cid in enumerate(all_cids, 1):
        comp = (
            supabase.table("companies")
            .select("ticker_symbol")
            .eq("company_id", cid)
            .limit(1)
            .execute()
        )
        ticker = comp.data[0]["ticker_symbol"] if comp.data else "?"

        next_date = predict_next_ex_date(cid)
        if next_date is None:
            # Check if it was insufficient data or past prediction
            hist_count = (
                supabase.table("dividend_history")
                .select("dividend_id", count="exact")
                .eq("company_id", cid)
                .execute()
            )
            if hist_count.count < 4:
                skipped_insufficient += 1
                logger.debug("[%d/%d] %s (cid=%d): insufficient history (%d rows)", i, len(all_cids), ticker, cid, hist_count.count)
            else:
                skipped_past += 1
                logger.debug("[%d/%d] %s (cid=%d): predicted date is in the past (suspended/slow)", i, len(all_cids), ticker, cid)
            continue

        try:
            payload = {
                "company_id": cid,
                "data_source": "predicted",
                "ex_dividend_date": next_date.isoformat(),
                "trust_score": 0.50,
                "status": "predicted",
                "source_observed_at": "now",
                "updated_at": "now",
            }
            supabase.table("upcoming_dividend_events").upsert(
                payload,
                on_conflict="company_id,data_source",
            ).execute()
            predicted_count += 1
            logger.info("[%d/%d] %s (cid=%d): predicted %s", i, len(all_cids), ticker, cid, next_date)
        except Exception as e:
            errors.append((cid, ticker, str(e)))
            logger.error("[%d/%d] %s (cid=%d): FAILED — %s", i, len(all_cids), ticker, cid, e)

    logger.info("=" * 50)
    logger.info("Backfill complete")
    logger.info("  Predicted (upserted): %d", predicted_count)
    logger.info("  Skipped (past date):  %d", skipped_past)
    logger.info("  Skipped (< 4 rows):   %d", skipped_insufficient)
    logger.info("  Errors:               %d", len(errors))
    if errors:
        for cid, ticker, err in errors:
            logger.error("  Error: %s (cid=%d): %s", ticker, cid, err)


if __name__ == "__main__":
    main()
