# Scheduler Architecture Design Document

**Document Version:** 1.0  
**Date:** 2026-06-03  
**Status:** Active (as-implemented documentation)  
**Author:** StockerPro Team  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Worker Process](#3-worker-process)
4. [Market Data Scheduler](#4-market-data-scheduler)
5. [Earnings Scheduler](#5-earnings-scheduler)
6. [Super Investors Scheduler](#6-super-investors-scheduler)
7. [Distributed Locking Mechanism](#7-distributed-locking-mechanism)
8. [Company Eligibility & Selection](#8-company-eligibility--selection)
9. [Bootstrap / First-Load Logic](#9-bootstrap--first-load-logic)
10. [Configuration Reference](#10-configuration-reference)
11. [Deployment & Operations](#11-deployment--operations)
12. [Log Analysis Guide](#12-log-analysis-guide)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Executive Summary

StockerPro uses three independent background schedulers to keep financial data fresh. Each runs as an async task inside a dedicated worker process (`scheduler_worker.py`), completely separate from the FastAPI HTTP server. All three share a common distributed locking mechanism via a Supabase `scheduler_locks` table, enabling safe multi-replica deployment without duplicate work.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Worker model | Separate asyncio process | Avoids Celery/Redis dependency; adequate for ~150 companies |
| Lock storage | Supabase table | No extra infra; works with existing DB |
| Concurrency | Per-scheduler semaphore | Prevents API rate-limit flooding |
| Incremental refresh | Watermark-based | First fetch full, then only new periods |
| Fail isolation | Per-company try/except | One bad company never blocks others |

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    scheduler_worker.py                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐      │
│  │                    Main Loop (heartbeat every 60s)      │      │
│  │                    Graceful shutdown on SIGTERM/SIGINT  │      │
│  └───────────────────────────┬────────────────────────────┘      │
│                              │                                    │
│         ┌────────────────────┼────────────────────┐              │
│         ▼                    ▼                    ▼              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐         │
│  │  Market Data │   │   Earnings  │   │SuperInvestors│         │
│  │  Scheduler  │   │  Scheduler  │   │  Scheduler  │         │
│  │  (24h loop) │   │  (2h loop)  │   │  (24h loop)  │         │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘         │
│         │                  │                  │                  │
│         │      ┌───────────┴───────────┐      │                  │
│         └──────┤   DefeatBetaProvider  ├──────┘                  │
│                │   (YFinance fallback) │                         │
│                └───────────┬───────────┘                         │
│                            │                                     │
│                     ┌──────┴──────┐                              │
│                     │  Supabase   │                              │
│                     │ (PostgreSQL)│                              │
│                     └──────┬──────┘                              │
│                            │                                     │
│              ┌─────────────┼─────────────┐                       │
│              ▼             ▼             ▼                       │
│        scheduler_locks  companies   income_statements            │
│        price_history    balance_sheets  cash_flow_statements     │
│        company_summary  financial_ratios  valuation_runs         │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Runs in |
|-----------|---------------|---------|
| `scheduler_worker.py` | Process lifecycle, starts/stops all schedulers | Worker process |
| `MarketDataRefreshScheduler` | Price history, splits, forecasts, IS/BS/CF bootstrap, derived metrics, valuations | Async task |
| `EarningsRefreshScheduler` | Refresh companies with upcoming earnings (±N days) | Async task |
| `SuperInvestorsRefreshScheduler` | Fetch 13F filings for tracked super investors | Async task |
| `SupabaseFinancialRepository` | All DB operations, including distributed locks | Shared library |
| `DefeatBetaProvider` | Primary data provider (Stockdex + Edgar + YFinance fallback) | Shared library |

### File Map

| File | Purpose |
|------|---------|
| `backend/scheduler_worker.py` | Worker entry point |
| `backend/application/schedulers/market_data_scheduler.py` | Market data refresh (543 lines) |
| `backend/application/schedulers/earnings_scheduler.py` | Earnings refresh (371 lines) |
| `backend/application/schedulers/super_investors_scheduler.py` | Super investors refresh |
| `backend/infrastructure/repositories/financial_repository.py` | Repository + lock methods |

---

## 3. Worker Process

### 3.1 Startup Sequence

```
scheduler_worker.py
│
├─ GracefulShutdown() → registers SIGTERM/SIGINT handlers
│
├─ if ENABLE_SUPER_INVESTORS_SCHEDULER (default: True):
│     → SuperInvestorsRefreshScheduler().start()
│
├─ if ENABLE_MARKET_DATA_SCHEDULER (default: True):
│     → MarketDataRefreshScheduler().start()
│
├─ if ENABLE_EARNINGS_SCHEDULER (default: False):
│     → EarningsRefreshScheduler().start()
│
└─ while not shutdown_requested:
      await asyncio.sleep(60)  # heartbeat
```

### 3.2 Graceful Shutdown

On `SIGTERM` or `SIGINT`:
1. Sets `shutdown_requested = True`
2. Worker's heartbeat loop exits
3. Calls `scheduler.stop()` on each scheduler → cancels the async task
4. In-progress company processing completes before shutdown

### 3.3 Log Output at Startup (from production)

```
[INFO] stockerpro.worker: Shutdown handlers registered (SIGTERM, SIGINT)
[INFO] stockerpro.worker: 🚀 StockerPro Background Worker Starting
[INFO] stockerpro.worker: Environment: development
[INFO] stockerpro.worker: Log Level: INFO
[INFO] stockerpro.worker: Supabase URL: https://xxx.supabase.co
[INFO] stockerpro.worker: ⏭️  Super Investors scheduler disabled (ENABLE_SUPER_INVESTORS_SCHEDULER=false)
[INFO] stockerpro.worker: Initializing Market Data scheduler...
[INFO] providers.defeat_beta_provider: DefeatBetaProvider initialized
[INFO] market_data_scheduler: 🚀 Market Data Scheduler started (interval: 24h)
[INFO] stockerpro.worker: ✅ Market Data scheduler started (interval: 24h)
[INFO] stockerpro.worker: Initializing Earnings scheduler...
[INFO] market_data_scheduler: 📊 Market data refresh cycle started
[INFO] stockerpro.worker: ✅ Earnings scheduler started (interval: 2h)
[INFO] stockerpro.worker: ✅ Worker process running with 2 active schedulers
```

Note: Each scheduler begins its first cycle immediately at startup (no initial delay).

---

## 4. Market Data Scheduler

### 4.1 Lifecycle

```
MarketDataRefreshScheduler.start()
  → _run_loop():
      while _is_running:
        _refresh_cycle()
        await asyncio.sleep(interval_hours * 3600)  # default: 24h
```

### 4.2 Cycle Flow (`_refresh_cycle`)

```
_refresh_cycle()
│
├─ 1. GET ACTIVE COMPANIES
│     → financial_repo.get_active_companies_for_market_data()
│     → Returns ~150 companies (those in ANY user's portfolio/watchlist)
│
├─ 2. CONCURRENT WORKERS
│     → Semaphore(max_concurrency=5)
│     → For each company: _worker(company)
│
└─ 3. PER-COMPANY WORKER
      │
      ├─ a. Acquire distributed lock
      │     → acquire_company_lock(company_id, lock_type="market_data_refresh")
      │     → If FAIL → skip ("🔒 Skip XYZ: lock held by another replica")
      │
      ├─ b. _process_company(symbol, company_id, security_type)
      │
      └─ c. Release lock
            → release_company_lock(company_id, owner_id)
```

### 4.3 Per-Company Processing (`_process_company`)

```
_process_company(symbol, company_id, security_type, exchange)
│
│  [Steps 1-2: ALL security types (stocks + ETFs/indices/funds)]
│
├─ Step 1: PRICE HISTORY
│     _has_any_price_history(company_id)?
│       ├─ NO  → BOOTSTRAP: fetch FULL daily history from DefeatBeta
│       │         → filter by retention window (default: 10 years)
│       │         → compress daily OHLCV to monthly EOM
│       │         → upsert to price_history
│       │
│       └─ YES → INCREMENTAL: fetch last lookback_days (default: 45)
│                 → filter by max(retention_cutoff, window_cutoff)
│                 → compress to monthly EOM
│                 → upsert to price_history
│
├─ Step 2: STOCK SPLITS
│     → get_splits_optimized(symbol, company_id)
│     → upsert_splits()
│
│  [Steps 3-8: STOCKS ONLY (security_type == "stock")]
│
├─ Step 3: REVENUE FORECAST
│     → fetch_revenue_forecast(symbol, company_id)
│     → upsert_revenue_forecast()
│
├─ Step 4: EARNINGS FORECAST
│     → fetch_earnings_forecast(symbol, company_id)
│     → upsert_earnings_forecast()
│
├─ Step 5: COMPANY SUMMARY
│     → get_company_summary_optimized(symbol, company_id)
│     → upsert_company_summary()
│     ⚠ This is where trailing_eps comes from (critical for valuations)
│
│  ════════════════════════════════════════════════════════
│  ★ Step 5c: IS/BS/CF BOOTSTRAP (FINANCIAL DATA FETCH) ★
│  ════════════════════════════════════════════════════════
│     _has_any_financials(company_id)?
│       → SELECT * FROM income_statements
│         WHERE company_id=? AND fiscal_quarter IS NULL LIMIT 1
│       │
│       ├─ NO ROWS → TRIGGER FULL FINANCIAL SYNC:
│       │   get_all_financials_optimized(
│       │     symbol=symbol,
│       │     company_id=company_id,
│       │     last_refreshed_fiscal_year=None,
│       │     last_refreshed_fiscal_quarter=None,
│       │     force_full_history=True,
│       │     min_fiscal_year=2021,
│       │   )
│       │   → if financials.income_statements.rows:
│       │       upsert_all_financials(financials)
│       │       update_company_refresh_metadata(is_first_load=True)
│       │       log: "[BOOTSTRAP] XYZ IS/BS/CF bootstrap complete"
│       │   → else:
│       │       log warning: "min_fiscal_year=2021 stripped all rows"
│       │
│       └─ ROWS EXIST → skip (data already present)
│
├─ Step 6: DERIVED FINANCIAL RATIOS
│     → compute_and_upsert_derived_financial_metrics(company_id)
│     → Version-gated: only writes rows whose source data changed
│
├─ Step 7: DIVIDEND METRICS
│     → compute_and_upsert_dividend_metrics(company_id)
│     → Exits early if no dividend_history rows
│
└─ Step 8: RI VALUATION
      → compute_residual_income_if_stale(symbol, force=True)
      → Triggers: Residual Income model computation + AI summary
```

### 4.4 Price History Behavior

| Scenario | Detection | Action |
|----------|-----------|--------|
| First time (no rows) | `_has_any_price_history()` → False | Bootstrap: fetch all daily history, compress to monthly EOM |
| Incremental (has rows) | `_has_any_price_history()` → True | Fetch last 45 days, recompute EOM for window |
| Retention pruning | Disabled by default | Optional: delete rows older than `retention_years` |

### 4.5 IS/BS/CF Bootstrap (the critical path)

This is the mechanism that fetches **income statements, balance sheets, and cash flow statements** for companies that have never been synced. It addresses the gap between what the Market Data Scheduler handles (price, splits, forecasts) and what the Earnings Scheduler handles (financials for companies near earnings dates).

**Why it exists:**
- The Earnings Scheduler only processes companies within ±N days of their earnings date
- A newly added company outside that window would have empty IS/BS/CF tables
- Derived metrics (ROIC, ROE, etc.) silently degrade to 0/100 when source tables are empty

**The check:**
```sql
SELECT fiscal_year FROM income_statements
WHERE company_id = :company_id
  AND fiscal_quarter IS NULL  -- annual statements only
LIMIT 1
```
If this returns 0 rows → trigger full DefeatBeta fetch with `force_full_history=True, min_fiscal_year=2021`.

---

## 5. Earnings Scheduler

### 5.1 Lifecycle

```
EarningsRefreshScheduler.start()
  → _run_scheduler_loop():
      while is_running:
        _check_and_refresh_earnings()
        await asyncio.sleep(interval_hours * 3600)  # default: 2h
```

### 5.2 Check & Refresh Flow

```
_check_and_refresh_earnings()
│
├─ 1. DETERMINE EARNINGS WINDOW
│     today = date.today()
│     start_date = today - buffer_days
│     end_date   = today + buffer_days
│     (default buffer: ±10 days → 21-day window)
│
├─ 2. QUERY COMPANIES IN WINDOW
│     → financial_repo.get_companies_with_upcoming_earnings(
│          start_date, end_date)
│     → WHERE next_earnings_date BETWEEN start_date AND end_date
│       AND data_completeness_status IN (INITIAL,PARTIAL,COMPLETE,CURRENT)
│       AND (security_type = 'stock' OR security_type IS NULL)
│
├─ 3. PER-COMPANY PROCESSING
│     For each company:
│       a. Acquire lock (lock_type="earnings_refresh")
│       b. _refresh_company_financials_optimized()
│       c. Release lock
│
└─ 4. LOG SUMMARY
      companies_found, companies_refreshed, companies_failed
```

### 5.3 Single Company Refresh

```
_refresh_company_financials_optimized(company_id, symbol, earnings_date)
│
├─ 1. GET REFRESH INFO
│     → refresh_info = get_company_refresh_info(company_id)
│     → is_first_time_load = (first_financial_data_loaded_at IS NULL)
│
├─ 2. FETCH FROM DEFEATBETA
│     → get_all_financials_optimized(
│         force_full_history=is_first_time_load,
│         last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
│         last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
│       )
│     → force_full_history=True on first load → fetches all years
│     → force_full_history=False on subsequent loads → fetches only NEW
│       fiscal years/quarters (watermark-based filtering)
│
├─ 3. UPSERT TO DATABASE
│     → upsert_all_financials(financials)
│
├─ 4. UPDATE METADATA
│     → update_company_refresh_metadata(
│         is_first_load=is_first_time_load,
│         next_earnings_date=...)
│
├─ 5. IF NEW ROWS WRITTEN:
│     a. Compute derived financial metrics
│     b. Audit data quality
│     c. Trigger RI valuation
│
└─ 6. RETURN RESULTS
```

### 5.4 Key Difference from Market Data Scheduler

| Aspect | Market Data Scheduler | Earnings Scheduler |
|--------|----------------------|-------------------|
| Trigger | All active companies (~150) | Only companies with earnings in ±10 day window |
| Interval | 24 hours | 2 hours |
| Data fetched | Price history, splits, forecasts, company summary, IS/BS/CF bootstrap, ratios, dividends, valuation | Full financials (IS/BS/CF), derived metrics, valuation |
| Bootstrap IS/BS/CF | Step 5c (escalation path) | Primary purpose |

---

## 6. Super Investors Scheduler

(Architecture summary; detailed docs in `docs/SCHEDULER_CHANGES_TODO.md` and `docs/BACKGROUND_SCHEDULER_DESIGN.md`)

### 6.1 Purpose

Fetches institutional 13F holdings for tracked super investors (Warren Buffett, Bill Ackman, etc.) from SEC EDGAR.

### 6.2 Flow

- Runs every `interval_hours` (default: 24)
- Queries `institutional_investors` table for tracked investors
- For each investor, checks if a new quarter filing is due
- Fetches missing quarters from SEC EDGAR
- Saves to `institutional_holdings` via upsert

### 6.3 Current Status

In production as of this writing: **DISABLED** (`ENABLE_SUPER_INVESTORS_SCHEDULER=false`)

---

## 7. Distributed Locking Mechanism

### 7.1 Database Schema

The `scheduler_locks` table in Supabase:

```sql
scheduler_locks (
  lock_id      VARCHAR    PRIMARY KEY,   -- owner identifier (e.g., "market_data:uuid")
  company_id   INT        UNIQUE,         -- one lock per company
  acquired_at  TIMESTAMPTZ,               -- when lock was taken
  expires_at   TIMESTAMPTZ,               -- when lock auto-releases
  lock_type    VARCHAR                     -- "market_data_refresh" | "earnings_refresh"
)
```

### 7.2 Lock Acquisition (`acquire_company_lock`)

```
acquire_company_lock(company_id, owner_id, ttl_seconds, lock_type):
│
├─ 1. TRY TAKE-OVER (expired locks)
│     → UPDATE scheduler_locks
│       SET lock_id=owner_id, acquired_at=NOW(), expires_at=NOW()+ttl
│       WHERE company_id=? AND expires_at <= NOW()
│     → If rows updated → acquired (returns True)
│
├─ 2. TRY INSERT (new lock)
│     → INSERT INTO scheduler_locks (...) VALUES (...)
│     → UNIQUE constraint on company_id prevents duplicates
│     → If success → acquired (returns True)
│
└─ 3. INSERT FAILED (another owner holds active lock)
      → Returns False
      → Scheduler logs: "🔒 Skip XYZ: lock held by another replica"
```

### 7.3 Lock Refresh (`refresh_company_lock`)

Extends the lock expiration without releasing it. Used by long-running operations to prevent the lock from expiring mid-work.

```
refresh_company_lock(company_id, owner_id, ttl_seconds):
  → UPDATE scheduler_locks SET expires_at=NOW()+ttl
    WHERE company_id=? AND lock_id=owner_id
  → Returns True if the lock was refreshed
```

### 7.4 Lock Release (`release_company_lock`)

```
release_company_lock(company_id, owner_id):
  → DELETE FROM scheduler_locks
    WHERE company_id=? AND lock_id=owner_id
```

### 7.5 Lock States

| Scenario | HTTP Request | Result |
|----------|-------------|--------|
| No lock exists | `PATCH (no match) → INSERT` | 200 (no rows) → 201 Created |
| Expired lock exists | `PATCH (match) → INSERT (no-op)` | 200 (1 row) → 409 Conflict (ignored) |
| Active lock exists (same owner) | `PATCH (match) → INSERT (no-op)` | 200 (1 row) → 409 Conflict (ignored) — but log is wrong: "held by another replica" |
| Active lock exists (different owner) | `PATCH (no match expired) → INSERT (unique violation)` | 200 (no rows) → 409 Conflict → returns False |

**Edge case:** The `.lte("expires_at", now)` filter uses PATCH which doesn't error on no-match. If the lock is held by the **same** owner (e.g., the scheduler restarted), the PATCH succeeds (overwrites), the INSERT gets 409 (ignored), and `True` is returned — which is correct behavior.

### 7.6 Lock TTL Values

| Scheduler | Lock Type | TTL | Config Key |
|-----------|-----------|-----|------------|
| Market Data | `market_data_refresh` | 1800s (30 min) | `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` |
| Earnings | `earnings_refresh` | 2700s (45 min) | `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` |

### 7.7 Why DB Locks Instead of Redis

- **No extra infrastructure** — works with existing Supabase/PostgreSQL
- **Pessimistic locking** — only one worker can process a company at a time
- **Auto-expiry** — if a worker crashes, the lock expires and another worker picks it up
- **Visibility** — locks are visible in the DB for debugging

---

## 8. Company Eligibility & Selection

### 8.1 Market Data Scheduler: `get_active_companies_for_market_data()`

```sql
-- Step 1: Get symbols from ALL users' portfolio_holdings
SELECT DISTINCT symbol FROM portfolio_holdings

-- Step 2: Lookup company_ids
SELECT company_id FROM companies
WHERE ticker_symbol IN (symbols_from_step_1)

-- Step 3: Get company_ids from ALL users' watchlist_items
SELECT company_id FROM watchlist_items

-- Step 4: Union + deduplicate → fetch full company rows
SELECT company_id, ticker_symbol, data_completeness_status, security_type
FROM companies
WHERE company_id IN (active_ids_from_steps_1_to_3)
```

**Key properties:**
- No `data_completeness_status` filter — ALL statuses processed
- No `security_type` filter — all types returned (ETFs/indexes only get steps 1-2)
- Union of portfolios + watchlists across **all users**
- Typically returns ~150 companies (vs 3,114 total)

### 8.2 Earnings Scheduler: `get_companies_with_upcoming_earnings()`

```sql
SELECT company_id, ticker_symbol, next_earnings_date,
       last_refreshed_fiscal_year, last_refreshed_fiscal_quarter,
       data_completeness_status, first_financial_data_loaded_at
FROM companies
WHERE next_earnings_date BETWEEN :start_date AND :end_date
  AND data_completeness_status IN ('INITIAL', 'PARTIAL', 'COMPLETE', 'CURRENT')
  AND (security_type = 'stock' OR security_type IS NULL)
```

### 8.3 Comparison

| Scheduler | Scope | Typical Size | Frequency |
|-----------|-------|-------------|-----------|
| Market Data | Any company in portfolio/watchlist | ~150 | 24h |
| Earnings | Companies with earnings in ±10 day window | 0-20 | 2h |
| Super Investors | Tracked institutional investors | ~24 investors | 24h |

---

## 9. Bootstrap / First-Load Logic

### 9.1 Market Data Scheduler Bootstrap (Step 5c)

The Market Data Scheduler has an escalation path for companies that have NO financial data:

```
_has_any_financials(company_id):
  → SELECT fiscal_year FROM income_statements
    WHERE company_id=? AND fiscal_quarter IS NULL
    LIMIT 1
  → Returns True if ANY annual income statement row exists

If False → TRIGGER FULL SYNC:
  get_all_financials_optimized(
    force_full_history=True,
    min_fiscal_year=2021,
    last_refreshed_fiscal_year=None,
    last_refreshed_fiscal_quarter=None,
  )
  → If data returned: upsert + update metadata + log "[BOOTSTRAP] complete"
  → If no data returned: log warning + skip (stripped by min_fiscal_year)
```

### 9.2 Earnings Scheduler First Load

The Earnings Scheduler detects first load via `first_financial_data_loaded_at`:
- If `NULL` → `force_full_history=True` (fetches all available years)
- If set → `force_full_history=False` (fetches only since last watermark)

### 9.3 Watermark Fields

Stored in `companies` table:

| Field | Purpose |
|-------|---------|
| `last_refreshed_fiscal_year` | Highest fiscal year successfully fetched |
| `last_refreshed_fiscal_quarter` | Highest fiscal quarter (NULL if annual-only) |
| `first_financial_data_loaded_at` | Timestamp of first successful load |
| `data_completeness_status` | INITIAL → PARTIAL → COMPLETE → CURRENT |
| `last_financial_refresh_at` | Timestamp of last refresh attempt |

---

## 10. Configuration Reference

### 10.1 Environment Variables

| Variable | Default | Scheduler | Purpose |
|----------|---------|-----------|---------|
| `ENABLE_SUPER_INVESTORS_SCHEDULER` | `True` | Super Investors | Enable/disable |
| `ENABLE_MARKET_DATA_SCHEDULER` | `True` | Market Data | Enable/disable |
| `ENABLE_EARNINGS_SCHEDULER` | `False` | Earnings | Enable/disable |
| `MARKET_DATA_REFRESH_INTERVAL_HOURS` | `24` | Market Data | Cycle interval |
| `MARKET_DATA_PRICE_LOOKBACK_DAYS` | `45` | Market Data | Price history window |
| `MARKET_DATA_MAX_CONCURRENCY` | `5` | Market Data | Parallel workers |
| `MARKET_DATA_COMPANY_STATUSES` | All 4 statuses | Market Data | Company filter (inactive: all are included) |
| `PRICE_HISTORY_RETENTION_YEARS` | `10` | Market Data | Retention window |
| `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` | `1800` (30m) | All | Lock TTL |
| `EARNINGS_REFRESH_CHECK_INTERVAL_HOURS` | `2` | Earnings | Cycle interval |
| `EARNINGS_REFRESH_BUFFER_DAYS` | `10` | Earnings | ±N day earnings window |

### 10.2 Internal Constants (code-defined)

| Constant | Value | Location |
|----------|-------|----------|
| `min_fiscal_year` (bootstrap) | `2021` | `market_data_scheduler.py:325` |
| `lookback_days` (min) | `40` | `market_data_scheduler.py:442` |
| Heartbeat interval | `60s` | `scheduler_worker.py:158` |

---

## 11. Deployment & Operations

### 11.1 Running the Worker

```bash
# Development
cd backend
python scheduler_worker.py

# Production (systemd)
systemctl start stockerpro-worker

# Docker
docker-compose up -d worker
```

### 11.2 Log Files

| Log | Location | Format |
|-----|----------|--------|
| Worker stdout | Console / systemd journal | `asctime [LEVEL] name: message` |
| Market Data cycle | Console | `market_data_scheduler: 📊 ...` |
| Earnings cycle | Console | `earnings_scheduler: 📊 ...` |
| Backfill history | `backend/logs/backfill_holdings.log` | `asctime [LEVEL] backfill_holdings: ...` |

### 11.3 Manual Triggers

```python
# Via API (if endpoints enabled)
POST /scheduler/market-data/trigger

# Via code (from Python shell)
import asyncio
from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
scheduler = MarketDataRefreshScheduler()
asyncio.run(scheduler.trigger_immediate_run())
```

### 11.4 Multi-Replica Safety

Two aspects ensure safe multi-replica deployment:

1. **Distributed locks** (`scheduler_locks` table):
   - Only one replica can process a given company at a time
   - Locks auto-release after TTL (30-45 min)
   - Crash recovery: expired locks are taken over by next cycle

2. **Idempotent upserts**:
   - All DB writes use `ON CONFLICT` upsert
   - Price history: `ON CONFLICT (company_id, price_date) DO UPDATE`
   - Financial statements: `ON CONFLICT (company_id, fiscal_year, fiscal_quarter)`
   - Running twice produces identical results

---

## 12. Log Analysis Guide

### 12.1 Startup Sequence

```
[INFO] stockerpro.worker: 🚀 StockerPro Background Worker Starting
[INFO] stockerpro.worker: Environment: development
[INFO] stockerpro.worker: ⏭️  Super Investors scheduler disabled (ENABLE_SUPER_INVESTORS_SCHEDULER=false)
[INFO] stockerpro.worker: Initializing Market Data scheduler...
[INFO] market_data_scheduler: 🚀 Market Data Scheduler started (interval: 24h)
[INFO] stockerpro.worker: ✅ Market Data scheduler started (interval: 24h)
[INFO] stockerpro.worker: Initializing Earnings scheduler...
[INFO] earnings_scheduler: 🚀 Earnings Scheduler started (interval: 2h)
[INFO] stockerpro.worker: ✅ Worker process running with 2 active schedulers
```

Note: The first Market Data cycle begins **immediately** after initialization (no 24h wait).

### 12.2 Market Data Cycle Start

```
[INFO] market_data_scheduler: 📊 Market data refresh cycle started
```

### 12.3 Company Discovery

```
[INFO] httpx: GET .../portfolio_holdings?select=symbol "200 OK"
[INFO] httpx: GET .../companies?select=company_id&ticker_symbol=in.(VZ,INTC,ADM,...) "200 OK"
[INFO] httpx: GET .../watchlist_items?select=company_id "200 OK"
[INFO] httpx: GET .../companies?select=company_id,...&company_id=in.(1027,571,...) "200 OK"
[INFO] market_data_scheduler: Found 158 companies for market-data refresh
```

Key logs:
- `portfolio_holdings?select=symbol` — identifies companies in portfolios
- `watchlist_items?select=company_id` — identifies companies in watchlists
- `Found N companies` — total active companies to process

### 12.4 Lock Acquisition

**Success (new lock):**
```
[INFO] httpx: PATCH .../scheduler_locks?company_id=eq.31&expires_at=lte... "200 OK"  ← no expired lock
[INFO] httpx: POST .../scheduler_locks "201 Created"  ← inserted new lock
```
Company with ID 31 (RBLX) acquires the lock and starts processing.

**Failure (held by another):**
```
[INFO] httpx: PATCH .../scheduler_locks?company_id=eq.32&expires_at=lte... "200 OK"  ← no expired lock
[INFO] httpx: POST .../scheduler_locks "409 Conflict"  ← UNIQUE constraint violation
[INFO] market_data_scheduler: 🔒 Skip SIRI (company_id=32): lock held by another replica
```

### 12.5 Price History Processing

```
# Bootstrap (no existing rows):
[INFO] httpx: GET .../price_history?select=price_date&company_id=eq.31&limit=1 "200 OK"  ← empty
[INFO] DuckDBClient: Cache is up-to-date. Update time: ...  ← DefeatBeta fetch
[INFO] ...: [PH][RBLX] Bootstrap monthly rows: 42

# Incremental (existing rows):
[INFO] httpx: GET .../price_history?select=open_price,...&company_id=eq.31&price_date=eq.2026-04-30 "200 OK"
[INFO] httpx: GET .../price_history?select=...&price_date=eq.2026-05-29 "200 OK"
[INFO] httpx: GET .../price_history?select=...&price_date=eq.2026-06-02 "200 OK"
[INFO] httpx: POST .../price_history?on_conflict=company_id,price_date "200 OK"
```

### 12.6 IS/BS/CF Bootstrap

```
# Check if financials exist:
[INFO] httpx: GET .../income_statements?select=fiscal_year&company_id=eq.31&fiscal_quarter=is.null&limit=1 "200 OK"

# If rows exist (has data → skip):
#   → No log message for skip case

# If NO rows exist (needs bootstrap):
[INFO] market_data_scheduler: [BOOTSTRAP] XYZ (company_id=N) has no IS/BS/CF rows — triggering full financial sync
[INFO] ...: [BOOTSTRAP] XYZ IS/BS/CF bootstrap complete — IS:7 BS:7 CF:7
```

### 12.7 Derived Metrics

```
[INFO] ...: [RATIOS] RBLX: 0/7 rows written  ← version-gated, no changes
```

### 12.8 Valuation

```
[INFO] ...: [VALUATION] RBLX RI valuation complete
```

### 12.9 Cycle Completion

```
[INFO] ...: DELETE .../scheduler_locks?company_id=eq.31&lock_id=eq.market_data:0f09... "200 OK"
[INFO] ...: ✅ Market data cycle complete: 1 ok, 0 failed
```

### 12.10 Earnings Scheduler

```
[INFO] earnings_scheduler: 📊 Starting earnings check cycle
[INFO] httpx: GET .../companies?select=...&next_earnings_date=gte.2026-05-24&next_earnings_date=lte.2026-06-13 "200 OK"
[INFO] financial_repository: Found 0 companies with earnings between 2026-05-24 and 2026-06-13
[INFO] earnings_scheduler: ✅ No companies with upcoming earnings to refresh
```

---

## 13. Troubleshooting

### 13.1 Company Not Getting Processed

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Company not in portfolio/watchlist of any user | Not eligible | Add to portfolio/watchlist |
| All replicas skipping | Lock held by another replica | Wait for lock expiry (30-45 min) or manually delete from `scheduler_locks` |
| Company skipped every cycle | Lock held by crashed worker | Locks auto-expire after TTL; or manually delete |
| No IS/BS/CF data | Bootstrap hasn't run yet | Check next cycle; or manually trigger `POST /stocks/{symbol}/refresh-financials` |

### 13.2 Lock Issues

```sql
-- View all active locks
SELECT * FROM scheduler_locks;

-- Force-release a lock for a specific company
DELETE FROM scheduler_locks WHERE company_id = <company_id>;

-- Force-release all locks held by a specific worker
DELETE FROM scheduler_locks WHERE lock_id LIKE 'market_data:%';
```

### 13.3 Checking Company Status

```sql
-- Check if a company has financial data
SELECT company_id, ticker_symbol, data_completeness_status,
       last_refreshed_fiscal_year, first_financial_data_loaded_at
FROM companies
WHERE ticker_symbol = 'ADM';

-- Check income statements exist
SELECT COUNT(*) FROM income_statements WHERE company_id = 571;

-- Check price history exists
SELECT COUNT(*) FROM price_history WHERE company_id = 571;
```

### 13.4 Forcing a Refresh

```bash
# Option 1: On-demand via API
curl -X POST /api/stocks/ADM/refresh-financials

# Option 2: Reset company status and wait for scheduler
UPDATE companies
SET data_completeness_status = 'INITIAL',
    last_refreshed_fiscal_year = NULL,
    last_refreshed_fiscal_quarter = NULL,
    last_financial_refresh_at = NULL,
    first_financial_data_loaded_at = NULL
WHERE ticker_symbol = 'ADM';

# Option 3: Run the backfill script for a single company
cd backend && python scripts/phase7_backfill.py --company-id 571
```

### 13.5 Key Log Patterns

| Log Pattern | Meaning |
|-------------|---------|
| `🔒 Skip XYZ: lock held by another replica` | Another worker is processing this company |
| `[BOOTSTRAP] XYZ has no IS/BS/CF rows` | Company needs financial data fetch |
| `[BOOTSTRAP] XYZ IS/BS/CF bootstrap complete` | Financial data successfully fetched |
| `Found N companies for market-data refresh` | Number of active companies in this cycle |
| `min_fiscal_year=2021 stripped all rows` | DefeatBeta returned data older than 2021 |
| `✅ No companies with upcoming earnings` | Earnings window has 0 matching companies |

---

## Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-03 | Initial design document (as-implemented) | StockerPro Team |
