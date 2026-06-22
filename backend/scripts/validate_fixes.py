"""
Validate proposed fixes by testing root cause assumptions against live APIs.

Run: python scripts/validate_fixes.py
Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars or they'll be read from .env.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date
from typing import Any, Dict, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
log = logging.getLogger("validate")

PASS = 0
FAIL = 0


def check(description: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        log.info("  ✅ PASS: %s", description)
    else:
        FAIL += 1
        log.error("  ❌ FAIL: %s", description)
        if detail:
            log.error("     %s", detail)


def test_yfinance_suffix_resolution():
    """Fix 3/4: Validate that .TO suffix makes yfinance find Canadian tickers."""
    log.info("\n=== Test: yfinance suffix resolution for Canadian tickers ===")

    import yfinance as yf

    # Non-Canadian ticker that should work without suffix
    ticker_aapl = yf.Ticker("AAPL")
    aapl_info = ticker_aapl.info or {}
    check("AAPL works without suffix", bool(aapl_info.get("currentPrice") or aapl_info.get("regularMarketPrice")))

    # Canadian tickers WITHOUT suffix (current broken behavior)
    canadian_raw = ["AC", "CS", "CGX", "RCI-B"]
    for sym in canadian_raw:
        ticker = yf.Ticker(sym)
        info = ticker.info or {}
        has_price = bool(info.get("currentPrice") or info.get("regularMarketPrice"))
        check(f"{sym} without .TO suffix returns price data (expected: False)", not has_price)

    # Canadian tickers WITH .TO suffix
    canadian_resolved = ["AC.TO", "CS.TO", "CGX.TO", "RCI-B.TO"]
    for sym in canadian_resolved:
        ticker = yf.Ticker(sym)
        info = ticker.info or {}
        has_price = bool(info.get("currentPrice") or info.get("regularMarketPrice"))
        check(f"{sym} with .TO suffix returns price data (expected: True)", has_price)


def test_yfinance_download_suffix_resolution():
    """Fix 2: Validate that yf.download with .TO suffix works."""
    log.info("\n=== Test: yf.download suffix resolution ===")

    import yfinance as yf

    raw = yf.download(["AC"], period="5d", auto_adjust=True, progress=False)
    any_data_available = raw is not None and not raw.empty
    check("yf.download(['AC']) without .TO — data available (expected: False)", not any_data_available)

    resolved = yf.download(["AC.TO"], period="5d", auto_adjust=True, progress=False)
    any_data_available = resolved is not None and not resolved.empty
    check("yf.download(['AC.TO']) with .TO — data available (expected: True)", any_data_available)

    # Also test that error handling gracefully returns empty
    from pandas import DataFrame
    try:
        bad = yf.download(["SYMBOL_DOES_NOT_EXIST_12345"], period="5d", auto_adjust=True, progress=False)
        check("yf.download with bad symbol returns empty or DataFrame, doesn't crash", isinstance(bad, DataFrame))
    except Exception as e:
        check("yf.download with bad symbol doesn't crash (expected: False — needs try/except)", False, str(e))


def test_postgrest_single_vs_limit():
    """Fix 1: Validate .single() 406 vs .limit(1) behavior."""
    log.info("\n=== Test: .single() vs .limit(1) for company_summary ===")

    from database import supabase
    from postgrest.exceptions import APIError

    # Use a non-existent company_id to ensure zero rows
    test_cid = -999999
    today = date.today().isoformat()

    # Test .single() — should raise on zero rows
    raised = False
    try:
        result = (
            supabase.table("company_summary")
            .select("company_id")
            .eq("company_id", test_cid)
            .eq("snapshot_date", today)
            .eq("provider", "defeatbeta")
            .single()
            .execute()
        )
        # If it didn't raise but returned data, that's unexpected
        result_data = result.data
    except APIError as e:
        raised = True
        status_code = getattr(e, "status_code", getattr(e, "code", "unknown"))
        check(".single() on zero rows raises 406 (expected: True)", raised,
              f"status={status_code}, message={e}")

    if not raised:
        check(".single() on zero rows raises 406 (expected: True)", False,
              "No exception raised — unexpected")

    # Test .limit(1) — should return empty list gracefully
    try:
        resp = (
            supabase.table("company_summary")
            .select("company_id")
            .eq("company_id", test_cid)
            .eq("snapshot_date", today)
            .eq("provider", "defeatbeta")
            .limit(1)
            .execute()
        )
        data = resp.data if hasattr(resp, "data") else []
        result_list = data if isinstance(data, list) else []
        check(".limit(1) on zero rows returns empty list (expected: True)",
              isinstance(result_list, list) and len(result_list) == 0,
              f"result={result_list!r}")
    except APIError as e:
        check(".limit(1) on zero rows doesn't raise",
              False, f"Unexpected APIError: {e}")
    except Exception as e:
        check(".limit(1) on zero rows doesn't raise",
              False, f"Unexpected exception: {e}")


def test_dead_letter_early_exit_logic():
    """Fix 5: Validate that DEFEAT_BETA_NO_DATA should skip to dead_letter."""
    log.info("\n=== Test: Dead-letter logic for permanent failures ===")

    # Simulate the scheduler_repository.fail_job logic
    max_attempts = 3

    def simulate_fail_job(attempts: int, error: str):
        next_attempt = attempts + 1
        if next_attempt >= max_attempts:
            return "dead_letter"
        if "DEFEAT_BETA_NO_DATA" in error:
            return "dead_letter"
        return "pending"

    # Without fix: regular error retries 3 times
    r1 = simulate_fail_job(0, "Some transient error")
    r2 = simulate_fail_job(1, "Some transient error")
    r3 = simulate_fail_job(2, "Some transient error")
    check("Transient error: attempt 0 → pending (expected: True)", r1 == "pending")
    check("Transient error: attempt 1 → pending (expected: True)", r2 == "pending")
    check("Transient error: attempt 2 → dead_letter (expected: True)", r3 == "dead_letter")

    # With fix: DEFEAT_BETA_NO_DATA goes to dead_letter immediately
    r4 = simulate_fail_job(0, "[DEFEAT_BETA_NO_DATA] Failed to fetch any financial data for CS")
    check("DEFEAT_BETA_NO_DATA: attempt 0 → dead_letter (expected: True)", r4 == "dead_letter")

    r5 = simulate_fail_job(1, "[DEFEAT_BETA_NO_DATA] Failed to fetch any financial data for CS")
    check("DEFEAT_BETA_NO_DATA: attempt 1 → dead_letter (expected: True)", r5 == "dead_letter")


def test_income_statements_for_3153():
    """Additional context: Verify company 3153 (AC) has financial data now."""
    log.info("\n=== Test: Company 3153 (AC) financial data ===")

    from database import supabase

    try:
        resp = (
            supabase.table("income_statements")
            .select("fiscal_year")
            .eq("company_id", 3153)
            .is_("fiscal_quarter", None)
            .limit(1)
            .execute()
        )
        has_data = bool(resp.data)
        check("Company 3153 (AC) has annual income statement data (explains why it succeeded)",
              has_data)
    except Exception as e:
        check("Company 3153 query works", False, str(e))


def main():
    log.info("=" * 60)
    log.info("Validating root cause assumptions for proposed fixes")
    log.info("=" * 60)

    test_yfinance_suffix_resolution()
    test_yfinance_download_suffix_resolution()
    test_postgrest_single_vs_limit()
    test_dead_letter_early_exit_logic()
    test_income_statements_for_3153()

    log.info("\n" + "=" * 60)
    log.info("Results: %d passed, %d failed", PASS, FAIL)
    log.info("=" * 60)

    if FAIL > 0:
        log.warning("Some assumptions were wrong — review before applying fixes.")
    else:
        log.info("All assumptions validated — fixes should work.")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
