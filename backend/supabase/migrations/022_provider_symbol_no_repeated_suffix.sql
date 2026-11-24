-- 022_provider_symbol_no_repeated_suffix.sql
-- Migration: make a doubled exchange suffix in securities.provider_symbol
-- unrepresentable, so reseeding or replaying migration 020 cannot revive the
-- yfinance 404 defect (T.TO.TO -> "Quote not found for symbol: T.TO.TO").
--
-- WHY A CONSTRAINT, NOT ONLY A TEST
--   Migration 021 repaired the seven rows that existed at the time. A test can
--   observe today's rows; only a schema constraint protects every future write.
--   A reader-side guard (domain.listing_identity.normalize_provider_symbol)
--   is still required for rows from an environment that has not applied this
--   migration, but the catalog itself must reject the invalid value.
--
-- RULE
--   Reject only an *identical repeated* trailing suffix (.TO.TO, .NE.NE,
--   .V.V, and longer repeats). Genuine dotted tickers such as BRK.B and
--   cross-exchange symbols such as ABC.TO.V are valid and remain allowed.
--
-- SAFETY / ROLLBACK
--   This is an additive CHECK constraint. It was rehearsed inside a
--   transaction with a seeded T.TO.TO value (rejected), then rolled back,
--   before being applied. To roll back the committed change run:
--     ALTER TABLE public.securities
--       DROP CONSTRAINT IF EXISTS ck_securities_provider_symbol_single_suffix;

DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.securities'::regclass
          AND conname = 'ck_securities_provider_symbol_single_suffix'
    ) THEN
        ALTER TABLE public.securities
            ADD CONSTRAINT ck_securities_provider_symbol_single_suffix
            CHECK (
                provider_symbol IS NULL
                OR provider_symbol !~* '(\.TO|\.NE|\.V)\1+$'
            );
    END IF;
END
$guard$;

COMMENT ON CONSTRAINT ck_securities_provider_symbol_single_suffix
    ON public.securities IS
    'Rejects a repeated trailing exchange suffix in a yfinance provider symbol; see migrations 020/021 and domain.listing_identity.normalize_provider_symbol.';
