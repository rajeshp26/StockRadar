-- 019_grant_portfolio_value_series_privileges.sql
-- Migration: grant the privileges portfolio_value_series requires.
--
-- WHY THIS EXISTS
--   Migration 017 created the table and its RLS policies but never granted any
--   privilege on the table itself. RLS policies decide which ROWS a role may
--   touch; they do not grant the right to touch the TABLE. Without the GRANT,
--   PostgREST rejects every statement with 42501 ("permission denied for table
--   portfolio_value_series") and PortfolioValueSeriesRepository degrades to live
--   computation - so the read model stays empty and no job fails.
--
--   This is the same failure migration 007 records for views ("PostgREST then
--   refused service_role reads with 42501, and the repositories swallowed the
--   exception and returned empty results"). Migrations 008 (freshness_snapshot)
--   and 015 (benchmark_series) apply this grant block alongside their CREATE
--   TABLE; 017 omitted it, which is why the table was unreadable and unwritable
--   even after its columns existed.
--
-- IDEMPOTENT
--   GRANT is idempotent; re-running is a no-op.
--
-- ROLLBACK:
--   REVOKE ALL ON public.portfolio_value_series FROM service_role;
--   REVOKE ALL ON public.portfolio_value_series FROM authenticated;
--   REVOKE ALL ON SEQUENCE public.portfolio_value_series_id_seq FROM service_role;

BEGIN;

-- Least privilege, matching 008/015: the service role owns read+write, an
-- authenticated user may only read.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.portfolio_value_series TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.portfolio_value_series_id_seq TO service_role;
GRANT SELECT ON public.portfolio_value_series TO authenticated;

COMMIT;
