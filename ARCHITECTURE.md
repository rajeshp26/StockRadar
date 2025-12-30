# Project Architecture and Environment Guide

This document provides a comprehensive overview of the project's technical architecture and development environment. It is the single source of truth for understanding how the system is built and how to run it correctly.

## 1. Core Technologies

*   **Frontend:**
    *   **Framework:** Next.js (React)
    *   **Authentication:** [Firebase Authentication](https://firebase.google.com/docs/auth). The client-side application uses the Firebase Web SDK to manage user sign-in and retrieve authentication tokens.
    *   **UI Components:** Tailwind CSS with shadcn/ui.

*   **Backend:**
    *   **Framework:** FastAPI (Python)
    *   **Database:** [Supabase](https://supabase.io/). The backend uses the `supabase-py` library to interact with the Supabase database.
    *   **Data Provider:** `yfinance` for fetching financial stock data.

*   **Development Environment:**
    *   **Orchestration:** Nix (`.idx/dev.nix`) configures the base development shell, providing Node.js, Python, and other system-level packages.
    *   **Python Dependencies:** Managed via a local virtual environment (`.venv`) located in the project root. Requirements are listed in `backend/requirements.txt`.
    *   **Node.js Dependencies:** Managed via `npm` and defined in `package.json`.

## 2. Authentication and Data Flow

The system uses a decoupled authentication and data architecture: **Firebase for authentication** and **Supabase for the database**.

1.  **User Login (Frontend):** A user signs in through the Next.js frontend, which uses the Firebase Authentication SDK.
2.  **Token Generation (Frontend):** Upon successful login, Firebase provides the client with a JSON Web Token (JWT).
3.  **API Request (Frontend):** When the frontend needs to communicate with the backend (e.g., to fetch a watchlist), it sends a request to the FastAPI server and includes the `Authorization: Bearer <token>` header.
4.  **Token Validation (Backend):** The FastAPI backend receives the request, extracts the JWT, and would need to be configured to validate it with Firebase to ensure it is authentic.
5.  **Database Operation (Backend):** Once the token is validated, the backend uses the `supabase-py` client to execute the requested database operations against the Supabase database.

## 3. Running the Application

### Frontend

The frontend server is managed by the IDE's preview manager.

*   **Command:** `npm run dev`
*   **Action:** This command starts the Next.js development server. The IDE should automatically handle this.

### Backend (Python)

The Python backend **must** be run from within its own virtual environment.

#### First-Time Setup
If the `.venv` directory does not exist in the project root, you must create and provision it:

1.  **Create Virtual Environment:**
    ```bash
    python -m venv .venv
    ```
2.  **Activate Environment & Install Dependencies:**
    ```bash
    source .venv/bin/activate && pip install -r backend/requirements.txt
    ```

#### Development and Running the Server

To run the backend server with automatic reloading, which is ideal for development, use the following command. The `--reload` flag ensures that the server will automatically restart when you make changes to the code.

1.  **Activate Environment and Run Server:**
    ```bash
    source .venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
    To run the server in the background, you can append `&` to the command:
    ```bash
    source .venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
    ```

**Important Notes:**

*   **`--host 0.0.0.0`**: This is important to ensure the server is accessible from outside its container in a development environment.
*   **`--reload`**: This flag automatically reloads the server when code changes are detected. This is very useful during development.
*   **Stopping the Server:** If you run the server in the background with `&`, you can stop it by finding its Process ID (PID) with `pgrep -f uvicorn` and then using `kill <PID>`.

## 4. Database Schema

The following SQL schema defines the structure of the Supabase database.

```sql
create table public.users (
  user_id serial not null,
  firebase_uid character varying(255) not null,
  email character varying(255) not null,
  username character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint users_pkey primary key (user_id),
  constraint users_firebase_uid_key unique (firebase_uid),
  constraint users_email_key unique (email)
) TABLESPACE pg_default;

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
  constraint companies_new_pkey primary key (company_id),
  constraint companies_ticker_exchange_unique unique (ticker_symbol, exchange),
  constraint companies_currency_fkey foreign KEY (currency) references currencies (code)
) TABLESPACE pg_default;

create index IF not exists idx_companies_exchange on public.companies using btree (exchange) TABLESPACE pg_default;
create index IF not exists idx_companies_sector on public.companies using btree (sector) TABLESPACE pg_default;
create index IF not exists idx_companies_industry on public.companies using btree (industry) TABLESPACE pg_default;

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

create table public.currencies (
  code character varying(3) not null,
  name character varying(50) not null,
  symbol character varying(5) null,
  constraint currencies_pkey primary key (code)
) TABLESPACE pg_default;

create table public.dividend_history (
  dividend_id serial not null,
  company_id integer null,
  ex_dividend_date date null,
  payment_date date null,
  record_date date null,
  dividend_amount numeric(10, 4) null,
  dividend_type character varying(20) null,
  currency character varying(3) null,
  frequency character varying(20) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint dividend_history_pkey primary key (dividend_id)
) TABLESPACE pg_default;

create table public.dividend_metrics (
  metric_id serial not null,
  company_id integer null,
  fiscal_year integer null,
  annual_dps numeric(10, 4) null,
  dividend_payout_ratio numeric(5, 2) null,
  dividend_yield numeric(5, 2) null,
  dividend_growth_rate_3yr numeric(5, 2) null,
  dividend_growth_rate_5yr numeric(5: 2) null,
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

create table public.balance_sheets (
  bs_id serial not null,
  company_id integer null,
  fiscal_year integer null,
  fiscal_quarter integer null,
  period_end_date date null,
  total_assets numeric(15, 2) null,
  current_assets numeric(15, 2) null,
  cash_equivalents numeric(15, 2) null,
  accounts_receivable numeric(15, 2) null,
  inventory numeric(15, 2) null,
  ppe_net numeric(15, 2) null,
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
  net_debt numeric(15, 2) null,
  working_capital numeric(15, 2) null,
  book_value_per_share numeric(10, 4) null,
  currency character varying(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint balance_sheets_pkey primary key (bs_id)
) TABLESPACE pg_default;

create table public.cash_flow_statements (
  cf_id serial not null,
  company_id integer null,
  fiscal_year integer null,
  fiscal_quarter integer null,
  period_end_date date null,
  operating_cash_flow numeric(15, 2) null,
  net_income numeric(15, 2) null,
  depreciation_amortization numeric(15, 2) null,
  changes_working_capital numeric(15, 2) null,
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
  free_cash_flow numeric(15, 2) null,
  fcf_per_share numeric(10, 4) null,
  currency character varying(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint cash_flow_statements_pkey primary key (cf_id)
) TABLESPACE pg_default;

create table public.earnings_per_share (
  eps_id serial not null,
  company_id integer null,
  fiscal_year integer null,
  fiscal_quarter integer null,
  eps_diluted numeric(10, 4) null,
  eps_basic numeric(10, 4) null,
  reporting_date date null,
  period_end_date date null,
  data_source character varying(50) null,
  is_restated boolean null default false,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint earnings_per_share_pkey primary key (eps_id)
) TABLESPACE pg_default;

create index IF not exists idx_eps_company_year on public.earnings_per_share using btree (company_id, fiscal_year) TABLESPACE pg_default;
create index IF not exists idx_eps_period_end on public.earnings_per_share using btree (period_end_date) TABLESPACE pg_default;

create table public.income_statements (
  is_id serial not null,
  company_id integer null,
  fiscal_year integer null,
  fiscal_quarter integer null,
  period_end_date date null,
  total_revenue numeric(15, 2) null,
  cost_of_revenue numeric(15, 2) null,
  gross_profit numeric(15, 2) null,
  operating_expenses numeric(15, 2) null,
  rd_expenses numeric(15, 2) null,
  sga_expenses numeric(15, 2) null,
  operating_income numeric(15, 2) null,
  interest_expense numeric(15, 2) null,
  tax_expense numeric(15, 2) null,
  net_income numeric(15, 2) null,
  eps_basic numeric(10, 4) null,
  eps_diluted numeric(10, 4) null,
  shares_outstanding_basic bigint null,
  shares_outstanding_diluted bigint null,
  gross_margin numeric(5, 2) null,
  operating_margin numeric(5, 2) null,
  net_margin numeric(5, 2) null,
  effective_tax_rate numeric(5, 2) null,
  ebitda numeric(15, 2) null,
  ebitda_margin numeric(5, 2) null,
  currency character varying(3) null,
  data_source character varying(50) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint income_statements_pkey primary key (is_id)
) TABLESPACE pg_default;

create unique INDEX IF not exists unique_annual_income_idx on public.income_statements using btree (company_id, fiscal_year) TABLESPACE pg_default
where (fiscal_quarter is null);
```