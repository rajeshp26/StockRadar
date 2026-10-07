"""RETIRED - do not run. This script was the source of the 2020-01-01 seeding defect.

It did two destructive things to accounts 9-12:

  1. DELETED every existing ``portfolio_events`` row for the account (including real
     ``transaction_imported`` history), breaking the append-only invariant the event
     log depends on.
  2. Wrote a replacement ``initial_holding_set`` event with ``effective_date`` hardcoded
     to ``"2020-01-01"``, while the quantities in the payload were read from the CURRENT
     ``portfolio_holdings`` projection.

Point 2 is the defect this codebase spent a long time chasing. Replay orders events by
effective date, so a capture of today's holdings stamped with a 2020 date is re-executed
against every corporate action that happened since: the seeded AAPL position was inflated
4x by its 2020-08-31 split and SHOP 10x by its 2022-06-29 split, on accounts 10-12. Total
cost and cash were untouched, so the corruption looked plausible instead of obviously
broken.

The correct way to record what an account holds when it has no usable history is a
``position_state_checkpoint`` whose effective date is the moment it was captured, not an
``initial_holding_set`` stamped with an invented past date. Migration
``backend/supabase/migrations/011_reclassify_projection_backfill_as_checkpoint.sql``
performs that reclassification, ``EventStore`` now rejects any future attempt to date a
projection capture before its capture instant, and the generators in
``backfill_initial_holdings.py`` / ``backfill_missing_initial.py`` emit the checkpoint
type. Snapshots are regenerated with ``rebuild_account_snapshots.py --apply``.

This file is retained only as a tombstone so the script is not reintroduced from history.
It is intentionally inert: every entry point refuses to run.
"""

import sys

_MESSAGE = (
    "fix_accounts_9_12.py is RETIRED. It deleted portfolio_events and re-seeded "
    "accounts 9-12 with a hardcoded 2020-01-01 effective_date, which replay then "
    "re-ran against later splits. Use position_state_checkpoint via the backfill "
    "generators, and rebuild snapshots with rebuild_account_snapshots.py. "
    "This script will not run."
)


def main() -> None:
    raise RuntimeError(_MESSAGE)


def seed_account(aid: int) -> None:
    raise RuntimeError(_MESSAGE)


def delete_events(aid: int) -> None:
    raise RuntimeError(_MESSAGE)


if __name__ == "__main__":
    print(_MESSAGE, file=sys.stderr)
    raise SystemExit(1)
