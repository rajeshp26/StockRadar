-- fix_price_history_precision.sql
-- Widen price_history price columns from numeric(12,4) to numeric(16,4)
-- to prevent overflow for extreme price values.
-- Safe to run multiple times (idempotent ALTER TYPE).
ALTER TABLE public.price_history
  ALTER COLUMN open_price TYPE numeric(16, 4),
  ALTER COLUMN close_price TYPE numeric(16, 4),
  ALTER COLUMN high_price TYPE numeric(16, 4),
  ALTER COLUMN low_price TYPE numeric(16, 4);
