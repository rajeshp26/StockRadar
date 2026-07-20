-- Migration: Add cdr_ratio and cdr_ratio_date columns to companies table
-- These store the per-company CDR ratio (TSX share price / CDR price)
-- Run this in Supabase Dashboard SQL Editor

ALTER TABLE companies ADD COLUMN IF NOT EXISTS cdr_ratio DECIMAL(10,2) DEFAULT NULL;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS cdr_ratio_date DATE DEFAULT NULL;

-- Verify
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'companies'
  AND column_name IN ('cdr_ratio', 'cdr_ratio_date');
