-- 012_enforce_snapshot_job_id_not_null.sql
-- Migration: make every portfolio snapshot attributable to the writer that made it.
--
-- WHY THIS EXISTS
--   portfolio_snapshots.job_id is the audit trail: it names the job or script that
--   produced a stored snapshot. It was declared as a bare nullable TEXT column, so a
--   writer that simply forgot the field produced an unattributable row and nothing
--   complained. Two rebuild scripts did exactly that. They built a snapshot row via
--   build_snapshot_row(job_id=...) and then hand-copied a subset of fields into the
--   row they actually wrote, omitting job_id from the copy. The value was computed
--   correctly and then dropped on the floor, silently, for every row they wrote.
--   The result was 3959 historical snapshots across accounts 7, 8 and 9 with an empty
--   job_id: real data with no way to say what produced it or whether it can be
--   trusted or rebuilt. They were empty strings rather than NULL because the column
--   also carried a permissive DEFAULT '', so a writer that omitted job_id did not
--   fail and did not even store NULL -- Postgres quietly filled in ''. That is why
--   this bug could hide behind a NOT NULL column.
--
--   Note the earlier intent existed as backend/scripts/migration_job_id_not_null.sql
--   but that file was never placed in supabase/migrations, so it was never part of
--   the migration pipeline and never ran. The column is still nullable in the live
--   database today. This migration is that same intent, correctly filed and applied.
--
-- THE FIX
--   1. Backfill the already-unattributable legacy rows to the literal 'unknown'.
--      'unknown' is the honest value: we do not know what wrote them, and claiming
--      a writer we cannot prove would be worse than admitting the gap. Going forward
--      every writer supplies a real id, so 'unknown' is a closed, auditable set.
--   2. Set NOT NULL so the column can never again hold a missing audit trail.
--   3. Drop any DEFAULT on the column. This is the load-bearing part. With a
--      DEFAULT in place, a writer that omits job_id does not fail -- Postgres
--      silently substitutes the default. That would let the exact bug this migration
--      exists to prevent keep passing, just with '' instead of NULL. With no default
--      and NOT NULL, an omitted job_id raises a not-null violation at write time and
--      the writer is forced to name itself. A loud failure is the whole point.
--
-- SCOPE
--   Touches no value columns: no total_value, cost_basis, cash_balance, holdings or
--   quality flag is modified. This changes only the provenance metadata and the
--   constraint that guards it.
--
-- IDEMPOTENT
--   The backfill matches only job_id IS NULL, and after the first run none remain.
--   SET NOT NULL on an already-NOT NULL column is a no-op, as is DROP DEFAULT on a
--   column that has none. A second run matches nothing and changes nothing.

BEGIN;

-- Step 1: honestly attribute the legacy rows we cannot attribute. Catch both NULL
--         and the empty string left behind by the old DEFAULT ''. Matching only
--         IS NULL silently skips every historical row this migration exists to fix.
UPDATE portfolio_snapshots
SET job_id = 'unknown'
WHERE job_id IS NULL OR job_id = '';

-- Step 2: remove any permissive default so an omitted job_id fails loudly
--         instead of being silently replaced.
ALTER TABLE portfolio_snapshots ALTER COLUMN job_id DROP DEFAULT;

-- Step 3: the audit trail is now mandatory.
ALTER TABLE portfolio_snapshots ALTER COLUMN job_id SET NOT NULL;

COMMIT;
