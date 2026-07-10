-- Price Ingestion Pipeline Tables
-- Run this on your Supabase database before deploying the new code.

CREATE TABLE IF NOT EXISTS price_sources (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    exchange        TEXT NOT NULL,
    price           NUMERIC(12, 4),
    currency        TEXT NOT NULL DEFAULT 'USD',
    source          TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ttl_seconds     INTEGER NOT NULL DEFAULT 300,
    data_quality    TEXT NOT NULL DEFAULT 'OK',
    UNIQUE (company_id, exchange)
);

CREATE INDEX IF NOT EXISTS idx_price_sources_company_exchange
    ON price_sources (company_id, exchange);

ALTER TABLE price_sources ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS price_source_preferences (
    id               BIGSERIAL PRIMARY KEY,
    company_id       INTEGER NOT NULL REFERENCES companies(company_id),
    exchange         TEXT NOT NULL,
    preferred_source TEXT NOT NULL,
    UNIQUE (company_id, exchange)
);

ALTER TABLE price_source_preferences ENABLE ROW LEVEL SECURITY;

-- Migrate existing current_market_data rows into price_sources
INSERT INTO price_sources (company_id, exchange, price, currency, source, fetched_at, ttl_seconds, data_quality)
SELECT cm.company_id, 'UNKNOWN', cm.current_price, 'USD', 'supabase_market_data', NOW(), 300, 'OK'
FROM current_market_data cm
ON CONFLICT (company_id, exchange) DO NOTHING;

-- Seed price_source_preferences for TOR-listed CDRs: yfinance
INSERT INTO price_source_preferences (company_id, exchange, preferred_source)
SELECT DISTINCT h.company_id, 'TOR', 'yfinance_tor'
FROM portfolio_holdings h
WHERE h.exchange_override = 'TOR'
  AND h.company_id IS NOT NULL
ON CONFLICT (company_id, exchange) DO NOTHING;

-- Seed price_source_preferences for US-listed holdings: supabase market data
INSERT INTO price_source_preferences (company_id, exchange, preferred_source)
SELECT DISTINCT c.company_id, c.exchange, 'supabase_market_data'
FROM companies c
JOIN portfolio_holdings h ON c.company_id = h.company_id
WHERE (h.exchange_override IS NULL OR h.exchange_override = '')
  AND c.exchange IN ('NMS', 'NYQ')
ON CONFLICT (company_id, exchange) DO NOTHING;

-- Seed price_source_preferences for unknown exchanges: price_history fallback
INSERT INTO price_source_preferences (company_id, exchange, preferred_source)
SELECT DISTINCT h.company_id, 'UNKNOWN', 'price_history_fallback'
FROM portfolio_holdings h
LEFT JOIN companies c ON h.company_id = c.company_id
WHERE c.company_id IS NULL
   OR c.exchange IS NULL
   OR c.exchange NOT IN ('NMS', 'NYQ', 'TOR')
ON CONFLICT (company_id, exchange) DO NOTHING;

-- ROLLBACK:
-- DROP TABLE IF EXISTS price_source_preferences CASCADE;
-- DROP TABLE IF EXISTS price_sources CASCADE;
