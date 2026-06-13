-- backend/scripts/migrate_valuation_multiples.sql
--
-- Phase 9: Adds enterprise_value, EV/EBITDA, P/FCF, and market_cap columns
-- to financial_ratios for historical per-period valuation data.
-- Follows the same pattern as Phase 7's trailing_pe + quarter_end_price.
--
-- Re-run safe: ADD COLUMN IF NOT EXISTS + idempotent ALTER statements.

ALTER TABLE financial_ratios
  ADD COLUMN IF NOT EXISTS market_cap         NUMERIC(20,2),
  ADD COLUMN IF NOT EXISTS enterprise_value   NUMERIC(20,2),
  ADD COLUMN IF NOT EXISTS ev_ebitda          NUMERIC(20,4),
  ADD COLUMN IF NOT EXISTS price_to_fcf       NUMERIC(20,4);

-- Widen from any narrower precision that may have been applied earlier
ALTER TABLE financial_ratios ALTER COLUMN market_cap       TYPE NUMERIC(20,2);
ALTER TABLE financial_ratios ALTER COLUMN enterprise_value TYPE NUMERIC(20,2);
ALTER TABLE financial_ratios ALTER COLUMN ev_ebitda        TYPE NUMERIC(20,4);
ALTER TABLE financial_ratios ALTER COLUMN price_to_fcf     TYPE NUMERIC(20,4);

COMMENT ON COLUMN financial_ratios.market_cap IS 'Quarter-end market cap = shares_outstanding × quarter_end_price';
COMMENT ON COLUMN financial_ratios.enterprise_value IS 'Enterprise Value = market_cap + total_debt - cash_and_cash_equivalents';
COMMENT ON COLUMN financial_ratios.ev_ebitda IS 'EV / EBITDA (NULL when EBITDA <= 0)';
COMMENT ON COLUMN financial_ratios.price_to_fcf IS 'EV / Free Cash Flow (NULL when FCF <= 0)';
