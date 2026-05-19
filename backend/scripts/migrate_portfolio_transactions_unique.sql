-- Migration: Add UNIQUE constraint for transaction fingerprint
--
-- Required by insert_transactions_with_duplicates() which uses
-- ON CONFLICT (account_id, transaction_date, symbol, quantity, net_cash_amount)
-- DO NOTHING via the Supabase upsert() API with ignore_duplicates=True.
--
-- Without this constraint, Postgres raises error 42P10:
--   "there is no unique or exclusion constraint matching the ON CONFLICT specification"

CREATE UNIQUE INDEX IF NOT EXISTS uq_transaction_fingerprint
  ON public.portfolio_transactions
  (account_id, transaction_date, symbol, quantity, net_cash_amount)
  WHERE symbol IS NOT NULL;
