"""RETIRED - do not run. This script was a source of CDR pricing corruption.

It computed ``cdr_ratio = TSX_share_price / CDR_average_cost`` and wrote that
market-derived value into ``companies.cdr_ratio``.

That is wrong. A CDR ratio is a STRUCTURAL property of the instrument, fixed by
the depositary at issuance (1 CDR = 1/10 of an underlying US share). It is not a
market measurement, so a ratio computed from a share price and a user's cost
basis is a meaningless number that happens to land in a plausible range. The
"sanity check" in the old code (rejecting ratios outside [1, 100]) did not catch
it: observed polluted values were 1.03, 1.28, 1.73, 1.94, 2.12, 2.31, 3.32,
10.91, 13.67 and 34.12, all of which pass.

Because the ratio divides the displayed price, a stored 34.12 underpriced the
holding by roughly 3.4x.

The ratio is now written only from the structural constant
``shared.cdr_utils.CDR_RATIO``, by
``application/jobs/price_ingestion_job.py::_update_cdr_ratios``. The data this
script corrupted was repaired by migration
``backend/supabase/migrations/009_cdr_ratio_integrity.sql``, and the
``companies_cdr_ratio_range`` CHECK constraint now rejects a ratio that does not
declare structural provenance.

This file is retained only as a tombstone so the script is not reintroduced from
history. It is intentionally inert: every entry point refuses to run.
"""

import sys

_MESSAGE = (
    "backfill_cdr_ratios.py is RETIRED. It derived companies.cdr_ratio from "
    "TSX price / CDR average cost, which corrupted CDR pricing. The ratio is a "
    "structural constant (shared.cdr_utils.CDR_RATIO). See migration "
    "009_cdr_ratio_integrity.sql. This script will not run."
)


def compute_and_store_ratios() -> None:
    raise RuntimeError(_MESSAGE)


def verify() -> None:
    raise RuntimeError(_MESSAGE)


def find_cdr_companies() -> None:
    raise RuntimeError(_MESSAGE)


if __name__ == "__main__":
    print(_MESSAGE, file=sys.stderr)
    raise SystemExit(1)
