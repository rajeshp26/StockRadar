-- Portfolio Snapshots Table for Performance Engine Re-engineering
-- Run this on your Supabase database before deploying the new code.

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    account_id          INTEGER NOT NULL REFERENCES portfolio_accounts(account_id) ON DELETE CASCADE,
    snapshot_date       DATE NOT NULL,
    total_value         NUMERIC(15, 2) NOT NULL,
    holdings_market_value NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    cost_basis          NUMERIC(15, 2) NOT NULL,
    cash_balance        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    net_deposits        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    holdings_json       JSONB,
    data_quality_flag   TEXT NOT NULL DEFAULT 'OK',
    job_id              TEXT,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_account_date
    ON portfolio_snapshots (account_id, snapshot_date DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_account_date_unique
    ON portfolio_snapshots (account_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_snapshots_quality
    ON portfolio_snapshots (data_quality_flag)
    WHERE data_quality_flag != 'OK';

ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;

-- Price history composite index: speeds up get_all_prices_historical queries
-- which filter by (company_id IN (?), price_date <= ?) and ORDER BY price_date DESC.
CREATE INDEX IF NOT EXISTS idx_price_history_company_date
    ON price_history (company_id, price_date DESC);

-- ROLLBACK:
-- DROP TABLE IF EXISTS portfolio_snapshots CASCADE;
-- DROP INDEX IF EXISTS idx_price_history_company_date;
