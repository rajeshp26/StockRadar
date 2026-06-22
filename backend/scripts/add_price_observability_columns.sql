-- Add price-history observability columns to companies
-- Run in Supabase Dashboard SQL Editor
ALTER TABLE companies 
ADD COLUMN IF NOT EXISTS last_price_attempt_at timestamptz,
ADD COLUMN IF NOT EXISTS last_price_success_at timestamptz,
ADD COLUMN IF NOT EXISTS consecutive_price_failures int DEFAULT 0;
