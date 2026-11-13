# Data Freshness: Coverage Reconciliation and Monitoring

## StockerPro P1 Design

**Document Version:** 1.0
**Date:** 2026-09-05
**Author:** StockerPro Team
**Status:** PROPOSED

**Parent:** DATA_PIPELINE_ARCHITECTURE.md (index)
**Builds on:** BACKGROUND_SCHEDULER_DESIGN.md (v3 queue, workers, locks)

---

## 1. Problem

Two gaps in the current earnings freshness model:

1. **Full-coverage reconciliation is absent.** `_check_and_refresh_earnings`
   sweeps companies that are stale relative to the date-driven watermark
   (`_last_completed_quarter_start`), but the sweep is bounded by a batch cap
   and has no notion of "expected periods vs present periods". A company whose
   earlier periods are missing is never repaired by the quarterly sweep.
2. **Monitoring is thin.** `scheduler_state`, `scheduler_run_history`, and
   `worker_heartbeats` observe scheduler health, but there is no aggregate view
   of data coverage ("what fraction of active companies have statements through
   the last completed quarter").

## 2. Design

### 2.1 ReconciliationScheduler (new planner, 168h)

Periodicity: one `plan()` per week; enqueues work into the existing queue.

For each active company:
- Compute expected periods: the set of calendar quarter-end dates from the
  quarter containing `first_financial_data_loaded_at` through the last
  completed quarter (`_last_completed_quarter_start(today)`, inclusive).
- Compare against distinct `period_end` rows present in income statements
  (source of truth for period coverage).
- Missing periods -> enqueue `company_refresh` with:
  - `dedupe_key` matching the routine key format (merges with routine work via
    the existing scope/reason merge in `enqueue_job`), reason = "reconciliation".
  - payload `scopes=["financials"]`.
  - `not_before` = now (no backoff; reconciliation is low urgency, priority 20 -
    low band of the in-use ladder: aggregation 10 < valuation 20 < market_data 30
    < earnings 40 < portfolio_snapshot 50; 50 is the highest band, reserved for
    routine portfolio snapshots, not a repair path).

For each tracked super investor (parallel pass):
- Expected: last N quarters (N = `SUPER_INVESTORS_INITIAL_QUARTERS`).
- Compare against distinct `quarter_end_date` in `institutional_holdings`.
- Missing period without any holdings -> enqueue `investor_refresh`.

Honors existing `resource_locks` (PK resource_type+resource_id+lock_type):
- reconciliation uses lock_type `earnings_refresh` / `investor_refresh`,
  distinct from `market_data_refresh`, so no deadlock with market data;
  lock acquisition is fail-fast (skip if held).

This is the durable replacement for the manual `run_earnings_batch.py` script:
the weekly planner keeps coverage complete without a batch cap.

### 2.2 FreshnessMonitorScheduler (new planner, 24h)

`plan()` returns a single `freshness_snapshot` job (dedupe_key
`freshness_snapshot:{date}`) rather than writing inline - planners return jobs
and handlers write. The worker dispatches `handle_freshness_snapshot`, which
instantiates the scheduler and calls `snapshot()`:

Computes one snapshot per domain and appends to `freshness_snapshot`:

| domain | numerator | denominator |
|--------|-----------|-------------|
| financial_statements | distinct `period_end` quarter-end dates present in `income_statements` across active candidates (status INITIAL/PARTIAL/COMPLETE/CURRENT, `first_financial_data_loaded_at` set, security_type stock/null - the `get_stale_financial_companies` predicate) within the window from the earliest first-load quarter through the last completed quarter | the quarter-end dates of that window |
| institutional_holdings | distinct `quarter_end_date` values present in `institutional_holdings` (tracked investors) within the last `SUPER_INVESTORS_INITIAL_QUARTERS` quarters | the quarter-end dates of those quarters |

- Expected period = date-driven watermark (same `_last_completed_quarter_start`
  logic; on the 13F side, prior quarter end).
- If `pct < FRESHNESS_ALERT_THRESHOLD_PCT` -> `logger.error` with domain,
  expected period, and the specific missing companies/investors (bounded list).
- Snapshot rows are append-only for trend; readable by a future
  `/api/system/freshness` endpoint. Write is small (one row per domain per day)
  - no rate-limit concern.

### 2.3 Hardening (folded into P1)

- `set_identity`: `SuperInvestorsRefreshScheduler` must call
  `edgar.set_identity` defensively before any `get_filings` (today identity is
  only reached via `SuperInvestorsService.__init__._ensure_edgar_identity`;
  standalone runs risk an `IdentityNotSetException` swallowed by the blanket
  `except Exception` -> misleading "No filings found").
- `total_rows_upserted`: accumulate in `_check_and_refresh_earnings` cycle
  summary (currently initialized to 0 and never written).

## 3. Schema (new table, migration 008)

    CREATE TABLE IF NOT EXISTS freshness_snapshot (
        id              BIGSERIAL PRIMARY KEY,
        domain          TEXT NOT NULL,             -- 'financial_statements' | 'institutional_holdings'
        as_of           DATE NOT NULL,
        expected_period TEXT NOT NULL,             -- ISO 'YYYY-MM-DD'
        total           INT NOT NULL,
        covered         INT NOT NULL,
        pct             NUMERIC(5,2) NOT NULL,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (domain, as_of)                     -- one snapshot row per domain per day
    );
    CREATE INDEX IF NOT EXISTS idx_freshness_snapshot_domain_asof
        ON freshness_snapshot (domain, as_of DESC);

## 4. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Dedupe_key collision with routine enqueues | Use the routine key format so `enqueue_job` merges scopes/reasons (existing behavior, scheduler_repository.py:106-172); never a separate key for the same company |
| Lock contention with market_data refresh | Distinct lock_type per concern; fail-fast acquisition; reconciliation retries next cycle |
| Full-coverage query cost at scale | Expected-period set computed in SQL (date range vs distinct period_end); single query per cohort, not per company |
| Freshness monitor false positives during quarter rollover | Expected period is date-driven; a company is covered the moment its period_end set includes the watermark quarter - no timing race |

## 5. Verification (minimal executable evidence)

- Unit: coverage computation (expected vs present period set) - missing period
  detected, full coverage not enqueued.
- Unit: freshness pct math per domain; alert fires below threshold, silent above.
- Unit: `enqueue_job` merge - reconciliation reason merges into an existing
  pending routine job.
- Integration: `ReconciliationScheduler.plan()` returns only missing-period
  companies for a seeded DB; `FreshnessMonitorScheduler.snapshot()` appends rows.
- Migration: 008 applies and rolls back in a disposable environment.
- Run on dev DB: coverage report vs the ~98 known-stale companies.
