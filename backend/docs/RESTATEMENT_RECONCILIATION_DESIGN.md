# Restatement Reconciliation

## StockerPro P3 Design

**Document Version:** 1.0
**Date:** 2026-09-05
**Author:** StockerPro Team
**Status:** PROPOSED

**Parent:** DATA_PIPELINE_ARCHITECTURE.md (index)
**Builds on:** BACKGROUND_SCHEDULER_DESIGN.md, DATA_FRESHNESS_RECONCILIATION.md (P1), FILINGS_WATCHER_DESIGN.md (P2)

---

## 1. Problem

Financial statements are deduplicated by period: the refresh pipeline writes
rows for a `period_end` once, and the watermark
(`last_refreshed_fiscal_year/quarter`) prevents re-fetching that period. When a
company restates a quarter (amended 10-Q, 10-K/A, corrected XBRL), the corrected
values never reach the database - the period is "already fresh" by watermark.

The professional-grade behavior is: a period has a *last observed filing date*,
and a newer filing for the same period triggers a re-pull.

## 2. Design

### 2.1 financial_filing_metadata (new table)

One row per (company, period_end) recording when we last observed a filing for
that period and what we ingested:

    CREATE TABLE IF NOT EXISTS financial_filing_metadata (
        company_id       INT NOT NULL REFERENCES companies(company_id),
        period_end       DATE NOT NULL,
        last_filing_date DATE,
        last_ingested_at TIMESTAMPTZ DEFAULT NOW(),
        content_hash     TEXT,             -- optional, see 2.4
        source           TEXT,             -- 'defeat-beta' | 'yfinance'
        PRIMARY KEY (company_id, period_end)
    );

Written by the refresh pipeline whenever rows for a period are upserted
(companion to the statement writes, same transaction).

### 2.2 Restatement re-pull window

Config `RESTATEMENT_REFRESH_WINDOW_DAYS` (default 45): a period is eligible for a
*destination re-pull* while `period_end + window >= today`, even if the watermark
already covers it.

- Target set: companies with `period_end` inside the window, re-enqueued once
  per window (extra reason "restatement" on the existing dedupe_key,
  `not_before` spread to avoid thundering herd).
- Upsert semantics already handle overwrite: newer values replace stored rows.
- This catches the common restatement profile (corrections land within 4-8 weeks
  of the original filing); it is a bounded, low-frequency cost.
- **Provider filter bypass (critical):** the provider's incremental path strips
  any period strictly newer than the watermark before upsert
  (`_filter_to_new_data`, defeat_beta_provider.py:402-404/1893-1943), so a
  windowed re-pull of an already-covered period would be filtered out and the
  re-pull would be a silent no-op. Windowed re-pulls must call
  `get_all_financials_optimized(force_full_history=True, min_fiscal_year=
  <window start fiscal year>)` to bypass the incremental filter while bounding
  the fetch.

**Watermark guard (critical):** the watermark update after a windowed re-pull
must NOT advance `last_refreshed_fiscal_year/quarter` past the re-pulled period
in a way that masks the window. Rule: watermark only advances on a *period-
forward* refresh; a windowed re-pull (period already covered) refreshes row
values but does not move the watermark forward. Enforced in the metadata update
function (`update_company_refresh_metadata`). The computed watermark is also
monotonic: `max(existing watermark, latest observed period)`, never regresses.
The current implementation derives the latest period from
`income_statements.rows[-1]` (earnings_scheduler.py:449-451), which is
order-dependent and regresses to the current fiscal year (quarter=None) when a
refresh returns zero new statement rows.

### 2.3 Delta detection and logging

On a windowed re-pull, compare key material values (total_revenue, net_income)
before/after upsert. If changed materially (delta > 0.05%):
- log `WARNING` once per (company, period_end) with before/after,
- record source of truth in `financial_filing_metadata` (updated content_hash),
- do NOT create alert noise - logging is the record, freshness monitor reports
  coverage, not churn.

### 2.4 content_hash: decision

Include a content hash (over the statement rows for the period) as the compact
change detector instead of comparing values column-by-column. Cheap to compute,
unambiguous restatement signal. Value comparison (2.3) stays as the human-
readable log; hash is the programmatic signal.

### 2.5 13F side (rides on P2)

Investor restatements ARE 13F-HR/A amendments, handled structurally in P2
(FILINGS_WATCHER_DESIGN.md section 2.2): the watcher detects HR/A and the
accession-targeted fetch re-upserts the same quarter_end_date. P3's 13F work is
only: record the amendment in filing_watch_state (form = 13F-HR/A) for audit.

## 3. Config additions (proposed)

| Key | Default | Notes |
|-----|---------|-------|
| ENABLE_RESTATEMENT_RECONCILIATION | True | gate |
| RESTATEMENT_REFRESH_WINDOW_DAYS | 45 | re-pull eligibility window |

## 4. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Watermark advances past windowed period, masking future re-pulls | Guard rule in watermark update (2.2); unit-tested |
| Thundering herd at the 45-day boundary | `not_before` spread across the window; existing queue priority/dispatch already rate-limits via 5-worker pool |
| content_hash mismatch on formatting-only changes | Hash over canonical fields (period_end, statement rows keyed by line_item), not raw payload |
| Extra defeat-beta provider load | Bounded: one re-pull per company per 45-day window; window slides with watermark |
| Restatement never reflected (provider lag) | Windowed re-pull calls `get_all_financials_optimized(force_full_history=True, min_fiscal_year=<window start year>)` so the incremental filter cannot strip the covered period; re-pull re-observes the provider as of that date |

## 5. Verification (minimal executable evidence)

- Unit: window eligibility (period_end + 45 >= today -> eligible, else not).
- Unit: provider incremental filter strips covered periods (`_is_new_fiscal_period`
  false for an already-watermarked period -> `_filter_to_new_data` drops it);
  windowed re-pull escapes via `force_full_history=True` (red->green).
- Unit: watermark guard - windowed re-pull does not advance watermark; period-
  forward refresh does.
- Unit: content_hash stability - identical rows -> same hash; changed row ->
  different hash; delta log records before/after.
- Unit: enqueue reason "restatement" merges onto existing pending job (dedupe).
- Integration: seeded company with restated period -> re-pull -> rows updated,
  metadata row written, watermark unchanged.
- Migration: 010 applies and rolls back.
- Existing tests: full backend suite stays green (1706 collected; scheduler-area suite 169 pass).
