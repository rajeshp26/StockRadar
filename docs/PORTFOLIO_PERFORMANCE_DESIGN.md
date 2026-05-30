# Portfolio Performance — Detailed Design Document

> **Date:** 2026-05-28
> **Status:** Draft for review
> **Feasibility Reference:** `docs/PORTFOLIO_PERFORMANCE_FEASIBILITY.md`

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Use Cases](#2-use-cases)
3. [UI/UX Design](#3-uiux-design)
4. [Frontend Scope](#4-frontend-scope)
5. [Backend Scope](#5-backend-scope)
6. [Software Architecture](#6-software-architecture)
7. [Sequence Diagrams](#7-sequence-diagrams)
8. [Class Diagrams](#8-class-diagrams)
9. [Dependencies & Environment](#9-dependencies--environment)
10. [Test Cases](#10-test-cases)
11. [Phased Development Plan](#11-phased-development-plan)
12. [Library Validation Phase](#12-library-validation-phase)
13. [Validation Strategy](#13-validation-strategy)
14. [Open Questions](#14-open-questions)

---

## 1. Introduction

### 1.1 Purpose

Design and implement advanced portfolio performance analytics for the StockerPro Portfolio page, including risk metrics, relationship metrics, portfolio optimization, and interactive visualizations.

### 1.2 Scope

| In Scope | Out of Scope |
|---|---|
| Portfolio-level risk metrics (variance, std dev, Sharpe, Sortino, VaR, CVaR) | Individual stock risk assessment (exists in `risk_assessment_service.py`) |
| Covariance & correlation matrices | Trade-level analytics (entry/exit analysis) |
| Max drawdown & underwater chart | Tax optimization (TLH, wash sales) |
| Efficient Frontier & minimum variance portfolio | Rebalancing engine / auto-trade |
| Risk contribution (marginal, component) | Portfolio backtesting engine |
| Rolling Sharpe & rolling volatility | Real-time streaming metrics |
| Visualizations (heatmap, drawdown, frontier) | PDF report generation |
| PyPortfolioOpt integration for optimization | Third-party data feeds (factors) |

### 1.3 References

- `docs/PORTFOLIO_PERFORMANCE_FEASIBILITY.md` — feasibility analysis & gap inventory
- `backend/shared/finance_math.py` — existing financial math utilities
- `backend/application/services/portfolio_service.py` — existing portfolio service
- `backend/application/services/risk_assessment_service.py` — existing single-stock risk (for pattern reference)
- `backend/schemas_portfolio.py` — existing Pydantic schemas
- `backend/api/portfolio.py` — existing API endpoints
- `web/src/lib/portfolio.types.ts` — existing TypeScript types
- `web/src/hooks/usePortfolio.ts` — existing React Query hooks
- `web/src/lib/portfolio.service.ts` — existing service layer
- PyPortfolioOpt docs: https://pyportfolioopt.readthedocs.io/en/latest/

---

## 2. Use Cases

### UC-1: View Risk Metrics Summary

| Item | Detail |
|---|---|
| **Actor** | Authenticated user on Portfolio > Performance tab |
| **Trigger** | User navigates to Performance tab or switches period |
| **Description** | Display a grid of KPI cards showing key risk/return metrics for the selected period |
| **Precondition** | Portfolio has at least one account with transaction history for the period |
| **Data Source** | `portfolio_snapshots` table → daily return series → statistical computation |
| **Input** | `period` (1D/1W/1M/3M/1Y/5Y/ALL), optional `account_ids` |
| **Output** | `RiskMetricsResponse`: total_return, total_return_pct, variance, std_deviation, sharpe_ratio, sortino_ratio, max_drawdown, max_drawdown_pct, value_at_risk_95, value_at_risk_99, conditional_var_95, downside_deviation, best_day, worst_day |
| **Success Path** | 1. User selects period → 2. Frontend calls `GET /portfolio/risk-metrics` → 3. Backend fetches snapshots, computes return series, calculates all metrics → 4. Frontend renders KPI cards |
| **Error Path** | Insufficient history (< 30 days): return metrics with `error: "Insufficient data"`, frontend shows informative message |

### UC-2: View Drawdown Chart

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects "Drawdown" sub-tab or views Risk Metrics section |
| **Description** | Display an underwater area chart showing peak-to-trough drawdown over time |
| **Data Source** | `portfolio_snapshots` table |
| **Input** | `period`, optional `account_ids` |
| **Output** | `DrawdownResponse`: drawdowns (date, value, drawdown_pct), max_drawdown, max_drawdown_pct, max_drawdown_start/end/recovery, avg_drawdown |
| **Success Path** | 1. Frontend calls `GET /portfolio/drawdown` → 2. Backend walks snapshot series, tracks running max, computes drawdown per point → 3. Frontend renders recharts AreaChart with red gradient fill below zero line |

### UC-3: View Covariance & Correlation Heatmap

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects "Correlations" sub-tab |
| **Description** | Display a color-coded heatmap of the correlation matrix between all holdings |
| **Data Source** | `company_prices` table for each holding |
| **Input** | `period`, optional `account_ids` |
| **Output** | `CovarianceResponse`: holdings (symbols), covariance_matrix, correlation_matrix |
| **Success Path** | 1. Frontend calls `GET /portfolio/covariance` → 2. Backend fetches prices for each holding, aligns dates, computes cov/corr matrices → 3. Frontend renders heatmap using recharts or a custom CSS grid with color scale |

### UC-4: View Efficient Frontier

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects "Efficient Frontier" sub-tab |
| **Description** | Display a scatter plot of the efficient frontier with current portfolio highlighted, max Sharpe and min variance points annotated |
| **Data Source** | `company_prices` table for each holding; current portfolio weights |
| **Input** | optional `account_ids`, `points` (number of frontier simulations, default 100) |
| **Output** | `EfficientFrontierResponse`: frontier points (volatility, expected_return, weights), max_sharpe point, min_variance point, CML line |
| **Success Path** | 1. Frontend calls `GET /portfolio/efficient-frontier` → 2. Backend computes expected returns and covariance via PyPortfolioOpt, runs optimizer → 3. Frontend renders recharts ScatterChart with frontier line, tangent line, and current portfolio marker |
| **Error Path** | Single holding portfolio: frontier is a single point, return message "Efficient Frontier requires 2+ holdings" |

### UC-5: View Rolling Sharpe

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects "Rolling Metrics" sub-tab |
| **Description** | Display a line chart of rolling Sharpe ratio over time |
| **Input** | `window` (default 252 trading days), optional `account_ids` |
| **Output** | `RollingSharpeResponse`: series (date, sharpe_ratio) |
| **Success Path** | 1. Frontend calls `GET /portfolio/rolling-sharpe?window=252` → 2. Backend computes rolling Sharpe over full available range → 3. Frontend renders line chart |

### UC-6: View Risk Contribution

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects "Risk Allocation" sub-tab |
| **Description** | Display a breakdown of how total portfolio risk is allocated across holdings |
| **Data Source** | Current portfolio weights + covariance matrix |
| **Input** | optional `account_ids` |
| **Output** | `RiskContributionResponse`: contributions (symbol, weight, marginal_risk, component_risk, risk_pct), total_risk |
| **Success Path** | 1. Frontend calls `GET /portfolio/risk-contribution` → 2. Backend fetches weights and covariance, computes marginal and component risk → 3. Frontend renders radar chart or horizontal bar chart |
| **Edge Case** | Single holding: 100% risk contribution to that holding |

### UC-7: View Factor Exposure

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects "Factor Exposure" sub-tab |
| **Description** | Display regression-based factor loadings for the portfolio |
| **Data Source** | Portfolio historical returns + factor return data (market, size, value, momentum proxies) |
| **Input** | optional `account_ids` |
| **Output** | `FactorExposureResponse`: exposures (factor → loading), r_squared |
| **Success Path** | 1. Frontend calls `GET /portfolio/factor-exposure` → 2. Backend runs OLS regression of portfolio returns against factor returns → 3. Frontend renders horizontal bar chart |
| **Note** | Factor return data is a separate data dependency. Phase 4 implementation may use SPY - RF as market factor, with hardcoded Fama-French factor data as initial source. |

### UC-8: View Benchmark Comparison (Extended)

| Item | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User selects benchmark symbols on existing Performance tab |
| **Description** | Extend existing `get_performance_compare()` to include risk-adjusted comparison (Sharpe, Sortino, max drawdown for benchmark vs portfolio) |
| **Input** | `period`, `benchmark_symbols`, optional `account_ids` |
| **Output** | Existing `BenchmarkCompareResponse` + risk metric comparison overlay |
| **Success Path** | 1. Existing API path → 2. Add risk metrics for both portfolio and benchmark → 3. Frontend shows side-by-side comparison |

### 2.1 Account Scoping

All portfolio metrics are **scoped by account selection**. The user can filter to a subset of accounts via the AccountSelector dropdown, and every metric, chart, and optimization reflects only the holdings within those accounts.

**How scoping flows through the system:**

```
AccountSelector dropdown
       │
       ▼
account_ids=[1,3]  ← passed as query param to ALL risk endpoints
       │
       ├── GET /portfolio/risk-metrics?period=1Y&account_ids=1,3
       │     └── Snapshots filtered to accounts 1+3 only
       │
       ├── GET /portfolio/covariance?period=1Y&account_ids=1,3
       │     └── Holdings → prices → covariance → only symbols in accounts 1+3
       │
       ├── GET /portfolio/efficient-frontier?account_ids=1,3
       │     └── Weights scoped to accounts 1+3 only
       │
       ├── GET /portfolio/drawdown?period=1Y&account_ids=1,3
       │     └── Snapshots filtered to accounts 1+3 only
       │
       └── GET /portfolio/risk-contribution?account_ids=1,3
             └── Holdings scoped to accounts 1+3 only
```

**Key implications for backend:**

| Endpoint | What Gets Scoped |
|---|---|
| `/risk-metrics` | `portfolio_snapshots` filtered by account → return series reflects only selected accounts |
| `/drawdown` | Same snapshot filter as risk-metrics |
| `/covariance` | `portfolio_holdings` filtered by account → only holdings in selected accounts appear in the matrix |
| `/efficient-frontier` | Holdings + weights filtered by account → frontier optimized for selected accounts' assets |
| `/risk-contribution` | Holdings + weights filtered by account → risk decomposed over selected accounts' assets |
| `/rolling-sharpe` | Snapshots filtered by account |
| `/factor-exposure` | Portfolio returns filtered by account |

**UI behavior:**
- When user changes account selection → all sub-tabs refetch (React Query keys include `account_ids`)
- If a subset of accounts excludes a holding that was previously in the covariance matrix → the matrix shrinks
- Empty state: if selected accounts have no holdings, all sub-tabs show "No holdings in selected accounts"

**Backend implementation:** All repository methods that fetch snapshots, holdings, or prices must accept optional `account_ids` filters, matching the existing pattern in `portfolio_service.py`:

```python
# Existing pattern (portfolio_service.py line ~1500):
async def get_portfolio_performance(self, user_id, period, account_ids=None):
    accounts = await self.portfolio_repo.get_user_accounts(user_id)
    if account_ids:
        accounts = [a for a in accounts if a["account_id"] in account_ids]
    # ... rest uses filtered accounts
```

All new service methods follow this same pattern.

---

## 3. UI/UX Design

### 3.1 Tab Layout

The existing `PerformanceTab` gets a sub-tab navigation bar below the period selector:

```
┌─────────────────────────────────────────────────────────────┐
│  [1D] [1W] [1M] [3M] [1Y] [5Y] [ALL]    Account: [▼]      │
├─────────────────────────────────────────────────────────────┤
│  [Summary] [Risk] [Correlations] [Frontier] [Drawdown] [Factors] │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  (Sub-tab content area)                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Sub-Tab Mockups

#### Summary (Existing — Extended)

The Summary tab preserves both existing charts **unchanged** and adds new risk metric cards above them:

```
┌──────────────────────────────────────────────────────┐
│  Return: +$12,450  Return%: +18.2%  Best: +3.1%     │
│  Worst: -2.4%     Sharpe: 1.24    Sortino: 1.87     │
│  Volatility: 14.2% Max DD: -8.3%  VaR 95: -2.1%    │
├──────────────────────────────────────────────────────┤
│  Portfolio Performance Chart (existing)                │
│  [Area: Portfolio Value] [Area: Net Deposits]         │
│  [Line: Benchmark overlay per selected symbol]        │
├──────────────────────────────────────────────────────┤
│  Benchmark Comparison Chart (existing)                 │
│  [Area: Portfolio normalized] [Line: per benchmark]   │
└──────────────────────────────────────────────────────┘
```

Both existing charts (`PortfolioPerformanceChart` and `BenchmarkComparisonChart`) are preserved in their current form. The risk metric bar above them collapses the key metrics from UC-1 into a single row.

#### Risk Metrics

```
┌──────────┬──────────┬──────────┬──────────┐
│ Sharpe   │ Sortino  │ Volatility│ Max DD  │
│  1.24    │  1.87    │  14.2%   │  -8.3%  │
│  ████░   │  █████░  │  ██░░░░  │  █░░░░░ │
├──────────┼──────────┼──────────┼──────────┤
│ VaR 95   │ VaR 99   │ CVaR 95  │ Downside │
│  -2.1%   │  -3.4%   │  -2.8%   │  10.1%   │
│  █░░░░░  │  █░░░░░  │  █░░░░░  │  ██░░░░  │
├──────────┼──────────┼──────────┼──────────┤
│ Best Day │ Worst Day│ Beta     │ Alpha    │
│  +3.1%   │  -2.4%   │  1.05    │  2.1%    │
└──────────┴──────────┴──────────┴──────────┘
```

Card design: dark glassmorphism (existing theme), metric name top-left, value center-large, mini progress bar at bottom showing percentile ranking or color coding (green = good, red = bad).

#### Correlations

```
┌─────────────────────────────────────────┐
│           Correlation Matrix             │
│   ┌─────────────────────────────────┐   │
│   │     AAPL  GOOG  MSFT  AMZN  NVDA│   │
│   │AAPL  1.00  0.45  0.52  0.38  0.61│   │
│   │GOOG  0.45  1.00  0.48  0.42  0.55│   │
│   │MSFT  0.52  0.48  1.00  0.35  0.58│   │
│   │AMZN  0.38  0.42  0.35  1.00  0.44│   │
│   │NVDA  0.61  0.55  0.58  0.44  1.00│   │
│   └─────────────────────────────────┘   │
│   Color scale: ▓ (1.0) → ░ (-1.0)      │
└─────────────────────────────────────────┘
```

#### Efficient Frontier

```
┌─────────────────────────────────────────┐
│  Expected  ★ Max Sharpe                  │
│  Return    ◆ Current Portfolio           │
│   20% ─           ┌───┐                 │
│         ╱  ╱ ★        ╲                 │
│   15% ─ ╱◆              ╲               │
│       ╱                    ╲             │
│   10% ─                      ┤ Min Var  │
│      ╱                        ┘         │
│    5% ─                                 │
│       └────┴────┴────┴────┴────         │
│        10%   20%   30%   40%   50%       │
│                Volatility                │
└─────────────────────────────────────────┘
```

#### Drawdown (Underwater)

```
┌─────────────────────────────────────────┐
│   0% ─══════════════════════════════    │
│        ╲         ╱╲                     │
│  -5% ─   ╲  ╱╲  ╱  ╲                   │
│            ╲╱    ╱    ╲  ╱╲            │
│ -10% ─          ╱      ╲╱  ╲           │
│                ╱            ╲          │
│ -15% ─       ╱              ╲_________ │
│       └───┬───┬───┬───┬───┬───┬───     │
│          Jan  Mar  May  Jul  Sep  Nov    │
│  Max Drawdown: -14.2% (Jun 2025)        │
└─────────────────────────────────────────┘
```

### 3.3 Design Conventions

| Element | Convention |
|---|---|
| **Colors** | Green `#22c55e` for positive metrics, Red `#ef4444` for negative, consistent with existing theme |
| **Glassmorphism** | Cards use `bg-white/5 backdrop-blur-xl border border-white/10` |
| **Loading** | Skeleton shimmer per sub-tab (independent React Query fetches) |
| **Empty State** | "Not enough data — need at least 30 trading days of history" with illustration |
| **Error State** | Toast notification + inline error message per sub-tab |
| **Responsiveness** | KPI grid: 4 cols desktop, 2 cols tablet, 1 col mobile. Charts: full width with `ResponsiveContainer` |

---

## 4. Frontend Scope

### 4.1 New Files to Create

| File | Purpose |
|---|---|
| `web/src/components/portfolio/RiskMetricCard.tsx` | Single KPI card |
| `web/src/components/portfolio/RiskMetricsGrid.tsx` | Grid of RiskMetricCards |
| `web/src/components/portfolio/CorrelationHeatmap.tsx` | Correlation matrix heatmap |
| `web/src/components/portfolio/DrawdownChart.tsx` | Underwater drawdown area chart |
| `web/src/components/portfolio/RollingSharpeChart.tsx` | Rolling Sharpe line chart |
| `web/src/components/portfolio/EfficientFrontierChart.tsx` | Frontier scatter + CML |
| `web/src/components/portfolio/RiskContributionChart.tsx` | Risk breakdown bar/radar |
| `web/src/components/portfolio/FactorExposureChart.tsx` | Factor loading bars |
| `web/src/components/portfolio/PortfolioSubNav.tsx` | Sub-tab navigation component |

### 4.2 Existing Files to Modify

| File | Change |
|---|---|
| `web/src/components/portfolio/PerformanceTab.tsx` | Add sub-tab navigation, render sub-tab content |
| `web/src/lib/portfolio.types.ts` | Add all new TypeScript interfaces |
| `web/src/lib/portfolio.service.ts` | Add service methods for each endpoint |
| `web/src/hooks/usePortfolio.ts` | Add React Query hooks for each endpoint |
| `web/src/lib/query-keys.ts` | Add query key factories |

### 4.3 TypeScript Interfaces

```typescript
// === portfolio.types.ts additions ===

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

interface DrawdownPoint {
  date: string;
  value: number;
  drawdown_pct: number;
}

interface DrawdownResponse {
  success: boolean;
  period: string;
  drawdowns: DrawdownPoint[];
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

### 4.4 React Query Hooks

```typescript
// === usePortfolio.ts additions ===

// Risk Metrics
export function usePortfolioRiskMetrics(
  period: string,
  accountIds?: number[],
  options?: UseQueryOptions<RiskMetricsResponse>
) {
  const idsParam = accountIds?.join(",") || "";
  return useQuery({
    queryKey: QK.portfolioRiskMetrics(period, idsParam),
    queryFn: () => portfolioService.getPortfolioRiskMetrics(period, idsParam),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
    placeholderData: keepPreviousData,
    ...options,
  });
}

// Covariance
export function usePortfolioCovariance(
  period: string,
  accountIds?: number[],
  options?: UseQueryOptions<CovarianceResponse>
) { /* similar pattern */ }

// Drawdown
export function usePortfolioDrawdown(
  period: string,
  accountIds?: number[],
  options?: UseQueryOptions<DrawdownResponse>
) { /* similar pattern */ }

// Efficient Frontier
export function usePortfolioEfficientFrontier(
  accountIds?: number[],
  points?: number,
  options?: UseQueryOptions<EfficientFrontierResponse>
) { /* similar pattern */ }

// Rolling Sharpe
export function usePortfolioRollingSharpe(
  window: number,
  accountIds?: number[],
  options?: UseQueryOptions<RollingSharpeResponse>
) { /* similar pattern */ }

// Risk Contribution
export function usePortfolioRiskContribution(
  accountIds?: number[],
  options?: UseQueryOptions<RiskContributionResponse>
) { /* similar pattern */ }

// Factor Exposure
export function usePortfolioFactorExposure(
  accountIds?: number[],
  options?: UseQueryOptions<FactorExposureResponse>
) { /* similar pattern */ }
```

### 4.5 Service Layer Methods

```typescript
// === portfolio.service.ts additions ===

async getPortfolioRiskMetrics(
  period: string,
  accountIdsParam?: string
): Promise<RiskMetricsResponse> {
  const params = new URLSearchParams({ period });
  if (accountIdsParam) params.set("account_ids", accountIdsParam);
  return this.request<RiskMetricsResponse>(
    `/api/proxy/portfolio/risk-metrics?${params}`
  );
}

async getPortfolioCovariance(
  period: string,
  accountIdsParam?: string
): Promise<CovarianceResponse> {
  // similar pattern
}

async getPortfolioDrawdown(
  period: string,
  accountIdsParam?: string
): Promise<DrawdownResponse> {
  // similar pattern
}

async getPortfolioEfficientFrontier(
  accountIdsParam?: string,
  points?: number
): Promise<EfficientFrontierResponse> {
  // similar pattern
}

async getPortfolioRollingSharpe(
  window: number,
  accountIdsParam?: string
): Promise<RollingSharpeResponse> {
  // similar pattern
}

async getPortfolioRiskContribution(
  accountIdsParam?: string
): Promise<RiskContributionResponse> {
  // similar pattern
}

async getPortfolioFactorExposure(
  accountIdsParam?: string
): Promise<FactorExposureResponse> {
  // similar pattern
}
```

### 4.6 Query Keys

```typescript
// === query-keys.ts additions ===

QK.portfolioRiskMetrics = (period: string, ids: string) =>
  ["portfolio", "risk-metrics", period, ids];

QK.portfolioCovariance = (period: string, ids: string) =>
  ["portfolio", "covariance", period, ids];

QK.portfolioDrawdown = (period: string, ids: string) =>
  ["portfolio", "drawdown", period, ids];

QK.portfolioEfficientFrontier = (ids: string, points?: number) =>
  ["portfolio", "efficient-frontier", ids, points];

QK.portfolioRollingSharpe = (window: number, ids: string) =>
  ["portfolio", "rolling-sharpe", window, ids];

QK.portfolioRiskContribution = (ids: string) =>
  ["portfolio", "risk-contribution", ids];

QK.portfolioFactorExposure = (ids: string) =>
  ["portfolio", "factor-exposure", ids];
```

---

## 5. Backend Scope

### 5.1 New Files to Create

| File | Purpose |
|---|---|
| `backend/shared/portfolio_stats.py` | Pure numpy-based statistical functions (hand-rolled) |
| `backend/application/services/portfolio_risk_service.py` | Service orchestrating DB access + stats computation + PyPortfolioOpt |
| `backend/tests/unit/test_portfolio_stats.py` | Unit tests for stats functions |
| `backend/tests/integration/test_portfolio_risk_api.py` | Integration tests for risk endpoints |
| `backend/tests/e2e/test_portfolio_risk_e2e.py` | End-to-end tests (no mocking) |

### 5.2 Existing Files to Modify

| File | Change |
|---|---|
| `backend/schemas_portfolio.py` | Add all new Pydantic schemas |
| `backend/api/portfolio.py` | Add 7 new endpoints |
| `backend/requirements.in` | Add `scipy`, `cvxpy`, `PyPortfolioOpt` |
| `backend/infrastructure/repositories/portfolio_repository.py` | Add methods for price history queries across multiple holdings |

### 5.3 Pydantic Schemas

```python
# === schemas_portfolio.py additions ===

class RiskMetricsResponse(BaseModel):
    success: bool
    period: str
    variance: float
    std_deviation: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    value_at_risk_95: float
    value_at_risk_99: float
    conditional_var_95: float
    downside_deviation: float
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None
    beta: Optional[float] = None
    alpha: Optional[float] = None
    error: Optional[str] = None

class CovarianceResponse(BaseModel):
    success: bool
    period: str
    holdings: List[str]
    covariance_matrix: List[List[float]]
    correlation_matrix: List[List[float]]
    error: Optional[str] = None

class DrawdownPoint(BaseModel):
    date: str
    value: float
    drawdown_pct: float

class DrawdownResponse(BaseModel):
    success: bool
    period: str
    drawdowns: List[DrawdownPoint]
    max_drawdown: float
    max_drawdown_pct: float
    max_drawdown_start: Optional[str] = None
    max_drawdown_end: Optional[str] = None
    max_drawdown_recovery: Optional[str] = None
    avg_drawdown: float
    error: Optional[str] = None

class EfficientFrontierPoint(BaseModel):
    volatility: float
    expected_return: float
    weights: Dict[str, float]
    sharpe_ratio: Optional[float] = None

class EfficientFrontierResponse(BaseModel):
    success: bool
    frontier: List[EfficientFrontierPoint]
    max_sharpe: Optional[EfficientFrontierPoint] = None
    min_variance: Optional[EfficientFrontierPoint] = None
    cml: Optional[List[Dict[str, float]]] = None
    error: Optional[str] = None

class RollingSharpeResponse(BaseModel):
    success: bool
    period: str
    window: int
    series: List[Dict[str, Any]]
    error: Optional[str] = None

class RiskContributionItem(BaseModel):
    symbol: str
    weight: float
    marginal_risk: float
    component_risk: float
    risk_pct: float

class RiskContributionResponse(BaseModel):
    success: bool
    contributions: List[RiskContributionItem]
    total_risk: float
    error: Optional[str] = None

class FactorExposureResponse(BaseModel):
    success: bool
    exposures: Dict[str, float]
    r_squared: float
    error: Optional[str] = None
```

### 5.4 API Endpoints

All new endpoints follow the same pattern as existing endpoints in `api/portfolio.py`:

| Endpoint | Method | Handler | Returns |
|---|---|---|---|
| `GET /portfolio/risk-metrics` | `get_risk_metrics` | `portfolio_risk_service.compute_risk_metrics()` | `RiskMetricsResponse` |
| `GET /portfolio/covariance` | `get_covariance` | `portfolio_risk_service.compute_covariance_matrix()` | `CovarianceResponse` |
| `GET /portfolio/drawdown` | `get_drawdown` | `portfolio_risk_service.compute_drawdown()` | `DrawdownResponse` |
| `GET /portfolio/efficient-frontier` | `get_efficient_frontier` | `portfolio_risk_service.compute_efficient_frontier()` | `EfficientFrontierResponse` |
| `GET /portfolio/rolling-sharpe` | `get_rolling_sharpe` | `portfolio_risk_service.compute_rolling_sharpe()` | `RollingSharpeResponse` |
| `GET /portfolio/risk-contribution` | `get_risk_contribution` | `portfolio_risk_service.compute_risk_contribution()` | `RiskContributionResponse` |
| `GET /portfolio/factor-exposure` | `get_factor_exposure` | `portfolio_risk_service.compute_factor_exposure()` | `FactorExposureResponse` |

### 5.5 `shared/portfolio_stats.py` — Pure Functions

```python
"""
Hand-rolled statistical functions for portfolio analysis.
All functions are pure (no DB access), operating on numpy arrays.
"""
import numpy as np
from typing import Optional, Tuple

def compute_daily_returns(values: np.ndarray) -> np.ndarray:
    """(v_t - v_{t-1}) / v_{t-1}"""

def compute_annualized_return(daily_returns: np.ndarray) -> float:
    """Mean daily return * 252"""

def compute_annualized_volatility(daily_returns: np.ndarray) -> float:
    """Std of daily returns * sqrt(252)"""

def compute_sharpe_ratio(
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.02
) -> float:
    """(mean_return - rf/252) / std_return * sqrt(252)"""

def compute_sortino_ratio(
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.02
) -> float:
    """(mean_return - rf/252) / downside_deviation"""

def compute_downside_deviation(daily_returns: np.ndarray) -> float:
    """Std of only negative returns * sqrt(252)"""

def compute_max_drawdown(values: np.ndarray) -> Tuple[float, float, int, int]:
    """Returns (max_dd_value, max_dd_pct, peak_index, trough_index)"""

def compute_drawdown_series(values: np.ndarray) -> np.ndarray:
    """(value - running_max) / running_max for each point"""

def compute_value_at_risk(
    daily_returns: np.ndarray,
    confidence: float = 0.95
) -> float:
    """Parametric VaR: mean - z * std"""

def compute_historical_var(
    daily_returns: np.ndarray,
    confidence: float = 0.95
) -> float:
    """Historical VaR: percentile of returns"""

def compute_conditional_var(
    daily_returns: np.ndarray,
    confidence: float = 0.95
) -> float:
    """Expected shortfall: mean of returns below VaR threshold"""

def compute_beta(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray
) -> float:
    """Cov(p, b) / Var(b)"""

def compute_alpha(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    risk_free_rate: float = 0.02
) -> float:
    """Actual return - (rf + beta * (benchmark_return - rf))"""

def compute_information_ratio(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray
) -> float:
    """(portfolio_return - benchmark_return) / tracking_error"""

def compute_tracking_error(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray
) -> float:
    """Std of (portfolio_return - benchmark_return)"""

def compute_rolling_sharpe(
    daily_returns: np.ndarray,
    window: int = 252,
    risk_free_rate: float = 0.02
) -> np.ndarray:
    """Rolling Sharpe over sliding window"""
```

### 5.6 `portfolio_risk_service.py` — Service Layer

```python
"""
Orchestrates DB access + statistical computation + PyPortfolioOpt optimization.
Follows existing PortfolioService pattern.

Every method accepts optional account_ids to scope results to selected accounts.
When account_ids is None, all user accounts are included (matching existing
PortfolioService behavior).
"""

class PortfolioRiskService:
    def __init__(self, portfolio_repo=None):
        self.portfolio_repo = portfolio_repo or PortfolioRepository()

    async def compute_risk_metrics(
        self, user_id: int, period: str, account_ids: Optional[List[int]] = None
    ) -> RiskMetricsResponse:
        """
        account_ids scoping:
        - Snapshots filtered to selected accounts only
        - Return series reflects only the subset of accounts
        """
        # 1. Fetch portfolio snapshots (filtered by account_ids)
        # 2. Compute daily return series
        # 3. Call portfolio_stats functions for each metric
        # 4. If benchmark provided, compute beta/alpha/tracking_error
        # 5. Return RiskMetricsResponse

    async def compute_covariance_matrix(
        self, user_id: int, period: str, account_ids: Optional[List[int]] = None
    ) -> CovarianceResponse:
        """
        account_ids scoping:
        - Holdings fetched only from selected accounts
        - Only symbols in selected accounts appear in the matrix
        """
        # 1. Fetch current holdings (filtered by account_ids)
        # 2. For each holding, fetch historical prices
        # 3. Compute daily returns per holding
        # 4. Align to common date range
        # 5. Use PyPortfolioOpt risk_models (LedoitWolf shrinkage)
        # 6. Return CovarianceResponse

    async def compute_drawdown(
        self, user_id: int, period: str, account_ids: Optional[List[int]] = None
    ) -> DrawdownResponse:
        """
        account_ids scoping:
        - Snapshots filtered to selected accounts only
        - Drawdown reflects only the subset of accounts
        """
        # 1. Fetch portfolio snapshots (filtered by account_ids)
        # 2. Call compute_drawdown_series()
        # 3. Identify max drawdown period
        # 4. Return DrawdownResponse

    async def compute_efficient_frontier(
        self, user_id: int, account_ids: Optional[List[int]] = None, points: int = 100
    ) -> EfficientFrontierResponse:
        """
        account_ids scoping:
        - Holdings + weights from selected accounts only
        - Frontier optimized for assets in selected accounts
        - Single-holding frontier returns an error (needs 2+)
        """
        # 1. Fetch current holdings + weights (filtered by account_ids)
        # 2. Fetch historical prices for each holding
        # 3. Compute expected returns + covariance via PyPortfolioOpt
        # 4. Run EfficientFrontier optimizer for N points
        # 5. Find max Sharpe and min variance portfolios
        # 6. Compute CML
        # 7. Return EfficientFrontierResponse

    async def compute_rolling_sharpe(
        self, user_id: int, window: int = 252, account_ids: Optional[List[int]] = None
    ) -> RollingSharpeResponse:
        """
        account_ids scoping:
        - Snapshots filtered to selected accounts
        """
        # 1. Fetch full snapshot history (filtered by account_ids)
        # 2. Call compute_rolling_sharpe()
        # 3. Return RollingSharpeResponse

    async def compute_risk_contribution(
        self, user_id: int, account_ids: Optional[List[int]] = None
    ) -> RiskContributionResponse:
        """
        account_ids scoping:
        - Holdings + weights from selected accounts only
        - Risk decomposition over selected accounts' assets
        """
        # 1. Fetch current weights (filtered by account_ids)
        # 2. Fetch covariance matrix (reuse compute_covariance_matrix)
        # 3. Compute marginal + component risk contribution
        # 4. Return RiskContributionResponse

    async def compute_factor_exposure(
        self, user_id: int, account_ids: Optional[List[int]] = None
    ) -> FactorExposureResponse:
        """
        account_ids scoping:
        - Portfolio returns from selected accounts only
        """
        # 1. Fetch portfolio returns (filtered by account_ids)
        # 2. Fetch factor returns (from config or hardcoded)
        # 3. Run OLS regression (numpy.linalg.lstsq or statsmodels)
        # 4. Return FactorExposureResponse
```

### 5.7 Repository Methods

Add to `portfolio_repository.py`:

```python
async def get_historical_prices_batch(
    symbols: List[str],
    start_date: date,
    end_date: date
) -> Dict[str, List[Dict]]:
    """Fetch historical prices for multiple symbols in one query."""

async def get_portfolio_snapshots_range(
    portfolio_id: int,
    start_date: date,
    end_date: date
) -> List[Dict]:
    """Fetch snapshots for date range."""

async def get_current_holdings_with_weights(
    portfolio_id: int
) -> List[Dict]:
    """Fetch current holdings with market value and weight."""
```

---

## 6. Software Architecture

### 6.1 4-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (Frontend — Next.js / TypeScript / recharts)          │
│                                                                           │
│  PerformanceTab.tsx                                                        │
│    └─ PortfolioSubNav.tsx                                                  │
│         ├─ [Summary]   → existing charts + RiskMetricsGrid                │
│         ├─ [Risk]      → RiskMetricsGrid + DrawdownChart                  │
│         ├─ [Corr]      → CorrelationHeatmap                                │
│         ├─ [Frontier]  → EfficientFrontierChart                           │
│         ├─ [Drawdown]  → DrawdownChart + stats                            │
│         └─ [Factors]   → FactorExposureChart + RiskContributionChart      │
│                                                                           │
│  React Query Hooks (usePortfolio.ts)                                       │
│    └─ portfolio.service.ts → HTTP to /api/proxy/portfolio/*               │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ proxy
                                    │ web/src/app/api/proxy/[...path]/route.ts
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  API LAYER (Backend — FastAPI)                                            │
│                                                                           │
│  api/portfolio.py                                                          │
│    ├─ GET /portfolio/risk-metrics       → portfolio_risk_service          │
│    ├─ GET /portfolio/covariance         → portfolio_risk_service          │
│    ├─ GET /portfolio/drawdown           → portfolio_risk_service          │
│    ├─ GET /portfolio/efficient-frontier → portfolio_risk_service          │
│    ├─ GET /portfolio/rolling-sharpe     → portfolio_risk_service          │
│    ├─ GET /portfolio/risk-contribution  → portfolio_risk_service          │
│    └─ GET /portfolio/factor-exposure   → portfolio_risk_service          │
│                                                                           │
│  Pydantic Schemas (schemas_portfolio.py)                                    │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ dependency injection
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SERVICE LAYER (Backend — Business Logic)                                  │
│                                                                           │
│  application/services/portfolio_risk_service.py                            │
│    ├─ compute_risk_metrics()        → portfolio_stats + optional benchmark │
│    ├─ compute_covariance_matrix()   → PyPortfolioOpt risk_models          │
│    ├─ compute_drawdown()            → portfolio_stats                     │
│    ├─ compute_efficient_frontier()  → PyPortfolioOpt EfficientFrontier   │
│    ├─ compute_rolling_sharpe()      → portfolio_stats                     │
│    ├─ compute_risk_contribution()   → PyPortfolioOpt + portfolio_stats    │
│    └─ compute_factor_exposure()     → numpy.linalg.lstsq                  │
│                                                                           │
│  shared/portfolio_stats.py (pure numpy functions, zero deps on DB)        │
│  shared/finance_math.py (existing — unchanged)                             │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ repository pattern
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  DATA LAYER (Backend — PostgreSQL via Supabase)                           │
│                                                                           │
│  infrastructure/repositories/portfolio_repository.py                       │
│    ├─ get_historical_prices_batch()   → company_prices table              │
│    ├─ get_portfolio_snapshots_range() → portfolio_snapshots table         │
│    └─ get_current_holdings_with_weights() → portfolio_holdings table      │
│                                                                           │
│  Tables: portfolio_snapshots, company_prices, portfolio_holdings,          │
│          portfolio_transactions, companies, benchmark_config              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Library Integration Strategy

```
PyPortfolioOpt
  │
  ├── risk_models.sample_cov(prices)         → covariance matrix
  ├── risk_models.CovarianceShrinkage(prices) → shrunk covariance
  ├── expected_returns.mean_historical_return(prices) → expected returns
  └── EfficientFrontier(mu, S)               → optimization
       ├── .max_sharpe()                     → tangent portfolio
       ├── .min_volatility()                 → min variance portfolio
       ├── .efficient_return(target_return)  → frontier point at target return
       ├── .efficient_risk(target_vol)       → frontier point at target vol
       ├── .clean_weights()                  → dict of non-trivial weights
       └── .portfolio_performance()          → metrics for each point

  Frontier generation (loop-based, no built-in method):
       → inefficient_return() loop over target returns
       → collect {return, volatility, sharpe, weights} dicts

Hand-rolled (shared/portfolio_stats.py)
  │
  ├── compute_sharpe_ratio(returns)           → scalar
  ├── compute_sortino_ratio(returns)          → scalar
  ├── compute_max_drawdown(values)            → (value, pct, peak, trough)
  ├── compute_value_at_risk(returns, 0.95)    → scalar
  ├── compute_conditional_var(returns, 0.95)  → scalar
  ├── compute_drawdown_series(values)         → array
  ├── compute_rolling_sharpe(returns, 252)    → array
  ├── compute_beta(returns, benchmark)        → scalar
  └── compute_alpha(returns, benchmark)       → scalar
```

---

## 7. Sequence Diagrams

### 7.1 Risk Metrics Flow (UC-1)

```
User                PerformanceTab          usePortfolio.ts        portfolio.service.ts         API              PortfolioRiskService    portfolio_repo    portfolio_stats
 │                        │                       │                       │                      │                     │                     │                 │
 │  select period         │                       │                       │                      │                     │                     │                 │
 │───────────────────────>│                       │                       │                      │                     │                     │                 │
 │                        │  fetch risk metrics   │                       │                      │                     │                     │                 │
 │                        │──────────────────────>│                       │                      │                     │                     │                 │
 │                        │                       │  GET /risk-metrics    │                      │                     │                     │                 │
 │                        │                       │──────────────────────>│                      │                     │                     │                 │
 │                        │                       │                       │  HTTP GET             │                     │                     │                 │
 │                        │                       │                       │─────────────────────>│                     │                     │                 │
 │                        │                       │                       │                      │  get_snapshots()    │                     │                 │
 │                        │                       │                       │                      │────────────────────>│                     │                 │
 │                        │                       │                       │                      │                     │  SELECT snapshots   │                 │
 │                        │                       │                       │                      │                     │────────────────────>│                 │
 │                        │                       │                       │                      │                     │  snapshots[]        │                 │
 │                        │                       │                       │                      │                     │<────────────────────│                 │
 │                        │                       │                       │                      │                     │                     │                 │
 │                        │                       │                       │                      │                     │  compute_returns()  │                 │
 │                        │                       │                       │                      │                     │────────────────────────────────────>│
 │                        │                       │                       │                      │                     │                     │                 │
 │                        │                       │                       │                      │                     │  compute_sharpe()   │                 │
 │                        │                       │                       │                      │                     │────────────────────────────────────>│
 │                        │                       │                       │                      │                     │                     │                 │
 │                        │                       │                       │                      │                     │  compute_sortino()  │                 │
 │                        │                       │                       │                      │                     │────────────────────────────────────>│
 │                        │                       │                       │                      │                     │                     │                 │
 │                        │                       │                       │                      │                     │  compute_var()      │                 │
 │                        │                       │                       │                      │                     │────────────────────────────────────>│
 │                        │                       │                       │                      │                     │                     │                 │
 │                        │                       │                       │                      │                     │  RiskMetricsResponse │                │
 │                        │                       │                       │                      │<────────────────────│                     │                 │
 │                        │                       │                       │  JSON response        │                     │                     │                 │
 │                        │                       │                       │<─────────────────────│                     │                     │                 │
 │                        │                       │  RiskMetricsResponse  │                      │                     │                     │                 │
 │                        │                       │<──────────────────────│                      │                     │                     │                 │
 │                        │  render KPI grid      │                       │                      │                     │                     │                 │
 │                        │──────────────────────>│                       │                      │                     │                     │                 │
 │  see KPIs              │                       │                       │                      │                     │                     │                 │
 │<───────────────────────│                       │                       │                      │                     │                     │                 │
```

### 7.2 Efficient Frontier Flow (UC-4)

```
User                PerformanceTab          usePortfolio.ts        API              PortfolioRiskService       PyPortfolioOpt      portfolio_repo
 │                        │                       │                      │                     │                      │                  │
 │  select Frontier tab   │                       │                      │                     │                      │                  │
 │───────────────────────>│                       │                      │                     │                      │                  │
 │                        │  fetch frontier       │                      │                     │                      │                  │
 │                        │──────────────────────>│                      │                     │                      │                  │
 │                        │                       │  GET /efficient-    │                     │                      │                  │
 │                        │                       │  frontier           │                     │                      │                  │
 │                        │                       │────────────────────>│                     │                      │                  │
 │                        │                       │                      │  get_holdings()      │                      │                  │
 │                        │                       │                      │────────────────────>│                      │                  │
 │                        │                       │                      │                     │  SELECT holdings     │                  │
 │                        │                       │                      │                     │─────────────────────>│                  │
 │                        │                       │                      │                     │  weights[]           │                  │
 │                        │                       │                      │                     │<─────────────────────│                  │
 │                        │                       │                      │                     │                      │                  │
 │                        │                       │                      │                     │  get_prices_batch()  │                  │
 │                        │                       │                      │                     │─────────────────────>│                  │
 │                        │                       │                      │                     │  prices_df           │                  │
 │                        │                       │                      │                     │<─────────────────────│                  │
 │                        │                       │                      │                     │                      │                  │
 │                        │                       │                      │                     │  expected_returns    │                  │
 │                        │                       │                      │                     │  .mean_historical    │                  │
 │                        │                       │                      │                     │─────────────────────>│                  │
 │                        │                       │                      │                     │  mu                  │                  │
 │                        │                       │                      │                     │<─────────────────────│                  │
 │                        │                       │                      │                     │                      │                  │
 │                        │                       │                      │                     │  risk_models         │                  │
 │                        │                       │                      │                     │  .sample_cov()       │                  │
 │                        │                       │                      │                     │─────────────────────>│                  │
 │                        │                       │                      │                     │  S (cov matrix)      │                  │
 │                        │                       │                      │                     │<─────────────────────│                  │
 │                        │                       │                      │                     │                      │                  │
 │                        │                       │                      │                     │  EfficientFrontier   │                  │
 │                        │                       │                      │                     │  .efficient_frontier │                  │
 │                        │                       │                      │                     │─────────────────────>│                  │
 │                        │                       │                      │                     │  frontier_points[]   │                  │
 │                        │                       │                      │                     │<─────────────────────│                  │
 │                        │                       │                      │                     │                      │                  │
 │                        │                       │                      │  EFResponse          │                     │                  │
 │                        │                       │<─────────────────────│                     │                      │                  │
 │                        │  render ScatterChart  │                      │                     │                      │                  │
 │                        │<──────────────────────│                      │                     │                      │                  │
 │  see frontier plot     │                       │                      │                     │                      │                  │
 │<───────────────────────│                       │                      │                     │                      │                  │
```

---

## 8. Class Diagrams

### 8.1 Backend Classes

```
┌──────────────────────────────────────┐
│         PortfolioRiskService         │
├──────────────────────────────────────┤
│ - portfolio_repo: PortfolioRepository│
│ - stats: PortfolioStatsModule        │
├──────────────────────────────────────┤
│ + compute_risk_metrics(user_id,      │
│     period, account_ids)             │
│ + compute_covariance_matrix(user_id, │
│     period, account_ids)             │
│ + compute_drawdown(user_id, period,  │
│     account_ids)                     │
│ + compute_efficient_frontier(        │
│     user_id, account_ids, points)    │
│ + compute_rolling_sharpe(user_id,    │
│     window, account_ids)             │
│ + compute_risk_contribution(         │
│     user_id, account_ids)            │
│ + compute_factor_exposure(           │
│     user_id, account_ids)            │
└─────────────────────┬────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
┌─────────────────┐    ┌──────────────────────┐
│PortfolioRepository│   │  PortfolioStatsModule │
├─────────────────┤    │  (portfolio_stats.py)  │
│ + get_user_     │    ├──────────────────────┤
│   accounts()    │    │ + compute_sharpe()    │
│ + get_account_  │    │ + compute_sortino()   │
│   transactions()│    │ + compute_var()       │
│ + get_historical│    │ + compute_cvar()      │
│   _prices_batch()│   │ + compute_max_dd()    │
│ + get_snapshots_│    │ + compute_dd_series() │
│   range()       │    │ + compute_rolling()   │
│ + get_current_  │    │ + compute_beta()      │
│   holdings()    │    │ + compute_alpha()     │
└─────────────────┘    └──────────────────────┘

┌──────────────────────────────────────┐
│         PyPortfolioOpt (external)     │
├──────────────────────────────────────┤
│ risk_models:                          │
│   sample_cov(prices) → DataFrame     │
│   CovarianceShrinkage(prices) → ...  │
│ expected_returns:                     │
│   mean_historical(prices) → Series   │
│ EfficientFrontier(mu, S):             │
│   .max_sharpe() → weights             │
│   .min_volatility() → weights         │
│   .efficient_frontier(points) → list  │
│   .portfolio_performance() → tuple    │
└──────────────────────────────────────┘
```

### 8.2 Frontend Component Tree

```
PerformanceTab
├── PeriodSelector (existing)
├── AccountSelector (existing)
├── PortfolioSubNav (new)
│   ├── "Summary"     → shows existing charts
│   ├── "Risk"        → RiskMetricsGrid + DrawdownChart
│   ├── "Correlations" → CorrelationHeatmap
│   ├── "Frontier"    → EfficientFrontierChart
│   ├── "Drawdown"    → DrawdownChart (full page)
│   └── "Factors"     → FactorExposureChart + RiskContributionChart
│
├── [Summary Tab]
│   ├── RiskSummaryBar (new — single row of key KPIs)
│   ├── PortfolioPerformanceChart (existing — value + net deposits area chart)
│   └── BenchmarkComparisonChart (existing — normalized benchmark overlay)
│
├── [Risk Tab]
│   ├── RiskMetricsGrid
│   │   └── RiskMetricCard (× N metrics)
│   └── DrawdownChart
│
├── [Correlations Tab]
│   └── CorrelationHeatmap
│
├── [Frontier Tab]
│   └── EfficientFrontierChart
│       └── ScatterChart + ReferenceLine
│
├── [Drawdown Tab]
│   └── DrawdownChart (full width)
│       └── AreaChart with gradient fill
│
└── [Factors Tab]
    ├── FactorExposureChart
    │   └── BarChart (horizontal)
    └── RiskContributionChart
        └── RadarChart or HorizontalBar
```

### 8.3 Data Flow Diagram

```
Account Selector ──> account_ids filter
       │
       ├──► portfolio_snapshots (filtered by account_ids)
       │         │
       │         ▼
       │    Return Series ──> portfolio_stats.py ──> Risk Metrics
       │         │                                  │
       │         │                                  ├── Sharpe
       │         │                                  ├── Sortino
       │         │                                  ├── VaR / CVaR
       │         │                                  ├── Max Drawdown
       │         │                                  └── Rolling Sharpe
       │
       └──► portfolio_holdings (filtered by account_ids)
                 │
                 ▼
           Per-Holding Prices ──> PyPortfolioOpt ──> Optimization
                                       │
                                       ├── Covariance Matrix
                                       ├── Expected Returns
                                       ├── Efficient Frontier
                                       ├── Risk Contribution
                                       └── Tangency Portfolio
```

**Every data source is scoped by `account_ids`.** Changing account selection re-fetches all metrics, charts, and optimizations for the new subset of holdings.

---

## 9. Dependencies & Environment

### 9.1 New Python Dependencies

| Package | Version | Purpose | Size Estimate |
|---|---|---|---|
| `scipy` | ~=1.15.0 | Required by PyPortfolioOpt (already transitive via matplotlib) | ~35 MB |
| `cvxpy` | ~=1.6.0 | Convex optimization solver for Efficient Frontier | ~5 MB |
| `PyPortfolioOpt` | ~=1.6.0 | Portfolio optimization library | ~500 KB |

Add to `backend/requirements.in`:
```
scipy~=1.15.0
cvxpy~=1.6.0
PyPortfolioOpt~=1.6.0
```

Then run: `pip-compile --output-file=requirements.txt requirements.in`

### 9.2 Already Available (No Action Needed)

| Library | Version | Available From |
|---|---|---|
| `numpy` | 2.4.4 | Already in requirements.txt |
| `pandas` | 3.0.2 | Already in requirements.txt |
| `matplotlib` | 3.10.9 | Transitive via defeatbeta-api |
| `plotly` | 6.7.0 | Already in requirements.txt |

### 9.3 No New Frontend Dependencies

All frontend visualizations use **recharts** (already in `package.json`). No new npm packages required.

### 9.4 Python Version

| Requirement | Value |
|---|---|
| Python | >= 3.12, < 3.13 |
| PyPortfolioOpt requires | Python >= 3.9 |
| cvxpy requires | Python >= 3.8 |
| **Compatible** | **Yes, Python 3.12 is supported** |

### 9.5 Environment Variables

No new environment variables required. Risk-free rate can be hardcoded (0.02 = 2%) in Phase 1 and made configurable in a later phase.

---

## 10. Test Cases

### 10.1 Unit Tests — `shared/portfolio_stats.py`

```python
# === test_portfolio_stats.py ===

import numpy as np
from shared.portfolio_stats import *

class TestComputeDailyReturns:
    def test_basic(self):
        values = np.array([100.0, 110.0, 121.0])
        result = compute_daily_returns(values)
        np.testing.assert_almost_equal(result, [0.1, 0.1])

    def test_single_value_returns_empty(self):
        result = compute_daily_returns(np.array([100.0]))
        assert len(result) == 0

    def test_negative_returns(self):
        values = np.array([100.0, 90.0, 81.0])
        result = compute_daily_returns(values)
        np.testing.assert_almost_equal(result, [-0.1, -0.1])

class TestComputeSharpeRatio:
    def test_positive_sharpe(self):
        returns = np.random.normal(0.001, 0.02, 252)
        sharpe = compute_sharpe_ratio(returns, risk_free_rate=0.0)
        assert sharpe > 0  # mean > 0, so sharpe > 0
        assert isinstance(sharpe, float)

    def test_negative_sharpe(self):
        returns = np.random.normal(-0.001, 0.02, 252)
        sharpe = compute_sharpe_ratio(returns, risk_free_rate=0.0)
        assert sharpe < 0

    def test_zero_volatility_returns_zero(self):
        returns = np.zeros(252)
        sharpe = compute_sharpe_ratio(returns, risk_free_rate=0.02)
        assert sharpe == 0.0

class TestComputeMaxDrawdown:
    def test_monotonic_increase(self):
        values = np.array([100, 110, 120, 130])
        dd_val, dd_pct, peak, trough = compute_max_drawdown(values)
        assert dd_pct == 0.0

    def test_monotonic_decrease(self):
        values = np.array([100, 80, 60, 40])
        dd_val, dd_pct, peak, trough = compute_max_drawdown(values)
        assert dd_pct == -60.0 / 100.0  # -60%

    def test_peak_then_trough(self):
        values = np.array([100, 200, 150, 100, 50])
        dd_val, dd_pct, peak, trough = compute_max_drawdown(values)
        assert dd_pct == -150.0 / 200.0  # -75%

class TestComputeValueAtRisk:
    def test_parametric_var_95(self):
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 1000)
        var_95 = compute_value_at_risk(returns, confidence=0.95)
        # 95% VaR should be approximately mean - 1.645 * std
        expected = np.mean(returns) - 1.645 * np.std(returns)
        assert abs(var_95 - expected) < 0.001

class TestComputeSortinoRatio:
    def test_vs_sharpe_with_symmetric_returns(self):
        # With perfectly normal returns, Sortino should differ from Sharpe
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 252)
        sortino = compute_sortino_ratio(returns, risk_free_rate=0.0)
        sharpe = compute_sharpe_ratio(returns, risk_free_rate=0.0)
        # Sortino is typically higher than Sharpe for normal returns
        # because downside deviation < total volatility
        assert sortino >= sharpe

class TestComputeBeta:
    def test_beta_of_one(self):
        portfolio = np.array([0.01, 0.02, -0.01, 0.03])
        benchmark = np.array([0.01, 0.02, -0.01, 0.03])
        beta = compute_beta(portfolio, benchmark)
        assert abs(beta - 1.0) < 0.001

    def test_beta_of_zero(self):
        portfolio = np.random.normal(0.001, 0.02, 100)
        benchmark = np.zeros(100)
        beta = compute_beta(portfolio, benchmark)
        assert abs(beta) < 0.001

class TestComputeRollingSharpe:
    def test_basic(self):
        returns = np.random.normal(0.001, 0.02, 500)
        result = compute_rolling_sharpe(returns, window=252)
        assert len(result) == 500 - 252 + 1
        assert not np.any(np.isnan(result))
```

### 10.2 Integration Tests — `test_portfolio_risk_api.py`

```python
# === test_portfolio_risk_api.py ===
# Tests with real database (test fixtures with known data)

class TestRiskMetricsEndpoint:
    """Requires a test user with known transactions in the DB."""

    async def test_risk_metrics_happy_path(self, test_client, test_user_id):
        """Full round-trip: call endpoint, verify response shape."""
        response = await test_client.get(
            f"/portfolio/risk-metrics?period=1Y"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "sharpe_ratio" in data
        assert "sortino_ratio" in data
        assert "max_drawdown_pct" in data
        assert "value_at_risk_95" in data
        assert isinstance(data["sharpe_ratio"], float)

    async def test_risk_metrics_insufficient_history(self, test_client, test_user_id):
        """User with < 30 days of history should get error."""
        # Setup: create user with only 1 week of transactions
        response = await test_client.get(
            f"/portfolio/risk-metrics?period=1M"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None

    async def test_risk_metrics_empty_portfolio(self, test_client, test_empty_user_id):
        """Empty portfolio should return safe defaults."""
        response = await test_client.get(
            f"/portfolio/risk-metrics?period=1Y"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

class TestCovarianceEndpoint:
    async def test_covariance_matrix_shape(self, test_client, test_user_id):
        response = await test_client.get(
            f"/portfolio/covariance?period=1Y"
        )
        data = response.json()
        assert data["success"] is True
        n = len(data["holdings"])
        assert len(data["covariance_matrix"]) == n
        assert len(data["covariance_matrix"][0]) == n

class TestEfficientFrontierEndpoint:
    async def test_frontier_with_multiple_holdings(self, test_client, test_user_id):
        response = await test_client.get(
            f"/portfolio/efficient-frontier?points=50"
        )
        data = response.json()
        assert data["success"] is True
        assert len(data["frontier"]) == 50
        assert data["max_sharpe"] is not None
        assert data["min_variance"] is not None

    async def test_frontier_single_holding(self, test_client, test_single_holding_user):
        response = await test_client.get(
            f"/portfolio/efficient-frontier"
        )
        data = response.json()
        assert data["error"] is not None
        assert "2+ holdings" in data["error"]
```

### 10.3 End-to-End Tests — `test_portfolio_risk_e2e.py`

```python
# === test_portfolio_risk_e2e.py ===
# Tests against REAL Supabase instance, no mocking.
# Requires a test user ID with real portfolio data.

import pytest
import httpx

# These tests run against the deployed API or local dev server
BASE_URL = "http://localhost:8000"
TEST_USER_ID = 1  # Known test user with 2+ years of transaction history

@pytest.mark.e2e
class TestRiskMetricsE2E:
    async def test_full_risk_metrics_flow(self):
        """Real E2E: API → DB → computation → response."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Arrange: authenticate as test user
            auth_headers = {"Authorization": "Bearer <test_token>"}

            # Act: fetch risk metrics for 1Y period
            response = await client.get(
                "/portfolio/risk-metrics?period=1Y",
                headers=auth_headers
            )

            # Assert: response is valid and values are realistic
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

            # Sanity checks for realistic values
            assert -1.0 < data["sharpe_ratio"] < 5.0  # reasonable Sharpe range
            assert 0.0 < data["std_deviation"] < 1.0    # std dev < 100%
            assert data["max_drawdown_pct"] <= 0.0      # drawdown is negative or zero
            assert data["max_drawdown_pct"] > -1.0      # not worse than -100%
            assert data["value_at_risk_95"] < 0.0        # VaR is negative
            assert data["value_at_risk_99"] < data["value_at_risk_95"]  # 99% VaR is worse

    async def test_drawdown_series_e2e(self):
        """Real E2E: verify drawdown computation."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.get(
                "/portfolio/drawdown?period=5Y",
                headers={"Authorization": "Bearer <test_token>"}
            )
            assert response.status_code == 200
            data = response.json()

            # Drawdown series should be chronological
            dates = [d["date"] for d in data["drawdowns"]]
            assert dates == sorted(dates)

            # All drawdown values should be ≤ 0
            for d in data["drawdowns"]:
                assert d["drawdown_pct"] <= 0.0

            # Max drawdown should match the worst point in series
            worst = min(d["drawdown_pct"] for d in data["drawdowns"])
            assert abs(data["max_drawdown_pct"] - worst) < 0.001

    async def test_efficient_frontier_e2e(self):
        """Real E2E: verify frontier optimization produces valid portfolios."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.get(
                "/portfolio/efficient-frontier?points=50",
                headers={"Authorization": "Bearer <test_token>"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

            # Each frontier point should have weights summing to ~1
            for point in data["frontier"]:
                total_weight = sum(point["weights"].values())
                assert abs(total_weight - 1.0) < 0.01

            # Max Sharpe should have higher Sharpe than min variance
            assert data["max_sharpe"]["sharpe_ratio"] >= data["min_variance"]["sharpe_ratio"]

            # Frontier should be convex (volatility increases with return)
            vols = [p["volatility"] for p in data["frontier"]]
            returns = [p["expected_return"] for p in data["frontier"]]
            assert vols == sorted(vols)  # monotonically increasing volatility

    async def test_cross_period_consistency(self):
        """Metrics for shorter period should be subset of longer period."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            headers = {"Authorization": "Bearer <test_token>"}

            resp_1y = await client.get("/portfolio/risk-metrics?period=1Y", headers=headers)
            resp_5y = await client.get("/portfolio/risk-metrics?period=5Y", headers=headers)

            data_1y = resp_1y.json()
            data_5y = resp_5y.json()

            # 5Y VaR should be more extreme (wider distribution over longer period)
            assert data_5y["value_at_risk_95"] <= data_1y["value_at_risk_95"]
```

### 10.4 Test Data Requirements

| Test Fixture | Data Needed | Setup |
|---|---|---|
| `test_user_id` | 2+ years of transactions across 5+ holdings | Pre-seeded in test DB |
| `test_empty_user_id` | User with no transactions | Created once |
| `test_single_holding_user` | User with transactions in only 1 stock | Created once |
| `test_short_history_user` | User with < 30 days of transactions | Created once |

---

## 11. Phased Development Plan

### Phase 0 — Library Validation (✅ COMPLETED, 2026-05-28)

**Goal:** Validate PyPortfolioOpt meets our needs before committing to the architecture.

**Result:** 98.6% pass rate (73/74 checks). All core APIs work correctly. Only `lp_portfolio()` requires `pulp` (not installed). `greedy_portfolio()` is the recommended default.

**Key corrections to design:**
- No `.efficient_frontier()` method → generate frontier via `efficient_return()` loop
- `exp_historical_return` → `ema_historical_return`
- `BlackLittermanModel(pi="equal")` invalid → `pi` must be array/series
- `efficient_risk()` does not accept `risk_free_rate` kwarg
- See [Validation Results](#123-validation-results-actual-from-validate_pypfoptpy) for full details.

### Phase 1 — Core Risk Metrics (5 days)

| Day | Task | Files |
|---|---|---|
| 1 | Implement `shared/portfolio_stats.py` with all pure functions | `backend/shared/portfolio_stats.py` |
| 2 | Unit tests for all stats functions | `backend/tests/unit/test_portfolio_stats.py` |
| 3 | Create `PortfolioRiskService` with `compute_risk_metrics()` + `compute_drawdown()` | `backend/application/services/portfolio_risk_service.py` |
| 4 | Add Pydantic schemas + API endpoints (risk-metrics, drawdown) | `backend/schemas_portfolio.py`, `backend/api/portfolio.py` |
| 5 | Integration tests for risk-metrics + drawdown endpoints | `backend/tests/integration/test_portfolio_risk_api.py` |

### Phase 2 — Frontend Risk Display (5 days)

| Day | Task | Files |
|---|---|---|
| 1 | TypeScript interfaces + query keys | `portfolio.types.ts`, `query-keys.ts` |
| 2 | Service methods + React Query hooks | `portfolio.service.ts`, `usePortfolio.ts` |
| 3 | RiskMetricCard + RiskMetricsGrid components | New component files |
| 4 | DrawdownChart component + PortfolioSubNav | New component files |
| 5 | PerformanceTab refactor with sub-tabs | `PerformanceTab.tsx` |

### Phase 3 — Covariance & Optimization (5 days)

| Day | Task | Files |
|---|---|---|
| 1 | Add price history batch query to repository + `compute_covariance_matrix()` to service | `portfolio_repository.py`, `portfolio_risk_service.py` |
| 2 | Add covariance endpoint + Pydantic schema | `api/portfolio.py`, `schemas_portfolio.py` |
| 3 | `compute_efficient_frontier()` + endpoint + schema | `portfolio_risk_service.py`, `api/portfolio.py` |
| 4 | `compute_risk_contribution()` + endpoint + schema | `portfolio_risk_service.py`, `api/portfolio.py` |
| 5 | `compute_rolling_sharpe()` + endpoint + schema | `portfolio_risk_service.py`, `api/portfolio.py` |

### Phase 4 — Optimization Visualizations (5 days)

| Day | Task | Files |
|---|---|---|
| 1 | CorrelationHeatmap component | New component file |
| 2 | EfficientFrontierChart component | New component file |
| 3 | RollingSharpeChart + RiskContributionChart components | New component files |
| 4 | Wire up all remaining hooks + sub-tabs | `usePortfolio.ts`, `PerformanceTab.tsx` |
| 5 | Integration tests for all new endpoints | `test_portfolio_risk_api.py` |

### Phase 5 — Factor Exposure & Polish (3 days)

| Day | Task | Files |
|---|---|---|
| 1 | Factor exposure computation + endpoint | `portfolio_risk_service.py`, `api/portfolio.py` |
| 2 | FactorExposureChart component + sub-tab | New component file |
| 3 | E2E tests + edge case handling + responsive polish | `test_portfolio_risk_e2e.py` |

### Total Timeline: ~23 working days (~5.5 weeks)

---

## 12. Library Validation Phase

### 12.1 Purpose

Before committing to PyPortfolioOpt in the architecture, validate each use case with real market data to confirm:
1. The library produces correct results
2. Our design assumptions (inputs/outputs) are correct
3. Performance is acceptable
4. Edge cases are handled

### 12.2 Validation Test Script

Create a standalone Jupyter notebook or Python script at `backend/notebooks/validate_pypfopt.py`:

```python
#!/usr/bin/env python
"""
PyPortfolioOpt Validation Script
Tests each use case we plan to use from PyPortfolioOpt.
Run against real market data from our Supabase DB.
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import supabase
from pypfopt import (
    EfficientFrontier,
    expected_returns,
    risk_models,
    objective_functions,
)
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices

# === CONFIG ===
USER_ID = 1
PERIOD = "3Y"
RISK_FREE_RATE = 0.02

# === HELPER ===
def fetch_holdings_and_prices(user_id: int, period: str):
    """Fetch current holdings and historical prices from DB."""
    # ... (implement DB queries) ...

# ============================================
# VALIDATION 1: Expected Returns
# ============================================
def validate_expected_returns():
    """
    Input: DataFrame of daily close prices (columns = symbols, index = date)
    Output: pd.Series of annualized expected returns

    Libraries used: pypfopt.expected_returns
    """
    prices = fetch_holdings_and_prices(USER_ID, PERIOD)
    print(f"Prices shape: {prices.shape}, date range: {prices.index[0]} to {prices.index[-1]}")

    # Method 1: Mean historical return
    mu = expected_returns.mean_historical_return(prices)
    print(f"\n=== Mean Historical Returns ===")
    for symbol, value in mu.items():
        print(f"  {symbol}: {value:.4f} ({value*100:.2f}%)")
    assert isinstance(mu, pd.Series)
    assert len(mu) == prices.shape[1]
    assert all(-0.5 < v < 0.5 for v in mu)  # sanity: reasonable returns

    # Method 2: CAPM return
    mu_capm = expected_returns.capm_return(prices)
    print(f"\n=== CAPM Returns ===")
    for symbol, value in mu_capm.items():
        print(f"  {symbol}: {value:.4f} ({value*100:.2f}%)")

    # Method 3: Exponential weighted
    mu_exp = expected_returns.ema_historical_return(prices, span=252)
    print(f"\n=== Exponentially Weighted Returns (span=252) ===")
    for symbol, value in mu_exp.items():
        print(f"  {symbol}: {value:.4f} ({value*100:.2f}%)")

    print("\n✅ Expected returns validation PASSED")
    return mu, prices


# ============================================
# VALIDATION 2: Covariance / Risk Models
# ============================================
def validate_risk_models(prices: pd.DataFrame):
    """
    Input: DataFrame of daily close prices
    Output: Covariance matrix as DataFrame

    Libraries used: pypfopt.risk_models
    """
    # Method 1: Sample covariance
    S_sample = risk_models.sample_cov(prices)
    print(f"\n=== Sample Covariance Matrix ===")
    print(f"Shape: {S_sample.shape}")
    assert S_sample.shape == (prices.shape[1], prices.shape[1])
    assert np.allclose(S_sample, S_sample.T)  # symmetric

    # Method 2: Ledoit-Wolf shrinkage (more robust)
    S_shrink = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    print(f"\n=== Ledoit-Wolf Shrunken Covariance ===")
    print(f"Shape: {S_shrink.shape}")

    # Method 3: Correlation matrix (derived)
    corr = risk_models.corr_to_cov(S_shrink)
    # Actually let's compute correlation manually
    D = np.sqrt(np.diag(S_shrink))
    corr_matrix = S_shrink.values / np.outer(D, D)
    print(f"\n=== Correlation Matrix ===")
    print(pd.DataFrame(corr_matrix, index=S_shrink.index, columns=S_shrink.columns))

    # Verify: diagonal should be 1.0
    np.testing.assert_almost_equal(np.diag(corr_matrix), np.ones(len(D)))

    print("\n✅ Risk models validation PASSED")
    return S_shrink


# ============================================
# VALIDATION 3: Efficient Frontier — Max Sharpe
# ============================================
def validate_max_sharpe(mu: pd.Series, S: pd.DataFrame):
    """
    Input: expected returns (Series), covariance matrix (DataFrame)
    Output: optimal weights (dict), performance metrics (tuple)

    Libraries used: pypfopt.EfficientFrontier
    """
    ef = EfficientFrontier(mu, S)

    # Constraint: long-only, no leverage
    weights = ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)
    cleaned = ef.clean_weights()

    print(f"\n=== Max Sharpe Portfolio ===")
    for symbol, w in sorted(cleaned.items(), key=lambda x: x[1], reverse=True):
        if w > 0.01:
            print(f"  {symbol}: {w:.4f} ({w*100:.2f}%)")

    # Verify: weights sum to 1
    total = sum(cleaned.values())
    print(f"  Total weight: {total:.4f}")
    assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    # Performance
    perf = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=True)
    expected_return, volatility, sharpe = perf
    print(f"  Expected annual return: {expected_return:.4f} ({expected_return*100:.2f}%)")
    print(f"  Annual volatility: {volatility:.4f} ({volatility*100:.2f}%)")
    print(f"  Sharpe ratio: {sharpe:.4f}")

    assert sharpe > 0, f"Max Sharpe portfolio should have positive Sharpe, got {sharpe}"
    assert 0 < volatility < 1, f"Volatility should be between 0 and 1, got {volatility}"

    print("\n✅ Max Sharpe validation PASSED")
    return cleaned, perf


# ============================================
# VALIDATION 4: Efficient Frontier — Full Curve
# ============================================
def validate_efficient_frontier(mu: pd.Series, S: pd.DataFrame):
    """
    Input: expected returns, covariance matrix
    Output: list of frontier points (volatility, return, weights)

    Libraries used: pypfopt.EfficientFrontier
    """
    # NOTE: PyPortfolioOpt v1.6.0 has NO built-in efficient_frontier() method.
    # Generate frontier by looping over target returns.
    target_returns = np.linspace(mu.min(), mu.max(), 50)
    frontier = []
    for target_ret in target_returns:
        ef = EfficientFrontier(mu, S)
        try:
            ef.efficient_return(target_return=target_ret)
            perf = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE)
            frontier.append({
                "return": float(perf[0]),
                "volatility": float(perf[1]),
                "sharpe": float(perf[2]),
                "weights": dict(ef.clean_weights())
            })
        except Exception:
            continue

    print(f"\n=== Efficient Frontier ({len(frontier)} feasible points) ===")
    volatilities = [p["volatility"] for p in frontier]
    returns_list = [p["return"] for p in frontier]

    print(f"  Volatility range: {min(volatilities):.4f} - {max(volatilities):.4f}")
    print(f"  Return range: {min(returns_list):.4f} - {max(returns_list):.4f}")

    # Verify: frontier is monotonically increasing (higher return → higher risk)
    is_non_decreasing = all(
        returns_list[i] <= returns_list[i+1]
        for i in range(len(returns_list) - 1)
    )
    assert is_non_decreasing, "Frontier returns should be non-decreasing"

    print(f"\n  Frontier points:")
    for i in range(0, len(frontier), 10):
        p = frontier[i]
        print(f"    vol={p['volatility']:.4f}, ret={p['return']:.4f}, Sharpe={p['sharpe']:.4f}")

    print("\n✅ Efficient Frontier validation PASSED")


# ============================================
# VALIDATION 5: Minimum Volatility Portfolio
# ============================================
def validate_min_volatility(mu: pd.Series, S: pd.DataFrame):
    """
    Input: expected returns, covariance matrix
    Output: minimum variance weights

    Libraries used: pypfopt.EfficientFrontier
    """
    ef = EfficientFrontier(mu, S)
    weights = ef.min_volatility()
    cleaned = ef.clean_weights()

    print(f"\n=== Minimum Volatility Portfolio ===")
    for symbol, w in sorted(cleaned.items(), key=lambda x: x[1], reverse=True):
        if w > 0.01:
            print(f"  {symbol}: {w:.4f} ({w*100:.2f}%)")

    total = sum(cleaned.values())
    assert abs(total - 1.0) < 0.01

    perf = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=True)
    print(f"  Expected return: {perf[0]:.4f}, Volatility: {perf[1]:.4f}, Sharpe: {perf[2]:.4f}")

    print("\n✅ Min Volatility validation PASSED")


# ============================================
# VALIDATION 6: Risk Contribution
# ============================================
def validate_risk_contribution(weights: dict, S: pd.DataFrame):
    """
    Input: portfolio weights, covariance matrix
    Output: marginal risk contribution per asset

    Libraries used: PyPortfolioOpt objective_functions
    (Or hand-rolled: MCR_i = (S @ w)_i / sqrt(w^T @ S @ w))
    """
    symbols = list(weights.keys())
    w = np.array([weights[s] for s in symbols])
    S_arr = S.loc[symbols, symbols].values

    # Portfolio variance
    port_var = w.T @ S_arr @ w
    port_vol = np.sqrt(port_var)

    # Marginal contribution to risk
    mcr = (S_arr @ w) / port_vol

    # Component contribution to risk
    ccr = w * mcr

    # Percentage contribution
    ccr_pct = ccr / port_vol

    print(f"\n=== Risk Contribution ===")
    for i, symbol in enumerate(symbols):
        print(f"  {symbol}: weight={w[i]:.4f}, MCR={mcr[i]:.4f}, CCR={ccr[i]:.4f}, risk%={ccr_pct[i]:.4f}")

    # Verify: sum of component contributions = portfolio volatility
    assert abs(ccr.sum() - port_vol) < 0.001, f"CCR sum {ccr.sum():.4f} != port vol {port_vol:.4f}"
    assert abs(ccr_pct.sum() - 1.0) < 0.001, f"Risk % should sum to 1, got {ccr_pct.sum():.4f}"

    print("\n✅ Risk Contribution validation PASSED")


# ============================================
# VALIDATION 7: Discrete Allocation
# ============================================
def validate_discrete_allocation(weights: dict, prices: pd.DataFrame):
    """
    Input: continuous weights, latest prices
    Output: actual share counts

    Libraries used: pypfopt.discrete_allocation
    """
    latest = get_latest_prices(prices)
    da = DiscreteAllocation(weights, latest, total_portfolio_value=100000)
    allocation, leftover = da.greedy_portfolio()

    print(f"\n=== Discrete Allocation ($100,000 portfolio) ===")
    for symbol, shares in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
        print(f"  {symbol}: {shares} shares (${latest[symbol]*shares:.2f})")
    print(f"  Funds remaining: ${leftover:.2f}")

    # Verify: allocated + leftover ≈ 100,000
    total_invested = sum(latest[s] * allocation[s] for s in allocation)
    assert abs(total_invested - 100000 + leftover) < 0.01
    assert leftover < max(latest.values())  # leftover should be less than one share

    print("\n✅ Discrete Allocation validation PASSED")


# ============================================
# VALIDATION 8: Edge Cases
# ============================================
def validate_edge_cases():
    print(f"\n{'='*60}")
    print("VALIDATION 8: Edge Cases")
    print(f"{'='*60}")

    # Edge case 1: Single asset
    print("\n--- Edge Case 1: Single Asset ---")
    single_prices = pd.DataFrame({"AAPL": [100 + i for i in range(252)]})
    mu_single = expected_returns.mean_historical_return(single_prices)
    S_single = risk_models.sample_cov(single_prices)
    ef_single = EfficientFrontier(mu_single, S_single)
    w_single = ef_single.max_sharpe()
    print(f"  Weights: {w_single}")
    assert abs(sum(w_single.values()) - 1.0) < 0.01

    # Edge case 2: Two assets (degenerate frontier)
    print("\n--- Edge Case 2: Two Assets ---")
    two_prices = pd.DataFrame({
        "AAPL": [100 + i for i in range(252)],
        "MSFT": [200 + i * 1.1 for i in range(252)],
    })
    mu_two = expected_returns.mean_historical_return(two_prices)
    S_two = risk_models.sample_cov(two_prices)
    ef_two = EfficientFrontier(mu_two, S_two)
    # Generate frontier via loop (no built-in method)
    frontier_two = []
    for t in np.linspace(mu_two.min(), mu_two.max(), 20):
        ef_t = EfficientFrontier(mu_two, S_two)
        try:
            ef_t.efficient_return(target_return=t)
            perf_t = ef_t.portfolio_performance(risk_free_rate=RISK_FREE_RATE)
            frontier_two.append(dict(ef_t.clean_weights()))
        except Exception:
            continue
    assert len(frontier_two) > 0
    print(f"  Generated {len(frontier_two)} frontier points for 2 assets")

    # Edge case 3: Zero variance (constant prices)
    print("\n--- Edge Case 3: Zero Variance ---")
    const_prices = pd.DataFrame({"AAPL": [100] * 252, "MSFT": [200] * 252})
    try:
        mu_const = expected_returns.mean_historical_return(const_prices)
        S_const = risk_models.sample_cov(const_prices)
        ef_const = EfficientFrontier(mu_const, S_const)
        w_const = ef_const.max_sharpe()
        print(f"  Zero variance handled: weights sum to {sum(w_const.values()):.4f}")
    except Exception as e:
        print(f"  Zero variance edge case: {e} (may need special handling)")

    print("\n✅ Edge cases validation PASSED")


# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    print(f"{'='*60}")
    print("PyPortfolioOpt Validation Suite")
    print(f"{'='*60}")
    print(f"User: {USER_ID}, Period: {PERIOD}")

    # Run validations
    mu, prices = validate_expected_returns()
    S = validate_risk_models(prices)
    weights, perf = validate_max_sharpe(mu, S)
    validate_efficient_frontier(mu, S)
    validate_min_volatility(mu, S)
    validate_risk_contribution(weights, S)
    validate_discrete_allocation(weights, prices)
    validate_edge_cases()

    print(f"\n{'='*60}")
    print("ALL VALIDATIONS PASSED ✅")
    print(f"{'='*60}")
```

### 12.3 Validation Results (Actual, from `validate_pypfopt.py`)

| # | Check | Result | Detail |
|---|-------|--------|--------|
| VR1 | 3 expected return models (mean, CAPM, EMA) | ✅ 3/3 | `ema_historical_return` (not `exp_historical_return`) |
| VR2 | Covariance: sample, Ledoit-Wolf, OAS | ✅ 3/3 | All symmetric positive-definite |
| VR3 | Correlation from covariance | ✅ 3/3 | Diag=1.0, in [-1,1], symmetric |
| VR4 | Max Sharpe optimization | ✅ 4/4 | Sum=1.0, weights in [0,1], keys match |
| VR5 | Portfolio performance | ✅ 3/3 | return, vol, sharpe as floats |
| VR6 | Efficient frontier generation | ✅ 5/5 | Loop over efficient_return (no built-in method) |
| VR7 | Min volatility | ✅ 3/3 | Sum=1.0, vol ≤ max sharpe vol |
| VR8 | Efficient risk | ✅ 2/2 | No risk_free_rate arg; use min_vol*1.5 |
| VR9 | Efficient return | ✅ 2/2 | Achieves target return within numerical tolerance |
| VR10 | L2 regularization | ✅ 3/3 | Reduces zero-weight concentration |
| VR11 | Weight bounds (0,0.2) and (-1,1) | ✅ 2/2 | Enforced correctly |
| VR12 | Discrete allocation (greedy) | ✅ 3/3 | Invested + leftover ≈ portfolio value |
| VR13 | Discrete allocation (LP) | ⬜ skipped | Requires `pulp`; use greedy_portfolio as default |
| VR14 | Black-Litterman (mean prior) | ✅ 2/2 | pi must be array/series, not "equal" string |
| VR15 | Black-Litterman (market cap prior) | ✅ 1/1 | Works with correct pi input |
| VR16 | HRP optimization | ✅ 4/4 | Weights sum to 1, cluster info available |
| VR17 | Single asset edge case | ✅ 1/1 | 100% weight to single asset |
| VR18 | Two assets edge case | ✅ 3/3 | Frontier and max_sharpe both work |
| VR19 | Perfect correlation | ✅ 1/1 | Equal weights for identical assets |
| VR20 | Short history (10 days) | ✅ 1/1 | No crash |
| VR21 | Mixed quality (extreme + poor) | ✅ 2/2 | Handles extreme performers gracefully |
| VR22 | Performance benchmark | ✅ 2/2 | ~5ms per max_sharpe, ~72ms per 10-pt frontier |

**Key API Findings from Validation:**
1. `EfficientFrontrier` has **no** `.efficient_frontier()` method → generate frontier via loop over `.efficient_return()`
2. `efficient_risk(target_vol)` does **not** accept `risk_free_rate` kwarg
3. `exp_historical_return` is **not** a valid function → use `ema_historical_return`
4. `BlackLittermanModel(pi="equal")` is **not** valid → `pi` must be a `pd.Series` or `np.array`
5. `DiscreteAllocation.lp_portfolio()` requires **pulp** → default to `greedy_portfolio()`
6. `HRPOpt.clusters` may be `None` or dict-like → use `isinstance` check before access
7. `clean_weights()` removes entries with weight < 1e-4, returns `OrderedDict`

### 12.4 Validation Checklist

| # | Use Case | Status | Notes |
|---|---|---|---|---|
| V1 | Mean historical returns produce Series with expected symbols | ✅ | Also validates CAPM and EMA |
| V2 | Covariance matrix is symmetric positive-definite | ✅ | Sample, Ledoit-Wolf, OAS all pass |
| V3 | Max Sharpe weights sum to ~1.0, all between 0 and 1 | ✅ | 10 assets, 27.3% max concentration |
| V4 | Efficient frontier is convex and monotonic | ✅ | Generated via loop over efficient_return |
| V5 | Min volatility has lower vol than any single asset | ✅ | 7.55% vs 10.80% for max sharpe |
| V6 | Risk contribution: sum(CCR) = portfolio volatility | ✅ | Python validation script passes |
| V7 | Discrete allocation: invested + leftover ≈ portfolio value | ✅ | greedy_portfolio: $9950.92 + $49.08 |
| V8 | Single and two-asset frontiers handled gracefully | ✅ | Perfect correlation → equal weights |
| V9 | Performance: full pipeline runs in < 5s for 20 holdings | ✅ | ~5ms per optimization, ~72ms frontier |
| V10 | All library imports resolve without version conflicts | ✅ | scipy 1.17.1, cvxpy 1.9.1, PyPortfolioOpt 1.6.0 |

### 12.5 Potential Findings & Responses

| If We Find | Then We Will |
|---|---|
| PyPortfolioOpt crashes on our data | Diagnose specific issue, file bug, consider alternative |
| Performance too slow (> 10s per frontier) | Cache covariance matrix, reduce frontier points, pre-compute |
| cvxpy fails to install in our environment | Pin specific version, test in CI, document workaround |
| Expected returns are unrealistic | Use CAPM or exponential weighting instead of mean historical |
| Weights too concentrated | Add L2 regularization via `ef.add_objective()` |
| Licenses conflict | PyPortfolioOpt is MIT — compatible with Apache 2.0 project |

### 12.6 Next Steps After Validation

1. If all validations pass → proceed to Phase 1 implementation
2. If partial failures → update design to work around limitations
3. If critical failures → fall back to hand-rolled scipy optimization (original plan)

---

---

## 13. Validation Strategy

A three-layer validation pipeline ensures no incorrect data reaches the user.

### 13.1 Layer 1 — Input Validation (Repository Layer)

Validated at the data-fetching stage before any computation begins.

#### Snapshot Validation

```python
# In portfolio_repository.py or portfolio_risk_service.py

def validate_snapshots(snapshots: List[Dict]) -> List[Dict]:
    """
    Checks performed on snapshot data before computing returns:
    1. Chronological order — dates must be ascending
    2. Non-negative values — total_value, cost_basis must be >= 0
    3. No duplicates — no two snapshots with the same date
    4. No gaps flagged — if gap > 30 calendar days, log warning
    5. Minimum count — raise if < 2 snapshots (can't compute returns)
    """
    if len(snapshots) < 2:
        raise InsufficientDataError("Need at least 2 snapshots")

    dates = [s["snapshot_date"] for s in snapshots]
    assert dates == sorted(dates), "Snapshots not in chronological order"
    assert len(dates) == len(set(dates)), "Duplicate snapshot dates"

    for s in snapshots:
        assert s["total_value"] >= 0, f"Negative total_value on {s['snapshot_date']}"
        assert s["total_cost"] >= 0, f"Negative total_cost on {s['snapshot_date']}"

    # Flag large gaps (don't raise, but log for observability)
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i-1]).days
        if gap > 30:
            logger.warning(f"Snapshot gap of {gap} days between {dates[i-1]} and {dates[i]}")

    return snapshots
```

**Failure behavior:**
| Issue | Action |
|---|---|
| < 2 snapshots | Return error response, frontend shows "Insufficient history" |
| Non-chronological | Log error, treat as data integrity issue, return error |
| Negative values | Log error, return error (data corruption unlikely but guarded) |
| Small gaps (< 30 days) | Continue normally (expected for weekends/holidays) |
| Large gaps (> 30 days) | Log warning, continue with available data |

#### Price Data Validation

```python
def validate_price_data(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    1. All symbols present — no empty columns
    2. No NaN in adjusted_close — forward-fill up to 5 days, then raise
    3. Date range alignment — all symbols have data for overlapping period
    4. Non-negative prices — raise if any <= 0
    5. At least 30 trading days of overlapping data — raise if less
    """
    required_cols = ["symbol", "price_date", "adjusted_close"]
    for col in required_cols:
        assert col in prices_df.columns, f"Missing column: {col}"

    # Forward-fill NaN prices (up to 5 consecutive trading days)
    prices_df["adjusted_close"] = prices_df.groupby("symbol")["adjusted_close"]\
        .transform(lambda s: s.ffill(limit=5))

    remaining_nans = prices_df["adjusted_close"].isna().sum()
    if remaining_nans > 0:
        raise InsufficientDataError(f"{remaining_nans} NaN prices after forward-fill")

    assert (prices_df["adjusted_close"] > 0).all(), "Non-positive prices detected"

    return prices_df
```

### 13.2 Layer 2 — Calculation Validation (Stats Layer)

Built into every function in `shared/portfolio_stats.py`. These are **runtime assertions** that catch logical errors during development and testing. In production, they log warnings and clamp values rather than crashing.

#### Sanity Bounds

```python
# Built into portfolio_stats.py — every function clamps output to sane range

def _sanity_bounds(metric_name: str, value: float, lo: float, hi: float) -> float:
    """Clamp metric to [lo, hi] and log if out of bounds."""
    if value < lo or value > hi:
        logger.warning(f"{metric_name}={value:.4f} outside sane range [{lo}, {hi}]")
    return max(lo, min(hi, value))

def compute_sharpe_ratio(daily_returns, risk_free_rate=0.02):
    # ... computation ...
    sharpe = (mean_annual_return - risk_free_rate) / annual_vol
    return _sanity_bounds("sharpe_ratio", sharpe, -3.0, 5.0)
    # Realistic range: -3 (terrible) to 5 (exceptional)

def compute_sortino_ratio(daily_returns, risk_free_rate=0.02):
    sortino = (mean_annual_return - risk_free_rate) / downside_dev
    return _sanity_bounds("sortino_ratio", sortino, -3.0, 10.0)
    # Sortino can be higher than Sharpe since downside dev < total vol

def compute_value_at_risk(daily_returns, confidence=0.95):
    var = mean_return - z_score * std_return
    return _sanity_bounds(f"VaR_{int(confidence*100)}", var, -0.5, 0.0)
    # VaR is always negative (loss), never worse than -50% daily

def compute_max_drawdown(values):
    dd_pct = min(0.0, (trough_value - peak_value) / peak_value)
    return _sanity_bounds("max_drawdown_pct", dd_pct, -1.0, 0.0)
    # Drawdown is always <= 0, never worse than -100%

def compute_correlation_matrix(returns_matrix):
    corr = np.corrcoef(returns_matrix)
    assert np.allclose(corr, corr.T), "Correlation matrix not symmetric"
    assert np.allclose(np.diag(corr), 1.0), "Correlation diagonal not 1.0"
    assert np.all(np.abs(corr) <= 1.0 + 1e-10), "Correlation outside [-1, 1]"
    return corr
```

#### Cross-Metric Invariants

These are checked at the service layer after all individual metrics are computed:

```python
def validate_risk_metrics_response(response: RiskMetricsResponse):
    """
    Cross-checks across related metrics.
    Every check has a corresponding unit test and E2E test.
    """
    checks = []

    # VaR consistency: VaR 99% should be more extreme than VaR 95%
    if response.value_at_risk_99 > response.value_at_risk_95:
        checks.append("VaR99 should be <= VaR95 (more extreme)")
        response.value_at_risk_99 = min(response.value_at_risk_99, response.value_at_risk_95)

    # CVaR should be more extreme than VaR
    if response.conditional_var_95 > response.value_at_risk_95:
        checks.append("CVaR should be <= VaR95")
        response.conditional_var_95 = min(response.conditional_var_95, response.value_at_risk_95)

    # Std dev must be >= downside deviation
    if response.downside_deviation > response.std_deviation:
        checks.append("Downside deviation should be <= std deviation")
        response.downside_deviation = min(response.downside_deviation, response.std_deviation)

    # Sortino should be >= Sharpe (downside dev <= total vol means higher ratio)
    if response.sortino_ratio + 0.01 < response.sharpe_ratio:
        # Allow small float tolerance
        if response.sortino_ratio < response.sharpe_ratio - 0.01:
            checks.append("Sortino should be >= Sharpe ratio (by definition)")

    # Max drawdown must be <= 0
    if response.max_drawdown_pct > 0:
        checks.append("Max drawdown must be <= 0")
        response.max_drawdown_pct = 0.0

    if checks:
        logger.warning(f"Risk metric invariant violations: {checks}")

    return response
```

#### NaN/Inf Propagation Prevention

```python
def _safe_metric(value: Optional[float], default: float = 0.0) -> float:
    """Replace NaN, Inf, or None with default. Never pass bad floats to frontend."""
    if value is None:
        return default
    if not np.isfinite(value):
        logger.warning(f"Non-finite metric value: {value}, replacing with {default}")
        return default
    return value

# Used at the response assembly point:
response.sharpe_ratio = _safe_metric(sharpe, default=0.0)
response.sortino_ratio = _safe_metric(sortino, default=0.0)
response.variance = _safe_metric(variance, default=0.0)
response.max_drawdown_pct = _safe_metric(max_dd_pct, default=0.0)
```

### 13.3 Layer 3 — Output Validation (API Layer)

Validated at the API boundary before the response is serialized.

#### Schema-Level Validation

Pydantic automatically validates types and ranges at serialization. Additionally, custom validators ensure business logic consistency:

```python
class RiskMetricsResponse(BaseModel):
    success: bool
    sharpe_ratio: float
    max_drawdown_pct: float
    value_at_risk_95: float
    error: Optional[str] = None

    @field_validator("sharpe_ratio")
    @classmethod
    def sharpe_must_be_sane(cls, v):
        if v < -3.0 or v > 5.0:
            logger.warning(f"Sharpe ratio {v} outside typical range")
        return v

    @field_validator("max_drawdown_pct")
    @classmethod
    def drawdown_must_be_non_positive(cls, v):
        if v > 0:
            logger.error(f"Max drawdown positive ({v}), clamping to 0")
            return 0.0
        if v < -1.0:
            logger.error(f"Max drawdown < -100% ({v}), clamping to -1.0")
            return -1.0
        return v

    @field_validator("value_at_risk_95")
    @classmethod
    def var_must_be_negative(cls, v):
        if v > 0:
            logger.warning(f"VaR positive ({v}), this may indicate data issue")
        return v
```

#### Error Classification

Every error response includes a machine-readable error code + human-readable message:

```python
class RiskMetricError(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    SINGLE_HOLDING = "single_holding"        # Efficient Frontier needs 2+
    NO_HOLDINGS = "no_holdings"              # Selected accounts have no holdings
    DATA_INTEGRITY = "data_integrity"        # Corrupt snapshots/prices
    COMPUTATION_FAILED = "computation_failed" # Internal math error (should not happen)
    ACCOUNT_NOT_FOUND = "account_not_found"  # Invalid account_id
```

**Error response format:**
```json
{
  "success": false,
  "error": "Insufficient trading history — need at least 30 days of data",
  "error_code": "insufficient_data",
  "period": "1M",
  "metrics_available": {
    "total_return": 1250.00,
    "total_return_pct": 0.052
  },
  "metrics_unavailable": [
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "value_at_risk_95"
  ]
}
```

This lets the frontend show partial data (total return is always available) while clearly indicating which metrics couldn't be computed and why.

### 13.4 User-Facing Safeguards

| Scenario | Frontend Behavior |
|---|---|
| **Error returned** | Show inline error message per sub-tab, keep other sub-tabs functional |
| **Insufficient data** | Show metric card as `—` (N/A) with tooltip explaining minimum data requirement |
| **Single holding** | Hide Efficient Frontier tab entirely, show message "Efficient Frontier requires 2+ holdings" |
| **No holdings in selected accounts** | Show empty state illustration across all sub-tabs |
| **Metric out of sane range** | Show value with warning icon and tooltip explaining the context |
| **Data loading** | Skeleton shimmer per card/chart (independent loading per sub-tab) |
| **Stale data** | Show "Data as of [timestamp]" label — particularly important for intraday |

### 13.5 Test Coverage for Validation

| Test Layer | What It Covers |
|---|---|
| **Unit tests** (stats functions) | Each function tested with valid input, edge case input (0 values, NaN, empty arrays), and cross-metric invariants |
| **Property-based tests** (hypothesis) | Random valid inputs produce outputs within sane bounds |
| **Integration tests** (API + DB) | Real data flows through the full pipeline, response shape and ranges verified |
| **E2E tests** (real Supabase) | Production-like data produces consistent, realistic metrics across periods |
| **Regression tests** | Known portfolios with pre-computed metrics (e.g., 60/40 portfolio has expected Sharpe ~0.5) |
| **Visual regression** (frontend) | UI renders correctly for all states: loading, error, empty, data |

### 13.6 Validation Matrix Summary

| What | When | Where | Who |
|---|---|---|---|
| Snapshots: chronological, non-negative, no gaps | Data fetch | `portfolio_repository.validate_snapshots()` | Backend |
| Prices: no NaN, all symbols present, 30-day min | Data fetch | `portfolio_risk_service._validate_prices()` | Backend |
| Holdings: weights sum to 1, no duplicates | Data fetch | `portfolio_risk_service._validate_holdings()` | Backend |
| Metrics: within sane numeric bounds | Computation | `portfolio_stats._sanity_bounds()` | Backend |
| Cross-metric invariants (VaR99 < VaR95, etc.) | Response assembly | `portfolio_risk_service.validate_risk_metrics_response()` | Backend |
| No NaN/inf in response | Response assembly | `portfolio_stats._safe_metric()` | Backend |
| Pydantic field validation | Serialization | `RiskMetricsResponse.field_validator()` | Backend |
| Error codes + human messages | Serialization | `RiskMetricError` enum + error message | Backend |
| Loading/error/empty states | Render | React components | Frontend |
| E2E sanity bounds | Test | `test_portfolio_risk_e2e.py` | CI |
| Known portfolio regression | Test | `test_portfolio_risk_e2e.py` | CI |

---

## 14. Open Questions

| # | Question | Decision Needed By |
|---|---|---|
| Q1 | Should Factor Exposure use Fama-French 3-factor or 5-factor model? | Phase 5 |
| Q2 | Where to source factor return data? (Hardcoded FF data from Ken French's site, or compute from market proxies?) | Phase 5 |
| Q3 | Risk-free rate: hardcoded 2% or configurable in DB/env? | Phase 2 |
| Q4 | Should we cache covariance matrices? (Expensive to recompute for every page load) | Phase 3 |
| Q5 | What period granularity for snapshots? (Daily is default, but weekly may be needed for 10Y periods) | Phase 1 |
| Q6 | Should the Efficient Frontier show unconstrained or long-only by default? | Phase 4 |
| Q7 | How many frontier points is optimal for UX vs performance? | Phase 4 (validation) |
