
# Supabase Database Schema

This document contains the `CREATE TABLE` statements for the primary tables in the StockerPro Supabase project.

## `public.users`
```sql
create table public.users (
  user_id serial not null,
  email character varying(255) not null,
  username character varying(100) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  last_signed_in timestamp with time zone null default CURRENT_TIMESTAMP,
  preferred_currency character varying(3) not null,
  auth_id text null,
  timezone character varying(50) not null default 'America/New_York'::character varying,
  constraint users_pkey primary key (user_id),
  constraint users_email_key unique (email),
  constraint users_firebase_uid_key unique (auth_id),
  constraint fk_users_currency foreign KEY (preferred_currency) references currencies (code),
  constraint check_timezone_format check (
    (
      (timezone)::text ~ '^[A-Za-z_]+(/[A-Za-z_]+)?(/[A-Za-z_]+)?$'::text
    )
  ),
  constraint check_valid_timezone check (
    (
      (timezone)::text ~ '^[A-Za-z_]+(/[A-Za-z_]+)?(/[A-Za-z_]+)?$'::text
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_users_timezone on public.users using btree (timezone) TABLESPACE pg_default;
```
## `public.watchlists`

```sql
create table public.watchlists (
  id serial not null,
  user_id integer not null,
  watchlist_name character varying(100) not null default 'My Watchlist'::character varying,
  description text null,
  is_default boolean null default false,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint watchlists_pkey primary key (id),
  constraint unique_user_watchlist_name unique (user_id, watchlist_name),
  constraint watchlists_user_id_fkey foreign KEY (user_id) references users (user_id) on delete CASCADE
) TABLESPACE pg_default;

create unique INDEX IF not exists unique_default_watchlist_per_user on public.watchlists using btree (user_id) TABLESPACE pg_default
where
  (is_default = true);

create index IF not exists idx_watchlists_user_id on public.watchlists using btree (user_id) TABLESPACE pg_default;

create trigger trigger_watchlists_updated_at BEFORE
update on watchlists for EACH row
execute FUNCTION update_watchlists_updated_at ();
```

## `public.watchlist_items`

```sql
create table public.watchlist_items (
  watchlist_item_id serial not null,
  watchlist_id integer not null,
  company_id integer not null,
  target_buy numeric(10, 2) null,
  target_sell numeric(10, 2) null,
  notes text null,
  position integer not null default 0,
  added_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint watchlist_items_pkey primary key (watchlist_item_id),
  constraint unique_watchlist_company unique (watchlist_id, company_id),
  constraint watchlist_items_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE,
  constraint watchlist_items_watchlist_id_fkey foreign KEY (watchlist_id) references watchlists (id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_watchlist_items_watchlist_id on public.watchlist_items using btree (watchlist_id) TABLESPACE pg_default;

create index IF not exists idx_watchlist_items_company_id on public.watchlist_items using btree (company_id) TABLESPACE pg_default;

create index IF not exists idx_watchlist_items_position on public.watchlist_items using btree (watchlist_id, "position") TABLESPACE pg_default;

create trigger trigger_watchlist_items_updated_at BEFORE
update on watchlist_items for EACH row
execute FUNCTION update_watchlists_updated_at ();
```

## `public.companies`

```sql
create table public.companies (
  company_id serial not null,
  ticker_symbol character varying(10) not null,
  company_name character varying(255) not null,
  exchange character varying(50) not null default 'UNKNOWN'::character varying,
  sector character varying(100) null,
  industry character varying(100) null,
  currency character varying(3) not null default 'USD'::character varying,
  fiscal_year_end_month integer null,
  description text null,
  website character varying(255) null,
  created_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  next_earnings_date date null,
  first_financial_data_loaded_at timestamp with time zone null,
  last_financial_refresh_at timestamp with time zone null,
  last_refreshed_fiscal_year integer null,
  last_refreshed_fiscal_quarter smallint null,
  data_completeness_status character varying(50) not null default 'INITIAL'::character varying,
  constraint companies_new_pkey primary key (company_id),
  constraint companies_ticker_exchange_unique unique (ticker_symbol, exchange),
  constraint companies_currency_fkey foreign KEY (currency) references currencies (code),
  constraint check_completeness_status check (
    (
      (data_completeness_status)::text = any (
        (
          array[
            'INITIAL'::character varying,
            'PARTIAL'::character varying,
            'COMPLETE'::character varying,
            'CURRENT'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint check_fiscal_quarter check (
    (
      (last_refreshed_fiscal_quarter is null)
      or (
        (last_refreshed_fiscal_quarter >= 1)
        and (last_refreshed_fiscal_quarter <= 4)
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_companies_next_earnings_date on public.companies using btree (next_earnings_date) TABLESPACE pg_default;

create index IF not exists idx_companies_data_completeness_status on public.companies using btree (data_completeness_status) TABLESPACE pg_default;

create index IF not exists idx_companies_next_earnings_with_status on public.companies using btree (next_earnings_date, data_completeness_status) TABLESPACE pg_default
where
  (next_earnings_date is not null);

create index IF not exists idx_companies_exchange on public.companies using btree (exchange) TABLESPACE pg_default;

create index IF not exists idx_companies_sector on public.companies using btree (sector) TABLESPACE pg_default;

create index IF not exists idx_companies_industry on public.companies using btree (industry) TABLESPACE pg_default;

create trigger tr_update_companies_at BEFORE
update on companies for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.currencies`

```sql
create table public.currencies (
  code character varying(3) not null,
  name character varying(50) not null,
  symbol character varying(5) null,
  constraint currencies_pkey primary key (code)
) TABLESPACE pg_default;
```

---
*The following financial data tables are also included for completeness.*
---

## `public.balance_sheets`

```sql
create table public.balance_sheets (
  bs_id serial not null,
  company_id integer not null,
  fiscal_year integer not null,
  fiscal_quarter smallint null,
  period_end_date date not null,
  total_assets numeric(15, 2) null,
  current_assets numeric(15, 2) null,
  cash_and_cash_equivalents numeric(15, 2) null,
  accounts_receivable numeric(15, 2) null,
  inventory numeric(15, 2) null,
  property_plant_equipment_net numeric(15, 2) null,
  intangible_assets numeric(15, 2) null,
  goodwill numeric(15, 2) null,
  total_liabilities numeric(15, 2) null,
  current_liabilities numeric(15, 2) null,
  accounts_payable numeric(15, 2) null,
  short_term_debt numeric(15, 2) null,
  long_term_debt numeric(15, 2) null,
  total_debt numeric(15, 2) null,
  shareholders_equity numeric(15, 2) null,
  retained_earnings numeric(15, 2) null,
  common_stock numeric(15, 2) null,
  currency character varying(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  long_term_investments numeric(15, 2) null,
  other_non_current_assets numeric(15, 2) null,
  other_current_liabilities numeric(15, 2) null,
  minority_interest numeric(15, 2) null,
  total_liabilities_and_equity numeric(15, 2) null,
  confidence_score double precision not null default 1.0,
  last_validated_at timestamp with time zone null,
  validation_notes text null,
  constraint balance_sheets_pkey primary key (bs_id),
  constraint uq_balance_sheets_company_fiscal unique (company_id, fiscal_year, fiscal_quarter),
  constraint check_balance_confidence check (
    (
      (confidence_score >= (0.0)::double precision)
      and (confidence_score <= (1.0)::double precision)
    )
  ),
  constraint check_balance_data_source check (
    (
      (data_source)::text = any (
        (
          array[
            'defeat_beta'::character varying,
            'yfinance'::character varying,
            'manual'::character varying,
            'external_api'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint check_fiscal_quarter_bs check (
    (
      (fiscal_quarter is null)
      or (
        (fiscal_quarter >= 1)
        and (fiscal_quarter <= 4)
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_balance_sheets_company_id on public.balance_sheets using btree (company_id) TABLESPACE pg_default;

create index IF not exists idx_balance_sheets_fiscal_year on public.balance_sheets using btree (fiscal_year) TABLESPACE pg_default;

create index IF not exists idx_balance_sheets_data_source on public.balance_sheets using btree (data_source) TABLESPACE pg_default;

create index IF not exists idx_balance_sheets_low_confidence on public.balance_sheets using btree (confidence_score) TABLESPACE pg_default
where
  (confidence_score < (0.8)::double precision);

create trigger update_balance_sheets_updated_at BEFORE
update on balance_sheets for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.cash_flow_statements`

```sql
create table public.cash_flow_statements (
  cf_id serial not null,
  company_id integer not null,
  fiscal_year integer not null,
  fiscal_quarter smallint null,
  period_end_date date not null,
  cash_from_operating_activities numeric(15, 2) null,
  net_income numeric(15, 2) null,
  depreciation_amortization numeric(15, 2) null,
  change_in_working_capital numeric(15, 2) null,
  deferred_taxes numeric(15, 2) null,
  stock_based_compensation numeric(15, 2) null,
  capital_expenditures numeric(15, 2) null,
  acquisitions numeric(15, 2) null,
  asset_sales numeric(15, 2) null,
  investment_purchases numeric(15, 2) null,
  debt_issued numeric(15, 2) null,
  debt_repayment numeric(15, 2) null,
  dividends_paid numeric(15, 2) null,
  share_repurchases numeric(15, 2) null,
  share_issuance numeric(15, 2) null,
  currency character varying(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  cash_from_investing_activities numeric(15, 2) null,
  cash_from_financing_activities numeric(15, 2) null,
  confidence_score double precision not null default 1.0,
  last_validated_at timestamp with time zone null,
  validation_notes text null,
  constraint cash_flow_statements_pkey primary key (cf_id),
  constraint uq_cash_flows_company_fiscal unique (company_id, fiscal_year, fiscal_quarter),
  constraint check_cashflow_confidence check (
    (
      (confidence_score >= (0.0)::double precision)
      and (confidence_score <= (1.0)::double precision)
    )
  ),
  constraint check_cashflow_data_source check (
    (
      (data_source)::text = any (
        (
          array[
            'defeat_beta'::character varying,
            'yfinance'::character varying,
            'manual'::character varying,
            'external_api'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint check_fiscal_quarter_cf check (
    (
      (fiscal_quarter is null)
      or (
        (fiscal_quarter >= 1)
        and (fiscal_quarter <= 4)
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_cash_flows_company_id on public.cash_flow_statements using btree (company_id) TABLESPACE pg_default;

create index IF not exists idx_cash_flows_fiscal_year on public.cash_flow_statements using btree (fiscal_year) TABLESPACE pg_default;

create index IF not exists idx_cash_flow_statements_data_source on public.cash_flow_statements using btree (data_source) TABLESPACE pg_default;

create trigger update_cash_flow_updated_at BEFORE
update on cash_flow_statements for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.income_statements`

```sql
create table public.income_statements (
  is_id serial not null,
  company_id integer not null,
  fiscal_year integer not null,
  fiscal_quarter smallint null,
  period_end_date date not null,
  revenue numeric(15, 2) null,
  cost_of_goods_sold numeric(15, 2) null,
  gross_profit numeric(15, 2) null,
  operating_expenses numeric(15, 2) null,
  rd_expenses numeric(15, 2) null,
  sga_expenses numeric(15, 2) null,
  operating_income numeric(15, 2) null,
  interest_expense numeric(15, 2) null,
  tax_expense numeric(15, 2) null,
  net_income numeric(15, 2) null,
  ebitda numeric(15, 2) null,
  currency character varying(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  non_operating_income_expense numeric(15, 2) null,
  pretax_income numeric(15, 2) null,
  equity_in_earnings numeric(15, 2) null,
  minority_interest numeric(15, 2) null,
  income_from_continuing_operations numeric(15, 2) null,
  discontinued_operations numeric(15, 2) null,
  net_income_to_common numeric(15, 2) null,
  preferred_dividends numeric(15, 2) null,
  ebit numeric(15, 2) null,
  confidence_score double precision not null default 1.0,
  last_validated_at timestamp with time zone null,
  validation_notes text null,
  constraint income_statements_pkey primary key (is_id),
  constraint uq_income_statements_company_fiscal unique (company_id, fiscal_year, fiscal_quarter),
  constraint check_fiscal_quarter check (
    (
      (fiscal_quarter is null)
      or (
        (fiscal_quarter >= 1)
        and (fiscal_quarter <= 4)
      )
    )
  ),
  constraint check_income_confidence check (
    (
      (confidence_score >= (0.0)::double precision)
      and (confidence_score <= (1.0)::double precision)
    )
  ),
  constraint check_income_data_source check (
    (
      (data_source)::text = any (
        (
          array[
            'defeat_beta'::character varying,
            'yfinance'::character varying,
            'manual'::character varying,
            'external_api'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_income_statements_company_id on public.income_statements using btree (company_id) TABLESPACE pg_default;

create index IF not exists idx_income_statements_fiscal_year on public.income_statements using btree (fiscal_year) TABLESPACE pg_default;

create index IF not exists idx_income_statements_data_source on public.income_statements using btree (data_source) TABLESPACE pg_default;

create index IF not exists idx_income_statements_low_confidence on public.income_statements using btree (confidence_score) TABLESPACE pg_default
where
  (confidence_score < (0.8)::double precision);

create trigger update_income_statements_updated_at BEFORE
update on income_statements for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.statistics`

```sql
create table public.statistics (
  stat_id serial not null,
  company_id integer not null,
  fiscal_year integer not null,
  fiscal_quarter smallint null,
  period_end_date date not null,
  period_type character varying(10) null default 'fiscal'::character varying,
  pe_ratio numeric(10, 4) null,
  ps_ratio numeric(10, 4) null,
  pcf_ratio numeric(10, 4) null,
  pb_ratio numeric(10, 4) null,
  enterprise_value numeric(18, 2) null,
  ev_to_ebitda numeric(10, 4) null,
  gross_margin_pct numeric(6, 3) null,
  operating_margin_pct numeric(6, 3) null,
  ebitda_margin_pct numeric(6, 3) null,
  net_margin_pct numeric(6, 3) null,
  return_on_assets_pct numeric(6, 3) null,
  return_on_equity_pct numeric(6, 3) null,
  return_on_invested_capital_pct numeric(6, 3) null,
  current_ratio numeric(8, 3) null,
  quick_ratio numeric(8, 3) null,
  asset_turnover numeric(8, 3) null,
  inventory_turnover numeric(8, 3) null,
  debt_to_assets numeric(8, 3) null,
  debt_to_equity numeric(8, 3) null,
  long_term_debt_to_assets numeric(8, 3) null,
  long_term_debt_to_equity numeric(8, 3) null,
  revenue_per_share numeric(12, 4) null,
  operating_cash_flow_per_share numeric(12, 4) null,
  free_cash_flow_per_share numeric(12, 4) null,
  ebit_per_share numeric(12, 4) null,
  ebitda_per_share numeric(12, 4) null,
  book_value_per_share numeric(12, 4) null,
  tangible_book_value_per_share numeric(12, 4) null,
  cash_per_share numeric(12, 4) null,
  total_debt_per_share numeric(12, 4) null,
  working_capital_per_share numeric(12, 4) null,
  capex_per_share numeric(12, 4) null,
  net_current_asset_value_per_share numeric(12, 4) null,
  dividends_per_share numeric(10, 4) null,
  dividend_yield_pct numeric(6, 3) null,
  payout_ratio_pct numeric(6, 3) null,
  shares_outstanding_basic bigint null,
  shares_outstanding_diluted bigint null,
  currency character(3) null,
  data_source character varying(50) null,
  calculated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  confidence_score double precision not null default 1.0,
  last_validated_at timestamp with time zone null,
  validation_notes text null,
  constraint statistics_pkey primary key (stat_id),
  constraint check_statistics_confidence check (
    (
      (confidence_score >= (0.0)::double precision)
      and (confidence_score <= (1.0)::double precision)
    )
  ),
  constraint check_statistics_data_source check (
    (
      (data_source)::text = any (
        (
          array[
            'defeat_beta'::character varying,
            'yfinance'::character varying,
            'manual'::character varying,
            'external_api'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint statistics_fiscal_quarter_check check (
    (
      (
        (fiscal_quarter >= 1)
        and (fiscal_quarter <= 4)
      )
      or (fiscal_quarter is null)
    )
  ),
  constraint statistics_period_type_check check (
    (
      (period_type)::text = any (
        (
          array[
            'fiscal'::character varying,
            'ttm'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_statistics_data_source on public.statistics using btree (data_source) TABLESPACE pg_default;

create unique INDEX IF not exists unique_quarterly_stats on public.statistics using btree (company_id, fiscal_year, fiscal_quarter) TABLESPACE pg_default
where
  (
    (fiscal_quarter is not null)
    and ((period_type)::text = 'fiscal'::text)
  );

create unique INDEX IF not exists unique_annual_stats on public.statistics using btree (company_id, fiscal_year) TABLESPACE pg_default
where
  (
    (fiscal_quarter is null)
    and ((period_type)::text = 'fiscal'::text)
  );

create unique INDEX IF not exists unique_ttm_stats on public.statistics using btree (company_id, fiscal_year, period_type) TABLESPACE pg_default
where
  ((period_type)::text = 'ttm'::text);

create index IF not exists idx_statistics_company_year_quarter on public.statistics using btree (company_id, fiscal_year desc, fiscal_quarter desc) TABLESPACE pg_default;

create index IF not exists idx_statistics_period_type on public.statistics using btree (period_type) TABLESPACE pg_default;

create index IF not exists idx_statistics_pe_ratio on public.statistics using btree (pe_ratio) TABLESPACE pg_default
where
  (pe_ratio is not null);

create index IF not exists idx_statistics_ev_ebitda on public.statistics using btree (ev_to_ebitda) TABLESPACE pg_default
where
  (ev_to_ebitda is not null);

create trigger update_statistics_updated_at BEFORE
update on statistics for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.dividend_history`

```sql
create table public.dividend_history (
  dividend_id serial not null,
  company_id integer not null,
  ex_dividend_date date not null,
  payment_date date null,
  record_date date null,
  dividend_amount numeric(10, 4) null,
  dividend_type character varying(30) null default 'regular'::character varying,
  currency character(3) null default 'USD'::bpchar,
  frequency character varying(20) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  confidence_score double precision not null default 1.0,
  last_validated_at timestamp with time zone null,
  validation_notes text null,
  constraint dividend_history_pkey primary key (dividend_id),
  constraint check_dividend_confidence check (
    (
      (confidence_score >= (0.0)::double precision)
      and (confidence_score <= (1.0)::double precision)
    )
  ),
  constraint check_dividend_data_source check (
    (
      (data_source)::text = any (
        (
          array[
            'defeat_beta'::character varying,
            'yfinance'::character varying,
            'manual'::character varying,
            'external_api'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_dividend_history_data_source on public.dividend_history using btree (data_source) TABLESPACE pg_default;

create unique INDEX IF not exists unique_dividend_per_company_exdate on public.dividend_history using btree (company_id, ex_dividend_date) TABLESPACE pg_default;

create index IF not exists idx_div_hist_comp_exdate_desc on public.dividend_history using btree (company_id, ex_dividend_date desc) TABLESPACE pg_default;

create index IF not exists idx_div_hist_payment_date on public.dividend_history using btree (payment_date desc) TABLESPACE pg_default;

create trigger update_dividend_history_updated_at BEFORE
update on dividend_history for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.dividend_metrics`

```sql
create table public.dividend_metrics (
  metric_id serial not null,
  company_id integer null,
  fiscal_year integer null,
  annual_dps numeric(10, 4) null,
  dividend_payout_ratio numeric(5, 2) null,
  dividend_yield numeric(5, 2) null,
  dividend_growth_rate_3yr numeric(5, 2) null,
  dividend_growth_rate_5yr numeric(5, 2) null,
  dividend_growth_rate_10yr numeric(5, 2) null,
  consecutive_years_paid integer null,
  fcfe_coverage_ratio numeric(5, 2) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  cash_dividend_payout_ratio numeric(10, 2) null,
  fcf_dividend_payout_ratio numeric(10, 2) null,
  dividend_coverage_fcf numeric(10, 2) null,
  ebitda_dividend_coverage numeric(10, 2) null,
  retention_ratio numeric(10, 2) null,
  constraint dividend_metrics_pkey primary key (metric_id)
) TABLESPACE pg_default;
```

## `public.earnings`

```sql
create table public.earnings (
  earnings_id serial not null,
  company_id integer not null,
  fiscal_year integer not null,
  fiscal_quarter smallint null,
  period_end_date date not null,
  announcement_date date null,
  eps_reported_basic numeric(10, 4) null,
  eps_reported_diluted numeric(10, 4) null,
  eps_estimate numeric(10, 4) null,
  eps_surprise_amount numeric(10, 4) null,
  eps_surprise_percent numeric(8, 3) null,
  revenue_reported numeric(18, 2) null,
  revenue_estimate numeric(18, 2) null,
  revenue_surprise_amount numeric(18, 2) null,
  revenue_surprise_percent numeric(8, 3) null,
  shares_outstanding_basic bigint null,
  shares_outstanding_diluted bigint null,
  currency character(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  confidence_score double precision not null default 1.0,
  last_validated_at timestamp with time zone null,
  validation_notes text null,
  constraint earnings_pkey primary key (earnings_id),
  constraint uq_earnings_company_fiscal unique (company_id, fiscal_year, fiscal_quarter),
  constraint check_earnings_confidence check (
    (
      (confidence_score >= (0.0)::double precision)
      and (confidence_score <= (1.0)::double precision)
    )
  ),
  constraint check_earnings_data_source check (
    (
      (data_source)::text = any (
        (
          array[
            'defeat_beta'::character varying,
            'yfinance'::character varying,
            'manual'::character varying,
            'external_api'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint earnings_fiscal_quarter_check check (
    (
      (
        (fiscal_quarter >= 1)
        and (fiscal_quarter <= 4)
      )
      or (fiscal_quarter is null)
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_earnings_data_source on public.earnings using btree (data_source) TABLESPACE pg_default;

create index IF not exists idx_earnings_company_year_quarter on public.earnings using btree (company_id, fiscal_year desc, fiscal_quarter desc) TABLESPACE pg_default;

create index IF not exists idx_earnings_announcement_date on public.earnings using btree (announcement_date desc) TABLESPACE pg_default;

create index IF not exists idx_earnings_eps_surprise on public.earnings using btree (eps_surprise_percent) TABLESPACE pg_default
where
  (eps_surprise_percent is not null);

create index IF not exists idx_earnings_company_id on public.earnings using btree (company_id) TABLESPACE pg_default;

create trigger update_earnings_updated_at BEFORE
update on earnings for EACH row
execute FUNCTION update_updated_at_column ();
```

## `public.current_market_data`

```sql
create table public.current_market_data (
  company_id integer not null,
  current_price numeric(10, 4) not null,
  open_price numeric(10, 4) null,
  high_price numeric(10, 4) null,
  low_price numeric(10, 4) null,
  close_price numeric(10, 4) null,
  volume bigint null,
  market_state character varying(20) null,
  last_updated timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint current_market_data_pkey primary key (company_id),
  constraint current_market_data_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;
```
## `public.data_conflicts`

```sql
create table public.data_conflicts (
  conflict_id bigserial not null,
  company_id integer not null,
  fiscal_year integer not null,
  fiscal_quarter smallint null,
  field_name character varying(100) not null,
  existing_value numeric null,
  existing_source character varying(50) not null,
  new_value numeric null,
  new_source character varying(50) not null,
  percent_diff double precision not null,
  resolved boolean null default false,
  resolution_notes text null,
  resolution_choice character varying(50) null,
  detected_at timestamp with time zone not null,
  resolved_at timestamp with time zone null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint data_conflicts_pkey primary key (conflict_id),
  constraint fk_data_conflicts_company foreign KEY (company_id) references companies (company_id) on delete CASCADE,
  constraint check_conflict_values check (
    (
      (
        (existing_value is not null)
        or (new_value is not null)
      )
      and (percent_diff >= (0)::double precision)
    )
  ),
  constraint check_resolution_choice check (
    (
      (resolution_choice is null)
      or (
        (resolution_choice)::text = any (
          (
            array[
              'keep_existing'::character varying,
              'use_new'::character varying,
              'manual_review'::character varying
            ]
          )::text[]
        )
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_data_conflicts_unresolved on public.data_conflicts using btree (resolved, detected_at desc) TABLESPACE pg_default
where
  (resolved = false);

create index IF not exists idx_data_conflicts_company on public.data_conflicts using btree (company_id, detected_at desc) TABLESPACE pg_default;

create index IF not exists idx_data_conflicts_percent_diff on public.data_conflicts using btree (percent_diff desc) TABLESPACE pg_default;

create index IF not exists idx_data_conflicts_resolved_at on public.data_conflicts using btree (resolved_at) TABLESPACE pg_default
where
  (resolved = true);
```
## `public.scheduler_locks`

```sql
create table public.scheduler_locks (
  lock_id character varying(100) not null,
  company_id integer not null,
  acquired_at timestamp with time zone not null,
  expires_at timestamp with time zone not null,
  lock_type character varying(50) null default 'financial_refresh'::character varying,
  constraint scheduler_locks_pkey primary key (lock_id),
  constraint scheduler_locks_company_id_key unique (company_id),
  constraint fk_scheduler_locks_company foreign KEY (company_id) references companies (company_id) on delete CASCADE,
  constraint check_lock_expiry check ((expires_at > acquired_at))
) TABLESPACE pg_default;

create index IF not exists idx_scheduler_locks_company_id on public.scheduler_locks using btree (company_id) TABLESPACE pg_default;

create index IF not exists idx_scheduler_locks_expires_at on public.scheduler_locks using btree (expires_at) TABLESPACE pg_default;


## `public.intrinsic_value_analysis`

create table public.intrinsic_value_analysis (
  analysis_id serial not null,
  company_id integer null,
  growth_rate numeric(10, 4) null,
  current_eps numeric(15, 4) null,
  future_pe numeric(10, 2) null,
  future_price numeric(15, 2) null,
  sticker_price numeric(15, 2) null,
  mos_price numeric(15, 2) null,
  last_updated timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint intrinsic_value_analysis_pkey primary key (analysis_id),
  constraint intrinsic_value_analysis_company_id_key unique (company_id),
  constraint intrinsic_value_analysis_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

## `public.industry_multiples`
create table public.industry_multiples (
  industry_multiple_id serial not null,
  sector character varying(100) null,
  industry character varying(100) null,
  calculation_date date null,
  avg_pe numeric(10, 2) null,
  avg_pb numeric(10, 2) null,
  avg_ps numeric(10, 2) null,
  avg_pcf numeric(10, 2) null,
  avg_peg numeric(10, 2) null,
  avg_ev_ebitda numeric(10, 2) null,
  avg_ev_revenue numeric(10, 2) null,
  avg_ev_fcf numeric(10, 2) null,
  median_pe numeric(10, 2) null,
  median_pb numeric(10, 2) null,
  median_ps numeric(10, 2) null,
  median_ev_ebitda numeric(10, 2) null,
  median_ev_revenue numeric(10, 2) null,
  avg_eps_growth numeric(5, 2) null,
  median_eps_growth numeric(5, 2) null,
  avg_revenue_growth numeric(5, 2) null,
  sample_size integer null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint industry_multiples_pkey primary key (industry_multiple_id)
) TABLESPACE pg_default;

create index IF not exists idx_sector_industry_date on public.industry_multiples using btree (sector, industry, calculation_date) TABLESPACE pg_default;

## `public.ddm_valuations`
create table public.ddm_valuations (
  ddm_id serial not null,
  company_id integer null,
  analysis_date date null,
  current_dps numeric(10, 4) null,
  next_year_dps numeric(10, 4) null,
  dividend_growth_rate numeric(5, 2) null,
  required_return numeric(5, 3) null,
  intrinsic_value_gordon numeric(10, 2) null,
  high_growth_years integer null,
  high_growth_rate numeric(5, 2) null,
  stable_growth_rate numeric(5, 2) null,
  intrinsic_value_multistage numeric(10, 2) null,
  current_stock_price numeric(10, 2) null,
  upside_downside_pct numeric(6, 2) null,
  analyst_name character varying(100) null,
  notes text null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint ddm_valuations_pkey primary key (ddm_id)
) TABLESPACE pg_default;

## `public.dcf_valuations`
create table public.dcf_valuations (
  dcf_id serial not null,
  company_id integer null,
  analysis_date date null,
  forecast_years integer null,
  revenue_growth_rate numeric(5, 2) null,
  terminal_growth_rate numeric(5, 2) null,
  wacc_used numeric(5, 3) null,
  fcf_margin_assumption numeric(5, 2) null,
  total_pv_fcf numeric(15, 2) null,
  terminal_value numeric(15, 2) null,
  pv_terminal_value numeric(15, 2) null,
  enterprise_value_dcf numeric(15, 2) null,
  less_net_debt numeric(15, 2) null,
  equity_value numeric(15, 2) null,
  shares_outstanding bigint null,
  intrinsic_value_per_share numeric(10, 2) null,
  current_stock_price numeric(10, 2) null,
  upside_downside_pct numeric(6, 2) null,
  analyst_name character varying(100) null,
  sensitivity_scenarios jsonb null,
  notes text null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint dcf_valuations_pkey primary key (dcf_id)
) TABLESPACE pg_default;

## `public.price_history`
create table public.price_history (
  company_id integer not null,
  price_date date not null,
  open_price numeric(12, 4) null,
  close_price numeric(12, 4) not null,
  high_price numeric(12, 4) null,
  low_price numeric(12, 4) null,
  volume bigint null,
  data_source character varying(50) not null default 'defeatbeta'::character varying,
  created_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint price_history_pk primary key (company_id, price_date),
  constraint price_history_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_price_history_company_date_desc on public.price_history using btree (company_id, price_date desc) TABLESPACE pg_default;

## `public.analyst_eps_estimates`
create table public.analyst_eps_estimates (
  estimate_id bigserial not null,
  company_id integer not null,
  fiscal_year integer not null,
  estimate_date date not null,
  eps_estimate numeric(12, 4) not null,
  number_of_analysts integer null,
  period_type character varying(20) null default 'annual'::character varying,
  provider character varying(50) not null default 'defeatbeta'::character varying,
  created_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint analyst_eps_estimates_pkey primary key (estimate_id),
  constraint analyst_eps_estimates_uq unique (company_id, fiscal_year, provider, estimate_date),
  constraint analyst_eps_estimates_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_analyst_eps_company_year on public.analyst_eps_estimates using btree (company_id, fiscal_year) TABLESPACE pg_default;

## `public.valuation_method_defaults`
create table public.valuation_method_defaults (
  method character varying(40) not null,
  params jsonb not null,
  updated_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint valuation_method_defaults_pkey primary key (method),
  constraint valuation_method_defaults_method_check check (
    (
      (method)::text = any (
        (
          array[
            'rule1'::character varying,
            'ddm_gordon'::character varying,
            'ddm_two_stage'::character varying,
            'dcf'::character varying,
            'owner_earnings'::character varying,
            'relative'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

## `public.company_valuation_overrides`
create table public.company_valuation_overrides (
  company_id integer not null,
  method character varying(40) not null,
  params jsonb not null,
  updated_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint company_valuation_overrides_pk primary key (company_id, method),
  constraint company_valuation_overrides_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE,
  constraint company_valuation_overrides_method_check check (
    (
      (method)::text = any (
        (
          array[
            'rule1'::character varying,
            'ddm_gordon'::character varying,
            'ddm_two_stage'::character varying,
            'dcf'::character varying,
            'owner_earnings'::character varying,
            'relative'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

## `public.valuation_runs`
create table public.valuation_runs (
  valuation_run_id bigserial not null,
  company_id integer not null,
  method character varying(40) not null,
  run_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  run_by_user_id integer null,
  input_snapshot jsonb not null,
  assumption_snapshot jsonb not null,
  output_snapshot jsonb not null,
  data_version_tag character varying(100) null,
  notes text null,
  constraint valuation_runs_pkey primary key (valuation_run_id),
  constraint valuation_runs_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE,
  constraint valuation_runs_run_by_user_id_fkey foreign KEY (run_by_user_id) references users (user_id),
  constraint valuation_runs_method_check check (
    (
      (method)::text = any (
        (
          array[
            'rule1'::character varying,
            'ddm_gordon'::character varying,
            'ddm_two_stage'::character varying,
            'dcf'::character varying,
            'owner_earnings'::character varying,
            'relative'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_valuation_runs_company_method_date on public.valuation_runs using btree (company_id, method, run_at desc) TABLESPACE pg_default;

## `public.splits`
create table public.splits (
  split_id bigint generated always as identity not null,
  company_id integer not null,
  report_date date not null,
  split_factor character varying(20) not null,
  reverse_split boolean null default false,
  data_source character varying(50) null default 'defeatbeta'::character varying,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint splits_pkey primary key (split_id),
  constraint splits_company_date_unique unique (company_id, report_date),
  constraint splits_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_splits_company_date on public.splits using btree (company_id, report_date desc) TABLESPACE pg_default;

## `public.revenue_forecast`
create table public.revenue_forecast (
  forecast_id bigint generated always as identity not null,
  company_id integer not null,
  report_date date not null,
  period_type character varying(20) not null,
  estimate_revenue_growth numeric(8, 4) null,
  number_of_analysts integer null,
  estimate_avg_revenue numeric(20, 2) null,
  estimate_high_revenue numeric(20, 2) null,
  estimate_low_revenue numeric(20, 2) null,
  year_ago_estimate_avg_revenue numeric(20, 2) null,
  currency character varying(5) null default 'USD'::character varying,
  provider character varying(50) null default 'defeatbeta'::character varying,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint revenue_forecast_pkey primary key (forecast_id),
  constraint revenue_forecast_unique unique (company_id, report_date, period_type, provider),
  constraint revenue_forecast_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_revenue_forecast_company_date on public.revenue_forecast using btree (company_id, report_date desc) TABLESPACE pg_default;

## `public.earnings_forecast`
create table public.earnings_forecast (
  earnings_forecast_id bigint generated always as identity not null,
  company_id integer not null,
  report_date date not null,
  period_type character varying(20) not null,
  currency character varying(5) null default 'USD'::character varying,
  estimate_eps_growth numeric(8, 4) null,
  estimate_avg_eps numeric(10, 4) null,
  estimate_high_eps numeric(10, 4) null,
  estimate_low_eps numeric(10, 4) null,
  number_of_analysts integer null,
  thirty_days_ago_estimate_avg_eps numeric(10, 4) null,
  sixty_days_ago_estimate_avg_eps numeric(10, 4) null,
  ninety_days_ago_estimate_avg_eps numeric(10, 4) null,
  year_ago_estimate_avg_eps numeric(10, 4) null,
  provider character varying(50) null default 'defeatbeta'::character varying,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint earnings_forecast_pkey primary key (earnings_forecast_id),
  constraint earnings_forecast_unique unique (company_id, report_date, period_type, provider),
  constraint earnings_forecast_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_earnings_forecast_company_date on public.earnings_forecast using btree (company_id, report_date desc) TABLESPACE pg_default;

## `public.company_summary`
create table public.company_summary (
  summary_id bigint generated always as identity not null,
  company_id integer not null,
  snapshot_date date not null default CURRENT_DATE,
  market_cap numeric(20, 2) null,
  enterprise_value numeric(20, 2) null,
  shares_outstanding numeric(20, 2) null,
  implied_shares_outstanding numeric(20, 2) null,
  beta numeric(8, 4) null,
  trailing_pe numeric(10, 4) null,
  forward_pe numeric(10, 4) null,
  trailing_eps numeric(10, 4) null,
  forward_eps numeric(10, 4) null,
  enterprise_to_ebitda numeric(10, 4) null,
  enterprise_to_revenue numeric(10, 4) null,
  peg_ratio numeric(10, 4) null,
  currency character varying(5) null default 'USD'::character varying,
  provider character varying(50) null default 'defeatbeta'::character varying,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint company_summary_pkey primary key (summary_id),
  constraint company_summary_unique unique (company_id, snapshot_date, provider),
  constraint company_summary_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_company_summary_company_date on public.company_summary using btree (company_id, snapshot_date desc) TABLESPACE pg_default;

## `public.valuation_diagnostics`
create table public.valuation_diagnostics (
  diag_id bigserial not null,
  company_id integer not null,
  method character varying(40) not null,
  code character varying(40) not null,
  severity character varying(10) not null,
  message text not null,
  context jsonb null,
  created_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  constraint valuation_diagnostics_pkey primary key (diag_id),
  constraint valuation_diagnostics_company_id_fkey foreign KEY (company_id) references companies (company_id) on delete CASCADE,
  constraint valuation_diagnostics_severity_check check (
    (
      (severity)::text = any (
        (
          array[
            'critical'::character varying,
            'high'::character varying,
            'medium'::character varying,
            'low'::character varying,
            'info'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_valuation_diagnostics_company_method on public.valuation_diagnostics using btree (company_id, method, created_at desc) TABLESPACE pg_default;