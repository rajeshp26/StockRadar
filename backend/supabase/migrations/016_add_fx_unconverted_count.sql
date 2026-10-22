-- 016_add_fx_unconverted_count.sql
-- Migration: persist the FX-unconverted holding count as a scalar column.
--
-- WHY THIS EXISTS
--   /portfolio/performance selected `holdings_json` on every snapshot read purely
--   to answer one question -- "does this date contain any holding whose FX rate
--   was unavailable (fx_applied=False), making its value an artifact rather than
--   a market move?" (portfolio_service.py:2006-2013). That question needs a
--   single integer, but answering it shipped the whole JSON blob:
--
--     holdings_json per row: avg 3,834 B, max 9,033 B
--     4,589 rows in a 3-account ALL-time window  ->  ~18 MB per request
--     measured: full column set 4,120 ms vs scalars-only 63 ms for the same rows
--
--   The count is already computed at write time (snapshot_builder.py:636-638)
--   but was never persisted. This column persists it, so the chart read can drop
--   holdings_json entirely.
--
-- SEMANTICS
--   fx_unconverted_count = number of entries in holdings_json with
--   fx_applied is False. 0 means every holding on that snapshot has a real FX
--   rate and the stored value is trustworthy. >0 marks the date as an FX
--   artifact for performance smoothing.
--
-- BACKFILL
--   Existing rows are backfilled by counting inside holdings_json. New rows are
--   populated by the write path. The default of 0 is only correct for rows with
--   no holdings_json or all-converted holdings; the backfill is what makes
--   pre-existing rows correct, and it is part of this migration so the column is
--   never silently 0 for a row that actually has unconverted FX.
--
-- IDEMPOTENT
--   ADD COLUMN IF NOT EXISTS; backfill guarded so a re-run does not redo work.
--   Safe to re-run.
--
-- ROLLBACK:
--   ALTER TABLE portfolio_snapshots DROP COLUMN IF EXISTS fx_unconverted_count;

BEGIN;

ALTER TABLE portfolio_snapshots
    ADD COLUMN IF NOT EXISTS fx_unconverted_count INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN portfolio_snapshots.fx_unconverted_count IS
    'Count of holdings_json entries with fx_applied=false on this snapshot. >0 marks the date as an unconverted-FX artifact for performance smoothing. Persisted so the chart read never has to ship holdings_json.';

-- Backfill: derive the count from the blob that already exists. Only touches
-- rows the write path could not have populated, so a re-run is a no-op for
-- rows already carrying a non-zero count.
UPDATE portfolio_snapshots
SET fx_unconverted_count = COALESCE((
        SELECT count(*)::int
        FROM jsonb_array_elements(holdings_json) AS h
        WHERE h->>'fx_applied' = 'false'
     ), 0)
WHERE holdings_json IS NOT NULL
  AND jsonb_typeof(holdings_json) = 'array'
  AND fx_unconverted_count = 0;

COMMIT;
