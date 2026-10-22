-- 017_create_portfolio_value_series.sql
-- Migration: Materialised portfolio value series (append-only read model).
--
-- WHY THIS EXISTS
--   /portfolio/performance reads portfolio_snapshots to build the value curve.
--   After migration 016 the read no longer ships holdings_json, but the series
--   is still recomputed from raw snapshot rows on every period selection.
--
--   The curve is a deterministic, append-only function of the snapshots: the
--   value on date D changes ONLY when (a) a snapshot for D is written or
--   corrected, (b) a backdated transaction alters an earlier date, or (c) the
--   account set changes. Absent those, past points are immutable and a period
--   selection is a slice of stored data, not a recomputation.
--
--   This table stores one row per (account_key, series_date). A period read is
--   a range scan over int/date/numeric with no blob and no wide row, so it
--   cannot regress the way the snapshot read did.
--
-- SEMANTICS
--   account_key            sorted, comma-joined account ids. Identity of the
--                          account set the series was built for.
--   series_date            one date of the curve.
--   total_value            summed value across the accounts at that date.
--   holdings_market_value  summed holdings value.
--   cost_basis             summed cost basis.
--   cash_balance           summed cash.
--   net_deposits           cumulative external deposits (TWR input).
--   fx_unconverted_count   count of the underlying snapshot rows carrying an
--                          unconverted-FX holding. >0 marks the date as an FX
--                          artifact for smoothing, same meaning as 016.
--   points_used            how many account snapshots fed this date.
--   locf_filled            1 when at least one account was carried forward to
--                          this date (last observation carried forward), 0 for
--                          a fully-observed date. Stored per point so a served
--                          response reports the exact locf_count the live
--                          merge would, without re-deriving it per account.
--   spike_suppressed       1 when a spike step onto this date was suppressed
--                          as an fx/LOCF artifact during the merge. Same
--                          reason as locf_filled: the served response must
--                          report the exact spike_detected the live merge would.
--   fingerprint            SHA-256(32) over account_key plus the ordered
--                          per-account snapshot scalar rows the build was
--                          computed from (account_id, snapshot_date, every
--                          value column). This is an INPUT fingerprint, not a
--                          hash of the stored points: the request path already
--                          reads the snapshot scalars, so it can recompute the
--                          same hash and detect an appended, corrected or
--                          BACKDATED snapshot before serving. A mismatch means
--                          the inputs changed and the curve must be rebuilt -
--                          never served.
--   computed_at            when this series was last built.
--   last_mark_date         the resolved window end this build covered (the
--                          request path always builds inception -> now). Rows
--                          before it are frozen; a later request whose window
--                          has advanced sees series_ends_before until new
--                          snapshot inputs change the fingerprint.
--
-- IDEMPOTENT
--   CREATE TABLE/INDEX IF NOT EXISTS; safe to re-run.
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS portfolio_value_series CASCADE;

BEGIN;

CREATE TABLE IF NOT EXISTS portfolio_value_series (
    id                    BIGSERIAL PRIMARY KEY,
    account_key           TEXT NOT NULL,
    series_date           DATE NOT NULL,
    total_value           NUMERIC(18, 4) NOT NULL,
    holdings_market_value NUMERIC(18, 4) NOT NULL DEFAULT 0,
    cost_basis            NUMERIC(18, 4) NOT NULL DEFAULT 0,
    cash_balance          NUMERIC(18, 4) NOT NULL DEFAULT 0,
    net_deposits          NUMERIC(18, 4) NOT NULL DEFAULT 0,
    fx_unconverted_count  INTEGER NOT NULL DEFAULT 0,
    points_used           INTEGER NOT NULL DEFAULT 0,
    locf_filled           INTEGER NOT NULL DEFAULT 0,
    spike_suppressed      INTEGER NOT NULL DEFAULT 0,
    fingerprint           TEXT NOT NULL,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_mark_date        DATE NOT NULL,
    CONSTRAINT unique_portfolio_value_point
        UNIQUE (account_key, series_date)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_value_series_lookup
    ON portfolio_value_series (account_key, series_date);

-- Repair path: CREATE TABLE IF NOT EXISTS cannot add columns to a table that
-- already exists, and this migration may have been applied before the per-point
-- metadata columns were introduced. Idempotent; safe to re-run.
ALTER TABLE portfolio_value_series
    ADD COLUMN IF NOT EXISTS locf_filled      INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS spike_suppressed INTEGER NOT NULL DEFAULT 0;

COMMENT ON TABLE portfolio_value_series IS
    'Materialised portfolio value curve; one row per (account set, date). Sliced by period on read, rebuilt only when the input fingerprint changes.';
COMMENT ON COLUMN portfolio_value_series.account_key IS
    'Sorted comma-joined account ids identifying the account set.';
COMMENT ON COLUMN portfolio_value_series.points_used IS
    'How many account snapshots contributed to this date. Distinguishes a fully-observed date from a LOCF-filled one.';
COMMENT ON COLUMN portfolio_value_series.fingerprint IS
    'SHA-256(32) over account_key and the ordered snapshot input rows. Mismatch => rebuild, never serve.';
COMMENT ON COLUMN portfolio_value_series.last_mark_date IS
    'Latest date covered by this build; earlier rows are frozen and only the tail is recomputed next run.';

-- RLS: service_role writes, authenticated reads (same convention as 008/015).
ALTER TABLE portfolio_value_series ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'portfolio_value_series'
          AND policyname = 'authenticated can read portfolio_value_series'
    ) THEN
        CREATE POLICY "authenticated can read portfolio_value_series"
            ON portfolio_value_series FOR SELECT
            TO authenticated
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'portfolio_value_series'
          AND policyname = 'service_role can insert portfolio_value_series'
    ) THEN
        CREATE POLICY "service_role can insert portfolio_value_series"
            ON portfolio_value_series FOR INSERT
            TO service_role
            WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'portfolio_value_series'
          AND policyname = 'service_role can update portfolio_value_series'
    ) THEN
        CREATE POLICY "service_role can update portfolio_value_series"
            ON portfolio_value_series FOR UPDATE
            TO service_role
            USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'portfolio_value_series'
          AND policyname = 'service_role can delete portfolio_value_series'
    ) THEN
        CREATE POLICY "service_role can delete portfolio_value_series"
            ON portfolio_value_series FOR DELETE
            TO service_role
            USING (true);
    END IF;
END $$;

COMMIT;
