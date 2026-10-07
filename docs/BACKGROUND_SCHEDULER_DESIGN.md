# Background Scheduler Architecture

## StockerPro Background Worker Design

**Document Version:** 3.1
**Date:** 2026-06-19
**Author:** StockerPro Team

---

## Table of Contents

1. [Document Structure](#1-document-structure)
2. [Current Production Architecture (v2)](#2-current-production-architecture-v2)
3. [Target Architecture (v3)](#3-target-architecture-v3)
4. [DB-Backed Job Queue](#4-db-backed-job-queue)
5. [Worker Process (Target)](#5-worker-process-target)
6. [Operational Model](#6-operational-model)
7. [Configuration Reference](#7-configuration-reference)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Appendix: Current State vs Target Summary](#9-appendix-current-state-vs-target-summary)

---

## 1. Document Structure

This document describes two architecture states:

| Section | State | Description |
|---------|-------|-------------|
| §2 | **Current (v2)** | What runs in production today |
| §3–§6 | **Target (v3)** | Approved next-state architecture (to be implemented) |
| §7 | **Current (v2)** | Configuration settings live today |
| §8 | **Roadmap** | Ordered steps to reach v3 from v2 |

---

## 2. Current Production Architecture (v2)

### 2.1 Overview

All background schedulers run in a **separate Python process** (`scheduler_worker.py`) independent from the FastAPI uvicorn process. This prevents any scheduler work from blocking HTTP requests.

```
┌─────────────────────────┐       ┌──────────────────────────┐
│   FastAPI (uvicorn)     │       │   scheduler_worker.py    │
│                         │       │                          │
│   HTTP API Endpoints    │       │   SuperInvestorsScheduler│
│   /scheduler/status     │       │   MarketDataScheduler    │
│   (static config only)  │       │   EarningsScheduler      │
│                         │       │   AggregationScheduler   │
└─────────┬───────────────┘       └────────────┬─────────────┘
          │                                    │
          │           ┌──────────┐             │
          └───────────│ Supabase │─────────────┘
                      │ (DB)    │
                      └──────────┘
```

**Key properties of v2:**
- Four independent async schedulers in one event loop
- Interval-driven (no job queue)
- Per-company distributed locks via `scheduler_locks` table
- Aggregation singleton lock via `aggregation_state` table
- In-memory state: lost on crash
- `/scheduler/status` returns static config only
- Graceful shutdown via SIGTERM/SIGINT

### 2.2 Scheduler Components

All live in `backend/application/schedulers/`.

#### 2.2.1 SuperInvestorsRefreshScheduler

**File:** `super_investors_scheduler.py`

Refreshes 13F filings for tracked super investors from SEC EDGAR.

| Property | Default | Config Key |
|----------|---------|------------|
| Interval | 24 hours | `SUPER_INVESTORS_REFRESH_INTERVAL_HOURS` |
| Initial quarters | 20 | `SUPER_INVESTORS_INITIAL_QUARTERS` |
| Grace days | 49 | `SUPER_INVESTORS_GRACE_DAYS` |

**Logic:**
- First run: fetches last N quarters (default 20 = 5 years) of historical 13F data
- Subsequent runs: only fetches new filings when past the due date (quarter end + grace days)
- Creates investor records in `institutional_investors` table on first encounter

**Error handling:** Individual investor errors are logged and continue. If ALL investors fail, `all_failed=True` is flagged for investigation.

#### 2.2.2 MarketDataRefreshScheduler

**File:** `market_data_scheduler.py`

Refreshes market-derived datasets for active companies.

| Property | Default | Config Key |
|----------|---------|------------|
| Interval | 24 hours | `MARKET_DATA_REFRESH_INTERVAL_HOURS` |
| Lookback days | 45 | `MARKET_DATA_PRICE_LOOKBACK_DAYS` |
| Max concurrency | 5 | `MARKET_DATA_MAX_CONCURRENCY` |
| Retention years | 10 | `PRICE_HISTORY_RETENTION_YEARS` |
| Lock TTL | 1800s (30 min) | `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` |

**Per-company processing steps (stocks):**
1. Price history — monthly EOM compression; bootstrap or incremental
2. Stock splits — via DefeatBeta provider
3. Revenue forecast — via DefeatBeta provider
4. Earnings forecast — via DefeatBeta provider
5. Company summary snapshot — via DefeatBeta provider
6. IS/BS/CF bootstrap — full financial sync if no income statement rows exist
7. Derived financial ratios — version-gated
8. Quarterly health scores — Piotroski F, Altman Z
9. Quarterly valuation metrics — trailing P/E, EV/EBITDA, P/FCF
10. Dividend metrics — exits early if no dividend history
11. Upcoming dividend events — YFinance + Stockdex + prediction fallback
12. RI valuation — residual income via ValuationService

For non-stock securities (ETFs, indices): only steps 1–2 run.

#### 2.2.3 EarningsRefreshScheduler

**File:** `earnings_scheduler.py`

Refreshes financial data for companies with upcoming earnings.

| Property | Default | Config Key |
|----------|---------|------------|
| Interval | 2 hours | `EARNINGS_REFRESH_CHECK_INTERVAL_HOURS` |
| Buffer days | ±10 | `EARNINGS_REFRESH_BUFFER_DAYS` |
| Lock TTL | 2700s (45 min) | `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` |

**Workflow:**
1. Query companies with `next_earnings_date` in ±N day window
2. For each: acquire per-company lock, refresh financials, update metadata, release lock
3. If new statement rows were written, trigger derived metrics, health scores, valuation metrics, data quality audit, and RI valuation

Smart filtering tracks `last_refreshed_fiscal_year/quarter` to fetch only new data (97.5% deduplication).

#### 2.2.4 AggregationScheduler

**File:** `aggregation_scheduler.py`

Computes sector/industry percentile stats for valuation metrics.

| Property | Default | Config Key |
|----------|---------|------------|
| Interval | 24 hours | `AGGREGATION_REFRESH_INTERVAL_HOURS` |

Singleton lock via `aggregation_state` table (`aggregation_id = "sector_metric_agg"`):
- No row → insert with lock
- Running + lease active → skip
- Stale/expired → take over

Calls `compute_and_upsert_group_metric_stats(group_type="sector", min_sample_size=5)`.

### 2.3 Worker Process

**File:** `backend/scheduler_worker.py`

**Startup:**
1. Register SIGTERM/SIGINT handlers
2. Initialize each enabled scheduler
3. If no schedulers enabled, exit with error

**Heartbeat:** Logs every 60s. DEBUG mode logs each scheduler's running status and `next_run_at`.

**Shutdown:**
```
SIGTERM → set shutdown_requested flag
       → stop() each scheduler (cancel asyncio task)
       → await cancellations
       → exit
```

### 2.4 Limitations of v2

| Concern | Impact |
|---------|--------|
| No durable job state | Crash loses in-flight work |
| No retry across cycles | Failure means wait until next interval |
| Static status endpoint | Can't tell if worker is alive |
| Ad hoc locking | No lease tokens, safe release, or renewal |
| Two schedulers, same companies | Duplicate fetches and lock contention |
| Aggregation uses different lock model | Inconsistent with rest of system |
| No janitor | Stale locks persist until TTL expiry |

These are addressed in the target architecture (v3).

---

## 3. Target Architecture (v3)

This section describes the approved next-state design. See §8 for the implementation roadmap.

### 3.1 Overview

```
┌─────────────────────────┐       ┌──────────────────────────────────┐
│   FastAPI (uvicorn)     │       │   scheduler_worker.py           │
│                         │       │                                  │
│   HTTP API Endpoints    │       │   ┌──────────────────────────┐   │
│   /scheduler/status     │       │   │  Planner Loop            │   │
│   (reads DB runtime)    │       │   │  (every ~60s)           │   │
│                         │       │   └──────────┬───────────────┘   │
│                         │       │              │ emits due jobs    │
│                         │       │              ▼                   │
│                         │       │   ┌──────────────────────────┐   │
│                         │       │   │  jobs table              │   │
│                         │       │   │  (durable queue)         │   │
│                         │       │   └──────────┬───────────────┘   │
│                         │       │              │ claim + lease     │
│                         │       │              ▼                   │
│                         │       │   ┌──────────────────────────┐   │
│                         │       │   │  Worker Pool             │   │
│                         │       │   │  (bounded concurrent)    │   │
│                         │       │   │  ├─ company_refresh     │   │
│                         │       │   │  ├─ investor_refresh    │   │
│                         │       │   │  └─ aggregation_refresh │   │
│                         │       │   └──────────────────────────┘   │
│                         │       │   ┌──────────────────────────┐   │
│                         │       │   │  Janitor Loop            │   │
│                         │       │   │  (every ~5min)           │   │
│                         │       │   └──────────────────────────┘   │
└─────────────────────────┘       └────────────┬─────────────────────┘
                                                │
                                      ┌─────────▼─────────────────────┐
                                      │    Supabase/DB                │
                                      │    (control plane)            │
                                      │                               │
                                      │  - jobs                       │
                                      │  - job_attempts               │
                                      │  - scheduler_state            │
                                      │  - scheduler_run_history      │
                                      │  - resource_locks             │
                                      │  - worker_heartbeats          │
                                      └───────────────────────────────┘
```

### 3.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| No Celery/Redis | DB-backed coordination avoids new infrastructure; Supabase is already a dependency |
| Planner + worker in one process | Deployment simplicity; the DB contract allows separating them later without schema changes |
| Lease-based job claims | Crash-safe: leases expire, work retries |
| Dedupe keys prevent duplicate jobs | Partial unique index on active jobs |
| All writes are idempotent | Retries are always safe |
| Unified `company_refresh` job | Eliminates overlap between MarketData and Earnings schedulers |

### 3.3 Planner and Worker Co-location

In v3, planning and execution live in the same process for operational simplicity. This means:

- A planner bug can stall job enqueueing, but in-flight worker tasks continue
- A worker crash while holding a lease is recovered by the janitor within ~5 minutes
- Memory/resource contention exists inside one runtime

**This is a deployment simplification, not the ideal end state.** The DB schema (§4) is designed so that planner and workers can be split into separate services without changes. When the system outgrows a single process, deploy:

- `scheduler-planner` — one instance, runs planner + janitor
- `worker-company-refresh` — N instances for company work
- `worker-investor-refresh` — N instances for investor work
- `worker-aggregation` — one instance for aggregation

---

## 4. DB-Backed Job Queue

The core improvement in v3. All job state is durable in Postgres, enabling retries, observability, crash recovery, and manual replay.

### 4.1 Tables

#### jobs

```sql
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        TEXT NOT NULL,          -- 'company_refresh', 'investor_refresh', 'aggregation_refresh'
    resource_type   TEXT,                   -- 'company', 'investor', 'aggregation'
    resource_id     TEXT,                   -- company_id, cik, 'sector_metric_agg'
    dedupe_key      TEXT NOT NULL,          -- unique logical key (see §4.4)
    priority        INT DEFAULT 50,         -- higher = more urgent
    status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'succeeded', 'dead_letter', 'cancelled')),
                  -- Note: no 'failed' status — retries return to 'pending'
    payload         JSONB,
    not_before      TIMESTAMPTZ,            -- don't claim before
    available_at    TIMESTAMPTZ DEFAULT NOW(),
    lease_owner     TEXT,
    lease_token     UUID,
    leased_until    TIMESTAMPTZ,
    attempts        INT DEFAULT 0,
    max_attempts    INT DEFAULT 3,
    last_error      TEXT,
    last_error_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Dedupe: only one active job per logical work unit
CREATE UNIQUE INDEX idx_active_jobs_dedupe
    ON jobs (dedupe_key)
    WHERE status IN ('pending', 'running');

-- Workers claim next available job
CREATE INDEX idx_jobs_claim
    ON jobs (status, priority DESC, available_at ASC)
    WHERE status = 'pending';
```

#### job_attempts

```sql
CREATE TABLE job_attempts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES jobs(id),
    attempt     INT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error       TEXT,
    duration_ms INT,
    UNIQUE (job_id, attempt)
);
```

#### scheduler_state

One row per scheduler, tracking the current status and timing.

```sql
CREATE TABLE scheduler_state (
    scheduler_name  TEXT PRIMARY KEY,
    enabled         BOOLEAN DEFAULT TRUE,
    interval_hours  INT,
    last_planned_at TIMESTAMPTZ,
    last_status     TEXT,           -- 'succeeded' | 'failed'
    last_error      TEXT,
    next_due_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### scheduler_run_history

Append-only history of each planner cycle.

```sql
CREATE TABLE scheduler_run_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheduler_name  TEXT NOT NULL,
    planned_at      TIMESTAMPTZ NOT NULL,
    jobs_enqueued   INT DEFAULT 0,
    status          TEXT,           -- 'succeeded' | 'failed'
    error           TEXT,
    duration_ms     INT
);
```

#### worker_heartbeats

```sql
CREATE TABLE worker_heartbeats (
    worker_id   TEXT PRIMARY KEY,
    hostname    TEXT,
    pid         INT,
    started_at  TIMESTAMPTZ,
    last_hb_at  TIMESTAMPTZ DEFAULT NOW(),
    active_jobs INT DEFAULT 0
);
```

#### resource_locks

Used only when multiple job types or out-of-band operations need cross-job serialization on the same entity. When a unified `company_refresh` job is the only job type touching a company, the job lease alone suffices.

```sql
CREATE TABLE resource_locks (
    resource_type   TEXT NOT NULL,     -- 'company', 'aggregation'
    resource_id     TEXT NOT NULL,
    lock_type       TEXT NOT NULL,     -- 'market_data_refresh', 'earnings_refresh'
    owner_id        TEXT NOT NULL,
    lease_token     UUID NOT NULL,
    leased_until    TIMESTAMPTZ NOT NULL,
    heartbeat_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (resource_type, resource_id, lock_type)
);
```

See §6.5 for the full lock contract.

### 4.2 Job Status Model

```
Statuses are defined per job:
  pending      → awaiting execution (may have been retried)
  running      → claimed by a worker
  succeeded    → completed successfully
  dead_letter  → exceeded max_attempts
  cancelled    → manually aborted

There is no 'failed' status at the job level. When an attempt fails:
  - If attempts < max_attempts → available_at = NOW() + backoff, status = 'pending'
  - If attempts >= max_attempts → status = 'dead_letter'

Attempts track their own status: 'running' | 'succeeded' | 'failed'
```

### 4.3 Job Lifecycle

```
planner → INSERT pending job (unique dedupe_key prevents duplicates)
              │
              ▼
worker → atomic claim via UPDATE ... RETURNING
    sets status='running', lease_owner, lease_token, leased_until
              │
              ▼
         Execute handler (periodic lease renewal for long jobs)
              │
         ┌────┴────┐
         ▼         ▼
    UPDATE      INSERT job_attempts (failed)
    status=     attempts < max_attempts?
    'succeeded'   ├── yes → UPDATE available_at = NOW() + backoff
                 │          UPDATE status = 'pending'
                 └── no  → UPDATE status = 'dead_letter'
```

### 4.4 Deduplication

The `dedupe_key` uniquely identifies a logical unit of work:

| Job Type | Dedupe Key Pattern | Example |
|----------|-------------------|---------|
| `company_refresh` | `company_refresh:{company_id}` | `company_refresh:123` |
| `investor_refresh` | `investor_refresh:{cik}` | `investor_refresh:0000320193` |
| `aggregation_refresh` | `aggregation_refresh:{group_type}` | `aggregation_refresh:sector` |

The partial unique index `idx_active_jobs_dedupe` ensures only one non-terminal job exists per dedupe key. The planner performs a simple INSERT and relies on duplicate-key violations being treated as successful deduplication.

**For unified company refresh** (see §4.7), merge rules must respect the one-active-job invariant:

```
When a new company_refresh request arrives for a company with
an existing pending job:
  - priority  = GREATEST(existing.priority, new.priority)
  - scopes    = UNION(existing.scopes, new.scopes)
  - reasons   = UNION(existing.reasons, new.reasons)
  - planner updates the existing pending job in place
    (within a transaction using SELECT ... FOR UPDATE to prevent
     concurrent merge conflicts) and skips INSERT.

When a new request arrives and the existing job is already running:
  - If new scopes ⊆ running job's scopes → no action needed.
  - If new scopes ⊈ running job's scopes → the planner records
    the delta in a per-company refresh request accumulator
    (a lightweight table or JSON field). After the running job
    completes, its completion handler checks for accumulated
    requests. If unprocessed scopes exist, the planner emits
    one follow-up pending job for those scopes.
  - This preserves the one-active-job-per-company invariant while
    still allowing scope expansion requests during execution.
```

The refresh request accumulator can be implemented as a simple table:

```sql
CREATE TABLE company_refresh_requests (
    company_id      INT NOT NULL,
    requested_at    TIMESTAMPTZ DEFAULT NOW(),
    scopes          TEXT[] NOT NULL,
    reasons         TEXT[] NOT NULL,
    priority        INT DEFAULT 50,
    processed       BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (company_id, requested_at)
);
```

The planner appends rows here when scope expansion is needed. The job completion handler reads unprocessed rows for the company and emits them as a single follow-up job with the union of all accumulated scopes. This decouples the one-active-job invariant from the need to capture scope requests during execution.

### 4.5 Atomic Claim Semantics

Workers must NOT do a separate SELECT then UPDATE — that creates race conditions. Instead:

```sql
WITH next_job AS (
    SELECT id
    FROM jobs
    WHERE status = 'pending'
      AND (available_at IS NULL OR available_at <= NOW())
    ORDER BY priority DESC, available_at ASC, created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE jobs j
SET status = 'running',
    lease_owner = :worker_id,
    lease_token = gen_random_uuid(),
    leased_until = NOW() + INTERVAL '30 minutes',
    attempts = attempts + 1,
    updated_at = NOW()
FROM next_job
WHERE j.id = next_job.id
RETURNING j.*;
```

`FOR UPDATE SKIP LOCKED` prevents contention — two workers can each claim different jobs without blocking each other. If Supabase's Postgres version doesn't support `SKIP LOCKED` (9.5+ does), fall back to `FOR UPDATE` with a small timeout.

### 4.6 Retry with Backoff

| Failure Pattern | Backoff | Max Attempts | Action |
|----------------|---------|-------------|--------|
| Network timeout | 5 min | 3 | Retry |
| Provider rate limit (429) | 15 min | 3 | Retry |
| Provider 5xx | 1 hour | 3 | Retry |
| Data validation error | — | 1 | Dead letter |
| Code exception | 5 min | 3 | Retry + escalate |

Backoff is stored as `available_at = NOW() + INTERVAL '...'` — the job becomes claimable again only after that timestamp.

### 4.7 Unified Company Refresh Model

Instead of MarketData and Earnings independently refreshing the same companies, define one canonical job type:

**Job type:** `company_refresh`

**Payload:**
```json
{
  "company_id": 123,
  "symbol": "AAPL",
  "reasons": ["routine"],
  "scopes": ["prices", "splits", "forecasts", "financials",
             "derived_metrics", "health_scores", "valuation_metrics",
             "dividends", "ri_valuation"],
  "priority": 50
}
```

**Planner sources:**
| Source | Cadence | Scopes | Priority |
|--------|---------|--------|----------|
| Routine sweep | Every 24h | All | 50 |
| Earnings window | Every 2h | `financials`, `derived_metrics`, `health_scores`, `valuation_metrics`, `ri_valuation` | 80 |
| Bootstrap | On add | All | 90 |
| Manual | On demand | As specified | 100 |

**Merge rules (see §4.4):** The planner merges new requests into existing pending jobs via priority upgrade and scope union, using row-level locking for safety. If the target job is already running, unhandled scopes are recorded in a `company_refresh_requests` accumulator table. The running job's completion handler checks the accumulator and emits one follow-up pending job for any accumulated unprocessed scopes.

---

## 5. Worker Process (Target)

**File:** `backend/scheduler_worker.py`

### 5.1 Architecture

The worker runs a single event loop with three async task types:

**Planner Loop** (every ~60s):
- For each enabled scheduler, check if `next_due_at` has passed
- If due, call `scheduler.plan()` which returns a list of job dicts
- INSERT jobs with dedupe keys (duplicate-key conflicts are treated as successful deduplication)
- Advance `next_due_at = NOW() + interval_hours`
- Record planner cycle to `scheduler_run_history`

**Missed-interval behavior:** Scheduler planning is state-based, not interval-replay-based. If the planner is down for multiple intervals, it emits at most one current batch and advances `next_due_at` from the current time. No catch-up batches are enqueued for missed intervals — the next scheduled run will handle whatever is due at that point.

**Worker Pool** (bounded concurrency):
- Poll `jobs` for pending work
- Claim atomically via CTE (§4.5)
- Execute the appropriate handler
- Record attempt outcome
- Renew lease every 60s for long-running jobs
- On completion: set status, or schedule retry with backoff

**Janitor Loop** (every ~5min):
```sql
-- Reclaim expired leases (capture old owner before nulling)
UPDATE jobs SET
    status = 'pending',
    lease_owner = NULL,
    lease_token = NULL,
    leased_until = NULL,
    last_error = CONCAT('lease expired: owner=', COALESCE(lease_owner, 'unknown')),
    last_error_at = NOW(),
    updated_at = NOW()
WHERE status = 'running'
  AND leased_until < NOW();

-- Log anomalies (stuck jobs, stale heartbeats)
SELECT COUNT(*) FROM jobs WHERE status = 'running' AND leased_until < NOW();
SELECT COUNT(*) FROM worker_heartbeats WHERE last_hb_at < NOW() - INTERVAL '2 minutes';
```

### 5.2 Startup Sequence

1. Register SIGTERM/SIGINT handlers
2. Initialize each enabled scheduler
3. Start planner, worker pool, and janitor loops as asyncio tasks
4. Log heartbeat every 60s (update `worker_heartbeats`)

### 5.3 Graceful Shutdown

1. Stop planner loop (no more enqueueing)
2. Signal worker pool to stop claiming new jobs
3. Wait for in-flight jobs (up to `TimeoutStopSec`, 300s via systemd)
4. Release leases on claimed-but-incomplete jobs (UPDATE `lease_owner = NULL`, `status = 'pending'`)
5. Stop janitor loop
6. Update worker heartbeat with final state
7. Exit

---

## 6. Operational Model

### 6.1 Runtime Status

**`GET /scheduler/status`** (FastAPI `main.py`) reads from DB.

The endpoint evolves across implementation phases:
- **Phase 1**: worker heartbeat + scheduler timing only
- **Phase 2+**: queue depth, dead letters, stale leases
- **Phase 3+**: stale heartbeat and anomaly reporting

The response exposes raw telemetry. Health classification (alive vs degraded vs healthy) may be added as a derived signal:

| Signal | Healthy | Degraded |
|--------|---------|----------|
| Worker heartbeat | `< 60s old` | `> 120s old` |
| Stale leases | `0` | `> 0` |
| Dead letter jobs | `0` | `> 0` and growing |
| Oldest pending job | `< 1 hour` | `> 4 hours` |

Example response:

```json
{
    "worker": {
        "alive": true,
        "last_heartbeat": "2026-06-19T12:00:00Z",
        "active_jobs": 3
    },
    "schedulers": {
        "super_investors": {
            "enabled": true,
            "interval_hours": 24,
            "last_planned_at": "2026-06-19T06:00:00Z",
            "next_due_at": "2026-06-20T06:00:00Z"
        },
        "market_data": {
            "enabled": true,
            "interval_hours": 24,
            "last_planned_at": "2026-06-19T05:00:00Z",
            "last_status": "succeeded"
        },
        "earnings": {
            "enabled": true,
            "interval_hours": 2,
            "last_planned_at": "2026-06-19T11:00:00Z",
            "next_due_at": "2026-06-19T13:00:00Z"
        },
        "aggregation": {
            "enabled": true,
            "interval_hours": 24,
            "last_planned_at": "2026-06-19T04:00:00Z",
            "next_due_at": "2026-06-20T04:00:00Z"
        }
    },
    "queue": {
        "pending": 12,
        "running": 3,
        "dead_letter": 0,
        "oldest_pending_age_seconds": 3400
    },
    "stale_leases": 0,
    "stale_heartbeats": 0
}
```

### 6.2 Idempotency

Every write path must be safely repeatable:

| Operation | Idempotency Mechanism |
|-----------|----------------------|
| Holding upsert | `UNIQUE(investor_id, company_id, quarter_end_date)` → upsert |
| Price history | `UNIQUE(company_id, price_date)` → upsert |
| Financial statements | `UNIQUE(company_id, fiscal_year, fiscal_quarter, table_type)` → skip/update |
| Derived metrics | Version-gated — only writes when source data hash changed |
| Dividend events | `UNIQUE(company_id, data_source)` → upsert |
| Aggregation stats | `UNIQUE(group_type, group_name, metric_name, source_version)` → upsert |

### 6.3 Aggregation Through Jobs (v3 change)

In v3, aggregation uses the same job queue as everything else:

- Job type: `aggregation_refresh`
- Dedupe key: `aggregation_refresh:sector`
- Worker handler calls `compute_and_upsert_group_metric_stats()`
- No separate `aggregation_state` table — the job lease IS the singleton lock

This eliminates the inconsistent locking model from v2 and gives aggregation all the same retry, observability, and dedupe benefits as other jobs.

### 6.4 Resource Locks vs Job Leases

Job leases (the `lease_owner`/`lease_token`/`leased_until` columns on `jobs`) control ownership of queue work. They are sufficient when exactly one job type touches a given resource.

`resource_locks` are only needed when:
- Multiple job types may touch the same entity concurrently (e.g., a `company_refresh` and a manual admin operation)
- Out-of-band operations (API endpoints, scripts) need the same lock contract

With unified `company_refresh` being the sole job type for companies, `resource_locks` may become unnecessary for the company use case. They are retained as a general-purpose primitive for cross-job serialization.

### 6.5 Lock Contract

**Acquire:**
- If no row exists → INSERT with `(owner_id, lease_token, leased_until)`
- If `leased_until < NOW()` → UPDATE (stale lock takeover)
- Otherwise → lock held (skip)

**Release:**
- Must match BOTH `owner_id` AND `lease_token` — prevents releasing another worker's lock

**Renewal:**
- Long-running jobs UPDATE `leased_until = NOW() + TTL` every 60s

### 6.6 Data Retention

| Table | Retention | Rationale |
|-------|-----------|-----------|
| `jobs` (succeeded) | 90 days | Enough for debugging, not so long that pruning is expensive |
| `jobs` (dead_letter) | 180 days | Keep longer for post-mortem analysis |
| `job_attempts` | 90 days | Tied to job retention |
| `scheduler_run_history` | 90 days | Enough to spot planner health trends |
| `worker_heartbeats` | 7 days after last update | Stale workers are pruned by janitor |

---

## 7. Configuration Reference

### 7.1 Feature Flags

| Setting | Default | Description |
|---------|---------|-------------|
| `ENABLE_SUPER_INVESTORS_SCHEDULER` | True | Enable super investors 13F refresh |
| `ENABLE_MARKET_DATA_SCHEDULER` | True | Enable market data refresh |
| `ENABLE_EARNINGS_SCHEDULER` | True | Enable earnings refresh |
| `ENABLE_AGGREGATION_SCHEDULER` | True | Enable sector metric aggregation |

### 7.2 Scheduler Intervals

| Setting | Default | Description |
|---------|---------|-------------|
| `SUPER_INVESTORS_REFRESH_INTERVAL_HOURS` | 24 | Hours between super investors runs |
| `MARKET_DATA_REFRESH_INTERVAL_HOURS` | 24 | Hours between market data runs |
| `EARNINGS_REFRESH_CHECK_INTERVAL_HOURS` | 2 | Hours between earnings checks |
| `AGGREGATION_REFRESH_INTERVAL_HOURS` | 24 | Hours between aggregation runs |

### 7.3 Scheduler-Specific Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `SUPER_INVESTORS_INITIAL_QUARTERS` | 20 | Quarters to fetch on first run |
| `SUPER_INVESTORS_GRACE_DAYS` | 49 | Days after quarter end before filing due |
| `MARKET_DATA_PRICE_LOOKBACK_DAYS` | 45 | Lookback window for incremental price fetch |
| `MARKET_DATA_MAX_CONCURRENCY` | 5 | Parallel company processing limit |
| `EARNINGS_REFRESH_BUFFER_DAYS` | 10 | ±N day window for upcoming earnings |
| `PRICE_HISTORY_RETENTION_YEARS` | 10 | Rolling retention window for price data |
| `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` | 1800 | Per-company lock TTL (2700 for earnings) |

### 7.4 Scheduler Locking (v2 current)

- **Market Data:** Per-company locks via `scheduler_locks` table
- **Earnings:** Per-company locks via `scheduler_locks` table
- **Aggregation:** Singleton lock via `aggregation_state` table (to be replaced in v3)

---

## 8. Implementation Roadmap

Ordered by impact vs. complexity. Each step is independently deployable.

### Phase 1: Runtime Observability (Low effort, high value)

**Status:** Not started

**What:**
1. Create `scheduler_state`, `scheduler_run_history`, `worker_heartbeats` tables
2. Have each scheduler write run metadata to `scheduler_state` after each cycle
3. Have the worker update `worker_heartbeats` every 60s
4. Update `/scheduler/status` to read from these tables instead of returning static config

**Why:** Without runtime visibility, you can't tell if the system is healthy. This is a wiring change — the logic already computes these values internally.

### Phase 2: DB-Backed Job Queue (Core improvement)

**Status:** Not started

**What:**
1. Create `jobs` and `job_attempts` tables with indexes
2. Refactor each scheduler from "execute work" to "plan work":
   - SuperInvestors: plan emits `investor_refresh` jobs per CIK
   - MarketData: plan emits `company_refresh` jobs per company
   - Earnings: plan emits `company_refresh` jobs for companies in earnings window
   - Aggregation: plan emits `aggregation_refresh` job
3. Implement atomic job claim CTE (§4.5)
4. Implement worker pool with bounded concurrency
5. Implement retry with backoff (§4.6)

**Why:** Unlocks crash recovery, retries, dedupe, manual replay, and queryable job state.

### Phase 3: Janitor Loop

**Status:** Not started

**What:**
1. Add janitor loop to worker process
2. Reclaim expired leases
3. Detect stale heartbeats and log anomalies
4. Prune old records per retention policy (§6.6)

**Why:** Without a janitor, crashed workers leave jobs in `running` state until leases naturally expire.

### Phase 4: Strengthen Lock Contract

**Status:** Not started

**What:**
1. Add `lease_token` (UUID) to `scheduler_locks`
2. Update acquire to generate and return lease token
3. Update release to require matching `(owner_id, lease_token)`
4. Add periodic lease renewal for long-running jobs

**Why:** Prevents one worker from accidentally releasing another's lock. Critical for multi-replica safety.

### Phase 5: Unified Company Refresh

**Status:** Not started

**What:**
1. Define single `company_refresh` job type with scopes/reasons (§4.7)
2. Merge MarketData and Earnings planners to emit the same job type
3. Implement dedupe merge rules (priority upgrade, scope union)
4. Remove `resource_locks` for company use case if no longer needed

**Why:** Eliminates duplicate work, lock contention, and inconsistent behavior between the two schedulers.

### Manual Replay

To requeue a job for manual replay (e.g., after a transient failure investigation):

```sql
-- Replay a specific dead-letter job
UPDATE jobs SET
    status = 'pending',
    attempts = 0,
    last_error = NULL,
    last_error_at = NULL,
    available_at = NOW(),
    lease_owner = NULL,
    lease_token = NULL,
    leased_until = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND status = 'dead_letter';
```

Replay should be restricted to dead-letter jobs. Replaying succeeded jobs risks duplicate side effects even with idempotent writes. The operator must also clear `lease_owner`, `lease_token`, and `leased_until` so the job is claimable.

### Implementation Notes

These are not architectural decisions but operational details to keep in mind during implementation.

**1. Janitor pruning.** The janitor loop should also delete old records per the retention policy (§6.6). After reclaiming expired leases, it should run:

```sql
DELETE FROM job_attempts WHERE finished_at < NOW() - INTERVAL '90 days';
DELETE FROM jobs          WHERE updated_at  < NOW() - INTERVAL '90 days'
                              AND status IN ('succeeded', 'cancelled');
DELETE FROM jobs          WHERE updated_at  < NOW() - INTERVAL '180 days'
                              AND status = 'dead_letter';
DELETE FROM scheduler_run_history WHERE planned_at < NOW() - INTERVAL '90 days';
DELETE FROM worker_heartbeats     WHERE last_hb_at  < NOW() - INTERVAL '7 days';
```

**2. Accumulator completion flow.** When a running `company_refresh` job finishes, its completion handler must:

```python
# Pseudocode — read unprocessed requests for this company
pending = company_refresh_requests.select(
    company_id=company_id, processed=False
)
if pending:
    merged_scopes = union(pending.scopes)
    merged_priority = max(pending.priority)
    # Emit one follow-up job with the accumulated scopes
    jobs.insert(dedupe_key=f"company_refresh:{company_id}",
                scopes=merged_scopes, priority=merged_priority)
    # Mark rows as processed
    company_refresh_requests.update(processed=True)
```

**3. Planner singleton.** The planner loop is safe in a single process. If the worker is ever split into separate planner and executor processes, only one planner instance should enqueue jobs (the dedupe keys on `jobs` prevent duplicates, but concurrent planner instances waste DB cycles and make `next_due_at` timing unreliable).

**4. Backoff edge cases.** The retry backoff table (§4.6) treats most provider failures as retryable. Some 4xx responses should bypass retry and go directly to dead-letter:

| HTTP Status | Example | Action |
|-------------|---------|--------|
| 404 | Filing not found (SEC) | Dead letter — resource doesn't exist |
| 400 | Bad request (malformed CIK) | Dead letter — will never succeed |
| 429 | Rate limited | Retry with longer backoff |
| 5xx | Provider unavailable | Retry with backoff |

These classifications are trivially adjustable in each job handler.

### Deferred (not in scope for v3)

| Item | Rationale |
|------|-----------|
| Separate planner/worker/processes | Add when single-process resource contention is observed |
| Per-provider rate limiting framework | SEC EDGAR throttling and provider stability are managed per-handler with timeouts and backoff; a global rate-limiter framework can be added if contention across handlers becomes an issue |
| Dirty-set aggregation triggers | 24h interval works; revisit if staleness becomes a problem |
| Decompose downstream steps into separate jobs | Do this after unified company refresh is stable |
| Circuit breakers for provider outages | Add when a specific provider outage pattern emerges |

---

## 9. Testing & Data Validation Plan

This section defines how to validate each scheduler's correctness, with emphasis on verifying the actual data stored in the database to ensure no gaps or corruption.

### 9.1 Testing Layers

| Layer | Scope | Environment |
|-------|-------|-------------|
| Unit tests | Individual methods, mocked providers | CI (fast) |
| Integration tests | Scheduler cycle against test DB, real provider data optional | CI + local |
| Data integrity audits | SQL queries against production DB to detect gaps | Scheduled job / manual |
| End-to-end | Full worker process lifecycle | Staging / dev |

### 9.2 SuperInvestors Refresh — Data Validation

**Tables under test:** `institutional_investors`, `institutional_holdings`, `companies`

#### Unit tests

| Test | What it validates | Current status |
|------|-------------------|----------------|
| `_create_investor_record` inserts correct columns | cik, investor_name, firm_name, investor_tag, is_super_investor, is_active all set | Missing — needs test |
| `_fetch_historical_data` saves holdings for each quarter | Holdings rows written for each of N quarters | Missing — needs test |
| `_save_holdings_to_db` computes delta correctly | shares_change, shares_change_pct, change_type values are correct | Missing — needs test |
| `_save_holdings_to_db` skips missing tickers | Row with no Ticker value is skipped | Missing — needs test |
| `_calculate_next_due_date` | Returns correct date based on last_period + grace_days | Missing — needs test |
| `_refresh_single_investor` skips when not due | Returns False, no DB writes | Missing — needs test |
| `_update_investor_tracking` | last_filed_period and last_filed_date updated | Missing — needs test |

#### Integration tests (test DB, real or seeded provider data)

**1. First-run historical fetch — no gaps in quarters**

```
Given: No investor record exists for CIK X
When:  _refresh_single_investor() runs
Then:  institutional_investors has 1 row for that CIK
And:   institutional_holdings has rows for each of the last N quarters
And:   No quarter in [recent_N_quarters] is missing from holdings
```

SQL validation:

```sql
-- Check all expected quarters are present for an investor
SELECT DISTINCT quarter_end_date
FROM institutional_holdings ih
JOIN institutional_investors ii ON ih.investor_id = ii.investor_id
WHERE ii.cik = :cik
ORDER BY quarter_end_date;

-- Expected: exactly N distinct quarters, no gaps in the sequence
-- Gap detection:
WITH quarters AS (
    SELECT quarter_end_date,
           LAG(quarter_end_date) OVER (ORDER BY quarter_end_date) AS prev_date
    FROM institutional_holdings ih
    JOIN institutional_investors ii ON ih.investor_id = ii.investor_id
    WHERE ii.cik = :cik
)
SELECT * FROM quarters
WHERE prev_date IS NOT NULL
  AND quarter_end_date - prev_date > INTERVAL '120 days';
```

**2. Incremental run — only new filing is saved**

```
Given: Investor record exists with last_filed_period = '2025-09-30'
When:  _refresh_single_investor() runs and SEC has a Q4 2025 filing
Then:  Only the 2025-12-31 quarter is added (no re-fetch of Q3 2025)
And:   Total distinct quarters for that investor increases by exactly 1
```

**3. Deduplication — same period does not create duplicate rows**

```
Given: Holdings exist for investor X, period 2025-12-31
When:  _save_holdings_to_db() is called again with same period
Then:  No duplicate (investor_id, company_id, quarter_end_date) rows exist
```

SQL validation:

```sql
-- Detect duplicate holdings
SELECT investor_id, company_id, quarter_end_date, COUNT(*)
FROM institutional_holdings
GROUP BY investor_id, company_id, quarter_end_date
HAVING COUNT(*) > 1;

-- Expected: zero rows returned
```

**4. Delta computation — correct change tracking**

```
Given: Investor held 1000 shares of AAPL in Q3 2025
When:  Q4 2025 filing shows 1200 shares
Then:  shares_change = +200
And:   shares_change_pct = +20.0
And:   change_type = 'increased'
```

**5. Company creation missing companies**

Only `companies` that already exist in the DB are used. If a ticker is not in `companies`, the holding is skipped (no auto-creation). Validate with:

```sql
-- Check no holdings reference a non-existent company
SELECT ih.*
FROM institutional_holdings ih
LEFT JOIN companies c ON ih.company_id = c.company_id
WHERE c.company_id IS NULL;

-- Expected: zero rows returned
```

### 9.3 Market Data Refresh — Data Validation

**Tables under test:** `price_history`, `company_summary`, `revenue_forecast`, `earnings_forecast`, `income_statements`, `balance_sheets`, `cash_flow_statements`, `financial_ratios`, `dividend_history`, `upcoming_dividend_events`, `splits`

#### Unit tests

| Test | What it validates | Current status |
|------|-------------------|----------------|
| `sanitize_daily_price_rows` | One row per trading day; coalesces NaN/zero, numeric coercion | Existing (test_price_rows.py) |
| `_upsert_daily_price_history` bootstrap | Full daily-grain fetch when no rows exist (>= retention cutoff) | Covered (integration, test_price_history_daily_density_integration.py) |
| `_upsert_daily_price_history` incremental | Recent-window daily rows supersede monthly-EOM rows at same PK | Covered (integration, test_price_history_daily_density_integration.py) |
| `_has_any_financials` | Correctly detects existing/annual rows | Missing — needs test |
| `_process_company` stock skips for ETF | Only prices + splits, no financials/ratios | Existing (test_non_stock_skips_stock_only_operations) |
| `_process_company` bootstrap triggers financial sync | get_all_financials_optimized called when no financials exist | Existing (test_bootstrap_uses_min_fiscal_year_2021) |
| `estimate_next_ex_date` | Predicts next ex-date from payment pattern | Missing — needs test |

#### Integration tests

**1. Price history — daily grain, no monthly compression**

```
Given: Company X has daily data from 2020 to 2026
When:  Market data refresh runs
Then:  price_history has one row per trading day (no monthly EOM compression)
And:   Every month holds multiple rows (>= 5 trading days), never a single
       monthly-EOM row
```

SQL validation:

```sql
-- Detect monthly compression (the defect: exactly one row per month)
WITH monthly AS (
    SELECT company_id,
           DATE_TRUNC('month', price_date) AS month,
           COUNT(*) AS rows_in_month
    FROM price_history
    WHERE company_id = :company_id
    GROUP BY company_id, DATE_TRUNC('month', price_date)
)
SELECT * FROM monthly WHERE rows_in_month < 5;

-- Expected: zero rows (daily grain preserved)
```

```sql
-- Detect missing months (gaps in the sequence)
WITH months AS (
    SELECT DISTINCT DATE_TRUNC('month', price_date) AS month
    FROM price_history
    WHERE company_id = :company_id
), all_months AS (
    SELECT GENERATE_SERIES(
        (SELECT MIN(month) FROM months),
        (SELECT MAX(month) FROM months),
        '1 month'::INTERVAL
    ) AS month
)
SELECT am.month AS missing_month
FROM all_months am
LEFT JOIN months m ON am.month = m.month
WHERE m.month IS NULL;

-- Expected: zero rows (no calendar gaps)
```

**2. Retention window enforced**

```
Given: retention_years = 10
When:  Price history bootstrap runs
Then:  No price_history rows have price_date older than 10 years ago
```

```sql
SELECT COUNT(*) FROM price_history
WHERE company_id = :company_id
  AND price_date < CURRENT_DATE - INTERVAL '10 years';

-- Expected: 0
```

**3. Split data — no orphan rows**

```sql
-- Check all splits reference valid companies
SELECT s.*
FROM splits s
LEFT JOIN companies c ON s.company_id = c.company_id
WHERE c.company_id IS NULL;

-- Expected: zero rows
```

**4. Revenue/earnings forecasts — chronological order**

```sql
-- Verify forecasts are in ascending fiscal period order
SELECT fiscal_period, fiscal_year, LEAD(fiscal_period) OVER (ORDER BY fiscal_year, fiscal_period) AS next_period
FROM revenue_forecast
WHERE company_id = :company_id
ORDER BY fiscal_year, fiscal_period;
```

**5. Derived metrics — version gating**

```sql
-- Verify no duplicate metric rows per company per period
SELECT company_id, metric_name, fiscal_year, fiscal_quarter, COUNT(*)
FROM financial_ratios
GROUP BY company_id, metric_name, fiscal_year, fiscal_quarter
HAVING COUNT(*) > 1;

-- Expected: zero rows
```

### 9.4 Earnings Refresh — Data Validation

**Tables under test:** `income_statements`, `balance_sheets`, `cash_flow_statements`, `company_refresh_metadata`

#### Unit tests

| Test | What it validates | Current status |
|------|-------------------|----------------|
| `_check_and_refresh_earnings` no companies | Returns early with 0 counts | Existing (test_no_companies_returns_early) |
| `_refresh_company_financials_optimized` rows written → derived metrics | Derived metrics computed only when rows written | Existing |
| `_refresh_company_financials_optimized` no rows → skip derived | Derived metrics NOT computed when zero rows | Existing |
| RI valuation triggered | compute_residual_income_if_stale called with force=True | Existing |
| Next earnings date propagated | update_company_refresh_metadata called with correct date | Missing — needs test |

#### Integration tests

**1. No duplicate statement rows**

```sql
-- Detect duplicate financial statements (across all three tables)
SELECT company_id, fiscal_year, fiscal_quarter, COUNT(*)
FROM income_statements
GROUP BY company_id, fiscal_year, fiscal_quarter
HAVING COUNT(*) > 1;

-- Same for balance_sheets and cash_flow_statements
```

**2. Statement rows have matching fiscal periods across tables**

```sql
-- Find mismatched periods: income_statements has 2024 Q4 but balance_sheets doesn't
SELECT DISTINCT i.fiscal_year, i.fiscal_quarter
FROM income_statements i
WHERE i.company_id = :company_id
  AND NOT EXISTS (
    SELECT 1 FROM balance_sheets b
    WHERE b.company_id = i.company_id
      AND b.fiscal_year = i.fiscal_year
      AND (b.fiscal_quarter = i.fiscal_quarter OR (b.fiscal_quarter IS NULL AND i.fiscal_quarter IS NULL))
  );
```

**3. Refresh metadata is updated after each run**

```sql
-- Verify last_refreshed_fiscal_year/quarter advance monotonically
SELECT last_refreshed_fiscal_year, last_refreshed_fiscal_quarter, updated_at
FROM company_refresh_metadata
WHERE company_id = :company_id
ORDER BY updated_at DESC
LIMIT 5;
```

### 9.5 Aggregation — Data Validation

**Tables under test:** Sector/industry metric aggregation tables

#### Integration tests

**1. All sectors present**

```sql
-- Verify all expected sectors have aggregation rows
SELECT DISTINCT group_name
FROM sector_metric_stats
WHERE group_type = 'sector'
ORDER BY group_name;

-- Compare against distinct sectors in companies table
SELECT DISTINCT sector FROM companies WHERE sector IS NOT NULL
EXCEPT
SELECT DISTINCT group_name FROM sector_metric_stats WHERE group_type = 'sector';

-- Expected: empty set (all sectors covered)
```

**2. Sample size threshold enforced**

```sql
-- Check min_sample_size=5 is respected
SELECT group_name, COUNT(*) AS company_count
FROM sector_metric_stats sms
JOIN companies c ON c.sector = sms.group_name
WHERE sms.group_type = 'sector'
GROUP BY group_name
HAVING COUNT(*) < 5;

-- Expected: sectors with <5 companies either excluded or flagged
```

**3. Metric values are within sane bounds**

```sql
-- Verify percentile values are valid (0-100 range)
SELECT metric_name, PERCENTILE_25, PERCENTILE_50, PERCENTILE_75, PERCENTILE_90
FROM sector_metric_stats
WHERE group_type = 'sector'
  AND (PERCENTILE_25 < 0 OR PERCENTILE_25 > 100
    OR PERCENTILE_50 < 0 OR PERCENTILE_50 > 100);

-- Expected: zero rows (all percentiles in [0,100])
```

### 9.6 Job Queue (v3) — Functional Tests

#### Unit tests

| Test | What it validates |
|------|-------------------|
| Job claim CTE claims exactly one pending job | Race condition safety |
| Job claim skips locked rows | `FOR UPDATE SKIP LOCKED` behavior |
| Retry increments attempts and sets available_at | Backoff delay is applied |
| Max attempts reached → dead_letter | Terminal state |
| Dedupe key prevents duplicate INSERT | Unique partial index works |
| Lease renewal updates leased_until | Long-running jobs stay claimed |
| Janitor reclaims expired leases | `leased_until < NOW()` reclaimed |
| Scheduler state updated after planner cycle | `last_planned_at`, `next_due_at` set |

#### Integration tests

**1. Planner → job lifecycle (end-to-end)**

```
Given: Scheduler X is due (next_due_at in the past)
When:  Planner loop runs
Then:  jobs table has N new pending rows with correct job_type, dedupe_key, payload
And:   scheduler_state.next_due_at is advanced
And:   scheduler_run_history has one new row
```

**2. Worker claims and executes**

```
Given: jobs has a pending row
When:  Worker pool runs claim CTE
Then:  That row has status='running', lease_owner set, lease_token set, leased_until set
And:   job_attempts has one row with status='running'
And:   After handler completes, job_attempts.status = 'succeeded'
And:   jobs.status = 'succeeded'
```

**3. Retry works across worker restarts**

```
Given: A job fails with a transient error
When:  Worker sets available_at = NOW() + backoff, status = 'pending'
Then:  Job is not claimable until available_at passes
And:   After available_at, a new worker can claim and execute it
```

**4. Dead letter stops retries**

```
Given: A job has failed 3 times
When:  The 3rd attempt fails
Then:  jobs.status = 'dead_letter'
And:   No more attempts are made
```

**5. Manual replay requeues dead letter**

```
Given: A job is in dead_letter status
When:  Operator runs the replay SQL
Then:  jobs.status = 'pending', lease fields cleared, attempts = 0
And:   Worker can claim and execute it again
```

### 9.7 Locking — Validation

**1. Concurrent claims are exclusive**

```
Given: Two workers attempt to claim the same job simultaneously
When:  Both run the claim CTE
Then:  Exactly one worker gets the row (RETURNING returns 1 row)
And:   The other worker gets zero rows
```

**2. Lease expiry allows reclamation**

```
Given: A job is running with leased_until = NOW() - 1 minute
When:  Janitor loop runs
Then:  job status = 'pending', lease fields cleared
And:   Another worker can claim it
```

**3. Resource lock safe release**

```
Given: Worker A holds a resource lock with lease_token = X
When:  Worker B tries to release using lease_token = Y
Then:  Release fails (0 rows updated)
And:   Worker A can still release using lease_token = X
```

### 9.8 Data Integrity Audits

These queries should be run periodically (e.g., as a scheduled job or manual check) to detect data quality issues.

#### Orphan records

```sql
-- Holdings without a valid investor
SELECT * FROM institutional_holdings
WHERE investor_id NOT IN (SELECT investor_id FROM institutional_investors);

-- Holdings without a valid company
SELECT * FROM institutional_holdings
WHERE company_id NOT IN (SELECT company_id FROM companies);

-- Price history without a valid company
SELECT * FROM price_history
WHERE company_id NOT IN (SELECT company_id FROM companies);

-- Financial ratios without a valid company
SELECT * FROM financial_ratios
WHERE company_id NOT IN (SELECT company_id FROM companies);
```

#### Duplicate detection

```sql
-- Duplicate price history (same company, same date)
SELECT company_id, price_date, COUNT(*)
FROM price_history
GROUP BY company_id, price_date
HAVING COUNT(*) > 1;

-- Duplicate company summary
SELECT company_id, COUNT(*)
FROM company_summary
GROUP BY company_id
HAVING COUNT(*) > 1;
```

#### Monotonicity checks

```sql
-- Holdings should have increasing quarter_end_date over time
-- A gap or regression indicates a problem
SELECT investor_id, quarter_end_date,
       LAG(quarter_end_date) OVER (PARTITION BY investor_id ORDER BY quarter_end_date) AS prev_quarter
FROM institutional_holdings
ORDER BY investor_id, quarter_end_date;
```

#### Freshness checks

```sql
-- Companies that should have been refreshed but haven't been
-- (relevant for market data: every company should have price history within retention window)
SELECT c.company_id, c.ticker_symbol,
       MAX(ph.price_date) AS last_price_date
FROM companies c
LEFT JOIN price_history ph ON c.company_id = ph.company_id
WHERE c.is_active = true
GROUP BY c.company_id
HAVING MAX(ph.price_date) < CURRENT_DATE - INTERVAL '60 days'
    OR MAX(ph.price_date) IS NULL;
```

### 9.9 Graceful Shutdown — Validation

| Test | What it validates |
|------|-------------------|
| SIGTERM during idle → clean exit | No jobs running, exit code 0 |
| SIGTERM during active job → job lease persists | Running job left with status='running', lease expires naturally |
| SIGTERM with timeout → force exit after TimeoutStopSec | systemd sends SIGKILL after 300s |
| Double SIGTERM → no crash | Idempotent shutdown handlers |

### 9.10 Test Fixtures

To run data validation tests, the following fixtures are needed:

```python
# Pseudocode for test fixtures

@pytest.fixture
def seeded_test_db():
    """Set up test DB with known data for validation tests."""
    # Insert a known company: AAPL
    # Insert known super investors
    # Insert known price history with gaps
    yield db_connection
    # Clean up test data

@pytest.fixture
def mock_provider_with_fixtures():
    """Provider that returns known, deterministic data for testing."""
    # Returns 20 quarters of fake 13F data
    # Returns 5 years of daily OHLCV data
    # Returns 10 years of income statements
```

### 9.11 Test Coverage Goals

| Area | Coverage Target | Priority |
|------|----------------|----------|
| Scheduler lifecycle (start/stop) | 100% of classes | High |
| Data write paths (every `supabase.table().insert/update`) | 100% | High |
| Delta/share change computation | 100% of branches | High |
| Gap detection queries | 1 query per table | Medium |
| Idempotency (double-write prevention) | All upsert paths | Medium |
| Lock acquire/release contracts | Both success + failure paths | Medium |
| Job queue CTE | Race condition scenarios | High |
| Retry backoff | All failure classifications | Medium |
| Graceful shutdown | SIGTERM at idle + active | Medium |

---

## 10. Appendix: Current State vs Target Summary

| Aspect | v2 (Current) | v3 (Target) |
|--------|-------------|-------------|
| Job execution | Interval-driven inline | DB queue with claims + leases |
| Crash recovery | Work lost | Leases expire, work retries |
| Retry | None across cycles | Backoff schedule per failure type |
| Status endpoint | Static config | Runtime state from DB |
| Scheduler overlap | MarketData + Earnings independent | Unified `company_refresh` job |
| Aggregation locking | `aggregation_state` table | Same job queue + lease model |
| Per-company locks | TTL-based | Lease tokens + safe release |
| Worker monitoring | Logs only | Heartbeat table |
| Janitor | None | Reclaims expired leases |
| Manual replay | Restart process | Requeue via operator workflow (see §8) |
| Dead letter | None | Status after N retries |

---

## Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 3.1 | 2026-06-19 | Split current (v2) and target (v3) clearly; added atomic claim CTE, merge rules, retention policy, resource lock vs job lease clarification, aggregation through jobs, implementation roadmap, implementation notes, and comprehensive test plan with data validation SQL. | StockerPro Team |
| 3.0 | 2026-06-19 | Added DB-backed job queue, lease-based locking, runtime status, unified company refresh, janitor loop. | StockerPro Team |
| 2.0 | 2026-06-19 | Rewritten to reflect actual async worker implementation. | StockerPro Team |
| 1.0 | 2026-04-26 | Initial design (Celery + Redis, never implemented). | StockerPro Team |

---

**End of Document**
