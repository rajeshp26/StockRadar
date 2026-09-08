-- 007_grant_service_role_select_on_views.sql
-- Migration: grant SELECT on all public views to service_role.
--
-- The Phase 2 read model (006) and the API views (portfolio_monthly_dividends,
-- portfolio_user_import_history, super_investor_current_holdings, v_*_valuations)
-- were created by one-off scripts (backend/scripts/create_all_views.sql,
-- phase2_valuation_read_model.sql) but never had their SELECT grants applied to the
-- local instance. PostgREST then refused service_role reads with 42501, and the
-- repositories swallowed the exception and returned empty results (e.g. the
-- valuation overview showing "No valuation data available yet").
--
-- Idempotent: re-running is a no-op. Views missing from the schema are skipped.
-- Grant policy (least-privilege): service_role only, matching the rest of the project.

DO $$
DECLARE
  r RECORD;
  v text;
BEGIN
  FOR r IN
    SELECT viewname FROM pg_views WHERE schemaname = 'public'
  LOOP
    v := r.viewname;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.role_table_grants g
      WHERE g.table_schema = 'public' AND g.table_name = v
        AND g.grantee = 'service_role' AND g.privilege_type = 'SELECT'
    ) THEN
      EXECUTE 'GRANT SELECT ON public.' || quote_ident(v) || ' TO service_role';
      RAISE NOTICE 'granted SELECT on %', v;
    END IF;
  END LOOP;
END $$;
