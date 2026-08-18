-- ============================================================================
-- Migration: Add auto-generating sequences to PK columns missing them
-- Tables: splits (split_id), company_summary (summary_id)
--
-- Idempotent — safe to run against any environment, safe to run twice.
-- Run with: psql -f fix_missing_sequences.sql  OR  via Supabase SQL editor.
-- ============================================================================

-- ── splits.split_id ──────────────────────────────────────────────────────────
DO $$
BEGIN
  -- Only add the DEFAULT if the column currently has none (i.e. was created
  -- as plain integer NOT NULL without SERIAL / GENERATED AS IDENTITY).
  IF NOT EXISTS (
    SELECT 1
    FROM   pg_attribute a
    JOIN   pg_class c ON c.oid = a.attrelid
    WHERE  c.relname   = 'splits'
      AND  a.attname   = 'split_id'
      AND  a.attnotnull
      AND  NOT a.attisdropped
      AND  NOT EXISTS (          -- no DEFAULT yet
        SELECT 1 FROM pg_attrdef d
        WHERE  d.adrelid = a.attrelid
          AND  d.adnum   = a.attnum
      )
  ) THEN
    CREATE SEQUENCE IF NOT EXISTS public.splits_split_id_seq
      OWNED BY public.splits.split_id;

    ALTER TABLE public.splits
      ALTER COLUMN split_id SET DEFAULT nextval('public.splits_split_id_seq');

    -- Seed sequence so the next INSERT gets a value higher than any existing row
    PERFORM setval(
      'public.splits_split_id_seq',
      COALESCE((SELECT MAX(split_id) FROM public.splits), 0)
    );

    RAISE NOTICE 'splits.split_id: sequence attached, seeded to %',
      (SELECT MAX(split_id) FROM public.splits);
  ELSE
    RAISE NOTICE 'splits.split_id: already has DEFAULT — skipped';
  END IF;
END $$;


-- ── company_summary.summary_id ───────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM   pg_attribute a
    JOIN   pg_class c ON c.oid = a.attrelid
    WHERE  c.relname   = 'company_summary'
      AND  a.attname   = 'summary_id'
      AND  a.attnotnull
      AND  NOT a.attisdropped
      AND  NOT EXISTS (
        SELECT 1 FROM pg_attrdef d
        WHERE  d.adrelid = a.attrelid
          AND  d.adnum   = a.attnum
      )
  ) THEN
    CREATE SEQUENCE IF NOT EXISTS public.company_summary_summary_id_seq
      OWNED BY public.company_summary.summary_id;

    ALTER TABLE public.company_summary
      ALTER COLUMN summary_id SET DEFAULT nextval('public.company_summary_summary_id_seq');

    PERFORM setval(
      'public.company_summary_summary_id_seq',
      COALESCE((SELECT MAX(summary_id) FROM public.company_summary), 0)
    );

    RAISE NOTICE 'company_summary.summary_id: sequence attached, seeded to %',
      (SELECT MAX(summary_id) FROM public.company_summary);
  ELSE
    RAISE NOTICE 'company_summary.summary_id: already has DEFAULT — skipped';
  END IF;
END $$;
