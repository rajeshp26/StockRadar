# Portfolio Performance — Feasibility Analysis

> **Date:** 2026-05-28 (Updated)
> **Scope:** Full-stack feasibility of implementing advanced portfolio performance analytics (return metrics, risk metrics, relationship metrics, risk-adjusted metrics, visualizations) for the Portfolio page
> **Methodology:** Trace each required metric from professional portfolio analytics back to existing database columns, API endpoints, services, types, and frontend components

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Walkthrough](#2-architecture-walkthrough)
3. [Metric Availability Matrix](#3-metric-availability-matrix)
4. [Existing Implementation Details](#4-existing-implementation-details)
5. [Gap Analysis — What Is Missing](#5-gap-analysis--what-is-missing)
6. [Data Dependencies](#6-data-dependencies)
7. [API Design](#7-api-design)
8. [Visualization Strategy](#8-visualization-strategy)
9. [Frontend State & Caching](#9-frontend-state--caching)
10. [Implementation Effort Estimate](#10-implementation-effort-estimate)
11. [Complete Gap Inventory](#11-complete-gap-inventory)
12. [Recommended Phasing](#12-recommended-phasing)

---

## 1. Executive Summary

**Verdict: FEASIBLE** — ~30% of the required portfolio performance metrics already exist in the codebase. The backend has strong infrastructure (FIFO lot tracking, portfolio snapshots, historical prices, benchmark comparison) but lacks statistical risk metrics (variance, covariance, correlation, Sortino, Max Drawdown, VaR, Efficient Frontier). The frontend has a well-structured Performance tab with recharts-based visualizations but limited to value-over-time and benchmark overlay charts.

**What exists today:**
- Total return ($ and %), best/worst day via `portfolio_service.py:1498-1779`
- Benchmark comparison (normalized value series) via `portfolio_service.py:1991-2090`
- Allocation breakdown by sector/geography/account via `portfolio_service.py:1905-1982`
- Portfolio snapshots (date, value, cost_basis, net_deposits) stored in `portfolio_snapshots` table
- FIFO-based cost basis tracking with per-holding unrealized/realized P&L
- Recharts-based frontend with ComposedChart serving as the visualization foundation

**What must be built:**
- Statistical risk engine: variance, std dev, covariance matrix, correlation matrix
- Risk-adjusted metrics: Sharpe ratio (already partially exists — verify scope), Sortino ratio, Max Drawdown, Value at Risk (VaR)
- Portfolio optimization: Efficient Frontier, Minimum Variance Portfolio, Risk Contribution
- Advanced visualizations: Correlation heatmap, Drawdown chart, Rolling Sharpe, Treemap, Scatter plot, Diversification wheel, Risk pyramid, Factor exposure
- New API endpoints, Pydantic schemas, frontend types, hooks, and visualization components

**Primary gaps and how they'll be filled:**
- **Variance / Std Dev** → New statistical function in `shared/finance_math.py` + new endpoint
- **Covariance / Correlation matrix** → New service module using `numpy.cov` / `pandas.DataFrame.corr`
- **Sortino Ratio** → Compute downside deviation from negative returns in period
- **Max Drawdown** → Walk portfolio snapshot series, find peak-to-trough decline
- **VaR (Historical / Parametric)** → Use percentile of return distribution or std-dev-based parametric formula
- **Efficient Frontier** → Monte Carlo simulation or scipy.optimize with covariance matrix
- **Visualizations** → Extend recharts or add Plotly for heatmaps; implement new chart components

**Data sufficiency:**
- Price history (`company_prices` table): sufficient for daily return data over time
- Portfolio snapshots (`portfolio_snapshots` table): sufficient for time-series portfolio valuation
- Company financial ratios (`company_financial_ratios`): available for factor analysis
- Holdings data (current positions + lot-level cost basis): available for allocation/weight computation

---

## 2. Architecture Walkthrough

### 2.1 Existing Pattern (to replicate)

Every portfolio feature follows a standard 4-layer architecture:

```
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND (Next.js / TypeScript / recharts)                   │
│                                                              │
│  PerformanceTab.tsx (tabs/period selector)                   │
│    └─ usePortfolioPerformance(period, accountIds)            │
│         └─ portfolioService.getPortfolioPerformance()        │
│              └─ GET /api/proxy/portfolio/performance         │
│                                                              │
│  PortfolioPerformanceChart.tsx                               │
│    └─ ComposedChart (recharts)                               │
│         ├─ Area: Portfolio Value                             │
│         ├─ Area: Net Deposits                                │
│         └─ Line: Benchmarks (per selected symbol)            │
│                                                              │
│  React Query Cache (QK.portfolio*)                           │
│    - Stale time: STALE.PORTFOLIO                             │
│    - GC time: GC.PORTFOLIO                                   │
└───────────────────────────────┬──────────────────────────────┘
                               │ same-origin proxy
                               │ (web/src/app/api/proxy/[...path]/route.ts)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ BACKEND (FastAPI / Python)                                   │
│                                                              │
│  api/portfolio.py                                            │
│    ├─ GET /portfolio/performance  → PerformanceResponse     │
│    ├─ GET /portfolio/performance/compare → BenchmarkCompare  │
│    └─ GET /portfolio/allocation    → AllocationResponse     │
│                                                              │
│  application/services/portfolio_service.py                   │
│    ├─ get_portfolio_performance()   - time-series snapshots  │
│    ├─ get_performance_compare()      - vs benchmark indices  │
│    ├─ get_portfolio_allocation()     - sector/geo/account    │
│    ├─ get_user_portfolio_overview()  - summary statistics    │
│    └─ enrich_holdings_with_prices()  - live + historical     │
│                                                              │
│  infrastructure/repositories/portfolio_repository.py         │
│    - portfolio_snapshots CRUD                                │
│    - company_prices queries                                  │
│    - portfolio_transactions, holdings, dividends access      │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Proposed New Architecture

New components needed for advanced portfolio analytics:

```
┌──────────────────────────────────────────────────────────────────┐
│ FRONTEND (NEW)                                                    │
│                                                                   │
│  PerformanceTab.tsx                                               │
│    └─ Sub-tabs: Performance | Risk Metrics | Correlations         │
│         | Drawdown | Efficient Frontier | Factor Exposure         │
│                                                                   │
│  NEW HOOKS:                                                        │
│    ├─ usePortfolioRiskMetrics(period, accountIds)                 │
│    ├─ usePortfolioCovariance(period, accountIds)                  │
│    ├─ usePortfolioDrawdown(period, accountIds)                    │
│    ├─ usePortfolioEfficientFrontier(accountIds, points)           │
│    ├─ usePortfolioRollingSharpe(window, accountIds)               │
│    ├─ usePortfolioFactorExposure(accountIds)                      │
│    └─ usePortfolioRiskContribution(accountIds)                    │
│                                                                   │
│  NEW COMPONENTS:                                                   │
│    ├─ RiskMetricCard.tsx                  - KPI grid              │
│    ├─ CovarianceHeatmap.tsx               - color-coded matrix    │
│    ├─ CorrelationHeatmap.tsx              - color-coded matrix    │
│    ├─ DrawdownChart.tsx                   - underwater chart      │
│    ├─ RollingSharpeChart.tsx              - line chart            │
│    ├─ EfficientFrontierChart.tsx          - scatter + CML         │
│    ├─ PortfolioTreemap.tsx                - allocation treemap    │
│    ├─ VolatilityVsReturnScatter.tsx       - bubble chart          │
│    ├─ FactorExposureChart.tsx             - bar chart             │
│    ├─ DiversificationWheel.tsx            - polar/radial chart    │
│    └─ RiskPyramid.tsx                     - layered risk viz      │
│                                                                   │
│  NEW SERVICE FUNCTIONS:                                            │
│    ├─ getPortfolioRiskMetrics()           - risk endpoint         │
│    ├─ getPortfolioCovariance()            - cov matrix endpoint   │
│    ├─ getPortfolioDrawdown()              - drawdown endpoint     │
│    ├─ getPortfolioEfficientFrontier()     - frontier endpoint     │
│    └─ getPortfolioFactorExposure()        - factor endpoint       │
└───────────────────────────────┬──────────────────────────────────┘
                               │ proxy
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ BACKEND (NEW)                                                     │
│                                                                   │
│  NEW: application/services/portfolio_risk_service.py              │
│    ├─ compute_portfolio_variance()                                │
│    ├─ compute_covariance_matrix()                                 │
│    ├─ compute_correlation_matrix()                                │
│    ├─ compute_sharpe_ratio()                                      │
│    ├─ compute_sortino_ratio()                                     │
│    ├─ compute_max_drawdown()                                      │
│    ├─ compute_value_at_risk()                                     │
│    ├─ compute_rolling_sharpe()                                    │
│    ├─ compute_efficient_frontier()                                │
│    ├─ compute_risk_contribution()                                 │
│    └─ compute_factor_exposure()                                   │
│                                                                   │
│  NEW: shared/portfolio_stats.py                                   │
│    - Pure math functions (no DB dependencies)                     │
│    - numpy/pandas-based statistical computations                  │
│                                                                   │
│  NEW API endpoints in api/portfolio.py:                            │
│    ├─ GET /portfolio/risk-metrics                                 │
│    ├─ GET /portfolio/covariance                                   │
│    ├─ GET /portfolio/drawdown                                     │
│    ├─ GET /portfolio/efficient-frontier                           │
│    ├─ GET /portfolio/rolling-sharpe                               │
│    ├─ GET /portfolio/risk-contribution                            │
│    └─ GET /portfolio/factor-exposure                              │
│                                                                   │
│  NEW Pydantic schemas in schemas_portfolio.py:                     │
│    ├─ RiskMetricsResponse                                         │
│    ├─ CovarianceResponse                                          │
│    ├─ DrawdownResponse                                            │
│    ├─ EfficientFrontierResponse                                   │
│    ├─ RollingSharpeResponse                                       │
│    ├─ RiskContributionResponse                                    │
│    └─ FactorExposureResponse                                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Metric Availability Matrix

| Metric | Existing Status | Where | Gap |
|---|---|---|---|
| **Return Metrics** | | | |
| Portfolio Total Return ($) | ✅ EXISTS | `portfolio_service.py:1754` | |
| Portfolio Total Return (%) | ✅ EXISTS | `portfolio_service.py:1755` | |
| Best Day / Worst Day | ✅ EXISTS | `portfolio_service.py:1758-1769` | |
| Time-Weighted Return | ❌ MISSING | — | Implement linking method |
| Money-Weighted Return (IRR) | ❌ MISSING | — | Requires scipy.optimize or manual XIRR |
| **Risk Metrics** | | | |
| Variance | ❌ MISSING | — | New compute function |
| Standard Deviation | ❌ MISSING | — | New compute function |
| Max Drawdown ($ and %) | ❌ MISSING | — | Walk snapshot series |
| Value at Risk (VaR 95/99) | ❌ MISSING | — | Parametric or historical |
| Conditional VaR (CVaR) | ❌ MISSING | — | Extension of VaR |
| Downside Deviation | ❌ MISSING | — | Needed for Sortino |
| **Relationship Metrics** | | | |
| Covariance Matrix | ❌ MISSING | — | numpy.cov on price returns |
| Correlation Matrix | ❌ MISSING | — | pandas corr or Pearson |
| Beta (portfolio vs benchmark) | ⚠️ PARTIAL | `portfolio_service` (verify) | May exist in comparison flow |
| **Risk-Adjusted Metrics** | | | |
| Sharpe Ratio | ⚠️ PARTIAL | Mentioned in codebase (verify exact location) | Confirm scope — may need extension |
| Sortino Ratio | ❌ MISSING | — | Requires downside deviation |
| Treynor Ratio | ❌ MISSING | — | Requires portfolio beta |
| Information Ratio | ❌ MISSING | — | Requires active return vs benchmark |
| **Portfolio Optimization** | | | |
| Efficient Frontier | ❌ MISSING | — | scipy.optimize + cov matrix |
| Minimum Variance Portfolio | ❌ MISSING | — | Derivative of frontier |
| Risk Contribution (Risk Budgeting) | ❌ MISSING | — | Marginal/component VaR |
| **Factor Analysis** | | | |
| Factor Exposures | ❌ MISSING | — | Regression model |
| Style Analysis | ❌ MISSING | — | Returns-based style analysis |

---

## 4. Existing Implementation Details

### 4.1 Backend Service — `portfolio_service.py`

**`get_portfolio_performance()`** (lines 1498–1779):
- Accepts `user_id`, `period` (1D/1W/1M/3M/1Y/5Y/ALL), optional `account_ids`
- Resolves date range via `_period_to_date_range()` (inclusive of all transactions)
- Enumerates all user transactions in date order
- Uses `_calculate_symbol_holding_fifo()` for lot-level cost basis tracking
- Builds daily/weekly/monthly snapshots of `{date, value, cost_basis, net_deposits}`
- Returns `total_return` (last snapshot value - first snapshot cost_basis)
- Returns `total_return_pct` (absolute return divided by initial cost basis × 100)
- Returns `best_day` / `worst_day` as `{date, return_pct}` objects
- Data source: `portfolio_transactions` and `portfolio_snapshots` tables

**`get_performance_compare()`** (lines 1991–2090):
- Accepts `user_id`, `period`, `benchmark_symbols[]`, optional `account_ids`
- Gets portfolio performance via `get_portfolio_performance()`
- Queries historical prices for each benchmark symbol
- Simulates "same cash flows" approach — what each benchmark would be worth with same deposits/withdrawals
- Returns normalized series for side-by-side charting

**`get_portfolio_allocation()`** (lines 1905–1982):
- Group by options: `sector`, `geography`, `account`
- Returns `{segment, value, weight, count, gain_loss}` per group

**`get_user_portfolio_overview()`** (line 968):
- Returns net worth, total cost basis, gain/loss ($ and %), YTD dividends, holdings count, top holdings, per-account breakdown

### 4.2 Backend API — `api/portfolio.py`

| Endpoint | Route | Status |
|---|---|---|
| List brokerages | `GET /portfolio/brokerages` | ✅ |
| List accounts | `GET /portfolio/accounts` | ✅ |
| Account holdings | `GET /portfolio/accounts/{id}/holdings` | ✅ |
| All holdings | `GET /portfolio/holdings` | ✅ |
| Portfolio overview | `GET /portfolio/overview` | ✅ |
| Account transactions | `GET /portfolio/accounts/{id}/transactions` | ✅ |
| All transactions | `GET /portfolio/transactions` | ✅ |
| Account dividends | `GET /portfolio/accounts/{id}/dividends` | ✅ |
| All dividends | `GET /portfolio/dividends` | ✅ |
| Dividend history | `GET /portfolio/accounts/{id}/dividend-history` | ✅ |
| **Portfolio performance** | **`GET /portfolio/performance`** | ✅ |
| **Performance compare** | **`GET /portfolio/performance/compare`** | ✅ |
| **Portfolio allocation** | **`GET /portfolio/allocation`** | ✅ |
| Manual transaction | `POST /portfolio/transactions/manual` | ✅ |
| Import transactions | `POST /portfolio/import` | ✅ |
| Import status | `GET /portfolio/import/{batch_id}/status` | ✅ |
| Import history | `GET /portfolio/import-history` | ✅ |
| Delete account | `DELETE /portfolio/accounts/{id}` | ✅ |
| List benchmarks | `GET /benchmarks` | ✅ |
| Company search | `GET /companies/search` | ✅ |

### 4.3 Pydantic Schemas — `schemas_portfolio.py`

Existing relevant schemas:

```python
class PerformanceSnapshot(BaseModel):   # lines 281-287
    date: str; value: float; cost_basis: float; net_deposits: float

class PerformanceResponse(BaseModel):    # lines 290-301
    success: bool; period: str; snapshots: List[PerformanceSnapshot]
    total_return: float; total_return_pct: float
    best_day: Optional[Dict]; worst_day: Optional[Dict]; error: Optional[str]

class BenchmarkSeries(BaseModel):        # lines 321-326
    symbol: str; name: str; data: List[Dict[str, Any]]

class BenchmarkCompareResponse(BaseModel):  # lines 329-336
    success: bool; period: str; portfolio: List[Dict]; benchmarks: List[BenchmarkSeries]

class AllocationSegment(BaseModel):     # lines 343-350
    segment: str; value: float; weight: float; count: int; gain_loss: float

class PortfolioAllocationResponse(BaseModel): # lines 353-360
    success: bool; group_by: str; segments: List[AllocationSegment]; total_value: float
```

### 4.4 Frontend Types — `portfolio.types.ts`

```typescript
interface PerformanceResponse {         // lines 174-183
    success: boolean; period: string; snapshots: PerformanceSnapshot[];
    total_return: number; total_return_pct: number;
    best_day: { date: string; return_pct: number } | null;
    worst_day: { date: string; return_pct: number } | null;
    error?: string;
}

interface PerformanceSnapshot {          // lines 167-172
    date: string; value: number; cost_basis: number; net_deposits: number;
}

interface BenchmarkCompareResponse {     // lines 193-199
    success: boolean; period: string;
    portfolio: { date: string; value: number }[];
    benchmarks: BenchmarkSeries[]; error?: string;
}

interface PortfolioAllocationResponse {  // lines 235-241
    success: boolean; group_by: string; segments: AllocationSegment[];
    total_value: number; error?: string;
}
```

### 4.5 Frontend Hooks — `usePortfolio.ts`

| Hook | Line | Returns |
|---|---|---|
| `usePortfolioPerformance(period, accountIds)` | 159 | `PerformanceResponse` |
| `useBenchmarkCompare(period, benchmarks, accountIds)` | 193 | `BenchmarkCompareResponse` |
| `usePortfolioAllocation(groupBy, accountIds)` | 235 | `PortfolioAllocationResponse` |
| `useAllDividends(accountIds)` | 255 | Dividend summaries |
| `useAllTransactions(accountIds, filter)` | 315 | Transaction list |

### 4.6 Frontend Visualizations — Existing

| Component | File | Type | Description |
|---|---|---|---|
| `PortfolioPerformanceChart` | `PortfolioPerformanceChart.tsx` | ComposedChart | Area: portfolio value + net deposits; Line: benchmarks |
| `BenchmarkComparisonChart` | `BenchmarkComparisonChart.tsx` | ComposedChart | Area: portfolio; Line: per-benchmark |
| `PerformanceTab` | `PerformanceTab.tsx` | Composite | Period selector + both charts |

The existing visualizations use **recharts** (`ComposedChart`, `Area`, `Line`, `XAxis`, `YAxis`, `Tooltip`, `CartesianGrid`, `ResponsiveContainer`, `Legend`). The styling uses a dark glassmorphism theme consistent with the app.

---

## 5. Gap Analysis — What Is Missing

### 5.1 Statistical Risk Engine (Backend)

**No statistical/risk computation currently exists** in the codebase. The `portfolio_service.py` does not import numpy, scipy, or pandas for statistical calculations. No module computes:

- **Variance / Standard Deviation**: The most basic risk metric. Requires daily/multi-period return series computed from portfolio snapshot values.

- **Covariance / Correlation Matrix**: Requires aligned daily return series for each holding in the portfolio, spanning the same time period.

- **Sortino Ratio**: Requires downside deviation (standard deviation of negative returns). Formula: `(portfolio_return - risk_free_rate) / downside_deviation`.

- **Max Drawdown**: Requires iterating through portfolio value series tracking the running maximum and computing peak-to-trough decline.

- **Value at Risk (VaR)**: Two approaches needed:
  - *Parametric VaR*: `μ - z × σ` where z depends on confidence level (1.645 for 95%, 2.326 for 99%)
  - *Historical VaR*: Take percentile of historical return distribution

- **Conditional VaR / Expected Shortfall**: Average of returns beyond VaR threshold.

- **Efficient Frontier**: Requires:
  - Expected returns for each holding
  - Covariance matrix
  - Scipy optimizer (`scipy.optimize.minimize`) to find optimal weights for different risk levels
  - Capital Market Line (CML) from risk-free rate tangent to frontier

- **Risk Contribution**: Marginal contribution to risk = `(weight × covariance with portfolio) / portfolio_variance`

- **Rolling Metrics**: Rolling Sharpe, rolling volatility — computed over a sliding window of the return series.

- **Factor Exposure**: Regression of portfolio returns against factor returns (market, size, value, momentum, etc.)

**Key files to create:**
- `backend/shared/portfolio_stats.py` — pure math functions
- `backend/application/services/portfolio_risk_service.py` — service with DB access

### 5.2 API Endpoints (Backend)

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /portfolio/risk-metrics` | New | Return all computed risk metrics for the portfolio |
| `GET /portfolio/covariance` | New | Return covariance/correlation matrix |
| `GET /portfolio/drawdown` | New | Return drawdown time series |
| `GET /portfolio/efficient-frontier` | New | Return efficient frontier points |
| `GET /portfolio/rolling-sharpe` | New | Return rolling Sharpe ratio time series |
| `GET /portfolio/risk-contribution` | New | Return risk contribution per holding |
| `GET /portfolio/factor-exposure` | New | Return factor exposures |

### 5.3 Pydantic Schemas (Backend)

New schemas needed in `schemas_portfolio.py`:

```python
class RiskMetricsResponse(BaseModel):
    success: bool; period: str
    variance: float; std_deviation: float
    sharpe_ratio: float; sortino_ratio: float
    max_drawdown: float; max_drawdown_pct: float
    value_at_risk_95: float; value_at_risk_99: float
    conditional_var_95: float
    downside_deviation: float
    tracking_error: Optional[float]
    information_ratio: Optional[float]
    beta: Optional[float]; alpha: Optional[float]
    error: Optional[str]

class CovarianceResponse(BaseModel):
    success: bool; period: str
    holdings: List[str]
    covariance_matrix: List[List[float]]
    correlation_matrix: List[List[float]]
    error: Optional[str]

class DrawdownResponse(BaseModel):
    success: bool; period: str
    drawdowns: List[Dict[str, Any]]
    max_drawdown: float; max_drawdown_pct: float
    max_drawdown_start: Optional[str]
    max_drawdown_end: Optional[str]
    max_drawdown_recovery: Optional[str]
    avg_drawdown: float
    error: Optional[str]

class EfficientFrontierPoint(BaseModel):
    volatility: float; expected_return: float
    weights: Dict[str, float]
    sharpe_ratio: Optional[float]

class EfficientFrontierResponse(BaseModel):
    success: bool
    frontier: List[EfficientFrontierPoint]
    max_sharpe: Optional[EfficientFrontierPoint]
    min_variance: Optional[EfficientFrontierPoint]
    cml: Optional[List[Dict[str, float]]]
    error: Optional[str]

class RollingSharpeResponse(BaseModel):
    success: bool; period: str; window: int
    series: List[Dict[str, Any]]
    error: Optional[str]

class RiskContributionItem(BaseModel):
    symbol: str; weight: float
    marginal_risk: float; component_risk: float
    risk_pct: float

class RiskContributionResponse(BaseModel):
    success: bool
    contributions: List[RiskContributionItem]
    total_risk: float
    error: Optional[str]

class FactorExposureResponse(BaseModel):
    success: bool
    exposures: Dict[str, float]
    r_squared: float
    error: Optional[str]
```

### 5.4 Frontend Types (TypeScript)

New types needed in `portfolio.types.ts`:

```typescript
interface RiskMetricsResponse {
    success: boolean;
    period: string;
    variance: number;
    std_deviation: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown: number;
    max_drawdown_pct: number;
    value_at_risk_95: number;
    value_at_risk_99: number;
    conditional_var_95: number;
    downside_deviation: number;
    tracking_error?: number;
    information_ratio?: number;
    beta?: number;
    alpha?: number;
    error?: string;
}

interface CovarianceResponse {
    success: boolean;
    period: string;
    holdings: string[];
    covariance_matrix: number[][];
    correlation_matrix: number[][];
    error?: string;
}

interface DrawdownResponse {
    success: boolean;
    period: string;
    drawdowns: { date: string; value: number; drawdown_pct: number }[];
    max_drawdown: number;
    max_drawdown_pct: number;
    max_drawdown_start?: string;
    max_drawdown_end?: string;
    max_drawdown_recovery?: string;
    avg_drawdown: number;
    error?: string;
}

interface EfficientFrontierPoint {
    volatility: number;
    expected_return: number;
    weights: Record<string, number>;
    sharpe_ratio?: number;
}

interface EfficientFrontierResponse {
    success: boolean;
    frontier: EfficientFrontierPoint[];
    max_sharpe?: EfficientFrontierPoint;
    min_variance?: EfficientFrontierPoint;
    cml?: { volatility: number; expected_return: number }[];
    error?: string;
}

interface RollingSharpeResponse {
    success: boolean;
    period: string;
    window: number;
    series: { date: string; sharpe_ratio: number }[];
    error?: string;
}

interface RiskContributionItem {
    symbol: string;
    weight: number;
    marginal_risk: number;
    component_risk: number;
    risk_pct: number;
}

interface RiskContributionResponse {
    success: boolean;
    contributions: RiskContributionItem[];
    total_risk: number;
    error?: string;
}

interface FactorExposureResponse {
    success: boolean;
    exposures: Record<string, number>;
    r_squared: number;
    error?: string;
}
```

### 5.5 Frontend Hooks

New hooks needed in `usePortfolio.ts`:

```typescript
export function usePortfolioRiskMetrics(period: string, accountIds?: number[])
    → RiskMetricsResponse

export function usePortfolioCovariance(period: string, accountIds?: number[])
    → CovarianceResponse

export function usePortfolioDrawdown(period: string, accountIds?: number[])
    → DrawdownResponse

export function usePortfolioEfficientFrontier(accountIds?: number[], points?: number)
    → EfficientFrontierResponse

export function usePortfolioRollingSharpe(window: number, accountIds?: number[])
    → RollingSharpeResponse

export function usePortfolioRiskContribution(accountIds?: number[])
    → RiskContributionResponse

export function usePortfolioFactorExposure(accountIds?: number[])
    → FactorExposureResponse
```

### 5.6 Service Layer (Frontend)

New methods needed in `portfolio.service.ts`:

```typescript
async getPortfolioRiskMetrics(period: string, accountIdsParam?: string): Promise<...>
async getPortfolioCovariance(period: string, accountIdsParam?: string): Promise<...>
async getPortfolioDrawdown(period: string, accountIdsParam?: string): Promise<...>
async getPortfolioEfficientFrontier(accountIdsParam?: string, points?: number): Promise<...>
async getPortfolioRollingSharpe(window: number, accountIdsParam?: string): Promise<...>
async getPortfolioRiskContribution(accountIdsParam?: string): Promise<...>
async getPortfolioFactorExposure(accountIdsParam?: string): Promise<...>
```

### 5.7 Query Key Management

New query keys needed in the global `QK` object to enable proper cache invalidation:

```typescript
QK.portfolioRiskMetrics(period, idsParam)        // → ['portfolio', 'risk-metrics', ...]
QK.portfolioCovariance(period, idsParam)         // → ['portfolio', 'covariance', ...]
QK.portfolioDrawdown(period, idsParam)           // → ['portfolio', 'drawdown', ...]
QK.portfolioEfficientFrontier(idsParam, points)  // → ['portfolio', 'efficient-frontier', ...]
QK.portfolioRollingSharpe(window, idsParam)      // → ['portfolio', 'rolling-sharpe', ...]
QK.portfolioRiskContribution(idsParam)           // → ['portfolio', 'risk-contribution', ...]
QK.portfolioFactorExposure(idsParam)             // → ['portfolio', 'factor-exposure', ...]
```

---

## 6. Data Dependencies

### 6.1 Required Tables

| Table | Columns Needed | Used For |
|---|---|---|
| `portfolio_snapshots` | `snapshot_date`, `total_value`, `total_cost`, `cash_balance` | Return series, drawdown, VaR |
| `portfolio_transactions` | `transaction_date`, `activity_type`, `symbol`, `quantity`, `unit_price` | FIFO cost basis, cash flows |
| `portfolio_holdings` | `symbol`, `quantity`, `average_cost` | Current weights, allocation |
| `company_prices` | `price_date`, `close_price`, `adjusted_close` | Holding-level returns, covariance |
| `portfolio_accounts` | `account_id`, `user_id`, `currency` | Account filtering |
| `companies` | `company_id`, `ticker_symbol`, `sector`, `industry` | Metadata for allocation |
| `company_financial_ratios` | Various financial ratios | Factor analysis (value/momentum) |
| `benchmark_config` | `symbol`, `name`, `market` | Benchmark metadata |

### 6.2 Portfolio Snapshots — Key Data Series

The `portfolio_snapshots` table is **the most critical data source** for risk metrics. Each snapshot contains:
- `portfolio_id` — which portfolio (user-level or account-level)
- `snapshot_date` — date of the snapshot
- `total_value` — market value on that date
- `total_cost` — cost basis on that date
- `cash_balance` — cash held

From these, daily return series can be computed as:
```
r_t = (total_value_t - total_value_{t-1} + net_deposits_t) / total_value_{t-1}
```

### 6.3 Company Prices — Holding-Level Data

For covariance/correlation matrix computation, we need daily return series per holding:

```
r_{i,t} = (close_{i,t} - close_{i,t-1}) / close_{i,t-1}
```

The `company_prices` table already stores daily close and adjusted_close prices. The following query pattern exists in the codebase:
```python
# From portfolio_service.py — existing price query pattern
prices = self.portfolio_repo.get_historical_prices(symbol, start_date, end_date)
```

---

## 7. API Design

### 7.1 `GET /portfolio/risk-metrics`

**Request:**
- `period` (query, default "1Y"): time period
- `account_ids` (query, optional): comma-separated account IDs

**Processing:**
1. Fetch portfolio performance snapshots for the period
2. Compute daily return series from snapshot value changes
3. Compute variance, std deviation from return series
4. Compute Sharpe ratio: `(mean_return - risk_free_rate) / std_deviation`
5. Compute Sortino ratio: `(mean_return - risk_free_rate) / downside_deviation`
6. Compute max drawdown from snapshot values
7. Compute VaR (95%, 99%) and CVaR from return distribution
8. If benchmark selected, compute beta, alpha, tracking error, information ratio

**Response:** `RiskMetricsResponse`

### 7.2 `GET /portfolio/covariance`

**Request:**
- `period` (query, default "1Y"): time period
- `account_ids` (query, optional): comma-separated account IDs

**Processing:**
1. Fetch current holdings for portfolio
2. For each holding, fetch historical prices for the period
3. Compute daily return series per holding
4. Align all series to common date range
5. Compute covariance matrix using `numpy.cov()`
6. Compute correlation matrix from covariance

**Response:** `CovarianceResponse`

### 7.3 `GET /portfolio/drawdown`

**Request:**
- `period` (query, default "1Y"): time period
- `account_ids` (query, optional): comma-separated account IDs

**Processing:**
1. Fetch portfolio performance snapshots
2. Track running maximum of portfolio value
3. For each point, compute drawdown: `(value - peak) / peak`
4. Identify max drawdown period (start, end, recovery)
5. Compute average drawdown

**Response:** `DrawdownResponse`

### 7.4 `GET /portfolio/efficient-frontier`

**Request:**
- `account_ids` (query, optional): comma-separated account IDs
- `points` (query, optional, default 100): number of frontier points

**Processing:**
1. Fetch current holdings with weights
2. Fetch historical prices per holding
3. Compute covariance matrix and expected returns
4. Run scipy optimizer for each target return level:
   - Minimize `w^T Σ w` subject to `Σ w_i × μ_i = target_return`, `Σ w_i = 1`
5. Find max Sharpe ratio point (tangent portfolio)
6. Find minimum variance point
7. Compute CML points from risk-free rate through max Sharpe point

**Response:** `EfficientFrontierResponse`

### 7.5 `GET /portfolio/rolling-sharpe`

**Request:**
- `window` (query, default 252): rolling window in trading days
- `account_ids` (query, optional): comma-separated account IDs

**Processing:**
1. Fetch portfolio performance snapshots (full available range)
2. Compute daily return series
3. For each window, compute Sharpe ratio
4. Return time series of rolling Sharpe values

**Response:** `RollingSharpeResponse`

### 7.6 `GET /portfolio/risk-contribution`

**Request:**
- `account_ids` (query, optional): comma-separated account IDs

**Processing:**
1. Fetch current portfolio weights per holding
2. Fetch covariance matrix (reuse covariance endpoint logic)
3. Compute marginal contribution to risk for each holding:
   ```
   MCR_i = (Σ × w)_i / sqrt(w^T × Σ × w)
   ```
4. Compute component contribution to risk:
   ```
   CCR_i = w_i × MCR_i
   ```
5. Normalize to percentages

**Response:** `RiskContributionResponse`

### 7.7 `GET /portfolio/factor-exposure`

**Request:**
- `account_ids` (query, optional): comma-separated account IDs

**Processing:**
1. Fetch portfolio historical returns (full available range)
2. Fetch factor returns for specified factors (market, size, value, momentum)
3. Run OLS regression: `portfolio_returns = α + β₁×MKT + β₂×SMB + β₃×HML + β₄×MOM + ε`
4. Return factor loadings and R²

**Note:** Factor return data is a separate data dependency. May need to source from external API or hardcode benchmark factors (e.g., SPY - risk-free as market factor).

**Response:** `FactorExposureResponse`

---

## 8. Visualization Strategy

### 8.1 Library Assessment

| Library | Available | Suitable For | Notes |
|---|---|---|---|
| **recharts** | ✅ In `package.json` | Line, Area, Bar, Scatter, Radar, Treemap | Already used; Treemap is native |
| **plotly.js / react-plotly** | ❌ Not installed | Heatmaps, 3D scatter, advanced | Best for correlation heatmap & efficient frontier |
| **d3.js** | ❌ Not installed | Custom visualizations | Heavy; prefer recharts/plotly |
| **chart.js / react-chartjs-2** | ❌ Not installed | General charts | Alternative to recharts |

**Recommendation:** Use **recharts** for all standard charts (line, area, bar, scatter, treemap, radar). **Add react-plotly** only for the correlation heatmap and potentially the efficient frontier. This avoids adding too many dependencies while getting the one critical visualization type that recharts handles poorly (2D heatmap).

### 8.2 Visualization Component Map

| Visualization | Chart Type | Library | Data Source |
|---|---|---|---|
| **Risk Metric Cards** | KPI grid (UI, not chart) | Tailwind/shadcn | `risk-metrics` endpoint |
| **Correlation Heatmap** | 2D color grid | Plotly | `covariance` endpoint |
| **Drawdown Chart** | Area chart (negative) | recharts AreaChart | `drawdown` endpoint |
| **Rolling Sharpe** | Line chart | recharts LineChart | `rolling-sharpe` endpoint |
| **Efficient Frontier** | Scatter + line | recharts ScatterChart | `efficient-frontier` endpoint |
| **Treemap** | Treemap | recharts Treemap | `allocation` endpoint (exists) |
| **Volatility vs Return Scatter** | Scatter (bubble) | recharts ScatterChart | hybrid: `risk-metrics` + holdings |
| **Factor Exposure** | Horizontal bar | recharts BarChart | `factor-exposure` endpoint |
| **Diversification Wheel** | Radial/polar | recharts RadarChart | `risk-contribution` endpoint |
| **Risk Pyramid** | Layered UI | Tailwind/shadcn | `risk-metrics` endpoint |

### 8.3 Component Architecture

```
PerformanceTab (existing — extend)
├── Period Pills (existing)
├── AccountSelector (existing)
├── Sub-tab Navigation (new)
│   ├── "Summary" — existing charts
│   ├── "Risk Metrics" — KPI cards + drawdown chart
│   ├── "Correlations" — heatmap + scatter
│   ├── "Efficient Frontier" — frontier scatter
│   ├── "Drawdown" — underwater chart + stats
│   └── "Factor" — factor exposure bars
```

### 8.4 UI/UX Considerations

- **Period consistency:** All risk metrics should be computed for the same period selected by the user across the performance tab
- **Loading states:** Each sub-tab can load independently (parallel React Query fetches)
- **Empty states:** If insufficient history (e.g., < 30 days), show informative message rather than broken chart
- **Color conventions:** Green for positive metrics, red for negative, consistent with existing theme
- **High-DPI support:** Use existing ResponsiveContainer wrappers

---

## 9. Frontend State & Caching

### 9.1 React Query Strategy

All new endpoints should follow the same caching pattern as existing portfolio endpoints:

```typescript
staleTime: STALE.PORTFOLIO,  // e.g., 30 seconds — risk metrics are semi-stale during trading
gcTime: GC.PORTFOLIO,        // e.g., 5 minutes
placeholderData: (previousData) => previousData,  // smooth transitions
```

**Cache invalidation:** The following events should invalidate all portfolio-related queries:
- Transaction import completes (`onSuccess` of import mutation)
- Manual transaction added
- Account deleted
- Any data-changing portfolio mutation

This is already partially handled in `useDeleteAccount` (lines 135-154 of `usePortfolio.ts`). The invalidation list needs to be extended for new query keys.

### 9.2 Query Key Structure

Follow the existing pattern in `QK`:

```typescript
// Existing (in lib/query-keys.ts):
QK.portfolioOverview = () => ['portfolio', 'overview']
QK.portfolioPerformance = (period, ids) => ['portfolio', 'performance', period, ids]
QK.portfolioBenchmarkCompare = (period, benchmarks, ids) => ['portfolio', 'benchmark-compare', period, ...benchmarks, ids]
QK.portfolioAllocation = (groupBy, ids) => ['portfolio', 'allocation', groupBy, ids]

// New:
QK.portfolioRiskMetrics = (period, ids) => ['portfolio', 'risk-metrics', period, ids]
QK.portfolioCovariance = (period, ids) => ['portfolio', 'covariance', period, ids]
QK.portfolioDrawdown = (period, ids) => ['portfolio', 'drawdown', period, ids]
QK.portfolioEfficientFrontier = (ids, points) => ['portfolio', 'efficient-frontier', ids, points]
QK.portfolioRollingSharpe = (window, ids) => ['portfolio', 'rolling-sharpe', window, ids]
QK.portfolioRiskContribution = (ids) => ['portfolio', 'risk-contribution', ids]
QK.portfolioFactorExposure = (ids) => ['portfolio', 'factor-exposure', ids]
```

---

## 10. Implementation Effort Estimate

### Phase 1: Statistical Foundation (Backend) — ~1 week

| Task | Files | Est. Days |
|---|---|---|
| Create `shared/portfolio_stats.py` with pure math functions | `backend/shared/portfolio_stats.py` | 1 |
| Create `portfolio_risk_service.py` with DB access | `backend/application/services/portfolio_risk_service.py` | 2 |
| Write unit tests for statistical functions | `backend/tests/unit/test_portfolio_stats.py` | 1 |
| Write integration tests | `backend/tests/integration/test_portfolio_risk.py` | 1 |

### Phase 2: API Layer (Backend) — ~1 week

| Task | Files | Est. Days |
|---|---|---|
| Add new Pydantic schemas | `backend/schemas_portfolio.py` (±150 lines) | 0.5 |
| Add risk-metrics endpoint | `backend/api/portfolio.py` | 0.5 |
| Add covariance endpoint | `backend/api/portfolio.py` | 0.5 |
| Add drawdown endpoint | `backend/api/portfolio.py` | 0.5 |
| Add efficient-frontier endpoint | `backend/api/portfolio.py` | 1 |
| Add rolling-sharpe endpoint | `backend/api/portfolio.py` | 0.5 |
| Add risk-contribution endpoint | `backend/api/portfolio.py` | 0.5 |
| Add factor-exposure endpoint | `backend/api/portfolio.py` | 1 |

### Phase 3: Frontend Types, Hooks, Service — ~1 week

| Task | Files | Est. Days |
|---|---|---|
| Add TypeScript interfaces | `portfolio.types.ts` (±200 lines) | 0.5 |
| Add query keys | Query keys config file | 0.25 |
| Add service methods | `portfolio.service.ts` | 0.75 |
| Add React Query hooks | `usePortfolio.ts` (±150 lines) | 0.5 |
| Add API proxy route | (if needed for new endpoints) | 0.25 |

### Phase 4: Visualization Components (Frontend) — ~2 weeks

| Task | Files | Est. Days |
|---|---|---|
| Risk Metric Cards component | New component file | 1 |
| Correlation Heatmap component | New component file (react-plotly) | 1.5 |
| Drawdown Chart component | New component file (recharts) | 1 |
| Rolling Sharpe Chart component | New component file (recharts) | 0.5 |
| Efficient Frontier component | New component file (recharts) | 1.5 |
| Portfolio Treemap | New component file (recharts) | 0.5 |
| Volatility vs Return Scatter | New component file (recharts) | 1 |
| Factor Exposure Chart | New component file (recharts) | 0.5 |
| Diversification Wheel | New component file (recharts RadarChart) | 1 |
| Risk Pyramid | New component file (Tailwind) | 0.5 |
| Sub-tab navigation in PerformanceTab | `PerformanceTab.tsx` refactor | 1 |

### Phase 5: Polish & Testing — ~1 week

| Task | Est. Days |
|---|---|
| Integration testing (backend) | 1 |
| Component testing (frontend) | 1 |
| Performance optimization (caching, memoization) | 0.5 |
| Edge case handling (empty portfolio, single holding, short history) | 1 |
| Loading/error/empty state coverage | 0.5 |
| Responsive design verification | 0.5 |
| Documentation (API docs, component stories) | 0.5 |

### Total Estimate: ~6 weeks

| Phase | Effort |
|---|---|
| Phase 1: Statistical Foundation | 5 days |
| Phase 2: API Layer | 4 days |
| Phase 3: Frontend Types/Hooks/Service | 2 days |
| Phase 4: Visualization Components | 10 days |
| Phase 5: Polish & Testing | 5 days |
| **Total** | **~26 working days (~6 weeks)** |

---

## 11. Complete Gap Inventory

### 11.1 Backend Gaps

| # | Gap | Current State | Solution | Difficulty | Priority |
|---|---|---|---|---|---|
| G1 | No variance/std deviation | Not computed anywhere | Add to `shared/portfolio_stats.py` | Easy | High |
| G2 | No covariance matrix | Not computed anywhere | Add to `shared/portfolio_stats.py` + service | Medium | High |
| G3 | No correlation matrix | Not computed anywhere | Derivative of covariance | Easy | High |
| G4 | No Sortino ratio | Not computed anywhere | Add to `shared/portfolio_stats.py` | Easy | Medium |
| G5 | No max drawdown | Not computed anywhere | Walk snapshot series | Easy | High |
| G6 | No VaR/CVaR | Not computed anywhere | Add to `shared/portfolio_stats.py` | Medium | Medium |
| G7 | No efficient frontier | Not computed anywhere | scipy optimizer + cov matrix | Hard | Medium |
| G8 | No rolling metrics | Not computed anywhere | Sliding window computations | Medium | Low |
| G9 | No risk contribution | Not computed anywhere | Derivative of cov matrix | Medium | Low |
| G10 | No factor exposure | Not computed anywhere | Regression model | Hard | Low |
| G11 | No risk-free rate config | Hardcoded assumption | Add env var or config table | Easy | Low |

### 11.2 Frontend Gaps

| # | Gap | Current State | Solution | Difficulty | Priority |
|---|---|---|---|---|---|
| G12 | No risk metric cards | Not implemented | New component | Easy | High |
| G13 | No correlation heatmap | Not implemented | New component (plotly) | Medium | High |
| G14 | No drawdown chart | Not implemented | New component (recharts) | Medium | High |
| G15 | No rolling Sharpe chart | Not implemented | New component (recharts) | Medium | Medium |
| G16 | No efficient frontier viz | Not implemented | New component (recharts) | Hard | Medium |
| G17 | No treemap | Not implemented (but recharts supports) | New component | Medium | Low |
| G18 | No scatter plot | Not implemented | New component (recharts) | Medium | Low |
| G19 | No factor exposure viz | Not implemented | New component (recharts) | Medium | Low |
| G20 | No diversification wheel | Not implemented | New component (RadarChart) | Medium | Low |
| G21 | No risk pyramid | Not implemented | New component (Tailwind) | Easy | Low |
| G22 | No TypeScript interfaces for risk | Not defined | Add to `portfolio.types.ts` | Easy | High |
| G23 | No service methods for risk | Not defined | Add to `portfolio.service.ts` | Easy | High |
| G24 | No React Query hooks for risk | Not defined | Add to `usePortfolio.ts` | Easy | High |
| G25 | No query keys for risk | Not defined | Add to query keys config | Easy | High |
| G26 | No sub-tab navigation | Not implemented | Refactor `PerformanceTab.tsx` | Medium | High |

### 11.3 Data Gaps

| # | Gap | Current State | Solution | Difficulty |
|---|---|---|---|---|
| G27 | Factor return data | Not available in DB | Build factor return data source (external API or computed from company_prices) | Hard |
| G28 | Risk-free rate history | Not stored | Add config table or fetch from external source | Easy |

---

## 12. Recommended Phasing

### Phase 1 — Core Risk Metrics (Weeks 1–2)

Deliverable: Risk metric KPI cards + drawdown chart on the Performance tab

Backend:
- `shared/portfolio_stats.py` — variance, std dev, downside deviation, max drawdown, Sharpe ratio, Sortino ratio, VaR
- `portfolio_risk_service.py` — orchestrates computation from snapshots
- `GET /portfolio/risk-metrics` endpoint
- `GET /portfolio/drawdown` endpoint
- New Pydantic schemas

Frontend:
- TypeScript interfaces for `RiskMetricsResponse`, `DrawdownResponse`
- Service methods + React Query hooks
- `RiskMetricCards` component (KPI grid)
- `DrawdownChart` component (underwater area chart)
- Sub-tab: "Risk Metrics" in PerformanceTab

### Phase 2 — Covariance & Correlation (Week 3)

Deliverable: Correlation matrix heatmap + enhanced portfolio understanding

Backend:
- Covariance/correlation matrix computation in `portfolio_stats.py`
- `GET /portfolio/covariance` endpoint
- Price history alignment logic

Frontend:
- Install `react-plotly.js` (or use custom Canvas-based heatmap with recharts)
- `CovarianceHeatmap` / `CorrelationHeatmap` component
- Sub-tab: "Correlations" in PerformanceTab

### Phase 3 — Efficient Frontier & Risk Decomposition (Weeks 4–5)

Deliverable: Efficient Frontier scatter plot + allocation optimization insights

Backend:
- Efficient Frontier computation via scipy optimizer
- `GET /portfolio/efficient-frontier` endpoint
- `GET /portfolio/risk-contribution` endpoint
- `GET /portfolio/rolling-sharpe` endpoint

Frontend:
- `EfficientFrontierChart` component (scatter + CML line)
- `DiversificationWheel` component (RadarChart for risk contribution)
- `RollingSharpeChart` component
- Sub-tabs: "Efficient Frontier", "Risk Allocation" in PerformanceTab

### Phase 4 — Advanced Analytics (Week 6)

Deliverable: Factor exposure, treemap, scatter plot, and risk pyramid

Backend:
- Factor exposure computation (regression)
- `GET /portfolio/factor-exposure` endpoint

Frontend:
- `FactorExposureChart` component
- `PortfolioTreemap` component (reuses allocation data)
- `VolatilityVsReturnScatter` component
- `RiskPyramid` component
- Full sub-tab navigation polished
- Edge case handling, responsiveness, loading states

---

## 13. Open-Source Library Assessment

Three open-source libraries were evaluated for potential use: [`quantstats`](https://github.com/ranaroussi/quantstats), [`empyrical`](https://github.com/quantopian/empyrical), and [`PyPortfolioOpt`](https://github.com/PyPortfolio/PyPortfolioOpt). Each is assessed for suitability, dependencies, and integration cost.

### 13.1 Library Comparison Matrix

| Dimension | **quantstats** | **empyrical** | **PyPortfolioOpt** |
|---|---|---|---|
| **Stars / Maturity** | 7.2k ⭐, active (Jan 2026) | 1.5k ⭐, frozen (last release 2020) | 5.8k ⭐, active (Feb 2026) |
| **Purpose** | Portfolio profiling, risk metrics, reports, Monte Carlo | Low-level risk/performance metrics | Portfolio optimization (Efficient Frontier, HRP, BL) |
| **Key Functions** | `sharpe`, `sortino`, `volatility`, `var`, `cvar`, `max_drawdown`, `drawdown_details`, `information_ratio`, `rolling_*`, `montecarlo` | `max_drawdown`, `alpha_beta`, `capture`, `roll_*` | `EfficientFrontier`, `risk_models`, `expected_returns`, `BlackLittermanModel`, `HRPOpt`, `DiscreteAllocation` |
| **Visualization** | Built-in (matplotlib/seaborn/plotly) — not directly usable in web frontend | None | Built-in (matplotlib) — not directly usable in web frontend |
| **Dependencies** | pandas, numpy, scipy, matplotlib, seaborn, tabulate, yfinance | numpy, pandas, scipy | pandas, numpy, scipy, cvxpy |
| **New deps needed** | scipy, seaborn, tabulate | scipy | scipy, cvxpy |
| **License** | Apache 2.0 | Apache 2.0 | MIT |

### 13.2 Detailed Analysis

#### 13.2.1 empyrical — RECOMMEND: SKIP

**Pros:**
- Lightweight, well-tested core functions (max_drawdown, alpha/beta, capture ratios)

**Cons:**
- **Unmaintained since 2020** — no Python 3.12+ compatibility guarantee
- Very narrow scope — only ~15 functions
- All functionality is strictly a subset of quantstats.stats
- No pandas Series/DataFrame extension, only numpy arrays

**Verdict:** Skip. quantstats covers everything empyrical offers, is actively maintained, and has a richer API.

#### 13.2.2 quantstats — RECOMMEND: OPTIONAL (can hand-roll instead)

**Pros:**
- **Comprehensive metrics module** (`quantstats.stats`) covering ALL risk metrics needed in Phase 1: Sharpe, Sortino, volatility, VaR, CVaR, max drawdown, drawdown details, information ratio, rolling metrics, skew, kurtosis, ulcer index, gain-to-pain ratio, Monte Carlo simulations, and more
- Actively maintained (latest release Jan 2026, Python 3.12+ compatible)
- Well-tested with 592 commits
- `qs.extend_pandas()` adds `.sharpe()`, `.sortino()`, etc. directly to pandas Series — clean integration
- Can use `quantstats.stats` module in isolation without importing plotly/seaborn

**Cons:**
- **`quantstats.plots` is matplotlib-based** — not directly usable for the web frontend. The plots module cannot be used.
- Adds seaborn and tabulate as new dependencies (~15 MB combined)
- **The core formulas (Sharpe, Sortino, VaR, max drawdown) are trivially implementable** — each is 5-15 lines of numpy. The time saved vs hand-rolling is modest (~1-2 days) and these are formulas we'd want to fully understand and control.
- `quantstats.reports.html` could be useful for PDF export, but that's a Phase 5+ feature not in current scope
- No use for `quantstats.plots` means we're pulling a visualization library only for its stats submodule

**Verdict:** OPTIONAL. The convenience of `quantstats.stats` is real, but every metric it provides is a simple numpy formula. Given the dependency cost (seaborn, tabulate) and the fact that we'd want to own these formulas for testing/auditing, **hand-rolling in `shared/portfolio_stats.py` is the leaner path**. Revisit if Phase 6+ requires Monte Carlo or advanced reporting.

#### 13.2.3 PyPortfolioOpt — RECOMMEND: ADOPT

**Pros:**
- **Industry-standard portfolio optimization library** used in both academia and production
- Covers ALL Phase 3+4 needs: Efficient Frontier (max Sharpe, min volatility, efficient return/risk), Black-Litterman, Hierarchical Risk Parity, Mean-CVaR, Mean-Semivariance
- Risk models: sample covariance, shrinkage (Ledoit-Wolf, Oracle Approximating), semicovariance, exponential covariance, minimum covariance determinant
- Expected return models: mean historical, exponential weighted, CAPM
- Built-in `DiscreteAllocation` to convert continuous weights into actual share counts
- Well-documented with extensive tests, cookbook/Jupyter notebooks
- Actively maintained (latest release Feb 2026)
- Modular design — easy to use individual components (e.g., just `risk_models` for covariance)

**Cons:**
- Requires `cvxpy` (convex optimization solver) as a new dependency — this is a moderate-weight library
- `scipy` needs to be explicitly added (currently only indirect via matplotlib)
- The plotting module is matplotlib-based, same limitation as quantstats for the web frontend
- `cvxpy` can be complex to install on some platforms (solver dependencies), but for standard use it's well-supported

**Verdict:** ADOPT. Unlike the basic risk metrics, the optimization algorithms in PyPortfolioOpt (quadratic programming constraints, covariance shrinkage, Black-Litterman) are genuinely complex to implement correctly. Hand-rolling would be error-prone and time-consuming. This saves ~5-6 days and provides battle-tested algorithms.

### 13.3 Overlap Analysis — Complementary or Redundant?

The two libraries are **complementary, not redundant**:

| Capability | quantstats | PyPortfolioOpt | Notes |
|---|---|---|---|
| Sharpe, Sortino, Win Rate | ✅ Core | ❌ | quantstats is the reporting layer |
| VaR, CVaR, Drawdown | ✅ Core | ❌ | Ex-post risk measurement |
| Rolling metrics | ✅ Core | ❌ | Time-series analysis |
| Efficient Frontier | ❌ | ✅ Core | Portfolio construction |
| Covariance shrinkage | ❌ | ✅ Core | Better estimates than sample cov |
| Black-Litterman / HRP | ❌ | ✅ Core | Advanced allocation models |
| Monte Carlo simulation | ✅ Core | ❌ | Scenario analysis |

**The only overlap** is that both can compute basic Sharpe/volatility, but:
- quantstats computes it **ex-post** on a return series (reporting: "my Sharpe was 0.8")
- PyPortfolioOpt uses it **ex-ante** for optimization (planning: "target Sharpe = 1.2")

That said, the **practical overlap is near zero** because the formulas are so simple. The real question is dependency cost vs build effort.

### 13.4 Final Recommendations

| Library | Verdict | Rationale |
|---|---|---|
| **PyPortfolioOpt** | ✅ **ADOPT** | Complex optimization algorithms (Efficient Frontier, covariance shrinkage, Black-Litterman, HRP) are genuinely hard to implement correctly. Saves ~5-6 days. Only adds `cvxpy` + `scipy`. |
| **quantstats** | ⚠️ **OPTIONAL** | Every metric is a 5-15 line numpy formula. The time saved (~1-2 days) doesn't justify seaborn + tabulate dependencies when we can hand-roll in `shared/portfolio_stats.py` with full control and test coverage. Revisit if Phase 6+ requires Monte Carlo or HTML reports. |
| **empyrical** | ❌ **SKIP** | Unmaintained, subset of quantstats, nothing unique. |

### 13.5 Revised Dependency Plan

Add to `requirements.in`:

```
# === New for Portfolio Performance ===
scipy~=1.15.0           # Required by PyPortfolioOpt (already transitive via matplotlib)
cvxpy~=1.6.0            # Required by PyPortfolioOpt — convex optimization solver
PyPortfolioOpt~=1.6.0   # Portfolio optimization
```

Note: Scipy is already available as a transitive dependency via matplotlib. We pin it explicitly to ensure version compatibility with PyPortfolioOpt.

### 13.6 Integration Pattern

PyPortfolioOpt should be used through a **service abstraction layer**, following the existing codebase pattern:

```
┌──────────────────────────────────────────────────────────────┐
│  api/portfolio.py (new endpoints, unchanged pattern)          │
├──────────────────────────────────────────────────────────────┤
│  application/services/portfolio_risk_service.py (NEW)        │
│    ├── compute_risk_metrics(returns, rf=0.02)               │
│    │     └── Hand-rolled numpy in shared/portfolio_stats.py  │
│    ├── compute_drawdown_series(returns)                      │
│    │     └── Hand-rolled numpy in shared/portfolio_stats.py  │
│    ├── compute_rolling_metrics(returns, window=252)           │
│    │     └── Hand-rolled numpy in shared/portfolio_stats.py  │
│    ├── compute_covariance_matrix(prices)                     │
│    │     └── PyPortfolioOpt.risk_models (LedoitWolf shrinkage)│
│    ├── compute_efficient_frontier(prices, points=100)        │
│    │     └── PyPortfolioOpt.EfficientFrontier                 │
│    └── compute_risk_contribution(weights, cov_matrix)        │
│          └── PyPortfolioOpt objective_functions               │
├──────────────────────────────────────────────────────────────┤
│  shared/portfolio_stats.py (NEW)                              │
│    └── numpy-based: variance, std dev, Sharpe, Sortino,      │
│         VaR, CVaR, max drawdown, downside deviation          │
└──────────────────────────────────────────────────────────────┘
```

### 13.7 Revised Effort Estimate

| Phase | Original | Revised | Savings |
|---|---|---|---|
| Phase 1: Statistical Foundation | 5 days | **5 days** | No change (hand-rolled anyway) |
| Phase 2: API Layer | 4 days | 4 days | No change |
| Phase 3: Frontend Types/Hooks | 2 days | 2 days | No change |
| Phase 4: Visualization Components | 10 days | 8 days | −2 days (PyPortfolioOpt risk_models for cov matrix) |
| Phase 5: Optimization (was Polish) | 5 days | **2 days** | −3 days (PyPortfolioOpt for frontier) |
| **Total** | **~26 days** | **~21 days** | **−5 days (~20%)** |

---

## Summary

**Verdict: FULLY FEASIBLE** with a phased approach over ~21 working days (~5 weeks).

The existing codebase provides a solid foundation with FIFO lot tracking, portfolio snapshots, historical prices, benchmark comparison, and allocation data.

**Library Recommendations:**
- **`PyPortfolioOpt`** — ✅ **ADOPT** for portfolio optimization (Phase 3-4). Replaces custom scipy optimizer for Efficient Frontier, Black-Litterman, HRP, covariance shrinkage. Genuinely complex algorithms that would be costly to hand-roll.
- **`quantstats`** — ⚠️ **OPTIONAL**. Convenient but every metric is a 5-15 line numpy formula. Hand-rolling in `shared/portfolio_stats.py` gives us full control, zero new deps, and better testability. Revisit if Monte Carlo / HTML reports are needed later.
- **`empyrical`** — ❌ **SKIP**. Unmaintained, subset of quantstats.

**New dependencies to add:** `scipy`, `cvxpy`, `PyPortfolioOpt`

**Key architectural decision:** Hand-roll basic risk metrics (Sharpe, Sortino, VaR, etc.) in `shared/portfolio_stats.py` using pure numpy. Use PyPortfolioOpt for complex optimization (Efficient Frontier, covariance shrinkage, risk contribution). Keep all visualization on recharts (frontend).

The highest-value, lowest-effort items (Phase 1 — risk metric cards and drawdown chart) should be delivered first, giving the most visible impact for the least development time.
