# Project Architecture and Environment Guide

This document provides a comprehensive overview of the project's technical architecture and development environment. It is the single source of truth for understanding how the system is built and how to run it correctly.

## 1. Core Technologies

*   **Frontend:**
    *   **Framework:** Next.js 15 (App Router), React 19.
    *   **Authentication:** [Firebase Authentication](https://firebase.google.com/docs/auth). The client-side application uses the Firebase Web SDK to manage user sign-in and retrieve authentication tokens.
    *   **UI Components:** Tailwind CSS with shadcn/ui.
    *   **Reactivity:** Firebase Firestore for reactive document synchronization where needed.

*   **Backend:**
    *   **Framework:** FastAPI (Python 3.11+).
    *   **Database:** [Supabase](https://supabase.io/). The backend uses the `supabase-py` library to interact with the Supabase database.
    *   **Data Provider:** `yfinance` for fetching financial stock data.
    *   **AI Layer:** Google Genkit AI (`src/ai/`) for advanced stock analysis and flow orchestration.

*   **Communication:**
    *   **Secure Bridge:** Next.js API Bridge (`src/app/api/proxy/`) for REST commands.
    *   **Real-time:** Server-Sent Events (SSE) for stock price synchronization.

---

## 2. System Architecture & The "Secure Bridge"

The system uses a decoupled architecture: **Firebase for authentication** and **Supabase for the database**. To avoid CORS and simplify security, the frontend communicates with the Python backend via a **Secure Bridge**.

`Browser` <---> `Next.js API Bridge (Proxy)` <---> `FastAPI Backend` <---> `Supabase / yfinance`

### 2.1 The Authentication "Trust" Model
Instead of traditional JWT headers for internal calls, this project uses an **Identity Propagation** model:
1.  **Client-Side Auth:** Firebase validates the user on the frontend.
2.  **The Payload:** The frontend includes the `firebase_uid` directly in the **JSON request body** for all authenticated POST/DELETE requests.
3.  **Backend Trust:** The Python backend, running in a protected internal network, trusts the `firebase_uid` provided by the Next.js Bridge.

### 2.2 Real-time Synchronization (Pub/Sub via SSE)
To optimize performance, the application uses a **Publish-Subscribe** model for real-time stock updates:
1.  **Subscription:** The frontend establishes a persistent connection via `GET /watchlists/stream`.
2.  **Monitoring:** The Backend runs a background task that fetches market data only for symbols with active subscribers.
3.  **Targeted Broadcast:** When a price change occurs, the backend pushes a JSON event over the SSE connection specifically to interested users.

---

## 3. Directory Map

| Path | Description |
| :--- | :--- |
| `src/app/(authenticated)/` | Protected route group. These routes are guarded by the `AuthProvider`. |
| `src/app/api/proxy/` | The Secure Bridge implementation (Next.js Route Handlers). |
| `src/lib/api.ts` | Axios instance configured to communicate with the Bridge. |
| `src/firebase/` | Firebase Client SDK initialization, Firestore hooks, and Auth providers. |
| `src/ai/` | Genkit AI flows and configuration. |
| `backend/api/` | FastAPI routers (feature-based: users, watchlists, etc.). |
| `backend/providers/` | External data abstractions (e.g., `yfinance_provider.py`). |

---

## 4. User Flows & Technical Sequences

This section details the interaction between frontend components, the API bridge, and backend services.

### 4.1 Flow: Startup & Authentication Guarding
**Trigger:** User visits the root URL.

*   **Frontend (UI):** `LandingPage` (`src/app/page.tsx`) renders the hero section.
*   **Frontend (Auth):** `AuthProvider` (`src/components/auth/auth-provider.tsx`) initializes the Firebase SDK.
*   **Frontend (Guard):** `middleware.ts` inspects the session. If authenticated, it redirects to `/dashboard`.
*   **Frontend (State):** If unauthenticated, the user remains on the landing page, and `user-nav.tsx` displays "Login/Signup" buttons.

### 4.2 Flow: New User Signup
**Trigger:** User submits the signup form.

1.  **Frontend (Component):** `SignupForm` captures email and password.
2.  **Frontend (Service):** Calls Firebase Auth `createUserWithEmailAndPassword`. Firebase returns a `UserCredential` with a unique `uid`.
3.  **Frontend (Bridge):** `api.ts` sends a `POST /users/sync` request containing the `firebase_uid`, `email`, and `display_name`.
4.  **Backend (Router):** `users.py` receives the sync request.
5.  **Backend (DB):** Performs a Supabase `upsert` on the `users` table, linking the `firebase_uid` to a new internal `user_id`.
6.  **Backend (Response):** Returns the user's synchronized profile.
7.  **Frontend (Routing):** `SignupForm` triggers a redirect to the `/dashboard`.

### 4.3 Flow: Dashboard Loading & Real-time Handshake
**Trigger:** User enters the authenticated dashboard.

1.  **Frontend (Component):** `Watchlist` (`src/components/dashboard/watchlist.tsx`) mounts and initiates `fetchWatchlist`.
2.  **Frontend (Data Fetch):** Calls `POST /watchlists/default-with-items` via the bridge.
3.  **Backend (Logic):** `watchlists.py` retrieves the default watchlist for the user and joins it with the `watchlist_items` and `companies` tables.
4.  **Backend (Provider):** `YFinanceProvider` fetches a synchronous market snapshot for all watchlist symbols.
5.  **Backend (Response):** Returns a unified JSON object containing the watchlist ID and an array of `stocks` (including prices and names).
6.  **Frontend (UI):** `Watchlist` renders multiple `StockCard` components using the snapshot.
7.  **Frontend (SSE Init):** `useEffect` in `Watchlist` opens an `EventSource` connection to `/api/proxy/watchlists/stream?firebase_uid=...`.
8.  **Backend (Subscription):** `watchlists.py` adds the user's `firebase_uid` and their watchlist symbols to the `symbol_subscribers` map and creates a dedicated `asyncio.Queue` for the connection.

### 4.4 Flow: Adding a Stock (Fast Add, Deep Sync)
**Trigger:** User clicks "Add Stock" and enters a ticker symbol.

1.  **Frontend (Component):** `AddStockDialog` captures the ticker (e.g., "AAPL") and target prices.
2.  **Frontend (Bridge):** Sends `POST /watchlist-items` containing the `firebase_uid`, `watchlist_id`, and stock details.
3.  **Backend (Router - Fast Path):** `watchlist_items.py` validates the ticker existence via `yfinance.Ticker(symbol).info`.
4.  **Backend (DB):** Inserts/Upserts records into Supabase `companies`, `current_market_data`, and `watchlist_items` tables using the basic info received.
5.  **Backend (Worker Trigger):** The router triggers a **FastAPI BackgroundTask** to perform a "Deep Sync".
6.  **Backend (Response):** Immediately returns the basic stock data to the frontend so it appears in the UI instantly.
7.  **Backend (Deep Sync Worker):** Running in the background, the worker fetches full DataFrames from `yfinance` (Income Statement, Balance Sheet, Cash Flow, Dividends, Earnings) and performs batch upserts into the corresponding Supabase tables (Section 7.1).

---

## 5. Responsibilities Matrix

| Feature | Frontend Responsibility | Backend Responsibility |
| :--- | :--- | :--- |
| **Authentication** | Sign-in UI, Session management. | Mapping `firebase_uid` to internal `user_id`. |
| **Data Fetching** | Initial Snapshot request. | `yfinance` fetch + DB lookups. |
| **Real-time** | `EventSource` lifecycle/reconnection. | Background monitoring, per-user queues. |
| **Persistence** | Optimistic UI updates. | DB Integrity, Deep background data synchronization. |

---

## 6. Running the Application

### Frontend
The frontend server is managed by the IDE's preview manager.
*   **Command:** `npm run dev` (Starts on port 9002).

### Backend (Python)
The Python backend **must** be run from within its own virtual environment.

#### First-Time Setup
1.  **Create Virtual Environment:** `python -m venv .venv`
2.  **Activate & Install:** `source .venv/bin/activate && pip install -r backend/requirements.txt`

#### Running the Server
```bash
source .venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 7. Database Schema (Supabase)

```sql
create table public.users (
  user_id serial not null,
  email character varying(255) not null,
  username character varying(100) null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  last_signed_in timestamp with time zone null default CURRENT_TIMESTAMP,
  preferred_currency character varying(3) not null default 'USD',
  firebase_uid text null,
  constraint users_pkey primary key (user_id),
  constraint users_email_key unique (email),
  constraint users_firebase_uid_key unique (firebase_uid)
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

create table public.companies (
  company_id serial not null,
  ticker_symbol character varying(10) not null,
  company_name character varying(255) not null,
  exchange character varying(50) not null default 'UNKNOWN'::character varying,
  sector character varying(100) null,
  industry character varying(100) null,
  currency character varying(3) not null default 'USD'::character varying,
  description text null,
  website character varying(255) null,
  created_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone not null default CURRENT_TIMESTAMP,
  next_earnings_date date null,
  constraint companies_new_pkey primary key (company_id),
  constraint companies_ticker_exchange_unique unique (ticker_symbol, exchange)
) TABLESPACE pg_default;

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

### 7.1 Deep Sync Financial Tables

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
  constraint income_statements_pkey primary key (is_id)
) TABLESPACE pg_default;

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
  constraint balance_sheets_pkey primary key (bs_id)
) TABLESPACE pg_default;

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
  constraint cash_flow_statements_pkey primary key (cf_id)
) TABLESPACE pg_default;

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
  shares_outstanding_basic bigint null,
  shares_outstanding_diluted bigint null,
  currency character(3) null,
  data_source character varying(50) null,
  calculated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint statistics_pkey primary key (stat_id)
) TABLESPACE pg_default;

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
  constraint earnings_pkey primary key (earnings_id)
) TABLESPACE pg_default;

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
  constraint dividend_history_pkey primary key (dividend_id)
) TABLESPACE pg_default;
```
