-- 013_checkpoint_backdating_invariant.sql
-- Migration: Make a backdated projection checkpoint unrepresentable in the database.
--
-- WHY THIS EXISTS
--   EventStore._assert_state_import_not_backdated already rejects a backdated
--   state import, but that guard is Python. It is advisory in the only sense
--   that matters: it protects exactly the code paths that remember to call it.
--
--   An audit of every writer in this repository found the production surface
--   clean -- EventStore is the only production writer of portfolio_events, and
--   shared/split_sync.py, the one production module that also writes, updates
--   the `splits` table rather than the event log. But scripts/ holds well over
--   a hundred operational one-offs holding a raw Supabase client, and the
--   repository guard cannot constrain a path that never imports it. The same
--   reasoning that produced 010 applies here: a control enforced only by the
--   writer is a claim, not an invariant.
--
--   The failure this forecloses is concrete. A snapshot of current holdings
--   stamped with a past effective_date gets re-executed by replay against every
--   corporate action in between, multiplying quantities that already include
--   those actions. On 2026-09-25 that inflated AAPL 4x and SHOP 10x on accounts
--   10-12 and desynchronised the Overview from the Snapshot chart.
--
-- SEMANTICS: MIRRORED, NOT INVENTED
--   The predicate below is a deliberate transcription of
--   EventStore._assert_state_import_not_backdated, so the write-time guard, the
--   database, and scripts/verify_snapshot_history.py agree by construction:
--
--     applies when  event_type = 'position_state_checkpoint'
--                  OR metadata->>'source' = 'portfolio_holdings'
--     exempt when  data->>'effective_date' is absent
--     reject when  effective_date < capture date
--
--   Two consequences worth stating rather than hiding:
--
--   1. An absent effective_date is exempt, because the Python guard exempts it
--      and a database stricter than its own application would reject writes the
--      application considers valid. This is a known, deliberate gap, not an
--      oversight: a projection row with no effective_date cannot be replay-
--      ordered, and closing that gap belongs in a change that also backfills
--      the affected rows.
--
--   2. The capture date is (NOW() AT TIME ZONE 'UTC')::date, not created_at.
--      created_at is client-suppliable, so a writer that forged a past
--      created_at would walk straight through a trigger that trusted it. NOW()
--      is server-controlled and UTC matches the application's
--      datetime.now(timezone.utc).date(), so the two guards cannot disagree
--      about which day it is. The pre-flight check below compares against the
--      stored created_at, because for rows that already exist the stored value
--      is the historical fact rather than a forgeable claim.
--
-- IDEMPOTENT
--   CREATE OR REPLACE, DROP TRIGGER IF EXISTS, and a pre-flight check that
--   either finds nothing to do or refuses outright, so a second run is a no-op.

BEGIN;

-- Refuse to install over dirty data. A trigger guards future writes only, so
-- installing one while historical violations survive would leave the invariant
-- true of new rows and false of old ones -- the worst of both, because the
-- migration would report success.
DO $$
DECLARE
    violations BIGINT;
    earliest  TEXT;
BEGIN
    SELECT count(*), min(left(e.data->>'effective_date', 10))
      INTO violations, earliest
      FROM public.portfolio_events e
     WHERE (e.event_type = 'position_state_checkpoint'
            OR e.metadata->>'source' = 'portfolio_holdings')
       AND e.data->>'effective_date' ~ '^\d{4}-\d{2}-\d{2}'
       AND left(e.data->>'effective_date', 10)::date < (e.created_at AT TIME ZONE 'UTC')::date;

    IF violations > 0 THEN
        RAISE EXCEPTION
            'Refusing to install: % existing portfolio_events row(s) are already backdated (earliest effective_date=%). Repair them first; installing the trigger over them would leave the invariant true for new rows and false for old ones.',
            violations, earliest;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION checkpoint_cannot_predate_capture()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    is_projection BOOLEAN;
    effective    DATE;
    captured     DATE;
BEGIN
    is_projection := NEW.event_type = 'position_state_checkpoint'
                     OR NEW.metadata->>'source' = 'portfolio_holdings';

    -- IS NOT TRUE, not "NOT is_projection". When metadata carries no source the
    -- comparison yields NULL, not FALSE, and NOT NULL is still NULL -- which IF
    -- treats as untaken, so the early return would be skipped and genuine
    -- historical imports would be rejected. It also covers metadata IS NULL.
    IF is_projection IS NOT TRUE THEN
        RETURN NEW;
    END IF;

    IF NEW.data->>'effective_date' IS NULL THEN
        RETURN NEW;
    END IF;

    IF NEW.data->>'effective_date' !~ '^\d{4}-\d{2}-\d{2}' THEN
        RAISE EXCEPTION
            'portfolio_events.data.effective_date must be an ISO date (YYYY-MM-DD), got %',
            NEW.data->>'effective_date'
            USING ERRCODE = 'check_violation';
    END IF;

    effective := left(NEW.data->>'effective_date', 10)::date;
    captured  := (NOW() AT TIME ZONE 'UTC')::date;

    IF effective < captured THEN
        RAISE EXCEPTION
            'State import dated % predates its capture date % (event_type=%). A snapshot of current holdings is only true as of the moment it was captured; backdating it re-applies corporate actions to quantities that already include them. Use the capture date as effective_date, or record real transactions as history preceding a checkpoint.',
            effective, captured, NEW.event_type
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tr_checkpoint_cannot_predate_capture ON public.portfolio_events;

CREATE TRIGGER tr_checkpoint_cannot_predate_capture
    BEFORE INSERT OR UPDATE ON public.portfolio_events
    FOR EACH ROW
    EXECUTE FUNCTION checkpoint_cannot_predate_capture();

COMMENT ON FUNCTION checkpoint_cannot_predate_capture() IS
    'Rejects a position_state_checkpoint or portfolio_holdings-sourced event whose data.effective_date predates its capture date. Installed by 013 because EventStore''s write-time guard constrains only callers that import it, and scripts/ hold a raw client that does not.';

COMMIT;
