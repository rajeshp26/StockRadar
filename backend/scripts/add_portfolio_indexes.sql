-- backend/scripts/add_portfolio_indexes.sql
-- The ONLY missing index for portfolio query performance.
-- All other originally-proposed indexes already exist as PKs or unique constraints.
-- CONCURRENTLY prevents table locks — safe for production.

-- Dividends: compound filter on (account_id, fiscal_year) in the N+1 batch query.
--    Used by: get_user_portfolio_overview(), dividend dashboard endpoints.
--    Without this: sequential scan on portfolio_dividends for every overview load.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_dividends_account_year
    ON portfolio_dividends (account_id, fiscal_year);

-- Rollback (if write performance degrades):
-- DROP INDEX IF EXISTS idx_portfolio_dividends_account_year;
