"""
Migration: Add exchange_override to portfolio_holdings (Option B).

Steps:
1. ALTER TABLE portfolio_holdings ADD COLUMN exchange_override TEXT
2. Revert companies.exchange back to NMS for CDR mega-cap symbols
3. Re-fetch current_market_data with NMS (default) for those symbols
4. Backfill exchange_override = "TOR" on existing CDR holdings

CDR symbols (US mega-caps held as CDRs on TSX):
  AAPL, AMZN, DIS, GOOG, INTC, META, MSFT, NFLX, PYPL, TSLA
"""
import sys
import logging
import re as re_module
from pathlib import Path
from typing import List, Dict, Any

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from providers.yfinance_provider import YFinanceProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger("migrate")

CDR_SYMBOLS = ["AAPL", "AMZN", "DIS", "GOOG", "INTC", "META", "MSFT", "NFLX", "PYPL", "TSLA"]
provider = YFinanceProvider()


def step1_add_column():
    """Add exchange_override column to portfolio_holdings."""
    try:
        supabase.table("portfolio_holdings").select("exchange_override").limit(1).execute()
        logger.info("exchange_override column already exists")
        return True
    except Exception:
        pass

    try:
        sql = 'ALTER TABLE portfolio_holdings ADD COLUMN exchange_override TEXT'
        supabase.rpc("exec_sql", {"sql": sql}).execute()
        logger.info("✓ exchange_override column added")
    except Exception as e:
        logger.warning("RPC failed, trying raw SQL...")
        try:
            supabase.table("portfolio_holdings").update({"exchange_override": None}).eq("exchange_override", "__test__").execute()
        except Exception:
            pass

        _raw_sql(sql)
    return True


def _raw_sql(sql: str) -> None:
    """Execute raw SQL via Supabase REST API."""
    try:
        response = supabase.postgrest.rpc("exec_sql", params={"sql": sql}).execute()
        logger.info("SQL executed: %s", sql[:80])
    except Exception as e:
        logger.error("Failed to execute SQL: %s", e)
        logger.info("Run this SQL manually in Supabase SQL editor:\n  %s", sql)


def _try_rpc(sql: str) -> bool:
    try:
        supabase.rpc("exec_sql", {"query": sql}).execute()
        return True
    except Exception:
        pass
    try:
        supabase.rpc("exec_sql", {"sql": sql}).execute()
        return True
    except Exception:
        pass
    return False


def step1b_alter_table():
    """Add column via Supabase SQL if possible, or print instructions."""
    sql = "ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS exchange_override TEXT;"
    if _try_rpc(sql):
        logger.info("✓ Column added via RPC")
    else:
        logger.info("Could not add column automatically. Run this in Supabase SQL editor:")
        logger.info("  %s", sql)


def step2_revert_exchange():
    """Revert companies.exchange back to NMS/NYQ for CDR symbols."""
    for symbol in CDR_SYMBOLS:
        try:
            company = supabase.table("companies").select("company_id, exchange").eq("ticker_symbol", symbol).single().execute()
            if not company.data:
                logger.warning("  No company record for %s", symbol)
                continue
            old_exchange = company.data.get("exchange", "?")
            if old_exchange == "TOR":
                # Determine original exchange: NMS for NASDAQ, NYQ for NYSE
                sd = provider.get_stock_details(symbol)
                orig_exchange = sd.exchange if sd and sd.exchange else "NMS"
                supabase.table("companies").update({"exchange": orig_exchange}).eq("ticker_symbol", symbol).execute()
                logger.info("  %s: %s → %s", symbol, old_exchange, orig_exchange)
            else:
                logger.info("  %s: already %s (no change)", symbol, old_exchange)
        except Exception as e:
            logger.error("  %s: failed to revert — %s", symbol, e)


def step3_refetch_current_market_data():
    """Re-fetch current_market_data with NMS exchange for CDR symbols."""
    print()
    for symbol in CDR_SYMBOLS:
        try:
            company = supabase.table("companies").select("company_id, exchange").eq("ticker_symbol", symbol).single().execute()
            if not company.data:
                continue
            cid = company.data["company_id"]
            exchange = company.data.get("exchange", "NMS")

            # Fetch with default exchange (NMS/NYQ)
            sd = provider.get_stock_details(symbol, exchange=exchange)
            if sd and sd.price is not None:
                supabase.table("current_market_data").upsert(
                    {"company_id": cid, "current_price": sd.price},
                    on_conflict="company_id",
                ).execute()
                logger.info("  %s: current_market_data → $%.2f (%s)", symbol, sd.price, exchange)
            else:
                logger.warning("  %s: no price from YFinance with %s", symbol, exchange)
        except Exception as e:
            logger.error("  %s: failed — %s", symbol, e)


def step4_backfill_holding_override():
    """Set exchange_override = 'TOR' on holdings whose transactions had CDR in raw_data."""
    for symbol in CDR_SYMBOLS:
        try:
            company = supabase.table("companies").select("company_id").eq("ticker_symbol", symbol).single().execute()
            if not company.data:
                continue
            cid = company.data["company_id"]

            # Get all holdings for this company
            holdings = supabase.table("portfolio_holdings").select("*").eq("company_id", cid).execute()
            if not holdings.data:
                continue

            for holding in holdings.data:
                holding_id = holding.get("holding_id") or holding.get("id")
                account_id = holding.get("account_id")

                # Check transactions for this account + symbol for CDR in raw_data
                txs = supabase.table("portfolio_transactions").select("raw_data").eq("account_id", account_id).eq("symbol", symbol).limit(5).execute()
                is_cdr = False
                for tx in txs.data or []:
                    raw = tx.get("raw_data")
                    if isinstance(raw, dict):
                        raw_symbol = raw.get("symbol", "") or ""
                        raw_name = raw.get("name", "") or ""
                        if re_module.search(r"\bCDR\b", raw_symbol + " " + raw_name, re_module.IGNORECASE):
                            is_cdr = True
                            break

                if is_cdr:
                    supabase.table("portfolio_holdings").update({"exchange_override": "TOR"}).eq("company_id", cid).eq("account_id", account_id).execute()
                    logger.info("  %s (account %s): exchange_override = TOR", symbol, account_id)
        except Exception as e:
            logger.error("  %s: failed — %s", symbol, e)


def main():
    print("=" * 60)
    print("MIGRATION: exchange_override on portfolio_holdings")
    print("=" * 60)

    print("\n[1/5] Adding exchange_override column...")
    step1b_alter_table()

    print("\n[2/5] Reverting companies.exchange to NMS/NYQ...")
    step2_revert_exchange()

    print("\n[3/5] Re-fetching current_market_data with default exchange...")
    step3_refetch_current_market_data()

    print("\n[4/5] Backfilling exchange_override on existing CDR holdings...")
    step4_backfill_holding_override()

    print("\n[5/5] Verifying...")
    verify()

    print("\n" + "=" * 60)
    print("Migration complete.")
    print("=" * 60)


def verify():
    """Verify the migration."""
    for symbol in CDR_SYMBOLS:
        try:
            company = supabase.table("companies").select("company_id, ticker_symbol, exchange").eq("ticker_symbol", symbol).single().execute()
            if company.data:
                cid = company.data["company_id"]
                holdings = supabase.table("portfolio_holdings").select("account_id, exchange_override").eq("company_id", cid).execute()
                overrides = [h for h in holdings.data or [] if h.get("exchange_override")]
                logger.info("  %s: exchange=%s, holdings with override=%d", symbol, company.data["exchange"], len(overrides))
        except Exception as e:
            logger.warning("  %s: verify failed — %s", symbol, e)


if __name__ == "__main__":
    main()
