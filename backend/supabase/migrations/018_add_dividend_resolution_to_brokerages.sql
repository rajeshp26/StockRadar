-- 018_add_dividend_resolution_to_brokerages.sql
-- Migration: Add dividend data resolution metadata to brokerages.
--
-- WHY THIS EXISTS
--   Different brokerages provide dividend data at different granularities.
--   Wealthsimple provides dividend information at monthly/statement level
--   (as exported via CSV), so we need to track and surface this limitation
--   to users. Other providers may provide daily resolution.
--
-- IDEMPOTENT
--   All operations use IF NOT EXISTS / safe updates.

ALTER TABLE public.portfolio_brokerages
  ADD COLUMN IF NOT EXISTS dividend_resolution VARCHAR(16) NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS dividend_resolution_note TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_portfolio_brokerages_dividend_resolution'
  ) THEN
    ALTER TABLE public.portfolio_brokerages
      ADD CONSTRAINT chk_portfolio_brokerages_dividend_resolution
        CHECK (dividend_resolution IN ('daily','weekly','monthly','quarterly','unknown'));
  END IF;
END $$;

-- Set Wealthsimple to monthly resolution (data provided at monthly/statement level)
UPDATE public.portfolio_brokerages
SET
  dividend_resolution = 'monthly',
  dividend_resolution_note = 'Dividend data from Wealthsimple is provided at monthly/statement level in the exported CSV. Per-day cash flow breakdown is not available from this feed, so values shown are aggregated to the available resolution.'
WHERE lower(brokerage_code) = 'wealthsimple'
  AND dividend_resolution = 'unknown';

COMMENT ON COLUMN public.portfolio_brokerages.dividend_resolution IS 'Minimum/available granularity of dividend cash flow data from this brokerage feed (daily/weekly/monthly/quarterly/unknown)';
COMMENT ON COLUMN public.portfolio_brokerages.dividend_resolution_note IS 'Human-readable explanation shown in UI when this source is active';
