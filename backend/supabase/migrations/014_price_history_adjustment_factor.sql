-- 014_price_history_adjustment_factor.sql
-- Migration: Add split-adjustment columns to price_history.
--
-- WHY THIS EXISTS
--   price_history.close_price is a scale hybrid: every row froze the scale
--   yfinance served on the day it was written, and yfinance restates its whole
--   series on each new split while old DB rows are never rewritten. Measured on
--   the local database (2026-09-30, canonical venv probe):
--     - TNXP  (cid 3112) rows span 1,459,200,000.0000 (2016-08-31) .. 9.745
--     - NFLX  (cid 424)  stored == provider raw (stored/raw = 1.0000)
--     - GIS   (cid 62)   legacy rows are ADJUSTED scale (stored/yf_adj = 1.0000,
--                        raw ~2.3x higher)
--   The professional model (Bloomberg/FactSet/S&P convention) stores raw prices
--   plus an adjustment factor; adjusted = raw x factor. Design locked in
--   docs/price-history-professional-model.md (D1-D8).
--
-- SEMANTICS
--   adjustment_factor(d) = PI(1 / parse_split_factor(s)) for all splits s with
--   s.report_date > d (= PI(from/to); parse returns to/from, so 3:1 -> 1/3 and
--   1:100 -> 100). adj_close(d) = close_price(d) x adjustment_factor(d).
--   The provider (yfinance auto_adjust=False, DefeatBeta fallback) serves Yahoo's
--   split-restated series, so the write path must first RECOVER true raw:
--   raw(d) = served(d) x PI(parse_split_factor(s) over later splits), store that
--   as close_price, then materialise factor + adj_close. Verified by
--   scripts/probe_factor_direction.py (NFLX 2015-07-14: served 10.0371 x 70 =
--   702.60 true raw; TNXP 2025-01-27: served 41.00 x 0.01 = 0.41; GIS 2010-06-01:
--   served 36.00 x 2 = 72.00). adj_close telescopes to the served series:
--   raw(d) x factor(d) = served(d). Both are write-time materialised by
--   financial_repository.upsert_price_history from the owned `splits` calendar
--   (the same calendar the replay engine uses on the quantity side), so the
--   single write choke point keeps old and new rows consistent. NULL while a
--   row has not been re-written; readers coalesce to close_price (see design D7).
--
-- IDEMPOTENT
--   ADD COLUMN IF NOT EXISTS; safe to re-run.

BEGIN;

ALTER TABLE price_history
    ADD COLUMN IF NOT EXISTS adjustment_factor NUMERIC(20, 15) NULL,
    ADD COLUMN IF NOT EXISTS adj_close           NUMERIC(16, 4)  NULL;

COMMENT ON COLUMN price_history.adjustment_factor IS
    'Multiplier converting this row''s raw close_price to the current share-count scale: product of split factors for all splits with report_date > price_date. NULL until the row is re-written by the fixed pipeline (014).';

COMMENT ON COLUMN price_history.adj_close IS
    'Materialised split-adjusted close = close_price x adjustment_factor. NULL until the row is re-written by the fixed pipeline (014); readers coalesce to close_price meanwhile.';

COMMIT;