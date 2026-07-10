-- Phase 1: Event-sourced log for portfolio domain.
-- Run against Supabase SQL editor or via psql.

CREATE TABLE IF NOT EXISTS public.portfolio_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    event_version INT NOT NULL DEFAULT 1,
    aggregate_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint for idempotency (only non-null keys enforce uniqueness)
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_events_idempotency
    ON public.portfolio_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Lookup indices
CREATE INDEX IF NOT EXISTS idx_portfolio_events_aggregate
    ON public.portfolio_events (aggregate_type, aggregate_id);

CREATE INDEX IF NOT EXISTS idx_portfolio_events_created
    ON public.portfolio_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_portfolio_events_type
    ON public.portfolio_events (event_type);

-- security_master: canonical mapping between company_id and identifiers
CREATE TABLE IF NOT EXISTS public.security_master (
    company_id INT PRIMARY KEY REFERENCES public.companies(company_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    isin TEXT,
    cusip TEXT,
    sedol TEXT,
    exchange TEXT,
    asset_class TEXT DEFAULT 'equity',
    currency TEXT DEFAULT 'USD',
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_master_symbol
    ON public.security_master (symbol);

-- fx_rate_history: exchange rates for multi-currency support
CREATE TABLE IF NOT EXISTS public.fx_rate_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_currency TEXT NOT NULL,
    to_currency TEXT NOT NULL,
    rate_date DATE NOT NULL,
    rate NUMERIC(20, 10) NOT NULL,
    source TEXT DEFAULT 'yfinance',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (from_currency, to_currency, rate_date)
);

COMMENT ON TABLE public.portfolio_events IS 'Immutable event log for portfolio domain. Append-only.';
COMMENT ON TABLE public.security_master IS 'Canonical security identifiers. Single source of truth for company→symbol mapping.';
COMMENT ON TABLE public.fx_rate_history IS 'Daily exchange rates for multi-currency portfolio valuation.';
