-- 009_cdr_ratio_integrity.sql
-- Migration: Repair CDR pricing at the root and make bad values unrepresentable.
--
-- ROOT CAUSE
--   application/jobs/price_ingestion_job.py::_update_cdr_ratios wrote the
--   correct structural ratio (CDR_RATIO = 10.0) and then, inside the same
--   function, OVERWROTE companies.cdr_ratio with a market-derived value
--   (TSX share price / CDR average cost) that was "sanity checked" only to lie
--   in [1, 100]. That writer is deleted by this change. This migration repairs
--   the data it corrupted and installs a database backstop so no future writer
--   can silently reintroduce a market-derived ratio.
--
-- DESIGN
--   A CDR ratio is a STRUCTURAL property of the instrument, fixed by the
--   depositary at issuance (1 CDR = 1/10 of an underlying US share). It is not
--   a market measurement. Nothing here derives a ratio from price or cost data.
--
--   All repairs are derived STRUCTURALLY from the canonical CDR signal - the
--   transaction security name (the same signal shared/cdr_utils.py keys on) -
--   never from hardcoded company or holding ids, so the migration re-derives
--   correctly for data added after it was authored.
--
-- IDEMPOTENT
--   Every statement is a no-op on a second run. The constraint is installed via
--   DROP ... IF EXISTS so it can be tightened in a later revision.

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Provenance column.
--    Must be declared before the UPDATEs below, which set it: step 5's
--    constraint requires a non-null ratio to carry a non-null provenance, so a
--    ratio written before this column exists could not be labelled.
-- ---------------------------------------------------------------------------
ALTER TABLE companies ADD COLUMN IF NOT EXISTS cdr_ratio_source TEXT;

-- ---------------------------------------------------------------------------
-- 1. Repair the per-holding CDR flag.
--    snapshot_builder applies the CDR ratio only when the HOLDING carries
--    exchange_override = 'TOR'. Holdings whose transactions were clearly CDR
--    trades but whose flag is NULL were priced as direct holdings. Idempotent:
--    only rows that are currently NULL are touched.
-- ---------------------------------------------------------------------------
UPDATE portfolio_holdings h
SET exchange_override = 'TOR'
WHERE h.exchange_override IS NULL
  AND EXISTS (
      SELECT 1
      FROM portfolio_transactions t
      WHERE t.account_id = h.account_id
        AND t.company_id = h.company_id
        AND (
            COALESCE(t.security_name, '') ~* '\s+CDR'
            OR COALESCE(t.raw_data::text, '') ~* '\s+CDR'
        )
  );

-- ---------------------------------------------------------------------------
-- 2. Write the structural constant for every CDR company.
--    Includes sold positions and MIXED companies (CDR in one account, direct in
--    another, e.g. AAPL). This is safe because no consumer divides a mixed
--    company by a company-global ratio:
--      - shared/price_utils.get_cdr_maps_for_companies applies a UNANIMOUS gate
--        (company divided only when ALL its holdings are TOR);
--      - shared/snapshot_builder._resolve_holding_price applies the ratio
--        PER HOLDING, gated on that holding's exchange_override.
-- ---------------------------------------------------------------------------
UPDATE companies c
SET cdr_ratio = 10.00,
    cdr_ratio_date = CURRENT_DATE,
    cdr_ratio_source = 'structural_constant'
WHERE c.company_id IN (
    SELECT DISTINCT t.company_id
    FROM portfolio_transactions t
    WHERE t.company_id IS NOT NULL
      AND (
          COALESCE(t.security_name, '') ~* '\s+CDR'
          OR COALESCE(t.raw_data::text, '') ~* '\s+CDR'
      )
)
AND c.cdr_ratio IS DISTINCT FROM 10.00;

-- ---------------------------------------------------------------------------
-- 3. Clear ratios on companies with no CDR evidence at all.
--    A company that was never traded as a CDR carries no ratio. This removes
--    market-derived leftovers. Idempotent: already-NULL rows are skipped.
-- ---------------------------------------------------------------------------
UPDATE companies c
SET cdr_ratio = NULL,
    cdr_ratio_date = NULL,
    cdr_ratio_source = NULL
WHERE c.cdr_ratio IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM portfolio_transactions t
      WHERE t.company_id = c.company_id
        AND (
            COALESCE(t.security_name, '') ~* '\s+CDR'
            OR COALESCE(t.raw_data::text, '') ~* '\s+CDR'
        )
  );

-- ---------------------------------------------------------------------------
-- 4. Provenance.
--    Labels the structural constant written in step 2. Scoped to cdr_ratio =
--    10.00 deliberately: steps 2 and 3 leave every row either exactly 10.00 or
--    NULL, so the narrower predicate labels exactly the same rows as
--    "cdr_ratio IS NOT NULL" while failing closed if a future edit reorders
--    those steps. A broader predicate here would stamp 'structural_constant'
--    onto values this migration never derived, which is how a market-derived
--    ratio ends up wearing structural provenance.
-- ---------------------------------------------------------------------------
UPDATE companies
SET cdr_ratio_source = 'structural_constant'
WHERE cdr_ratio = 10.00
  AND cdr_ratio_source IS NULL;

COMMENT ON COLUMN companies.cdr_ratio IS
    'Structural CDR ratio (1 CDR = 1/cdr_ratio of the underlying US share), fixed at '
    'issuance by the depositary. NOT a market measurement - never derived from price or '
    'cost data. NULL for companies that are not CDRs.';
COMMENT ON COLUMN companies.cdr_ratio_source IS
    'Provenance of cdr_ratio. Only ''structural_constant'' is a legitimate value.';

-- ---------------------------------------------------------------------------
-- 5. Backstop constraint.
--    Layer 2 of the fix. It rejects zero (which would divide by zero during
--    pricing), negatives, absurd magnitudes, and any ratio that does not
--    declare structural provenance.
--
--    It deliberately does NOT pin the value to 10.0: a legitimate future 1:2 or
--    1:20 CDR must remain expressible.
--
--    The explicit "IS NOT NULL" is required, not redundant. A CHECK passes when
--    its expression is NULL, and "cdr_ratio_source = 'structural_constant'"
--    evaluates to NULL - not FALSE - when the source is NULL. Without the guard
--    the whole OR becomes NULL and a ratio with no provenance is accepted.
--    scripts/verify_cdr_constraint.py exercises every case in this comment.
-- ---------------------------------------------------------------------------
ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_cdr_ratio_range;

ALTER TABLE companies ADD CONSTRAINT companies_cdr_ratio_range CHECK (
    cdr_ratio IS NULL
    OR (
        cdr_ratio > 0
        AND cdr_ratio <= 1000
        AND cdr_ratio_source IS NOT NULL
        AND cdr_ratio_source = 'structural_constant'
    )
);

COMMIT;
