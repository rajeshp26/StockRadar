-- 015_create_benchmark_series.sql
-- Migration: Materialised benchmark comparison series (append-only read model).
--
-- WHY THIS EXISTS
--   /portfolio/performance/compare (and its holding twin) simulated the
--   benchmark from inception on EVERY request. The simulation is deterministic
--   for any date whose inputs have not changed, so recomputing it per timeline
--   selection was pure waste: selecting a different period rebuilt the same
--   series and only the visible window changed. This table stores the series
--   once and lets a period read be a slice.
--
--   The economic shape is append-only: the value on date D changes ONLY when
--   (a) a price row for D arrives or is corrected, (b) a transaction with a
--   backdated date is imported, or (c) an earlier transaction moves inception.
--   Absent those three, past values are immutable and there is nothing to
--   recompute. That is what makes this a safe read model rather than a cache
--   that can silently go stale -- see the fingerprint columns below.
--
-- SEMANTICS
--   account_key     sorted, comma-joined account ids for the portfolio path,
--                   or 'holding:<SYMBOL>' for the per-holding path. It is the
--                   identity of the account set the series was built for.
--   symbol          benchmark ticker (SPY, QQQ, ...).
--   series_date     the date of one simulated point.
--   value           simulated dollars for that date (shares * price).
--   inception_date  the earliest date the simulation started from. Stored so a
--                   later import that moves inception is detected.
--   initial_value   the seed (portfolio/holding value at the first non-zero
--                   inception snapshot). Stored so a seed change is detected.
--   fingerprint     SHA-256 (32 hex chars) over the exact inputs that produce
--                   the whole series: account_key, symbol, inception_date,
--                   initial_value, the ordered cash-flow list, and the count
--                   of price rows up to the mark date. A mismatch means the
--                   series must be rebuilt -- never served.
--   computed_at     Gate-1 timestamp: when this series was last built.
--   last_mark_date  the latest date this build covered. Rows before it are
--                   frozen; only dates after it are recomputed on the next run.
--
-- IDEMPOTENT
--   CREATE TABLE/INDEX IF NOT EXISTS; safe to re-run.
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS benchmark_series CASCADE;

BEGIN;

CREATE TABLE IF NOT EXISTS benchmark_series (
    id              BIGSERIAL PRIMARY KEY,
    account_key     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    series_date     DATE NOT NULL,
    value           NUMERIC(18, 4) NOT NULL,
    inception_date  DATE NOT NULL,
    initial_value   NUMERIC(18, 4) NOT NULL,
    fingerprint     TEXT NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_mark_date  DATE NOT NULL,
    CONSTRAINT unique_benchmark_series_point
        UNIQUE (account_key, symbol, series_date)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_series_lookup
    ON benchmark_series (account_key, symbol, series_date);

COMMENT ON TABLE benchmark_series IS
    'Materialised same-cash-flows benchmark series; one row per (account set, symbol, date). Sliced by period on read, rebuilt only when the input fingerprint changes.';
COMMENT ON COLUMN benchmark_series.account_key IS
    'Sorted comma-joined account ids (portfolio path) or ''holding:<SYMBOL>'' (holding path).';
COMMENT ON COLUMN benchmark_series.fingerprint IS
    'SHA-256(32) over account_key, symbol, inception, seed, ordered cash flows and price-row count. Mismatch => rebuild, never serve.';
COMMENT ON COLUMN benchmark_series.last_mark_date IS
    'Latest date covered by this build; earlier rows are frozen and only the tail is recomputed next run.';

-- RLS: service_role writes, authenticated reads (same convention as 008).
ALTER TABLE benchmark_series ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY has no IF NOT EXISTS in Postgres, so a bare CREATE POLICY makes
-- this migration fail on re-run (verified: DuplicateObject on the second apply).
-- DROP-then-CREATE guarded by a catalog check keeps the migration idempotent.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'benchmark_series'
          AND policyname = 'authenticated can read benchmark_series'
    ) THEN
        CREATE POLICY "authenticated can read benchmark_series"
            ON benchmark_series FOR SELECT
            USING (auth.role() IN ('authenticated', 'service_role'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'benchmark_series'
          AND policyname = 'service_role can insert benchmark_series'
    ) THEN
        CREATE POLICY "service_role can insert benchmark_series"
            ON benchmark_series FOR INSERT
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'benchmark_series'
          AND policyname = 'service_role can update benchmark_series'
    ) THEN
        CREATE POLICY "service_role can update benchmark_series"
            ON benchmark_series FOR UPDATE
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'benchmark_series'
          AND policyname = 'service_role can delete benchmark_series'
    ) THEN
        CREATE POLICY "service_role can delete benchmark_series"
            ON benchmark_series FOR DELETE
            USING (auth.role() = 'service_role');
    END IF;
END
$$;

-- Role grants: PostgREST/service_role needs table AND sequence privileges
-- (RLS alone is not sufficient - 42501 discovered by live E2E verification).
GRANT SELECT, INSERT, UPDATE, DELETE ON public.benchmark_series TO service_role;
GRANT SELECT ON public.benchmark_series TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.benchmark_series_id_seq TO service_role;

COMMIT;
