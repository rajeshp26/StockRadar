"""
Integration test: price_history daily-density contract of
MarketDataRefreshScheduler._upsert_daily_price_history.

Regression guard for the monthly-EOM compression defect (61/193 companies had
exactly one price_history row per month; the 2024-12-31 / 2025-03-31 account
value dips are a downstream artifact of that storage shape).

The canonical write path must store ONE row per provider-reported trading day:

  * bootstrap  (no existing rows): write the full retained daily history
  * incremental (rows exist):      write the recent window's daily rows, which
                                    supersede any seeded monthly-EOM row at the
                                    same (company_id, price_date) PK

Requires a real Supabase connection and real provider access (yfinance /
defeatbeta). No mocks are used anywhere in the chain:
MarketDataRefreshScheduler() default-constructs the real SupabaseFinancialRepository
and the real DI provider singletons.

Run with:
    RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_price_history_daily_density_integration.py -v

The test creates and cleans up real rows (throwaway company; price_history and
data_conflicts rows are deleted explicitly, company deleted last).
"""

import os
import uuid
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run against real Supabase",
)

# Symbol + unique exchange suffix so UNIQUE(ticker_symbol, exchange) never
# collides with the real AAPL/NMS row. The provider resolves an unknown
# exchange to the bare symbol, so real AAPL data is fetched.
TICKER = "AAPL"


def _create_company():
    """Insert a throwaway company; returns (company_id, ticker, exchange)."""
    from database import supabase

    suffix = uuid.uuid4().hex[:8]
    exchange = f"ZZTEST-{suffix}"
    ins = supabase.table("companies").insert({
        "ticker_symbol": TICKER,
        "company_name": f"Integration Test {suffix}",
        "exchange": exchange,
        "currency": "USD",
        "security_type": "stock",
    }).execute()
    company_id = ins.data[0]["company_id"]
    return company_id, TICKER, exchange


def _fetch_price_rows(company_id: int) -> list[dict]:
    """Read back ALL stored price_history rows for a company."""
    from database import supabase
    resp = supabase.table("price_history").select(
        "price_date, open_price, high_price, low_price, close_price, volume, data_source"
    ).eq("company_id", company_id).limit(5000).execute()
    return resp.data or []


def _cleanup_company(company_id: int):
    """Delete child rows first, then the company (guarded; idempotent)."""
    from contextlib import suppress

    from database import supabase

    for table in ("data_conflicts", "price_history"):
        with suppress(Exception):
            supabase.table(table).delete().eq("company_id", company_id).execute()
    with suppress(Exception):
        supabase.table("companies").delete().eq("company_id", company_id).execute()


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


class TestBootstrapDailyDensity:
    """Bootstrap path: a fresh company must get full daily-grain history."""

    async def test_bootstrap_writes_daily_rows_not_monthly_rows(self):
        company_id, ticker, exchange = _create_company()
        try:
            from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler

            scheduler = MarketDataRefreshScheduler()  # real repo + real DI providers
            written = await scheduler._upsert_daily_price_history(ticker, company_id, exchange=exchange)
            assert written > 0, "bootstrap path must write at least one daily row"

            rows = _fetch_price_rows(company_id)
            assert len(rows) >= 50, f"expected a multi-year daily history for {ticker}, got {len(rows)} rows"

            months: dict[tuple[int, int], int] = {}
            for r in rows:
                d = _to_date(r["price_date"])
                months[(d.year, d.month)] = months.get((d.year, d.month), 0) + 1

            assert len(months) >= 3, f"expected history spanning >= 3 months, got {len(months)}"
            # One row per trading day: total rows must be a large multiple of
            # the distinct month count. Monthly-EOM storage would give rows == months.
            assert len(rows) >= 5 * len(months), (
                f"daily-grain contract violated: {len(rows)} rows across {len(months)} months "
                f"(monthly-EOM would be ~1 row/month)"
            )
            # No row may carry the defect marker.
            assert all((r.get("data_source") or "") != "monthly-eom" for r in rows), (
                "bootstrap wrote a monthly-eom marked row"
            )
        finally:
            _cleanup_company(company_id)


class TestIncrementalSupersedesMonthlyEOM:
    """Incremental path: existing monthly-EOM rows are superseded by daily rows."""

    async def test_incremental_supersedes_seeded_monthly_eom_rows(self):
        company_id, ticker, exchange = _create_company()
        try:
            from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
            from database import supabase
            from dependencies import get_defeat_beta_provider
            from shared.time_utils import now_utc

            scheduler = MarketDataRefreshScheduler()  # real repo + real DI providers

            # The incremental window the scheduler will refresh (lookback 45d default).
            lookback = max(scheduler.lookback_days, 40)
            window_cutoff = now_utc().date() - timedelta(days=lookback)

            # Fetch the provider's OWN recent rows (real data) so the seeded
            # month-end dates are guaranteed trading days inside the window.
            provider = get_defeat_beta_provider()
            recent = await provider.get_price_history_optimized(
                ticker, company_id,
                start_date=window_cutoff - timedelta(days=40),
                exchange=exchange,
            )
            assert recent, "provider returned no recent rows; cannot seed monthly-EOM state"

            # Month-end trading day per month, restricted to dates strictly
            # inside the incremental window (a date exactly at the cutoff may
            # not be re-fetched, which would leave the seeded row untouched).
            month_ends: dict[tuple[int, int], dict] = {}
            for r in recent:
                d = _to_date(r["price_date"])
                if d <= window_cutoff:
                    continue
                key = (d.year, d.month)
                if key not in month_ends or d > _to_date(month_ends[key]["price_date"]):
                    month_ends[key] = r
            seeds = sorted(month_ends.values(), key=lambda r: _to_date(r["price_date"]))[-2:]
            assert seeds, "no month-end trading day strictly inside the refresh window"

            # Seed the defect state: exactly ONE monthly-EOM row per month,
            # carrying the marker the old compressors wrote. Values are coerced
            # to JSON-safe types (the provider may return Decimal) — the
            # canonical write path sanitizes; this seeding simulates what the
            # old compressors actually stored.
            def _json_safe(value, cast):
                return None if value is None else cast(value)

            for seed in seeds:
                supabase.table("price_history").insert({
                    "company_id": company_id,
                    "price_date": _to_date(seed["price_date"]).isoformat(),
                    "open_price": _json_safe(seed["open_price"], float),
                    "high_price": _json_safe(seed["high_price"], float),
                    "low_price": _json_safe(seed["low_price"], float),
                    "close_price": _json_safe(seed["close_price"], float),
                    "volume": _json_safe(seed["volume"], int),
                    "data_source": "monthly-eom",
                }).execute()

            seeded_dates = {_to_date(s["price_date"]) for s in seeds}

            written = await scheduler._upsert_daily_price_history(ticker, company_id, exchange=exchange)
            assert written > 0, "incremental path must write recent daily rows"

            rows = _fetch_price_rows(company_id)
            by_date = {_to_date(r["price_date"]): r for r in rows}

            # Every seeded monthly-EOM row must have been superseded by the real
            # daily row at the same PK (same date, different data_source).
            for sd in seeded_dates:
                assert sd in by_date, f"seeded month-end {sd} missing after refresh"
                assert (by_date[sd].get("data_source") or "") != "monthly-eom", (
                    f"seeded monthly-eom row at {sd} was NOT superseded by the daily row"
                )

            # Each seeded month must now hold multiple daily rows (>= 3), i.e.
            # the month is no longer 1-row monthly-EOM.
            for key in {(_to_date(s["price_date"]).year, _to_date(s["price_date"]).month) for s in seeds}:
                month_count = sum(
                    1 for r in rows
                    if (_to_date(r["price_date"]).year, _to_date(r["price_date"]).month) == key
                )
                assert month_count >= 3, f"month {key} still monthly-grain after refresh ({month_count} rows)"

            # The window as a whole must be daily-dense, not 1-row-per-month.
            assert len(rows) > len(seeded_dates), (
                "refresh wrote no extra daily rows beyond the seeded month-ends"
            )
        finally:
            _cleanup_company(company_id)
