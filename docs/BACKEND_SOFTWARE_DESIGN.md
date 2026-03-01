# Backend Software Design Document

This document provides a detailed overview of the backend software design for the application, intended to help new developers quickly understand the codebase, architecture, and key components.

## 1. High-Level Architecture

The backend follows a layered architecture pattern, promoting separation of concerns and modularity. This makes the system easier to maintain, test, and scale. The layers are:

- **API Layer (Presentation):** Handles incoming HTTP requests, performs data validation, and calls the appropriate services. It's built with FastAPI.
- **Application Layer (Service):** Contains the core business logic. It orchestrates calls to the domain and infrastructure layers to fulfill use cases. This layer includes both services and schedulers.
- **Domain Layer:** Represents the core business concepts, entities, and rules of the application. It is independent of any specific framework or technology.
- **Infrastructure Layer:** Implements interfaces defined in the domain layer, handling external concerns like database interactions and communication with third-party services.

API Layer (FastAPI)
      ↓
Application Layer (Services + Schedulers)
      ↓
Domain Layer (Entities + Pydantic Models)
      ↓
Infrastructure Layer (Repositories + Providers)
      ↓
External Systems (Supabase, DefeatBeta, YFinance)

### Key Architectural Enhancements
| Feature | Description |
| Dual Schedulers | Market Data Scheduler + Earnings Scheduler run independently and concurrently.|
| Distributed Locking | Per-company locks using Supabase scheduler_locks table prevent double-processing in multi‑replica deployments.|
| Smart Financial Refresh| Earnings scheduler fetches only incremental financial data (97.5% dedupe).|
| DBeta → YF Fallback | All DefeatBeta providers have an internal YFinance fallback. |
| Conflict Detection Logging | Ingestion automatically logs data inconsistencies into data_conflicts.
| Monthly Price Compression | Daily OHLCV compressed into monthly EOM candles to reduce DB load. |
| Two-Phase Add‑Stock Workflow | Instant UI response + background data ingestion.|
| Real-Time SSE | Live price updates for all watchlist symbols. |


## 2. Folder Structure and File Descriptions

Here’s a breakdown of the key files and their responsibilities within the `backend/` directory:
'''
backend
├── api
│   ├── __pycache__
│   ├── users.py
│   ├── valuations.py
│   ├── watchlist_items.py
│   └── watchlists.py
├── application
│   ├── __init__.py
│   ├── jobs
│   │   ├── data_quality_audit_job.py
│   │   ├── derived_financial_metrics_job.py
│   │   └── __pycache__
│   ├── normalizers
│   │   ├── __pycache__
│   │   └── statement_normalizer.py
│   ├── __pycache__
│   ├── schedulers
│   │   ├── earnings_scheduler.py
│   │   ├── __init__.py
│   │   ├── market_data_scheduler.py
│   │   └── __pycache__
│   └── services
│       ├── dcf_service.py
│       ├── dcf_suitability.py
│       ├── ddm_service.py
│       ├── ddm_suitability.py
│       ├── __init__.py
│       ├── __pycache__
│       ├── recompute_guard.py
│       ├── rule1_suitability.py
│       ├── valuation_service.py
│       └── watchlist_service.py
├── auth.py
├── config.py
├── database.py
├── dependencies.py
├── domain
│   ├── entities
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   └── watchlist.py
│   ├── exceptions.py
│   ├── __init__.py
│   ├── interfaces
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── repository.py
│   │   └── stock_provider.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── valuation_dcf.py
│   │   ├── valuation_ddm.py
│   │   └── valuation_rule1.py
│   ├── model_types.py
│   └── __pycache__
├── google_credentials.json
├── infrastructure
│   ├── __init__.py
│   ├── __pycache__
│   └── repositories
│       ├── financial_repository.py
│       ├── __init__.py
│       ├── __pycache__
│       ├── supabase_repository.py
│       └── valuation_repository.py
├── logs
│   ├── backend.log
│   ├── (and other log files...)
├── main.py
├── providers
│   ├── base.py
│   ├── defeat_beta_provider.py
│   ├── __init__.py
│   ├── __pycache__
│   └── yfinance_provider.py
├── __pycache__
├── requirements.txt
├── schemas.py
├── service-account.json
├── services
│   ├── __pycache__
│   └── sync_service.py
├── shared
│   ├── constants.py
│   ├── exceptions
│   │   ├── base.py
│   │   ├── __init__.py
│   │   └── __pycache__
│   ├── __init__.py
│   └── __pycache__
├── start-prod.sh
├── start.sh
├── status.sh
└── stop.sh




```

### 2.1. `main.py`

- **Purpose:** The main entry point of the FastAPI application.
- **Key Responsibilities:**
    - Initializes the FastAPI app.
    - Configures CORS middleware, rate limiting, and exception handlers.
    - Includes the API routers (`users`, `watchlists`, `watchlist_items`).
    - Defines system-level endpoints like `/health`.
    - Manages the application's startup and shutdown events, including initializing Firebase and starting background tasks.
    New responsibilities:
    - Starts three background tasks:
        Earnings Scheduler
        Market Data Scheduler
        Real-time Price Monitor (SSE)
    - Ensures clean shutdown of:
        background tasks
        long-lived async loops
        scheduler locks
    - Exposes admin endpoints:
        GET /scheduler/status
        POST /scheduler/earnings/trigger
        POST /scheduler/market-data/trigger
    - Supports dynamic enable/disable flags:
        ENABLE_EARNINGS_SCHEDULER
        ENABLE_MARKET_DATA_SCHEDULER

### 2.2. API Layer (`api/`)

- **`users.py`:** Manages user-related endpoints. `POST /users/sync` synchronizes user data from Firebase Auth to the Supabase database.
- **`watchlists.py`:** Handles watchlist-specific endpoints. `POST /watchlists/default-with-items` retrieves the default watchlist for a user. `GET /watchlists/stream` establishes a Server-Sent Events (SSE) connection for real-time updates.
- **`watchlist_items.py`:** Manages the items within a watchlist. `POST /watchlist-items` adds a new stock. `PATCH /watchlist-items/{item_id}` updates target prices. `POST /watchlist-items/delete` removes a stock. `POST /stocks/{symbol}/refresh-financials` triggers an on-demand refresh of financial data.
**Important flows:**
/watchlist-items
Triggers:
1. Fast path
  - Get real-time price via YFinanceProvider
  - Insert into current_market_data
  - Upsert company
  - Add watchlist item
    → Returns instantly
2. Slow path (background)
  - Kick off async task (non-blocking)
  - Fetch:
      full historical daily OHLCV
      splits
      revenue forecast
      earnings forecast
      company summary
  - Compress OHLCV → monthly EOM
  - Upsert everything
  - Update company metadata

### 2.3. Application Layer (`application/`)

- **`services/watchlist_service.py`:** Contains the core business logic for watchlist operations, orchestrating the process of adding stocks, fetching data, and triggering background updates.
Enhancements:
- Two-phase add‑stock ingestion
- Uses DefeatBetaProvider with YF fallback
- Immediately updates real-time price tables
- Spawns background ingestion task
- Now interacts with market-data ingestion pipeline
- **`schedulers/earnings_scheduler.py`:** A background scheduler that periodically refreshes financial data for companies with upcoming earnings announcements.
EarningsRefreshScheduler
- Runs every N hours (default 2)
- Uses smart refresh to fetch only new financial rows
- Adds per-company distributed locks
- Uses DBeta → YF fallback for reliability
- Upserts via unified financial_repository

Cycle:
  find companies w/ earnings in ± buffer window
    ↓
  acquire per-company lock
    ↓
  fetch incremental financial data
    ↓
  upsert all statements
    ↓
  update metadata
    ↓
  release lock

MarketDataRefreshScheduler (New)
Runs every N hours (default 24 hours):
Cycle:
  list all active companies
      ↓
  acquire per-company lock
      ↓
  fetch daily OHLCV (DBeta → YF fallback)
      ↓
  compress to monthly EOM
      ↓
  upsert into price_history
      ↓
  upsert splits / forecasts / summary
      ↓
  release lock

Key enhancements:
✔ Per-company distributed locks
✔ YF fallback injection
✔ Automatic conflict detection logging
✔ Efficient EOM compression (no duplicates)
✔ Concurrency-limited processing

### 2.4. Domain Layer (`domain/`)

- **`entities/` and `models/`:** Define the Pydantic models for the application, such as `WatchlistWithStocks`, `StockPriceInfo`, and financial data models like `IncomeStatementRow`.
- **`interfaces/`:** Defines the abstract base classes for repositories (`WatchlistRepository`, `UserRepository`) and service providers (`StockProvider`).

### 2.5. Infrastructure Layer (`infrastructure/`)
#### 2.5.1 Providers
- **`repositories/supabase_repository.py`:** Implements the `WatchlistRepository` and `UserRepository` interfaces using Supabase.
- **`repositories/financial_repository.py`:** A dedicated repository for all financial data operations with Supabase, including `upsert` operations for financial statements.
- **`providers/yfinance_provider.py`:** Implements the `StockProvider` interface using the `yfinance` library, primarily for real-time market data.
Used for:
- Real-time price
- Fallback for:
    price history
    splits
    company summary
- **`providers/defeat_beta_provider.py`:** The primary provider for historical financial data, with a fallback to `yfinance`.
UPDATED WITH:
- Fully wired YF fallback
- Smart filtering for incremental financial fetches
- Robust timeout + retry logic
- Data source tagging (defeatbeta / yfinance)
- Detailed debug logging

#### 2.5.2 Repositories
**financial_repository.py (Major changes)**
New features:
✔ Per-company distributed locks
Uses Supabase table: scheduler_locks(lock_id, company_id, expires_at)

Prevents multi-replica duplicates.
✔ Conflict detection logging
Auto-logs inconsistencies into: data_conflicts

e.g.
- DBeta vs YF price mismatch
- Monthly OHLC compression conflicts
- Forecast disagreement
- Summary metric deltas

✔ Upserts for all new market-data tables:
- price_history (monthly)
- splits
- revenue_forecast
- earnings_forecast
- company_summary

✔ Row-level conflict scanning (before upsert)

## 3. Class Diagrams (Text-Based)

### 3.1. Watchlist Service and Dependencies

```
[FastAPI Router] -> [WatchlistService]
      |                   |
      |                   v
      |            [FinancialRepository]
      |
      |                   v
      |            [DefeatBetaProvider]
      |                   |
      |                   v
      |            [YFinanceProvider]
      |
      |                   v
      +----------> [UserRepository]
      |
      +----------> [WatchlistRepository]
```

### 3.2. Data Flow for Adding a Stock

```
Client → POST /watchlist-items
     |
     v
 FAST PATH (sync)
   YFinanceProvider → real-time price
   Supabase → upsert company
   Supabase → add watchlist item
     |
     +——————→ return response to client
     |
     v
 SLOW PATH (async task)
   DefeatBetaProvider (w/ fallback YF)
       |
       +— price history (daily)
       +— splits
       +— forecasts (rev/eps)
       +— summary snapshot
       |
   FinancialRepository
       |- compress to monthly EOM
       |- conflict detection
       |- upsert rows
       |- update company metadata
```

### 3.3 Updated Scheduler Architecture
Scheduler Loop (Earnings / Market Data)
      |
      v
Get Companies → For each:
      |
      v
acquire_company_lock(company_id)
      |
      v
fetch data (DBeta → YF)
      |
      v
financial_repository.upsert_*
      |
      v
financial_repository.update_company_refresh_metadata
      |
      v
release_company_lock(company_id)

## 4. Key Concepts and Logic

- **Authentication:** Handled via Firebase Authentication. A JWT is verified by a FastAPI dependency.
- **Real-time Updates:** Server-Sent Events (SSE) push real-time stock prices to clients.
- **Database:** Supabase (PostgreSQL) is the primary database.
- **Asynchronous Operations:** The application makes extensive use of `asyncio` for non-blocking I/O, especially for database operations and background tasks. The `add_stock_to_watchlist` flow is a prime example of a responsive, two-phase, asynchronous operation.
- **Scheduled Tasks:** The `EarningsRefreshScheduler` is a background task that runs independently of user requests to keep financial data up-to-date.

## 5. Data Providers and `yfinance` Integration

- **`DefeatBetaProvider`:** This is the primary provider for comprehensive historical financial data (income statements, balance sheets, etc.). It is designed to be the main source of truth for financial statements.
- **`YFinanceProvider`:** This provider is now used for two main purposes:
    1.  **Real-time Market Data:** It provides the current stock price for the initial, fast response when a user adds a stock to their watchlist.
    2.  **Fallback:** It serves as a fallback for the `DefeatBetaProvider` if the primary provider fails to retrieve data.

This separation of concerns ensures that the application has a reliable and robust data retrieval strategy.

## 6. Code Comments and Further Exploration

For a deeper understanding, it is recommended to:

- **Review the Pydantic models** in `domain/` to understand the data structures.
- **Examine the service methods** in `application/services/` to see how business logic is implemented.
- **Trace the execution flow** of a request from the API layer down to the infrastructure layer.

