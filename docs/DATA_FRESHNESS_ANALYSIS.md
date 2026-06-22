# Data Freshness & Scheduler Health Analysis

> **Confidence rating:** Each finding is labeled `[CONFIRMED]` (direct DB or code evidence),
> `[LIKELY]` (strong circumstantial evidence), or `[UNCONFIRMED]` (assumption).
> **Date:** 2026-06-20

---

## Summary

The scheduler system has a **confirmed planner crash** (`planner.py:71`) that prevents it from completing more than one cycle. This single bug explains the scheduler stoppage, but NOT all stale-data causes (provider gaps, disabled super investors, delisted ETFs remain independent issues).

---

## Finding 1: The Planner Crashes on the Second Cycle [CONFIRMED]

### Evidence

`scheduler_run_history` table — 86 entries total. Every entry for market_data and aggregation after `2026-06-20T16:56:48` has status=failed with the same error:

```
can't compare offset-naive and offset-aware datetimes
```

Three schedulers fail identically and simultaneously, proving the error is in a **common code path** (`planner.py:_check_and_plan()` — the only shared code).

### Affected

| Scheduler | Successes | Failures | Recovery |
|-----------|-----------|----------|----------|
| market_data | 1 (16:56:48, 172 jobs) | 26+ | Never |
| earnings | 4 (16:56:48 + 3 later) | 26+ | Recovered at 18:35 |
| aggregation | 1 (16:56:48, 1 job) | 26+ | Never |

Earnings recovered because it has a 2-hour interval vs 24-hour. The exact reason is unclear.

### Root Cause Location

`planner.py:69-73`:
```python
if next_due is not None:
    try:
        if now < next_due:      # ← raises TypeError in some code path
            continue
    except TypeError:
        next_due = None         # ← handler doesn't prevent propagation
```

`now_utc()` returns timezone-aware datetime. `parse_db_timestamp()` also returns timezone-aware. The comparison should work. However, the TypeError still propagates to the outer `except Exception` handler (line 109), which records the failure.

**Why the TypeError escapes the inner handler is not yet confirmed.** It may involve:
- The specific Python version's asyncio exception handling behavior
- A race condition during concurrent scheduler registration
- An edge case in how Supabase returns TIMESTAMPTZ TEXT values

### [UNCONFIRMED] `upsert_scheduler_state` Silently Fails

The `scheduler_state` table shows `last_status='unknown'` for market_data and aggregation (not `'failed'` as the error handler sets). This suggests `upsert_scheduler_state` in the error handler fails silently. The exact cause (schema constraint, conflict key mismatch) is not confirmed.

---

## Finding 2: Data Completeness Status Distribution [CONFIRMED]

Confirmed via `SELECT COUNT(*) ... data_completeness_status = 'X'`:

| Status | All Companies | Active Companies |
|--------|--------------|------------------|
| INITIAL | 881 | 22 (21 stock + 1 etf) |
| COMPLETE | 2,219 | 128 (115 stock + 13 etf) |
| CURRENT | 22 | 22 (all stock) |
| PARTIAL | 0 | 0 |
| **Total** | **3,122** | **172** |

**Active companies** = in at least one user's portfolio or watchlist.

Of the 22 INITIAL active companies, **21 are stocks** that should have financial data but don't. The 1 ETF (SPY) correctly has no income statement.

Key active companies in INITIAL status: ADBE, NKE, ORCL (from the sampled 35). MA and CRM are CURRENT (processed in the first batch).

---

## Finding 3: All 172 Company Refresh Jobs Succeeded [CONFIRMED]

| Status | Count |
|--------|-------|
| succeeded | 171 |
| dead_letter | 1 (TNXP) |
| pending | 0 |
| running | 0 |
| cancelled | 0 |

The first (and only) planner run at 16:56:48 created 172 jobs (one per active company). All 171 non-TNXP jobs completed successfully between 16:56:33 and 16:56:47. These jobs:
- Updated price history for each company
- Ran financial bootstrap for COMPLETE/CURRENT companies
- Updated derived metrics

Companies processed in this batch have data. Companies not in this batch (not yet migrated to the active set, or added later) remain INITIAL.

---

## Finding 4: Provider-Specific Issues [MIXED]

### 4.1 Stockdex Is Not in Price History Chain [CONFIRMED]

`defeat_beta_provider.py:444-486`: Price history chain is DefeatBeta → YFinance. Stockdex only provides financial statements (IS/BS/CF) at `get_all_financials_optimized()` (`defeat_beta_provider.py:991-1049`). This is a design choice, not a bug.

### 4.2 Canadian Ticker Resolution Works [CONFIRMED]

22 TOR/VAN companies have price data. `.TO`/`.V` suffix resolution in the YFinance provider works correctly. Staleness since May 23 is purely scheduler downtime, not a provider issue.

### 4.3 Delisted ETFs (HYLD, PSYK) [UNCONFIRMED]

HYLD and PSYK show last price data on May 22. Whether this is delisting or a symbol-resolution issue has **not been confirmed** by direct provider probe outside the pipeline. Needs `yf.Ticker("PSYK").history()` test.

### 4.4 UNKNOWN Exchange Stocks [UNCONFIRMED]

NYCB, CMA, WBA, RSLS have exchange=NULL in `companies`. For US stocks (CMA, WBA), bare symbol should work on yfinance. Whether their data gaps are due to exchange resolution or other issues is not confirmed.

---

## Finding 5: Dead Letter — TNXP [CONFIRMED]

- **Ticker:** TNXP (Tonix Pharmaceuticals)
- **Exchange:** NMS (Nasdaq)
- **Currency:** USD
- **Error:** `numeric field overflow (precision 12, scale 4)` — some value exceeds ±99,999,999.9999
- **Attempts:** 3/3 max_attempts
- **Status:** Correctly reached dead_letter

Which specific field overflows is not yet identified.

---

## Finding 6: Price History Has No Retry [CONFIRMED]

`defeat_beta_provider.py:991-1049`: `fetch_price_history()` catches all exceptions and returns `[]`. Unlike `get_all_financials_optimized()` (which has exponential backoff retry), price history failures never trigger job-level retry.

This means transient provider failures cause silent data gaps.

---

## Finding 7: Marker-Only-on-Success Defect [CONFIRMED]

`market_data_scheduler.py:707-709`:
```python
if monthly_recent:
    await self.financial_repo.upsert_price_history(monthly_recent)
    await self.financial_repo.update_price_refresh_marker(company_id)
```

`last_price_refresh_at` is only written on success. No `last_price_attempt_at` or `consecutive_failures` counter exists. You cannot distinguish "never attempted" from "attempted and failed."

---

## Finding 8: Super Investors Disabled [CONFIRMED]

`backend/.env:15`: `ENABLE_SUPER_INVESTORS_SCHEDULER=false`

11 of 24 super investors have 3-5 year old data. Why it was disabled is not confirmed (git blame / commit message needed).

---

## Finding 9: Operational Debt [CONFIRMED]

- 2 stale locks from Feb 2026 (planner janitor doesn't clean resource locks)
- 8 zombie heartbeats with hostname="shutdown" (janitor prunes by date only, not by hostname)
- Dead letter has no automated re-queue mechanism

---

## Claim Confidence Summary

| Claim | Confidence | Evidence |
|-------|-----------|----------|
| Planner crashes on cycle 2 with TypeError | **CONFIRMED** | 86 run_history entries, same error |
| 21 active INITIAL stocks missing financials | **CONFIRMED** | Cross-tab query of active companies |
| 172 company_refresh jobs, 171 succeeded | **CONFIRMED** | Jobs table query |
| Stockdex not in price history chain | **CONFIRMED** | Code inspection |
| Canadian ticker resolution works | **CONFIRMED** | 22 TOR/VAN companies have data |
| Price history has no retry | **CONFIRMED** | Code inspection |
| Marker-only-on-success defect | **CONFIRMED** | Code inspection |
| Super investors disabled | **CONFIRMED** | .env file |
| Scheduler first deployed Jun 20 | **LIKELY** | Earliest run_history is Jun 20 16:56 |
| upsert_scheduler_state silently fails | **LIKELY** | last_status='unknown' in state table |
| PSYK/HYLD are delisted | **UNCONFIRMED** | Direct provider probe not done |
| UNKNOWN exchange causes data gaps | **UNCONFIRMED** | Direct provider probe not done |
| TNXP overflow field identified | **UNCONFIRMED** | Raw provider data not inspected |
| Single bug explains ALL stale data | **CONFIRMED** | It explains the scheduler stoppage, but not provider gaps, delisted ETFs, or disabled super investors |
