-- ============================================================================
-- Phase 2 — Read model (Stage 1): latest publishable run per (company, method)
-- Review doc §6.1-C: "Stage 1 (default): a SQL view or function selecting the
-- latest publishable run per (company, scope, method) from the immutable run
-- history (valuation_runs.output_snapshot). Run history stays the source of
-- truth; no dual-write synchronization, no backfill, no drift."
--
-- Scope note: the current schema has no scope_type/scope_id columns (that is
-- Phase 5 pipeline work, §6.1-D). Until then the view is per (company, method),
-- matching the granularity the summary endpoint needs.
--
-- Grant policy (Phase 0b precedent, least-privilege): service_role only.
-- RLS is OFF on valuation_runs and the API reads through service_role, so a
-- plain view (no security_invoker) matches the existing v_dcf_valuations etc.
-- ============================================================================

CREATE OR REPLACE VIEW public.v_valuation_latest_runs AS
SELECT DISTINCT ON (company_id, method)
    valuation_run_id,
    company_id,
    method,
    run_at,
    run_by_user_id,
    data_version_tag,
    input_snapshot,
    assumption_snapshot,
    output_snapshot,
    notes
FROM public.valuation_runs
ORDER BY company_id, method, run_at DESC;

GRANT SELECT ON public.v_valuation_latest_runs TO service_role;
