# Stock vs Index Outperformance Analysis — Design Document

> **Feature:** Compare a stock's performance against a benchmark index (e.g. SPY) using quantitative metrics, fundamental growth, visual signals, and chart overlays.
>
> **Status:** Implemented — v1.0
>
> **Backend endpoint:** `GET /{symbol}/stock-vs-index?benchmark_symbols=SPY&years=3`
>
> **Frontend route:** `/analysis/{symbol}` → "Market Comparison" tab
>
> **Design:** Supports multiple benchmarks (comma-separated). First benchmark drives scoring; all appear in charts. Shared `BenchmarkSelector` component + `BENCHMARK_COLORS` map used by both Portfolio Performance and Stock vs Index features for consistent UX.

---

## Table of Contents

1. [Use Cases](#1-use-cases)
2. [Architecture Overview](#2-architecture-overview)
3. [Frontend Components](#3-frontend-components)
4. [Backend Components](#4-backend-components)
5. [Database Tables](#5-database-tables)
6. [Scoring Methodology](#6-scoring-methodology)
7. [Sequence Diagrams](#7-sequence-diagrams)
8. [Class Diagrams](#8-class-diagrams)
9. [Alternate Scenarios & Error Handling](#9-alternate-scenarios--error-handling)
10. [Test Plan](#10-test-plan)

---

## 1. Use Cases

### Primary Use Case: Analyze Stock vs Index Performance

**Actor:** Authenticated user viewing the analysis page for a symbol

**Preconditions:**
- User is logged in (Firebase auth → backend JWT)
- Stock symbol exists in `companies` table
- At least one active benchmark exists in `benchmark_config` (default: `us_market` → SPY)
- Both stock and benchmark have price history in `price_history`

**Postconditions:**
- User sees combined outperformance score (0–100), quantitative metrics (alpha, beta, Sharpe, growth), visual signals (RS trend, outperform rate, drawdown ratio), and charts (normalized price overlay + relative strength line)

**Main Flow:**
1. User navigates to `/analysis/{symbol}` and clicks "Market Comparison" tab
2. `StockVsIndexPanel` mounts with default benchmark `["SPY"]` selected
3. Panel fetches available benchmarks via `GET /analysis/benchmarks`
4. User can toggle additional benchmarks (max 5) via `BenchmarkSelector` dropdown
5. `useStockVsIndex(symbol, selectedBenchmarks)` hook fires `useQuery` with key `["stock-vs-index", symbol, "SPY", 3]`
6. `fetchStockVsIndex` calls `GET /api/proxy/analysis/{symbol}/stock-vs-index?benchmark_symbols=SPY&years=3`
7. Backend resolves company context, resolves each benchmark symbol to its company_id via `benchmark_config`
8. First benchmark drives quantitative + visual scoring
9. All benchmarks' price data is fetched and included in chart data
10. Response returned: scoring metrics for primary benchmark, chart data for all
11. Frontend renders score + metrics + charts with consistent colors per benchmark (SPY=amber, QQQ=violet, etc.)

### Secondary Use Case: Compare Against Multiple Benchmarks

**Actor:** Authenticated user

**Flow:** Toggle additional benchmarks (QQQ, IWM, VTI, DIA) in the BenchmarkSelector. Each toggle triggers a new API call with the updated comma-separated list. The primary benchmark (first in list) drives all scoring; additional benchmarks appear only in the normalized price overlay and relative strength charts, each drawn in their consistent color (matching Portfolio Performance).

### Secondary Use Case: Adjust Time Window

**Actor:** Developer / API consumer

**Flow:** Pass `years=1` or `years=5` (range: 1–10). Shorter windows increase sensitivity to recent trends; longer windows provide more statistical significance.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                          │
│                                                                     │
│  page.tsx (analysis/[symbol])                                       │
│    └─ StockVsIndexPanel                                             │
│         ├─ useStockVsIndex (hook)                                   │
│         │    └─ fetchStockVsIndex (service fn)                      │
│         │         └─ fetch() → /api/proxy/analysis/{symbol}/...     │
│         ├─ useAnalysisBenchmarks (hook)                             │
│         │    └─ fetchBenchmarks (service fn)                        │
│         │         └─ fetch() → /api/proxy/analysis/benchmarks       │
│         ├─ BenchmarkSelector (shared component)                     │
│         ├─ Metric, SectionHeader (shared-ui)                        │
│         └─ recharts (LineChart, one Line per benchmark)             │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTP (credentials: "include")
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Next.js Proxy Layer                              │
│  /api/proxy/{path} → forwards to backend:8001/{path}               │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                               │
│                                                                     │
│  api/analysis.py                                                    │
│    ├─ GET /analysis/{symbol}/stock-vs-index                         │
│    │    └─ StockIndexComparisonService.evaluate_outperformance()    │
│    │         ├─ _quantitative_analysis() (vs primary)              │
│    │         ├─ _visual_analysis() (vs primary)                    │
│    │         └─ _prepare_chart_data() (all benchmarks)             │
│    └─ GET /analysis/benchmarks                                      │
│         └─ Returns all active benchmark_config rows                 │
│                                                                     │
│  infrastructure/repositories/                                       │
│    ├─ AnalysisRepository                                            │
│    │    ├─ get_benchmark_by_symbol()                                │
│    │    ├─ get_all_active_benchmarks()                              │
│    │    ├─ get_price_history_range()                                │
│    │    └─ get_revenue_and_eps_growth()                             │
│    └─ ValuationRepository (delegated via _repo)                     │
│         ├─ get_company_context()                                    │
│         ├─ get_fcf_history()                                        │
│         ├─ get_company_summary_latest()                             │
│         └─ get_income_statements_annual()                           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ Supabase PostgreSQL (via postgrest-py)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Supabase / PostgreSQL                         │
│                                                                     │
│  Tables accessed:                                                   │
│    companies         (company_id, ticker_symbol, sector, industry)  │
│    benchmark_config  (role, company_id, symbol, is_active)          │
│    price_history     (company_id, price_date, close_price, ...)     │
│    income_statements (company_id, fiscal_year, revenue, net_income) │
│    cash_flow_statements (company_id, fiscal_year, fcf, ...)         │
│    company_summary   (company_id, trailing_pe, ...)                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Stateless service** | Price-based analysis changes daily; no value in caching to `valuation_runs` table |
| **Price-history alignment truncation** | Stock and index may have different row counts; align to shorter length to prevent `IndexError` |
| **Monthly EOM price data** | Scheduler compresses daily → monthly EOM bars; sufficient for multi-year trend analysis |
| **Role-based benchmark indirection** | `benchmark_config` table maps roles to tickers; code never hardcodes "SPY" |
| **Symbol-based multi-benchmark selection** | Frontend selects by symbol (SPY, QQQ), backend resolves via `get_benchmark_by_symbol()`. First symbol = primary for scoring; all symbols included in chart data |
| **Shared color map** | `BENCHMARK_COLORS` in `web/src/lib/colors.ts` is the single source of truth for both Portfolio Performance and Stock vs Index chart colors |
| **Shared BenchmarkSelector** | `BenchmarkSelector` moved to `web/src/components/ui/benchmark-selector.tsx`; reused by both features with the same look, feel, and behavior |
| **No pagination needed** | Monthly data for 3–10 years is 36–120 rows, well under Supabase's 1000-row limit |
| **Throws on error** | Unlike cached valuation methods (which handle 404 gracefully), this is a stateless computation that should always succeed if data exists |
| **CAPM-based alpha** | Alpha = actual return − (risk-free rate + β × (market return − risk-free rate)) |

---

## 3. Frontend Components

### 3.1 Component Tree

```
page.tsx (analysis/[symbol])
└── "Market Comparison" tab (tab === "comparison")
    └── StockVsIndexPanel ({ symbol })
        ├── useAnalysisBenchmarks() → available benchmarks (on mount)
        ├── selectedBenchmarks state (default: ["SPY"])
        ├── Error banner (conditional)
        ├── Summary Card (useMemo)
        │   ├── SectionHeader (title + subtitle)
        │   ├── BenchmarkSelector (shared component, top right)
        │   │   └── dropdown with checkboxes, max 5, +Compare label
        │   ├── Combined Score (score/100 + recommendation vs primary)
        │   ├── Quantitative Metrics grid
        │   │   ├── Alpha (fmtPct, emerald accent)
        │   │   ├── Beta (toFixed(2))
        │   │   ├── Sharpe Ratio (toFixed(2))
        │   │   └── Growth Score (X/3)
        │   └── Visual Signals grid
        │       ├── RS Trend (fmtPct)
        │       ├── Outperform Rate (fmtPct)
        │       └── Drawdown Ratio (toFixed(2))
        └── Charts Card (useMemo, conditional on data.charts)
            ├── Normalized Price Performance (LineChart, 300px)
            │   ├── Stock line (violet #8b5cf6)
            │   └── One Line per selected benchmark (color from BENCHMARK_COLORS)
            └── Relative Strength (LineChart, 200px)
                └── One RS line per selected benchmark (color from BENCHMARK_COLORS)
```

### 3.2 Component Responsibilities

| Component | File | Responsibility |
|-----------|------|---------------|
| `StockVsIndexPanel` | `components/stock-vs-index-panel.tsx` | Orchestrates data fetching via hook, manages `selectedBenchmarks` state, renders `BenchmarkSelector`, summary + charts, handles loading/error states |
| `useStockVsIndex` | `hooks/useStockVsIndex.ts` | TanStack Query wrapper, maps response to `{ loading, error, data }`, accepts `benchmarkSymbols: string[]` and `years` params |
| `useAnalysisBenchmarks` | `hooks/useStockVsIndex.ts` | TanStack Query wrapper for `GET /analysis/benchmarks`, returns `BenchmarkInfo[]` |
| `fetchStockVsIndex` | `services/analysis.service.ts` | `fetch()` to backend via proxy, comma-joins `benchmarkSymbols` into query param, throws on non-OK or invalid response |
| `fetchBenchmarks` | `services/analysis.service.ts` | `fetch()` to `GET /analysis/benchmarks`, returns `BenchmarkInfo[]` |
| `BenchmarkSelector` | `components/ui/benchmark-selector.tsx` | Shared dropdown with checkboxes, max 5 selection, used by both Portfolio Performance and Stock vs Index |
| `Metric` | `components/shared-ui.tsx` | Reusable stat tile: label, value, optional accent color |
| `SectionHeader` | `components/shared-ui.tsx` | Reusable section title + subtitle |
| `fmtPct` | `components/shared-ui.tsx` | Formats decimal as percentage string (`0.1505` → `"15.1%"`), returns `"—"` for null/NaN |
| `fmtInt` | `components/shared-ui.tsx` | Formats number as integer string, returns `"—"` for null/NaN |

### 3.3 Data Flow

```
Tab click → StockVsIndexPanel mounts
  → useAnalysisBenchmarks() → fetches available benchmarks
  → useStockVsIndex(symbol, ["SPY"]) called (default selection)
    → useQuery fires fetchStockVsIndex(symbol, ["SPY"], 3)
      → fetch() to /api/proxy/analysis/{symbol}/stock-vs-index?benchmark_symbols=SPY&years=3
        → returns StockVsIndexResponse JSON
      → cached under QK.stockVsIndex(symbol, ["SPY"], 3)
  → User toggles QQQ benchmark
    → selectedBenchmarks becomes ["SPY", "QQQ"]
    → useQuery fires fetchStockVsIndex(symbol, ["SPY", "QQQ"], 3)
      → fetch() to /api/proxy/analysis/{symbol}/stock-vs-index?benchmark_symbols=SPY,QQQ&years=3
      → cached under QK.stockVsIndex(symbol, ["QQQ", "SPY"], 3) (sorted)
  → Component renders:
    - Loading → MetricSkeleton (4 shimmer tiles)
    - Error   → AlertTriangle banner with error message
    - Success → Summary card + charts card (with multiple benchmark lines)
```

### 3.4 Query Key

```typescript
QK.stockVsIndex = (symbol: string, benchmarkSymbols: string[], years: number) =>
  ["stock-vs-index", symbol, ...benchmarkSymbols, years] as const;
```

- **Stale time:** `STALE.VALUATION` (10 min)
- **GC time:** `GC.VALUATION` (30 min)
- **Retry:** 1 attempt on failure
- **Enabled:** Only when `symbol` is non-empty AND `benchmarkSymbols.length > 0`

---

## 4. Backend Components

### 4.1 API Route

| Property | Value |
|----------|-------|
| Method | `GET` |
| Path | `/analysis/{symbol}/stock-vs-index` |
| Auth | Required (`get_current_user_dep`) |
| Rate limit | 30/minute |
| Query params | `benchmark_symbols` (default `"SPY"`, comma-separated tickers), `years` (default `3`, range 1–10) |
| Response | `Dict` matching `StockVsIndexResponse` shape |

**Additional endpoint:**
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/analysis/benchmarks` | Lists all active benchmarks from `benchmark_config` |

**Error mapping:**
| Exception | HTTP Status | Detail |
|-----------|-------------|--------|
| `ValueError` (symbol not found) | 404 | `"Symbol '{symbol}' not found"` |
| `ValueError` (none of benchmarks configured) | 404 | `"None of the requested benchmark symbols are configured"` |
| `ValueError` (insufficient price history) | 404 | `"Insufficient price history for analysis"` |
| Any other `Exception` | 500 | `"Stock vs index analysis failed."` |

### 4.2 Service Layer (`StockIndexComparisonService`)

**Constructor:**
```python
StockIndexComparisonService(repo: AnalysisRepository)
```

**Public method:**
```python
async def evaluate_outperformance(
    symbol: str,
    benchmark_symbols: Optional[List[str]] = None,
    years: int = 3,
) -> Dict[str, Any]:
```
- `benchmark_symbols` defaults to `["SPY"]` if None or empty
- First symbol is the **primary** benchmark — drives all scoring
- All symbols appear in chart data
- Each symbol is resolved via `get_benchmark_by_symbol()` in the repository

**Private methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `_quantitative_analysis` | `Dict` (beta, alpha, sharpe, growth, peg, score) | CAPM metrics + fundamental CAGR + PEG |
| `_visual_analysis` | `Dict` (rs_trend, outperform_rate, max_drawdowns, dd_ratio, score) | Relative strength, 12-month rolling outperformance, drawdown |
| `_prepare_chart_data` | `Dict` (dates, normalized_prices, relative_strength, rolling_12m_returns, drawdowns) | Time-series data for recharts |
| `_calculate_returns` | `List[float]` | Period-over-period returns |
| `_align_returns` | `Tuple[List, List]` | Truncates to shorter length |
| `_calculate_beta` | `float` | Cov(stock, index) / Var(index) via numpy |
| `_annualized_return` | `float` | (End/Start)^(1/years) − 1 |
| `_sharpe_ratio` | `float` | (Annual return − RFR) / (σ × √252) |
| `_calculate_fcf_growth` | `Optional[float]` | CAGR from cash flow statements |
| `_normalize_prices` | `List[float]` | Base 100: `p / p[0] * 100` |
| `_count_outperformance_months` | `int` | Count months where stock 12m return > index 12m return |
| `_max_drawdown` | `float` | Peak-to-trough decline |
| `_rolling_returns` | `List[Optional[float]]` | Rolling N-period returns |
| `_drawdown_series` | `List[float]` | Drawdown at each point |
| `_get_recommendation` | `str` | Maps combined score to human label |

### 4.3 Repository Layer (`AnalysisRepository`)

| Method | Table | Purpose |
|--------|-------|---------|
| `get_benchmark(role)` | `benchmark_config` | Resolves role → company_id, symbol |
| `get_benchmark_by_symbol(symbol)` | `benchmark_config` | Resolves ticker symbol → company_id (for multi-benchmark) |
| `get_all_active_benchmarks(market)` | `benchmark_config` | Returns all active benchmarks for a market |
| `get_price_history_range(company_id, start, end)` | `price_history` | Monthly price bars for date range |
| `get_revenue_and_eps_growth(company_id, years)` | `income_statements` (via `ValuationRepository`) | 3-year revenue + EPS CAGR |

### 4.4 Delegated Repository Methods (`ValuationRepository`)

| Method | Table | Purpose |
|--------|-------|---------|
| `get_company_context(symbol)` | `companies` | Resolves symbol → company_id |
| `get_income_statements_annual(company_id, limit)` | `income_statements` | Annual revenue, net income, shares |
| `get_fcf_history(company_id, years)` | `cash_flow_statements` | Annual OCF + capex → FCF |
| `get_company_summary_latest(company_id)` | `company_summary` | Trailing PE for PEG ratio |

---

## 5. Database Tables

### 5.1 `companies`
| Column | Type | Used For |
|--------|------|----------|
| `company_id` | `int` PK | Join key |
| `ticker_symbol` | `text` | Symbol resolution |
| `sector`, `industry` | `text` | Context (not currently used by this feature) |

### 5.2 `benchmark_config`
| Column | Type | Used For |
|--------|------|----------|
| `role` | `text` | Lookup key (`"us_market"`) |
| `company_id` | `int` FK → companies | Price history lookup |
| `symbol` | `text` | Display name (e.g. `"SPY"`) |
| `is_active` | `bool` | Only active benchmarks used |
| `market` | `text` | Market filter (`"US"`) |

### 5.3 `price_history`
| Column | Type | Used For |
|--------|------|----------|
| `company_id` | `int` FK | Filter |
| `price_date` | `date` | Date range filter |
| `close_price` | `decimal` | All return calculations |
| `high_price`, `low_price`, `volume` | `decimal` | Fetched but not used in current computations |

### 5.4 `income_statements`
| Column | Type | Used For |
|--------|------|----------|
| `company_id` | `int` FK | Filter |
| `fiscal_year` | `int` | CAGR period calculation |
| `revenue` | `decimal` | Revenue CAGR |
| `net_income` / `net_income_to_common` | `decimal` | EPS CAGR |
| `shares_outstanding_diluted` | `bigint` | Per-share EPS calculation |

### 5.5 `cash_flow_statements`
| Column | Type | Used For |
|--------|------|----------|
| `company_id` | `int` FK | Filter |
| `fiscal_year` | `int` | CAGR period |
| `cash_from_operating_activities` | `decimal` | FCF = OCF − Capex |
| `capital_expenditures` | `decimal` | FCF component |

### 5.6 `company_summary`
| Column | Type | Used For |
|--------|------|----------|
| `company_id` | `int` FK | Filter |
| `trailing_pe` | `decimal` | PEG ratio (PE / EPS growth) |

---

## 6. Scoring Methodology

### 6.1 Quantitative Score (60% of combined)

| Component | Weight | Condition | Rationale |
|-----------|--------|-----------|-----------|
| Alpha | 30% | `alpha > 0` | Positive alpha = stock beat CAPM expectation |
| Sharpe | 25% | `stock_sharpe > index_sharpe` | Better risk-adjusted return than index |
| Beta | 15% | `0.8 ≤ beta ≤ 1.2` | Near-market volatility (not excessively risky or defensive) |
| Growth | 20% | `growth_score / 3` | Revenue, EPS, or FCF CAGR > 12% (1.5× index avg of 8%) |
| PEG | 10% | `peg_ratio < 1.5` | Earnings growth justifies valuation |

**Growth score** (0–3): One point each for revenue CAGR > 12%, EPS CAGR > 12%, FCF CAGR > 12%.

### 6.2 Visual Score (40% of combined)

| Component | Weight | Condition | Rationale |
|-----------|--------|-----------|-----------|
| Outperform Rate | 40% | `outperform_rate > 0.6` | Stock beats index in >60% of rolling 12-month periods |
| RS Trend | 30% | `rs_trend > 0.15` | Relative strength line ascending (>15% gain over period) |
| Drawdown Ratio | 30% | `0.7 < dd_ratio < 1.0` | Stock drawdown not significantly worse than index |

### 6.3 Combined Score → Recommendation

| Range | Recommendation |
|-------|---------------|
| ≥ 0.80 | Strong Outperformance Signal |
| ≥ 0.65 | Likely Outperforms |
| ≥ 0.50 | Neutral / Mixed Signals |
| < 0.50 | Unlikely to Outperform |

### 6.4 Score Floor

Due to the beta component, the minimum quantitative score is 0.15 (if beta is between 0.8–1.2, which is common). The minimum visual score is 0.0.

---

## 7. Sequence Diagrams

### 7.1 Happy Path — Successful Analysis

```
User                    Frontend                  Backend                   Supabase
 │                         │                         │                         │
 │ click "Market Comp."    │                         │                         │
 │────────────────────────>│                         │                         │
 │                         │                         │                         │
 │                         │ useAnalysisBenchmarks() │                         │
 │                         │────────────────────────>│                         │
 │                         │ ← [{symbol:"SPY",...}...]│                         │
 │                         │                         │                         │
 │                         │ useStockVsIndex("RBLX", │                         │
 │                         │   ["SPY"])              │                         │
 │                         │ fetchStockVsIndex()     │                         │
 │                         │────────────────────────>│                         │
 │                         │                         │ get_company_context()   │
 │                         │                         │────────────────────────>│
 │                         │                         │ company_id=31          │
 │                         │                         │<────────────────────────│
 │                         │                         │                         │
 │                         │                         │ get_benchmark_by_symbol │
 │                         │                         │ ("SPY")                 │
 │                         │                         │────────────────────────>│
 │                         │                         │ SPY, company_id=61      │
 │                         │                         │<────────────────────────│
 │                         │                         │                         │
 │                         │                         │ get_price_history_range │
 │                         │                         │ (31, start, end)        │
 │                         │                         │────────────────────────>│
 │                         │                         │ 39 price rows           │
 │                         │                         │<────────────────────────│
 │                         │                         │                         │
 │                         │                         │ get_price_history_range │
 │                         │                         │ (61, start, end)        │
 │                         │                         │────────────────────────>│
 │                         │                         │ 38 price rows           │
 │                         │                         │<────────────────────────│
 │                         │                         │                         │
 │                         │                         │ (compute quant+visual   │
 │                         │                         │  vs primary SPY)         │
 │                         │                         │                         │
 │                         │ 200 OK (JSON response)  │                         │
 │                         │<────────────────────────│                         │
 │                         │                         │                         │
 │                         │ Render score + chart    │                         │
 │                         │ (SPY line in amber)     │                         │
 │ │<───────────────────────│                         │                         │
 │                         │                         │                         │
 │ toggle "QQQ"            │                         │                         │
 │────────────────────────>│                         │                         │
 │                         │                         │                         │
 │                         │ useStockVsIndex("RBLX", │                         │
 │                         │   ["SPY","QQQ"])        │                         │
 │                         │ fetchStockVsIndex()     │                         │
 │                         │────────────────────────>│                         │
 │                         │                         │ get_benchmark_by_symbol │
 │                         │                         │ ("SPY","QQQ")           │
 │                         │                         │────────────────────────>│
 │                         │                         │ SPY (id=61), QQQ (id=62)│
 │                         │                         │<────────────────────────│
 │                         │                         │                         │
 │                         │                         │ get_price_history_range │
 │                         │                         │ (stock, SPY, QQQ)       │
 │                         │                         │────────────────────────>│
 │                         │                         │ 3 sets of prices        │
 │                         │                         │<────────────────────────│
 │                         │                         │                         │
 │                         │                         │ (scoring vs SPY,        │
 │                         │                         │  chart data: all 3)     │
 │                         │                         │                         │
 │                         │ 200 OK (with QQQ data)  │                         │
 │                         │<────────────────────────│                         │
 │                         │                         │                         │
 │                         │ Re-render chart with    │                         │
 │                         │ SPY (amber) + QQQ       │                         │
 │                         │ (violet) lines          │                         │
 │ │<───────────────────────│                         │                         │
```

### 7.2 Error — Insufficient Price History

```
User                    Frontend                  Backend
 │                         │                         │
 │ click "Market Comp."    │                         │
 │────────────────────────>│                         │
 │                         │ fetchStockVsIndex()     │
 │                         │────────────────────────>│
 │                         │                         │ get_price_history_range
 │                         │                         │ → returns [] (no data)
 │                         │                         │
 │                         │                         │ raise ValueError(
 │                         │                         │   "Insufficient price ...")
 │                         │                         │
 │                         │ 404 {"detail": "Insufficient..."}
 │                         │<────────────────────────│
 │                         │                         │
 │                         │ throw Error("Insufficient...")
 │                         │                         │
 │                         │ retry (1 attempt)       │
 │                         │ ... same result         │
 │                         │                         │
 │                         │ React Query error state │
 │                         │                         │
 │ │<───────────────────────│                         │
 │ See error banner:       │                         │
 │ ⚠ Insufficient price    │                         │
 │   history for analysis  │                         │
```

### 7.3 Edge Case — Mismatched Price Row Counts (fixed)

```
Backend                    Supabase
 │                         │
 │ get_price_history_range │
 │ (stock)                 │
 │────────────────────────>│
 │ 39 rows                 │
 │<────────────────────────│
 │                         │
 │ get_price_history_range │
 │ (index)                 │
 │────────────────────────>│
 │ 38 rows                 │
 │<────────────────────────│
 │                         │
 │ ┌─ _visual_analysis     │
 │ │  min_len = min(39,38) │
 │ │  → 38                 │
 │ │  truncate both arrays │
 │ │  → safe computation   │
 │ └────────────────────── │
 │                         │
 │ ┌─ _prepare_chart_data  │
 │ │  min_len = 38         │
 │ │  truncate both arrays │
 │ │  → 38 dates, closes   │
 │ └────────────────────── │
```

---

## 8. Class Diagrams

### 8.1 Backend Class Diagram

```
┌───────────────────────────────┐
│  StockIndexComparisonService  │
├───────────────────────────────┤
│ - repo: AnalysisRepository    │
│ - RISK_FREE_RATE: float = 0.045│
├───────────────────────────────┤
│ + evaluate_outperformance()   │
│ - _quantitative_analysis()    │
│ - _visual_analysis()          │
│ - _prepare_chart_data()       │
│ - _calculate_returns()        │
│ - _align_returns()            │
│ - _calculate_beta()           │
│ - _annualized_return()        │
│ - _sharpe_ratio()             │
│ - _calculate_fcf_growth()     │
│ - _normalize_prices()         │
│ - _count_outperformance_months│
│ - _max_drawdown()             │
│ - _rolling_returns()          │
│ - _drawdown_series()          │
│ - _get_recommendation()       │
└───────────┬───────────────────┘
            │
            │ uses
            ▼
┌───────────────────────────────┐
│      AnalysisRepository       │
├───────────────────────────────┤
│ - _repo: ValuationRepository  │
├───────────────────────────────┤
│ + get_benchmark(role)         │
│ + get_all_active_benchmarks() │
│ + get_price_history_range()   │
│ + get_revenue_and_eps_growth()│
│ (plus MF, CANSlim methods)    │
└───────────┬───────────────────┘
            │
            │ delegates to
            ▼
┌───────────────────────────────┐
│    ValuationRepository        │
├───────────────────────────────┤
│ + get_company_context()       │
│ + get_company_summary_latest()│
│ + get_income_statements_annual│
│ + get_fcf_history()           │
│ (plus DCF, DDM, Rule#1, etc.) │
└───────────────────────────────┘
```

### 8.2 API Layer

```
┌──────────────────────────────────────────┐
│           analysis.py (router)           │
├──────────────────────────────────────────┤
│ _get_stock_vs_index_service()            │
│   → StockIndexComparisonService          │
│                                          │
│ GET /analysis/{symbol}/stock-vs-index    │
│   → get_stock_vs_index()                 │
│     → parse benchmark_symbols (split ",")│
│     → normalize symbol                   │
│     → evaluate_outperformance(symbol,    │
│         benchmark_symbols, years)        │
│     → return dict                        │
│                                          │
│ GET /analysis/benchmarks                 │
│   → list_benchmarks()                    │
│     → supabase.table("benchmark_config") │
│       .select().eq("is_active", true)    │
│     → return list                        │
└──────────────────────────────────────────┘
```

### 8.3 Frontend Class Diagram (TypeScript Interfaces)

```
┌─────────────────────────────┐
│   StockVsIndexResponse      │
├─────────────────────────────┤
│ symbol: string              │
│ primary_index: string       │  ← first selected benchmark
│ benchmarks: [{symbol,name}] │  ← all selected benchmarks
│ period_years: number        │
│ quantitative: Quant         │  ← scored vs primary_index
│ visual: Visual              │  ← scored vs primary_index
│ combined_score: number      │
│ recommendation: string      │
│ charts: Charts              │  ← data for ALL benchmarks
└─────────────────────────────┘
         │ 1          1 │
         ▼              ▼
┌──────────────────┐  ┌──────────────────────┐
│ StockVsIndexQuant│  │ StockVsIndexVis      │
├──────────────────┤  ├──────────────────────┤
│ beta: number     │  │ rs_trend: number     │
│ alpha: number    │  │ outperform_rate      │
│ stock_sharpe     │  │ stock_max_dd         │
│ index_sharpe     │  │ index_max_dd         │
│ growth_score     │  │ dd_ratio: number     │
│ revenue_cagr     │  │ score: number        │
│ eps_cagr         │  └──────────────────────┘
│ fcf_cagr         │
│ peg_ratio        │  ┌──────────────────────┐
│ score: number    │  │ StockVsIdxCharts     │
└──────────────────┘  ├──────────────────────┤
                       │ dates: string[]      │
                       │ normalized_prices    │
                       │  → Record<symbol,numbers> │
                       │ relative_strength    │
                       │  → Record<symbol,numbers> │
                       │ rolling_12m_returns  │
                       │ drawdowns            │
                       └──────────────────────┘
```

---

## 9. Alternate Scenarios & Error Handling

### 9.1 Symbol Not Found

**Trigger:** Symbol doesn't exist in `companies` table (e.g. nonexistent ticker)

**Backend:** `get_company_context` returns `None` → `ValueError("Symbol 'XXXX' not found")` → 404

**Frontend:** `fetchStockVsIndex` throws → React Query sets error state → error banner shows `"Symbol 'XXXX' not found"`

### 9.2 Benchmark Not Configured

**Trigger:** None of the requested `benchmark_symbols` match active `benchmark_config` rows

**Backend:** `get_benchmark_by_symbol` returns `None` for all → `ValueError("None of the requested benchmark symbols are configured: ...")` → 404

### 9.3 Insufficient Price History

**Trigger:** Stock or index has fewer than 2 price_history rows in the date range

**Backend:** Empty price list → `ValueError("Insufficient price history for analysis")` → 404

**Prevalence:** Newly listed stocks with <3 years of data (e.g. IPO this year)

### 9.4 Mismatched Price Row Counts (fixed)

**Trigger:** Stock and index have different numbers of monthly price rows (frequent — different listing dates)

**Backend (before fix):** `IndexError` in `_count_outperformance_months` → 500

**Backend (after fix):** Both `_visual_analysis` and `_prepare_chart_data` truncate to `min(len(stock), len(index))` → correct computation

**Prevalence:** Very common — almost every stock/index pair has slightly different dates

### 9.5 Missing Financial Data

**Scenario 1 — No income statements:** `get_revenue_and_eps_growth` returns `None` for both CAGRs → growth_score limited to FCF only (if available), or 0

**Scenario 2 — No cash flow statements:** `get_fcf_history` returns `[]` → `fcf_cagr = None` → growth_score limited to revenue/EPS

**Scenario 3 — No company_summary:** `trailing_pe` is `None` → `peg_ratio = None` → PEG component = 0

**All scenarios:** Graceful — metrics show `None` / 0 rather than crashing

### 9.6 Supabase 1000-Row Limit

**Risk:** Low — monthly EOM data for 10 years is ~120 rows

**Mitigation:** Not needed for current data volume, but if daily data is used in the future, `get_price_history_range` would need `.range()` pagination

### 9.7 Network Timeout

**Trigger:** Backend takes >20 seconds (the `doFetch` timeout)

**Frontend:** `fetchStockVsIndex` throws `"Network error..."` → React Query retries once → error banner shown

### 9.8 Backend 500 Error

**Trigger:** Any unhandled exception in the service

**Backend:** Caught by `except Exception` → logged with traceback → returns 500

**Frontend:** `fetchStockVsIndex` throws → error banner shows `"Stock vs index analysis failed."`

---

## 10. Test Plan

### 10.1 Unit Tests — Backend Service

#### Test: `evaluate_outperformance` — Happy Path

```python
async def test_happy_path_returns_all_fields():
    """Verify response shape matches StockVsIndexResponse."""
    service = StockIndexComparisonService(mock_repo)
    result = await service.evaluate_outperformance("AAPL")
    assert result["symbol"] == "AAPL"
    assert result["index"] == "SPY"
    assert result["period_years"] == 3
    assert "quantitative" in result
    assert "visual" in result
    assert "charts" in result
    assert 0 <= result["combined_score"] <= 1
```

#### Test: Symbol Not Found

```python
async def test_unknown_symbol_raises():
    mock_repo._repo.get_company_context.return_value = None
    service = StockIndexComparisonService(mock_repo)
    with pytest.raises(ValueError, match="not found"):
        await service.evaluate_outperformance("NONEXISTENT")
```

#### Test: Benchmark Not Configured

```python
async def test_missing_benchmark_raises():
    mock_repo.get_benchmark.return_value = None
    service = StockIndexComparisonService(mock_repo)
    with pytest.raises(ValueError, match="not configured"):
        await service.evaluate_outperformance("AAPL", index_role="invalid_role")
```

#### Test: Insufficient Price History

```python
async def test_empty_prices_raises():
    mock_repo.get_price_history_range.return_value = []
    service = StockIndexComparisonService(mock_repo)
    with pytest.raises(ValueError, match="Insufficient price history"):
        await service.evaluate_outperformance("AAPL")
```

#### Test: Mismatched Row Counts (the IndexError fix)

```python
async def test_mismatched_price_counts_does_not_crash():
    """Stock has 39 rows, index has 38 — must not raise IndexError."""
    stock_prices = [{"price_date": ..., "close_price": ...}] * 39
    index_prices = [{"price_date": ..., "close_price": ...}] * 38
    mock_repo.get_price_history_range.side_effect = [stock_prices, index_prices]
    service = StockIndexComparisonService(mock_repo)
    result = await service.evaluate_outperformance("RBLX")
    assert len(result["charts"]["dates"]) == 38  # truncated
```

#### Test: Beta Edge Cases

```python
async def test_beta_defaults_to_one():
    """With <2 returns, beta defaults to 1.0."""
    prices = [{"price_date": "2024-01-01", "close_price": 100}]
    assert service._calculate_beta([], []) == 1.0
```

```python
async def test_beta_with_single_element():
    assert service._calculate_beta([0.01], [0.02]) == 1.0
```

#### Test: Sharpe Ratio Edge Cases

```python
async def test_sharpe_empty_returns_zero():
    assert service._sharpe_ratio([], 0.1) == 0.0
```

```python
async def test_sharpe_zero_std_returns_zero():
    assert service._sharpe_ratio([0.01, 0.01, 0.01], 0.1) == 0.0
```

#### Test: Annualized Return Edge Cases

```python
async def test_annualized_return_single_price():
    prices = [{"price_date": "2024-01-01", "close_price": 100}]
    assert service._annualized_return(prices) == 0.0
```

```python
async def test_annualized_return_negative_start():
    prices = [
        {"price_date": "2024-01-01", "close_price": -1},
        {"price_date": "2025-01-01", "close_price": 100},
    ]
    assert service._annualized_return(prices) == 0.0
```

#### Test: FCF Growth Edge Cases

```python
async def test_fcf_growth_less_than_two_years():
    assert service._calculate_fcf_growth([{"fiscal_year": 2024, "fcf": 100}]) is None
```

```python
async def test_fcf_growth_negative_start():
    data = [
        {"fiscal_year": 2022, "fcf": -10},
        {"fiscal_year": 2024, "fcf": 100},
    ]
    assert service._calculate_fcf_growth(data) is None
```

#### Test: Outperformance Count with <12 Months

```python
async def test_outperformance_count_fewer_than_12_months():
    prices = [{"close_price": 100}] * 11
    assert service._count_outperformance_months(prices, prices) == 0
```

#### Test: Multi-Benchmark — Chart Data Contains All Benchmarks

```python
async def test_multi_benchmark_chart_data():
    """When evaluating against SPY+QQQ, charts should contain both."""
    spy_cfg = {"symbol": "SPY", "company_id": 61, "name": "SPDR S&P 500"}
    qqq_cfg = {"symbol": "QQQ", "company_id": 62, "name": "Invesco QQQ"}
    mock_repo.get_benchmark_by_symbol.side_effect = [spy_cfg, qqq_cfg]
    mock_repo.get_price_history_range.return_value = mock_prices(40)
    service = StockIndexComparisonService(mock_repo)
    result = await service.evaluate_outperformance("AAPL", ["SPY", "QQQ"])
    assert result["primary_index"] == "SPY"
    assert len(result["benchmarks"]) == 2
    assert "SPY" in result["charts"]["normalized_prices"]
    assert "QQQ" in result["charts"]["normalized_prices"]
    assert "SPY" in result["charts"]["relative_strength"]
    assert "QQQ" in result["charts"]["relative_strength"]
```

#### Test: Multi-Benchmark — First Symbol Drives Scoring

```python
async def test_multi_benchmark_scoring_uses_primary():
    """Scoring should be based on the first (primary) benchmark only."""
    spy_cfg = {"symbol": "SPY", "company_id": 61}
    qqq_cfg = {"symbol": "QQQ", "company_id": 62}
    mock_repo.get_benchmark_by_symbol.side_effect = [spy_cfg, qqq_cfg]
    mock_repo.get_price_history_range.return_value = mock_prices(40)
    service = StockIndexComparisonService(mock_repo)
    result = await service.evaluate_outperformance("AAPL", ["SPY", "QQQ"])
    # quantitative + visual scores should correspond to SPY (not QQQ)
    assert result["quantitative"]["score"] > 0  # scored vs SPY
```

#### Test: Recommendation Boundaries

```python
@pytest.mark.parametrize("score,expected", [
    (0.85, "Strong Outperformance Signal"),
    (0.70, "Likely Outperforms"),
    (0.55, "Neutral / Mixed Signals"),
    (0.30, "Unlikely to Outperform"),
])
def test_recommendation_boundaries(score, expected):
    assert service._get_recommendation(score) == expected
```

### 10.2 Unit Tests — Frontend

#### Test: `fmtPct` formatter

```typescript
describe("fmtPct", () => {
  it("formats decimal as percentage", () => {
    expect(fmtPct(0.1505)).toBe("15.1%");
  });
  it("handles null", () => {
    expect(fmtPct(null)).toBe("—");
  });
  it("handles NaN", () => {
    expect(fmtPct(NaN)).toBe("—");
  });
});
```

#### Test: `fetchStockVsIndex` error handling

```typescript
describe("fetchStockVsIndex", () => {
  it("throws on 500 response", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({ detail: "Server error" }) });
    await expect(fetchStockVsIndex("AAPL")).rejects.toThrow("Server error");
  });
  it("throws on network error", async () => {
    mockFetch.mockRejectedValue(new Error("Network error"));
    await expect(fetchStockVsIndex("AAPL")).rejects.toThrow("Network error");
  });
});
```

### 10.3 Integration Tests

#### API Endpoint (backend)

```python
async def test_api_returns_200_for_valid_symbol(client):
    """Full integration: route → service → Supabase."""
    response = await client.get("/AAPL/stock-vs-index?index_role=us_market&years=3")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert data["index"] == "SPY"
    assert len(data["charts"]["dates"]) > 0
```

```python
async def test_api_returns_404_for_invalid_symbol(client):
    response = await client.get("/NONEXISTENT/stock-vs-index")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
```

```python
async def test_api_returns_404_for_no_price_data(client):
    """Newly listed stock with no price_history yet."""
    # Use a symbol that exists in companies but has no price_history
    response = await client.get("/SOME_NEW_SYMBOL/stock-vs-index")
    assert response.status_code == 404
```

#### Frontend + Backend (proxy)

```typescript
describe("StockVsIndexPanel integration", () => {
  it("renders metrics after successful fetch", async () => {
    mockFetch.mockResolvedValue(mockValidResponse);
    render(<StockVsIndexPanel symbol="AAPL" />);
    await waitFor(() => {
      expect(screen.getByText(/Combined Score/)).toBeInTheDocument();
      expect(screen.getByText(/Alpha/)).toBeInTheDocument();
    });
  });
  it("renders error banner on 404", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "not found" }) });
    render(<StockVsIndexPanel symbol="NONEXISTENT" />);
    await waitFor(() => {
      expect(screen.getByText(/not found/)).toBeInTheDocument();
    });
  });
});
```

### 10.4 E2E Test Checklist

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| 1 | Stock outperforms | Navigate to a strong stock (e.g. NVDA 3yr) | Score > 50, positive alpha, charts show stock above index |
| 2 | Stock underperforms | Navigate to a weak stock (e.g. RBLX 3yr) | Score < 50, negative alpha, charts show stock below index |
| 3 | New stock (no financials) | Navigate to IPO stock | Growth score 0/3, PEG shows "—", rest computed from prices only |
| 4 | 1-year window | `years=1` | Shorter charts, fewer data points |
| 5 | 10-year window | `years=10` | Longest charts, more data points |
| 6 | Invalid symbol | Navigate to `ZZZZZ` | Error banner: "Symbol 'ZZZZZ' not found" |
| 7 | Loading state | Slow network (throttle to Slow 3G) | MetricSkeleton shimmer visible |
| 8 | Error recovery | First request fails, second succeeds | Data renders after retry |
| 9 | Cache hit | Navigate to same symbol twice | Second load is instant (no network request) |
| 10 | Mobile viewport | 375px width | Grid stacks to single column, charts responsive |
| 11 | Multi-benchmark selection | Toggle SPY + QQQ + IWM | Chart shows 3 colored lines (amber, violet, pink) matching Portfolio Performance colors |
| 12 | Add benchmark after initial load | Start with SPY, then toggle QQQ | New API call fires with both symbols, chart updates with QQQ line |
| 13 | Remove all but one benchmark | Deselect QQQ, keep only SPY | Single API call with just SPY, chart reverts to single line |
| 14 | Max benchmarks (5) | Toggle all 5: SPY, QQQ, IWM, VTI, DIA | Dropdown shows "Max 5 benchmarks", +Compare button shows "SPY +4" |
| 15 | Benchmark list fetch fails | Backend /analysis/benchmarks returns error | Dropdown is hidden (empty benchmark list), default SPY comparison still works |

---

## Appendix: Response JSON Shape

```json
{
  "symbol": "RBLX",
  "primary_index": "SPY",
  "benchmarks": [
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust"}
  ],
  "period_years": 3,
  "quantitative": {
    "beta": 0.989,
    "alpha": -0.1505,
    "stock_sharpe": 0.005,
    "index_sharpe": 0.276,
    "growth_score": 1,
    "revenue_cagr": 0.3002,
    "eps_cagr": null,
    "fcf_cagr": null,
    "peg_ratio": null,
    "score": 0.217
  },
  "visual": {
    "rs_trend": -0.129,
    "outperform_rate": 0.421,
    "stock_max_drawdown": 0.6011,
    "index_max_drawdown": 0.0865,
    "dd_ratio": 6.95,
    "score": 0.0
  },
  "combined_score": 0.13,
  "recommendation": "Unlikely to Outperform",
  "charts": {
    "dates": ["2023-04-28", ...],
    "normalized_prices": {
      "RBLX": [100.0, ...],
      "SPY": [100.0, ...],
      "QQQ": [100.0, ...]
    },
    "relative_strength": {
      "SPY": [100.0, ...],
      "QQQ": [100.0, ...]
    },
    "rolling_12m_returns": {
      "RBLX": [null, ..., 0.05, ...],
      "SPY": [null, ..., 0.12, ...],
      "QQQ": [null, ..., 0.15, ...]
    },
    "drawdowns": {
      "RBLX": [0.0, ..., -60.1, ...],
      "SPY": [0.0, ..., -8.7, ...],
      "QQQ": [0.0, ..., -12.3, ...]
    }
  }
}
```
