-- 011_reclassify_projection_backfill_as_checkpoint.sql
-- Migration: record a captured projection as a checkpoint, not as a historical fact.
--
-- WHY THIS EXISTS
--   initial_holding_set and position_state_checkpoint look interchangeable and are
--   not. initial_holding_set is a HISTORICAL claim: "on this date the account held
--   X". position_state_checkpoint is a CAPTURE: "as of this instant the account holds
--   X", where X was read out of a live projection and therefore already includes
--   every corporate action to date.
--
--   The backfills wrote the second thing using the first thing's type. They read
--   current quantities from portfolio_holdings and stamped them with a hardcoded
--   effective_date of 2020-01-01, producing a row that asserted the account held
--   pre-split quantities on a date that preceded the splits.
--
--   Replay orders by effective date, so the real later splits were then applied to
--   quantities that already reflected them. On accounts 10-12 this inflated the
--   seeded AAPL position 4x (split of 2020-08-31) and SHOP 10x (2022-06-29), which
--   is what desynchronised the Snapshot chart from the Overview. Total cost and cash
--   were unaffected, which is why the corruption read as plausible.
--
-- THE FIX
--   Reclassify the mislabelled events instead of editing a date on them. A
--   projection capture is not history, so it becomes position_state_checkpoint and
--   its effective date becomes the capture instant it already recorded in
--   created_at, rather than a date the payload was never true on. Replay then
--   RESETS the account to the captured state instead of accumulating onto invented
--   history, and the write-time guard in EventStore rejects any future attempt to
--   date a checkpoint before the moment it was captured.
--
--   This is a reclassification, not a repair of values: no quantity, cost, or cash
--   figure is touched. The payloads were already correct; only their type and the
--   date they are entitled to assert were wrong.
--
-- SCOPE
--   Only events carrying metadata.source = 'portfolio_holdings' are affected. A
--   genuine historical initial_holding_set, recorded from real account history,
--   does not carry that marker and is left alone -- it is entitled to an old date.
--
-- IDEMPOTENT
--   The WHERE clause matches only event_type = 'initial_holding_set', which this
--   migration rewrites to position_state_checkpoint. A second run matches nothing.

BEGIN;

UPDATE portfolio_events
SET event_type = 'position_state_checkpoint',
    data = jsonb_set(data, '{effective_date}', to_jsonb(created_at::date::text), true),
    idempotency_key = 'position_state_checkpoint_' || split_part(aggregate_id, '_', 2)
WHERE event_type = 'initial_holding_set'
  AND metadata->>'source' = 'portfolio_holdings'
  AND data ? 'effective_date';

COMMIT;
