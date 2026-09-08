# Filings Watcher: Event-Driven 13F Ingestion

## StockerPro P2 Design

**Document Version:** 1.0
**Date:** 2026-09-05
**Author:** StockerPro Team
**Status:** PROPOSED

**Parent:** DATA_PIPELINE_ARCHITECTURE.md (index)
**Builds on:** BACKGROUND_SCHEDULER_DESIGN.md

---

## 1. Problem

Super-investor refresh is calendar-driven, not event-driven:

- `SuperInvestorsRefreshScheduler.plan()` only enqueues an investor when
  "today >= quarter end + 49 days grace" (`_calculate_next_due_date`).
- Fetches use `get_filings(year, form="13F-HR").filter(cik=...)` and process
  `filings[0]` - the single latest original filing.
- **13F-HR/A amendments are ignored** (form filter is exactly "13F-HR"), so a
  corrected filing never updates the stored quarter.
- **13F-NT notices are ignored**; the system learns about a filing only by
  calendar guesswork.
- A filing arriving early (or late) is not acted on; the system waits for the
  grace deadline.

A production-grade 13F tracker reacts to the filing, not the calendar.

## 2. Design

### 2.1 FilingsWatcherScheduler (new planner, 6h)

For each tracked CIK (from `SUPER_INVESTORS`):
- GET `https://data.sec.gov/submissions/CIK{10-digit}.json` (metadata only;
  same endpoint already proven for the Ackman/Einhorn verification).
- Read `filings.recent[]` (newest first); for each entry newer than
  `last_seen_filing_date`, classify form:
  | form | action |
  |------|--------|
  | 13F-HR | enqueue `investor_refresh` {cik, accession, form: "13F-HR"} |
  | 13F-HR/A | enqueue `investor_refresh` {cik, accession, form: "13F-HR/A"} |
  | 13F-NT | record in `filing_watch_state.hr_pending_since`; no enqueue |
- Advance cursor: set `last_seen_filing_date`/`last_seen_accession` to the
  newest processed filing, regardless of type (prevents reprocessing).
- Filter noise: ignore all other forms (D, 4, 8-K, etc.) by full-form match.

Cursor pitfalls handled:
- Two filings same day -> track `last_seen_accession` (not just date).
- `filings.recent` is capped by SEC; watcher only ever needs the newest M entries,
  the cursor only advances forward - no pagination walk required at 6h cadence.
- 13F-NT expectation: if `hr_pending_since` is set and no 13F-HR/HR-A for that
  period arrives within `FILINGS_WATCH_HR_GRACE_DAYS` (default 21):
  `logger.error` (missed/failed HR), clear the flag (do not block the cursor).

### 2.2 Handler change: accession-targeted fetch

`handle_investor_refresh` (scheduler_worker.py:157) currently calls
`_refresh_single_investor(cik, info)`. Extend:
- Payload carries `accession` + `form`.
- New `_fetch_filing_by_accession(cik, info, accession, form)` resolves the
  specific filing document, parses holdings, upserts (reuses
  `_save_holdings_to_db` unchanged - the write path already upserts on
  `holding_id`).
- `_refresh_single_investor` (calendar path) stays for backfill/legacy.
- Amendment behavior: 13F-HR/A upserts the same `quarter_end_date` - the stored
  row is overwritten with the amended values (existing upsert semantics).
- 13F-HR/A for a period whose holdings are missing entirely -> also covered by
  the existing self-heal check (`_holdings_exist_for_period`).

### 2.3 Identity hardening

`set_identity(settings.EDGAR_IDENTITY)` before any `get_filings`/document
resolution inside the scheduler (see P1 hardening).

## 3. Schema (new table, migration 009)

    CREATE TABLE IF NOT EXISTS filing_watch_state (
        cik                   TEXT PRIMARY KEY,   -- matches institutional_investors.cik
        last_seen_filing_date DATE NOT NULL,
        last_seen_accession   TEXT,
        last_seen_form        TEXT,
        hr_pending_since      DATE,               -- set on 13F-NT, cleared when HR observed
        updated_at            TIMESTAMPTZ DEFAULT NOW()
    );

Bootstrapped on first watch run per CIK from current `institutional_investors`
metadata (last_filed_period/date), not from scratch.

## 4. Config additions (proposed)

| Key | Default | Notes |
|-----|---------|-------|
| ENABLE_FILINGS_WATCHER_SCHEDULER | True | gate |
| FILINGS_WATCH_INTERVAL_HOURS | 6 | poll cadence |
| FILINGS_WATCH_HR_GRACE_DAYS | 21 | NT -> HR expectation window |

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| SEC submissions endpoint rate limits | metadata-only, small payload, 6h cadence, ~15 CIKs - far below limits; add exponential backoff on 4xx/5xx |
| Dedupe collision: watcher vs calendar plan() | Distinct keys (`investor_refresh:{cik}:{accession}` vs `investor_refresh:{cik}`); `enqueue_job` merges only on exact dedupe_key match (scheduler_repository.py:122-130), so no scope merge occurs - overlap is safe because a duplicate fetch upserts idempotently (holding_id) and `_holdings_exist_for_period` skips covered periods |
| HR/A reprocessing storms | Cursor advances on every processed form; an already-processed accession is never re-enqueued (dedupe on pending/running) |
| 13F-NT never followed by HR | hr_pending_since + grace alert; cursor does not wait |
| Identity unset in standalone runs | defensive set_identity in scheduler (P1 hardening) |

## 6. Verification (minimal executable evidence)

- Unit: form classification from a stubbed `filings.recent` payload (HR enqueues,
  A enqueues with same period, NT sets pending flag, noise skipped).
- Unit: cursor advancement (same-day filings, accession vs date ordering).
- Unit: `_fetch_filing_by_accession` resolves the exact accession (mock
  get_filings/doc resolution) and upserts the same quarter_end_date for HR/A.
- Integration: watcher dry-run against real CIKs (Ackman 0001336528, Einhorn
  0001079114 - known states) advances cursor without enqueueing stale work.
- Migration: 009 applies and rolls back.
- Existing tests: full backend suite stays green (1706 collected; scheduler-area suite 169 pass).
