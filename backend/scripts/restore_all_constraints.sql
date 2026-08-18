-- ============================================================================
-- COMPLETE SCHEMA RESTORE — StockerPro Database
-- Generated: 2026-08-03
-- Contains: ALL 48 tables with complete DDL, constraints, indexes, triggers
-- Run order: Trigger functions first, then base tables, then dependent tables
-- ============================================================================

-- ============================================================================
-- TRIGGER FUNCTIONS (must exist before triggers on tables)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.update_watchlists_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.event_insert_sequence_trigger()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.event_sequence (event_id, aggregate_id, version, created_at)
  VALUES (NEW.id, NEW.aggregate_id, NEW.event_version, NEW.created_at);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. currencies (base — no dependencies)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.currencies (
  code character varying(3) NOT NULL,
  name character varying(50) NOT NULL,
  symbol character varying(5) NULL,
  CONSTRAINT currencies_pkey PRIMARY KEY (code)
) TABLESPACE pg_default;

-- ============================================================================
-- 2. users
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.users (
  user_id serial NOT NULL,
  email character varying(255) NOT NULL,
  username character varying(100) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  last_signed_in timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  preferred_currency character varying(3) NOT NULL,
  auth_id text NULL,
  timezone character varying(50) NOT NULL DEFAULT 'America/New_York'::character varying,
  first_name TEXT NULL,
  last_name TEXT NULL,
  avatar_url TEXT NULL,
  CONSTRAINT users_pkey PRIMARY KEY (user_id),
  CONSTRAINT users_email_key UNIQUE (email),
  CONSTRAINT users_firebase_uid_key UNIQUE (auth_id),
  CONSTRAINT uq_users_auth_id UNIQUE (auth_id),
  CONSTRAINT uq_users_email UNIQUE (email),
  CONSTRAINT fk_users_currency FOREIGN KEY (preferred_currency) REFERENCES public.currencies (code),
  CONSTRAINT check_timezone_format CHECK (
    ((timezone)::text ~ '^[A-Za-z_]+(/[A-Za-z_]+)?(/[A-Za-z_]+)?$'::text)
  ),
  CONSTRAINT check_valid_timezone CHECK (
    ((timezone)::text ~ '^[A-Za-z_]+(/[A-Za-z_]+)?(/[A-Za-z_]+)?$'::text)
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_users_timezone ON public.users USING btree (timezone) TABLESPACE pg_default;

-- ============================================================================
-- 3. companies
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.companies (
  company_id serial NOT NULL,
  ticker_symbol character varying(10) NOT NULL,
  company_name character varying(255) NOT NULL,
  exchange character varying(50) NOT NULL DEFAULT 'UNKNOWN'::character varying,
  sector character varying(100) NULL,
  industry character varying(100) NULL,
  currency character varying(3) NOT NULL DEFAULT 'USD'::character varying,
  fiscal_year_end_month integer NULL,
  description text NULL,
  website character varying(255) NULL,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  next_earnings_date date NULL,
  first_financial_data_loaded_at timestamp with time zone NULL,
  last_financial_refresh_at timestamp with time zone NULL,
  last_refreshed_fiscal_year integer NULL,
  last_refreshed_fiscal_quarter smallint NULL,
  data_completeness_status character varying(50) NOT NULL DEFAULT 'INITIAL'::character varying,
  security_type text NULL DEFAULT 'stock'::text,
  last_price_refresh_at timestamp with time zone NULL,
  last_price_attempt_at timestamptz NULL,
  last_price_success_at timestamptz NULL,
  consecutive_price_failures int DEFAULT 0,
  cdr_ratio decimal(10,2) DEFAULT NULL,
  cdr_ratio_date date DEFAULT NULL,
  CONSTRAINT companies_new_pkey PRIMARY KEY (company_id),
  CONSTRAINT companies_ticker_exchange_unique UNIQUE (ticker_symbol, exchange),
  CONSTRAINT companies_currency_fkey FOREIGN KEY (currency) REFERENCES public.currencies (code),
  CONSTRAINT check_completeness_status CHECK (
    (data_completeness_status IN ('INITIAL', 'PARTIAL', 'COMPLETE', 'CURRENT'))
  ),
  CONSTRAINT check_fiscal_quarter CHECK (
    ((last_refreshed_fiscal_quarter IS NULL) OR ((last_refreshed_fiscal_quarter >= 1) AND (last_refreshed_fiscal_quarter <= 4)))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_companies_next_earnings_date ON public.companies USING btree (next_earnings_date) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_companies_data_completeness_status ON public.companies USING btree (data_completeness_status) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_companies_next_earnings_with_status ON public.companies USING btree (next_earnings_date, data_completeness_status) TABLESPACE pg_default WHERE (next_earnings_date IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_companies_exchange ON public.companies USING btree (exchange) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_companies_sector ON public.companies USING btree (sector) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_companies_industry ON public.companies USING btree (industry) TABLESPACE pg_default;

CREATE TRIGGER tr_update_companies_at BEFORE UPDATE ON public.companies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 4. portfolio_brokerages
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_brokerages (
  brokerage_id serial NOT NULL,
  brokerage_code character varying(50) NOT NULL,
  brokerage_name character varying(100) NOT NULL,
  country_code character varying(10) NOT NULL DEFAULT 'CA'::character varying,
  is_active boolean NOT NULL DEFAULT true,
  parser_class character varying(100) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT portfolio_brokerages_pkey PRIMARY KEY (brokerage_id),
  CONSTRAINT portfolio_brokerages_brokerage_code_unique UNIQUE (brokerage_code)
) TABLESPACE pg_default;

-- ============================================================================
-- 5. portfolio_accounts
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_accounts (
  account_id serial NOT NULL,
  user_id integer NOT NULL,
  brokerage_id integer NULL,
  account_external_id text NULL,
  account_name character varying(100) NOT NULL,
  account_type character varying(50) NOT NULL,
  currency character varying(3) NOT NULL DEFAULT 'USD'::character varying,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  last_import_at timestamp with time zone NULL,
  CONSTRAINT portfolio_accounts_pkey PRIMARY KEY (account_id),
  CONSTRAINT fk_portfolio_accounts_user FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE,
  CONSTRAINT fk_portfolio_accounts_brokerage FOREIGN KEY (brokerage_id) REFERENCES public.portfolio_brokerages (brokerage_id)
) TABLESPACE pg_default;

-- ============================================================================
-- 6. portfolio_holdings
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_holdings (
  holding_id serial NOT NULL,
  account_id integer NOT NULL,
  company_id integer NOT NULL,
  symbol character varying(20) NOT NULL,
  quantity numeric(15, 6) NOT NULL DEFAULT 0,
  average_cost numeric(15, 6) NOT NULL DEFAULT 0,
  total_cost numeric(15, 2) NOT NULL DEFAULT 0,
  realized_gain_loss numeric(15, 2) NOT NULL DEFAULT 0,
  currency character varying(3) NULL DEFAULT 'USD'::character varying,
  first_purchase_date date NULL,
  last_transaction_date date NULL,
  computed_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  exchange_override character varying(10) NULL,
  CONSTRAINT portfolio_holdings_pkey PRIMARY KEY (holding_id),
  CONSTRAINT fk_portfolio_holdings_account FOREIGN KEY (account_id) REFERENCES public.portfolio_accounts (account_id) ON DELETE CASCADE,
  CONSTRAINT fk_portfolio_holdings_company FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_account_id ON public.portfolio_holdings USING btree (account_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_company_id ON public.portfolio_holdings USING btree (company_id) TABLESPACE pg_default;

-- ============================================================================
-- 7. portfolio_transactions
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_transactions (
  transaction_id serial NOT NULL,
  account_id integer NOT NULL,
  company_id integer NULL,
  transaction_date date NOT NULL,
  settlement_date date NULL,
  activity_type character varying(50) NOT NULL,
  activity_sub_type character varying(50) NULL,
  direction character varying(10) NULL,
  symbol character varying(50) NULL,
  security_name character varying(255) NULL,
  currency character varying(3) NULL,
  quantity numeric(15, 6) NULL,
  unit_price numeric(15, 6) NULL,
  commission numeric(15, 2) NULL DEFAULT 0,
  net_cash_amount numeric(15, 2) NULL,
  import_batch_id text NULL,
  raw_data jsonb NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  entry_source character varying(50) NULL,
  created_by_user_id integer NULL,
  CONSTRAINT portfolio_transactions_pkey PRIMARY KEY (transaction_id),
  CONSTRAINT fk_portfolio_transactions_account FOREIGN KEY (account_id) REFERENCES public.portfolio_accounts (account_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_account_id ON public.portfolio_transactions USING btree (account_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_company_id ON public.portfolio_transactions USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_date ON public.portfolio_transactions USING btree (transaction_date) TABLESPACE pg_default;
CREATE UNIQUE INDEX IF NOT EXISTS uq_transaction_fingerprint ON public.portfolio_transactions (account_id, transaction_date, symbol, quantity, net_cash_amount) WHERE symbol IS NOT NULL;

-- ============================================================================
-- 8. portfolio_dividends
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_dividends (
  dividend_id serial NOT NULL,
  account_id integer NOT NULL,
  company_id integer NULL,
  transaction_id integer NULL,
  symbol character varying(20) NULL,
  payment_date date NOT NULL,
  amount numeric(15, 2) NOT NULL,
  currency character varying(3) NULL,
  fiscal_year integer NOT NULL,
  fiscal_month integer NOT NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT portfolio_dividends_pkey PRIMARY KEY (dividend_id),
  CONSTRAINT fk_portfolio_dividends_account FOREIGN KEY (account_id) REFERENCES public.portfolio_accounts (account_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_portfolio_dividends_account_year ON public.portfolio_dividends (account_id, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_portfolio_dividends_account_id ON public.portfolio_dividends USING btree (account_id) TABLESPACE pg_default;

-- ============================================================================
-- 9. portfolio_events
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  event_version INT NOT NULL DEFAULT 1,
  aggregate_id TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  data JSONB NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  idempotency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) TABLESPACE pg_default;

CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_events_idempotency ON public.portfolio_events (idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_portfolio_events_aggregate ON public.portfolio_events (aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_events_created ON public.portfolio_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_events_type ON public.portfolio_events (event_type);

-- ============================================================================
-- 10. portfolio_snapshots
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_snapshots (
  id bigserial NOT NULL,
  account_id integer NOT NULL,
  snapshot_date date NOT NULL,
  total_value numeric(15, 2) NOT NULL,
  holdings_market_value numeric(15, 2) NOT NULL DEFAULT 0.00,
  cost_basis numeric(15, 2) NOT NULL,
  cash_balance numeric(15, 2) NOT NULL DEFAULT 0.00,
  net_deposits numeric(15, 2) NOT NULL DEFAULT 0.00,
  holdings_json jsonb NULL,
  data_quality_flag text NOT NULL DEFAULT 'OK',
  job_id text NOT NULL DEFAULT '',
  computed_at timestamp with time zone NOT NULL DEFAULT NOW(),
  created_at timestamp with time zone NOT NULL DEFAULT NOW(),
  CONSTRAINT portfolio_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT fk_portfolio_snapshots_account FOREIGN KEY (account_id) REFERENCES public.portfolio_accounts (account_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_snapshots_account_date ON public.portfolio_snapshots (account_id, snapshot_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_account_date_unique ON public.portfolio_snapshots (account_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_quality ON public.portfolio_snapshots (data_quality_flag) WHERE data_quality_flag != 'OK';

ALTER TABLE public.portfolio_snapshots ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 11. portfolio_performance
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_performance (
  snapshot_id serial NOT NULL,
  account_id integer NOT NULL,
  snapshot_date date NOT NULL,
  total_value numeric(15, 2) NOT NULL,
  cost_basis numeric(15, 2) NOT NULL DEFAULT 0,
  net_deposits numeric(15, 2) NOT NULL DEFAULT 0,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT portfolio_performance_pkey PRIMARY KEY (snapshot_id),
  CONSTRAINT fk_portfolio_performance_account FOREIGN KEY (account_id) REFERENCES public.portfolio_accounts (account_id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- ============================================================================
-- 12. portfolio_import_history
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_import_history (
  import_id serial NOT NULL,
  user_id integer NOT NULL,
  brokerage_id integer NULL,
  import_batch_id text NOT NULL,
  csv_hash text NULL,
  csv_filename text NULL,
  csv_size_bytes integer NULL,
  total_rows integer NOT NULL DEFAULT 0,
  imported_rows integer NOT NULL DEFAULT 0,
  duplicate_rows integer NULL DEFAULT 0,
  error_rows integer NULL DEFAULT 0,
  account_filter text NULL,
  accounts_created integer NULL DEFAULT 0,
  accounts_updated integer NULL DEFAULT 0,
  symbols_created integer NULL DEFAULT 0,
  status character varying(20) NOT NULL DEFAULT 'pending'::character varying,
  error_message text NULL,
  started_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at timestamp with time zone NULL,
  rows_parsed integer NULL DEFAULT 0,
  CONSTRAINT portfolio_import_history_pkey PRIMARY KEY (import_id),
  CONSTRAINT portfolio_import_history_status_check CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  CONSTRAINT fk_portfolio_import_user FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE,
  CONSTRAINT fk_portfolio_import_brokerage FOREIGN KEY (brokerage_id) REFERENCES public.portfolio_brokerages (brokerage_id)
) TABLESPACE pg_default;

-- ============================================================================
-- 13. portfolio_user_import_history (VIEW — not a real table)
-- ============================================================================

-- ============================================================================
-- 14. accounts
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.accounts (
  id serial NOT NULL,
  user_id integer NOT NULL,
  account_name character varying(100) NOT NULL,
  account_type character varying(50) NOT NULL,
  currency character varying(3) NOT NULL DEFAULT 'USD'::character varying,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT accounts_pkey PRIMARY KEY (id),
  CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- ============================================================================
-- 15. balance_sheets
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.balance_sheets (
  bs_id serial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  fiscal_quarter smallint NULL,
  period_end_date date NOT NULL,
  total_assets numeric(15, 2) NULL,
  current_assets numeric(15, 2) NULL,
  cash_and_cash_equivalents numeric(15, 2) NULL,
  accounts_receivable numeric(15, 2) NULL,
  inventory numeric(15, 2) NULL,
  property_plant_equipment_net numeric(15, 2) NULL,
  intangible_assets numeric(15, 2) NULL,
  goodwill numeric(15, 2) NULL,
  total_liabilities numeric(15, 2) NULL,
  current_liabilities numeric(15, 2) NULL,
  accounts_payable numeric(15, 2) NULL,
  short_term_debt numeric(15, 2) NULL,
  long_term_debt numeric(15, 2) NULL,
  total_debt numeric(15, 2) NULL,
  shareholders_equity numeric(15, 2) NULL,
  retained_earnings numeric(15, 2) NULL,
  common_stock numeric(15, 2) NULL,
  currency character varying(3) NULL,
  data_source character varying(50) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  long_term_investments numeric(15, 2) NULL,
  other_non_current_assets numeric(15, 2) NULL,
  other_current_liabilities numeric(15, 2) NULL,
  minority_interest numeric(15, 2) NULL,
  total_liabilities_and_equity numeric(15, 2) NULL,
  confidence_score double precision NOT NULL DEFAULT 1.0,
  last_validated_at timestamp with time zone NULL,
  validation_notes text NULL,
  shares_outstanding bigint NULL,
  invested_capital numeric(15, 2) NULL,
  capital_lease_obligations numeric(15, 2) NULL,
  total_non_current_liabilities numeric(15, 2) NULL,
  total_non_current_assets numeric(15, 2) NULL,
  tangible_book_value numeric(15, 2) NULL,
  deferred_revenue_current numeric(15, 2) NULL,
  deferred_revenue_non_current numeric(15, 2) NULL,
  other_current_assets numeric(15, 2) NULL,
  CONSTRAINT balance_sheets_pkey PRIMARY KEY (bs_id),
  CONSTRAINT uq_balance_sheets_company_fiscal UNIQUE (company_id, fiscal_year, fiscal_quarter),
  CONSTRAINT balance_sheets_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_balance_confidence CHECK (
    ((confidence_score >= (0.0)::double precision) AND (confidence_score <= (1.0)::double precision))
  ),
  CONSTRAINT check_balance_data_source CHECK (
    (data_source IN ('defeat_beta', 'defeatbeta', 'yfinance', 'yfinance_backfill', 'manual', 'external_api', 'stockdex', 'edgar', 'derived'))
  ),
  CONSTRAINT check_fiscal_quarter_bs CHECK (
    ((fiscal_quarter IS NULL) OR ((fiscal_quarter >= 1) AND (fiscal_quarter <= 4)))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_balance_sheets_company_id ON public.balance_sheets USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_balance_sheets_fiscal_year ON public.balance_sheets USING btree (fiscal_year) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_balance_sheets_data_source ON public.balance_sheets USING btree (data_source) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_balance_sheets_low_confidence ON public.balance_sheets USING btree (confidence_score) TABLESPACE pg_default WHERE (confidence_score < (0.8)::double precision);

CREATE TRIGGER update_balance_sheets_updated_at BEFORE UPDATE ON public.balance_sheets FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 16. cash_flow_statements
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.cash_flow_statements (
  cf_id serial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  fiscal_quarter smallint NULL,
  period_end_date date NOT NULL,
  cash_from_operating_activities numeric(15, 2) NULL,
  net_income numeric(15, 2) NULL,
  depreciation_amortization numeric(15, 2) NULL,
  change_in_working_capital numeric(15, 2) NULL,
  deferred_taxes numeric(15, 2) NULL,
  stock_based_compensation numeric(15, 2) NULL,
  capital_expenditures numeric(15, 2) NULL,
  acquisitions numeric(15, 2) NULL,
  asset_sales numeric(15, 2) NULL,
  investment_purchases numeric(15, 2) NULL,
  debt_issued numeric(15, 2) NULL,
  debt_repayment numeric(15, 2) NULL,
  dividends_paid numeric(15, 2) NULL,
  share_repurchases numeric(15, 2) NULL,
  share_issuance numeric(15, 2) NULL,
  currency character varying(3) NULL,
  data_source character varying(50) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  cash_from_investing_activities numeric(15, 2) NULL,
  cash_from_financing_activities numeric(15, 2) NULL,
  confidence_score double precision NOT NULL DEFAULT 1.0,
  last_validated_at timestamp with time zone NULL,
  validation_notes text NULL,
  net_change_in_cash numeric(15, 2) NULL,
  effect_of_fx_on_cash numeric(15, 2) NULL,
  beginning_cash numeric(15, 2) NULL,
  ending_cash numeric(15, 2) NULL,
  short_term_debt_net_change numeric(15, 2) NULL,
  asset_impairment_charge numeric(15, 2) NULL,
  free_cash_flow numeric(15, 2) NULL,
  CONSTRAINT cash_flow_statements_pkey PRIMARY KEY (cf_id),
  CONSTRAINT uq_cash_flows_company_fiscal UNIQUE (company_id, fiscal_year, fiscal_quarter),
  CONSTRAINT cash_flow_statements_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_cashflow_confidence CHECK (
    ((confidence_score >= (0.0)::double precision) AND (confidence_score <= (1.0)::double precision))
  ),
  CONSTRAINT check_cashflow_data_source CHECK (
    (data_source IN ('defeat_beta', 'defeatbeta', 'yfinance', 'yfinance_backfill', 'manual', 'external_api', 'stockdex', 'edgar', 'derived'))
  ),
  CONSTRAINT check_fiscal_quarter_cf CHECK (
    ((fiscal_quarter IS NULL) OR ((fiscal_quarter >= 1) AND (fiscal_quarter <= 4)))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_cash_flows_company_id ON public.cash_flow_statements USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_cash_flows_fiscal_year ON public.cash_flow_statements USING btree (fiscal_year) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_cash_flow_statements_data_source ON public.cash_flow_statements USING btree (data_source) TABLESPACE pg_default;

CREATE TRIGGER update_cash_flow_updated_at BEFORE UPDATE ON public.cash_flow_statements FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 17. financial_ratios
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.financial_ratios (
  ratio_id serial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  period_end_date date NULL,
  roic numeric(10, 6) NULL,
  roe numeric(10, 6) NULL,
  roa numeric(10, 6) NULL,
  gross_margin numeric(10, 6) NULL,
  operating_margin numeric(10, 6) NULL,
  ebitda_margin numeric(10, 6) NULL,
  net_margin numeric(10, 6) NULL,
  fcf_margin numeric(10, 6) NULL,
  free_cash_flow numeric(20, 2) NULL,
  fcf_conversion numeric(10, 6) NULL,
  dividend_payout_ratio numeric(10, 6) NULL,
  fcf_dividend_payout_ratio numeric(10, 6) NULL,
  dividend_coverage_fcf numeric(10, 6) NULL,
  debt_to_equity numeric(10, 6) NULL,
  debt_to_assets numeric(10, 6) NULL,
  long_term_debt_to_equity numeric(10, 6) NULL,
  long_term_debt_to_assets numeric(10, 6) NULL,
  interest_coverage numeric(10, 6) NULL,
  current_ratio numeric(10, 6) NULL,
  quick_ratio numeric(10, 6) NULL,
  asset_turnover numeric(10, 6) NULL,
  inventory_turnover numeric(10, 6) NULL,
  revenue_per_share numeric(12, 4) NULL,
  ocf_per_share numeric(12, 4) NULL,
  fcf_per_share numeric(12, 4) NULL,
  ebit_per_share numeric(12, 4) NULL,
  ebitda_per_share numeric(12, 4) NULL,
  book_value_per_share numeric(12, 4) NULL,
  tangible_book_value_per_share numeric(12, 4) NULL,
  cash_per_share numeric(12, 4) NULL,
  total_debt_per_share numeric(12, 4) NULL,
  working_capital_per_share numeric(12, 4) NULL,
  capex_per_share numeric(12, 4) NULL,
  computed_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  source_version_tag text NULL,
  data_source character varying(50) NULL,
  confidence_score double precision NOT NULL DEFAULT 1.0,
  validation_notes text NULL,
  fiscal_quarter smallint NULL,
  piotroski_score double precision NULL,
  altman_z_score double precision NULL,
  trailing_pe numeric(10, 4) NULL,
  quarter_end_price numeric(12, 4) NULL,
  market_cap numeric(20, 2) NULL,
  enterprise_value numeric(20, 2) NULL,
  ev_ebitda numeric(20, 4) NULL,
  price_to_fcf numeric(20, 4) NULL,
  CONSTRAINT financial_ratios_pkey PRIMARY KEY (ratio_id),
  CONSTRAINT uq_financial_ratios_company_fiscal UNIQUE (company_id, fiscal_year, fiscal_quarter),
  CONSTRAINT financial_ratios_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_financial_ratios_company_id ON public.financial_ratios USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_financial_ratios_fiscal_year ON public.financial_ratios USING btree (fiscal_year) TABLESPACE pg_default;

-- ============================================================================
-- 18. derived_financial_metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.derived_financial_metrics (
  metric_id bigserial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  period_end_date date NULL,
  roic numeric(10, 6) NULL,
  roe numeric(10, 6) NULL,
  gross_margin numeric(10, 6) NULL,
  operating_margin numeric(10, 6) NULL,
  net_margin numeric(10, 6) NULL,
  fcf_margin numeric(10, 6) NULL,
  free_cash_flow numeric(20, 2) NULL,
  dividend_payout_ratio numeric(10, 6) NULL,
  fcf_dividend_payout_ratio numeric(10, 6) NULL,
  dividend_coverage_fcf numeric(10, 6) NULL,
  computed_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source_version_tag text NULL,
  data_source character varying(50) NOT NULL DEFAULT 'derived'::character varying,
  confidence_score double precision NOT NULL DEFAULT 1.0,
  validation_notes text NULL,
  fcf_conversion numeric(10, 6) NULL,
  debt_to_equity numeric(10, 6) NULL,
  interest_coverage numeric(10, 6) NULL,
  CONSTRAINT derived_financial_metrics_pkey PRIMARY KEY (metric_id),
  CONSTRAINT uq_derived_fin_metrics UNIQUE (company_id, fiscal_year),
  CONSTRAINT derived_financial_metrics_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_dfm_company_year ON public.derived_financial_metrics USING btree (company_id, fiscal_year DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_dfm_roic ON public.derived_financial_metrics USING btree (roic) TABLESPACE pg_default WHERE (roic IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_dfm_roe ON public.derived_financial_metrics USING btree (roe) TABLESPACE pg_default WHERE (roe IS NOT NULL);

-- ============================================================================
-- 19. earnings
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.earnings (
  earnings_id serial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  fiscal_quarter smallint NULL,
  period_end_date date NOT NULL,
  announcement_date date NULL,
  eps_reported_basic numeric(10, 4) NULL,
  eps_reported_diluted numeric(10, 4) NULL,
  eps_estimate numeric(10, 4) NULL,
  eps_surprise_amount numeric(10, 4) NULL,
  eps_surprise_percent numeric(8, 3) NULL,
  revenue_reported numeric(18, 2) NULL,
  revenue_estimate numeric(18, 2) NULL,
  revenue_surprise_amount numeric(18, 2) NULL,
  revenue_surprise_percent numeric(8, 3) NULL,
  shares_outstanding_basic bigint NULL,
  shares_outstanding_diluted bigint NULL,
  currency character(3) NULL,
  data_source character varying(50) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  confidence_score double precision NOT NULL DEFAULT 1.0,
  last_validated_at timestamp with time zone NULL,
  validation_notes text NULL,
  CONSTRAINT earnings_pkey PRIMARY KEY (earnings_id),
  CONSTRAINT uq_earnings_company_fiscal UNIQUE (company_id, fiscal_year, fiscal_quarter),
  CONSTRAINT earnings_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_earnings_confidence CHECK (
    ((confidence_score >= (0.0)::double precision) AND (confidence_score <= (1.0)::double precision))
  ),
  CONSTRAINT check_earnings_data_source CHECK (
    (data_source IN ('defeat_beta', 'defeatbeta', 'yfinance', 'yfinance_backfill', 'manual', 'external_api', 'stockdex', 'edgar', 'derived'))
  ),
  CONSTRAINT earnings_fiscal_quarter_check CHECK (
    (((fiscal_quarter >= 1) AND (fiscal_quarter <= 4)) OR (fiscal_quarter IS NULL))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_earnings_data_source ON public.earnings USING btree (data_source) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_earnings_company_year_quarter ON public.earnings USING btree (company_id, fiscal_year DESC, fiscal_quarter DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_earnings_announcement_date ON public.earnings USING btree (announcement_date DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_earnings_eps_surprise ON public.earnings USING btree (eps_surprise_percent) TABLESPACE pg_default WHERE (eps_surprise_percent IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_earnings_company_id ON public.earnings USING btree (company_id) TABLESPACE pg_default;

CREATE TRIGGER update_earnings_updated_at BEFORE UPDATE ON public.earnings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 19b. income_statements
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.income_statements (
  is_id serial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  fiscal_quarter integer NULL,
  period_end_date date NOT NULL,
  revenue numeric(15, 2) NULL,
  cost_of_goods_sold numeric(15, 2) NULL,
  gross_profit numeric(15, 2) NULL,
  operating_expenses numeric(15, 2) NULL,
  rd_expenses numeric(15, 2) NULL,
  sga_expenses numeric(15, 2) NULL,
  operating_income numeric(15, 2) NULL,
  interest_expense numeric(15, 2) NULL,
  tax_expense numeric(15, 2) NULL,
  net_income numeric(15, 2) NULL,
  ebitda numeric(15, 2) NULL,
  currency character varying(3) NULL DEFAULT 'USD'::character varying,
  data_source character varying(50) NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  non_operating_income_expense numeric(15, 2) NULL,
  pretax_income numeric(15, 2) NULL,
  equity_in_earnings numeric(15, 2) NULL,
  minority_interest numeric(15, 2) NULL,
  income_from_continuing_operations numeric(15, 2) NULL,
  discontinued_operations numeric(15, 2) NULL,
  net_income_to_common numeric(15, 2) NULL,
  preferred_dividends numeric(15, 2) NULL,
  ebit numeric(15, 2) NULL,
  confidence_score double precision NULL DEFAULT 1.0,
  last_validated_at timestamp with time zone NULL,
  validation_notes text NULL,
  eps_basic numeric(10, 4) NULL,
  eps_diluted numeric(10, 4) NULL,
  shares_outstanding_basic bigint NULL,
  shares_outstanding_diluted bigint NULL,
  interest_income numeric(15, 2) NULL,
  effective_tax_rate numeric(8, 6) NULL,
  total_unusual_items numeric(15, 2) NULL,
  special_charges numeric(15, 2) NULL,
  CONSTRAINT income_statements_pkey PRIMARY KEY (is_id),
  CONSTRAINT uq_income_statements_company_fiscal UNIQUE (company_id, fiscal_year, fiscal_quarter),
  CONSTRAINT income_statements_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_is_confidence CHECK (
    ((confidence_score >= (0.0)::double precision) AND (confidence_score <= (1.0)::double precision))
  ),
  CONSTRAINT check_is_data_source CHECK (
    (data_source IN ('defeat_beta', 'defeatbeta', 'yfinance', 'yfinance_backfill', 'manual', 'external_api', 'stockdex', 'edgar', 'derived'))
  ),
  CONSTRAINT check_is_fiscal_quarter CHECK (
    (((fiscal_quarter >= 1) AND (fiscal_quarter <= 4)) OR (fiscal_quarter IS NULL))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_income_statements_company_id ON public.income_statements USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_income_statements_fiscal_year ON public.income_statements USING btree (fiscal_year) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_income_statements_data_source ON public.income_statements USING btree (data_source) TABLESPACE pg_default;

CREATE TRIGGER update_income_statements_updated_at BEFORE UPDATE ON public.income_statements FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 20. splits
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.splits (
  split_id integer NOT NULL,
  company_id integer NOT NULL,
  report_date date NOT NULL,
  split_factor character varying(20) NOT NULL,
  reverse_split boolean NULL DEFAULT false,
  data_source character varying(50) NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  processed boolean DEFAULT false,
  CONSTRAINT splits_pkey PRIMARY KEY (split_id),
  CONSTRAINT splits_company_date_unique UNIQUE (company_id, report_date),
  CONSTRAINT splits_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_splits_company_date ON public.splits USING btree (company_id, report_date DESC) TABLESPACE pg_default;

-- ============================================================================
-- 21. analyst_eps_estimates
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.analyst_eps_estimates (
  estimate_id bigserial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  estimate_date date NOT NULL,
  eps_estimate numeric(12, 4) NOT NULL,
  number_of_analysts integer NULL,
  period_type character varying(20) NULL DEFAULT 'annual'::character varying,
  provider character varying(50) NOT NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT analyst_eps_estimates_pkey PRIMARY KEY (estimate_id),
  CONSTRAINT analyst_eps_estimates_uq UNIQUE (company_id, fiscal_year, provider, estimate_date),
  CONSTRAINT analyst_eps_estimates_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_analyst_eps_company_year ON public.analyst_eps_estimates USING btree (company_id, fiscal_year) TABLESPACE pg_default;

-- ============================================================================
-- 22. dividend_history
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.dividend_history (
  dividend_id serial NOT NULL,
  company_id integer NOT NULL,
  ex_dividend_date date NOT NULL,
  payment_date date NULL,
  record_date date NULL,
  dividend_amount numeric(10, 4) NULL,
  dividend_type character varying(30) NULL DEFAULT 'regular'::character varying,
  currency character(3) NULL DEFAULT 'USD'::bpchar,
  frequency character varying(20) NULL,
  data_source character varying(50) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  confidence_score double precision NOT NULL DEFAULT 1.0,
  last_validated_at timestamp with time zone NULL,
  validation_notes text NULL,
  CONSTRAINT dividend_history_pkey PRIMARY KEY (dividend_id),
  CONSTRAINT dividend_history_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_dividend_confidence CHECK (
    ((confidence_score >= (0.0)::double precision) AND (confidence_score <= (1.0)::double precision))
  ),
  CONSTRAINT check_dividend_data_source CHECK (
    (data_source IN ('defeat_beta', 'defeatbeta', 'yfinance', 'yfinance_backfill', 'manual', 'external_api', 'stockdex', 'edgar', 'derived'))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_dividend_history_data_source ON public.dividend_history USING btree (data_source) TABLESPACE pg_default;
CREATE UNIQUE INDEX IF NOT EXISTS unique_dividend_per_company_exdate ON public.dividend_history USING btree (company_id, ex_dividend_date) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_div_hist_comp_exdate_desc ON public.dividend_history USING btree (company_id, ex_dividend_date DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_div_hist_payment_date ON public.dividend_history USING btree (payment_date DESC) TABLESPACE pg_default;

CREATE TRIGGER update_dividend_history_updated_at BEFORE UPDATE ON public.dividend_history FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 23. dividend_metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.dividend_metrics (
  metric_id serial NOT NULL,
  company_id integer NULL,
  fiscal_year integer NULL,
  annual_dps numeric(10, 4) NULL,
  dividend_yield numeric(5, 2) NULL,
  dividend_growth_rate_3yr numeric(5, 2) NULL,
  dividend_growth_rate_5yr numeric(5, 2) NULL,
  dividend_growth_rate_10yr numeric(5, 2) NULL,
  consecutive_years_paid integer NULL,
  fcfe_coverage_ratio numeric(5, 2) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  cash_dividend_payout_ratio numeric(10, 2) NULL,
  ebitda_dividend_coverage numeric(10, 2) NULL,
  retention_ratio numeric(10, 2) NULL,
  CONSTRAINT dividend_metrics_pkey PRIMARY KEY (metric_id),
  CONSTRAINT uq_dividend_metrics_company_year UNIQUE (company_id, fiscal_year)
) TABLESPACE pg_default;

-- ============================================================================
-- 24. upcoming_dividend_events
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.upcoming_dividend_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id INTEGER NOT NULL REFERENCES public.companies(company_id),
  data_source VARCHAR(50) NOT NULL,
  ex_dividend_date DATE NOT NULL,
  trust_score DECIMAL(3,2) NOT NULL DEFAULT 0.0,
  status VARCHAR(20) NOT NULL DEFAULT 'predicted' CHECK (status IN ('predicted', 'provider_reported')),
  source_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT unique_source_opinion UNIQUE (company_id, data_source)
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_upcoming_events_company ON public.upcoming_dividend_events (company_id);
CREATE INDEX IF NOT EXISTS idx_upcoming_events_date ON public.upcoming_dividend_events (ex_dividend_date);

-- ============================================================================
-- 25. current_market_data
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.current_market_data (
  company_id integer NOT NULL,
  current_price numeric(10, 4) NOT NULL,
  open_price numeric(10, 4) NULL,
  high_price numeric(10, 4) NULL,
  low_price numeric(10, 4) NULL,
  close_price numeric(10, 4) NULL,
  volume bigint NULL,
  market_state character varying(20) NULL,
  source character varying(50) NULL DEFAULT 'yfinance'::character varying,
  last_updated timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT current_market_data_pkey PRIMARY KEY (company_id),
  CONSTRAINT current_market_data_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- ============================================================================
-- 26. price_history
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.price_history (
  company_id integer NOT NULL,
  price_date date NOT NULL,
  open_price numeric(12, 4) NULL,
  close_price numeric(12, 4) NOT NULL,
  high_price numeric(12, 4) NULL,
  low_price numeric(12, 4) NULL,
  volume bigint NULL,
  data_source character varying(50) NOT NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT price_history_pk PRIMARY KEY (company_id, price_date),
  CONSTRAINT price_history_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_price_history_company_date_desc ON public.price_history USING btree (company_id, price_date DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_price_history_company_date ON public.price_history (company_id, price_date DESC);

-- ============================================================================
-- 27. price_sources
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.price_sources (
  id bigserial NOT NULL,
  company_id integer NOT NULL REFERENCES public.companies(company_id),
  exchange text NOT NULL,
  price numeric(12, 4) NULL,
  currency text NOT NULL DEFAULT 'USD',
  source text NOT NULL,
  fetched_at timestamptz NOT NULL DEFAULT NOW(),
  ttl_seconds integer NOT NULL DEFAULT 300,
  data_quality text NOT NULL DEFAULT 'OK',
  CONSTRAINT price_sources_pkey PRIMARY KEY (id),
  CONSTRAINT price_sources_company_exchange_unique UNIQUE (company_id, exchange)
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_price_sources_company_exchange ON public.price_sources (company_id, exchange);

ALTER TABLE public.price_sources ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 28. price_source_preferences
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.price_source_preferences (
  id bigserial NOT NULL,
  company_id integer NOT NULL REFERENCES public.companies(company_id),
  exchange text NOT NULL,
  preferred_source text NOT NULL,
  CONSTRAINT price_source_preferences_pkey PRIMARY KEY (id),
  CONSTRAINT price_source_preferences_company_exchange_unique UNIQUE (company_id, exchange)
) TABLESPACE pg_default;

ALTER TABLE public.price_source_preferences ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 29. data_conflicts
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.data_conflicts (
  conflict_id bigserial NOT NULL,
  company_id integer NOT NULL,
  fiscal_year integer NOT NULL,
  fiscal_quarter smallint NULL,
  field_name character varying(100) NOT NULL,
  existing_value numeric NULL,
  existing_source character varying(50) NOT NULL,
  new_value numeric NULL,
  new_source character varying(50) NOT NULL,
  percent_diff double precision NOT NULL,
  resolved boolean NULL DEFAULT false,
  resolution_notes text NULL,
  resolution_choice character varying(50) NULL,
  detected_at timestamp with time zone NOT NULL,
  resolved_at timestamp with time zone NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT data_conflicts_pkey PRIMARY KEY (conflict_id),
  CONSTRAINT fk_data_conflicts_company FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_conflict_values CHECK (
    (((existing_value IS NOT NULL) OR (new_value IS NOT NULL)) AND (percent_diff >= (0)::double precision))
  ),
  CONSTRAINT check_resolution_choice CHECK (
    ((resolution_choice IS NULL) OR (resolution_choice IN ('keep_existing', 'use_new', 'manual_review')))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_data_conflicts_unresolved ON public.data_conflicts USING btree (resolved, detected_at DESC) TABLESPACE pg_default WHERE (resolved = false);
CREATE INDEX IF NOT EXISTS idx_data_conflicts_company ON public.data_conflicts USING btree (company_id, detected_at DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_data_conflicts_percent_diff ON public.data_conflicts USING btree (percent_diff DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_data_conflicts_resolved_at ON public.data_conflicts USING btree (resolved_at) TABLESPACE pg_default WHERE (resolved = true);

-- ============================================================================
-- 30. scheduler_locks
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.scheduler_locks (
  lock_id character varying(100) NOT NULL,
  company_id integer NOT NULL,
  acquired_at timestamp with time zone NOT NULL,
  expires_at timestamp with time zone NOT NULL,
  lock_type character varying(50) NULL DEFAULT 'financial_refresh'::character varying,
  CONSTRAINT scheduler_locks_pkey PRIMARY KEY (lock_id),
  CONSTRAINT scheduler_locks_company_id_key UNIQUE (company_id),
  CONSTRAINT fk_scheduler_locks_company FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT check_lock_expiry CHECK ((expires_at > acquired_at))
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_scheduler_locks_company_id ON public.scheduler_locks USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_scheduler_locks_expires_at ON public.scheduler_locks USING btree (expires_at) TABLESPACE pg_default;

-- ============================================================================
-- 31. intrinsic_value_analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.intrinsic_value_analysis (
  analysis_id serial NOT NULL,
  company_id integer NULL,
  growth_rate numeric(10, 4) NULL,
  current_eps numeric(15, 4) NULL,
  future_pe numeric(10, 2) NULL,
  future_price numeric(15, 2) NULL,
  sticker_price numeric(15, 2) NULL,
  mos_price numeric(15, 2) NULL,
  last_updated timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT intrinsic_value_analysis_pkey PRIMARY KEY (analysis_id),
  CONSTRAINT intrinsic_value_analysis_company_id_key UNIQUE (company_id),
  CONSTRAINT intrinsic_value_analysis_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- ============================================================================
-- 32. industry_multiples
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.industry_multiples (
  industry_multiple_id serial NOT NULL,
  sector character varying(100) NULL,
  industry character varying(100) NULL,
  calculation_date date NULL,
  avg_pe numeric(10, 2) NULL,
  avg_pb numeric(10, 2) NULL,
  avg_ps numeric(10, 2) NULL,
  avg_pcf numeric(10, 2) NULL,
  avg_peg numeric(10, 2) NULL,
  avg_ev_ebitda numeric(10, 2) NULL,
  avg_ev_revenue numeric(10, 2) NULL,
  avg_ev_fcf numeric(10, 2) NULL,
  median_pe numeric(10, 2) NULL,
  median_pb numeric(10, 2) NULL,
  median_ps numeric(10, 2) NULL,
  median_ev_ebitda numeric(10, 2) NULL,
  median_ev_revenue numeric(10, 2) NULL,
  avg_eps_growth numeric(5, 2) NULL,
  median_eps_growth numeric(5, 2) NULL,
  avg_revenue_growth numeric(5, 2) NULL,
  avg_roic numeric(10, 2) NULL,
  avg_gross_margin numeric(10, 2) NULL,
  sample_size integer NULL,
  data_source character varying(50) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT industry_multiples_pkey PRIMARY KEY (industry_multiple_id)
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_sector_industry_date ON public.industry_multiples USING btree (sector, industry, calculation_date) TABLESPACE pg_default;

-- ============================================================================
-- 33. ddm_valuations
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.ddm_valuations (
  ddm_id serial NOT NULL,
  company_id integer NULL,
  analysis_date date NULL,
  current_dps numeric(10, 4) NULL,
  next_year_dps numeric(10, 4) NULL,
  dividend_growth_rate numeric(5, 2) NULL,
  required_return numeric(5, 3) NULL,
  intrinsic_value_gordon numeric(10, 2) NULL,
  high_growth_years integer NULL,
  high_growth_rate numeric(5, 2) NULL,
  stable_growth_rate numeric(5, 2) NULL,
  intrinsic_value_multistage numeric(10, 2) NULL,
  current_stock_price numeric(10, 2) NULL,
  upside_downside_pct numeric(6, 2) NULL,
  analyst_name character varying(100) NULL,
  notes text NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT ddm_valuations_pkey PRIMARY KEY (ddm_id)
) TABLESPACE pg_default;

-- ============================================================================
-- 34. dcf_valuations
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.dcf_valuations (
  dcf_id serial NOT NULL,
  company_id integer NULL,
  analysis_date date NULL,
  forecast_years integer NULL,
  revenue_growth_rate numeric(5, 2) NULL,
  terminal_growth_rate numeric(5, 2) NULL,
  wacc_used numeric(5, 3) NULL,
  fcf_margin_assumption numeric(5, 2) NULL,
  total_pv_fcf numeric(15, 2) NULL,
  terminal_value numeric(15, 2) NULL,
  pv_terminal_value numeric(15, 2) NULL,
  enterprise_value_dcf numeric(15, 2) NULL,
  less_net_debt numeric(15, 2) NULL,
  equity_value numeric(15, 2) NULL,
  shares_outstanding bigint NULL,
  intrinsic_value_per_share numeric(10, 2) NULL,
  current_stock_price numeric(10, 2) NULL,
  upside_downside_pct numeric(6, 2) NULL,
  analyst_name character varying(100) NULL,
  sensitivity_scenarios jsonb NULL,
  notes text NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT dcf_valuations_pkey PRIMARY KEY (dcf_id)
) TABLESPACE pg_default;

-- ============================================================================
-- 35. valuation_method_defaults
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.valuation_method_defaults (
  method character varying(40) NOT NULL,
  params jsonb NOT NULL,
  updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT valuation_method_defaults_pkey PRIMARY KEY (method),
  CONSTRAINT valuation_method_defaults_method_check CHECK (
    (method IN ('rule1', 'ddm_gordon', 'ddm_two_stage', 'dcf', 'owner_earnings', 'relative', 'canslim', 'residual_income', 'magic_formula'))
  )
) TABLESPACE pg_default;

-- ============================================================================
-- 36. company_valuation_overrides
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.company_valuation_overrides (
  company_id integer NOT NULL,
  method character varying(40) NOT NULL,
  params jsonb NOT NULL,
  updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT company_valuation_overrides_pk PRIMARY KEY (company_id, method),
  CONSTRAINT company_valuation_overrides_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT company_valuation_overrides_method_check CHECK (
    (method IN ('rule1', 'ddm_gordon', 'ddm_two_stage', 'dcf', 'owner_earnings', 'relative', 'canslim', 'residual_income', 'magic_formula'))
  )
) TABLESPACE pg_default;

-- ============================================================================
-- 37. valuation_runs
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.valuation_runs (
  valuation_run_id bigserial NOT NULL,
  company_id integer NOT NULL,
  method character varying(40) NOT NULL,
  run_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  run_by_user_id integer NULL,
  input_snapshot jsonb NOT NULL,
  assumption_snapshot jsonb NOT NULL,
  output_snapshot jsonb NOT NULL,
  data_version_tag character varying(100) NULL,
  notes text NULL,
  CONSTRAINT valuation_runs_pkey PRIMARY KEY (valuation_run_id),
  CONSTRAINT valuation_runs_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT valuation_runs_run_by_user_id_fkey FOREIGN KEY (run_by_user_id) REFERENCES public.users (user_id),
  CONSTRAINT valuation_runs_method_check CHECK (
    (method IN ('rule1', 'ddm_gordon', 'ddm_two_stage', 'dcf', 'owner_earnings', 'relative', 'canslim', 'residual_income', 'magic_formula'))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_valuation_runs_company_method_date ON public.valuation_runs USING btree (company_id, method, run_at DESC) TABLESPACE pg_default;

-- ============================================================================
-- 38. company_summary
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.company_summary (
  summary_id integer NOT NULL,
  company_id integer NOT NULL,
  snapshot_date date NOT NULL DEFAULT CURRENT_DATE,
  market_cap numeric(20, 2) NULL,
  enterprise_value numeric(20, 2) NULL,
  shares_outstanding numeric(20, 2) NULL,
  implied_shares_outstanding numeric(20, 2) NULL,
  beta numeric(8, 4) NULL,
  trailing_pe numeric(10, 4) NULL,
  forward_pe numeric(10, 4) NULL,
  trailing_eps numeric(10, 4) NULL,
  forward_eps numeric(10, 4) NULL,
  enterprise_to_ebitda numeric(10, 4) NULL,
  enterprise_to_revenue numeric(10, 4) NULL,
  peg_ratio numeric(10, 4) NULL,
  currency character varying(5) NULL DEFAULT 'USD'::character varying,
  provider character varying(50) NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT company_summary_pkey PRIMARY KEY (summary_id),
  CONSTRAINT company_summary_unique UNIQUE (company_id, snapshot_date, provider),
  CONSTRAINT company_summary_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_company_summary_company_date ON public.company_summary USING btree (company_id, snapshot_date DESC) TABLESPACE pg_default;

-- ============================================================================
-- 39. valuation_diagnostics
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.valuation_diagnostics (
  diag_id bigserial NOT NULL,
  company_id integer NOT NULL,
  method character varying(40) NOT NULL,
  code character varying(40) NOT NULL,
  severity character varying(10) NOT NULL,
  message text NOT NULL,
  context jsonb NULL,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT valuation_diagnostics_pkey PRIMARY KEY (diag_id),
  CONSTRAINT valuation_diagnostics_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT valuation_diagnostics_severity_check CHECK (
    (severity IN ('critical', 'high', 'medium', 'low', 'info'))
  )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_valuation_diagnostics_company_method ON public.valuation_diagnostics USING btree (company_id, method, created_at DESC) TABLESPACE pg_default;

-- ============================================================================
-- 40. data_quality_events
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.data_quality_events (
  event_id bigserial NOT NULL,
  company_id integer NOT NULL,
  scope character varying(40) NOT NULL,
  metric character varying(60) NOT NULL,
  severity character varying(10) NOT NULL,
  message text NOT NULL,
  details jsonb NULL,
  detected_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT data_quality_events_pkey PRIMARY KEY (event_id),
  CONSTRAINT data_quality_events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_dqe_company_time ON public.data_quality_events USING btree (company_id, detected_at DESC) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_dqe_scope_metric ON public.data_quality_events USING btree (scope, metric) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_dqe_severity ON public.data_quality_events USING btree (severity) TABLESPACE pg_default;

-- ============================================================================
-- 41. moat_analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.moat_analysis (
  id bigserial PRIMARY KEY,
  company_id bigint NOT NULL REFERENCES public.companies(company_id) ON DELETE CASCADE,
  symbol text NOT NULL,
  roic double precision,
  wacc double precision,
  roic_minus_wacc double precision,
  gross_margin_pct double precision,
  operating_margin_pct double precision,
  net_margin_pct double precision,
  roic_5y_avg double precision,
  roic_5y_std double precision,
  roic_stability_score double precision,
  asset_turnover double precision,
  capital_efficiency_score double precision,
  moat_score double precision,
  moat_category text CHECK (moat_category IN ('Wide', 'Narrow', 'None', 'Unknown')),
  text_analysis_available boolean NOT NULL DEFAULT false,
  keyword_matches_count integer NOT NULL DEFAULT 0,
  sector text,
  sector_adjustment double precision DEFAULT 0.0,
  ai_narrative_available boolean NOT NULL DEFAULT false,
  fiscal_years_used integer NOT NULL DEFAULT 0,
  data_sources text NOT NULL DEFAULT 'database',
  quarters_used integer NOT NULL DEFAULT 0,
  fallbacks_used boolean NOT NULL DEFAULT false,
  computed_at timestamptz NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_moat_analysis_company UNIQUE (company_id)
);

CREATE INDEX IF NOT EXISTS idx_moat_analysis_symbol ON public.moat_analysis (symbol);
CREATE INDEX IF NOT EXISTS idx_moat_analysis_computed_at ON public.moat_analysis (computed_at DESC);

-- ============================================================================
-- 42. moat_keyword_evidence
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.moat_keyword_evidence (
  id bigserial PRIMARY KEY,
  company_id bigint NOT NULL REFERENCES public.companies(company_id) ON DELETE CASCADE,
  symbol text NOT NULL,
  filing_type text NOT NULL DEFAULT '10-K',
  filing_date date,
  accession_number text,
  section text,
  keyword text NOT NULL,
  keyword_group text NOT NULL,
  snippet text,
  relevance_score double precision DEFAULT 1.0,
  matched_at timestamptz NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_moat_keyword_evidence UNIQUE (company_id, filing_date, section, keyword, snippet)
);

CREATE INDEX IF NOT EXISTS idx_moat_evidence_company ON public.moat_keyword_evidence (company_id);
CREATE INDEX IF NOT EXISTS idx_moat_evidence_keyword_group ON public.moat_keyword_evidence (keyword_group);

-- ============================================================================
-- 43. moat_ai_narratives
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.moat_ai_narratives (
  id bigserial PRIMARY KEY,
  company_id bigint NOT NULL REFERENCES public.companies(company_id) ON DELETE CASCADE,
  symbol text NOT NULL,
  model text NOT NULL DEFAULT 'openrouter/default',
  narrative text NOT NULL,
  summary text,
  quant_snapshot jsonb,
  evidence_count integer NOT NULL DEFAULT 0,
  generated_at timestamptz NOT NULL DEFAULT NOW(),
  generation_time_ms integer,
  CONSTRAINT uq_moat_ai_company UNIQUE (company_id)
);

CREATE INDEX IF NOT EXISTS idx_moat_ai_symbol ON public.moat_ai_narratives (symbol);

-- ============================================================================
-- 44. revenue_forecast
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.revenue_forecast (
  forecast_id integer NOT NULL,
  company_id integer NOT NULL,
  report_date date NOT NULL,
  period_type character varying(20) NOT NULL,
  estimate_revenue_growth numeric(8, 4) NULL,
  number_of_analysts integer NULL,
  estimate_avg_revenue numeric(20, 2) NULL,
  estimate_high_revenue numeric(20, 2) NULL,
  estimate_low_revenue numeric(20, 2) NULL,
  year_ago_estimate_avg_revenue numeric(20, 2) NULL,
  currency character varying(5) NULL DEFAULT 'USD'::character varying,
  provider character varying(50) NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT revenue_forecast_pkey PRIMARY KEY (forecast_id),
  CONSTRAINT revenue_forecast_unique UNIQUE (company_id, report_date, period_type, provider),
  CONSTRAINT revenue_forecast_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_revenue_forecast_company_date ON public.revenue_forecast USING btree (company_id, report_date DESC) TABLESPACE pg_default;

-- ============================================================================
-- 45. earnings_forecast
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.earnings_forecast (
  earnings_forecast_id integer NOT NULL,
  company_id integer NOT NULL,
  report_date date NOT NULL,
  period_type character varying(20) NOT NULL,
  currency character varying(5) NULL DEFAULT 'USD'::character varying,
  estimate_eps_growth numeric(8, 4) NULL,
  estimate_avg_eps numeric(10, 4) NULL,
  estimate_high_eps numeric(10, 4) NULL,
  estimate_low_eps numeric(10, 4) NULL,
  number_of_analysts integer NULL,
  thirty_days_ago_estimate_avg_eps numeric(10, 4) NULL,
  sixty_days_ago_estimate_avg_eps numeric(10, 4) NULL,
  ninety_days_ago_estimate_avg_eps numeric(10, 4) NULL,
  year_ago_estimate_avg_eps numeric(10, 4) NULL,
  provider character varying(50) NULL DEFAULT 'defeatbeta'::character varying,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT earnings_forecast_pkey PRIMARY KEY (earnings_forecast_id),
  CONSTRAINT earnings_forecast_unique UNIQUE (company_id, report_date, period_type, provider),
  CONSTRAINT earnings_forecast_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_earnings_forecast_company_date ON public.earnings_forecast USING btree (company_id, report_date DESC) TABLESPACE pg_default;

-- ============================================================================
-- 46. watchlists
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.watchlists (
  id serial NOT NULL,
  user_id integer NOT NULL,
  watchlist_name character varying(100) NOT NULL DEFAULT 'My Watchlist'::character varying,
  description text NULL,
  is_default boolean NULL DEFAULT false,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT watchlists_pkey PRIMARY KEY (id),
  CONSTRAINT unique_user_watchlist_name UNIQUE (user_id, watchlist_name),
  CONSTRAINT watchlists_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE UNIQUE INDEX IF NOT EXISTS unique_default_watchlist_per_user ON public.watchlists USING btree (user_id) TABLESPACE pg_default WHERE (is_default = true);
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON public.watchlists USING btree (user_id) TABLESPACE pg_default;

CREATE TRIGGER trigger_watchlists_updated_at BEFORE UPDATE ON public.watchlists FOR EACH ROW EXECUTE FUNCTION update_watchlists_updated_at();

-- ============================================================================
-- 47. watchlist_items
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.watchlist_items (
  watchlist_item_id serial NOT NULL,
  watchlist_id integer NOT NULL,
  company_id integer NOT NULL,
  target_buy numeric(10, 2) NULL,
  target_sell numeric(10, 2) NULL,
  notes text NULL,
  position integer NOT NULL DEFAULT 0,
  added_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT watchlist_items_pkey PRIMARY KEY (watchlist_item_id),
  CONSTRAINT unique_watchlist_company UNIQUE (watchlist_id, company_id),
  CONSTRAINT watchlist_items_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE,
  CONSTRAINT watchlist_items_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists (id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON public.watchlist_items USING btree (watchlist_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_watchlist_items_company_id ON public.watchlist_items USING btree (company_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_watchlist_items_position ON public.watchlist_items USING btree (watchlist_id, "position") TABLESPACE pg_default;

CREATE TRIGGER trigger_watchlist_items_updated_at BEFORE UPDATE ON public.watchlist_items FOR EACH ROW EXECUTE FUNCTION update_watchlists_updated_at();

-- ============================================================================
-- 48. portfolio_cash_activity
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.portfolio_cash_activity (
  activity_id serial NOT NULL,
  account_id integer NOT NULL,
  activity_date date NOT NULL,
  activity_type character varying(50) NOT NULL,
  amount numeric(15, 2) NOT NULL,
  currency character varying(3) NULL,
  description text NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT portfolio_cash_activity_pkey PRIMARY KEY (activity_id),
  CONSTRAINT fk_portfolio_cash_activity_account FOREIGN KEY (account_id) REFERENCES public.portfolio_accounts (account_id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- ============================================================================
-- SCHEDULER / INFRASTRUCTURE TABLES
-- ============================================================================

-- ============================================================================
-- 49. jobs
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  resource_type TEXT NULL,
  resource_id TEXT NULL,
  dedupe_key TEXT NOT NULL,
  priority INT DEFAULT 50,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'succeeded', 'dead_letter', 'cancelled')),
  payload JSONB,
  not_before TIMESTAMPTZ,
  available_at TIMESTAMPTZ DEFAULT NOW(),
  lease_owner TEXT,
  lease_token UUID,
  leased_until TIMESTAMPTZ,
  attempts INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  last_error TEXT,
  last_error_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_jobs_dedupe ON public.jobs (dedupe_key) WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON public.jobs (status, priority DESC, available_at ASC) WHERE status = 'pending';

-- ============================================================================
-- 50. job_attempts
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.job_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES public.jobs(id),
  attempt INT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  error TEXT,
  duration_ms INT,
  UNIQUE (job_id, attempt)
);

-- ============================================================================
-- 51. scheduler_state
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.scheduler_state (
  scheduler_name TEXT PRIMARY KEY,
  enabled BOOLEAN DEFAULT true,
  interval_hours NUMERIC DEFAULT 24,
  last_planned_at TIMESTAMPTZ,
  last_status TEXT,
  last_error TEXT,
  next_due_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 52. scheduler_run_history
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.scheduler_run_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scheduler_name TEXT NOT NULL,
  planned_at TIMESTAMPTZ NOT NULL,
  jobs_enqueued INT DEFAULT 0,
  status TEXT,
  error TEXT,
  duration_ms INT
);

CREATE INDEX IF NOT EXISTS idx_run_history_scheduler ON public.scheduler_run_history (scheduler_name, planned_at DESC);

-- ============================================================================
-- 53. worker_heartbeats
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.worker_heartbeats (
  worker_id TEXT PRIMARY KEY,
  hostname TEXT,
  pid INT,
  started_at TIMESTAMPTZ,
  last_hb_at TIMESTAMPTZ DEFAULT NOW(),
  active_jobs INT DEFAULT 0
);

-- ============================================================================
-- 54. resource_locks
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.resource_locks (
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  lock_type TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  lease_token UUID NOT NULL,
  leased_until TIMESTAMPTZ NOT NULL,
  heartbeat_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (resource_type, resource_id, lock_type)
);

-- ============================================================================
-- 55. company_refresh_requests
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.company_refresh_requests (
  company_id INT NOT NULL,
  requested_at TIMESTAMPTZ DEFAULT NOW(),
  scopes TEXT[] NOT NULL,
  reasons TEXT[] NOT NULL,
  priority INT DEFAULT 50,
  processed BOOLEAN DEFAULT false,
  PRIMARY KEY (company_id, requested_at)
);

-- ============================================================================
-- EVENT SOURCING / PROJECTION TABLES
-- ============================================================================

-- ============================================================================
-- 56. event_sequence
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.event_sequence (
  seq_id bigserial PRIMARY KEY,
  event_id UUID NOT NULL REFERENCES public.portfolio_events(id),
  aggregate_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_sequence_created ON public.event_sequence (created_at);
CREATE INDEX IF NOT EXISTS idx_event_sequence_aggregate ON public.event_sequence (aggregate_id, seq_id);

-- ============================================================================
-- 57. projection_checkpoint
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.projection_checkpoint (
  id INTEGER PRIMARY KEY DEFAULT 1,
  last_seq_id BIGINT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- FX / MULTI-CURRENCY TABLES
-- ============================================================================

-- ============================================================================
-- 58. exchange_rates
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.exchange_rates (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL PRIMARY KEY,
  base_currency char(3) NOT NULL,
  target_currency char(3) NOT NULL,
  rate numeric(18, 8) NOT NULL,
  rate_date date NOT NULL,
  source text NOT NULL DEFAULT 'yfinance',
  fetched_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT unique_rate_per_day UNIQUE (base_currency, target_currency, rate_date),
  CONSTRAINT rate_positive CHECK (rate > 0),
  CONSTRAINT currencies_len CHECK (
    (length(base_currency) = 3) AND (length(target_currency) = 3)
  ),
  CONSTRAINT no_same_currency CHECK (base_currency <> target_currency),
  CONSTRAINT currencies_uppercase CHECK (
    (base_currency = upper(base_currency)) AND (target_currency = upper(target_currency))
  )
);

CREATE INDEX IF NOT EXISTS idx_exchange_rates_lookup ON public.exchange_rates (base_currency, target_currency, rate_date DESC);

ALTER TABLE public.exchange_rates ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 59. fx_rate_history
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.fx_rate_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_currency TEXT NOT NULL,
  to_currency TEXT NOT NULL,
  rate_date DATE NOT NULL,
  rate NUMERIC(20, 10) NOT NULL,
  source TEXT DEFAULT 'yfinance',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (from_currency, to_currency, rate_date)
);

-- ============================================================================
-- 60. security_master
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.security_master (
  company_id INT PRIMARY KEY REFERENCES public.companies(company_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  isin TEXT,
  cusip TEXT,
  sedol TEXT,
  exchange TEXT,
  asset_class TEXT DEFAULT 'equity',
  currency TEXT DEFAULT 'USD',
  first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_master_symbol ON public.security_master (symbol);

-- ============================================================================
-- AGGREGATION TABLES
-- ============================================================================

-- ============================================================================
-- 61. group_metric_stats
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.group_metric_stats (
  id serial NOT NULL,
  group_type text NOT NULL,
  group_key text NOT NULL,
  metric_id text NOT NULL,
  p05 numeric(10, 2) NULL,
  p25 numeric(10, 2) NULL,
  p50 numeric(10, 2) NULL,
  p75 numeric(10, 2) NULL,
  p95 numeric(10, 2) NULL,
  mean numeric(10, 2) NULL,
  sample_size integer NOT NULL DEFAULT 0,
  computed_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT group_metric_stats_pkey PRIMARY KEY (id),
  CONSTRAINT uq_group_metric UNIQUE (group_type, group_key, metric_id)
);

CREATE INDEX IF NOT EXISTS idx_group_metric_stats_lookup ON public.group_metric_stats (group_type, group_key, metric_id);

-- ============================================================================
-- 62. aggregation_state
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.aggregation_state (
  aggregation_id text NOT NULL DEFAULT 'sector_metric_agg',
  is_running boolean NOT NULL DEFAULT false,
  last_started_at timestamp with time zone NULL,
  last_completed_at timestamp with time zone NULL,
  lock_owner text NULL,
  lock_expires_at timestamp with time zone NULL,
  CONSTRAINT aggregation_state_pkey PRIMARY KEY (aggregation_id)
);

-- ============================================================================
-- SUPER INVESTOR TABLES
-- ============================================================================

-- ============================================================================
-- 63. institutional_investors
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.institutional_investors (
  investor_id serial NOT NULL,
  cik character varying(20) NULL,
  investor_name character varying(255) NOT NULL,
  firm_name character varying(255) NULL,
  is_super_investor boolean NOT NULL DEFAULT false,
  investor_tag character varying(100) NULL,
  investment_style character varying(100) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  last_filed_period character varying(10) NULL,
  last_filed_date date NULL,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT institutional_investors_pkey PRIMARY KEY (investor_id)
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_institutional_investors_super ON public.institutional_investors (is_super_investor) WHERE is_super_investor = true;

-- ============================================================================
-- 64. institutional_holdings
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.institutional_holdings (
  holding_id serial NOT NULL,
  investor_id integer NOT NULL,
  company_id integer NOT NULL,
  quarter_end_date date NOT NULL,
  filing_date date NULL,
  shares_held bigint NULL,
  position_value numeric(18, 2) NULL,
  portfolio_weight numeric(8, 6) NULL,
  shares_change bigint NULL,
  shares_change_pct numeric(15, 4) NULL,
  change_type character varying(20) NULL,
  data_source character varying(50) NULL,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT institutional_holdings_pkey PRIMARY KEY (holding_id),
  CONSTRAINT institutional_holdings_investor_fkey FOREIGN KEY (investor_id) REFERENCES public.institutional_investors (investor_id) ON DELETE CASCADE,
  CONSTRAINT institutional_holdings_company_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_inst_holdings_investor ON public.institutional_holdings (investor_id);
CREATE INDEX IF NOT EXISTS idx_inst_holdings_company ON public.institutional_holdings (company_id);
CREATE INDEX IF NOT EXISTS idx_inst_holdings_quarter ON public.institutional_holdings (quarter_end_date DESC);

-- ============================================================================
-- RISK / BENCHMARK TABLES
-- ============================================================================

-- ============================================================================
-- 65. risk_ai_narratives
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.risk_ai_narratives (
  id bigserial NOT NULL,
  company_id integer NOT NULL,
  narrative_type character varying(50) NOT NULL DEFAULT 'risk_assessment',
  model character varying(100) NOT NULL DEFAULT 'openrouter/default',
  narrative text NOT NULL,
  summary text NULL,
  generated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  generation_time_ms integer NULL,
  CONSTRAINT risk_ai_narratives_pkey PRIMARY KEY (id),
  CONSTRAINT risk_ai_narratives_company_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_risk_narratives_company ON public.risk_ai_narratives (company_id);

-- ============================================================================
-- 66. benchmark_config
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.benchmark_config (
  role character varying(50) NOT NULL,
  company_id integer NULL,
  symbol character varying(20) NOT NULL,
  market character varying(20) NOT NULL,
  description text NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT benchmark_config_pkey PRIMARY KEY (role),
  CONSTRAINT benchmark_config_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies (company_id) ON DELETE SET NULL
) TABLESPACE pg_default;

-- ============================================================================
-- TRIGGERS (re-create after functions)
-- ============================================================================

-- Portfolio events auto-populate event_sequence
DROP TRIGGER IF EXISTS trg_portfolio_events_after_insert ON public.portfolio_events;
CREATE TRIGGER trg_portfolio_events_after_insert
AFTER INSERT ON public.portfolio_events
FOR EACH ROW EXECUTE FUNCTION public.event_insert_sequence_trigger();

-- ============================================================================
-- ROW LEVEL SECURITY POLICIES (exchange_rates)
-- ============================================================================

-- exchange_rates policies
CREATE POLICY "authenticated can read exchange_rates" ON public.exchange_rates
  FOR SELECT USING (auth.role() IN ('authenticated', 'service_role'));

CREATE POLICY "service_role can insert exchange_rates" ON public.exchange_rates
  FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role can update exchange_rates" ON public.exchange_rates
  FOR UPDATE USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role can delete exchange_rates" ON public.exchange_rates
  FOR DELETE USING (auth.role() = 'service_role');

-- ============================================================================
-- END OF SCHEMA RESTORE
-- ============================================================================
