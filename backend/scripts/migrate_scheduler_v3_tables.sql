-- StockerPro v3 Scheduler Architecture — Control Plane Tables
-- Design: docs/BACKGROUND_SCHEDULER_DESIGN.md §4.1
-- Run this against your Supabase database (SQL editor or psql)

-- ============================================================================
-- 1. jobs — durable job queue
-- ============================================================================
CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        TEXT NOT NULL,          -- 'company_refresh', 'investor_refresh', 'aggregation_refresh'
    resource_type   TEXT,                   -- 'company', 'investor', 'aggregation'
    resource_id     TEXT,                   -- company_id, cik, 'sector_metric_agg'
    dedupe_key      TEXT NOT NULL,          -- unique logical key (see §4.4)
    priority        INT DEFAULT 50,         -- higher = more urgent
    status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'succeeded', 'dead_letter', 'cancelled')),
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_jobs_dedupe
    ON jobs (dedupe_key)
    WHERE status IN ('pending', 'running');

-- Workers claim next available job
CREATE INDEX IF NOT EXISTS idx_jobs_claim
    ON jobs (status, priority DESC, available_at ASC)
    WHERE status = 'pending';

-- ============================================================================
-- 2. job_attempts — attempt history per job
-- ============================================================================
CREATE TABLE IF NOT EXISTS job_attempts (
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

-- ============================================================================
-- 3. scheduler_state — one row per scheduler
-- ============================================================================
CREATE TABLE IF NOT EXISTS scheduler_state (
    scheduler_name  TEXT PRIMARY KEY,
    enabled         BOOLEAN DEFAULT TRUE,
    interval_hours  INT,
    last_planned_at TIMESTAMPTZ,
    last_status     TEXT,           -- 'succeeded' | 'failed'
    last_error      TEXT,
    next_due_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 4. scheduler_run_history — append-only planner cycle log
-- ============================================================================
CREATE TABLE IF NOT EXISTS scheduler_run_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheduler_name  TEXT NOT NULL,
    planned_at      TIMESTAMPTZ NOT NULL,
    jobs_enqueued   INT DEFAULT 0,
    status          TEXT,           -- 'succeeded' | 'failed'
    error           TEXT,
    duration_ms     INT
);

CREATE INDEX IF NOT EXISTS idx_run_history_scheduler
    ON scheduler_run_history (scheduler_name, planned_at DESC);

-- ============================================================================
-- 5. worker_heartbeats — worker liveness tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id   TEXT PRIMARY KEY,
    hostname    TEXT,
    pid         INT,
    started_at  TIMESTAMPTZ,
    last_hb_at  TIMESTAMPTZ DEFAULT NOW(),
    active_jobs INT DEFAULT 0
);

-- ============================================================================
-- 6. resource_locks — cross-job serialization
-- ============================================================================
CREATE TABLE IF NOT EXISTS resource_locks (
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

-- ============================================================================
-- 7. company_refresh_requests — scope accumulator for unified refresh
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_refresh_requests (
    company_id      INT NOT NULL,
    requested_at    TIMESTAMPTZ DEFAULT NOW(),
    scopes          TEXT[] NOT NULL,
    reasons         TEXT[] NOT NULL,
    priority        INT DEFAULT 50,
    processed       BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (company_id, requested_at)
);
