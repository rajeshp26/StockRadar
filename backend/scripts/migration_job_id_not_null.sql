-- Migration: Enforce job_id NOT NULL on portfolio_snapshots
-- This prevents unauditable snapshot writes (e.g., from manual scripts).

-- Step 1: Backfill existing NULL job_ids
UPDATE portfolio_snapshots SET job_id = 'unknown' WHERE job_id IS NULL;

-- Step 2: Add NOT NULL constraint
ALTER TABLE portfolio_snapshots ALTER COLUMN job_id SET NOT NULL;

-- Step 3: Update the default so future inserts without job_id fail clearly
ALTER TABLE portfolio_snapshots ALTER COLUMN job_id SET DEFAULT '';
