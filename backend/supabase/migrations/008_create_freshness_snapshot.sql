-- 008_create_freshness_snapshot.sql
-- Migration: Create freshness_snapshot table for the Data Freshness Monitoring feature.
-- Part of Data Freshness & Reconciliation (design doc: backend/docs/DATA_FRESHNESS_RECONCILIATION.md)

CREATE TABLE IF NOT EXISTS freshness_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    domain          TEXT NOT NULL,             -- 'financial_statements' | 'institutional_holdings'
    as_of           DATE NOT NULL,
    expected_period TEXT NOT NULL,             -- ISO 'YYYY-MM-DD' watermark / prior quarter end
    total           INT NOT NULL,
    covered         INT NOT NULL,
    pct             NUMERIC(5, 2) NOT NULL,    -- coverage as percentage (0.00-100.00)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_freshness_domain_asof UNIQUE (domain, as_of)
);

CREATE INDEX IF NOT EXISTS idx_freshness_snapshot_domain_asof
    ON freshness_snapshot (domain, as_of DESC);

COMMENT ON TABLE freshness_snapshot IS
    'Daily per-domain data freshness coverage snapshots.';
COMMENT ON COLUMN freshness_snapshot.pct IS
    'Coverage as percentage (0.00-100.00); below threshold alerts.';

-- RLS: service_role writes, authenticated reads (same convention as exchange_rates)
ALTER TABLE freshness_snapshot ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated can read freshness_snapshot"
    ON freshness_snapshot
    FOR SELECT
    USING (auth.role() IN ('authenticated', 'service_role'));

CREATE POLICY "service_role can insert freshness_snapshot"
    ON freshness_snapshot
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role can update freshness_snapshot"
    ON freshness_snapshot
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role can delete freshness_snapshot"
    ON freshness_snapshot
    FOR DELETE
    USING (auth.role() = 'service_role');

-- Role grants: PostgREST/service_role needs table AND sequence privileges (RLS alone is not
-- sufficient - 42501 discovered by live E2E verification). Mirrors 008 RLS model:
-- service_role CRUD + authenticated read; no anon.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.freshness_snapshot TO service_role;
GRANT SELECT ON public.freshness_snapshot TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.freshness_snapshot_id_seq TO service_role;