# Dividends Page Redesign — Feasibility Study & Design Document (Revised)

> **Status**: Draft for review  
> **Target**: Portfolio Dashboard → Dividends Tab  
> **Reference**: HTML mockup (hero, charts, holdings table, modal drill-down)

---

## 1. Design Principles (Revised)

1. **Separate actuals from estimates** — Every metric is categorized as *actual received*, *forward estimate*, or *company-quality metadata*. The UI communicates confidence, not false precision.
2. **Trust first** — Show coverage/confidence badges. Never fabricate exact dates or amounts from low-confidence heuristics.
3. **Load independently** — Summary, upcoming ex-dates, holdings table, and detail drawer each have their own fetch. One failing section does not break the page.
4. **Lazy-load detail** — Per-holding history loads only when the user opens the modal.
5. **Decision-first layout** — Organized around the questions income investors actually ask, not visual sections alone.

---

## 2. Reference Design Overview

The mockup presents a full-page dividend dashboard with these sections. The revised design adapts them with clearer semantics:

| Mockup Section | Revised Approach |
|----------------|------------------|
| Giant hero with "Projected Annual Income" | 4-6 **summary cards**: Trailing 12M Income, Forward Annual Estimate, YTD, Forward YoC, Growth (w/ coverage), Safety (w/ coverage) |
| "Est. financial freedom in X years" | **Removed from V1** — requires a full goal engine |
| Goal progress bar | **Kept** — `Monthly Income / User-Set Goal`, simple math |
| Upcoming list | **Renamed** to "Upcoming Ex-Dates" — explicit that these are eligibility cutoff dates, not payment dates; confidence-labeled |
| Income Trend Chart | **Kept** — monthly received (solid); forward estimate line deferred to V2 |
| Sector Donut | **Kept** — income by sector |
| Holdings Table | **Kept** — 10 columns, sortable, searchable, filterable |
| Row Click Modal | **Replaced with right-side Drawer** — lazy-loaded per-holding detail |
| Kings/Aristocrats filter | **Kept** — but only if streak semantics (`consecutive_increases` vs `consecutive_years_paid`) are verified |

---

## 3. Existing Assets — What We Already Have

The golden rule: **no snowflakes.** Every dashboard metric must reuse an existing service, table, or computation. If it doesn't exist yet, we build it once in the new `DividendDashboardService` and reuse it everywhere. Below is a complete accounting of every existing asset we can leverage.

### 3.1 Database Tables — Column-Level Detail

#### `portfolio_dividends` — User's actual dividend payments
| Column | Type | Populated By | Used For |
|--------|------|-------------|----------|
| `dividend_id` | BIGINT PK | Auto | — |
| `account_id` | BIGINT FK | CSV import / manual trade | Account filtering |
| `company_id` | INTEGER FK | CSV import | Joining to `companies`, `dividend_metrics` |
| `symbol` | VARCHAR | CSV import | Table display |
| `payment_date` | DATE | CSV import | Trailing 12M filtering, monthly grouping |
| `amount` | NUMERIC | CSV import | All income totals (always positive) |
| `currency` | VARCHAR | CSV import | Currency normalization |
| `fiscal_year` | INTEGER | CSV import | YTD filtering, monthly grouping |
| `fiscal_month` | INTEGER | CSV import | Monthly grouping |
| `shares_held` | NUMERIC? | CSV import (if available) | Per-share calculations |
| `amount_per_share` | NUMERIC? | CSV import (if available) | Forward estimate basis |

**Exists:** ✅ Full table, populated on CSV import.
**Gap:** `shares_held` and `amount_per_share` may be NULL if the CSV didn't provide them.

---

#### `dividend_history` — Company-level per-share dividends
| Column | Type | Populated By | Used For |
|--------|------|-------------|----------|
| `dividend_id` | SERIAL PK | Ingestion job | — |
| `company_id` | INTEGER | Ingestion job | Joining to holdings |
| `ex_dividend_date` | DATE | Ingestion job | Upcoming ex-dates, trailing 12M |
| `payment_date` | DATE | Ingestion job | Future: payable dates |
| `record_date` | DATE | Ingestion job | Future use |
| `dividend_amount` | NUMERIC(10,4) | Ingestion job | Per-share amount for forward estimates |
| `dividend_type` | VARCHAR(30) | Ingestion job | Filtering regular vs special dividends |
| `frequency` | VARCHAR(20) | Ingestion job | Payment frequency inference |
| `currency` | CHAR(3) | Ingestion job | Currency |
| `confidence_score` | DOUBLE | Ingestion job | Data quality indicator |

**Exists:** ✅ Full table, populated by the market data scheduler.
**Used for:** Forward income estimates (`current_shares × latest_regular_dividend_amount`), upcoming ex-dates, streak computation (via `dividend_metrics`).

---

#### `dividend_metrics` — Pre-computed per-company dividend analytics
| Column | Type | Populated By | Used For |
|--------|------|-------------|----------|
| `company_id` | INTEGER | Scheduler job | Join key |
| `fiscal_year` | INTEGER | Scheduler job | Year filter |
| `annual_dps` | NUMERIC(10,4) | Scheduler job | Forward estimate fallback, yield calc |
| `dividend_growth_rate_3yr` | NUMERIC(5,2) | Scheduler job | Per-holding growth (weighted → portfolio) |
| `dividend_growth_rate_5yr` | NUMERIC(5,2) | Scheduler job | Per-holding growth (weighted → portfolio) |
| `dividend_growth_rate_10yr` | NUMERIC(5,2) | Scheduler job | Per-holding growth (weighted → portfolio) |
| `consecutive_years_paid` | INTEGER | Scheduler job | Streak column in holdings table |
| `cash_dividend_payout_ratio` | NUMERIC(10,2) | Scheduler job | Payout ratio (GAAP basis) |
| `fcfe_coverage_ratio` | NUMERIC(5,2) | Scheduler job | Dividend safety depth |
| `retention_ratio` | NUMERIC(10,2) | Scheduler job | Growth sustainability |

**Exists:** ✅ Populated by `derived_financial_metrics_job.py` `compute_and_upsert_dividend_metrics()`, run on scheduler.
**⚠️ Gap:** `dividend_yield`, `dividend_payout_ratio`, `fcf_dividend_payout_ratio`, `dividend_coverage_fcf`, `ebitda_dividend_coverage` columns exist in the schema but are **never written** by the job. The live `DividendAnalysisService` computes equivalents on-the-fly from raw financials, so the dashboard should use the **service layer** for safety/payout metrics, not the bare `dividend_metrics` table.

---

#### `companies` — Company metadata
| Column | Type | Used For |
|--------|------|----------|
| `company_id` | INTEGER PK | Join key |
| `company_name` | VARCHAR | Table display |
| `sector` | VARCHAR | Sector breakdown donut chart |
| `industry` | VARCHAR | Future: industry filtering |
| `exchange` | VARCHAR | Market group |
| `security_type` | VARCHAR | ETF vs stock filtering |

**Exists:** ✅ Full table.

---

#### `portfolio_holdings` — Current user positions
| Column | Type | Used For |
|--------|------|----------|
| `account_id` | BIGINT FK | Account filtering |
| `company_id` | INTEGER FK | Join key to `companies`, `dividend_metrics` |
| `symbol` | VARCHAR | Table display |
| `quantity` | NUMERIC | Forward estimate: `shares × dps` |
| `average_cost` | NUMERIC | Yield on cost denominator |
| `total_cost` | NUMERIC | Yield on cost denominator |
| `current_value` | NUMERIC | Market value column (enriched at query time) |

**Exists:** ✅ Full table, recalculated on each CSV import.

---

#### `portfolio_monthly_dividends` — Pre-aggregated view (exists in Supabase, no SQL in repo)
| Column | Type | Used For |
|--------|------|----------|
| `account_id` | BIGINT | Account filtering |
| `fiscal_year` | INTEGER | Trend chart X-axis |
| `fiscal_month` | INTEGER | Trend chart X-axis |
| `total_amount` | NUMERIC | Trend chart Y-axis (received) |
| `payment_count` | INTEGER | Future: payment frequency analysis |
| `paying_companies` | INTEGER | Future: income diversification |

**Exists:** ✅ View exists in Supabase. SQL definition not checked into repo (should be captured).

---

### 3.2 Existing Backend Services — What They Already Compute

#### `DividendAnalysisService` (at `dividend_analysis_service.py`)
This is the single most important existing asset. It already computes everything we need per-company:

| Method | Returns | Dashboard Use |
|--------|---------|---------------|
| `_compute_overview()` | `annual_dividend`, `dividend_yield`, `payout_ratio_fcf`, `ex_dividend_date`, `frequency`, `status` | Current yield, payout ratio, next event type |
| `_compute_safety()` | `composite_score` (0-100), `composite_category`, `metrics[]` (7 sub-metrics), `earnings_stability`, `strengths[]`, `risks[]` | **Portfolio Safety Score** (weighted avg), detail drawer safety section |
| `_compute_growth()` | `cagr_1y/3y/5y/10y`, `consecutive_increases`, `annual_totals`, `recent_changes[]` | **Portfolio Dividend Growth 5Y** (weighted avg), streak, detail drawer history bar chart |
| `_compute_yield()` | `current_yield`, `avg_yield_5y`, `yield_percentile`, `theory_signal`, `yield_history[]` | Yield context in detail drawer |

**How to use it in the dashboard:** For each held symbol, call `DividendAnalysisService.get_dividend_analysis(symbol)` (or better, the existing React Query hook `useDividendAnalysis(symbol)` from the frontend). The dashboard's backend aggregates these per-holding results into portfolio-weighted averages.

**⚠️ Performance concern:** Calling the service for 50 holdings would be N queries. The dashboard endpoint should batch-fetch `dividend_metrics` + `dividend_history` for all held companies at once, then weight the results — avoiding per-company service calls.

---

#### `PortfolioService` (at `portfolio_service.py`)
Existing methods we extend (not rewrite):

| Method | Returns | Dashboard Use |
|--------|---------|---------------|
| `get_user_portfolio_overview()` | `{ ytd_dividends, total_cost_basis, top_holdings[], ... }` | YTD income (already exists!) |
| `enrich_holdings_with_prices()` | Holdings with `current_price`, `current_value` | Market value column |
| `get_dividend_history_detail()` | `{ dividends[], current_year_total }` | Detail drawer recent payments |
| `aggregate_holdings()` | Per-symbol aggregated holdings with cost basis | Forward income denominator |

---

#### `ValuationRepository` (at `valuation_repository.py`)
Existing methods we reuse:

| Method | Returns | Dashboard Use |
|--------|---------|---------------|
| `get_dividend_metrics_latest(company_id)` | Row from `dividend_metrics` table | Growth rates, streak, payout ratio |
| `get_dividend_history(company_id, limit)` | Rows from `dividend_history` | Upcoming ex-date, history bar chart |
| `get_current_market_price(company_id)` | Latest price | Yield calculation |

---

### 3.3 Existing Frontend Assets — What We Reuse

| Asset | Location | Dashboard Use |
|-------|----------|---------------|
| Recharts (`BarChart`, `LineChart`, `PieChart`) | Already used in 9+ components | All 3 dashboard charts |
| `useDividendAnalysis(symbol)` hook | `analysis/hooks/useDividendAnalysis.ts` | Detail drawer — reuses existing React Query hook for per-holding safety/growth |
| `useAggregatedHoldings()` hook | `portfolio/hooks/usePortfolio.ts` | Holdings table cost basis data |
| `useAllDividends(accountIds)` hook | `portfolio/hooks/usePortfolio.ts` | Monthly history for trend chart |
| `glass-panel` / card styling | global CSS | Dashboard cards |
| `Skeleton` component | `@/components/ui/skeleton` | Loading states per section |
| `cn()` utility | `@/lib/utils` | Conditional classes |

---

### 3.4 What Must Be Built (Genuinely New)

| Need | Why Existing Doesn't Cover It |
|------|------------------------------|
| **Per-holding trailing 12M income** | `portfolio_dividends` has raw payments but no pre-aggregated per-symbol rolling 12M |
| **Per-holding forward income estimate** | Requires joining `portfolio_holdings.quantity` × `dividend_history.latest_regular_dps` — no existing query |
| **Upcoming ex-date matching** | Requires joining `portfolio_holdings` → `companies` → `dividend_history` filtered to future dates — no existing query |
| **Portfolio-weighted averages** | `DividendAnalysisService` is per-company only. No portfolio-level aggregation exists. |
| **Sector income breakdown** | Requires joining `portfolio_dividends` → `companies.sector` and aggregating — no existing query |

These 5 items are what the new `DividendDashboardService` builds. Everything else is reused.

---

### 3.5 Reuse Traceability Matrix (No Snowflakes)

| Dashboard Metric | Existing Source | Reuse Strategy |
|-----------------|----------------|----------------|
| Trailing 12M Income | `portfolio_dividends.amount` | New query: `SUM(amount) WHERE payment_date > 365d` |
| Forward Annual Estimate | `portfolio_holdings.quantity` × `dividend_history.dividend_amount` | New query: join + multiply |
| YTD Dividends | `PortfolioService.get_user_portfolio_overview().ytd_dividends` | **Reuse existing** |
| Forward Yield on Cost | Forward Estimate ÷ `portfolio_holdings.total_cost` | New query: divide |
| Portfolio Growth 5Y | `dividend_metrics.dividend_growth_rate_5yr` | New: weighted avg across holdings |
| Portfolio Safety Score | `DividendAnalysisService._compute_safety().composite_score` | New: weighted avg — but read from `dividend_metrics` and financials directly (not per-company service calls) |
| Upcoming Ex-Dates | `dividend_history.ex_dividend_date` | New query: `WHERE ex_dividend_date >= today` |
| Monthly Trend | `portfolio_monthly_dividends` view | **Reuse existing view** |
| Sector Breakdown | `portfolio_dividends` × `companies.sector` | New query: join + GROUP BY |
| Per-Holding Streak | `dividend_metrics.consecutive_years_paid` | **Reuse pre-computed column** |
| Per-Holding Payout Ratio | `DividendAnalysisService._compute_overview().payout_ratio_fcf` or `dividend_metrics.cash_dividend_payout_ratio` | **Reuse pre-computed** (prefer service layer for FCF basis) |
| Per-Holding Safety | `DividendAnalysisService._compute_safety().composite_score` | **Reuse via** `useDividendAnalysis(symbol)` in drawer |
| Per-Holding Dividend History | `dividend_history` or `portfolio_dividends` | New: per-symbol query for detail drawer |
| Current Yield | `dividend_metrics.dividend_yield` or `annual_dps / current_price` | Compute from existing columns |

**Result:** 5 new queries, 3 weighted aggregations, everything else reused. No duplicate dividend analysis logic.

---

## 4. Gap Analysis — What We Have vs. What We Need

### 4.1 Metrics Map (Revised)

| Metric | Class | Source | Status | V1 Decision |
|--------|-------|--------|--------|-------------|
| Trailing 12M Income | **Actual** | `SUM(portfolio_dividends.amount)` last 12 months | New query | ✅ Show in summary cards |
| Forward Annual Estimate | **Estimate** | `SUM(current_shares × latest_regular_dps)` per holding | New calculation | ✅ Show in summary cards |
| YTD Dividends | **Actual** | Existing `current_year_total` | ✅ Exists | ✅ Show in summary cards |
| Forward Yield on Cost | **Estimate** | Forward Estimate ÷ `SUM(holding.total_cost)` (dividend payers only) | New calculation | ✅ Show in summary cards |
| Avg Monthly Income (12M) | **Actual** | Trailing 12M ÷ 12 | Trivial | ✅ Show in summary cards |
| Est. Monthly Income (Forward) | **Estimate** | Forward Annual ÷ 12 | Trivial | ✅ Show in summary cards (labeled) |
| Goal Progress | **Actual** | `Monthly Income / User Goal` | UI calc | ✅ Keep |
| Portfolio Dividend Growth 5Y | **Metadata** | Weighted avg of `dividend_metrics.growth_rate_5yr` by forward income | New aggregation | ✅ Show **with `coverage_pct`** |
| Portfolio Safety Score | **Metadata** | Weighted avg of `dividend_analysis.safety.composite_score` by forward income | New aggregation | ✅ Show **with `coverage_pct`** |
| Upcoming Ex-Dates | **Estimate** | Join holdings × `dividend_history` future ex_dividend_date | New query | ✅ Show **with `confidence`** |
| Monthly Income Trend | **Actual** | Existing `monthly_summaries` | ✅ Exists | ✅ Show in chart |
| Income by Sector | **Metadata** | Join dividends × `companies.sector` | New query | ✅ Show in donut chart |
| Est. Financial Freedom | **Estimate** | Goal-based projection | New | ❌ **V2** |

### 4.2 Holdings Table Columns (Revised)

| Column | Class | Source | V1 Decision |
|--------|-------|--------|-------------|
| Holding | — | `portfolio_holdings` + `companies` | ✅ |
| Market Value | **Actual** | `current_price × quantity` | ✅ |
| Forward Income | **Estimate** | `current_shares × latest_regular_dps` | ✅ Main income column |
| Trailing 12M | **Actual** | `sum(portfolio_dividends.amount)` last 12m | ✅ Secondary column |
| Current Yield | **Metadata** | `dividend_metrics.dividend_yield` or `annual_dps / price` | ✅ |
| Forward YoC | **Estimate** | Forward Income ÷ `total_cost` | ✅ |
| Increase Streak | **Metadata** | `dividend_metrics.consecutive_years_paid` or `dividend_analysis.growth.consecutive_increases` | ✅ Labeled precisely |
| Payout Ratio | **Metadata** | `dividend_analysis.overview.payout_ratio_fcf` | ✅ |
| Safety | **Metadata** | `dividend_analysis.safety.composite_score` | ✅ Show nullable |
| Next Event | **Estimate** | Future `ex_dividend_date` from `dividend_history` | ✅ Show type + date + confidence |

### 4.3 Gaps Requiring New Backend Work

| Need | Current State | Effort |
|------|--------------|--------|
| Per-holding forward income estimate | `portfolio_dividends` has past payments only; `dividend_history` has company-level dps | Medium |
| Trailing 12M income per holding | Only monthly aggregates exist, not per-symbol rolling | Low |
| Upcoming ex-date → holding matching | No join exists between portfolio holdings and `dividend_history` | Medium |
| Weighted quality/growth averages | `dividend_metrics` and `dividend_analysis` exist per-company, not portfolio-weighted | Medium |
| Per-holding cost basis for YoC | Existing in `portfolio_holdings.total_cost` | ✅ Already exists |

---

## 5. API Design (Revised)

Four endpoints, not one. Each has its own cache TTL and failure boundary. This avoids payload bloat, enables independent caching, and lets each section load separately.

| Endpoint | Cache TTL | Failure Impact |
|----------|-----------|----------------|
| `GET /portfolio/dividends/summary` | 5 min | Summary cards + charts hidden |
| `GET /portfolio/dividends/upcoming` | 1 hr | Upcoming card hidden |
| `GET /portfolio/dividends/holdings` | 5 min | Table hidden |
| `GET /portfolio/dividends/holdings/{symbol}` | 5 min | Drawer shows error state |

### 5.1 `GET /portfolio/dividends/summary`

Hero cards, trend chart, sector donut, goal progress.

```json
{
  "success": true,
  "currency": "USD",

  "trailing_12m_income": 7248.00,
  "forward_annual_income_estimate": 7512.00,
  "ytd_income": 3488.00,
  "avg_monthly_income_trailing_12m": 604.00,
  "estimated_monthly_income_forward": 626.00,
  "forward_yield_on_cost": 0.079,

  "goal": {
    "monthly_target": 1000.00,
    "current_monthly_income": 604.00,
    "progress_pct": 60.4
  },

  "portfolio_growth_5y": {
    "value": 0.112,
    "coverage_pct": 0.81
  },
  "portfolio_safety_score": {
    "value": 88,
    "coverage_pct": 0.76
  },

  "monthly_history": [
    { "month": "2024-07", "received": 580.00 },
    { "month": "2024-08", "received": 620.00 }
  ],

  "sector_breakdown": [
    { "sector": "Technology", "forward_income": 474.00, "weight": 0.42 }
  ]
}
```

### 5.2 `GET /portfolio/dividends/upcoming`

Upcoming ex-dates. Separate from summary because the cache lifetime is different — dividend declarations change at most daily, while summary income data changes only on new transactions.

```json
{
  "success": true,
  "events": [
    {
      "symbol": "PG",
      "company_name": "Procter & Gamble",
      "event_type": "ex_date",
      "event_date": "2025-07-20",
      "estimated_amount": 92.50,
      "confidence": "medium"
    }
  ]
}
```

Query params: `?account_ids=1,3` (optional filter).

### 5.3 `GET /portfolio/dividends/holdings`

Table rows. **No nested history** — per-holding detail loads on demand.

```json
{
  "success": true,
  "holdings": [
    {
      "symbol": "AAPL",
      "company_name": "Apple Inc.",
      "sector": "Technology",
      "market_value": 28450.00,
      "current_yield": 0.009,
      "forward_yield_on_cost": 0.042,
      "trailing_12m_income": 256.00,
      "forward_annual_income": 272.00,
      "dividend_increase_streak": 12,
      "payout_ratio": 0.42,
      "safety_score": 92,
      "next_event": {
        "type": "ex_date",
        "date": "2025-08-11",
        "confidence": "high"
      }
    }
  ]
}
```

Query params: `?account_ids=1,3` (optional filter).

### 5.4 `GET /portfolio/dividends/holdings/{symbol}`

Lazy-loaded for the detail drawer/modal.

```json
{
  "success": true,
  "symbol": "AAPL",
  "summary": {
    "market_value": 28450.00,
    "cost_basis": 6400.00,
    "forward_annual_income": 272.00,
    "trailing_12m_income": 256.00,
    "forward_yield_on_cost": 0.042
  },
  "quality": {
    "current_yield": 0.009,
    "dividend_growth_5y": 0.061,
    "dividend_increase_streak": 12,
    "payout_ratio": 0.42,
    "safety_score": 92
  },
  "history": {
    "annual_dividends_per_share": [
      { "year": 2021, "amount": 0.88 },
      { "year": 2022, "amount": 0.92 }
    ],
    "cash_received_by_year": [
      { "year": 2023, "amount": 188.00 },
      { "year": 2024, "amount": 244.00 }
    ]
  },
  "recent_payments": [
    {
      "payment_date": "2025-05-15",
      "amount": 64.00,
      "shares_held": 100,
      "amount_per_share": 0.25
    }
  ]
}
```

---

## 6. Metric Definitions & Trust Model

Every visible number must have a well-defined computation rule:

### 6.1 Trailing 12M Income
- **Formula**: `SUM(portfolio_dividends.amount)` where `payment_date` is within the last 365 days
- **Class**: Actual
- **Confidence**: High
- **Edge cases**: Includes special dividends. Reflects past ownership, not current.

### 6.2 Forward Annual Income Estimate
- **Formula**: `SUM(current_shares × latest_regular_dividend_per_share)` per held symbol
- **Class**: Estimate
- **Confidence**: Medium (assumes no cuts, no sold positions, regular dividend only)
- **Special dividends**: Excluded from forward estimate
- **Fallback**: If no `dividend_history` dps exists for a holding, exclude it and report lower coverage

### 6.3 Forward Yield on Cost
- **Formula**: `Forward Annual Estimate ÷ SUM(total_cost of dividend-paying holdings)`
- **Denominator scope**: Only holdings where `quantity > 0` AND `forward_annual_income > 0`
- **Class**: Estimate

### 6.4 Portfolio Dividend Growth 5Y
- **Formula**: Weighted average of `dividend_metrics.dividend_growth_rate_5yr` per held symbol, weighted by each holding's `forward_annual_income`
- **Class**: Metadata
- **Coverage**: `number_of_holdings_with_growth_rate / total_dividend_paying_holdings`
- **Display**: `11.2% (covers 81% of income)`

### 6.5 Portfolio Safety Score
- **Formula**: Weighted average of `dividend_analysis.safety.composite_score` per symbol, weighted by `forward_annual_income`
- **Class**: Metadata
- **Coverage**: Same as growth
- **Display**: `88 / 100 (covers 76% of income)`

### 6.6 Upcoming Ex-Dates
- **Source**: `dividend_history` where `ex_dividend_date >= today`
- **Amount estimate**: `amount_per_share × current_shares_held`
- **Confidence levels**:
  - `high`: Announced ex-date + amount in `dividend_history`
  - `medium`: Only ex-date available, amount estimated from last payment
  - `low`: Neither — date/amount inferred from payment frequency
- **Event types**: `ex_date` (V1 only; payable date added when data available)

---

## 7. Frontend Architecture (Revised)

### 7.1 Component Tree

```
DividendsTab (composed sections, independent queries)
├── DividendsSummarySection
│   ├── MetricCard[] (Trailing 12M, Forward Est, YTD, Forward YoC, Growth, Safety)
│   │   └── CoverageBadge (shown for Growth & Safety)
│   └── GoalProgressCard (monthly income / user target)
├── DividendsChartSection
│   ├── DividendTrendChart (Recharts LineChart)
│   └── DividendSectorChart (Recharts PieChart donut)
├── DividendsUpcomingCard
│   └── ExDateRow[] — confidence-labeled
├── DividendsHoldingsSection
│   ├── SearchInput + FilterSelect
│   └── DividendHoldingsTable (sortable columns, clickable row)
└── DividendDetailDrawer (lazy-loaded on row click)
    ├── HoldingIncomeSummary
    ├── QualityMetricsGrid
    ├── DividendHistoryChart (Recharts BarChart)
    └── RecentPaymentsList
```

### 7.2 Data Fetching Strategy

```
DividendsTab
├── useDividendSummary(accountIds)        → GET /portfolio/dividends/summary          (staleTime: 5 min)
├── useDividendUpcoming(accountIds)       → GET /portfolio/dividends/upcoming         (staleTime: 1 hr)
├── useDividendHoldings(accountIds)       → GET /portfolio/dividends/holdings         (staleTime: 5 min)
└── useDividendHoldingDetail(symbol)      → GET /portfolio/dividends/holdings/{symbol} (staleTime: 5 min)
                                           (enabled only when drawer is open)
```

Each section has its own loading/error state. If quality metrics fail, summary cards and table still render.

### 7.3 New / Modified Files

| File | Action | Purpose |
|------|--------|---------|
| `DividendsTab.tsx` | **Rewrite** | Compose all section components |
| `DividendsSummarySection.tsx` | **New** | Summary cards row |
| `MetricCard.tsx` | **New** | Reusable metric card with optional coverage badge |
| `GoalProgressCard.tsx` | **New** | Progress toward monthly goal |
| `DividendTrendChart.tsx` | **New** | Recharts `LineChart` — monthly received |
| `DividendSectorChart.tsx` | **New** | Recharts `PieChart` donut |
| `DividendsUpcomingCard.tsx` | **New** | Upcoming ex-date list |
| `DividendsHoldingsSection.tsx` | **New** | Search, filter, sort + table |
| `DividendHoldingsTable.tsx` | **New** | Sortable table component |
| `DividendDetailDrawer.tsx` | **New** | Right-side drawer (lazy-loaded) |
| `portfolio.types.ts` | **Modify** | Add dashboard response types |
| `portfolio.service.ts` | **Modify** | Add 4 new API methods |
| `usePortfolio.ts` | **Modify** | Add 4 new React Query hooks |

---

## 8. Implementation Plan (Phase 1)

### Phase 1a — Backend (Est. 2-3 days)

| Step | What | Files |
|------|------|-------|
| 8.1 | Add repo methods: trailing 12M per holding, forward estimate per holding, upcoming ex-date matching, sector breakdown aggregation | `portfolio_repository.py` |
| 8.2 | Add `DividendDashboardService` with sub-methods: `get_summary`, `get_holdings`, `get_holding_detail` | `dividend_dashboard_service.py` (new) |
| 8.3 | Add Pydantic schemas for all 4 response types | `schemas_portfolio.py` |
| 8.4 | Add 4 routes: `GET /portfolio/dividends/summary`, `/upcoming`, `/holdings`, `/holdings/{symbol}` | `portfolio.py` |
| 8.5 | Unit tests for each endpoint | `tests/` |

### Phase 1b — Frontend (Est. 3-4 days)

| Step | What | Files |
|------|------|-------|
| 8.6 | Types + service methods + hooks | `portfolio.types.ts`, `portfolio.service.ts`, `usePortfolio.ts` |
| 8.7 | Summary cards + goal progress | `DividendsSummarySection.tsx`, `MetricCard.tsx`, `GoalProgressCard.tsx` |
| 8.8 | Charts | `DividendTrendChart.tsx`, `DividendSectorChart.tsx` |
| 8.9 | Upcoming card | `DividendsUpcomingCard.tsx` |
| 8.10 | Holdings table w/ search/filter/sort | `DividendsHoldingsSection.tsx`, `DividendHoldingsTable.tsx` |
| 8.11 | Detail drawer | `DividendDetailDrawer.tsx` |
| 8.12 | Compose in DividendsTab | `DividendsTab.tsx` |

---

## 9. File Inventory (What Changes)

### Not changed (reused as-is):
- `usePortfolio.ts` — existing hooks for overview, performance, allocation, transactions
- `AlocationDonutCard.tsx` — reference pattern only; new sector chart is separate
- Any analysis-related components/pages

### Deleted:
- `DividendsTab.tsx` (old) — replaced by new composed version

### Changed:
- `portfolio.types.ts` — add dashboard response types
- `portfolio.service.ts` — add 4 API methods
- `usePortfolio.ts` — add 4 hooks
- `schemas_portfolio.py` — add 4 response schemas
- `portfolio.py` — add 4 routes
- `portfolio_repository.py` — add 5+ query methods

### New:
- `backend/application/services/dividend_dashboard_service.py`
- `web/src/features/portfolio/components/DividendsSummarySection.tsx`
- `web/src/features/portfolio/components/MetricCard.tsx`
- `web/src/features/portfolio/components/GoalProgressCard.tsx`
- `web/src/features/portfolio/components/DividendsUpcomingCard.tsx`
- `web/src/features/portfolio/components/DividendTrendChart.tsx`
- `web/src/features/portfolio/components/DividendSectorChart.tsx`
- `web/src/features/portfolio/components/DividendsHoldingsSection.tsx`
- `web/src/features/portfolio/components/DividendHoldingsTable.tsx`
- `web/src/features/portfolio/components/DividendDetailDrawer.tsx`

---

## 10. Edge Cases & Handling

| Edge Case | Handling |
|-----------|----------|
| No dividend data at all | Empty state with CTA to import transactions. All endpoints return empty arrays. |
| Mixed CAD/USD | Return `currency` field on summary; if mixed, show "Mixed currencies" badge. Full normalization deferred to V2. |
| Holding sold mid-year | Trailing 12M includes payments when held. Forward estimate = 0 (no current shares). This is correct behavior. |
| Special dividends | Included in trailing 12M. **Excluded** from forward estimate by using "latest regular" dps. |
| Dividend cut announced | Forward estimate is optimistic until `dividend_history` reflects new rate. Document as known limitation. |
| `dividend_metrics` not computed for a symbol | Growth/safety show `null` with `coverage_pct` reflecting actual coverage. Table still shows income columns. |
| No future ex-date found | `next_event` is `null`. Table shows `—`. Upcoming card excludes it. |
| Partial holdings in non-dividend stocks | Excluded from YoC denominator (only dividend-payers count). Income columns show 0 or `—`. |

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Upcoming ex-dates sparse | Empty upcoming card | Show "No upcoming ex-dates found" — acceptable for V1 |
| Scheduler hasn't run for `dividend_metrics` | Growth/safety show low coverage | `coverage_pct` makes this transparent. Scheduler runs daily. |
| Endpoint performance with 50+ holdings | 4 endpoints each hitting 3-5 tables | Each endpoint is focused. Use Supabase batched queries. React Query caches 5 min (1 hr for upcoming). |
| Currency mixing invalidates totals | Misleading dollar figures | `currency` field + warning badge. Document as V1 limitation. |
| User has no holdings | Empty everything | Single empty state: "Import your transactions to see dividend income." |

---

## 12. What Phase 1 Does NOT Include

- DRIP boost projection / toggle
- Est. financial freedom / years-to-goal
- Payable dates (only ex-dates)
- Tax-aware views (withholding, CAD/USD split, TFSA vs RRSP breakout)
- Export (CSV/PDF)
- Email/notification for ex-dates
- What-if scenario planner

---

## 13. Comparison: Original Design vs Revised Design

| Aspect | Original | Revised |
|--------|----------|---------|
| Endpoints | 1 mega-endpoint | 4 focused endpoints (summary, upcoming, holdings, detail) |
| Hero | Single giant card with 8+ metrics | 4-6 summary cards + goal progress |
| Actuals vs Estimates | Blended ("Projected Annual Income") | Separated (Trailing 12M ≠ Forward Estimate) |
| Upcoming | Called "dividends", no confidence | Called "ex-dates", with `confidence` field |
| Modal data | Embedded in table payload | Lazy-loaded via `/holdings/{symbol}` |
| Metric trust | No coverage/confidence | `coverage_pct` and `confidence` on all estimated/metadata fields |
| Est. Financial Freedom | In hero | Deferred to V2 |
| Growth/Safety | Unqualified hero numbers | Badged with `coverage_pct` |
| Streak | Ambiguous ("Streak") | Precise ("Dividend Increase Streak" vs "Years Paid") |

---

## 14. Decision Records

### ADR-1: 4 endpoints vs 1 mega-endpoint
**Decision**: 4 endpoints (summary, upcoming, holdings, holding detail).
**Rationale**: Independent loading/caching with different TTLs — summary changes on new transactions (5 min stale), upcoming changes on dividend declarations (~daily, 1 hr stale). One failing endpoint doesn't degrade the others. Summary payload ~2KB, upcoming ~200B, holdings ~5KB for 50 rows, detail ~3KB. Total initial load ~7KB vs ~25KB+ if all history were embedded.

### ADR-2: Actuals and estimates are always separate
**Decision**: No unlabeled "Projected Annual Income." Always show "Trailing 12M Income" + "Forward Annual Income Estimate" as distinct metrics.
**Rationale**: Trust. Users need to know what is factual cash received vs what is a forward-looking estimate.

### ADR-3: Modal is lazy-loaded via dedicated endpoint
**Decision**: `GET /portfolio/dividends/holdings/{symbol}` loaded on drawer open.
**Rationale**: Avoids bloating the holdings table payload with per-row history that most users never expand. Scales to 100+ holdings.

### ADR-4: Goal progress stays, financial freedom defers
**Decision**: Show `Monthly Income / User Goal` bar. Remove "Est. financial freedom in X years."
**Rationale**: Goal progress is simple math that users can trust. "Years to freedom" requires compounding assumptions, inflation, contribution modeling — proper goal engine work for V2.

### ADR-5: All charts use Recharts (not Chart.js)
**Decision**: Consistent with existing codebase (9+ Recharts components). No new charting dependency.

---

## 15. Test Plan

### 15.1 Backend Unit Tests (DividendDashboardService)

Each unit test seeds Supabase with controlled data and calls the service method directly via `DividendDashboardService(account_ids=[1])`.

| # | Test | Input Data | Assertion |
|---|------|-----------|-----------|
| UT1 | `test_trailing_twelve_month_income` | 4 dividend records for 2 holdings: 2 inside 365-day window, 1 older, 1 future | SUM = sum of 2 in-window payments. Older + future excluded. |
| UT2 | `test_forward_annual_estimate_per_holding` | Holding A: 100 shares × $0.50/qtr dps = $200/yr. Holding B: 50 shares × $1.00/qtr = $200/yr | Forward total = $400. Per-holding: A=$200, B=$200. |
| UT3 | `test_forward_annual_excludes_special` | Standard dps = $0.50/qtr, but `dividend_history` has a $5.00 special | Forward uses $0.50 × 4 × shares. Special excluded. |
| UT4 | `test_weighted_portfolio_growth_5yr` | A: fwd_income=$200, growth=8% → weight=0.5. B: fwd_income=$200, growth=4% → weight=0.5 | Weighted avg = 6.0%. `coverage_pct` = 100% (both have data). |
| UT5 | `test_weighted_portfolio_safety` | A: fwd_income=$200, safety=85. B: fwd_income=$200, safety=65 | Weighted avg = 75.0. |
| UT6 | `test_safety_growth_coverage_pct` | 3 holdings, only 2 have `dividend_metrics` rows | Coverage = 66.67%. Missing holding excluded from avg. |
| UT7 | `test_sector_breakdown` | 4 holdings across 3 sectors (Tech 2, Finance 1, Energy 1) with fwd income | Array of 3 objects with `sector`, `forward_income`, `pct_of_total`. Sum of pct = 100%. |
| UT8 | `test_upcoming_ex_dates_sorted` | 3 future ex-dates for 2 holdings, various dates | Returns array sorted ascending by `ex_dividend_date`. Most recent (soonest) first. |
| UT9 | `test_upcoming_confidence_high` | `dividend_history` row with `dividend_type='regular'` and announced date < 90 days ago | `confidence = "high"` |
| UT10 | `test_upcoming_confidence_low` | Same but no recent `dividend_history` announcement, date inferred from pattern | `confidence = "low"` |
| UT11 | `test_per_holding_next_event` | Holding has a future ex-date in `dividend_history` | `next_event.ex_dividend_date` = that date, `next_event.type = "ex-date"`, `next_event.confidence` present |
| UT12 | `test_per_holding_no_next_event` | Holding has no future ex-dates | `next_event = null` |
| UT13 | `test_per_holding_trailing_12M` | 6 payments for same symbol in last 12 months | SUM correctly scoped to that symbol + 365-day window |
| UT14 | `test_per_holding_dividend_history_limited` | 20+ payments for a holding in `portfolio_dividends` | Returns last 12 (sorted DESC by `payment_date`) |
| UT15 | `test_yield_on_cost_denominator` | 2 holdings: A (div payer, cost=$5k, fwd=$200), B (no dps, cost=$10k, fwd=$0) | YoC = $200 / $5k = 4%. Holding B excluded from denominator. |
| UT16 | `test_currency_uniform_usd` | All portfolio dividends are USD | Summary `currency = "USD"`, `currencies_mixed = false` |
| UT17 | `test_currency_mixed` | 2 dividends in USD, 1 in CAD | Summary `currency = "Mixed"`, `currencies_mixed = true` |
| UT18 | `test_account_filtering` | Account 1 has 3 dividend holdings, Account 2 has 2. Query with `account_ids=[1]`. | All 4 endpoints return only Account 1's data. |

### 15.2 Backend Integration Tests (Route-Level)

Each test starts a test FastAPI client, seeds Supabase with known data, and hits the real route.

| # | Test | Method | Endpoint | Assertion |
|---|------|--------|----------|-----------|
| IT1 | `test_summary_route_shape` | GET | `/portfolio/dividends/summary?account_ids=1` | 200. Body matches `PortfolioDividendSummary` schema: `trailing_12m_income`, `forward_annual_estimate`, `ytd_dividends`, `forward_yield_on_cost`, `avg_monthly_trailing`, `avg_monthly_forward`, `portfolio_growth_5yr` (with `value`, `coverage_pct`), `portfolio_safety` (with `value`, `coverage_pct`), `goal_progress` (with `monthly_income`, `monthly_goal`, `pct`), `currency`, `currencies_mixed`, `last_updated`. |
| IT2 | `test_summary_empty_portfolio` | GET | `/portfolio/dividends/summary?account_ids=2` (no holdings) | 200. All income = 0. Goal progress = 0%. Coverage = 0%. Currency = null. |
| IT3 | `test_summary_no_account_ids` | GET | `/portfolio/dividends/summary` | 401 or validation error (consistent with existing endpoints). |
| IT4 | `test_holdings_route_shape` | GET | `/portfolio/dividends/holdings?account_ids=1` | 200. Body is array matching `PortfolioDividendHolding[]`. Each has: `symbol`, `company_name`, `sector`, `quantity`, `market_value`, `total_cost`, `forward_income`, `trailing_12m_income`, `current_yield`, `forward_yield_on_cost`, `payout_ratio`, `increase_streak`, `safety_score` (nullable), `next_event` (nullable). |
| IT5 | `test_holdings_sort_default` | GET | `/portfolio/dividends/holdings?account_ids=1` | Default sort by `forward_income` DESC. First row is highest. |
| IT6 | `test_holdings_search` | GET | `/portfolio/dividends/holdings?account_ids=1&search=MSFT` | Only holdings matching "MSFT" in symbol or name. |
| IT7 | `test_holdings_filter_sector` | GET | `/portfolio/dividends/holdings?account_ids=1&sector=Technology` | Only Technology sector holdings. |
| IT8 | `test_detail_route_shape` | GET | `/portfolio/dividends/holdings/AAPL?account_ids=1` | 200. Body matches `PortfolioDividendDetail`: symbol, company_name, sector, income (trailing_12m, forward, ytd, yield_on_cost), quality_metrics (safety, payout_ratio, growth_5yr, consecutive_increases, yield_5yr_avg), dividend_history[12] (date, amount), recent_payments[12] (payment_date, amount, shares_held). |
| IT9 | `test_detail_not_found` | GET | `/portfolio/dividends/holdings/INVALID?account_ids=1` | 200 with `symbol = "INVALID"`, all income = 0, quality_metrics = null, history = []. |
| IT10 | `test_detail_no_data` | GET | `/portfolio/dividends/holdings/AAPL?account_ids=1` where AAPL has no `dividend_metrics` | 200. Quality metrics fields are null. `coverage_pct` fields reflect missing data. Income fields still populate from `portfolio_dividends`. |
| IT11 | `test_upcoming_route_shape` | GET | `/portfolio/dividends/upcoming?account_ids=1` | 200. Body is array matching `UpcomingExDate[]`. Each has: `symbol`, `company_name`, `ex_dividend_date`, `amount_per_share`, `estimated_income` (= shares × amount), `dividend_type`, `confidence`. |
| IT12 | `test_upcoming_empty` | GET | `/portfolio/dividends/upcoming?account_ids=2` (no future ex-dates) | 200. Empty array `[]`. |
| IT13 | `test_upcoming_excludes_special` | GET | `/portfolio/dividends/upcoming?account_ids=1` with a special dividend in future | Only regular dividends appear. Specials excluded. |
| IT14 | `test_all_endpoints_scope_by_account` | 4 GETs | Each endpoint with `account_ids=[2]` in a multi-account user | Summary only reflects account 2. Holdings count matches account 2. Detail for a symbol not in account 2 returns empty/zero data. Upcoming only from account 2's holdings. |

### 15.3 Backend Correctness Tests (Assertions on Math)

These test the arithmetic specifically, not just the shape. They use known seed values so we can assert exact numbers.

| # | Test | Seed Data | Expected Calculation |
|---|------|-----------|---------------------|
| CT1 | Trailing 12M math | 3 payments: $100, $150, $200 all within 365 days | $450.00 |
| CT2 | Trailing 12M boundary | $100 at day -366, $150 at day -180, $200 at day -30 | $350.00 (excludes $100) |
| CT3 | Forward estimate per holding | 50 shares × $0.25/qtr = $12.50/qt × 4 = $50 | $50.00 |
| CT4 | Forward estimate with fractional shares | 50.5 shares × $0.25/qtr = $12.625 × 4 | $50.50 |
| CT5 | YoC calculation | Fwd=$200, total_cost=$4,000 (div payers only) | 5.00% |
| CT6 | YoC with non-dividend payer | Fwd=$200 payer1, Fwd=$0 payer2. Denominator = $4,000 (payer1 only) | 5.00% |
| CT7 | Weighted growth avg | 3 holdings: A(fwd=$400, gr=10%), B(fwd=$200, gr=5%), C(fwd=$400, gr=0%) | ($400×10 + $200×5 + $400×0) / $1000 = 5.0% |
| CT8 | Weighted safety avg | Same weights as CT7: A=80, B=70, C=90 | ($400×80 + $200×70 + $400×90) / $1000 = 82.0 |
| CT9 | Goal progress | Monthly income = $833.33, monthly goal = $5,000 | 16.67% |
| CT10 | Goal progress above 100% | Monthly income = $6,000, goal = $5,000 | 100% (clamped) |
| CT11 | Sector pct sum | Tech=$1,200, Finance=$600, Energy=$200, total=$2,000 | Tech=60%, Finance=30%, Energy=10%. Sum = 100%. |
| CT12 | Upcoming estimated income | 100 shares × $0.50 DPS | $50.00 |
| CT13 | Dividend history limit | 15 payments exist | Returns 12 (most recent). |

### 15.4 Edge Case Tests (from Section 10)

Each edge case in Section 10 has a corresponding test:

| # | Edge Case | Test Strategy |
|---|-----------|--------------|
| EC1 | **No dividend data at all** | Account with holdings but zero `portfolio_dividends` records and missing `dividend_history`. Summary: all income = 0, coverage = 0%. Holdings: income columns = 0, quality columns = null. Upcoming: []. Detail: income=0, quality=null, empty arrays. |
| EC2 | **Mixed CAD/USD** | Seed dividends in both currencies. Summary shows `currency = "Mixed"`, `currencies_mixed = true`. No crash. |
| EC3 | **Holding sold mid-year** | Holding exists in `portfolio_holdings` (was sold, shares=0). Trailing 12M includes historical payments. Forward estimate = 0 (no current shares). |
| EC4 | **Special dividends in history** | `dividend_history` has a `dividend_type='special'` record. Forward estimate ignores it. Upcoming excludes it. Trailing 12M includes it (actual cash received). |
| EC5 | **Dividend cut — old dps in table vs new actual** | `dividend_history` has dps=$0.50, but last 2 `portfolio_dividends` show $0.30. Forward estimate uses $0.50 (known limitation). Documented. |
| EC6 | **dividend_metrics not computed** | Symbol exists in holdings but no `dividend_metrics` row. Growth = null, safety = null, coverage_pct reflects only covered holdings. Table still shows income columns. |
| EC7 | **No future ex-date** | Holding has no `dividend_history.ex_dividend_date >= today`. `next_event = null`. Upcoming array excludes it. |
| EC8 | **Non-dividend-paying holdings** | Stock with 0 dps. Forward income = 0, excluded from YoC denominator. |
| EC9 | **Zero shares** | `portfolio_holdings.quantity = 0` for a symbol. Forward estimate = 0. Still shows in holdings table. |
| EC10 | **Duplicate symbols across accounts** | Same symbol in 2 different accounts within the same portfolio. Aggregated correctly. |
| EC11 | **Fiscal month boundary** | Payment on Dec 31 vs Jan 1 — correct fiscal_year/fiscal_month grouping. |
| EC12 | **Very large portfolio (100+ holdings)** | Performance benchmark: each endpoint completes in < 3 seconds. |

### 15.5 Frontend Unit Tests (Component)

Using Vitest + React Testing Library. Each component tested in isolation with mock data matching the TypeScript types.

| # | Component | Test | Mock Data | Assertion |
|---|-----------|------|-----------|-----------|
| FT1 | `MetricCard` | Renders value and label | `{ label: "Trailing 12M", value: "$1,234.56", ... }` | Text "Trailing 12M" and "$1,234.56" visible. |
| FT2 | `MetricCard` | Renders with coverage badge | `{ coveragePct: 85 }` | Badge text "85% coverage" visible. |
| FT3 | `MetricCard` | Renders without coverage badge | `{ coveragePct: undefined }` | No badge element. |
| FT4 | `MetricCard` | Handles null value | `{ value: null }` | Shows "—" or "N/A". |
| FT5 | `MetricCard` | Highlights positive/negative | `{ change: 5.2, changeType: 'positive' }` | Green/up arrow. |
| FT6 | `MetricCard` | Negative change styling | `{ change: -3.1, changeType: 'negative' }` | Red/down arrow. |
| FT7 | `GoalProgressCard` | Renders progress bar | `{ monthlyIncome: 833.33, monthlyGoal: 5000 }` | Bar width ≈ 16.67%. Text "$833.33 / $5,000.00". |
| FT8 | `GoalProgressCard` | Progress at 0% | `{ monthlyIncome: 0, monthlyGoal: 5000 }` | Bar width = 0%. |
| FT9 | `GoalProgressCard` | Progress over 100% | `{ monthlyIncome: 6000, monthlyGoal: 5000 }` | Bar clamped at 100%. |
| FT10 | `GoalProgressCard` | No goal set | `{ monthlyIncome: 500, monthlyGoal: null }` | Shows "Set a monthly income goal in Settings." |
| FT11 | `DividendTrendChart` | Renders LineChart | 12 months of `{ month: "Jan", amount: 450 }` | SVG with 12 data points. Axes labeled. |
| FT12 | `DividendTrendChart` | Empty data | `[]` | "No dividend data yet" empty state. |
| FT13 | `DividendSectorChart` | Renders PieChart | 3 sectors with values summing to $2,000 | SVG donut with 3 slices. Legend matches. |
| FT14 | `DividendSectorChart` | Single sector | `[{ sector: "Technology", value: 2000 }]` | Full donut in one color. |
| FT15 | `DividendSectorChart` | Empty data | `[]` | "No sector data" empty state. |
| FT16 | `DividendsUpcomingCard` | Renders list | 3 upcoming ex-dates | 3 rows visible. Each shows symbol, date, amount, estimated income, confidence badge. |
| FT17 | `DividendsUpcomingCard` | Empty list | `[]` | "No upcoming ex-dates found" empty state. |
| FT18 | `DividendsUpcomingCard` | High vs low confidence | 1 with high, 1 with low | High shows green badge, low shows yellow/gray badge. |
| FT19 | `DividendHoldingsTable` | Renders all rows | 5 holding rows | 5 rows visible. Column headers present. |
| FT20 | `DividendHoldingsTable` | Sort by forward income | Same data | Click column header → sorted DESC. Click again → ASC. |
| FT21 | `DividendHoldingsTable` | Sort by yield | Same data | Click yield column header → sorted by yield value. |
| FT22 | `DividendHoldingsTable` | Search by symbol | Type "MSFT" in search input | Only MSFT row visible. |
| FT23 | `DividendHoldingsTable` | Search by name | Type "Microsoft" in search input | Only MSFT row visible. |
| FT24 | `DividendHoldingsTable` | Search no match | Type "ZZZZ" | "No holdings match your search." |
| FT25 | `DividendHoldingsTable` | Filter by sector | Select "Technology" from filter dropdown | Only Technology holdings visible. |
| FT26 | `DividendHoldingsTable` | Filter + search combined | Sector=Tech + search="MS" | Only matching subset. |
| FT27 | `DividendHoldingsTable` | Null safety score | Row with `safety_score: null` | Shows "—" in safety column. |
| FT28 | `DividendHoldingsTable` | No next event | Row with `next_event: null` | Shows "—" in next event column. |
| FT29 | `DividendDetailDrawer` | Opens on row click | Mock API returns detail | Drawer opens. Skeleton shown. Data replaces skeleton. |
| FT30 | `DividendDetailDrawer` | Loading state | Slow API (2s delay) | Skeleton visible. |
| FT31 | `DividendDetailDrawer` | Error state | API returns 500 | Error message "Failed to load holding details. Retry". |
| FT32 | `DividendDetailDrawer` | Renders quality metrics | Safety, payout ratio, growth, streak, yield 5yr avg | All 5 metrics visible with values. |
| FT33 | `DividendDetailDrawer` | Quality metrics null | API returns null quality fields | Shows "No data" or "—" for each. |
| FT34 | `DividendDetailDrawer` | Renders history bar chart | 12 quarterly payments | BarChart rendered with 12 bars. |
| FT35 | `DividendDetailDrawer` | Renders recent payments | 6 payment records | 6 rows in payment table. |
| FT36 | `DividendDetailDrawer` | Closes | Click close button/overlay | Drawer closes. No visible drawer content. |

### 15.6 Frontend Integration Tests

Full `DividendsTab` rendering with MSW (Mock Service Worker) intercepting all 4 endpoints.

| # | Test | Mock Scenario | Assertion |
|---|------|---------------|-----------|
| FIT1 | Full page render | All 4 endpoints return realistic data | Summary cards visible. Trend chart visible. Sector chart visible. Upcoming card visible. Holdings table with 5+ rows. No loading spinners. |
| FIT2 | Summary loading | Only summary endpoint delayed (2s) | Summary section shows Skeleton. Other sections render normally (charts, upcoming, table). |
| FIT3 | Summary error | Summary endpoint 500 | Summary section shows error state. Other sections unaffected. |
| FIT4 | Holdings loading | Only holdings endpoint delayed | Table shows Skeleton. Summary and charts unaffected. |
| FIT5 | Holdings error | Holdings endpoint 500 | Table shows error state. Summary and charts unaffected. |
| FIT6 | Upcoming loading | Upcoming endpoint delayed | Upcoming card shows Skeleton. Holdings and summary unaffected. |
| FIT7 | Upcoming error | Upcoming endpoint 500 | Upcoming card shows error. Other sections unaffected. |
| FIT8 | Detail load and display | Click holding row → detail endpoint | Drawer opens with data. Verify detail API called with correct symbol. |
| FIT9 | All endpoints slow | All 4 delayed 3s | All sections show skeleton simultaneously. No partial empty states flash. |
| FIT10 | All endpoints error | All 4 return 500 | All sections show error states. App doesn't crash. |
| FIT11 | Empty portfolio | All 4 return empty/null | Empty state: "Import your transactions to see dividend income." |
| FIT12 | Tab re-mounts (navigate away and back) | Navigate to another tab, then back | All 4 endpoints called again. No stale cache. (or cache returns if within staleTime) |

### 15.7 Test Fixture Strategy

| Fixture | Contents | Used By |
|---------|----------|---------|
| `seed_portfolio_1.sql` | 2 accounts, 10 companies, 20 holdings, 60 `portfolio_dividends` records (3 years), 8 `dividend_history` records (future+past), 8 `dividend_metrics` rows, company sectors (Tech, Finance, Energy, Healthcare) | UT1-18, IT1-14, CT1-13 |
| `seed_empty_portfolio.sql` | 1 account, 0 holdings, 0 dividends | UT2 variant, EC1 |
| `seed_mixed_currency.sql` | Same as portfolio_1 but 2 dividends in CAD | UT17, EC2 |
| `seed_missing_metrics.sql` | Portfolio_1 data but 3 holdings missing `dividend_metrics` | UT6, EC6 |
| Mock handlers (MSW) | 4 handlers returning typed JSON matching schemas | FT1-36, FIT1-12 |

### 15.8 Test Execution

| Command | Scope | Expected Count |
|---------|-------|---------------|
| `pytest tests/unit/services/test_dividend_dashboard_service.py` | Backend unit (UT*) | ~18 tests |
| `pytest tests/integration/api/test_dividend_dashboard.py` | Backend integration (IT*) | ~14 tests |
| `pytest tests/integration/api/test_dividend_dashboard_correctness.py` | Backend correctness (CT*) | ~13 tests |
| `pytest tests/integration/api/test_dividend_dashboard_edge_cases.py` | Backend edge cases (EC*) | ~12 tests |
| `npx vitest run web/src/features/portfolio/components/__tests__/` | Frontend component (FT*) | ~36 tests |
| `npx vitest run web/src/features/portfolio/__tests__/DividendsTab.integration.test.tsx` | Frontend integration (FIT*) | ~12 tests |
| **Total** | | **~105 tests** |
