-- 010_cdr_ratio_provenance_guard.sql
-- Migration: Make a market-derived cdr_ratio unrepresentable, not merely labelled.
--
-- WHY THIS EXISTS
--   009 installed the CHECK constraint companies_cdr_ratio_range. Verifying it
--   against live data showed it does NOT stop the corruption it was meant to
--   stop, and the reason is structural rather than a mistake in the predicate.
--
--   The original writer updates companies.cdr_ratio and companies.cdr_ratio_date
--   but never mentions cdr_ratio_source. 009 backfilled that column to
--   'structural_constant'. So a market-derived write such as 1.73 arriving
--   through that path inherits the surviving label and produces a row that
--   reads:
--
--       cdr_ratio = 1.73, cdr_ratio_source = 'structural_constant'
--
--   which satisfies every clause of 009's constraint: in range, provenance
--   present, provenance correct. The constraint certifies that a claim was made,
--   not that the claim is true. A column written once and thereafter inherited
--   is a claim, not provenance.
--
--   Observed on the local database after 009 was applied: 9 of 11 CDR companies
--   holding market-derived ratios, every one labelled 'structural_constant'.
--
-- WHY NOT A PROVENANCE-DECLARATION TRIGGER
--   The first attempt here rejected a ratio change that did not also change
--   cdr_ratio_source. Executing it against live data disproved that predicate:
--   a writer that legitimately restates the SAME provenance (cdr_ratio 10.00 ->
--   2.50 with cdr_ratio_source left at 'structural_constant') is rejected
--   alongside the polluting writer, because "restated" and "never mentioned"
--   are indistinguishable inside a trigger. Any control that depends on the
--   writer self-certifying cannot separate those two cases, so this migration
--   stops asking the writer to certify anything.
--
-- THE FIX
--   cdr_ratio_registry is an authoritative allowlist of structural ratios, and a
--   BEFORE INSERT OR UPDATE trigger rejects any companies.cdr_ratio absent from
--   it. A market-derived value is rejected because it is not a depositary
--   ratio, regardless of how plausible it looks or what provenance it claims.
--   A legitimate future ratio is expressed by registering it, which is a
--   reviewed change rather than a privilege a writer can grant itself.
--
--   009's range constraint is retained: the registry rejects unregistered
--   values, and the range constraint still rejects zero, which would divide by
--   zero during pricing.
--
-- IDEMPOTENT
--   CREATE OR REPLACE, CREATE TABLE IF NOT EXISTS, ON CONFLICT DO UPDATE, and
--   DROP TRIGGER IF EXISTS, so a second run is a no-op.

BEGIN;

CREATE TABLE IF NOT EXISTS cdr_ratio_registry (
    cdr_ratio NUMERIC(10,2) PRIMARY KEY,
    meaning   TEXT NOT NULL
);

-- Every other migration grants the roles the app connects as (006, 007, 008);
-- without this the tr_cdr_ratio_must_be_registered trigger's SELECT is denied
-- when a companies row is inserted via the service_role connection.
GRANT SELECT ON public.cdr_ratio_registry TO service_role;

-- Seeded with the single ratio this data actually contains. Other Canadian
-- depositary ratios (1:2, 1:20) exist in the market but no instrument here uses
-- one, so they are deliberately NOT pre-authorized: a ratio becomes expressible
-- by inserting it here with its meaning, which is a reviewed change rather than
-- something a writer can grant itself.
INSERT INTO cdr_ratio_registry (cdr_ratio, meaning) VALUES
    (10.00, '1 CDR = 1/10 of an underlying US share (standard Canadian CDR)')
ON CONFLICT (cdr_ratio) DO UPDATE SET meaning = EXCLUDED.meaning;

CREATE OR REPLACE FUNCTION cdr_ratio_must_be_registered()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.cdr_ratio IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM cdr_ratio_registry r WHERE r.cdr_ratio = NEW.cdr_ratio
       )
    THEN
        RAISE EXCEPTION
            'cdr_ratio % for company_id=% is not a registered structural ratio; add it to cdr_ratio_registry with its meaning if it is genuinely structural',
            NEW.cdr_ratio,
            NEW.company_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tr_cdr_ratio_requires_provenance ON companies;
DROP FUNCTION IF EXISTS cdr_ratio_requires_provenance();
DROP TRIGGER IF EXISTS tr_cdr_ratio_must_be_registered ON companies;

CREATE TRIGGER tr_cdr_ratio_must_be_registered
    BEFORE INSERT OR UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION cdr_ratio_must_be_registered();

COMMENT ON TABLE cdr_ratio_registry IS
    'Authoritative allowlist of structural CDR ratios (1 CDR = 1/cdr_ratio of the underlying US share). A cdr_ratio is structural, fixed by the depositary at issuance, and is never a market measurement. Adding a row here is the supported way to express a newly encountered depositary ratio; nothing in the pricing path may insert one.';

COMMENT ON FUNCTION cdr_ratio_must_be_registered() IS
    'Rejects any companies.cdr_ratio absent from cdr_ratio_registry. Installed by 010 because 009''s range constraint could not distinguish a legitimate structural ratio from a market-derived one that merely looked plausible.';

COMMIT;
