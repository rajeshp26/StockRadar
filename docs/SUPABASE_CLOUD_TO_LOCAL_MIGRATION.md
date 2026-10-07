# Supabase Cloud → Local Migration Plan

**Date:** 2026-08-02
**Status:** Ready for Review
**Cloud Project:** `viqdqgxcumcdhqxooplw` (https://viqdqgxcumcdhqxooplw.supabase.co)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Database Schema Inventory](#3-database-schema-inventory)
4. [Supabase Interaction Code Map](#4-supabase-interaction-code-map)
5. [Migration Plan — Step by Step](#5-migration-plan--step-by-step)
6. [Environment Variables](#6-environment-variables)
7. [Verification Mechanism — Ensuring Zero Data Loss](#7-verification-mechanism--ensuring-zero-data-loss)
8. [Rollback Plan](#8-rollback-plan)
9. [Risks & Mitigations](#9-risks--mitigations)

---

## 1. Executive Summary

StockerPro currently connects to a **hosted Supabase project** at `viqdqgxcumcdhqxooplw.supabase.co`. The goal is to run **Supabase entirely locally** using Docker, eliminating the cloud dependency for development and testing.

### What Changes

| Aspect | Current (Cloud) | Target (Local) |
|--------|----------------|----------------|
| Database host | `viqdqgxcumcdhqxooplw.supabase.co` | `localhost:5432` (Postgres) |
| Auth endpoint | `viqdqgxcumcdhqxooplw.supabase.co/auth/v1` | `localhost:54320/auth/v1` (GoTrue) |
| API endpoint | `viqdqgxcumcdhqxooplw.supabase.co/rest/v1` | `localhost:54321/rest/v1` (PostgREST) |
| Supabase Dashboard | Cloud dashboard | `localhost:54323` (Studio) |
| Docker containers | None | 5 containers (Kong, GoTrue, PostgREST, Realtime, Studio) |

### What Stays the Same

- All 55+ database tables and their schemas
- Backend Python code (repository pattern, Supabase client SDK)
- Frontend TypeScript code (auth flow, API calls)
- JWT verification logic (HS256 local verification)
- All SQL migrations (already in `backend/scripts/` and `backend/supabase/migrations/`)

---

## 2. Current State Analysis

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Auth Provider│  │  Supabase.ts │  │  Middleware (CSP) │  │
│  │  (signUp,     │  │  (browser    │  │  (hardcodes cloud │  │
│  │   signIn,     │  │   client)    │  │   URL in CSP)     │  │
│  │   signOut)    │  │              │  │                    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘  │
│         │                  │                                  │
│         ▼                  ▼                                  │
│  ┌──────────────────────────────────────┐                   │
│  │  /api/auth/session (cookie mint)     │                   │
│  │  /api/proxy/[...path] (BFF proxy)    │                   │
│  └──────────────────┬───────────────────┘                   │
└─────────────────────┼───────────────────────────────────────┘
                      │ Authorization: Bearer <jwt>
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI/Python)                     │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │  auth.py  │  │ database.py  │  │  config.py         │   │
│  │  (verify  │  │ (lazy proxy  │  │  (SUPABASE_URL,    │   │
│  │   JWT)    │  │  singleton)  │  │   SERVICE_ROLE_KEY, │   │
│  └──────────┘  └──────┬───────┘  │   JWT_SECRET)       │   │
│                        │          └────────────────────┘   │
│                        ▼                                    │
│  ┌──────────────────────────────────────┐                  │
│  │  Supabase Python Client (service_role)│                  │
│  │  supabase.table("...").select()...    │                  │
│  └──────────────────┬───────────────────┘                  │
└─────────────────────┼───────────────────────────────────────┘
                      │ HTTPS (service_role key)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Supabase Cloud (viqdqgxcumcdhqxooplw)          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Postgres │  │ PostgREST│  │  GoTrue  │  │  Kong    │  │
│  │ (55+ tbl)│  │ (REST API│  │  (Auth)  │  │  (Proxy) │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Authentication Flow

1. Frontend calls `supabase.auth.signUp()` or `supabase.auth.signInWithPassword()` → goes to Supabase Auth (confirmed in `auth-provider.tsx:87` and `login-form.tsx`)
2. On success, `onAuthStateChange` fires (`auth-provider.tsx:201`) → `persistSessionCookie()` sends JWT to `/api/auth/session`
3. Next.js server mints httpOnly `__session` cookie (`session/route.ts:22-27`) containing the Supabase JWT, verified with `SUPABASE_JWT_SECRET` (`session/route.ts:53`)
4. All API requests go through `/api/proxy/[...path]` → reads `__session` cookie (`proxy/[...path]/route.ts:34,61`) → injects `Authorization: Bearer <jwt>` (`proxy/[...path]/route.ts:114`)
5. FastAPI backend verifies JWT locally using `SUPABASE_JWT_SECRET` (HS256) or cached JWKS (RS256) — no network call per request

### 2.3 Database Access Pattern

- Backend uses **only the `service_role` key** via `database.py` — bypasses all RLS
- `database.py` creates a lazy-initialized singleton using `supabase.create_client()` with `SyncClientOptions(storage=SyncMemoryStorage())` — Python SDK v2.28.3
- Frontend **never queries database tables directly** — all queries go through backend
- Frontend only uses Supabase for Auth operations (sign-in, sign-up, OAuth, session management)
- No Edge Functions, no Realtime subscriptions, no database RPC calls
- Supabase JS SDK: `@supabase/supabase-js@^2.49.0` + `@supabase/ssr@^0.6.1`

### 2.4 Environment Variables

| Variable | Location | Current Value |
|----------|----------|---------------|
| `SUPABASE_URL` | `backend/.env` | `https://viqdqgxcumcdhqxooplw.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/.env` | (secret — set locally, never committed) |
| `SUPABASE_JWT_SECRET` | `backend/.env` | (base64 HS256 secret) |
| `NEXT_PUBLIC_SUPABASE_URL` | `web/.env.local` | `https://viqdqgxcumcdhqxooplw.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `web/.env.local` | (JWT anon key) |
| `SUPABASE_JWT_SECRET` | `web/.env.local` | (same as backend) |

---

## 3. Database Schema Inventory

### 3.1 Tables by Domain (55+ tables)

#### Core Business (5 tables)
| Table | Description |
|-------|-------------|
| `companies` | Stock/company master data (ticker, name, exchange, sector, industry) |
| `users` | User accounts (linked to Supabase Auth via `auth_id`) |
| `currencies` | Currency reference data (ISO 4217 codes) |
| `current_market_data` | Latest real-time price per company |
| `price_history` | Historical daily OHLCV price data |

#### Financial Statements (4 tables)
| Table | Description |
|-------|-------------|
| `income_statements` | Quarterly/annual income statements |
| `balance_sheets` | Quarterly/annual balance sheets |
| `cash_flow_statements` | Quarterly/annual cash flow statements |
| `financial_ratios` | Pre-computed ratios, health scores, valuation multiples |

#### Portfolio (10 tables + 1 view)
| Table | Description |
|-------|-------------|
| `portfolio_accounts` | User brokerage accounts |
| `portfolio_holdings` | Current holdings per account |
| `portfolio_transactions` | Buy/sell transaction log |
| `portfolio_dividends` | Dividend payments received |
| `portfolio_events` | Immutable event-sourced log (append-only) |
| `portfolio_snapshots` | Daily portfolio valuation snapshots |
| `portfolio_performance` | Legacy performance snapshots |
| `portfolio_brokerages` | Brokerage definitions |
| `portfolio_import_history` | CSV import job tracking |
| `portfolio_user_import_history` | Per-user import tracking (used in `portfolio_repository.py`) |

**Views (created in cloud, no CREATE VIEW in codebase):**
| View | Description |
|------|-------------|
| `portfolio_monthly_dividends` | Pre-aggregated monthly dividend summaries (used in `portfolio_repository.py:get_monthly_dividends()`) |

> **⚠️ Critical:** `portfolio_monthly_dividends` is a **VIEW**, not a table. It does not have a `CREATE VIEW` statement in the codebase — it was created directly in the cloud database. You **must** export this view's definition from the cloud database before migration. See [Step 5 — Exporting Views](#step-5-exporting-views-from-cloud).

#### Watchlist (2 tables)
| Table | Description |
|-------|-------------|
| `watchlists` | User watchlists |
| `watchlist_items` | Individual watchlist entries |

#### Valuation & Analysis (8 tables)
| Table | Description |
|-------|-------------|
| `valuation_runs` | Completed valuation calculation records |
| `valuation_method_defaults` | Default valuation methods |
| `company_valuation_overrides` | User overrides for valuation methods |
| `intrinsic_value_analysis` | Intrinsic value computation results |
| `dcf_valuations` | DCF valuation details |
| `ddm_valuations` | DDM valuation details |
| `industry_multiples` | Sector/industry relative valuation multiples |
| `company_summary` | Aggregated company metrics over time |

#### Moat Analysis (3 tables)
| Table | Description |
|-------|-------------|
| `moat_analysis` | Economic moat composite scores |
| `moat_keyword_evidence` | Keyword match evidence from 10-K filings |
| `moat_ai_narratives` | Cached AI-generated moat narratives |

#### Dividend (3 tables)
| Table | Description |
|-------|-------------|
| `dividend_history` | Historical dividend payment facts |
| `dividend_metrics` | Aggregated dividend metrics |
| `upcoming_dividend_events` | Forward-looking dividend predictions |

#### Institutional / Super Investors (2 tables)
| Table | Description |
|-------|-------------|
| `institutional_investors` | Super investor profiles |
| `institutional_holdings` | Super investor quarterly 13-F holdings |

#### Scheduler / Infrastructure (8 tables)
| Table | Description |
|-------|-------------|
| `jobs` | Durable job queue |
| `job_attempts` | Per-job attempt history |
| `scheduler_state` | One row per scheduler (state machine) |
| `scheduler_run_history` | Append-only planner cycle log |
| `worker_heartbeats` | Worker liveness tracking |
| `resource_locks` | Cross-job resource serialization |
| `company_refresh_requests` | Scope accumulator for unified refresh |
| `scheduler_locks` | Per-company scheduler locks |

#### Event Sourcing (2 tables)
| Table | Description |
|-------|-------------|
| `event_sequence` | BIGSERIAL sequence for event polling |
| `projection_checkpoint` | Resumable polling checkpoint |

#### FX / Currency (1 table)
| Table | Description |
|-------|-------------|
| `exchange_rates` | Daily FX rates for multi-currency support |

> **Note:** `fx_rate_history` exists in migration SQL (`migrate_create_portfolio_events.sql`) and design docs but has **no production `.table()` calls**. It may exist in the cloud database but is not actively used by the application.

#### Data Quality (2 tables)
| Table | Description |
|-------|-------------|
| `data_quality_events` | Data quality audit event log |
| `data_conflicts` | Data conflict detection log |

> **Note:** `derived_financial_metrics` exists in the cloud schema (`docs/Supabase_Schema.md`) but the application code writes computed metrics to `financial_ratios` instead. The `derived_financial_metrics_job.py` function `compute_and_upsert_derived_financial_metrics()` explicitly states: *"Does NOT write to: derived_financial_metrics (deprecated)"*. This table may exist in the cloud database but is not actively written to.

#### Aggregation (2 tables)
| Table | Description |
|-------|-------------|
| `group_metric_stats` | Percentile distribution stats per sector/industry |
| `aggregation_state` | Distributed lock + watermark for aggregation |

#### Price Pipeline (2 tables)
| Table | Description |
|-------|-------------|
| `price_sources` | Real-time price ingestion pipeline |
| `price_source_preferences` | Per-company preferred price source |

#### Forecast (2 tables)
| Table | Description |
|-------|-------------|
| `revenue_forecast` | Revenue forecast data |
| `earnings_forecast` | Earnings forecast data |

#### Other (6 tables)
| Table | Description |
|-------|-------------|
| `earnings` | Earnings announcement data |
| `splits` | Stock split events |
| `benchmark_config` | Market benchmark configuration |
| `risk_ai_narratives` | Cached AI risk narratives |
| `analyst_eps_estimates` | Analyst EPS estimates **(schema-only — no `.table()` calls in production code)** |
| `security_master` | Canonical company-to-identifier mapping **(schema-only — no `.table()` calls in production code, only in migration SQL)** |

### 3.2 SQL Migrations Found

**Location: `backend/supabase/migrations/` (4 files)**
1. `001_create_exchange_rates_table.sql` — Creates `exchange_rates` with RLS
2. `002_add_cdr_ratio_to_companies.sql` — Adds `cdr_ratio` and `cdr_ratio_date` columns
3. `003_add_split_processed.sql` — Adds `processed` boolean to `splits`
4. `004_alter_scheduler_interval_hours_to_numeric.sql` — Widens `scheduler_state.interval_hours`

**Location: `backend/scripts/` (17 SQL files)**
1. `migrate_scheduler_v3_tables.sql` — Creates 7 scheduler tables
2. `migrate_create_portfolio_events.sql` — Creates `portfolio_events`, `security_master`, `fx_rate_history`
3. `migrate_moat_analysis.sql` — Creates moat analysis tables
4. `migrate_fundamentals_health_scores.sql` — Adds Piotroski + Altman Z-score columns
5. `migrate_valuation_multiples.sql` — Adds market_cap, enterprise_value, etc.
6. `migrate_users_schema_v2.sql` — Adds profile fields + UNIQUE constraints
7. `migrate_upcoming_dividend_events.sql` — Creates `upcoming_dividend_events`
8. `migrate_portfolio_transactions_unique.sql` — Adds UNIQUE fingerprint
9. `migrate_portfolio_import_defaults.sql` — Fixes constraints
10. `migration_group_metric_stats.sql` — Creates `group_metric_stats` and `aggregation_state`
11. `migration_job_id_not_null.sql` — Enforces `job_id NOT NULL`
12. `add_portfolio_snapshots_table.sql` — Creates `portfolio_snapshots`
13. `add_price_sources_table.sql` — Creates price pipeline tables
14. `add_price_observability_columns.sql` — Adds price tracking columns
15. `add_portfolio_indexes.sql` — Adds indexes
16. `sql/migration_step2_tables.sql` — Creates `event_sequence` + `projection_checkpoint`
17. `drop_current_market_data.sql` — **⚠️ ENTIRELY COMMENTED OUT** — planned deprecation of `current_market_data` table. Do NOT apply unless you intend to drop that table.

---

## 4. Supabase Interaction Code Map

### 4.1 Backend Python Files (44+ files)

**Core Client Setup:**
- `backend/database.py` — Lazy-initialized Supabase client singleton (service_role key)
- `backend/config.py` — Pydantic settings validation (SUPABASE_URL, SERVICE_ROLE_KEY, JWT_SECRET)
- `backend/auth.py` — JWT verification (HS256 local + RS256 JWKS fallback)

**Repository Layer (Data Access):**
- `backend/infrastructure/repositories/supabase_repository.py` — Watchlist + User repos
- `backend/infrastructure/repositories/portfolio_repository.py` — Portfolio CRUD
- `backend/infrastructure/repositories/portfolio_snapshots_repository.py` — Snapshot CRUD
- `backend/infrastructure/repositories/financial_repository.py` — Financial data writes
- `backend/infrastructure/repositories/valuation_repository.py` — Valuation reads/writes
- `backend/infrastructure/repositories/analysis_repository.py` — Analysis reads
- `backend/infrastructure/repositories/risk_repository.py` — Risk data reads
- `backend/infrastructure/repositories/moat_repository.py` — Moat analysis CRUD
- `backend/infrastructure/repositories/fundamentals_repository.py` — Fundamentals reads
- `backend/infrastructure/repositories/price_repository.py` — Price pipeline
- `backend/infrastructure/repositories/scheduler_repository.py` — Scheduler v3 tables
- `backend/infrastructure/repositories/event_store.py` — Event sourcing

**API Layer:**
- `backend/api/watchlists.py`, `api/watchlist_items.py`, `api/users.py`
- `backend/api/stocks.py`, `api/portfolio.py`, `api/super_investors.py`
- `backend/api/valuations.py`, `api/analysis.py`

**Jobs / Schedulers:**
- `backend/application/jobs/portfolio_snapshot_job.py`
- `backend/application/jobs/derived_financial_metrics_job.py`
- `backend/application/jobs/data_quality_audit_job.py`
- `backend/application/jobs/aggregation_jobs.py`
- `backend/application/jobs/price_ingestion_job.py`
- `backend/application/schedulers/market_data_scheduler.py`
- `backend/application/schedulers/super_investors_scheduler.py`
- `backend/application/schedulers/aggregation_scheduler.py`

### 4.2 Frontend TypeScript Files (8 files)

- `web/src/lib/supabase.ts` — Browser Supabase client singleton
- `web/src/providers/auth-provider.tsx` — Auth context (signUp, signIn, signOut)
- `web/src/components/auth/login-form.tsx` — Email/password sign-in
- `web/src/components/auth/step-verify-email.tsx` — Email verification flow
- `web/src/app/auth/callback/route.ts` — OAuth callback (server-side)
- `web/src/app/api/auth/session/route.ts` — Session cookie management
- `web/src/app/api/proxy/[...path]/route.ts` — Secure proxy bridge
- `web/src/middleware.ts` — CSP headers (hardcodes cloud URL)

### 4.3 Key Architecture Decision

**The backend connects with `service_role` key only.** This means:
- All RLS policies are bypassed (service_role has full access)
- The frontend never queries database tables directly
- All table queries go through the Next.js proxy → FastAPI backend
- Frontend only uses Supabase for Auth operations

**Impact for local migration:** We can disable RLS entirely on the local instance since the backend bypasses it anyway. This simplifies the local setup significantly.

> **⚠️ Note on `get_supabase_user_client`:** This function in `database.py` accepts an optional `id_token` parameter but **ignores it entirely** — it always returns the same service-role client. User-level scoping is not implemented. This means there is no difference between the service-role client and the "user" client; all database operations use the service-role key.

### 4.4 Additional Cloud URL References

The cloud Supabase URL (`https://viqdqgxcumcdhqxooplw.supabase.co`) is hardcoded in **21 locations** across the codebase. Beyond `web/src/middleware.ts` (CSP headers), these files also reference it:

| File | Line | Context |
|------|------|---------|
| `mobile/lib/main.dart` | 15 | Default value for `supabaseUrl` |
| `backend/scripts/seed_e2e_data.ps1` | 8 | Seed script URL |
| `backend/tests/test_portfolio_api_latency.py` | 21 | Test constant |
| `backend/tests/test_portfolio_e2e_performance.py` | 25 | Test constant |
| `docs/architecture-design.md` | 161, 540, 552 | Documentation |
| `docs/FUNDAMENTALS_TAB_DESIGN.md` | 1452 | Documentation |

**For local migration:** Only `web/src/middleware.ts` (Step 9) and the `.env` files (Steps 7-8) **must** be updated. The mobile app, tests, and docs can remain pointing at the cloud URL unless you want a fully local setup.

---

## 5. Migration Plan — Step by Step

### Step 1: Install Docker Desktop (if not installed)

**Prerequisites:**
- Docker Desktop for Windows with WSL 2 backend enabled
- At least 4GB RAM allocated to Docker
- Ports available: 5432, 54320, 54321, 54323, 54324, 54325, 8000, 8443

**Actions:**
1. Download Docker Desktop from https://docs.docker.com/desktop/install/windows-install/
2. Install with WSL 2 backend enabled
3. Allocate at least 4GB RAM in Docker Desktop → Settings → Resources → Advanced
4. Verify: `docker --version` and `docker compose version`

**Outcome:** Docker Desktop running with WSL 2 backend.

---

### Step 2: Initialize Supabase CLI

**Actions:**
```bash
# Install Supabase CLI (one-time)
npm install -g supabase

# Initialize Supabase in project root
cd C:\Project\StockerPro\StockerPro
supabase init
```

This creates:
```
supabase/
  config.toml    # Supabase local dev configuration
```

**Outcome:** `supabase/config.toml` created at project root.

---

### Step 3: Configure Local Supabase

Edit `supabase/config.toml` to match the project's needs:

```toml
[project]
id = "stockerpro-local"

[api]
port = 54321
schemas = ["public", "graphql_public"]
extra_search_path = ["public", "extensions"]
max_rows = 1000

[db]
port = 5432
shadow_port = 54320
major_version = 15

[studio]
port = 54323
api_url = "http://localhost"

[inbucket]
port = 54324
smtp_port = 54325
pop3_port = 54326

[auth]
site_url = "http://localhost:3000"
additional_redirect_urls = ["https://localhost:3000"]
jwt_expiry = 3600
enable_refresh_token_rotation = true
refresh_token_reuse_interval = 10
enable_signup = true

[auth.email]
enable_signup = true
double_confirm_changes = true
enable_confirmations = false

[auth.external.google]
enabled = true
client_id = ""
secret = ""
redirect_uri = "http://localhost:54321/auth/v1/callback"

[storage]
file_size_limit = "50MiB"
```

**Key configuration notes:**
- `site_url` = `http://localhost:3000` (Next.js dev server)
- Email confirmations disabled for local dev (faster testing)
- Google OAuth placeholder (needs real credentials for OAuth to work locally)

**Outcome:** Local Supabase configured for development.

---

### Step 4: Start Local Supabase

**Actions:**
```bash
cd C:\Project\StockerPro\StockerPro
supabase start
```

This pulls Docker images and starts all services:
- **Kong** (API gateway) — ports 8000, 8443
- **PostgREST** (REST API) — port 54321
- **GoTrue** (Auth) — port 54320
- **PostgreSQL** — port 5432
- **Supabase Studio** — port 54323
- **Inbucket** (email testing) — port 54324

**First start takes 2-5 minutes** to pull images.

After startup, Supabase CLI outputs:
```
Started supabase local development setup.

         API URL: http://localhost
          DB URL: postgresql://postgres:postgres@localhost:5432/postgres
      Studio URL: http://localhost:54323
    Inbucket URL: http://localhost:54324
        anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**SAVE THESE KEYS** — you'll need them for environment variables.

**Outcome:** Local Supabase running on localhost. Studio accessible at http://localhost:54323.

---

### Step 4.5: Export Views from Cloud (CRITICAL — No Data Loss)

**⚠️ This step is critical to prevent data loss.** Some database objects exist in the cloud database but have no `CREATE` statement in the codebase. These **must** be exported before migration.

**Views to export:**

The `portfolio_monthly_dividends` view is used by `portfolio_repository.py` but has no `CREATE VIEW` statement anywhere in the codebase. It was created directly in the cloud database.

**Actions:**
```bash
# Connect to cloud database and export the view definition
# You need the cloud database password (from Supabase Dashboard → Settings → Database)

# Option 1: Using psql
psql "postgresql://postgres:[PASSWORD]@db.viqdqgxcumcdhqxooplw.supabase.co:5432/postgres" \
  -c "SELECT pg_get_viewdef('portfolio_monthly_dividends', true);"

# Option 2: Using Supabase Dashboard
# Go to SQL Editor → Run:
# SELECT pg_get_viewdef('portfolio_monthly_dividends', true);
# Copy the output and save it

# Save the view definition to a file
# Save as: backend/scripts/create_portfolio_monthly_dividends_view.sql
```

**Also check for other views:**
```sql
-- List all views in the database
SELECT table_name, view_definition
FROM information_schema.views
WHERE table_schema = 'public';
```

**Apply to local after schema is created:**
```bash
supabase db exec --file backend/scripts/create_portfolio_monthly_dividends_view.sql
```

**Outcome:** All views exported from cloud and ready to apply locally.

---

### Step 5: Apply Database Schema

**Option A: Apply all migrations in order (recommended)**

```bash
cd C:\Project\StockerPro\StockerPro

# Apply each migration file via supabase db exec
supabase db exec --file backend/supabase/migrations/001_create_exchange_rates_table.sql
supabase db exec --file backend/supabase/migrations/002_add_cdr_ratio_to_companies.sql
supabase db exec --file backend/supabase/migrations/003_add_split_processed.sql
supabase db exec --file backend/supabase/migrations/004_alter_scheduler_interval_hours_to_numeric.sql

# Apply script migrations
supabase db exec --file backend/scripts/migrate_scheduler_v3_tables.sql
supabase db exec --file backend/scripts/migrate_create_portfolio_events.sql
supabase db exec --file backend/scripts/migrate_moat_analysis.sql
supabase db exec --file backend/scripts/migrate_fundamentals_health_scores.sql
supabase db exec --file backend/scripts/migrate_valuation_multiples.sql
supabase db exec --file backend/scripts/migrate_users_schema_v2.sql
supabase db exec --file backend/scripts/migrate_upcoming_dividend_events.sql
supabase db exec --file backend/scripts/migrate_portfolio_transactions_unique.sql
supabase db exec --file backend/scripts/migrate_portfolio_import_defaults.sql
supabase db exec --file backend/scripts/migration_group_metric_stats.sql
supabase db exec --file backend/scripts/migration_job_id_not_null.sql
supabase db exec --file backend/scripts/add_portfolio_snapshots_table.sql
supabase db exec --file backend/scripts/add_price_sources_table.sql
supabase db exec --file backend/scripts/add_price_observability_columns.sql
supabase db exec --file backend/scripts/add_portfolio_indexes.sql
supabase db exec --file backend/scripts/sql/migration_step2_tables.sql
```

**Option B: Export full schema from cloud and apply (alternative)**

If you have `pg_dump` access to the cloud database:
```bash
# Export from cloud (requires cloud database password from Supabase Dashboard → Settings → Database)
pg_dump -h db.viqdqgxcumcdhqxooplw.supabase.co -U postgres -d postgres \
  --schema-only --no-owner --no-privileges \
  -f supabase/schema-full.sql

# Apply to local
supabase db exec --file supabase/schema-full.sql
```

> **⚠️ Important:** `pg_dump` requires the **database password**, not the service_role key. Find it in Supabase Dashboard → Project Settings → Database → Connection string → Password.

**⚠️ Important:** Some migrations may have dependencies (e.g., `companies` table must exist before `income_statements`). Apply in the order listed above, or use Option B for a clean schema export. Also note that `portfolio_monthly_dividends` is a **VIEW** — if using Option B, it will be included in the schema dump. If using Option A, you must create it separately (see Step 4.5).

**Outcome:** All 55+ tables created in local PostgreSQL.

---

### Step 6: Seed Initial Data (Optional)

If you need reference data (currencies, etc.):

```bash
# Create a seed file
cat > supabase/seed.sql << 'EOF'
-- Seed currencies
INSERT INTO currencies (code, name, symbol) VALUES
  ('USD', 'US Dollar', '$'),
  ('CAD', 'Canadian Dollar', 'C$'),
  ('EUR', 'Euro', '€'),
  ('GBP', 'British Pound', '£'),
  ('JPY', 'Japanese Yen', '¥')
ON CONFLICT (code) DO NOTHING;
EOF

# Apply seed
supabase db exec --file supabase/seed.sql
```

Or use `supabase seed` to run `supabase/seed.sql` automatically on `supabase start`.

**Outcome:** Reference data seeded into local database.

---

### Step 7: Update Backend Environment Variables

Edit `backend/.env`:

```env
# Supabase — LOCAL
SUPABASE_URL=http://localhost
SUPABASE_SERVICE_ROLE_KEY=<service_role key from Step 4 output>
SUPABASE_JWT_SECRET=<jwt-secret from supabase/config.toml [auth] section>

# Everything else stays the same
OPEN_ROUTER_KEY='sk-or-v1-...'
OPEN_ROUTER_MODEL='openai/gpt-oss-120b:free'
EDGAR_IDENTITY="StockerPro rajeshp01@gmail.com"
ENABLE_SUPER_INVESTORS_SCHEDULER=true
ENABLE_EVENT_REPLAY_SNAPSHOTS=true
EVENT_REPLAY_COMPARISON_MODE=true
```

**Key changes:**
- `SUPABASE_URL`: `https://viqdqgxcumcdhqxooplw.supabase.co` → `http://localhost`
- `SUPABASE_SERVICE_ROLE_KEY`: Use the service_role key from `supabase start` output
- `SUPABASE_JWT_SECRET`: Use the JWT secret from `supabase/config.toml`

**Outcome:** Backend configured to connect to local Supabase.

---

### Step 8: Update Frontend Environment Variables

Edit `web/.env.local`:

```env
# Supabase — LOCAL
NEXT_PUBLIC_SUPABASE_URL=http://localhost
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key from Step 4 output>

# Backend Configuration
BACKEND_ORIGIN=http://127.0.0.1:8001
PROXY_IDTOKEN_COOKIE=__session
PROXY_EXTRA_TOKEN_HEADERS=x-id-token,x-firebase-token
PROXY_REQUIRE_AUTH=true

# JWT secret for local token verification (mirrors backend/.env)
SUPABASE_JWT_SECRET=<jwt-secret from supabase/config.toml>
```

**Key changes:**
- `NEXT_PUBLIC_SUPABASE_URL`: Cloud URL → `http://localhost`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Use the anon key from `supabase start` output

**⚠️ Important:** The anon key from local Supabase is different from the cloud anon key. Using the wrong key will break auth.

**Outcome:** Frontend configured to connect to local Supabase.

---

### Step 9: Update CSP Headers in Middleware

Edit `web/src/middleware.ts`:

Replace all occurrences of `https://viqdqgxcumcdhqxooplw.supabase.co` with `http://localhost`:

```typescript
// In buildCsp() function, both dev and production blocks:

// Development block (line ~37):
"connect-src 'self'" +
" http://localhost:*" +
" ws://localhost:*" +
" wss://localhost:*" +
" http://localhost" +           // ← ADD THIS (local Supabase)
" https://*.googleapis.com",

// Production block (line ~54):
"connect-src 'self'" +
" http://localhost" +           // ← ADD THIS (local Supabase)
" https://*.googleapis.com",
```

**Additional files with hardcoded cloud URL (optional to update):**

| File | Change Required |
|------|-----------------|
| `mobile/lib/main.dart:15` | Update default `supabaseUrl` if mobile app should use local |
| `backend/scripts/seed_e2e_data.ps1:8` | Update if seed script should run against local |
| `backend/tests/test_portfolio_api_latency.py:21` | Update if tests should run against local |
| `backend/tests/test_portfolio_e2e_performance.py:25` | Update if tests should run against local |

> **Note:** The test and mobile files are optional — they only matter if you want those components to also use the local instance. The core app (backend + web frontend) only requires the middleware and `.env` changes.

**Outcome:** CSP allows connections to local Supabase.

---

### Step 10: Update Auth Verification for Local JWKS

The `backend/auth.py` file fetches JWKS from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. For local Supabase, this becomes `http://localhost/auth/v1/.well-known/jwks.json`.

**No code change needed** — the URL is constructed from `settings.SUPABASE_URL`, which we updated in Step 7.

However, local Supabase uses HS256 (shared secret) by default, not RS256 (JWKS). The auth code already supports both:

```python
# backend/auth.py line 90-95
if alg == "HS256":
    decoded = _verify_hs256(token, options)
elif alg == "RS256":
    decoded = _verify_rs256(token, kid, options)
```

**Verify:** After starting local Supabase, check which algorithm the JWT uses:
```bash
# Decode the JWT header (without verification)
echo "<token>" | cut -d'.' -f1 | base64 -d 2>/dev/null || echo "<token>" | cut -d'.' -f1 | base64 -d
```

If it returns `{"alg":"HS256",...}`, the backend will use `_verify_hs256()` with the JWT secret. No JWKS fetch needed.

**Outcome:** Auth verification works with local Supabase JWTs.

---

### Step 11: Update Google OAuth Redirect URLs (If Used)

If Google OAuth is enabled:

1. Go to Google Cloud Console → APIs & Services → Credentials
2. Add `http://localhost:54321/auth/v1/callback` to Authorized redirect URIs
3. Update `supabase/config.toml`:
   ```toml
   [auth.external.google]
   enabled = true
   client_id = "your-google-client-id"
   secret = "your-google-client-secret"
   redirect_uri = "http://localhost:54321/auth/v1/callback"
   ```

**Outcome:** Google OAuth works with local Supabase.

---

### Step 12: Start Backend and Frontend

**Terminal 1 — Backend:**
```bash
cd C:\Project\StockerPro\StockerPro\backend
.\venv\Scripts\activate    # Windows
# or: source .venv/bin/activate  # WSL/Linux
python main.py
```

**Terminal 2 — Frontend:**
```bash
cd C:\Project\StockerPro\StockerPro\web
npm run dev
```

**Verify startup:**
- Backend: http://localhost:8001/docs (FastAPI docs)
- Frontend: http://localhost:3000
- Supabase Studio: http://localhost:54323

**Outcome:** Full stack running locally.

---

### Step 13: Test Authentication Flow

1. Open http://localhost:3000
2. Navigate to login page
3. Test email/password sign-up:
   - Enter email and password
   - Check Inbucket (http://localhost:54324) for confirmation email (if enabled)
   - Complete sign-up
4. Test sign-in with created account
5. Verify session cookie is set (browser DevTools → Application → Cookies)
6. Verify API calls work (Network tab should show 200 responses)

**Outcome:** Authentication flow works end-to-end with local Supabase.

---

### Step 14: Test Database Operations

1. Sign in to the app
2. Create a watchlist
3. Add stocks to watchlist
4. Verify data appears in Supabase Studio (http://localhost:54323 → Table Editor)
5. Test portfolio operations if applicable

**Outcome:** Database read/write operations work with local Supabase.

---

## 6. Environment Variables — Complete Reference

> **⚠️ Note:** `SUPABASE_JWT_SECRET` is **missing from both `.env.example` files** (`backend/.env.example` and `web/.env.example`), even though it is a **required field** in `backend/config.py` (Pydantic `Field(...)` with no default). A new developer copying from `.env.example` would get a startup failure. This is a pre-existing documentation gap, not specific to the local migration.

### Backend (`backend/.env`)

```env
# ===========================================
# Supabase — LOCAL
# ===========================================
SUPABASE_URL=http://localhost
SUPABASE_SERVICE_ROLE_KEY=<from supabase start output>
SUPABASE_JWT_SECRET=<from supabase/config.toml [auth] section>

# ===========================================
# AI & External Providers (unchanged)
# ===========================================
OPEN_ROUTER_KEY='sk-or-v1-...'
OPEN_ROUTER_MODEL='openai/gpt-oss-120b:free'
EDGAR_IDENTITY="StockerPro rajeshp01@gmail.com"

# ===========================================
# Feature Flags (unchanged)
# ===========================================
ENABLE_SUPER_INVESTORS_SCHEDULER=true
ENABLE_EVENT_REPLAY_SNAPSHOTS=true
EVENT_REPLAY_COMPARISON_MODE=true
```

### Frontend (`web/.env.local`)

```env
# ===========================================
# Supabase — LOCAL
# ===========================================
NEXT_PUBLIC_SUPABASE_URL=http://localhost
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from supabase start output>

# ===========================================
# Backend Configuration (unchanged)
# ===========================================
BACKEND_ORIGIN=http://127.0.0.1:8001
PROXY_IDTOKEN_COOKIE=__session
PROXY_EXTRA_TOKEN_HEADERS=x-id-token,x-firebase-token
PROXY_REQUIRE_AUTH=true

# ===========================================
# JWT secret (from supabase/config.toml)
# ===========================================
SUPABASE_JWT_SECRET=<from supabase/config.toml [auth] section>
```

---

## 7. Verification Mechanism — Ensuring Zero Data Loss

This section defines the **exact mechanism** to confirm the migration is 100% accurate with no data loss or corruption. It uses a three-layer approach: **baseline capture → automated comparison → application smoke tests**.

### 7.1 Pre-Migration: Capture Cloud Baseline

Run these SQL queries against the **cloud database** (via Supabase Dashboard → SQL Editor) and save the results. These become your "source of truth."

**Save the output of each query to a file:** `docs/migration_baseline/`

```bash
mkdir -p docs/migration_baseline
```

#### Query 1: All tables with row counts
```sql
-- Save as: docs/migration_baseline/01_table_row_counts.csv
-- NOTE: n_live_tup is an approximation (PostgreSQL stats collector).
-- For exact counts, run SELECT COUNT(*) FROM <table> individually.
SELECT
    schemaname,
    tablename,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

#### Query 2: All views with definitions
```sql
-- Save as: docs/migration_baseline/02_view_definitions.csv
SELECT
    table_name,
    view_definition
FROM information_schema.views
WHERE table_schema = 'public'
ORDER BY table_name;
```

#### Query 3: All columns with types and constraints
```sql
-- Save as: docs/migration_baseline/03_column_definitions.csv
SELECT
    table_name,
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
```

#### Query 4: All indexes
```sql
-- Save as: docs/migration_baseline/04_indexes.csv
SELECT
    indexname,
    tablename,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

#### Query 5: All constraints
```sql
-- Save as: docs/migration_baseline/05_constraints.csv
-- NOTE: Uses pg_constraint directly for accurate FK column mapping.
-- information_schema joins cause Cartesian products for multi-column FKs.
SELECT
    c.conrelid::regclass::text AS table_name,
    c.conname AS constraint_name,
    CASE c.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'c' THEN 'CHECK'
        WHEN 't' THEN 'TRIGGER'
    END AS constraint_type,
    a.attname AS column_name,
    CASE WHEN c.contype = 'f'
        THEN c.confrelid::regclass::text
    END AS foreign_table_name,
    CASE WHEN c.contype = 'f'
        THEN (
            SELECT array_agg(ab.attname ORDER BY x.n)
            FROM unnest(c.conkey) WITH ORDINALITY AS x(attnum, n)
            JOIN pg_attribute ab ON ab.attrelid = c.confrelid AND ab.attnum = x.attnum
        )
    END AS foreign_columns
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.connamespace = 'public'::regnamespace
ORDER BY table_name, constraint_name;
```

#### Query 6: All triggers
```sql
-- Save as: docs/migration_baseline/06_triggers.csv
SELECT
    event_object_table AS table_name,
    trigger_name,
    action_timing,
    event_manipulation,
    action_statement
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table, trigger_name;
```

#### Query 7: All functions
```sql
-- Save as: docs/migration_baseline/07_functions.sql
-- NOTE: information_schema.routines.routine_definition is NULL for PL/pgSQL.
-- Use pg_proc.prosrc for complete function bodies.
SELECT
    p.proname AS routine_name,
    CASE p.prokind
        WHEN 'f' THEN 'FUNCTION'
        WHEN 'p' THEN 'PROCEDURE'
        WHEN 'a' THEN 'AGGREGATE'
        WHEN 'w' THEN 'WINDOW'
    END AS routine_type,
    pg_get_function_result(p.oid) AS return_type,
    p.prosrc AS routine_definition
FROM pg_proc p
JOIN pg_language l ON p.prolang = l.oid
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = 'public'
  AND p.prokind IN ('f', 'p')
ORDER BY p.proname;
```

#### Query 8: Total table count
```sql
-- Save as: docs/migration_baseline/08_table_count.txt
SELECT COUNT(*) AS total_tables
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
```

#### Query 9: Total view count
```sql
-- Save as: docs/migration_baseline/09_view_count.txt
SELECT COUNT(*) AS total_views
FROM information_schema.views
WHERE table_schema = 'public';
```

#### Query 10: Database size
```sql
-- Save as: docs/migration_baseline/10_database_size.txt
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;
```

---

### 7.2 Post-Migration: Verify Local Database

After applying all migrations to the local database, run the **exact same queries** against the local instance and save to `docs/migration_verification/`:

```bash
mkdir -p docs/migration_verification
```

```bash
# Run all baseline queries against local
# Use the same SQL files but connect to local:
psql "postgresql://postgres:postgres@localhost:5432/postgres" \
  -f docs/migration_baseline/01_table_row_counts.csv
# ... repeat for all queries
```

---

### 7.3 Automated Comparison Script

Create a Python script that connects to **both** cloud and local databases and compares them automatically.

**Save as:** `backend/scripts/verify_migration.py`

```python
"""
Migration Verification Script
Compares cloud and local Supabase databases to ensure zero data loss.

Usage:
    # Set cloud credentials (read-only)
    export CLOUD_DATABASE_URL="postgresql://postgres:[PASSWORD]@db.viqdqgxcumcdhqxooplw.supabase.co:5432/postgres"

    # Local is always:
    # postgresql://postgres:postgres@localhost:5432/postgres

    cd backend
    python scripts/verify_migration.py
"""
import os
import sys


def get_cloud_connection():
    """Connect to cloud database (requires password from Supabase Dashboard)."""
    try:
        import psycopg2
    except ImportError:
        print("SKIP: psycopg2 not installed (pip install psycopg2-binary)")
        return None

    url = os.environ.get("CLOUD_DATABASE_URL")
    if not url:
        print("SKIP: CLOUD_DATABASE_URL not set (set it to verify against cloud)")
        return None

    try:
        return psycopg2.connect(url)
    except Exception as e:
        print(f"SKIP: Cannot connect to cloud database: {e}")
        return None


def get_local_connection():
    """Connect to local Supabase database."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed (pip install psycopg2-binary)")
        sys.exit(1)

    try:
        return psycopg2.connect(
            "postgresql://postgres:postgres@localhost:5432/postgres"
        )
    except Exception as e:
        print(f"ERROR: Cannot connect to local database: {e}")
        sys.exit(1)


QUERY_TABLES = """
SELECT tablename
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY tablename;
"""

QUERY_VIEWS = """
SELECT table_name
FROM information_schema.views
WHERE table_schema = 'public'
ORDER BY table_name;
"""

QUERY_INDEXES = """
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
"""

QUERY_TRIGGERS = """
SELECT
    event_object_table AS table_name,
    trigger_name
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table, trigger_name;
"""

QUERY_CONSTRAINTS = """
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema = 'public'
ORDER BY tc.table_name, tc.constraint_name;
"""


def fetch_all(conn, query):
    """Fetch all rows from a query."""
    with conn.cursor() as cur:
        cur.execute(query)
        return set(row[0] if len(row) == 1 else row for row in cur.fetchall())


def fetch_row_counts(conn):
    """Fetch table names with row counts (approximate from stats collector)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename, n_live_tup
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        return {row[0]: row[1] for row in cur.fetchall()}


def compare(label, cloud_set, local_set):
    """Compare two sets and report differences."""
    missing_in_local = cloud_set - local_set
    extra_in_local = local_set - cloud_set

    if not missing_in_local and not extra_in_local:
        print(f"  [MATCH] {label}: {len(cloud_set)} items")
        return True
    else:
        print(f"  [MISMATCH] {label}")
        if missing_in_local:
            print(f"     Missing in local: {sorted(missing_in_local)}")
        if extra_in_local:
            print(f"     Extra in local: {sorted(extra_in_local)}")
        return False


def main():
    print("=" * 60)
    print("MIGRATION VERIFICATION: Cloud vs Local")
    print("=" * 60)

    cloud = get_cloud_connection()
    local = get_local_connection()

    if not cloud:
        print("\n  Cloud connection unavailable. Performing local-only checks.")
        print("  To verify against cloud, set CLOUD_DATABASE_URL.\n")

    all_passed = True

    try:
        # --- Local-only checks ---
        print("\n--- Local Database Structure Checks ---")

        local_tables = fetch_all(local, QUERY_TABLES)
        print(f"  Tables found: {len(local_tables)}")

        local_views = fetch_all(local, QUERY_VIEWS)
        print(f"  Views found: {len(local_views)}")

        local_indexes = fetch_all(local, QUERY_INDEXES)
        print(f"  Indexes found: {len(local_indexes)}")

        local_triggers = fetch_all(local, QUERY_TRIGGERS)
        print(f"  Triggers found: {len(local_triggers)}")

        # Check minimum expected counts
        expected_min_tables = 55
        if len(local_tables) < expected_min_tables:
            print(f"  [FAIL] Expected at least {expected_min_tables} tables, found {len(local_tables)}")
            all_passed = False
        else:
            print(f"  [PASS] {len(local_tables)} tables (expected >= {expected_min_tables})")

        # Check critical tables exist
        # This list covers all major feature areas with heavy .table() usage
        critical_tables = [
            # Core business
            "companies", "users", "currencies",
            # Watchlist
            "watchlists", "watchlist_items",
            # Portfolio
            "portfolio_accounts", "portfolio_holdings", "portfolio_transactions",
            "portfolio_events", "portfolio_snapshots", "portfolio_dividends",
            "portfolio_brokerages", "portfolio_performance",
            # Financial statements
            "income_statements", "balance_sheets", "cash_flow_statements",
            "financial_ratios", "earnings", "splits",
            # Market data
            "current_market_data", "price_history",
            # Dividends
            "dividend_history", "dividend_metrics", "upcoming_dividend_events",
            # Valuation
            "valuation_runs", "valuation_method_defaults",
            "company_valuation_overrides", "intrinsic_value_analysis",
            "dcf_valuations", "ddm_valuations", "industry_multiples",
            "company_summary",
            # Moat analysis
            "moat_analysis", "moat_keyword_evidence", "moat_ai_narratives",
            # Super investors
            "institutional_investors", "institutional_holdings",
            # Scheduler / infrastructure
            "jobs", "job_attempts", "scheduler_state",
            "scheduler_run_history", "worker_heartbeats",
            "resource_locks", "company_refresh_requests", "scheduler_locks",
            # Event sourcing
            "event_sequence", "projection_checkpoint",
            # FX / data quality
            "exchange_rates", "data_quality_events", "data_conflicts",
            # Aggregation
            "group_metric_stats", "aggregation_state",
            # Forecast
            "revenue_forecast", "earnings_forecast",
        ]
        missing_critical = [t for t in critical_tables if t not in local_tables]
        if missing_critical:
            print(f"  [FAIL] Missing critical tables: {missing_critical}")
            all_passed = False
        else:
            print(f"  [PASS] All {len(critical_tables)} critical tables present")

        # --- Cloud vs Local comparison ---
        if cloud:
            print("\n--- Cloud vs Local Comparison ---")

            cloud_tables = fetch_all(cloud, QUERY_TABLES)
            all_passed &= compare("Tables", cloud_tables, local_tables)

            cloud_views = fetch_all(cloud, QUERY_VIEWS)
            all_passed &= compare("Views", cloud_views, local_views)

            cloud_indexes = fetch_all(cloud, QUERY_INDEXES)
            all_passed &= compare("Indexes", cloud_indexes, local_indexes)

            cloud_triggers = fetch_all(cloud, QUERY_TRIGGERS)
            all_passed &= compare("Triggers", cloud_triggers, local_triggers)

            cloud_constraints = fetch_all(cloud, QUERY_CONSTRAINTS)
            local_constraints = fetch_all(local, QUERY_CONSTRAINTS)
            all_passed &= compare("Constraints", cloud_constraints, local_constraints)

            # Row count comparison (informational - local will be empty)
            print("\n--- Row Counts (Cloud) ---")
            cloud_counts = fetch_row_counts(cloud)
            for table, count in sorted(cloud_counts.items()):
                if count > 0:
                    print(f"  {table}: {count:,} rows")

            total_rows = sum(cloud_counts.values())
            print(f"\n  Total rows in cloud: {total_rows:,}")

    finally:
        local.close()
        if cloud:
            cloud.close()

    # --- Final result ---
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED - review output above")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

**Run after migration:**
```bash
cd C:\Project\StockerPro\StockerPro\backend

# Install psycopg2 if needed
pip install psycopg2-binary

# Set cloud database password (from Supabase Dashboard → Settings → Database)
export CLOUD_DATABASE_URL="postgresql://postgres:[YOUR-PASSWORD]@db.viqdqgxcumcdhqxooplw.supabase.co:5432/postgres"

# Run verification
python scripts/verify_migration.py
```

---

### 7.4 Application Smoke Tests

After the structural verification passes, run these application-level tests to confirm the app works end-to-end with the local database.

#### Test 1: Backend connects to local Supabase
```bash
cd C:\Project\StockerPro\StockerPro\backend
python -c "
from database import supabase
result = supabase.table('companies').select('company_id').limit(1).execute()
print(f'Backend connection OK. Companies table accessible: {len(result.data)} row(s)')
"
```

#### Test 2: Auth flow works
```bash
cd C:\Project\StockerPro\StockerPro\backend
python -c "
from tests.e2e.helpers import get_auth_headers
import httpx

headers = get_auth_headers()
print(f'Generated auth headers: {list(headers.keys())}')

# Test a protected endpoint
resp = httpx.get('http://localhost:8001/users/me', headers=headers, timeout=10)
print(f'GET /users/me: {resp.status_code}')
if resp.status_code == 200:
    print(f'Auth flow OK. User: {resp.json().get(\"email\", \"unknown\")}')
else:
    print(f'Auth flow issue: {resp.text}')
"
```

> **Note:** This test requires the backend to be running (start with `python main.py` in another terminal). The `get_auth_headers()` helper will auto-generate a test user and sign in via Supabase Auth, returning a valid JWT.

#### Test 3: Run existing E2E tests against local
```bash
cd C:\Project\StockerPro\StockerPro

# Point tests at local
export SUPABASE_URL=http://localhost
export SUPABASE_SERVICE_ROLE_KEY=<local-service-role-key>
export SUPABASE_ANON_KEY=<local-anon-key>
export E2E_BASE_URL=http://localhost:8001
export RUN_E2E=true

# Run E2E tests
python -m pytest tests/e2e/ -v
```

#### Test 4: Run backend unit tests
```bash
cd C:\Project\StockerPro\StockerPro\backend
python -m pytest tests/ -v --ignore=tests/integration -x
```

#### Test 5: Frontend builds without errors
```bash
cd C:\Project\StockerPro\StockerPro\web

# Prerequisite: web/.env.local must be configured per Step 8
# NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are inlined at build time
npm run build
```

> **Important:** A successful build does NOT guarantee the app will work. After building, verify:
> 1. `web/.env.local` has correct `NEXT_PUBLIC_SUPABASE_URL=http://localhost` (Step 8)
> 2. `web/src/middleware.ts` CSP headers allow `http://localhost` (Step 9)
> 3. Start the app with `npm run dev` and check browser console for CSP violations

---

### 7.5 Verification Decision Matrix

| Check | Tool | Pass Criteria | Fail Action |
|-------|------|---------------|-------------|
| Table count matches | `verify_migration.py` | Cloud count == Local count | Re-run migrations, check for errors |
| All critical tables present | `verify_migration.py` | 23 critical tables exist | Check migration order, apply missing migrations |
| View definitions match | `verify_migration.py` + manual SQL comparison | Same views, same definitions | Export views from cloud, apply to local |
| Index count matches | `verify_migration.py` | Cloud count == Local count | Check for missing CREATE INDEX in migrations |
| Constraint count matches | `verify_migration.py` | Cloud count == Local count | Check for missing constraints in migrations |
| Trigger count matches | `verify_migration.py` | Cloud count == Local count | Check for missing CREATE TRIGGER in migrations |
| Row counts (cloud reference) | `verify_migration.py` | Informational — shows what cloud has | N/A (local starts empty) |
| Backend connects | Manual Python test | No connection errors | Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` |
| Auth flow works | E2E tests | Sign-up/sign-in succeeds | Check `SUPABASE_JWT_SECRET`, anon key |
| Frontend builds | `npm run build` | No TypeScript errors | Fix any build errors |
| API endpoints respond | E2E tests | 200 status codes | Check backend logs, auth config |

### 7.6 What "No Data Loss" Means

For this migration, "no data loss" means:

1. **Schema parity**: Every table, view, index, constraint, trigger, and function in the cloud database exists in the local database with the same definition.
2. **No missing objects**: No table or view was accidentally omitted from the migration.
3. **No structural drift**: Column types, nullability, defaults, and constraints match exactly.
4. **Data is intentionally empty**: The local database starts empty — this is expected. The schema is what matters.
5. **Application works**: The app can perform all CRUD operations against the local database without errors.

**What is NOT a concern:**
- Row counts matching (local starts empty — you seed data as needed)
- Performance parity (local Docker is slower than cloud — expected)
- RLS policies (backend bypasses RLS via service_role key)

---

## 8. Rollback Plan

If local Supabase doesn't work or you need to revert:

1. **Stop local Supabase:**
   ```bash
   supabase stop
   ```

2. **Restore environment variables:**
   - `backend/.env`: Revert `SUPABASE_URL` to `https://viqdqgxcumcdhqxooplw.supabase.co`
   - `backend/.env`: Revert `SUPABASE_SERVICE_ROLE_KEY` to cloud key
   - `web/.env.local`: Revert `NEXT_PUBLIC_SUPABASE_URL` to cloud URL
   - `web/.env.local`: Revert `NEXT_PUBLIC_SUPABASE_ANON_KEY` to cloud anon key

3. **Restore CSP headers:**
   - `web/src/middleware.ts`: Remove `http://localhost` from `connect-src`

4. **Restart backend and frontend**

**No data loss** — the cloud database is untouched.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Docker not installed / WSL not configured | Cannot run local Supabase | Install Docker Desktop with WSL 2 backend first |
| Port conflicts (5432, 54321, etc.) | Services fail to start | Stop conflicting services or change ports in `config.toml` |
| Migrations have ordering dependencies | Schema creation fails | Apply migrations in the documented order, or export full schema from cloud |
| Views not exported from cloud | `portfolio_monthly_dividends` and other views missing → app errors | Export all views BEFORE migration (Step 4.5) — check `information_schema.views` |
| `pg_dump` requires database password, not service_role key | Export fails | Get password from Supabase Dashboard → Settings → Database → Connection string |
| Google OAuth doesn't work locally | Cannot test OAuth sign-in | Use email/password auth for local dev; configure OAuth separately if needed |
| Local Supabase uses different JWT algorithm | Auth verification fails | Check JWT header algorithm; backend already supports both HS256 and RS256 |
| CSP blocks local connections | Frontend cannot reach Supabase | Update `web/src/middleware.ts` CSP `connect-src` directive |
| Local data is empty | App shows no data | Seed reference data (currencies, companies) or export from cloud |
| Supabase CLI version mismatch | Unexpected behavior | Pin CLI version: `npm install -g supabase@1.x.x` |
| `derived_financial_metrics` table may have legacy data | Data confusion | This table is deprecated — app writes to `financial_ratios`. Safe to ignore or drop. |
| Mobile app / test files still point to cloud URL | Those components won't work locally | Update `mobile/lib/main.dart` and test files if needed (see Step 9) |

---

## 10. Quick Reference Commands

```bash
# Start local Supabase
supabase start

# Stop local Supabase (preserves data)
supabase stop

# Stop and wipe all data
supabase stop --no-backup

# View status
supabase status

# Apply a migration
supabase db exec --file path/to/migration.sql

# Open Supabase Studio
# http://localhost:54323

# View logs
supabase logs

# Reset database (drop all tables, reapply migrations)
supabase db reset
```

---

## Price History Recovery Status (2026-10-01)

### Outcome

The TRUE RAW refetch completed. The row-count reduction is dominated by the intended
10-year retention window, but two companies lost daily history that retention did not
account for. Recovery is **blocked on an external source** — see "What is missing".

### Verified numbers

| Measure | Value |
| --- | --- |
| Rows before refetch | 881,983 |
| Rows after refetch | 408,903 |
| Reduction | 473,080 |
| Attributable to the 10y retention window | ~468,103 |
| Known genuine shortfall | 4,977 (LEG 2,490 + RMAX 2,487) |
| Targeted regression tests | 142 passed |
| Split/factor identity defects | 0 (394 split rows, 108 companies) |

Mechanism: `backend/scripts/refetch_price_history.py:225` deletes every row for a
company, then reinserts only the rows the provider returns inside the retention
window. `prune_price_history()` has no active caller; the scheduler invocation is
commented out.

This classification is arithmetic over the refetch log, not a row-by-row
reconstruction. It is consistent with intended retention; it does **not** prove the
absence of any other in-window shortfall.

A coverage guard now refuses to authorize destructive deletion when the provider
returns materially fewer rows than are stored. TNXP and MSFT were re-applied and
verified with zero mismatches across 3,147 dates.

### Cloud source: unreachable

`viqdqgxcumcdhqxooplw.supabase.co` returns NXDOMAIN via both `Resolve-DnsName` and
`nslookup`. `supabase.com` and `api.supabase.com` resolve, so this is specific to that
project ref and not a general DNS outage. No Supabase CLI project-ref file exists in
the repository, and `backend/.env` points at `localhost:54321`. A current project ref is
required to continue recovery.

### Backup assessed: insufficient

`C:\Documents\db_cluster-31-08-2026@19-49-47.backup.gz` (10.54 MB) is a valid gzip
plain-SQL `pg_dump` containing 57 tables, but its `price_history` coverage is
month-end sampled:

| Company | id | Rows in dump | Range | Typical gap |
| --- | --- | --- | --- | --- |
| LEG | 899 | 569 | 1980-03-31 .. 2026-07-24 | 28-33 days |
| RMAX | 3162 | 123 | 2013-10-31 .. 2026-07-24 | 28-33 days |

The dump holds 40,327 `price_history` rows across 176 companies (maximum 788 for any
one company). Company IDs match the local database (LEG 899, RMAX 3162), so identity is
not the obstacle. The dump uses the legacy 9-column layout with neither
`adjustment_factor` nor `adj_close`, so any row selected from it would require canonical
re-derivation on import.

**This backup cannot restore the missing daily rows.** It is a valid partial
mitigation only, and must not be presented as equivalent to the original daily history.

### What is missing

1. A current Supabase project ref or URL for the live project, **or**
2. A genuine daily `price_history` backup for LEG and RMAX covering 2016-10-01 onward.

Until one is supplied, LEG and RMAX hold one row each locally. Do not import the
sampled rows as a substitute for daily history.

Reproduce the assessment with:

```bash
python backend/scripts/verify_dump_company_identity.py   # company_id + split identity
python backend/scripts/inspect_cloud_dump.py             # columns, ranges, row counts
python backend/scripts/inspect_dump_sampling.py          # day-of-month / gap distribution
```

---

*Document generated for StockerPro migration from Supabase Cloud to Local Supabase.*
