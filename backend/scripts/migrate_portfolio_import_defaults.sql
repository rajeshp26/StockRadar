-- Migration: Fix portfolio_import_history constraints for async import flow
--
-- Changes:
--   1. Add DEFAULT 0 to total_rows and imported_rows (safety net for code paths
--      that don't explicitly set them)
--   2. Update status CHECK constraint to allow 'pending' and 'processing'
--      (async flow states) and remove 'partial' (never written by code)
--
-- Background:
--   create_import_job() sets status='pending' and omits imported_rows from
--   the INSERT payload. The original constraints rejected both:
--     • imported_rows INTEGER NOT NULL (no DEFAULT) → error 23502
--     • status CHECK only allowed 'completed'|'partial'|'failed' → error 23514
--   The async flow uses states: pending → processing → completed/failed.

ALTER TABLE public.portfolio_import_history
  ALTER COLUMN total_rows      SET DEFAULT 0,
  ALTER COLUMN imported_rows   SET DEFAULT 0;

ALTER TABLE public.portfolio_import_history
  DROP CONSTRAINT IF EXISTS portfolio_import_history_status_check;

ALTER TABLE public.portfolio_import_history
  ADD CONSTRAINT portfolio_import_history_status_check
  CHECK (status IN ('pending', 'processing', 'completed', 'failed'));
