# Data Pipeline Architecture

## StockerPro Financial Data Freshness and Filings Architecture

**Document Version:** 1.0
**Date:** 2026-09-05
**Author:** StockerPro Team
**Status:** PROPOSED (pending implementation approval)

---

## 1. Purpose

Align the financial-data ingestion architecture with production-grade practices.
This index document maps the five gaps identified against the professional-app
analysis to per-feature design documents. It is deliberately small; each feature
has its own design doc and cross-references the v3 scheduler ADR.

## 2. The five gaps

| # | Gap | Feature doc | Phase |
|---|-----|-------------|-------|
| 1 | Event-driven filing push absent (pure polling) | FILINGS_WATCHER_DESIGN.md | P2 |
| 2 | Full-coverage reconciliation absent (only per-company stale sweep) | DATA_FRESHNESS_RECONCILIATION.md | P1 |
| 3 | Restatement reconciliation absent (period dedupe skips restatements) | RESTATEMENT_RECONCILIATION_DESIGN.md | P3 |
| 4 | 13F amendment handling shallow (no 13F-HR/A, no 13F-NT) | FILINGS_WATCHER_DESIGN.md | P2 |
| 5 | Freshness monitoring/alerting thin (no aggregate SLO view) | DATA_FRESHNESS_RECONCILIATION.md | P1 |

## 3. Document map

| Document | Scope |
|----------|-------|
| DATA_PIPELINE_ARCHITECTURE.md (this file) | Index, phasing, config, cross-refs |
| DATA_FRESHNESS_RECONCILIATION.md | P1: coverage reconciliation + freshness monitor + hardening |
| FILINGS_WATCHER_DESIGN.md | P2: event-driven 13F watcher, amendments (13F-HR/A), 13F-NT |
| RESTATEMENT_RECONCILIATION_DESIGN.md | P3: filing metadata, 45-day re-pull window, delta detection |

**References (existing):**
- `docs/BACKGROUND_SCHEDULER_DESIGN.md` (v3.1) - the DB-backed job queue ADR this design builds on.
- `docs/DATA_FRESHNESS_ANALYSIS.md` - baseline staleness analysis.
- `docs/SUPER_INVESTORS_CONFIG_DESIGN.md` - super-investor config origin.

## 4. Phasing

Dependency rule: a phase is independent when it introduces no new producers
that depend on another phase's state.

| Phase | Contents | Depends on |
|-------|----------|------------|
| P1 | Reconciliation + freshness monitor + hardening | nothing (foundation) |
| P2 | Filings watcher + 13F amendment/NT-aware fetch | P1 discipline only |
| P3 | Restatement metadata + re-pull | P2 filing-aware fetch for 13F side; earnings side independent |

Rationale: P1 delivers durable coverage (clears the ~98 stale companies without a
manual batch cap) and observability with zero provider changes. P2 adds the event
signal that makes freshness event-driven instead of calendar-guessed. P3 makes
restatements visible; its earnings-statement side can start in parallel with P2,
its 13F side needs P2's accession-targeted fetch.

## 5. Config additions (proposed)

| Key | Default | Phase |
|-----|---------|-------|
| ENABLE_RECONCILIATION_SCHEDULER | True | P1 |
| RECONCILIATION_INTERVAL_HOURS | 168 | P1 |
| ENABLE_FRESHNESS_MONITOR_SCHEDULER | True | P1 |
| FRESHNESS_ALERT_THRESHOLD_PCT | 95.0 | P1 |
| ENABLE_FILINGS_WATCHER_SCHEDULER | True | P2 |
| FILINGS_WATCH_INTERVAL_HOURS | 6 | P2 |
| FILINGS_WATCH_HR_GRACE_DAYS | 21 | P2 |
| ENABLE_RESTATEMENT_RECONCILIATION | True | P3 |
| RESTATEMENT_REFRESH_WINDOW_DAYS | 45 | P3 |

All follow the existing pydantic-settings pattern in `backend/config.py`
(strict Field patterns, ENABLE_* gate).

## 6. Worker registration (proposed)

Each new capability is a planner exposing `plan()` returning job dicts,
registered in `backend/scheduler_worker.py` alongside the existing planners
(super_investors 24h, market_data 24h, earnings 2h, portfolio_snapshot daily,
aggregation 24h, price_ingestion 1min, valuation 24h).

| Planner | Interval | Jobs enqueued |
|---------|----------|---------------|
| reconciliation | 168h | company_refresh (financials, reason=reconciliation) |
| freshness_monitor | 24h | freshness_snapshot job (dedupe_key freshness_snapshot:{date}, handler appends) |
| filings_watcher | 6h | investor_refresh (cik, accession, form) |

## 7. Out of scope (explicit)

- Price-data freshness parity (owned by price_ingestion scheduler).
- External alert routing (email/webhook) - logging to ERROR is the alert for now.
- EDGAR companyfacts XBRL ingestion to replace defeat-beta - future work.
