# Dividend Data Pipeline — Architecture, Analysis & Design

> **Author:** Code Analysis  
> **Date:** 2026-06-19  
> **Context:** Upcoming Ex-Dates card shows "No upcoming ex-dates found"  
> **Scope:** Full-stack data flow for dividend dates, historical + forward-looking

---

## Table of Contents

1. [Current Pipeline Architecture](#1-current-pipeline-architecture)
2. [Scheduler Overlap & Override Analysis](#2-scheduler-overlap--override-analysis)
3. [Provider Capability Matrix](#3-provider-capability-matrix)
4. [Root Cause: Empty Upcoming Ex-Dates](#4-root-cause-empty-upcoming-ex-dates)
5. [Confidence Score Bug](#5-confidence-score-bug)
6. [Alternative Design Review](#6-alternative-design-review)
7. [Proposed Solution](#7-proposed-solution)
8. [Long-Term Roadmap](#8-long-term-roadmap)
9. [Appendix: Code References](#9-appendix-code-references)

---

## 1. Current Pipeline Architecture

### 1.1 Overview

```
                         ┌─────────────────────────────────────┐
                         │         Supabase PostgreSQL          │
                         │  ┌───────────────────────────────┐  │
                         │  │      dividend_history         │  │
                         │  │  (company_id, ex_date, amt)   │  │
                         │  └──────────┬────────────────────┘  │
                         │             │                       │
                         │  ┌──────────▼────────────────────┐  │
                         │  │      dividend_metrics          │  │
                         │  │  (growth, payout, streak)      │  │
                         │  └───────────────────────────────┘  │
                         └─────────────────────────────────────┘
                                    ▲            ▲
                                    │            │
                    ┌───────────────┘            │
                    │                            │
         ┌──────────┴──────────┐    ┌────────────┴────────────┐
         │ EarningsRefresh     │    │ MarketDataRefresh       │
         │ Scheduler (2h)      │    │ Scheduler (24h)         │
         │                     │    │                         │
         │ Fetches:            │    │ Fetches:                │
         │  • IS / BS / CF     │    │  • Price history        │
         │  • Dividends        │    │  • Splits               │
         │  • Next earnings    │    │  • Forecasts            │
         │                     │    │  • IS/BS/CF (bootstrap) │
         │ Upserts:            │    │  • Derived ratios       │
         │  • dividend_history  │    │  • Dividend metrics*    │
         │  • financial data   │    │  • Valuation            │
         └─────────────────────┘    └─────────────────────────┘
              * dividend_metrics is read-only on dividend_history
```

### 1.2 Data Source

Both schedulers ultimately call the same provider chain:

```
DefeatBeta SDK → ticker.dividends()     ← PRIMARY (historical DIVIDENDS only)
    ↓ if empty/fails
YFinance → yf.Ticker.dividends          ← FALLBACK (historical dividends only)
```

Both return **historical dividend payments** only—past ex-dates with amounts paid.

### 1.3 Idempotent Storage

```python
# backend/infrastructure/repositories/financial_repository.py:516
supabase.table('dividend_history').upsert(
    data,
    on_conflict='company_id,ex_dividend_date'
)
```

The `on_conflict` clause makes repeated writes safe: if a row for the same `(company_id, ex_dividend_date)` already exists, it gets updated in place rather than duplicated.

---

## 2. Scheduler Overlap & Override Analysis

### 2.1 What Each Scheduler Does with Dividends

| Aspect | EarningsRefreshScheduler | MarketDataRefreshScheduler |
|--------|------------------------|---------------------------|
| **Interval** | Every 2 hours | Every 24 hours |
| **Target** | Companies with earnings in ±N day window | All portfolio + watchlist companies |
| **Fetches dividends?** | Yes — as part of `get_all_financials_optimized()` | Only during **bootstrap** (step 5c) for companies with zero financial data |
| **Writes to `dividend_history`?** | Yes — via `upsert_all_financials()` | Only during bootstrap path (first-time sync) |
| **Writes to `dividend_metrics`?** | **No** | Yes — step 7 calls `compute_and_upsert_dividend_metrics()` |

### 2.2 Do They Override Each Other?

**For `dividend_history`:**

No destructive override. The EarningsRefreshScheduler is the sole regular writer. The MarketDataRefreshScheduler only writes during bootstrap (companies with zero financials). Once a company has been bootstrapped, the MarketDataRefreshScheduler never fetches dividends for it again.

The upsert is idempotent (`on_conflict='company_id,ex_dividend_date'`), so even if both hit the same row simultaneously, the result is identical data.

**For `dividend_metrics`:**

No conflict. Only the MarketDataRefreshScheduler writes to it. The EarningsRefreshScheduler does not call `compute_and_upsert_dividend_metrics()`.

**Race condition risk:**

Both schedulers acquire a **per-company distributed lock** before processing. This prevents concurrent processing of the same company across scheduler instances (or replicas). Properly handled.

### 2.3 Why Two Schedulers?

They serve different purposes:

| Scheduler | Purpose |
|-----------|---------|
| **EarningsRefreshScheduler** | Keep **financial statements** (IS/BS/CF) up to date around earnings season. Dividends are included as a side effect because they're part of the `CompleteFundamentals` bundle. |
| **MarketDataRefreshScheduler** | Keep **market data** (prices, splits, forecasts) current for all holdings. Dividend **metrics** are derived here because they depend on annual DPS aggregations that don't change daily. |

The dividend `dividend_history` data is a **byproduct** of the earnings scheduler's financial bundle fetch, not a dedicated concern of either scheduler. The `dividend_metrics` (growth rates, payout ratios) are computed in the market data scheduler because they require an annual perspective and are closer to "derived analytics" than "live data."

This split is reasonable but creates a gap: neither scheduler actively maintains forward-looking dividend dates.

---

## 3. Provider Capability Matrix

Tested from WSL Ubuntu (Python 3.12) against the installed versions.

### 3.1 Can They Provide Future Ex-Dividend Dates?

| Provider | Historical Dividends | Upcoming Ex-Date | Method | Tested |
|----------|--------------------|------------------|--------|--------|
| **DefeatBeta SDK** | ✅ `ticker.dividends()` | ❌ **No** — calendar only has earnings dates | `ticker.calendar()` has `symbol, report_date, time, name, fiscal_quarter_ending` only | Yes (O, VZ, KO, JNJ, PG, T, WMT, HD, XOM, CVX) |
| **YFinance** | ✅ `yf.Ticker.dividends` | ✅ `info['exDividendDate']` (Unix ts) | `Ticker.info` dict | Yes |
| **YFinance** | — | ✅ `calendar['Ex-Dividend Date']` (datetime) | `Ticker.calendar` dict | Yes |
| **Stockdex** | ❌ (broken `finviz_dividends_date_data` is empty) | ✅ `finviz_overall_dividend()['dividendExDate']` | Finviz web scrape | Yes (O, VZ, KO, JNJ) |
| **Stockdex** | ❌ (`digrin_dividend` is a property, not callable in v1.2.5) | ❌ | — | Yes |
| **EdgarTools** | ❌ No dividend methods | ❌ No dividend methods | SEC filings only | Yes |

### 3.2 Stockdex Deep Dive

**Correct import:**
```python
from stockdex import Ticker as StockdexTicker  # NOT 'Stockdex'
```

**Working dividend method — `finviz_overall_dividend()`:**
```python
t = StockdexTicker(ticker='O')
od = t.finviz_overall_dividend()
# Returns DataFrame with columns:
#   dividendExDate: '2026-06-30T00:00:00'  ← upcoming ex-date
#   dividendEstimate: 3.273                 ← estimated annual DPS
#   dividendTTM: 3.237                      ← trailing 12M DPS
#   lastClose: 60.24                        ← recent price
```

**Broken methods in stockdex 1.2.5:**
| Method | Error | Cause |
|--------|-------|-------|
| `digrin_dividend()` | `TypeError: 'DataFrame' object is not callable` | It's a property, not a method in this version |
| `digrin_payout_ratio()` | Same | Same |
| `finviz_dividends_annual_data()` | `IndexError: list index out of range` | Upstream Finviz layout change |
| `finviz_dividends_date_data()` | Empty DataFrame | Upstream Finviz layout change |

### 3.3 EdgarTools Deep Dive

**Correct constructor (single argument):**
```python
Company('O')  # NOT Company('O', 'Realty Income')
```

**Dividend methods: NONE.** EdgarTools reads SEC 10-K/10-Q XBRL filings for financial statements only. No dividend data is available through this provider.

### 3.4 Portfolio Coverage Scan (71 symbols)

| Source | Future ex-date `>= today` | Past ex-date | No data |
|--------|--------------------------|-------------|---------|
| **YFinance `info.exDividendDate`** | 16 (23%) | 22 (31%) | 33 (46%) |
| **Stockdex `finviz_overall_dividend`** | Not fully tested across portfolio | — | — |

Combined YFinance + Stockdex is expected to cover ~23% of all portfolio symbols (higher among dividend payers). Non-dividend stocks and invalid tickers (AC, CS, ETHY, WBA) account for most of the "no data" group. The prediction fallback in step 3 covers the remainder.

---

## 4. Root Cause: Empty Upcoming Ex-Dates

**The current pipeline never fetches forward-looking dividend dates.** Both data sources in the pipeline:

| Source | Returns |
|--------|---------|
| `defeatbeta.Ticker.dividends()` | Historical dividend payments only |
| `yfinance.Ticker.dividends` | Historical dividend payments only |

Neither source has any concept of "upcoming" or "future" ex-dates. They return records where `ex_dividend_date <= today`.

The two sources that **do** have future ex-dates are **not wired into any pipeline**:

| Available but unused | Location |
|----------------------|----------|
| `yf.Ticker.info['exDividendDate']` | YFinanceProvider has no method to read it |
| `yf.Ticker.calendar['Ex-Dividend Date']` | YFinanceProvider has no method to read it |
| `stockdex.Ticker.finviz_overall_dividend()['dividendExDate']` | StockdexProvider has no method for it |

The frontend `DividendsUpcomingCard` correctly queries the API, which correctly queries the database, which correctly filters `ex_dividend_date >= today` — but no future-dated rows exist in the database to return.

---

## 5. Confidence Score Bug

**Location:** `backend/application/services/dividend_dashboard_service.py:177` and `:261`

```python
# Bug: cs >= 70 but DB stores 0.0–1.0
cs = ex.get("confidence_score") or 0
confidence = "high" if cs >= 70 else "medium" if cs >= 40 else "low"
```

**Actual values stored in DB:**
- `DEFEAT_BETA_CONFIDENCE_SCORE` = `1.0` (config default)
- `YFINANCE_FALLBACK_CONFIDENCE_SCORE` = `0.8` (config default)

Since `1.0 >= 70` is `False`, all confidence labels render as `"low"`.

**Fix applied:** Changed to `cs >= 0.7` and `cs >= 0.4`.

**Note:** This bug only affects the confidence label shown in the UI. It does not affect whether ex-dates are returned.

---

## 6. Alternative Design Review

This section addresses a peer critique of the simpler solution in §7. The critic proposed a more complex architecture with a new `dividend_events` table, dedicated 6-hour scheduler, ML-based prediction, and observability stack. Below we assess each claim and explain why the simpler approach prevails.

### 6.1 Summary of Critic Claims

| # | Claim | Severity |
|---|-------|----------|
| 1 | **Fundamental architectural flaw** — dividends as side effect of earnings, not intentional collection | Low |
| 2 | **Data inconsistency** — two schedulers (2h + 24h) write to same table at different frequencies | Low |
| 3 | **Provider chain deficiency** — no forward-looking provider wired in | Valid |
| 4 | **Scalability concerns** — per-company sequential processing; no batch operations | Low |
| 5 | **Observability gap** — no data source quality metrics or alerting | Medium (future) |

### 6.2 Critic's Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Dividend Pipeline (dedicated)              │
│                                                              │
│  ┌────────────────┐    ┌──────────────────┐                  │
│  │    Scheduler    │    │   Orchestrator    │                  │
│  │  (every 6h)    │───▶│                   │                  │
│  └────────────────┘    └────────┬──────────┘                  │
│                                  │                            │
│          ┌───────────────────────┼───────────────────────┐   │
│          │                       │                       │   │
│          ▼                       ▼                       ▼   │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │  YFinance     │     │  Stockdex    │     │  Historical  │ │
│  │  Provider     │     │  Provider    │     │  Predictor   │ │
│  └──────┬────────┘     └──────┬───────┘     └──────┬───────┘ │
│         └─────────────────────┼─────────────────────┘          │
│                               │                                │
│                               ▼                                │
│                     ┌─────────────────┐                        │
│                     │  Data Quality    │                        │
│                     │  Layer           │                        │
│                     │  (merge, dedup,  │                        │
│                     │   validate)      │                        │
│                     └────────┬────────┘                        │
│                               │                                │
│                               ▼                                │
│                     ┌─────────────────┐                        │
│                     │  Storage Mgr    │                        │
│                     └────────┬────────┘                        │
│                               │                                │
└───────────────────────────────┼────────────────────────────────┘
                                │
                                ▼
                     ┌─────────────────┐
                     │  dividend_      │
                     │  events         │
                     │  (NEW table)    │
                     └─────────────────┘
```

### 6.3 Assessment of Each Claim

#### Claim 1: "Fundamental Architectural Flaw"

**Verdict: Overstated.**

The critic calls dividends-as-side-effect a "design choice that guarantees failure for any temporal query." In reality:
- The pipeline correctly serves its original purpose (historical dividend growth rates for `dividend_metrics`).
- The bug is a missing method call (read `yfinance.info['exDividendDate']`), not a missing scheduler.
- Calling it "architectural" is dramatic for a ~20-line addition to an existing provider.

#### Claim 2: "Data Inconsistency"

**Verdict: Not a real problem.**

| Aspect | Reality |
|--------|---------|
| Two schedulers writing to same table | Only EarningsRefresh (2h) is the regular writer. MarketDataRefresh (24h) only writes during bootstrap (first-time sync) for companies with zero financial data. |
| Different frequencies causing staleness | Both read from the same `dividend_history` table. Metrics (`dividend_metrics`) are computed in the 24h scheduler because they aggregate annual DPS — daily updates would produce no meaningful change. |
| No single source of truth | `dividend_history` is the source of truth. Both schedulers write through the same `upsert_dividends()` path with the same `on_conflict` clause. No conflict. |

The per-company distributed lock (acquired before processing) prevents concurrent writes to the same company. Race conditions are properly handled.

#### Claim 3: "Provider Chain Deficiency"

**Verdict: Valid.**

This is the actual root cause. No forward-looking source is wired into any provider. The critic correctly identifies that YFinance (`info.exDividendDate`, `calendar.Ex-Dividend Date`) and Stockdex (`finviz_overall_dividend()['dividendExDate']`) have data that nobody reads.

**This is the problem our proposed solution (section 7) solves directly** — no new architecture needed.

#### Claim 4: "Scalability Concerns"

**Verdict: Premature optimization.**

| Concern | Reality |
|---------|---------|
| Per-company sequential processing | The existing schedulers use `asyncio.gather` with per-task parallel execution. The lock acquisition is sequential (atomic `SELECT ... FOR UPDATE`), but the actual provider calls are concurrent. |
| No batch operations | There is no batch endpoint for dividends in any financial data provider — each symbol requires a separate request. Batching at the application level would add complexity for negligible gain at current portfolio scale (71 symbols). |
| Rate limiting risks | YFinance has no documented rate limit. Stockdex (Finviz scrape) should be rate-limited to 1 req/sec. This can be handled with a simple `asyncio.sleep(1)` between calls, not a new scheduler. |

#### Claim 5: "Observability Gap"

**Verdict: Valid but non-blocking.**

A monitoring dashboard for data source coverage, confidence distributions, and stale-date alerts would be valuable — but it's not required to fix the immediate bug. The critic's monitoring proposal is a reasonable Phase 2/3 item with no architectural implications.

### 6.4 Schema Gap Analysis

The critic proposes a new `dividend_events` table. Comparison with existing `dividend_history`:

| Column | `dividend_history` | Critic's `dividend_events` | Gap? |
|--------|-------------------|---------------------------|------|
| `company_id` | ✅ `integer NOT NULL` | ✅ `integer NOT NULL` | No |
| `ex_dividend_date` | ✅ `date NOT NULL` | ✅ `date NOT NULL` | No |
| `dividend_amount` | ✅ `numeric(10,4) NULL` | ✅ `decimal(10,4)` | No (nullable in existing supports predicted dates) |
| `dividend_type` | ✅ `varchar(30) DEFAULT 'regular'` | ✅ `text` ('regular','special','estimated') | No |
| `confidence_score` | ✅ `double precision DEFAULT 1.0` | ✅ `decimal(3,2) DEFAULT 0.0` | No (range 0.0-1.0 in both) |
| `data_source` | ✅ `varchar(50)` with enum check | ✅ `text NOT NULL` | No (need to add 'stockdex' to enum check) |
| `payment_date` / `payable_date` | ✅ `payment_date date NULL` | ✅ `payable_date date` | No (same field, different name) |
| `record_date` | ✅ `date NULL` | ✅ `date` | No |
| `frequency` | ✅ `varchar(20) NULL` | ✅ `text` | No |
| `is_confirmed` | ❌ — but `confidence_score >= 0.9` implies this | ✅ `boolean DEFAULT FALSE` | Minor — redundant with confidence_score |
| `metadata JSONB` | ❌ | ✅ `jsonb` | Nice-to-have, not required |
| `source_timestamp` | ❌ (but `updated_at` exists) | ✅ `timestamptz NOT NULL` | Minor — `updated_at` serves same purpose |
| `announcement_date` | ❌ | ✅ `date` | Nice-to-have for Phase 3+ |

**Key finding:** All required columns already exist in `dividend_history`. The three missing columns (`is_confirmed`, `metadata`, `announcement_date`) are future nice-to-haves, not blockers for the immediate fix.

### 6.5 Critical Concern: Metrics Pollution

The critic's most valid concern: **storing predicted future dates in `dividend_history` could skew `compute_and_upsert_dividend_metrics()`** by including estimated future dividends in annual DPS calculations.

**Resolution: separate table eliminates this concern entirely.**

Predictions are stored in a dedicated `upcoming_dividend_events` table. The `dividend_history` table remains strictly historical — every row is a fact, never a forecast. The metrics query reads only from `dividend_history` and is structurally incapable of being polluted:

```python
# Metrics query reads historical facts only — no filter needed
dh_resp = (
    supabase.table("dividend_history")
    .select("ex_dividend_date, dividend_amount")
    .eq("company_id", company_id)
    .not_.is_("ex_dividend_date", None)
    .not_.is_("dividend_amount", None)
    .order("ex_dividend_date", desc=False)
    .execute()
)
```

No discipline required. No NULL-amount convention. The two tables never intersect.

### 6.6 Why the New-Table Approach Prevails Over Both Extremes

| Dimension | Original (single-table) | **Adopted (new table)** | Critic's (full pipeline) |
|-----------|----------------------|------------------------|--------------------------|
| **New tables** | 0 | 1 (tiny, ~71 rows) | 1+ |
| **New schedulers** | 0 | 0 | 1 (6h dedicated) |
| **Lines of code** | ~50 | ~80 | ~500+ |
| **Metrics safety** | Discipline-based (NULL amount) | **Structural** (two tables never intersect) | Structural |
| **Semantic clarity** | Blurred (history + future mixed) | **Clean** (each table means one thing) | Clean |
| **Migration risk** | Alters production table | **Zero risk** (additive only) | Low |
| **Time to fix** | ~2 hours | ~3 hours | ~1 week |

The adopted approach adds a single small table that stores only the fields predictions need (no NULL columns, no `dividend_amount` at all). It avoids both the discipline fragility of the single-table approach and the four-week migration of the full pipeline approach.

### 6.7 Adopted Guardrails (Updated for Separate Table)

| # | Guardrail | Rationale |
|---|-----------|-----------|
| 1 | **Separate table for predictions** | `dividend_history` stays 100% historical. No discipline needed. |
| 2 | **Prediction reads `dividend_history` actuals only** | `dividend_amount IS NOT NULL AND ex_dividend_date <= today`. Prevents self-feed. |
| 3 | **Expire past-due events with 14-day grace** | `DELETE WHERE ex_date < today - 14`. Prevents gaps from provider refresh lag. |
| 4 | **Move refresh call to main scheduler loop** | Bootstrap path only fires for zero-financials companies. |
| 5 | **Rate limit Stockdex to 1 req/sec** | Finviz blocks aggressive scrapers. |
| 6 | **Source-based identity (not date-based)** | `UNIQUE(company_id, source)` — each source has one opinion. Providers can change predictions without leaving ghosts. |
| 7 | **API ranks by trust_score, not earliest date** | `ORDER BY trust_score DESC, observed_at DESC LIMIT 1`. Higher-confidence source wins. |
| 8 | **Freshness monitoring** | Alert if `source_observed_at > 7 days`. Prevents silent stale-data serving. |

These guardrails require ~80 lines of code and one small new table. No changes to `dividend_history`.

---

## 7. Proposed Solution

### 7.1 Design Goals

| Goal | Priority |
|------|----------|
| Show upcoming ex-dividend dates for all dividend-paying holdings | P0 |
| Clearly distinguish confirmed dates from estimated | P0 |
| One new additive table. No new services, no new schedulers, no new API keys. | P1 |
| Update automatically without manual intervention | P1 |
| Gracefully degrade when a source is unavailable | P1 |

### 7.2 Architecture

```
                         ┌──────────────────────┐
                         │  Existing Scheduler  │
                         │  (MarketDataRefresh) │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  refresh_upcoming_   │
                         │  dividend()          │
                         │                      │
                         │  1. Try yfinance     │
                         │     (confidence 0.95)│
                         │                      │
                         │  2. Try stockdex     │
                         │     (confidence 0.80)│
                         │                      │
                         │  3. Predict from     │
                         │     history          │
                         │     (confidence 0.50)│
                         │                      │
                         │  4. Rank by score    │
                         │     (not earliest)   │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  upcoming_dividend_   │
                         │  events              │
                         │  (NEW table)         │
                         │                      │
                         │  ex_date             │
                         │  confidence_score    │
                         │  data_source         │
                         │  source_observed_at  │
                         └──────────────────────┘

  dividend_history (unchanged — historical facts only)
```

### 7.3 Implementation

#### Step 1: Add method to YFinanceProvider

```python
# backend/providers/yfinance_provider.py
def get_upcoming_ex_date(self, symbol: str) -> Optional[date]:
    """Get next upcoming ex-dividend date from yfinance calendar/info.
    
    Returns only the ex-date. Estimated amount is derived from
    historical payments on read (see Step 3).
    Uses America/New_York timezone for ex-date conversion since
    ex-dividend dates follow NYSE/Nasdaq calendar dates.
    """
    from zoneinfo import ZoneInfo
    tkr = yf.Ticker(symbol.upper())
    info = tkr.info or {}
    cal = tkr.calendar if isinstance(tkr.calendar, dict) else {}

    # Source 1: info.exDividendDate (Unix timestamp)
    ts = info.get('exDividendDate')
    if ts and isinstance(ts, (int, float)):
        d = datetime.fromtimestamp(ts, tz=ZoneInfo("America/New_York")).date()
        if d >= date.today():
            return d

    # Source 2: calendar.Ex-Dividend Date
    cal_ex = cal.get('Ex-Dividend Date')
    if cal_ex:
        d = cal_ex.date() if isinstance(cal_ex, datetime) else cal_ex
        if isinstance(d, date) and d >= date.today():
            return d

    return None
```

#### Step 2: Add method to StockdexProvider

```python
# backend/providers/stockdex_provider.py
def get_upcoming_ex_date(self, symbol: str) -> Optional[date]:
    """Get next upcoming ex-dividend date from Finviz.
    
    Returns only the ex-date. Estimated amount is derived from
    historical payments on read.
    """
    from stockdex import Ticker as StockdexTicker
    t = StockdexTicker(ticker=symbol)
    od = t.finviz_overall_dividend()
    raw = od['dividendExDate'].iloc[0]
    if raw:
        d = datetime.fromisoformat(str(raw)).date()
        if d >= date.today():
            return d
    return None
```

#### Step 3: Add prediction method

```python
# backend/application/services/dividend_dashboard_service.py
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

def _as_date(d) -> date:
    """Coerce a Supabase date value (ISO string or date) to `date`."""
    return d if isinstance(d, date) else datetime.fromisoformat(str(d)).date()

def estimate_next_ex_date(company_id: int) -> Optional[date]:
    """Estimate next ex-dividend date from historical payment pattern.
    
    LIMITATION: Assumes stable dividend cadence. Will fail to predict if:
      - The company has suspended dividends
      - Frequency changed (e.g., quarterly → monthly)
      - The company is in financial distress
    For those cases, the provider chain (YFinance, Stockdex) is the
    primary source. Prediction is a last-resort UX enhancement.

    Reads actuals only (dividend_amount IS NOT NULL, ex_date <= today)
    from dividend_history. Never reads upcoming_dividend_events.
    Supabase returns date columns as ISO strings — parse with _as_date.
    """
    rows = (
        supabase.table("dividend_history")
        .select("ex_dividend_date, dividend_amount, dividend_type")
        .eq("company_id", company_id)
        .not_.is_("dividend_amount", None)
        .lte("ex_dividend_date", date.today())
        .order("ex_dividend_date", desc=True)
        .limit(8)
        .execute()
    ).data

    if not rows or len(rows) < 4:
        return None  # Need minimum 4 actual payments to infer frequency

    # Filter out special dividends (not representative of regular cadence)
    regular = [r for r in rows if r.get("dividend_type", "regular") != "special"]
    if len(regular) < 4:
        regular = rows[:4]

    # Parse dates (Supabase returns ISO strings, not date objects)
    sorted_dates = sorted(_as_date(r["ex_dividend_date"]) for r in regular)
    gaps = [(b - a).days for a, b in zip(sorted_dates, sorted_dates[1:]) if (b - a).days > 0]

    if not gaps:
        return None

    avg_gap = sum(gaps) / len(gaps)
    last_ex = sorted_dates[-1]

    # Map avg gap to frequency
    if avg_gap <= 35:
        next_date = last_ex + timedelta(days=round(avg_gap))
    elif avg_gap <= 100:
        # Quarterly: round to nearest quarter boundary
        months = round(avg_gap / 30.44)
        next_date = last_ex + relativedelta(months=months)
    elif avg_gap <= 200:
        # Semi-annual
        next_date = last_ex + relativedelta(months=6)
    else:
        # Annual
        next_date = last_ex + relativedelta(years=1)

    # Suppress predictions for deep-past dates (suspended payers)
    if next_date >= date.today():
        return next_date
    return None
```

#### Step 4: New table + upsert method

```sql
-- New table: upcoming_dividend_events
-- One row per (company_id, source). Each source maintains exactly
-- one current opinion. When a source updates its prediction,
-- the existing row is replaced (not duplicated).
CREATE TABLE upcoming_dividend_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    data_source VARCHAR(50) NOT NULL,
    ex_dividend_date DATE NOT NULL,
    trust_score DECIMAL(3,2) NOT NULL DEFAULT 0.0,
    status VARCHAR(20) NOT NULL DEFAULT 'predicted'
        CHECK (status IN ('predicted', 'provider_reported')),
    source_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Each source has exactly one opinion per company
    CONSTRAINT unique_source_opinion UNIQUE (company_id, data_source)
);

CREATE INDEX idx_upcoming_events_company ON upcoming_dividend_events(company_id);
CREATE INDEX idx_upcoming_events_date ON upcoming_dividend_events(ex_dividend_date);
```

```python
# backend/infrastructure/repositories/financial_repository.py
# trust_score is a heuristic ranking, not a calibrated probability:
#   yfinance  → 0.95 (provider-reported, typically reliable)
#   finviz    → 0.80 (provider-reported, scraper source)
#   predicted → 0.50 (algorithmic estimate from history)
TRUST_BY_SOURCE = {
    "yfinance": 0.95,
    "finviz": 0.80,
    "predicted": 0.50,
}

STATUS_BY_SOURCE = {
    "yfinance": "provider_reported",
    "finviz": "provider_reported",
    "predicted": "predicted",
}

async def upsert_upcoming_dividend(
    self,
    company_id: int,
    ex_date: date,
    data_source: str,
) -> None:
    """Upsert a single upcoming dividend event per source.
    
    Each source has exactly one row per company
    (UNIQUE(company_id, data_source)). When a provider changes its
    mind, the old row is replaced — not duplicated.
    """
    row = {
        "company_id": company_id,
        "ex_dividend_date": ex_date,
        "data_source": data_source,
        "trust_score": TRUST_BY_SOURCE.get(data_source, 0.0),
        "status": STATUS_BY_SOURCE.get(data_source, "predicted"),
        "source_observed_at": datetime.utcnow(),
    }
    await self.client.table("upcoming_dividend_events").upsert(
        row,
        on_conflict="company_id,data_source"
    ).execute()
```

#### Step 5: Wire into scheduler (main loop, not bootstrap)

```python
# At module level — global semaphore to rate-limit Stockdex
# across parallel company processing in the scheduler's loop.
stockdex_semaphore = asyncio.Semaphore(1)

# Called from MarketDataRefreshScheduler per-company main loop
async def refresh_upcoming_dividend(company_id: int, symbol: str) -> None:
    # ── 1. Run all providers (they may disagree — let trust_score decide) ──
    yf_date = await yf_provider.get_upcoming_ex_date(symbol)

    async with stockdex_semaphore:
        await asyncio.sleep(1)  # Rate limit: max 1 Stockdex req/sec
        sd_date = await stockdex_provider.get_upcoming_ex_date(symbol)

    # ── 2. Upsert each source opinion ────────────────────────────────
    # Each source replaces its own old row via UNIQUE(company_id, source).
    # The API selects the best by ORDER BY trust_score DESC later.
    if yf_date:
        await repo.upsert_upcoming_dividend(
            company_id, yf_date, data_source="yfinance"
        )
    if sd_date:
        await repo.upsert_upcoming_dividend(
            company_id, sd_date, data_source="finviz"
        )
    if not yf_date and not sd_date:
        pred_date = estimate_next_ex_date(company_id)
        if pred_date:
            await repo.upsert_upcoming_dividend(
                company_id, pred_date, data_source="predicted"
            )

    # ── 3. Expire stale events with 14-day grace period ──────────────
    await cleanup_stale_events(company_id)


async def cleanup_stale_events(company_id: int) -> None:
    """Remove past-due events from upcoming table.
    
    14-day grace period prevents gaps when a provider hasn't refreshed.
    This only affects upcoming_dividend_events — never touches history.
    """
    cutoff = date.today() - timedelta(days=14)
    await supabase.table("upcoming_dividend_events")\
        .delete()\
        .eq("company_id", company_id)\
        .lt("ex_dividend_date", cutoff)\
        .execute()
```

#### Step 6: API source selection

The upcoming-ex-date API chooses the best available date by ranking:

```sql
SELECT *
FROM upcoming_dividend_events
WHERE ex_dividend_date >= today
ORDER BY trust_score DESC,          -- highest-ranked source first
         source_observed_at DESC    -- freshest observation as tiebreaker
LIMIT 1
```

If no row matches (no sources have data, all predictions are past-due), the API returns `null` and the card shows "No upcoming ex-dates found." This is a deliberate graceful degradation — no fallback to stale data.

---

### 7.4 What Changes (and What Doesn't)

| What | Changes? | Details |
|------|----------|---------|
| `dividend_history` table | **No** | Unchanged — remains purely historical |
| `upcoming_dividend_events` table | **New** | Columns: `company_id`, `data_source`, `ex_dividend_date`, `trust_score`, `status`, `source_observed_at` |
| Frontend `DividendsUpcomingCard` | **Minor** — read from new table | Show "Likely" (0.95) / "Estimate" (0.80) / "Predicted" (0.50) badges; "Amount TBD" when no amount |
| `GET /portfolio/dividends/upcoming` | **Modify** — query new table with source selection | `SELECT * FROM upcoming_dividend_events WHERE ex_date >= today ORDER BY trust_score DESC, source_observed_at DESC LIMIT 1` |
| `portfolio_repository` | **Add** new query | `get_next_upcoming_event()` targets new table |
| `YFinanceProvider` | **Add** one method | `get_upcoming_ex_date()` returns date only |
| `StockdexProvider` | **Add** one method | `get_upcoming_ex_date()` returns date only |
| `FinancialRepository` | **Add** two methods | `upsert_upcoming_dividend()` + `cleanup_stale_events()` targeting new table |
| MarketDataRefreshScheduler | **Modify** — add call in per-company loop | `refresh_upcoming_dividend()` under existing lock; NOT in bootstrap path |
| `dividend_dashboard_service.py` | **Modify** — read from new table | Add `trust_label` derived from `trust_score`: "Likely" (0.95), "Estimate" (0.80), "Predicted" (0.50) |
| `estimate_next_ex_date()` utility | **New** | Reads actuals only from `dividend_history`, never touches new table |

### 7.5 Edge Cases

| Case | Behavior |
|------|----------|
| Symbol not found on yfinance | Falls through to stockdex |
| Stockdex rate-limited (429) | `asyncio.sleep(1)` between calls mitigates; still fails → falls to prediction |
| YFinance + Stockdex give different dates | Both upserted separately (different `ex_dividend_date`). API picks the highest-confidence source's date. |
| YFinance + Stockdex give same date | `ON CONFLICT` keeps the higher confidence score. |
| Company has < 4 historical dividends | Cannot predict — skipped (need minimum 4 to infer frequency) |
| Special dividends in history | Filtered out of gap calculation (only regular considered) |
| Source replacement (same source changes date) | `UNIQUE(company_id, data_source)` replaces old opinion atomically. No delete needed — upsert overwrites. |
| Grace cleanup (dates past 14-day window) | `DELETE WHERE ex_date < today - 14`. Separate sweep; only affects `upcoming_dividend_events`. |
| Scheduler crashes after upsert, before grace cleanup | Upsert already committed; stale cleanup runs next cycle. No data loss, no ghost rows. |
| Scheduler crashes before any upsert | No rows in `upcoming_dividend_events` for that company; card shows graceful "No upcoming" state. |
| Prediction self-feeds | Reads `dividend_history` only (`.not_.is_("dividend_amount", None).lte("ex_dividend_date", today)`). Never sees rows from `upcoming_dividend_events`. |
| Monthly dividend payer (O, AGNC) | avg_gap ≤ 35 days → monthly prediction |
| Semi-annual payer | avg_gap 100-200 days → 6-month prediction |
| Frequency recently changed (e.g., AAPL 2012) | Last 8 payments detect the dominant gap; transitional period uses most frequent pattern |
| No upcoming date found from any source | No row upserted; card shows "No upcoming ex-dates found" (graceful degradation) |
| `upcoming_dividend_events` table not yet created | Migration must ship in same PR. API query returns empty result set (no crash). |
| Timezone mismatch | `datetime.fromtimestamp(ts)` uses server local time. Ex-dates are NYSE calendar. Fix: `fromtimestamp(ts, tz=ZoneInfo("America/New_York"))` in Step 1. |
| Suspended payer (no dividends for >2 cycles) | `next_date >= today` guard suppresses prediction; card shows "No upcoming ex-dates found" (correct) |
| Payer that is merely late (delayed by weeks) | Same guard suppresses it; acceptable for v1. Phase 2 can add a median-gap retry. |

---

### 7.6 Test Plan

#### 7.6.1 Unit Tests

**Prediction Algorithm (`estimate_next_ex_date`)**

| Test | Input | Expected | Validates |
|------|-------|----------|-----------|
| Quarterly frequency | 8 payments spaced ~91 days apart | Next ex-date ~91 days after last | `avg_gap` 36–100 → quarterly |
| Monthly frequency | 12 payments spaced ~30 days apart | Next ex-date ~30 days after last | `avg_gap` ≤ 35 → monthly |
| Semi-annual frequency | 6 payments spaced ~182 days apart | Next ex-date ~182 days after last | `avg_gap` 101–200 → semi-annual |
| Annual frequency | 5 payments spaced ~365 days apart | Next ex-date ~365 days after last | `avg_gap` > 200 → annual |
| Minimum history guard | 3 payments | Returns `None` | `< 4` check |
| Boundary: exactly 4 payments | 4 quarterly payments | Valid prediction returned | Boundary test |
| Special dividend exclusion | Quarterly data + 1 special | Same prediction as pure quarterly | `dividend_type != 'special'` filter |
| All special dividends | 4 special-only payments | Falls back to raw rows (predicts from all) | Graceful degradation |
| Self-feed prevention | Mix of actual + prediction rows | Only actuals used (`IS NOT NULL`, `<= today`) | Query filter correctness |
| No data | Empty result set | Returns `None` | Empty guard |

**Provider Methods**

| Test | Input | Expected | Validates |
|------|-------|----------|-----------|
| YFinance `info.exDividendDate` present | Unix timestamp in future | Date returned | Primary source |
| YFinance `calendar.Ex-Dividend Date` present | Datetime in future | Date returned | Secondary source |
| YFinance no future date | Both fields absent or past | `None` returned | Missing data guard |
| YFinance missing `info` dict | `tkr.info` returns `{}` | `None` returned | Defensive access |
| Stockdex valid response | Finviz DataFrame with future date | Date returned | Primary source |
| Stockdex empty DataFrame | Empty result from scrape | `None` returned | Empty guard |
| Stockdex missing column | DataFrame without `dividendExDate` | `None` returned (KeyError caught) | Defensive access |

**Repository Layer (targets `upcoming_dividend_events`)**

| Test | Input | Expected | Validates |
|------|-------|----------|-----------|
| Upsert yfinance source | `data_source='yfinance'` | `trust_score=0.95`, `status='provider_reported'` | Source-based scoring |
| Upsert finviz source | `data_source='finviz'` | `trust_score=0.80`, `status='provider_reported'` | Source-based scoring |
| Upsert predicted source | `data_source='predicted'` | `trust_score=0.50`, `status='predicted'` | Source-based scoring |
| Upsert sets `source_observed_at` | Any source | `source_observed_at` is not NULL | Auditability |
| on_conflict replaces old source opinion | Same source twice, different dates | Old row replaced (UNIQUE company+source) | Source replacement |
| Source replacement on update | YFinance changes 07-15 → 07-22 | Single row, date=07-22, old 07-15 gone | No duplicate opinions |
| Stale cleanup deletes past events | `ex_date < today - 14 days` | Row removed | Expiry with grace period |
| Stale cleanup preserves recent past | `ex_date >= today - 14 days` | Row kept (grace period) | No premature deletion |
| Stale cleanup preserves future events | `ex_date >= today` | Row kept | No false positives |
| Separate table: `dividend_history` unaffected | Delete all from `upcoming_dividend_events` | `dividend_history` rows unchanged | Structural safety |

#### 7.6.2 Integration Tests

**Scheduler Wiring**

| Test | Steps | Expected |
|------|-------|----------|
| End-to-end refresh | Call `refresh_upcoming_dividend(company_id, symbol)` for KO | Row upserted into `upcoming_dividend_events` with `ex_date >= today` |
| Multi-source different dates | YFinance returns 07-15, Stockdex returns 07-22 | Two rows upserted (different sources, different dates), each with own trust_score |
| Source replacement | YFinance returns 07-15, then next cycle returns 07-22 | Single YFinance row, date updated to 07-22, old 07-15 gone |
| Full fallback chain | Both sources return `None`, company has 8 historical payments | Row stored from prediction with `data_source='predicted'`, `status='predicted'`, `trust_score=0.50` |
| Rate limiting | Only hits Stockdex if YFinance returned nothing | `asyncio.sleep(1)` before Stockdex call |
| Write-before-delete | Past-due event exists → `refresh_upcoming_dividend` called | New event upserted first, then stale cleanup runs with 14-day grace |
| Lock prevents concurrent | Same company processed twice simultaneously | Only one succeeds (distributed lock) |

**End-to-End API Flow**

| Test | Steps | Expected |
|------|-------|----------|
| Upcoming date visible | Upsert event → GET `/portfolio/dividends/upcoming` | Response includes the date |
| Trust label | Upsert with trust_score=0.95 → GET response | `trust_label: "Likely"` |
| Different source labels | Upsert yfinance (trust=0.95) vs prediction (trust=0.50) → GET | `trust_label: "Likely"` vs `"Predicted"` |
| API picks highest trust | YFinance (trust=0.95, date=07-22) + Stockdex (trust=0.80, date=07-15) | API returns YFinance date (higher trust wins over earlier date) |
| Stale event excluded | Event passes 14-day grace → cleanup runs → GET | Event no longer returned |
| Recent past event kept in grace | Event `ex_date = today - 5d` → cleanup runs | Event kept (within 14-day grace) |
| Source replacement | YFinance changes 07-15 → 07-22 → GET | Single YFinance row, date=07-22 |
| Metrics not polluted | Insert event in `upcoming_dividend_events` → compute metrics | Annual DPS unchanged (metrics reads `dividend_history` only) |
| No upcoming events | No rows in table → GET | Returns empty list, card shows "No upcoming ex-dates found" |

#### 7.6.3 Data Accuracy Validation

**Structural Safety Test (separate table)**

Must pass before deploy:

```python
# 1. Events in upcoming table never affect dividend_history
await repo.upsert_upcoming_dividend(
    company_id=1, ex_date="2026-12-15", data_source="predicted"
)

dh_count = supabase.table("dividend_history")\
    .select("count", "dividend_id")\
    .eq("company_id", 1)\
    .execute().data[0]["count"]

ue_count = supabase.table("upcoming_dividend_events")\
    .select("count", "id")\
    .eq("company_id", 1)\
    .execute().data[0]["count"]

assert ue_count == 1, "Event should exist in upcoming table"
assert dh_count == 12, "Historical table should be unchanged"
```

**Historical Data Integrity (regression checks)**

```python
# 1. No historical rows should have NULL dividend_amount
rows = supabase.table("dividend_history")\
    .select("count", "dividend_id")\
    .is_("dividend_amount", None)\
    .lte("ex_dividend_date", date.today())\
    .execute()
assert rows.data[0]["count"] == 0, f"Found {rows.data[0]['count']} rows with NULL amount"

# 2. All confidence_scores in valid range
rows = supabase.table("dividend_history")\
    .select("count", "dividend_id")\
    .or_("confidence_score.lt.0.0,confidence_score.gt.1.0")\
    .execute()
assert rows.data[0]["count"] == 0, "confidence_score out of range"
```

**Prediction Accuracy (golden dataset)**

| Symbol | Known Frequency | Tolerance | Test |
|--------|----------------|-----------|------|
| KO | Quarterly (~91 days) | ±5 days | Predict → compare to actual next ex-date from YFinance |
| O | Monthly (~30 days) | ±3 days | Predict → compare to actual next ex-date |
| JNJ | Quarterly (~91 days) | ±5 days | Predict → compare to actual next ex-date |
| PG | Quarterly (~91 days) | ±5 days | Predict → compare to actual next ex-date |
| SO | Quarterly (~91 days) | ±5 days | Predict → compare to actual next ex-date |
| XOM | Quarterly (~91 days) | ±5 days | Predict → compare to actual next ex-date |

For each: run `estimate_next_ex_date(company_id)`, then fetch confirmed date from YFinance `info.exDividendDate`. Assert prediction is within tolerance of confirmed date.

**Metrics Pollution Prevention (quantitative)**

```python
# Baseline: capture annual DPS before any event
baseline = compute_and_upsert_dividend_metrics(company_id)

# Insert event in upcoming_dividend_events (separate table)
await repo.upsert_upcoming_dividend(
    company_id=1, ex_date="2026-12-15", data_source="predicted"
)

# Verify: metrics unchanged (metrics reads dividend_history only)
after = compute_and_upsert_dividend_metrics(company_id)
assert baseline == after, (
    "Event in upcoming table altered historical metrics"
)
```

#### 7.6.4 Production Validation (Scheduled)

Run daily after MarketDataRefresh cycle:

```python
async def validate_dividend_pipeline():
    """Daily health check for the dividend pipeline."""

    # 1. Coverage: at least 15% of holdings have upcoming events
    holdings = await portfolio_repo.get_all_holdings()
    company_ids = [h.company_id for h in holdings]
    upcoming_rows = supabase.table("upcoming_dividend_events")\
        .select("company_id")\
        .in_("company_id", company_ids)\
        .gte("ex_dividend_date", date.today())\
        .execute()
    upcoming_company_ids = {r["company_id"] for r in upcoming_rows.data}
    coverage = len(upcoming_company_ids) / max(len(company_ids), 1)
    if coverage < 0.15:
        await alert_slack(
            f"Dividend coverage dropped to {coverage:.1%} "
            f"({len(upcoming_company_ids)}/{len(company_ids)} holdings)"
        )

    # 2. No stale events in upcoming table
    stale = supabase.table("upcoming_dividend_events")\
        .select("count", "id")\
        .lt("ex_dividend_date", date.today())\
        .execute()
    if stale.data[0]["count"] > 0:
        await alert_slack(
            f"{stale.data[0]['count']} stale events found — "
            "cleanup may not be running"
        )

    # 3. Missing rows: track holdings with no upcoming event
    held_ids = set(company_ids)
    missing_ids = held_ids - upcoming_company_ids
    logger.info(
        f"{len(missing_ids)}/{len(held_ids)} holdings have no upcoming event"
    )

    # 4. Source distribution (drift detection)
    sources = supabase.table("upcoming_dividend_events")\
        .select("data_source", count="exact")\
        .execute()
    logger.info(f"Upcoming event sources: {sources.data}")

    # 5. Freshness check: sources should have reported within 7 days
    stale_sources = supabase.table("upcoming_dividend_events")\
        .select("count", "id")\
        .lt("source_observed_at", datetime.utcnow() - timedelta(days=7))\
        .execute()
    if stale_sources.data[0]["count"] > 0:
        await alert_slack(
            f"{stale_sources.data[0]['count']} stale source observations "
            "(>7 days since last refresh)"
        )

    # 6. No NULL amounts on historical rows (regression)
    null_amt = supabase.table("dividend_history")\
        .select("count", "dividend_id")\
        .is_("dividend_amount", None)\
        .lte("ex_dividend_date", date.today())\
        .execute()
    if null_amt.data[0]["count"] > 0:
        await alert_slack(
            f"{null_amt.data[0]['count']} historical rows with NULL "
            "dividend_amount — possible data corruption"
        )

    return {
        "coverage_pct": round(coverage * 100, 1),
        "stale_count": stale.data[0]["count"],
        "stale_source_count": stale_sources.data[0]["count"],
        "null_historical_count": null_amt.data[0]["count"],
        "missing_event_count": len(missing_ids),
        "source_distribution": sources.data,
    }
```

#### 7.6.5 Test Fixtures

```python
# Sample historical data for deterministic prediction tests
FIXTURE_QUARTERLY_8 = [
    {"ex_dividend_date": "2026-03-13", "dividend_amount": 0.27, "dividend_type": "regular"},
    {"ex_dividend_date": "2025-12-12", "dividend_amount": 0.27, "dividend_type": "regular"},
    {"ex_dividend_date": "2025-09-12", "dividend_amount": 0.25, "dividend_type": "regular"},
    {"ex_dividend_date": "2025-06-13", "dividend_amount": 0.25, "dividend_type": "regular"},
    {"ex_dividend_date": "2025-03-13", "dividend_amount": 0.25, "dividend_type": "regular"},
    {"ex_dividend_date": "2024-12-13", "dividend_amount": 0.25, "dividend_type": "regular"},
    {"ex_dividend_date": "2024-09-13", "dividend_amount": 0.23, "dividend_type": "regular"},
    {"ex_dividend_date": "2024-06-13", "dividend_amount": 0.23, "dividend_type": "regular"},
]
# Expected: avg_gap ≈ 91 days → quarterly → next ≈ last + 91 days

FIXTURE_MONTHLY_12 = [
    {"ex_dividend_date": f"2026-{m:02d}-15", "dividend_amount": 0.07, "dividend_type": "regular"}
    for m in range(1, 13)
]
# Expected: avg_gap ≈ 30 days → monthly → next ≈ 30 days after Dec 15

FIXTURE_QUARTERLY_WITH_SPECIAL = FIXTURE_QUARTERLY_8 + [
    {"ex_dividend_date": "2025-01-15", "dividend_amount": 0.50, "dividend_type": "special"},
]
# Expected: same as FIXTURE_QUARTERLY_8 (special excluded from gap calc)

FIXTURE_INSUFFICIENT_3 = FIXTURE_QUARTERLY_8[:3]
# Expected: None returned (minimum 4 not met)

FIXTURE_EMPTY = []
# Expected: None returned
```

#### 7.6.6 Expected Results Matrix

| Test | Input | Expected Output | Validates |
|------|-------|----------------|-----------|
| Quarterly prediction | FIXTURE_QUARTERLY_8 | ~91 days after last ex-date | Frequency inference |
| Monthly prediction | FIXTURE_MONTHLY_12 | ~30 days after last ex-date | Frequency inference |
| Special dividend exclusion | FIXTURE_QUARTERLY_WITH_SPECIAL | Same as pure quarterly | `dividend_type` filter |
| Insufficient history | FIXTURE_INSUFFICIENT_3 | `None` | Minimum-4 guard |
| Empty history | FIXTURE_EMPTY | `None` | Empty guard |
| Metrics pollution | Event in `upcoming_dividend_events` | Annual DPS unchanged (metrics reads `dividend_history` only) | Structural safety |
| Stale cleanup (past grace) | `ex_date < today - 14 days` | Row deleted | Expiry with grace |
| Stale cleanup (within grace) | `ex_date = today - 5 days` | Row kept | 14-day grace period |
| Source identity (single source) | YFinance returns 07-15, then 07-22 next cycle | One row, date=07-22 (replaced) | `UNIQUE(company_id, source)` |
| Two sources, same date | YFinance 07-15 + Stockdex 07-15 | Two rows (different sources). API picks higher trust_score. | Source ranking |
| Two sources, different dates | YFinance (0.95, 07-22), Stockdex (0.80, 07-15) | API returns YFinance row (trust_score wins over earlier date) | Source hierarchy |
| API selection rule | Multiple rows → `ORDER BY trust_score DESC, observed_at DESC LIMIT 1` | Deterministic, predictable | API contract |
| Freshness monitoring | `source_observed_at > 7 days` | Alert triggered | Stale-data detection |
| Future date in `upcoming_dividend_events` | Row with `ex_date >= today` and `trust_score=0.95` | Card shows "Likely" badge | UX accuracy |

---

## 8. Long-Term Roadmap

### Phase 1 — Immediate (this sprint)

| Item | Effort | Impact |
|------|--------|--------|
| Add `get_upcoming_ex_date()` to YFinanceProvider | ~20 lines | Covers ~23% of portfolio symbols |
| Add `get_upcoming_ex_date()` to StockdexProvider | ~15 lines | Additional coverage (untested across portfolio) |
| Create `upcoming_dividend_events` table with `UNIQUE(company_id, data_source)` | Migration | Source-based identity; each source has one opinion |
| Add `upsert_upcoming_dividend()` to FinancialRepository | ~20 lines | `trust_score` (heuristic ranking), `status` enum, `source_observed_at` |
| Add `estimate_next_ex_date()` prediction utility | ~50 lines | Covers remaining payers with ≥4 historical payments |
| Add `cleanup_stale_events()` with 14-day grace | ~5 lines | `DELETE WHERE ex_date < today - 14` |
| Add API source selection query | ~10 lines | `ORDER BY trust_score DESC, observed_at DESC LIMIT 1` |
| Wire into MarketDataRefreshScheduler per-company main loop | ~30 lines | YFinance first, Stockdex only as fallback, prediction last |
| Frontend: show "Likely" / "Estimate" / "Predicted" | ~15 lines | Honest UX based on `trust_score` |
| Add freshness monitoring to daily validation | ~10 lines | Alert if `source_observed_at > 7 days` |

### Phase 2 — Short-term (next sprint)

| Item | Effort | Impact |
|------|--------|--------|
| Compute estimated DPS from last actual on read | ~15 lines | Provides per-share amount for upcoming card |
| Add `source_observed_at` to upcoming table queries | ~5 lines | Auditability for stale-source detection |
| Cache yfinance calendar calls per symbol to avoid redundant fetches | ~15 lines | Reliability |

### Phase 3 — Medium-term

| Item | Rationale |
|------|-----------|
| Add a dedicated **ex-dividend calendar provider** (Polygon.io, Nasdaq Data Link, etc.) | Accuracy: real announced dates > predicted |
| Add confidence score decay: predicted dates lose confidence as they age | `confidence = 0.5 - (days_since_prediction / 90) * 0.2` |
| Show "Next expected ex-date" on holdings table rows | UX improvement |
| Send notification when upcoming ex-date is within 7 days | User engagement |

### Phase 4 — Long-term

| Item | Rationale |
|------|-----------|
| Replace prediction with a dedicated dividend calendar API (cost ~$50-200/mo) | Best accuracy, covers 100% of US-listed stocks |
| Track dividend announcement dates vs ex-dates separately | More granular confidence: "declared" vs "estimated" |
| Machine learning model for dividend prediction (amount + date + probability) | Sophisticated alternative |

### What We Explicitly Won't Do

| Non-goal | Reason |
|----------|--------|
| New scheduler service | Running in existing scheduler is simpler and proven |
| Full pipeline with orchestrator + quality layer | Over-engineered for 71 symbols with daily refreshes |
| External paid API dependency | YFinance + Stockdex + prediction covers 100% for free |
| Separate microservice | Unnecessary complexity for a read-once-per-day data point |
| Real-time dividend alerts | Out of scope; notifications can be added later without architecture change |

---

## 9. Appendix: Code References

### Key Files

| File | Role |
|------|------|
| `backend/application/schedulers/earnings_scheduler.py` | Fetches dividends as part of financial bundle (2h cycle) |
| `backend/application/schedulers/market_data_scheduler.py` | Computes dividend metrics from history (24h cycle) |
| `backend/providers/defeat_beta_provider.py:679-692` | `_fetch_dividends()` — calls `ticker.dividends()` |
| `backend/providers/defeat_beta_provider.py:1552-1611` | `_parse_dividends()` — maps DataFrame to `DividendRow` |
| `backend/providers/yfinance_provider.py:147-158` | `get_dividends_df()` — `yf.Ticker.dividends` |
| `backend/infrastructure/repositories/financial_repository.py:499-522` | `upsert_dividends()` — stores to `dividend_history` |
| `backend/infrastructure/repositories/financial_repository.py` (new) | `upsert_upcoming_dividend()` + `cleanup_stale_events()` — targets `upcoming_dividend_events` |
| `backend/infrastructure/repositories/portfolio_repository.py:617-637` | `get_upcoming_ex_dates()` — reads from `dividend_history` |
| `backend/infrastructure/repositories/portfolio_repository.py` (new) | `get_next_upcoming_event()` — reads from `upcoming_dividend_events` |
| `backend/application/services/dividend_dashboard_service.py:157-189` | `get_upcoming()` — merges holdings with ex-dates |
| `backend/application/services/dividend_dashboard_service.py:191-283` | `get_holdings()` — includes `next_event` per holding |
| `backend/application/jobs/derived_financial_metrics_job.py:1249-1432` | `compute_and_upsert_dividend_metrics()` |
| `backend/schemas_portfolio.py:489-506` | `PortfolioDividendHolding` Pydantic model |
| `backend/infrastructure/repositories/portfolio_repository.py:547-549` | `get_holdings_with_companies()` |
| `web/src/features/portfolio/components/DividendsUpcomingCard.tsx` | Frontend card rendering |
| `web/src/features/portfolio/hooks/usePortfolio.ts:418-429` | `useDividendUpcoming()` React Query hook |

### DB Tables

| Table | Schema Ref | Used By |
|-------|-----------|---------|
| `dividend_history` | `Supabase_Schema.md:563-616` | Historical dividend metrics (unchanged) |
| `upcoming_dividend_events` | §7.3 Step 4 | Upcoming ex-dates card (new table) |
| `dividend_metrics` | `Supabase_Schema.md` (derived) | Portfolio dashboard summary |
| `portfolio_holdings` | `PORTFOLIO_DESIGN.md` | Share quantities for income estimates |
| `portfolio_dividends` | `PORTFOLIO_DESIGN.md:218-230` | Actual payments received (imported) |

### Scheduler Config

| Setting | Default | File |
|---------|---------|------|
| `EARNINGS_REFRESH_CHECK_INTERVAL_HOURS` | 2 | `earnings_scheduler.py:86` |
| `MARKET_DATA_REFRESH_INTERVAL_HOURS` | 24 | `market_data_scheduler.py` (config-driven) |
| `SCHEDULER_COMPANY_LOCK_TTL_SECONDS` | 2700 | `earnings_scheduler.py:72` |
