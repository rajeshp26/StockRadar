"""
StockerPro — Phase 7 spot-check script
Run after the backfill to verify critical fields are populated.

Usage:
  cd backend
  python scripts/spot_check.py --symbols MSFT,GOOGL,AAPL

Checks per company:
  - income_statements: non-empty, shares_outstanding_diluted populated, interest_income populated
  - balance_sheets: non-empty, shares_outstanding populated, invested_capital populated
  - cash_flow_statements: non-empty, cash_from_financing_activities populated
  - company_summary: row exists with shares_outstanding
  - valuation_runs: RI run exists with no earlyAbort flag
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("spot_check")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


def check(label: str, condition: bool, value=None) -> bool:
    icon = PASS if condition else FAIL
    detail = f"  → {value}" if value is not None else ""
    logger.info("  %s %s%s", icon, label, detail)
    return condition


async def spot_check_company(symbol: str) -> bool:
    logger.info("━━━ %s ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", symbol)
    all_ok = True

    # Resolve company_id
    co = supabase.table("companies") \
        .select("company_id, exchange") \
        .eq("ticker_symbol", symbol.upper()) \
        .limit(1).execute()
    if not co.data:
        logger.error("  %s company not found in DB", FAIL)
        return False
    company_id = co.data[0]["company_id"]
    logger.info("  company_id=%s", company_id)

    # ── income_statements ────────────────────────────────────────────────────
    is_rows = supabase.table("income_statements") \
        .select("fiscal_year, shares_outstanding_diluted, interest_income, "
                "effective_tax_rate, data_source") \
        .eq("company_id", company_id) \
        .is_("fiscal_quarter", "null") \
        .order("fiscal_year", desc=True) \
        .limit(5).execute().data or []

    ok = check("income_statements non-empty", len(is_rows) > 0, f"{len(is_rows)} annual rows")
    all_ok &= ok
    if is_rows:
        latest_is = is_rows[0]
        ok = check("  data_source = defeat_beta",
                   latest_is.get("data_source") == "defeat_beta",
                   latest_is.get("data_source"))
        all_ok &= ok
        ok = check("  shares_outstanding_diluted populated",
                   latest_is.get("shares_outstanding_diluted") is not None,
                   latest_is.get("shares_outstanding_diluted"))
        all_ok &= ok
        ok = check("  interest_income populated",
                   latest_is.get("interest_income") is not None,
                   latest_is.get("interest_income"))
        all_ok &= ok
        ok = check("  effective_tax_rate populated",
                   latest_is.get("effective_tax_rate") is not None,
                   latest_is.get("effective_tax_rate"))
        all_ok &= ok

    # ── balance_sheets ───────────────────────────────────────────────────────
    bs_rows = supabase.table("balance_sheets") \
        .select("fiscal_year, shares_outstanding, invested_capital, "
                "long_term_investments, data_source") \
        .eq("company_id", company_id) \
        .is_("fiscal_quarter", "null") \
        .order("fiscal_year", desc=True) \
        .limit(5).execute().data or []

    ok = check("balance_sheets non-empty", len(bs_rows) > 0, f"{len(bs_rows)} annual rows")
    all_ok &= ok
    if bs_rows:
        latest_bs = bs_rows[0]
        ok = check("  shares_outstanding populated",
                   latest_bs.get("shares_outstanding") is not None,
                   latest_bs.get("shares_outstanding"))
        all_ok &= ok
        ok = check("  invested_capital populated",
                   latest_bs.get("invested_capital") is not None,
                   latest_bs.get("invested_capital"))
        all_ok &= ok
        ok = check("  long_term_investments populated",
                   latest_bs.get("long_term_investments") is not None,
                   latest_bs.get("long_term_investments"))
        all_ok &= ok

    # ── cash_flow_statements ─────────────────────────────────────────────────
    cf_rows = supabase.table("cash_flow_statements") \
        .select("fiscal_year, cash_from_financing_activities, share_repurchases, "
                "asset_sales, data_source") \
        .eq("company_id", company_id) \
        .is_("fiscal_quarter", "null") \
        .order("fiscal_year", desc=True) \
        .limit(5).execute().data or []

    ok = check("cash_flow_statements non-empty", len(cf_rows) > 0, f"{len(cf_rows)} annual rows")
    all_ok &= ok
    if cf_rows:
        latest_cf = cf_rows[0]
        ok = check("  cash_from_financing_activities populated",
                   latest_cf.get("cash_from_financing_activities") is not None,
                   latest_cf.get("cash_from_financing_activities"))
        all_ok &= ok
        ok = check("  share_repurchases populated",
                   latest_cf.get("share_repurchases") is not None,
                   latest_cf.get("share_repurchases"))
        all_ok &= ok
        ok = check("  asset_sales populated",
                   latest_cf.get("asset_sales") is not None,
                   latest_cf.get("asset_sales"))
        all_ok &= ok

    # ── company_summary ──────────────────────────────────────────────────────
    summary = supabase.table("company_summary") \
        .select("shares_outstanding, snapshot_date") \
        .eq("company_id", company_id) \
        .order("snapshot_date", desc=True) \
        .limit(1).execute().data or []

    ok = check("company_summary exists", len(summary) > 0)
    all_ok &= ok
    if summary:
        ok = check("  shares_outstanding populated",
                   summary[0].get("shares_outstanding") is not None,
                   summary[0].get("shares_outstanding"))
        all_ok &= ok

    # ── RI valuation run ─────────────────────────────────────────────────────
    ri_runs = supabase.table("valuation_runs") \
        .select("output_snapshot, run_at") \
        .eq("company_id", company_id) \
        .eq("method", "residual_income") \
        .order("run_at", desc=True) \
        .limit(1).execute().data or []

    ok = check("RI valuation_run exists", len(ri_runs) > 0)
    all_ok &= ok
    if ri_runs:
        snap = ri_runs[0].get("output_snapshot") or {}
        early_abort = snap.get("earlyAbort", False)
        iv = (snap.get("valuation") or {}).get("intrinsicValuePerShare")
        ok = check("  RI no earlyAbort", not early_abort,
                   "ABORTED — shares still unavailable" if early_abort else "clean run")
        all_ok &= ok
        ok = check("  intrinsicValuePerShare populated", iv is not None, iv)
        all_ok &= ok

    logger.info("  %s %s overall: %s",
                PASS if all_ok else FAIL, symbol,
                "all checks passed" if all_ok else "FAILURES — review above")
    return all_ok


async def run(symbols: list[str]) -> None:
    results = []
    for symbol in symbols:
        ok = await spot_check_company(symbol)
        results.append((symbol, ok))

    logger.info("")
    logger.info("━━━ SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    all_passed = True
    for symbol, ok in results:
        icon = PASS if ok else FAIL
        logger.info("  %s %s", icon, symbol)
        all_passed &= ok
    logger.info("")

    if not all_passed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="StockerPro post-backfill spot check")
    parser.add_argument("--symbols", default="MSFT", help="Comma-separated ticker list")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    asyncio.run(run(symbols))


if __name__ == "__main__":
    main()