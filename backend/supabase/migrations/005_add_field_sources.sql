-- Add field_sources jsonb provenance columns to the three financial-statement
-- tables. The ingestion pipeline records each normalized field's data origin
-- alongside the value itself.
--
-- Already applied and verified on cloud project viqdqgxcumcdhqxooplw (2026-08-24);
-- committed so fresh environments cannot diverge again.

ALTER TABLE public.income_statements ADD COLUMN IF NOT EXISTS field_sources jsonb;
ALTER TABLE public.balance_sheets ADD COLUMN IF NOT EXISTS field_sources jsonb;
ALTER TABLE public.cash_flow_statements ADD COLUMN IF NOT EXISTS field_sources jsonb;