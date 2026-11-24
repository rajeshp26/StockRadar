-- 021_repair_provider_symbol_suffixes.sql
-- Migration: repair doubled exchange suffixes in securities.provider_symbol.
--
-- WHY THIS EXISTS
--   Migration 020 built provider_symbol as `symbol || suffix` unconditionally.
--   Seven source tickers already carried a suffix (ENB.TO, YTSL.NE, ...), so
--   the stored value became ENB.TO.TO / YTSL.NE.NE. Yahoo returns HTTP 404
--   "Quote not found for symbol: ENB.TO.TO" on every price refresh.
--
-- RULE
--   Use the same idempotent expression as domain.listing_identity.provider_symbol_for:
--   an already-suffixed symbol is returned unchanged; only a plain ticker gets
--   an exchange suffix appended. Migration 020 remains untouched because it was
--   already applied; this is a forward, idempotent data repair.
--
-- SAFETY
--   * The predicate makes a second application a no-op.
--   * Only provider_symbol is written; security_id and every other identity
--     column are unchanged, so watchlist/portfolio foreign keys stay stable.
--   * uq_securities_listing is (symbol, exchange, kind, currency, provider_symbol).
--     The rollback-only probe found zero target-key collisions across 3162 rows;
--     a collision would abort the enclosing transaction rather than corrupt data.

UPDATE public.securities
SET provider_symbol = CASE
        WHEN position('.' in symbol) > 0 THEN symbol
        ELSE symbol || CASE exchange
            WHEN 'TSX' THEN '.TO'
            WHEN 'NEO' THEN '.NE'
            WHEN 'TSXV' THEN '.V'
            ELSE ''
        END
    END
WHERE provider_symbol IS DISTINCT FROM (
    CASE
        WHEN position('.' in symbol) > 0 THEN symbol
        ELSE symbol || CASE exchange
            WHEN 'TSX' THEN '.TO'
            WHEN 'NEO' THEN '.NE'
            WHEN 'TSXV' THEN '.V'
            ELSE ''
        END
    END
);

COMMENT ON COLUMN public.securities.provider_symbol IS 'Canonical yfinance symbol for this listing; exchange suffix is applied exactly once (see domain.listing_identity.provider_symbol_for).';
