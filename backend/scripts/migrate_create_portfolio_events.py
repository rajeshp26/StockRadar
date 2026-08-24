"""
Migration: Create portfolio_events, security_master, and fx_rate_history tables.

Steps:
1. CREATE TABLE portfolio_events + indices
2. CREATE TABLE security_master + indices
3. CREATE TABLE fx_rate_history + index
"""

import logging
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger("migrate")

# Each statement should be self-contained (no dependencies on prior statements in the same call)
STATEMENTS: list[str] = [
    # portfolio_events table
    """CREATE TABLE IF NOT EXISTS public.portfolio_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    event_version INT NOT NULL DEFAULT 1,
    aggregate_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);""",

    # portfolio_events indices
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_events_idempotency
    ON public.portfolio_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;""",

    "CREATE INDEX IF NOT EXISTS idx_portfolio_events_aggregate ON public.portfolio_events (aggregate_type, aggregate_id);",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_events_created ON public.portfolio_events (created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_events_type ON public.portfolio_events (event_type);",

    # security_master table
    """CREATE TABLE IF NOT EXISTS public.security_master (
    company_id INT PRIMARY KEY REFERENCES public.companies(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    isin TEXT,
    cusip TEXT,
    sedol TEXT,
    exchange TEXT,
    asset_class TEXT DEFAULT 'equity',
    currency TEXT DEFAULT 'USD',
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);""",

    "CREATE INDEX IF NOT EXISTS idx_security_master_symbol ON public.security_master (symbol);",

    # fx_rate_history table
    """CREATE TABLE IF NOT EXISTS public.fx_rate_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_currency TEXT NOT NULL,
    to_currency TEXT NOT NULL,
    rate_date DATE NOT NULL,
    rate NUMERIC(20, 10) NOT NULL,
    source TEXT DEFAULT 'yfinance',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (from_currency, to_currency, rate_date)
);""",
]


def _try_rpc(sql: str) -> bool:
    try:
        supabase.rpc("exec_sql", {"sql": sql}).execute()
        return True
    except Exception:
        pass
    try:
        supabase.rpc("exec_sql", {"query": sql}).execute()
        return True
    except Exception:
        pass
    try:
        supabase.postgrest.rpc("exec_sql", params={"sql": sql}).execute()
        return True
    except Exception:
        pass
    return False


def main():
    logger.info("=" * 60)
    logger.info("MIGRATION: create portfolio_events, security_master, fx_rate_history")
    logger.info("=" * 60)

    success = 0
    failed = 0
    for i, sql in enumerate(STATEMENTS, 1):
        label = sql.strip().split("\n")[0].strip().rstrip(";").strip()
        if _try_rpc(sql):
            logger.info("  ✓ [%d/%d] %s", i, len(STATEMENTS), label)
            success += 1
        else:
            logger.warning("  ✗ [%d/%d] %s — RPC failed", i, len(STATEMENTS), label)
            failed += 1
            logger.info("    Run manually:\n%s", sql[:200])

    logger.info("=" * 60)
    logger.info("Result: %d succeeded, %d failed", success, failed)
    if failed == 0:
        logger.info("Migration complete — all tables created.")
    else:
        logger.info("Run failed statements manually via Supabase SQL editor.")


if __name__ == "__main__":
    main()
