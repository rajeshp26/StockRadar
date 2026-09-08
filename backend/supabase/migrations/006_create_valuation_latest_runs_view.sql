-- 006_create_valuation_latest_runs_view.sql
-- Migration: Phase 2 valuation read model (Stage 1) — latest publishable run per (company, method).
-- Mirrors backend/scripts/phase2_valuation_read_model.sql so `supabase db reset` preserves the view
-- AND the service_role SELECT grant. Without the grant the summary endpoint (get_valuation_summary_rows)
-- fails with 42501, the exception is swallowed, and every method reports not_computed in the UI.
--
-- Grant policy (least-privilege): service_role only, matching the other public views.

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
