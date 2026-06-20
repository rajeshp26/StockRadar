-- ============================================================================
-- Migration: upcoming_dividend_events
-- 
-- Creates a separate table for forward-looking dividend predictions.
-- dividend_history remains strictly historical — every row is a fact.
-- 
-- Each source (yfinance, finviz, predicted) has exactly one current opinion
-- per company.  When a provider updates its prediction, the existing row
-- is replaced (not duplicated) via UNIQUE(company_id, data_source).
-- 
-- See docs/Dividend_Data_Pipeline_Design.md §7.3 Step 4 for full design.
-- ============================================================================

-- Drop if re-running (safe for idempotent dev migrations)
DROP TABLE IF EXISTS upcoming_dividend_events CASCADE;

CREATE TABLE upcoming_dividend_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    data_source VARCHAR(50) NOT NULL,
    ex_dividend_date DATE NOT NULL,
    trust_score DECIMAL(3,2) NOT NULL DEFAULT 0.0,
    status VARCHAR(20) NOT NULL DEFAULT 'predicted'
        CHECK (status IN ('predicted', 'provider_reported')),
    source_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Each source has exactly one opinion per company
    CONSTRAINT unique_source_opinion UNIQUE (company_id, data_source)
);

CREATE INDEX idx_upcoming_events_company ON upcoming_dividend_events(company_id);
CREATE INDEX idx_upcoming_events_date ON upcoming_dividend_events(ex_dividend_date);

COMMENT ON TABLE upcoming_dividend_events IS
    'Forward-looking ex-dividend dates from providers (yfinance, finviz) and predictions. '
    'Separate from dividend_history to prevent metrics pollution. '
    'UNIQUE(company_id, data_source) ensures each source has exactly one current opinion.';

COMMENT ON COLUMN upcoming_dividend_events.trust_score IS
    'Heuristic ranking: yfinance=0.95, finviz=0.80, predicted=0.50. '
    'Not a calibrated probability — used for source selection ORDER BY.';

COMMENT ON COLUMN upcoming_dividend_events.status IS
    '''provider_reported'' = confirmed by a data source, '
    '''predicted'' = algorithmically estimated from historical pattern.';
