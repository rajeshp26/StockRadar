# Stock Performance Tab — Detailed Design Document

> **Version:** 1.4
> **Date:** 2026-06-07
> **Status:** Bugs fixed; proposed enhancements for completeness, correctness, and UX
> **New in v1.4:** §12 — Performance Summary Card (return attribution, best/worst month, drawdown, days above cost basis, volatility) + Tab Overflow Fix
> **Design Goals:** Professional grade, minimal complexity, maximum reuse, long-term extensibility

---

## Table of Contents

0. [Implementation Audit Findings](#0-implementation-audit-findings)
1. [Use Case Analysis](#1-use-case-analysis)
2. [Frontend Design](#2-frontend-design)
3. [Backend Design](#3-backend-design)
4. [Frontend-Backend Interaction](#4-frontend-backend-interaction)
5. [Sequence Diagrams](#5-sequence-diagrams)
6. [Performance Requirements](#6-performance-requirements)
7. [Design Principles & Professional Grade Assessment](#7-design-principles--professional-grade-assessment)
8. [Assumptions](#8-assumptions)
9. [Test Plan](#9-test-plan)
10. [Appendix: Calculation Correctness Validation](#10-appendix-calculation-correctness-validation)
11. [Proposed Enhancements — Implementation Plan](#11-proposed-enhancements--implementation-plan)
12. [Performance Summary Card + Tab Overflow Fix](#12-performance-summary-card--tab-overflow-fix)

---

## 0. Implementation Audit Findings

> **Audit Date:** 2026-06-06
> **Audit Scope:** Code-to-design verification for all Stock Performance Tab features
> **Status:** Bugs fixed, features implemented

### 0.1 Critical Bugs (All FIXED)

#### BUG-01: Gain/Loss Calculation Formula Fixed
- **File:** `backend/application/services/portfolio_service.py:1974-1977`
- **Fix:** Changed `snapshots[0]["cost_basis"]` → `snapshots[-1]["cost_basis"]` for `total_return`.
  Changed price-based return `(last_value - first_value) / first_value * 100` → cost-based return
  `(total_return / last_cost_basis * 100)`.
- **Verification:** 3 regression tests with varying cost_basis now pass with correct values.

#### BUG-02: Benchmark Comparison Fixed
- **File:** `web/src/features/analysis/components/stock-performance-panel.tsx:284-312`
- **Fix:** Added `useBenchmarkCompare(period, selectedBenchmarks)` hook call. Rewrote
  `buildPerformanceChartData()` to merge benchmark time-series data instead of setting
  `null` values. Note: uses portfolio-level benchmark comparison endpoint.
- **Verification:** Frontend tests verify benchmark compare hook is called when benchmarks
  are selected.

#### BUG-03: `YTD` Period Support Added
- **File:** `backend/api/portfolio.py:990`
- **Fix:** Added `YTD` to regex pattern: `^(1D|1W|1M|3M|1Y|5Y|YTD|ALL)$`

#### BUG-04: `total_dividends_pct` Fallback Fixed
- **File:** `backend/application/services/portfolio_service.py:1978`
- **Fix:** Removed `or 1` fallback; uses `last_cumulative_invested` directly with
  `> 0` guard.

### 0.2 Missing Features (All FIXED Except M-01, M-02)

| # | Feature | Status | Implementation |
|---|---------|--------|----------------|
| M-01 | **Per-Account Breakdown** | ⏳ Not implemented | Requires new backend endpoint to group holdings by account |
| M-02 | **Transaction History for Ticker** | ⏳ Not implemented | Requires new backend endpoint to return transactions for a symbol |
| M-03 | **Total Share Count** | ✅ FIXED | Added `shares_held` to `_compute_fifo_snapshots` → `HoldingPerformanceSnapshot` → shown in "Total Value" summary card subtitle |
| M-04 | **Purchase Amount & Price in Chart Tooltip** | ✅ FIXED | Added `avg_cost_per_share` to snapshots; custom tooltip renders shares_held and avg_cost_per_share |

### 0.3 Proposed Improvements (NEW — after user review)

| # | Improvement | Priority | Description |
|---|-------------|----------|-------------|
| P-01 | **Total Invested (Cost Basis) Summary Card** | High | Add a 5th summary card showing `cumulative_invested` from `snapshots[-1]` so users see total $ put in vs current value |
| P-02 | **Chart Start from First Purchase Date** | High | For "ALL" period, compute start date from the symbol's earliest transaction — not the portfolio's earliest. For periods before first purchase, show zero values |
| P-03 | **Holding-Level Benchmark Comparison** | High | Benchmarks must simulate the same buy/sell pattern for the specific stock, not the portfolio's cash flow deltas. Currently uses portfolio-level `_get_cashflow_deltas` |
| P-04 | **Transaction History Table** | High | Show a sortable/filterable table of all buys/sells for the symbol within the Performance tab |
| P-05 | **Per-Account Breakdown Implementation** | Medium | Table showing each account: account name, type, shares held, total cost, current value, gain/loss $, gain/loss % |
| P-06 | **Pre-Purchase Period Shows "No Data"** | Medium | When selected period starts before the first purchase, the chart should clearly indicate no position existed (flat zero line with label) |
| P-07 | **Re-label "Total Gain/Loss" Cards** | Low | Update labels to clarify: "Total Gain/Loss ($)" = Current Value − Cost Basis of Held Shares, "Total Gain/Loss (%)" = Gain/Loss $ / Cost Basis × 100 |

### 0.4 Remaining Design-Implementation Gaps

| # | Item | Document States | Actual Implementation | Impact |
|---|------|-----------------|----------------------|--------|
| D-13 | **Chart start date for "ALL" period** | Should start from holding's first purchase | Uses `_period_to_date_range(period, account_ids)` which computes from portfolio's earliest transaction, not the symbol's | Chart shows empty/irrelevant data before stock was first purchased |
| D-14 | **Benchmark compare for single stock** | Should use holding-level cash flows | Uses `get_performance_compare` which calls `get_portfolio_performance` and `_get_cashflow_deltas` — both portfolio-level | Benchmarks show comparison with portfolio cash flows, not holding-specific cash flows |
| D-15 | **`cumulative_invested` not shown** | Not mentioned as a summary card | Field exists in snapshots but only `position_value` and `cost_basis` are shown | Users cannot see total $ invested vs current value side-by-side |

### 0.5 Design Document Inaccuracies

| # | Item | Document States | Actual Implementation |
|---|------|----------------|----------------------|
| D-01 | **File naming** | `stock-performance.tsx` | `Stock-performance-panel.tsx` (case-sensitive on some filesystems) |
| D-02 | **`HoldingAccountBreakdown` type** | Defined in Section 2.3 | Does not exist in `web/src/features/portfolio/types/portfolio.types.ts` |
| D-03 | **`placeholderData` import** | Uses `keepPreviousData` named import | Uses inline `placeholderData: (previousData) => previousData` (functionally equivalent but different) |
| D-04 | **Period options** | UC-03: "1M, 3M, 1Y, YTD, ALL" | Backend regex allows `1D, 1W, 1M, 3M, 1Y, 5Y, YTD, ALL` (BUG-03 FIXED) |
| D-05 | **DividendChart as separate component** | Listed as `[NEW]` separate component | Dividend bar chart rendered inline within `StockPerformancePanel`, not as a separate component |
| D-06 | **`total_return` formula** | Section 2.3: `current_value - total_cost` | Actual formula: `last_value - snapshots[-1]["cost_basis"]` (BUG-01 FIXED) |
| D-07 | **`total_return_pct` formula** | Section 2.3: `(current_value / total_cost - 1) * 100` | Actual formula: `total_return / last_cost_basis * 100` (BUG-01 FIXED) |
| D-08 | **`get_dividends_for_symbol` signature** | Section 3.5: `(account_ids, symbol)` | Actual: `(user_id, symbol)` — resolves accounts internally |
| D-09 | **`_compute_fifo_snapshots` signature** | Section 3.2: `(txns, price_map, start_date, end_date, step)` | Actual: `(lots, in_txns_sorted, sorted_dates, price_map, cumulative_invested_map)` |
| D-10 | **Holdings check for tab visibility** | Section 2.2: `useHoldingExists(symbol) → isHeld` | Correctly implemented in `analysis/[symbol]/page.tsx:118-127` ✓ |
| D-11 | **BenchmarkSelector** | Listed as reused component | Correctly reused from `@/components/ui/benchmark-selector` ✓ |
| D-12 | **Rate limit for exists endpoint** | Section 3.3: 60/minute | Correctly implemented at `portfolio.py:965` ✓ |
| D-13 | **Chart start date for "ALL"** | Should start from holding's first purchase | Uses portfolio-wide earliest transaction, not symbol-specific |
| D-14 | **Benchmark compare is portfolio-level** | Should be holding-level for single stock | Uses `get_performance_compare` with portfolio cash flows |
| D-15 | **`cumulative_invested` hidden** | Not a visible summary card | Field exists in snapshots but not surfaced in UI |

---

## 1. Use Case Analysis

---

## 1. Use Case Analysis

### 1.1 Primary Actors

| Actor | Description |
|-------|-------------|
| **Portfolio Investor** | User who holds stocks in their portfolio and wants to analyze individual positions |
| **Fundamental Analyst** | User using existing analysis tools (valuation, moat, dividend) who also wants portfolio-contextualized performance |

### 1.2 Use Cases

```
UC-01: Navigate from Portfolio to Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      Portfolio Investor
Precondition: User is on /portfolio page, viewing Holdings tab
Trigger:    User clicks on a holding row
Flow:
  1. System highlights row on hover (cursor pointer)
  2. User clicks holding row
  3. System navigates to /analysis/{symbol}
  4. Analysis page loads with all existing tabs + "Performance" tab visible
Postcondition: User sees analysis page with performance data for held stock


UC-02: View Stock Performance Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      Portfolio Investor
Precondition: User is on /analysis/{symbol}, "Performance" tab is visible
Trigger:    User clicks "Performance" tab
Flow:
  1. System shows four summary cards:
     - Total Value (current position value)
     - Total Gain/Loss ($)
     - Gain/Loss (%)
     - Total Dividends Received
  2. System shows per-account breakdown if stock is held across multiple accounts
Postcondition: User sees aggregated performance snapshot of their position


UC-03: View Stock Performance Chart
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      Portfolio Investor
Precondition: Performance tab is active
Trigger:    Tab renders (no explicit action)
Flow:
  1. System fetches time-series performance data (position value, cost basis)
  2. System renders a ComposedChart with:
     - Area: Position Value over time
     - Line: Cost Basis (dashed, green)
     - Lines: Selected benchmarks (dashed, per BENCHMARK_COLORS)
  3. User can toggle benchmarks via BenchmarkSelector
  4. User can change period via TimePeriodSelector (1M, 3M, 1Y, YTD, ALL)
Postcondition: Chart updates reactively on period/benchmark changes


UC-04: View Dividend History Bar Chart
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      Portfolio Investor
Precondition: Performance tab is active, stock pays dividends
Trigger:    Dividend data loads
Flow:
  1. System fetches dividend history (aggregated from portfolio_dividends)
  2. System renders a BarChart grouped by fiscal quarter/year
  3. Each bar shows total dividends received in that period
  4. Tooltip shows amount, per-share amount, date range
  5. User can scroll/zoom through available time range
Postcondition: User sees historical dividend payments for their holdings


UC-05: Detect Portfolio Context (Source Agnostic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      System (automatic)
Precondition: Analysis page mounts for any symbol
Trigger:    Page loads (regardless of whether user clicked from watchlist, portfolio, or direct URL)
Flow:
  1. System calls GET /portfolio/holdings/{symbol}/exists
  2. If held=true, "Performance" tab appears in TOP_TABS
  3. If held=false, tab is hidden (no change from current behavior)
Postcondition: Tab visibility is determined solely by whether the user holds the stock, NOT by navigation source. Zero data is fetched for non-held stocks.


UC-06: Navigate Back to Portfolio from Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      Portfolio Investor
Precondition: User arrived from portfolio page (via ?from=portfolio query param)
Trigger:    User clicks browser back or "Back to Portfolio" link
Flow:
  1. System reads ?from=portfolio from URL
  2. Optional: Shows "Back to Portfolio" breadcrumb with account context
  3. router.back() returns to /portfolio?tab=holdings
Postcondition: User returns to portfolio page at the Holdings tab


UC-07: Access from Watchlist — Show Performance Tab for Held Stocks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Actor:      Portfolio Investor
Precondition: User is on /dashboard (watchlist). Stock is visible in their watchlist AND also held in their portfolio.
Trigger:    User clicks a stock card/grid item in the watchlist
Flow:
  1. System navigates to /analysis/{symbol} (exact same route as UC-01, no source tracking needed)
  2. UC-05 fires automatically on page load
  3. If held=true, "Performance" tab appears in TOP_TABS
  4. All performance data, charts, and dividend history load from the same portfolio-context endpoints
Postcondition: User sees the same "Performance" tab with identical data, regardless of which dashboard they clicked from

Key design rationale:
  - The exists check (UC-05) is source-agnostic — it simply queries "does the current user hold this stock?"
  - No ?source=watchlist, no referrer sniffing, no conditional rendering by origin
  - A user who holds AAPL in their portfolio and watches it on their dashboard gets the same experience
    whether they clicked from the Portfolio holdings page or from the Watchlist dashboard
  - A user who watches a stock but does NOT hold it will never see the Performance tab (correct behavior)
```

### 1.3 Use Case Diagram (textual)

```
                    ┌─────────────────────────────────────────────┐
                    │              Portfolio Investor              │
                    └──────┬──────────┬──────────────┬─────────────┘
                           │          │              │
             ┌─────────────┘          │              └─────────────┐
             ▼                        │                          ▼
     ┌──────────────┐                 │                  ┌──────────────┐
     │ /dashboard    │                 │                  │ /portfolio    │
     │ (Watchlist)   │                 │                  │ (Holdings)    │
     └──────┬───────┘                 │                  └──────┬───────┘
            │ click stock             │                         │ click stock
            ▼                         │                         ▼
     ┌──────────────┐                 │                  ┌──────────────┐
     │ UC-07        │                 │                  │ UC-01        │
     │ Watchlist →  │                 │                  │ Portfolio →  │
     │ Analysis     │                 │                  │ Analysis     │
     └──────┬───────┘                 │                  └──────┬───────┘
            │                         │                         │
            └──────────┬──────────────┘─────────────────────────┘
                       ▼
              ┌──────────────────┐
              │ UC-05            │
              │ Auto-detect      │
              │ Portfolio Context│
              │ (source agnostic)│
              └──────┬───────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   ┌──────────────┐    ┌──────────────────┐
   │ UC-02        │    │ UC-04            │
   │ View Perf.   │    │ View Dividend    │
   │ Summary/Chart│    │ History Chart    │
   └──────────────┘    └──────────────────┘
          │
          ▼
   ┌──────────────┐
   │ UC-03        │
   │ Chart Period │
   │ & Benchmark  │
   └──────────────┘
```

---

## 2. Frontend Design

### 2.1 Module Scope

| Module | Directory | Responsibility |
|--------|-----------|----------------|
| **portfolio/components** | `web/src/features/portfolio/components/` | HoldingsTab, SegmentDrillDown row click handlers |
| **analysis/components** | `web/src/features/analysis/components/` | StockPerformancePanel (summary + charts) |
| **analysis/page** | `web/src/app/(authenticated)/analysis/[symbol]/` | Conditional tab rendering logic |
| **portfolio/hooks** | `web/src/features/portfolio/hooks/` | useHoldingExists, useHoldingPerformance (new hooks) |
| **portfolio/services** | `web/src/features/portfolio/services/` | checkHoldingExists, getHoldingPerformance (new methods) |
| **portfolio/types** | `web/src/features/portfolio/types/` | HoldingPerformanceResponse, HoldingExistsResponse (new types) |
| **lib** | `web/src/lib/` | New query keys in query-keys.ts |
| **ui** | `web/src/components/ui/` | BenchmarkSelector (reused, no changes) |

> **Note (D-01):** Actual file is `Stock-performance-panel.tsx` (pascal-case), not `stock-performance.tsx` as originally specified.

### 2.2 Component Tree (New & Modified)

```
┌─────────────────────────────────────────────────────────────────────┐
│  AnalysisPage [modified]                                            │
│  web/src/app/(authenticated)/analysis/[symbol]/page.tsx             │
│                                                                     │
│  ├─ TOP_TABS [modified: conditionally includes "Performance"]       │
│  │    ├─ useHoldingExists(symbol) → isHeld                          │
│  │    └─ if isHeld → insert { id: "performance", ... }              │
│  │                                                                  │
│  └─ {tab === "performance" &&                                       │
│       <StockPerformancePanel symbol={upperSymbol} />                │
│      }                                                              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  StockPerformancePanel [NEW]                                  │   │
│  │  web/src/features/analysis/components/Stock-performance-panel │   │
│  │                                                               │   │
│  │  ├─ SummaryCards                                               │   │
│  │  │    useHoldingPerformance(symbol, period)                    │   │
│  │  │    ├─ Card: Total Value    ← snapshots[-1].position_value   │   │
│  │  │    ├─ Card: Gain/Loss $    ← perf.total_return             │   │
│  │  │    ├─ Card: Gain/Loss %    ← perf.total_return_pct          │   │
│  │  │    ├ Card: Total Invested ← snapshots[-1].cumulative_invested [P-01]
│  │  │    ├ Card: Gain/Loss $    ← perf.total_return
│  │  │    ├ Card: Gain/Loss %    ← perf.total_return_pct
│  │  │    └ Card: Total Dividends ← perf.total_dividends
│  │  │
│  │  ├ TransactionHistory [NEW — P-04]
│  │  │    └ Sortable table of BUY/SELL transactions
│  │  │       Columns: Date, Type, Qty, Price, Commission,
│  │  │       Net Cash, Account Name
│  │  │       Source: GET /portfolio/holdings/{symbol}/transactions
│  │  │
│  │  ├ AccountBreakdown [NEW — P-05]
│  │  │    └ Table: per-account holding details
│  │  │       Columns: Account, Type, Shares, Cost, Value, G/L $, %
│  │  │       Source: GET /portfolio/holdings/{symbol}/accounts
│  │  │
│  │  ├ PerformanceChart [NEW]
│  │  │    Adapted from PortfolioPerformanceChart
│  │  │    ├ TimePeriodSelector (reused)
│  │  │    ├ BenchmarkSelector (reused)
│  │  │    └ Recharts ComposedChart
│  │  │         ├ Area: position_value
│  │  │         ├ Line: cost_basis (dashed)
│  │  │         ├ Line: benchmarks (holding-cash-flow adjusted)
│  │  │         │   [P-03: benchmark compares using symbol's buys]
│  │  │         └ Chart start = first purchase date [P-02]

│  │  └─ DividendChart [inline, NOT separate component]              │   │
│  │       └─ Recharts BarChart                                      │   │
│  │            ├─ X: fiscal quarter                                 │   │
│  │            └─ Y: total_amount received                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 TypeScript Type/Interface Design

```typescript
// ──── TYPES (web/src/features/portfolio/types/portfolio.types.ts) ────

/** Snapshot point for a single stock's performance over time */
export interface HoldingPerformanceSnapshot {
  date: string;                          // "2024-01-15"
  position_value: number;                // quantity × close_price at date
  cost_basis: number;                    // total cost of remaining lots at date (FIFO)
  cumulative_invested: number;           // total $ put in (buys - sells) to date
  shares_held?: number;                  // total shares owned at this snapshot (M-03 FIXED)
  avg_cost_per_share?: number;           // weighted avg cost per share (M-04 FIXED)
}

/** Full response for single-stock performance */
export interface HoldingPerformanceResponse {
  success: boolean;
  symbol: string;
  period: string;
  snapshots: HoldingPerformanceSnapshot[];
  total_return: number;                  // last_value - last_cost_basis (BUG-01 FIXED)
  total_return_pct: number;              // total_return / last_cost_basis * 100 (BUG-01 FIXED)
  total_dividends: number;               // sum of dividends received in period (correct)
  total_dividends_pct: number;           // dividends / cumulative_invested × 100 (BUG-04 FIXED)
  error?: string;
}

/** Lightweight holding existence check */
export interface HoldingExistsResponse {
  symbol: string;
  held: boolean;
}

/** Per-account breakdown of a single holding — NOT IMPLEMENTED in codebase */
// export interface HoldingAccountBreakdown {
//   account_id: number;
//   account_name: string;
//   account_type: string;
//   quantity: number;
//   total_cost: number;
//   current_value: number;
//   unrealized_gain_loss: number;
//   unrealized_gain_loss_pct: number;
//   dividends_received: number;
// }

// ──── TYPES for dividend chart ──── (CORRECTLY IMPLEMENTED)

export interface HoldingDividendSummary {
  fiscal_year: number;
  fiscal_quarter: number;                // 1-4
  label: string;                         // "Q1 2024"
  total_amount: number;
  payments_count: number;
  amount_per_share: number;
}

// ──── PROPOSED NEW TYPES (for P-04, P-05) ────

/** Single transaction for a holding (used in TransactionHistory) */
export interface HoldingTransaction {
  transaction_id: number;
  transaction_date: string;              // "2024-01-15"
  activity_sub_type: string;             // "BUY" | "SELL"
  quantity: number;                      // positive for BUY, negative for SELL
  unit_price: number;
  commission: number;
  net_cash_amount: number;               // negative for BUY (money out), positive for SELL
  account_name: string;
  account_type: string;
}

/** Per-account breakdown of a single holding */
export interface HoldingAccountBreakdown {
  account_id: number;
  account_name: string;
  account_type: string;
  shares_held: number;
  total_cost: number;                    // cost basis for this account's shares
  current_value: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  dividends_received: number;
}
```

### 2.4 Hook Design

```typescript
// ──── HOOKS (web/src/features/portfolio/hooks/usePortfolio.ts) ────

/**
 * Hook: useHoldingExists
 * ──────────────────────
 * Checks if the current user holds a position in the given symbol.
 * Used by the analysis page to conditionally show the Performance tab.
 */
export function useHoldingExists(symbol: string) {
  const { portfolioService } = useServices();
  return useQuery<HoldingExistsResponse, Error>({
    queryKey: QK.holdingExists(symbol),
    queryFn: () => portfolioService.checkHoldingExists(symbol),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
  });
}

/**
 * Hook: useHoldingPerformance
 * ────────────────────────────
 * Fetches time-series performance data for a single held stock.
 * Cache strategy: staleTime = 5 min
 */
export function useHoldingPerformance(symbol: string, period: TimePeriod = "1Y") {
  const { portfolioService } = useServices();
  return useQuery<HoldingPerformanceResponse, Error>({
    queryKey: QK.holdingPerformance(symbol, period),
    queryFn: () => portfolioService.getHoldingPerformance(symbol, period),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
    placeholderData: (previousData) => previousData,  // inline fn, not keepPreviousData import
  });
}

/**
 * Hook: useHoldingDividends
 * ──────────────────────────
 * Fetches dividend history for a single held stock (quarterly aggregates).
 */
export function useHoldingDividends(symbol: string) {
  const { portfolioService } = useServices();
  return useQuery<HoldingDividendSummary[], Error>({
    queryKey: QK.holdingDividends(symbol),
    queryFn: () => portfolioService.getHoldingDividends(symbol),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
  });
}
```

> **Note (D-03):** Actual implementation uses inline `placeholderData: (previousData) => previousData`, not the named `keepPreviousData` import shown in the original design. Functionally equivalent.

### 2.5 Service Methods

```typescript
// ──── NEW SERVICE METHODS (web/src/features/portfolio/services/portfolio.service.ts) ────

class PortfolioService {
  // ...

  /** Lightweight check: does user hold symbol? */
  async checkHoldingExists(symbol: string): Promise<HoldingExistsResponse> {
    const res = await this.api.get(`/portfolio/holdings/${symbol}/exists`);
    return res.data;
  }

  /** Time-series performance for a single held stock */
  async getHoldingPerformance(
    symbol: string,
    period: string = "1Y"
  ): Promise<HoldingPerformanceResponse> {
    const res = await this.api.get(`/portfolio/holdings/${symbol}/performance`, {
      params: { period },
    });
    return res.data;
  }

  /** Dividend history for a single held stock (quarterly aggregates) */
  async getHoldingDividends(symbol: string): Promise<HoldingDividendSummary[]> {
    const res = await this.api.get(`/portfolio/holdings/${symbol}/dividends`);
    return res.data;
  }
}
```

### 2.6 Query Key Additions

```typescript
// ──── NEW QUERY KEYS (web/src/lib/query-keys.ts) ────

holdingExists: (symbol: string) =>
  ["portfolio", "holding", "exists", symbol.toUpperCase()] as const,

holdingPerformance: (symbol: string, period: string) =>
  ["portfolio", "holding", "performance", symbol.toUpperCase(), period] as const,

holdingDividends: (symbol: string) =>
  ["portfolio", "holding", "dividends", symbol.toUpperCase()] as const,
```

---

## 3. Backend Design

### 3.1 Module Scope

| Module | Directory | Responsibility |
|--------|-----------|----------------|
| **portfolio API router** | `backend/api/portfolio.py` | New routes: exists, performance, dividends |
| **portfolio service** | `backend/application/services/portfolio_service.py` | Business logic: holding check, FIFO engine for single stock |
| **portfolio schemas** | `backend/schemas_portfolio.py` | New Pydantic models |
| **portfolio repository** | `backend/infrastructure/repositories/portfolio_repository.py` | New query methods (if needed for optimization) |

### 3.2 Service Class Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PortfolioService                                                       │
│  backend/application/services/portfolio_service.py                      │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  PUBLIC METHODS                                                  │    │
│  │                                                                   │    │
│  │  check_holding_exists(user_id, symbol) → bool                    │    │
│  │    Gets all holdings, checks if symbol exists, returns boolean    │    │
│  │                                                                   │    │
│  │  get_holding_performance(user_id, symbol, period) → dict          │    │
│  │    1. Get accounts for user                                       │    │
│  │    2. Get transactions for symbol across accounts                 │    │
│  │    3. Compute FIFO snapshots (reuses shared engine)               │    │
│  │    4. Compute summary metrics — BUG: uses snapshots[0].cost_basis │    │
│  │    5. Return snapshots + summary                                  │    │
│  │                                                                   │    │
│  │  get_holding_dividends(user_id, symbol) → list[dict]              │    │
│  │    Gets all dividend records for symbol, aggregates by quarter    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  PRIVATE HELPERS (EXTRACTED)                                     │    │
│  │                                                                   │    │
│  │  _compute_fifo_snapshots(                                         │    │
│  │    lots, in_txns_sorted, sorted_dates, price_map,                 │    │
│  │    cumulative_invested_map                                        │    │
│  │  ) → list[dict]                                                   │    │
│  │    ── Shared engine: used by both portfolio-level and             │    │
│  │       single-stock performance computation                        │    │
│  │    ── Extracted from existing get_portfolio_performance()         │    │
│  │    ── Handles: lot tracking, buys/sells, FIFO ordering           │    │
│  │    ── Note: signature differs from original design                │    │
│  │       (uses pre-built lots dict and sorted_dates list)            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  DEPENDENCIES                                                     │    │
│  │                                                                   │    │
│  │  PortfolioRepository (composition)                                │    │
│  │    └─ get_user_accounts(user_id)                                  │    │
│  │    └─ get_account_transactions(account_id)                        │    │
│  │    └─ get_user_all_holdings(user_id)                              │    │
│  │    └─ get_dividends_for_symbol(user_id, symbol)                   │    │
│  │    └─ get_transactions_for_symbol(user_id, symbol)                │    │
│  │                                                                   │    │
│  │  Supabase client (direct queries for price_history)               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

> **Note (D-09):** `_compute_fifo_snapshots` signature is `(lots, in_txns_sorted, sorted_dates, price_map, cumulative_invested_map)` — not `(txns, price_map, start_date, end_date, step)` as originally designed.

### 3.3 API Route Design

```python
# ──── NEW ROUTES (backend/api/portfolio.py) ────

@router.get(
    "/portfolio/holdings/{symbol}/exists",
    tags=["Portfolio"],
    status_code=200,
    summary="Check if user holds a position in the symbol"
)
@limiter.limit("60/minute")
async def check_holding_exists(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> HoldingExistsResponse:
    """Lightweight endpoint. O(1) after holdings are cached in service."""
    ...


@router.get(
    "/portfolio/holdings/{symbol}/performance",
    tags=["Portfolio"],
    status_code=200,
    summary="Time-series performance for a single held stock"
)
@limiter.limit("20/minute")
async def get_holding_performance(
    request: Request,
    symbol: str,
    period: str = Query("1Y", regex="^(1D|1W|1M|3M|1Y|5Y|ALL)$"),
    user: dict = Depends(get_current_user_dep),
) -> HoldingPerformanceResponse:
    """
    Returns FIFO-based position value and cost basis snapshots.
    Period options: 1D, 1W, 1M, 3M, 1Y, 5Y, ALL
    ⚠ BUG: Regex excludes YTD. Frontend sends YTD → 422 validation error.
    Service layer _period_to_date_range supports YTD but route regex blocks it.
    """
    ...


@router.get(
    "/portfolio/holdings/{symbol}/dividends",
    tags=["Portfolio"],
    status_code=200,
    summary="Dividend history for a single held stock (quarterly)"
)
@limiter.limit("30/minute")
async def get_holding_dividends(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> list[dict]:
    """Returns quarterly-aggregated dividends from portfolio_dividends table."""
    ...
```

### 3.4 Pydantic Schemas

```python
# ──── NEW SCHEMAS (backend/schemas_portfolio.py) ────

class HoldingExistsResponse(BaseModel):
    symbol: str
    held: bool


class HoldingPerformanceSnapshot(BaseModel):
    date: str
    position_value: float
    cost_basis: float
    cumulative_invested: float


class HoldingPerformanceResponse(BaseModel):
    success: bool = True
    symbol: str
    period: str
    snapshots: List[HoldingPerformanceSnapshot] = []
    total_return: float = 0       # ⚠ BUG: see §0.1 BUG-01
    total_return_pct: float = 0   # ⚠ BUG: see §0.1 BUG-01
    total_dividends: float = 0
    total_dividends_pct: float = 0
    error: Optional[str] = None


class HoldingDividendSummary(BaseModel):
    fiscal_year: int
    fiscal_quarter: int
    label: str
    total_amount: float
    payments_count: int
    amount_per_share: float
```

### 3.5 Repository Additions

```python
# ──── NEW/OPTIMIZED METHODS (backend/infrastructure/repositories/portfolio_repository.py) ────

class PortfolioRepository:
    # Existing methods (unchanged):
    #   get_user_accounts(user_id)
    #   get_account_transactions(account_id, activity_types=None)
    #   get_user_all_holdings(user_id)
    #   get_account_dividends_by_year(account_id, fiscal_year)

    def get_dividends_for_symbol(
        self, user_id: int, symbol: str      # NOTE: signature is (user_id, symbol), not (account_ids, symbol) as originally designed
    ) -> List[Dict[str, Any]]:
        """Get ALL dividend payments for a symbol across user's accounts."""
        accounts = self.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
        if not account_ids:
            return []
        try:
            res = (
                self.client.table("portfolio_dividends")
                .select("*")
                .in_("account_id", account_ids)
                .eq("symbol", symbol.upper())
                .order("payment_date", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get dividends for {symbol}: {e}")
            return []

    def get_transactions_for_symbol(
        self, user_id: int, symbol: str
    ) -> List[Dict[str, Any]]:
        """Get all Trade transactions for a symbol across user's accounts."""
        accounts = self.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
        if not account_ids:
            return []
        try:
            res = (
                self.client.table("portfolio_transactions")
                .select("*")
                .in_("account_id", account_ids)
                .eq("symbol", symbol.upper())
                .in_("activity_type", ["Trade"])
                .order("transaction_date", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get transactions for {symbol}: {e}")
            return []
```

---

## 4. Frontend-Backend Interaction

### 4.1 Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                                    │
│                                                                             │
│  Analysis Page                      StockPerformancePanel                   │
│  ┌──────────────┐                  ┌──────────────────────────────┐        │
│  │ useHolding   │ ◄── isHeld ──   │ SummaryCards                  │        │
│  │ Exists(sym)  │                  │  └─ useHoldingPerformance()  │        │
│  └──────┬───────┘                  │  └─ useHoldingDividends()    │        │
│         │                          │                                │        │
│         │ holds?                   │ PerformanceChart              │        │
│         ▼                          │  └─ useHoldingPerformance()   │        │
│  Show/Hide Tab                     │                                │        │
│                                    │ DividendChart                  │        │
│                                    │  └─ useHoldingDividends()     │        │
│                                    └──────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
         │                          │
         │ HTTP /api/proxy/*        │ HTTP /api/proxy/*
         ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  NEXT.JS API PROXY                                                          │
│  web/src/app/api/proxy/[...path]/route.ts                                   │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │  Rewrites /api/proxy/portfolio/* → http://localhost:8001/portfolio/*   │
│  └──────────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND (port 8001)                                                │
│                                                                             │
│  /portfolio/holdings/{symbol}/exists                                        │
│  ┌──────────────────────────────────────────────┐                          │
│  │  1. Resolve auth_id → user_id                │                          │
│  │  2. PortfolioService.check_holding_exists()  │                          │
│  │  3. PortfolioRepository.get_user_all_holdings│                          │
│  │  4. Check symbol in holdings list            │                          │
│  │  5. Return { symbol, held: bool }            │                          │
│  └──────────────────────────────────────────────┘                          │
│                                                                             │
│  /portfolio/holdings/{symbol}/performance                                   │
│  ┌──────────────────────────────────────────────┐                          │
│  │  1. Resolve auth_id → user_id                │                          │
│  │  2. Parse period → date range                │                          │
│  │     ⚠ Period regex blocks YTD (BUG-03)       │                          │
│  │  3. Get transactions for symbol+accounts     │                          │
│  │  4. Get price_history for symbol             │                          │
│  │  5. Run _compute_fifo_snapshots()            │                          │
│  │  6. Compute total_return, total_dividends    │                          │
│  │     ⚠ total_return = last_value - snapshots[0].cost_basis  (BUG-01)    │
│  │     ⚠ Should be: snapshots[-1].cost_basis    │                          │
│  │     ⚠ total_return_pct uses price-based      │                          │
│  │  7. Return HoldingPerformanceResponse        │                          │
│  └──────────────────────────────────────────────┘                          │
│                                                                             │
│  /portfolio/holdings/{symbol}/dividends                                    │
│  ┌──────────────────────────────────────────────┐                          │
│  │  1. Resolve auth_id → user_id                │                          │
│  │  2. Get dividend records for symbol           │                          │
│  │  3. Aggregate by fiscal quarter               │                          │
│  │  4. Return list[HoldingDividendSummary]       │                          │
│  └──────────────────────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow Table

| Frontend Hook | API Endpoint | Backend Service Method | DB Tables |
|---------------|-------------|----------------------|-----------|
| `useHoldingExists(symbol)` | `GET /portfolio/holdings/{symbol}/exists` | `check_holding_exists()` | `portfolio_holdings` |
| `useHoldingPerformance(symbol, period)` | `GET /portfolio/holdings/{symbol}/performance?period=1Y` | `get_holding_performance()` | `portfolio_transactions`, `price_history`, `portfolio_dividends` |
| — (missing) | `GET /portfolio/performance/compare` | `get_performance_compare()` | needed for benchmark overlay — see BUG-02 |
| `useHoldingDividends(symbol)` | `GET /portfolio/holdings/{symbol}/dividends` | `get_holding_dividends()` | `portfolio_dividends` |

### 4.3 Error Handling Strategy

```
Layer           Error Type              Handling
──────────────  ──────────────────────  ──────────────────────────────
API Router      Invalid symbol          Return 400 + { success: false, error: message }
API Router      Stock not held          Return success:true with empty snapshots[] (not 404 as originally designed)
API Router      Internal error          Return 500 + { success: false, error: "Internal error" }

Service         No transactions         Return empty snapshots[] + success: true
Service         No price data           Use last known price or fall back to avg_cost (no yfinance fallback)
Service         Dividend calc fail      Return total_dividends: 0 (non-fatal)

Frontend Hook   Network error           Show error skeleton/retry button
Frontend Hook   Empty data              Show "No performance data yet" message
Frontend Hook   Stale data (refetch)    Keep displaying previous data + subtle loading indicator
```

---

## 5. Sequence Diagrams

### 5.1 Sequence: Navigate from Portfolio to Analysis (UC-01)

```
PortfolioInvestor    HoldingsTab          useRouter          /analysis/[symbol]     useHoldingExists
       │                  │                  │                     │                     │
       │  click row       │                  │                     │                     │
       │─────────────────>│                  │                     │                     │
       │                  │ router.push(     │                     │                     │
       │                  │   /analysis/     │                     │                     │
       │                  │   AAPL?from=     │                     │                     │
       │                  │   portfolio      │                     │                     │
       │                  │   &tab=holdings) │                     │                     │
       │                  │─────────────────>│                     │                     │
       │                  │                  │ navigate            │                     │
       │                  │                  │────────────────────>│                     │
       │                  │                  │                     │                     │
       │                  │                  │   GET /portfolio/   │                     │
       │                  │                  │   holdings/AAPL/    │                     │
       │                  │                  │   exists            │                     │
       │                  │                  │──────────────────────────────────────────>│
       │                  │                  │                     │                     │
       │                  │                  │       { held: true }│                     │
       │                  │                  │<──────────────────────────────────────────│
       │                  │                  │                     │                     │
       │                  │                  │  Insert "Perfor-    │                     │
       │                  │                  │  mance" tab into    │                     │
       │                  │                  │  TOP_TABS           │                     │
       │                  │                  │                     │                     │
       │  sees analysis page with "Performance" tab visible        │                     │
       │<──────────────────────────────────────────────────────────│                     │
```

### 5.2 Sequence: Load Stock Performance Tab (UC-02, UC-03)

```
PortfolioInvestor    StockPerformancePanel   useHoldingPerformance   FastAPI      DB
       │                      │                      │                 │          │
       │  click "Performance" │                      │                 │          │
       │─────────────────────>│                      │                 │          │
       │                      │  fetch performance   │                 │          │
       │                      │─────────────────────>│                 │          │
       │                      │                      │   GET /portfolio/│          │
       │                      │                      │   holdings/AAPL/│          │
       │                      │                      │   performance   │          │
       │                      │                      │   ?period=1Y    │          │
       │                      │                      │────────────────>│          │
       │                      │                      │                 │          │
       │                      │                      │   1. Get accounts          │
       │                      │                      │   ────────────>│──────────│
       │                      │                      │                 │          │
       │                      │                      │   2. Get transactions      │
       │                      │                      │       for symbol           │
       │                      │                      │   ────────────>│──────────│
       │                      │                      │                 │          │
       │                      │                      │   3. Get price_history     │
       │                      │                      │   ────────────>│──────────│
       │                      │                      │                 │          │
       │                      │                      │   4. FIFO calc            │
       │                      │                      │   (server-side)           │
       │                      │                      │                 │          │
       │                      │                      │   5. Compute summary       │
       │                      │                      │                 │          │
       │                      │                      │<───────────────│          │
       │                      │<─────────────────────│                 │          │
       │                      │                      │                 │          │
       │  ┌─────────────────  │                      │                 │          │
       │  │ Render:           │                      │                 │          │
       │  │ 4 summary cards   │                      │                 │          │
       │  │ Performance chart │                      │                 │          │
       │  │ Dividend chart    │                      │                 │          │
       │  └─────────────────  │                      │                 │          │
       │<─────────────────────│                      │                 │          │
```

### 5.3 Sequence: Dividend Bar Chart Load (UC-04)

```
PortfolioInvestor    StockPerformancePanel   useHoldingDividends   FastAPI      DB
       │                      │                      │                │          │
       │  tab active          │                      │                │          │
       │                      │  fetch dividends     │                │          │
       │                      │─────────────────────>│                │          │
       │                      │                      │  GET /portfolio/│          │
       │                      │                      │  holdings/AAPL/│          │
       │                      │                      │  dividends     │          │
       │                      │                      │───────────────>│          │
       │                      │                      │                │          │
       │                      │                      │  1. Get accounts       │
       │                      │                      │  ───────────>│─────────│
       │                      │                      │                │          │
       │                      │                      │  2. Get div records    │
       │                      │                      │      for symbol        │
       │                      │                      │  ───────────>│─────────│
       │                      │                      │                │          │
       │                      │                      │  3. Aggregate by qtr   │
       │                      │                      │                │          │
       │                      │                      │<───────────────│          │
       │                      │<─────────────────────│                │          │
       │                      │                      │                │          │
       │  Render BarChart     │                      │                │          │
       │  with quarterly bars │                      │                │          │
       │<─────────────────────│                      │                │          │
```

### 5.4 Sequence: Period Change (UC-03 variant)

```
PortfolioInvestor    StockPerformancePanel   TimePeriodSelector   useHoldingPerformance
       │                      │                      │                    │
       │  click "3M"          │                      │                    │
       │─────────────────────>│                      │                    │
       │                      │  onChange("3M")      │                    │
       │                      │─────────────────────>│                    │
       │                      │                      │                    │
       │                      │                      │  setPeriod("3M")   │
       │                      │                      │  (react-query re-  │
       │                      │                      │   fetches with     │
       │                      │                      │   new query key)   │
       │                      │                      │───────────────────>│
       │                      │                      │                    │
       │                      │                      │  placeholderData   │
       │                      │                      │  (keep previous    │
       │                      │                      │   data while loading)│
       │                      │                      │                    │
       │                      │  Show subtle pulse   │                    │
       │                      │  indicator on chart  │                    │
       │                      │                      │                    │
       │                      │                      │  Data arrives for  │
       │                      │                      │  3M period         │
       │                      │                      │<───────────────────│
       │                      │                      │                    │
       │  Chart updates with  │                      │                    │
       │  3M data             │                      │                    │
       │<─────────────────────│                      │                    │
```

### 5.5 Sequence: Access from Watchlist → Analysis → Performance Tab (UC-07)

```
WatchlistInvestor   StockCard/Watchlist    useRouter        /analysis/[symbol]      useHoldingExists      PortfolioService
       │                    │                  │                    │                     │                    │
       │  click stock card  │                  │                    │                     │                    │
       │───────────────────>│                  │                    │                     │                    │
       │                    │ router.push(     │                    │                     │                    │
       │                    │   /analysis/     │                    │                     │                    │
       │                    │   AAPL)          │                    │                     │                    │
       │                    │─────────────────>│                    │                     │                    │
       │                    │                  │  navigate          │                     │                    │
       │                    │                  │───────────────────>│                     │                    │
       │                    │                  │                    │                     │                    │
       │                    │                  │  ── SAME PAGE, SAME HOOK AS UC-01 ──      │                    │
       │                    │                  │                    │                     │                    │
       │                    │                  │   GET /portfolio/  │                     │                    │
       │                    │                  │   holdings/AAPL/   │                     │                    │
       │                    │                  │   exists           │                     │                    │
       │                    │                  │───────────────────────────────────────────>│                    │
       │                    │                  │                    │                     │                    │
       │                    │                  │                    │   check_holding_    │                    │
       │                    │                  │                    │   exists(1, "AAPL") │                    │
       │                    │                  │                    │                     │───────────────────>│
       │                    │                  │                    │                     │                    │
       │                    │                  │                    │   { held: true }    │                    │
       │                    │                  │                    │<────────────────────│<───────────────────│
       │                    │                  │                    │                     │                    │
       │                    │                  │  Insert "Perfor-   │                     │                    │
       │                    │                  │  mance" tab into   │                     │                    │
       │                    │                  │  TOP_TABS          │                     │                    │
       │                    │                  │                    │                     │                    │
       │  sees "Performance" tab — SAME as if clicked from Portfolio                        │                    │
       │<───────────────────────────────────────────────────────────│                     │                    │
```

Key points:
- No `?from=watchlist` param needed — same route, same code path
- The exists check is identical to UC-01 (portfolio click)
- User experience is consistent regardless of entry point

---

### 6.1 Response Time Budgets

| Operation | Target | Degradation Threshold | Measurement |
|-----------|--------|-----------------------|-------------|
| Holding exists check | < 200ms | 500ms | p95 latency |
| Holding performance (1Y) | < 1000ms | 2000ms | p95 latency |
| Holding performance (ALL) | < 3000ms | 5000ms | p95 latency |
| Holding dividends | < 500ms | 1000ms | p95 latency |
| Chart render (Recharts) | < 200ms | 500ms | JS main thread block |
| Page navigation (from click) | < 500ms | 1000ms | Next.js route transition |

### 6.2 Data Size Estimates

| Resource | Estimated Size | Notes |
|----------|---------------|-------|
| Holding exists response | ~50 bytes | `{ symbol: "AAPL", held: true }` |
| Holding performance (1Y, weekly) | ~55 snapshots × 100 bytes = ~5.5 KB | 52 weeks + endpoints |
| Holding performance (ALL, monthly) | ~120 snapshots × 100 bytes = ~12 KB | 10 years max |
| Holding dividends (all time) | ~40 records × 150 bytes = ~6 KB | 10 years of quarterly dividends |
| Chart data (merged with benchmarks) | ~55 rows × 8 columns × ~20 bytes = ~8.8 KB | In-memory after fetch |

### 6.3 Caching Strategy

```
Layer          Cache                TTL              Invalidation Trigger
─────────────  ───────────────────  ───────────────  ─────────────────────
Frontend       React Query cache    5 min (stale)    Window refocus, mutation
               (useHoldingExists)   30 min (gc)      Portfolio import
               
Frontend       React Query cache    5 min (stale)    Period change, refocus
               (useHoldingPerf)     30 min (gc)      Trade recorded
               
Frontend       React Query cache    5 min (stale)    New dividend detected
               (useHoldingDiv)      30 min (gc)      Import completed

Backend        Python in-memory     None              ── (computed on each request)
               (no caching layer)
               
Database       PostgreSQL buffer    Shared buffer    ── (managed by Postgres)
               (shared_buffers)
```

### 6.4 Optimization Techniques

| Technique | Where | Benefit |
|-----------|-------|---------|
| **placeholderData (keepPreviousData)** | Frontend hooks | Instant UI on period switch, no flash |
| **Query key co-location** | `[period]` in key | Auto-refetch when period changes, no manual logic |
| **Dedicated DB queries** | `get_transactions_for_symbol` | Avoids fetching all transactions (portfolio perf fetches ALL) |
| **Aggregation in SQL** | Dividend quarterly grouping | Less data transfer vs fetching all rows and grouping in Python |
| **Rate limiting** | 60/min (exists), 20/min (perf) | Prevents abuse, fair resource allocation |
| **SSR/SSG** | Not used (all client data) | Data is user-specific, cannot pre-render |

### 6.5 Future Scalability Concerns

| Concern | Mitigation |
|---------|------------|
| User with 10,000+ transactions for a single symbol | Limit snapshots to max 365 points; use monthly aggregation for "ALL" period |
| Dividend chart with 20+ years of data | Pre-aggregate to yearly bars for "ALL" range, quarterly for shorter ranges |
| Concurrent requests during market open | Rate limiting + connection pooling in Supabase (max 20 pool connections) |
| Large portfolio with 50+ symbols | Each symbol's performance is computed independently — no cross-symbol optimization needed |

---

## 7. Design Principles & Professional Grade Assessment

### 7.1 Applied Design Principles

| Principle | Application |
|-----------|-------------|
| **DRY (Don't Repeat Yourself)** | FIFO engine extracted into `_compute_fifo_snapshots()` shared by portfolio and single-stock performance. Navigation click handler pattern copied from `StockCard.tsx`. Query key factory pattern from existing `QK` object. |
| **Single Responsibility** | Each module has one job: `HoldingsTab` handles display, `StockPerformancePanel` handles performance display, `PortfolioService` handles business logic, `PortfolioRepository` handles DB access. |
| **Open/Closed** | Analysis page tabs are defined in an array. Adding "Performance" is insertion into that array — no switch statement changes needed. New valuation methods follow same pattern. |
| **Composition over Inheritance** | `StockPerformancePanel` composes `Metric`, `SectionHeader`, `BenchmarkSelector`, `TimePeriodSelector` rather than extending base classes. |
| **Dependency Inversion** | `PortfolioService` depends on `PortfolioRepository` interface, not concrete Supabase implementation. `useHoldingPerformance` depends on `portfolioService` injected via `ServiceContext`. |
| **Separation of Concerns** | Frontend (display, interaction) ↔ API proxy (routing) ↔ Backend API (HTTP handling) ↔ Service (business logic) ↔ Repository (data access) ↔ Database. Each layer is independently testable. |
| **Convention over Configuration** | Follows existing patterns: same rate limiting style, same error handling, same response envelope (`success: bool`), same query key structure. |
| **Fail Fast** | Invalid symbol returns 400 immediately. Stock not held returns 404. Empty results return `success: true` with empty arrays — frontend shows "No data" states. |

### 7.2 Professional Grade Indicators

| Indicator | Evidence in Design |
|-----------|--------------------|
| **Graceful degradation** | Missing data shows empty states, not errors. Network failures show retry skeletons. Period switching uses `placeholderData` for smooth transitions. |
| **Observability** | All backend errors logged with `logger.error` + `exc_info=True`. Rate limits monitored via slowapi. Frontend errors caught by React Query's `onError` and show user-facing toasts. |
| **Defensive coding** | Symbol normalization (`.toUpperCase()`). Null-safe formatting (`total_return ?? 0`). Input validation (period regex `^(1D|1W|1M|3M|1Y|5Y|ALL)$`). Account ownership verified in every endpoint. |
| **Consistent patterns** | Same 4-layer architecture as every other feature (API → Service → Repository → DB). Same response format (`success`, `error`). Same rate limiting decorators. Same dependency injection. |
| **Performance awareness** | Data size estimates documented. Caching strategy defined. Rate limits specified. Future scalability concerns addressed. |
| **Testability** | Layers are independently mockable. Service depends on repository interface. Frontend hooks depend on injected service. |

### 7.3 Simplicity Assessment

| Aspect | Why It's Simple |
|--------|-----------------|
| **Navigation** | 3 lines of code added to each of 2 files. Same pattern already used in 2 other places. No new routing, state management, or params. |
| **Conditional tab** | Single boolean state + array insertion. No new page layout, no conditional routing, no redirects. |
| **Performance chart** | Already-existing chart component adapted by swapping data source. Same Recharts library, same `ComposedChart` pattern. |
| **Dividend chart** | Same data already exists in `portfolio_dividends` table. Just aggregating differently (quarterly bars vs monthly list). |
| **Backend endpoints** | Follow existing pattern exactly. Same 3-step flow: resolve user → call service → return response. Same error handling. |

### 7.3b Planned Improvements (User-Requested)

The following improvements have been requested by the user to enhance the Stock Performance tab:

| Improvement | Description | Status |
|-------------|-------------|--------|
| **Transaction History for Ticker** | Show a table of all transactions (buys/sells) for the current symbol within the Performance panel | Not implemented |
| **Total Share Count** | Display the total number of shares currently held for this symbol in summary cards | Not implemented — requires adding `quantity` or `shares_held` to `HoldingPerformanceSnapshot` |
| **Purchase Price & Amount in Chart Tooltip** | Extend the chart tooltip to show unit price, quantity, and average cost per share when hovering over data points | Not implemented — requires exposing lot-level data |
| **Fix Benchmark Compare** | Benchmark comparison lines in the Performance chart currently show nothing (BUG-02) | Broken — see §0.1 |
| **Fix Gain/Loss Calculation** | Gain/Loss $ and % values are incorrect when shares are bought/sold during the period (BUG-01) | Broken — see §0.1 |

#### Implementation Notes for Improvements

1. **Transaction History**: Reuse existing `getAllTransactions()` service method filtered by symbol, or add a new `GET /portfolio/holdings/{symbol}/transactions` endpoint for efficiency.

2. **Total Share Count**: Either:
   - Add `shares_held` to each `HoldingPerformanceSnapshot` in the backend FIFO engine (preferred — shows shares over time)
   - Or compute from the existing `Holding` object via a parallel query

3. **Purchase Price in Tooltip**: Extend `HoldingPerformanceSnapshot` to include `avg_cost_per_share` field (computed from FIFO lots at each snapshot). Show in chart tooltip alongside position_value and cost_basis.

4. **Benchmark Fix**: Follow the pattern in `PortfolioPerformanceChart.tsx:197-230` — call `useBenchmarkCompare(period, selectedBenchmarks)` and merge benchmark data into chartData instead of setting to `null`.

5. **Gain/Loss Fix**: Change `portfolio_service.py:1976` to use `snapshots[-1]["cost_basis"]` instead of `snapshots[0]["cost_basis"]`, and fix `total_return_pct` to be relative to cost basis.

---

### 7.4 Long-Term Extensibility

| Future Feature | How Design Accommodates It |
|----------------|---------------------------|
| **Add more summary metrics** | Add fields to `HoldingPerformanceResponse` + new cards in `StockPerformancePanel` |
| **Add risk metrics per stock** | New component `<StockRiskPanel>` added as another section in the performance tab |
| **Export performance data** | Existing pattern: add `?format=csv` to `performance` endpoint |
| **Multiple currency support** | `currency` field already in `portfolio_transactions`; extend response with `currency` field |
| **Tax lot tracking details** | Extend FIFO engine to expose individual lots in response |
| **Performance vs cost basis** | Already designed into `HoldingPerformanceResponse` (position_value vs cost_basis in each snapshot) |

---

### 4.4 Missing Hooks/Endpoints (for Benchmark Compare)

The `StockPerformancePanel` is missing a `useHoldingPerformanceCompare` integration. Unlike `PortfolioPerformanceChart` which correctly calls both `usePortfolioPerformance` AND `useBenchmarkCompare`, the single-stock panel only calls `useHoldingPerformance`. It needs to:

1. Call `useBenchmarkCompare(period, selectedBenchmarks)` — reuses the portfolio-level benchmark compare endpoint
2. Merge benchmark series data into chart data (as done in `PortfolioPerformanceChart.buildChartData()`)
3. Set benchmark values to actual data points instead of `null`

Until fixed, the `BenchmarkSelector` UI is present but non-functional.

---

## 8. Assumptions

### 8.1 Design Assumptions

| # | Assumption | Rationale | Risk if Wrong |
|---|------------|-----------|---------------|
| A1 | `portfolio_transactions` table is complete and accurate for FIFO calculations | The performance engine depends on trade history, not current holdings snapshot | Numbers will be wrong if trades are missing; mitigated by holding verification checks |
| A2 | `price_history` table contains daily close prices for all held stocks | The FIFO engine needs price data for each snapshot date | Falls back to yfinance in existing code; frontend shows partial data with warning |
| A3 | A stock's symbol in `portfolio_holdings` matches the symbol used in analysis URLs | Navigation routes by symbol | Mismatch causes 404 on analysis page; already handled by existing search/redirect logic |
| A4 | The `useLivePrice` SSE data is sufficient for real-time price in performance calculations | The FIFO engine uses historical close prices for past dates, not live prices | Minor: live price data is only used for the "current" position value display |
| A5 | Tab visibility is source-agnostic — the Performance tab shows for any held stock regardless of whether the user arrived from watchlist or portfolio | UC-07 codifies that the exists check (UC-05) is the single source of truth, not the navigation referrer | If future requirements want different behavior per source, the exists check would need a `source` param |
| A6 | Performance data period options match portfolio period options (1D, 1W, 1M, 3M, 1Y, 5Y, ALL) | Consistency with existing `PERIOD_OPTIONS` | ⚠ VIOLATED: `PERIOD_OPTIONS` includes YTD but backend performance regex does not (BUG-03) |
| A7 | The authenticated user context is available in both portfolio and analysis pages | Both routes are under `(authenticated)/` layout | Guaranteed by existing auth guard layout |

### 8.2 Technical Assumptions

| # | Assumption | Rationale |
|---|------------|-----------|
| T1 | Supabase PostgreSQL connection supports `in_()` queries with large account ID lists | Already used in `get_user_all_holdings` |
| T2 | The existing `_period_to_date_range` method in `PortfolioService` can be reused for single stock | It's account-agnostic; just needs date math |
| T3 | Recharts `ComposedChart` supports mixing `Area` and `Line` types (portfolio area + benchmark lines) | Already proven in `PortfolioPerformanceChart.tsx` |
| T4 | `keepPreviousData` from `@tanstack/react-query` works with TypeScript generics | Already used in `usePortfolioPerformance` |
| T5 | Next.js API proxy rewrites `/api/proxy/portfolio/*` to backend correctly | Already proven by all existing portfolio endpoints |

### 8.3 Business Assumptions

| # | Assumption | Rationale |
|---|------------|-----------|
| B1 | The user is the only viewer of their portfolio performance data | No sharing/team features exist yet |
| B2 | Dividend data is recorded per-transaction at import time | CSV parser already extracts dividends from brokerage statements |
| B3 | Cost basis tracking uses FIFO (First In, First Out) | This is the existing implementation; no LIFO or specific identification |
| B4 | Historical prices are in the user's portfolio currency (USD/CAD) | Exchange rate handling is out of scope |

---

## 9. Test Plan

### 9.1 Unit Tests

#### 9.1.1 Backend Unit Tests

```
Test Suite: test_holding_exists
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File: backend/tests/test_portfolio_holding.py

TC-EXISTS-01: Holding exists — symbol found in user's holdings
  Input: user_id=1, symbol="AAPL"
  Mock: get_user_all_holdings returns [{ symbol: "AAPL" }, { symbol: "MSFT" }]
  Expected: { held: true }
  
TC-EXISTS-02: Holding does not exist — symbol not in user's holdings
  Input: user_id=1, symbol="GOOGL"
  Mock: get_user_all_holdings returns [{ symbol: "AAPL" }, { symbol: "MSFT" }]
  Expected: { held: false }
  
TC-EXISTS-03: User has no holdings at all
  Input: user_id=2, symbol="AAPL"
  Mock: get_user_all_holdings returns []
  Expected: { held: false }
  
TC-EXISTS-04: Case insensitivity — "aapl" matches "AAPL"
  Input: user_id=1, symbol="aapl"
  Mock: get_user_all_holdings returns [{ symbol: "AAPL" }]
  Expected: { held: true }


Test Suite: test_holding_performance
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File: backend/tests/test_portfolio_holding.py

TC-PERF-01: Basic 1-year performance
  Input: user_id=1, symbol="AAPL", period="1Y"
  Mock: 
    get_user_accounts → [{ account_id: 1 }]
    get_transactions_for_symbol → [
      { transaction_date: "2024-01-15", symbol: "AAPL", quantity: 10, unit_price: 180, activity_sub_type: "BUY" }
    ]
    price_history → { "2024-01-15": 180, "2024-07-15": 200, "2024-12-31": 220 }
  Expected: 
    - total_return = 400 (2200 - 1800)
    - total_return_pct ≈ 22.22%
    - 3 snapshots (start, mid, end)
    - First snapshot: position_value ≈ 1800, cost_basis = 1800
    ⚠ Note: This test passes with current buggy formula because cost_basis is constant
       across all snapshots (single buy, no sells). The bug is NOT detected by this test.
       A test with multiple buys/sells during the period would expose BUG-01.

TC-PERF-02: Multiple buys at different prices (FIFO test)
  Input: Same as TC-PERF-01 but with 2 buys
  Expected: Correct weighted cost basis

TC-PERF-03: Buy and partial sell
  Input: Buy 10 @ $100, Sell 3 @ $120
  Expected: Remaining position = 7 shares, cost_basis = $700

TC-PERF-04: Stock not held (no transactions)
  Mock: get_transactions_for_symbol returns []
  Expected: { success: true, snapshots: [], total_return: 0 }

TC-PERF-05: No price history available
  Mock: price_history returns empty
  Expected: snapshots use 0 for position_value, error flag set

TC-PERF-06: Period "ALL" with 5 years of data
  Expected: Monthly snapshots, max 120 points

TC-PERF-07: Invalid period string
  Input: period="INVALID"
  Expected: 422 validation error (regex reject)

TC-PERF-08: Gain/Loss with multiple buys during period (REGRESSION — exposes BUG-01)
  Input: user_id=1, symbol="AAPL", period="1Y"
  Mock:
    Buy 10 @ $100 on 2024-01-15 (pre-period: lot established before start)
    Buy 5 @ $120 on 2024-06-01 (in-period: adds to position)
    price_history: 2024-01-01=$100, 2024-12-31=$150
  Expected:
    - total_return = (15×$150) - (10×$100 + 5×$120) = $2,250 - $1,600 = $650
    - total_return_pct = $650 / $1,600 = 40.625%
    ⚠ CURRENT BUGGY FORMULA gives: total_return = $2,250 - $1,000 = $1,250 (wrong!)
      because it uses snapshots[0].cost_basis = $1,000 (only 10 shares) instead of
      snapshots[-1].cost_basis = $1,600 (15 shares after June buy)

TC-PERF-09: YTD period validation (REGRESSION — exposes BUG-03)
  Input: period="YTD"
  Expected: 200 OK (currently: 422 because regex blocks YTD)


Test Suite: test_holding_dividends
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TC-DIV-01: Quarterly dividend aggregation
  Mock: 6 dividend records across 2 quarters
  Expected: 2 quarterly summaries with correct totals

TC-DIV-02: No dividends received
  Mock: empty result
  Expected: Empty list

TC-DIV-03: Dividends across multiple accounts
  Mock: 3 dividends in account 1, 2 in account 2, all same symbol
  Expected: Correct quarterly totals (aggregated across accounts)
```

#### 9.1.2 Frontend Unit Tests

```
Test Suite: useHoldingExists hook
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File: web/src/features/portfolio/hooks/__tests__/usePortfolio.test.ts

TC-HOOK-EXISTS-01: Returns held=true when API returns true
  Mock: portfolioService.checkHoldingExists resolves { symbol: "AAPL", held: true }
  Expected: data.held === true

TC-HOOK-EXISTS-02: Returns held=false when API returns false
  Mock: resolves { symbol: "AAPL", held: false }
  Expected: data.held === false

TC-HOOK-EXISTS-03: Query key includes uppercased symbol
  Assert: QK.holdingExists("aapl") === ["portfolio", "holding", "exists", "AAPL"]


Test Suite: useHoldingPerformance hook
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TC-HOOK-PERF-01: Returns performance response
  Mock: portfolioService.getHoldingPerformance resolves valid HoldingPerformanceResponse
  Expected: data.snapshots.length > 0, data.total_return matches mock

TC-HOOK-PERF-02: Query key changes with period
  Assert: QK.holdingPerformance("AAPL", "1M") !== QK.holdingPerformance("AAPL", "1Y")

TC-HOOK-PERF-03: Disabled when no symbol
  Assert: enabled = true only when symbol is non-empty


Test Suite: StockPerformancePanel component
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File: web/src/features/analysis/components/__tests__/stock-performance.test.tsx

TC-PANEL-01: Renders 4 summary cards when data loaded
  Render <StockPerformancePanel symbol="AAPL" />
  Assert: 4 Metric components rendered with correct values
  
TC-PANEL-02: Shows loading skeleton while fetching
  Assert: Skeleton components visible, no Metric components

TC-PANEL-03: Shows error state on fetch failure
  Mock: useHoldingPerformance returns isError=true
  Assert: Error message visible

TC-PANEL-04: Renders ComposedChart when snapshots exist
  Assert: Recharts ResponsiveContainer rendered with ComposedChart

TC-PANEL-05: Renders BarChart when dividends exist
  Assert: Recharts BarChart rendered

TC-PANEL-06: Period selector changes trigger refetch
  Simulate: click "3M" button
  Assert: useHoldingPerformance called with period="3M"
```

### 9.2 Integration Tests

```
Test Suite: Frontend-Backend Integration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TC-INT-01: End-to-end navigation flow
  1. Visit /portfolio?tab=holdings
  2. Click on AAPL holding row
  3. Assert: navigated to /analysis/AAPL
  4. Assert: "Performance" tab visible in TOP_TABS
  5. Click "Performance" tab
  6. Assert: Summary cards show correct values matching holdings page

TC-INT-02: Non-held stock shows no Performance tab
  1. Visit /analysis/STOCK_NOT_IN_PORTFOLIO
  2. Assert: "Performance" tab NOT in TOP_TABS

TC-INT-03: Period switching on performance chart
  1. Navigate to /analysis/AAPL → Performance tab
  2. Assert: Default period = "1Y"
  3. Click "3M" in TimePeriodSelector
  4. Assert: Chart re-renders with fewer data points

TC-INT-04: Benchmark toggle
  1. Performance tab visible
  2. Click "SPY" in BenchmarkSelector
  3. Assert: SPY line appears on chart ⚠ CURRENTLY BROKEN (BUG-02)
  4. Click "SPY" again
  5. Assert: SPY line disappears

TC-INT-05: Dividend bar chart rendering
  1. Performance tab visible for dividend-paying stock (e.g., "AAPL")
  2. Assert: BarChart rendered with quarterly bars
  3. Hover over bar
  4. Assert: Tooltip shows amount + date
```

### 9.3 Performance Tests

```
Test Suite: Performance & Load
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TC-PERF-01: Holding exists response time
  Target: p95 < 200ms
  Method: 100 requests with 10 concurrent users
  Assert: p95 latency under 200ms

TC-PERF-02: Holding performance (1Y) response time
  Target: p95 < 1000ms
  Method: 50 requests with 5 concurrent users
  Assert: p95 latency under 1000ms

TC-PERF-03: Holding performance (ALL) response time
  Target: p95 < 3000ms
  Method: 20 requests with 2 concurrent users
  Assert: p95 latency under 3000ms

TC-PERF-04: Chart render performance
  Target: < 200ms main thread blocking
  Method: React Profiler, 55 data points × 8 series
  Assert: Commit time < 200ms

TC-PERF-05: Cache hit ratio
  Target: > 80% within 5 minute window
  Method: Monitor React Query devtools, repeated tab switches
  Assert: Refetches are minimal (< 20% of navigations)

TC-PERF-06: Memory usage
  Target: < 5MB incremental for performance tab
  Method: Chrome Memory tab before/after tab switch
  Assert: No memory leak, heap returns to baseline after navigating away
```

### 9.4 Edge Case Tests

```
Test Suite: Edge Cases
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TC-EDGE-01: Zero-cost basis (free stock/stock grant)
  Mock: transaction with unit_price=0
  Expected: total_return_pct shows ∞ or "—" gracefully

TC-EDGE-02: Negative cost basis (wash sales, return of capital)
  Mock: sells exceed buys (speculative)
  Expected: Negative cost basis handled, total_return_pct = "—"

TC-EDGE-03: Stock split symbol change
  If symbol changes (e.g., GOOG→GOOGL), transactions may have old symbol
  Expected: Only matches exact symbol; no cross-symbol aggregation

TC-EDGE-04: Empty portfolio (no accounts)
  Mock: get_user_accounts returns []
  Expected: { held: false }, empty snapshots

TC-EDGE-05: Stock sold completely (zero current position)
  Mock: transactions show full sell, current holdings show 0 quantity
  Expected: { held: false } (no current position), but historical data exists
  Decision: If closed position, "Performance" tab shows but with "Position Closed" banner

TC-EDGE-06: Multiple accounts, same symbol
  Mock: AAPL in account 1 (10 shares) and account 2 (20 shares)
  Expected: Aggregated position_value = 30 × current_price

TC-EDGE-07: Very long time range with sparse data
  Period "ALL" with only 1 trade in 10 years
  Expected: Only 1 snapshot (or snapshots at trade dates), chart shows minimal data
```

### 9.5 Regression Tests

```
Test Suite: Regression
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TC-REG-01: Portfolio holdings page unchanged for non-click interactions
  1. Visit /portfolio?tab=holdings
  2. Hover over holding rows (no click)
  Assert: No navigation occurs, page layout unchanged

TC-REG-02: Analysis page unchanged for non-held stocks
  1. Visit /analysis/TICKER_NOT_HELD
  2. Assert: TOP_TABS exactly matches existing 9 tabs
  3. Assert: All existing tabs work correctly (intrinsic, dividend, etc.)

TC-REG-03: Portfolio performance chart unchanged
  1. Visit /portfolio?tab=performance
  2. Assert: PortfolioPerformanceChart still renders with same data source

TC-REG-04: Existing analysis tabs preserve their state
  1. Visit /analysis/AAPL
  2. Click "Dividend" tab
  3. Assert: Dividend panel loads correctly (no cross-contamination from performance feature)

TC-REG-05: Watchlist navigation — Performance tab visible for held stocks
  1. Visit /dashboard (watchlist)
  2. Click on AAPL card (user holds AAPL)
  3. Assert: Navigated to /analysis/AAPL
  4. Assert: "Performance" tab visible in TOP_TABS
  5. Assert: Performance data loads correctly (same data as TC-REG-01 path)

TC-REG-06: Watchlist navigation — no Performance tab for non-held stocks
  1. Visit /dashboard (watchlist)
  2. Click on GOOGL card (user does NOT hold GOOGL)
  3. Assert: Navigated to /analysis/GOOGL
  4. Assert: "Performance" tab NOT in TOP_TABS

TC-REG-07: Watchlist → Performance tab data consistency
  1. Note values from /portfolio?tab=holdings for AAPL (total value, gain/loss)
  2. Visit /dashboard, click AAPL
  3. Navigate to Performance tab
  4. Assert: Summary card values match observed portfolio values

TC-REG-08: Browser back button works (portfolio origin)
  1. From /portfolio, click holding → /analysis/AAPL
  2. Click browser back
  3. Assert: Returns to /portfolio with same tab+account state

TC-REG-09: Browser back button works (watchlist origin)
  1. From /dashboard, click AAPL card → /analysis/AAPL
  2. Click browser back
  3. Assert: Returns to /dashboard with same watchlist state
```

### 9.6 Test Automation Strategy

| Test Type | Tool | When Run | Who Runs |
|-----------|------|----------|----------|
| Backend unit tests | pytest | Pre-commit, CI | Developer, CI |
| Frontend unit tests | Vitest | Pre-commit, CI | Developer, CI |
| Integration tests | Playwright | CI (PR) | CI |
| Performance tests | k6 + React Profiler | Nightly | QA |
| Regression suite | Playwright (full suite) | CI (merge to main) | CI |

### 9.7 Test Data Setup

```sql
-- Test fixture: seed data for integration tests
INSERT INTO portfolio_accounts (account_id, user_id, brokerage_id, account_name) VALUES
  (1, 1, 1, 'Main TFSA'),
  (2, 1, 1, 'RRSP');

INSERT INTO portfolio_transactions (account_id, symbol, quantity, unit_price, activity_sub_type, transaction_date)
VALUES
  (1, 'AAPL', 10, 150.00, 'BUY', '2024-01-15'),
  (1, 'AAPL', 5, 180.00, 'BUY', '2024-06-01'),
  (2, 'AAPL', 8, 175.00, 'BUY', '2024-03-10'),
  (1, 'AAPL', -3, 200.00, 'SELL', '2024-09-01');

INSERT INTO portfolio_dividends (account_id, symbol, amount, payment_date, fiscal_year, fiscal_month)
VALUES
  (1, 'AAPL', 22.50, '2024-02-15', 2024, 2),
  (1, 'AAPL', 23.00, '2024-05-15', 2024, 5),
  (2, 'AAPL', 18.00, '2024-02-15', 2024, 2),
  (1, 'AAPL', 23.50, '2024-08-15', 2024, 8);
```

Expected results for test data:
- **Total position:** 20 shares (10+5+8-3)
- **Total gain/loss:** (20 × current_price) - total_cost
- **Total dividends:** $87.00
- **Quarterly breakdown:** Q1=$40.50, Q2=$23.00, Q3=$23.50

---

## 10. Appendix: Calculation Correctness Validation

### 10.1 Gain/Loss ($) — `total_return`

**Desired formula (industry standard):**
```
Gain/Loss = Current Market Value - Cost Basis of Shares Held
          = position_value - cost_basis_of_currently_held_shares
```

**Current (buggy) implementation** (`portfolio_service.py:1976`):
```python
total_return = last_value - snapshots[0]["cost_basis"]
```

**Why it's wrong:** `snapshots[0]["cost_basis"]` is the cost basis at the *start* of the period. If shares were bought during the period, this understates the cost basis → inflates gain. If shares were sold, it overstates the cost basis → deflates gain.

**Correct formula:**
```python
last_cost_basis = snapshots[-1]["cost_basis"]  # cost basis at end of period (today)
total_return = last_value - last_cost_basis
```

**Validation examples:**

| Scenario | First cost_basis | Last cost_basis | Current Value | Buggy Result | Correct Result |
|----------|-----------------|-----------------|---------------|--------------|----------------|
| Single buy, hold | $1,000 | $1,000 | $1,500 | $500 ✅ | $500 ✅ |
| Buy more during period | $1,000 | $1,600 | $2,250 | $1,250 ❌ | $650 ✅ |
| Partial sell during period | $1,000 | $700 | $1,050 | $50 ❌ | $350 ✅ |

### 10.2 Gain/Loss (%) — `total_return_pct`

**Desired formula (industry standard):**
```
Gain/Loss % = (Current Value - Cost Basis) / Cost Basis × 100
            = Gain/Loss $ / Cost Basis × 100
```

**Current (buggy) implementation** (`portfolio_service.py:1977`):
```python
total_return_pct = ((last_value - first_value) / first_value * 100) if first_value > 0 else 0
```

**Why it's wrong:** This measures the percentage change in *position value* from start to end, not the return on invested capital. If the user added more capital during the period, the position value grows but that growth isn't from investment returns — it's from additional capital.

**Correct formula:**
```python
last_cost_basis = snapshots[-1]["cost_basis"]
total_return_pct = (total_return / last_cost_basis * 100) if last_cost_basis > 0 else 0
```

### 10.3 Dividend Yield (%) — `total_dividends_pct`

**Current implementation** (`portfolio_service.py:1978`):
```python
total_dividends_pct = (
    total_dividends / (snapshots[-1].get("cumulative_invested") or 1) * 100
) if snapshots[-1].get("cumulative_invested", 0) > 0 else 0
```

**Issue:** When `cumulative_invested` is 0, `or 1` fallback produces wildly inflated percentage (e.g., $50 dividends / 1 × 100 = 5000%). Should return 0 when denominator is 0.

**Improved formula:**
```python
cum_invested = snapshots[-1].get("cumulative_invested", 0)
total_dividends_pct = (total_dividends / cum_invested * 100) if cum_invested > 0 else 0
```

### 10.4 Position Value — `position_value`

**Formula** (in `_compute_fifo_snapshots`, lines 1561-1587):
```
For each held lot:
  position_value += qty_in_lot × historical_price (or avg_cost if no price data)
```

**Validation:** This is correct FIFO valuation. The historical price lookup tries exact date match first, then nearest preceding date. Falls back to average cost per share if no price data exists. ✓

### 10.5 Cost Basis — `cost_basis`

**Formula** (in `_compute_fifo_snapshots`, lines 1561-1587):
```
For each held lot:
  cost_basis += qty_in_lot × cost_per_share_of_lot
```

**Validation:** Correct — sum of (remaining shares × original purchase price) across all FIFO lots. This is the standard tax lot cost basis. ✓

### 10.6 Cumulative Invested — `cumulative_invested`

**Formula** (in `get_holding_performance`, lines 1919-1931):
```
running_ci = 0
For each transaction (all time, sorted):
  if BUY:  running_ci += qty × price + commission
  if SELL: running_ci -= abs(qty) × price - commission
  record running_ci at transaction date
```

**Issue (minor):** The SELL formula `abs(qty) * price - commission` subtracts commission from the proceeds (reducing cumulative_invested more than it should). The BUY formula correctly adds commission. For consistency:
- Buy:  `running_ci += qty * price + commission` (money going out) ✓
- Sell: `running_ci -= abs(qty) * price - commission` (money coming in, but...)
  - Should arguably be `running_ci -= abs(qty) * price - commission` if we want net cash flow
  - Or `running_ci -= abs(qty) * price` + `running_ci += commission` if commission is considered a cost

Either way, the SELL formula is symmetric with BUY and gives a reasonable "net cash out" measure. ✓

### 10.7 Benchmark Compare — Missing

The `StockPerformancePanel` fundamentally cannot show benchmarks because:
1. No `useBenchmarkCompare` hook is called
2. The `buildPerformanceChartData` function initializes benchmark values to `null`
3. No endpoint integration exists for holding-level benchmark comparison

**Fix:** Follow the pattern in `PortfolioPerformanceChart.tsx`:
```typescript
// Call the hook
const { data: compareData } = useBenchmarkCompare(period, selectedBenchmarks);

// Merge in buildChartData instead of setting to null
function buildPerformanceChartData(perf, compareData, selectedBenchmarks) {
  // If no benchmarks selected, return perf data only
  if (!compareData || selectedBenchmarks.length === 0) {
    return perf.snapshots.map(s => ({
      date: s.date,
      position_value: s.position_value,
      cost_basis: s.cost_basis,
    }));
  }
  // Merge benchmark series into date-keyed map
  const dateMap = {};
  for (const s of perf.snapshots) {
    dateMap[s.date] = { ...s, position_value: s.position_value, cost_basis: s.cost_basis };
  }
  for (const bs of compareData.benchmarks) {
    for (const point of bs.data) {
      dateMap[point.date] = { ...(dateMap[point.date] || {}), [bs.symbol]: point.value };
    }
  }
   return Object.keys(dateMap).sort().map(date => ({ date, ...dateMap[date] }));
}

---

## 11. Proposed Enhancements — Implementation Plan

> **Status:** Proposed (not yet implemented)
> **Section added:** 2026-06-06
> **Related:** P-01 through P-07 in §0.3

### 11.1 P-01: Add "Total Invested" Summary Card

**Problem:** Users can see current value and gain/loss but not the total capital they have put into the position.

**Implementation:**
```typescript
// stock-performance-panel.tsx — add after Total Value card
<MetricItem
  label="Total Invested"
  value={perf.snapshots.length > 0
    ? `$${perf.snapshots[perf.snapshots.length - 1].cumulative_invested.toLocaleString(...)}`
    : '—'}
  icon={Wallet}
  color="text-white"
/>
```

**Data source:** `snapshots[-1].cumulative_invested` — already exists in the response.

### 11.2 P-02: Chart Starts from First Purchase Date

**Problem:** The "ALL" period uses portfolio-wide earliest transaction date, not the symbol-specific first purchase. Periods before the first purchase show empty data.

**Root cause:** `_period_to_date_range(period, account_ids)` in `get_holding_performance()` passes `account_ids` (portfolio level) instead of computing from the symbol's own transactions.

**Fix — `get_holding_performance()` in `portfolio_service.py`:**

```python
async def get_holding_performance(self, user_id, symbol, period="1Y"):
    txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
    if not txns:
        return empty_response

    # Compute symbol-specific date range
    if period.upper() == "ALL":
        symbol_earliest = min(t["transaction_date"] for t in txns
                              if isinstance(t.get("transaction_date"), (date, datetime)))
        start_date = symbol_earliest if isinstance(symbol_earliest, date) else symbol_earliest.date()
    else:
        # For named periods, use the later of period_start or first purchase
        period_start, end_date = self._period_to_date_range(period, account_ids)
        symbol_first = min(t["transaction_date"] for t in txns
                           if isinstance(t.get("transaction_date"), (date, datetime)))
        symbol_first = symbol_first if isinstance(symbol_first, date) else symbol_first.date()
        start_date = max(period_start, symbol_first)

    # ... rest of existing logic
```

**Chart rendering behavior:**
| Period | Start Date | Pre-Purchase Behavior |
|--------|-----------|----------------------|
| 1D–5Y | `max(period_start, first_purchase_date)` | Snapshots before first purchase are excluded |
| ALL | `first_purchase_date` | Chart starts exactly at first purchase |
| User selects date before purchase | All snapshots show `position_value=0, cost_basis=0` | Chart shows flat zero line with tooltip "No position" |

### 11.3 P-03: Holding-Level Benchmark Comparison

**Problem:** Current benchmark comparison (`get_performance_compare`) uses portfolio-level cash flows (`_get_cashflow_deltas` — MoneyMovement/BonusPayment transactions). For single-stock comparison, we need to simulate benchmarks using the symbol's own buy/sell cash flows.

**Current flow (WRONG for single stock):**
```
get_performance_compare()
  → get_portfolio_performance()  [portfolio-wide]
  → _get_cashflow_deltas()       [portfolio deposits/withdrawals]
  → _simulate_benchmark_value()  [uses portfolio cash flows]
  → Returns portfolio vs benchmark comparison

StockPerformancePanel
  → useBenchmarkCompare(period, selectedBenchmarks)  [calls portfolio-level endpoint]
  → buildPerformanceChartData()  [merges into holding chart]
```

**Fix: Add `get_holding_performance_compare()` service method:**

```python
async def get_holding_performance_compare(
    self, user_id, symbol, period, benchmark_symbols
) -> Dict:
    """Compare single-stock performance against benchmarks using same buy/sell cash flows."""

    # 1. Get holding performance — provides position_value snapshots
    perf = await self.get_holding_performance(user_id, symbol, period)
    if not perf["snapshots"]:
        return empty_response

    snapshots = perf["snapshots"]
    start_date, end_date = ...  # same as holding performance

    # 2. Find first non-zero snapshot (when position was first opened)
    first_nonzero = next((i for i, s in enumerate(snapshots) if s["position_value"] > 0), 0)
    snapshots_subset = snapshots[first_nonzero:]
    initial_value = snapshots_subset[0]["position_value"]
    snapshot_dates = [s["date"] for s in snapshots_subset]

    # 3. Build holding-level cash flow deltas from the symbol's own transactions
    #    (buys = positive cash flow into benchmark, sells = negative)
    txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
    holding_cashflows = []
    for t in txns:
        qty = float(t.get("quantity") or 0)
        price = float(t.get("unit_price") or 0)
        commission = float(t.get("commission") or 0)
        d = t["transaction_date"]
        if isinstance(d, str): d = date.fromisoformat(d)
        sub = (t.get("activity_sub_type") or "").upper()
        if sub == "BUY":
            amount = abs(qty) * price + commission  # money outflow
            holding_cashflows.append({"date": d, "amount": amount})
        elif sub == "SELL":
            amount = -(abs(qty) * price - commission)  # negative = money inflow
            holding_cashflows.append({"date": d, "amount": amount})
    holding_cashflows.sort(key=lambda x: x["date"])

    # 4. Simulate each benchmark using holding-level cash flows
    benchmark_series = []
    for sym in benchmark_symbols:
        company = await self.financial_repo.get_company_by_symbol(sym)
        if not company: continue
        series = self._simulate_benchmark_value(
            benchmark_company_id=company["company_id"],
            start_date=start_date,
            end_date=end_date,
            initial_value=initial_value,
            cashflow_deltas=holding_cashflows,
            snapshot_dates=snapshot_dates,
        )
        if series:
            benchmark_series.append({"symbol": sym, "name": sym, "data": series})

    return {
        "success": True,
        "period": period,
        "portfolio": [{"date": s["date"], "value": s["position_value"]} for s in snapshots_subset],
        "benchmarks": benchmark_series,
    }
```

**New API route:**
```python
@router.get(
    "/portfolio/holdings/{symbol}/performance/compare",
    tags=["Portfolio"], status_code=200
)
async def get_holding_performance_compare(
    request: Request, symbol: str,
    period: str = Query("1Y", regex="^(1D|1W|1M|3M|1Y|5Y|YTD|ALL)$"),
    benchmarks: str = "SPY",
    user: dict = Depends(get_current_user_dep),
) -> BenchmarkCompareResponse:
    """Compare single-stock performance vs benchmarks using holding-level cash flows."""
    ...
```

**Frontend hook update:**
```typescript
// New hook in usePortfolio.ts
export function useHoldingBenchmarkCompare(
  symbol: string,
  period: TimePeriod,
  benchmarks: string[],
) {
  const { portfolioService } = useServices();
  return useQuery({
    queryKey: QK.holdingBenchmarkCompare(symbol, period, benchmarks),
    queryFn: () => portfolioService.getHoldingBenchmarkCompare(symbol, period, benchmarks),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
    enabled: benchmarks.length > 0,
  });
}
```

### 11.4 P-04: Transaction History Table

**Problem:** Users cannot see the individual buy/sell transactions that make up their position in the Performance tab.

**New backend endpoint:**
```python
@router.get(
    "/portfolio/holdings/{symbol}/transactions",
    tags=["Portfolio"], status_code=200
)
@limiter.limit("30/minute")
async def get_holding_transactions(
    request: Request, symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> list[dict]:
    """Return all BUY/SELL transactions for a symbol across user accounts."""
    auth_id = user["sub"]
    db_user_id = _resolve_db_user_id(auth_id)
    service = _get_portfolio_service()
    return await service.get_holding_transactions(db_user_id, symbol)
```

**New service method:**
```python
async def get_holding_transactions(self, user_id, symbol):
    txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
    accounts = self.portfolio_repo.get_user_accounts(user_id)
    account_map = {a["account_id"]: a for a in accounts}

    result = []
    for t in txns:
        sub = (t.get("activity_sub_type") or "").upper()
        if sub not in ("BUY", "SELL"):
            continue
        aid = t.get("account_id")
        result.append({
            "transaction_id": t["transaction_id"],
            "transaction_date": t["transaction_date"].isoformat() if isinstance(t["transaction_date"], date) else t["transaction_date"],
            "activity_sub_type": sub,
            "quantity": float(t.get("quantity") or 0),
            "unit_price": float(t.get("unit_price") or 0),
            "commission": float(t.get("commission") or 0),
            "net_cash_amount": float(t.get("net_cash_amount") or 0),
            "account_name": account_map.get(aid, {}).get("account_name", "Unknown"),
            "account_type": account_map.get(aid, {}).get("account_type", ""),
        })

    result.sort(key=lambda x: x["transaction_date"], reverse=True)
    return result
```

**Frontend component:**
```typescript
// TransactionHistory table in StockPerformancePanel
function TransactionHistory({ symbol }: { symbol: string }) {
  const { data: transactions, isLoading } = useHoldingTransactions(symbol);

  return (
    <div className="glass-panel p-6">
      <SectionHeader title="Transaction History" subtitle="All buys and sells" />
      <table className="w-full text-sm">
        <thead>
          <tr className="text-white/40 text-xs uppercase tracking-wider">
            <th>Date</th><th>Type</th><th>Qty</th>
            <th>Price</th><th>Commission</th><th>Net Cash</th><th>Account</th>
          </tr>
        </thead>
        <tbody>
          {transactions?.map(tx => (
            <tr key={tx.transaction_id}>
              <td>{tx.transaction_date}</td>
              <td className={tx.activity_sub_type === 'BUY' ? 'text-green-400' : 'text-red-400'}>
                {tx.activity_sub_type}
              </td>
              <td>{tx.quantity}</td>
              <td>${tx.unit_price.toFixed(2)}</td>
              <td>${tx.commission.toFixed(2)}</td>
              <td>${tx.net_cash_amount.toFixed(2)}</td>
              <td className="text-white/40">{tx.account_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### 11.5 P-05: Per-Account Breakdown

**Problem:** Users cannot see how their position is distributed across accounts (e.g., 10 shares in TFSA, 20 in RRSP).

**Implementation approach:** Reuse existing `portfolio_holdings` table data filtered by symbol, enriched with current market price.

**New endpoint:** `GET /portfolio/holdings/{symbol}/accounts`

```python
async def get_holding_accounts(self, user_id, symbol):
    holdings = self.portfolio_repo.get_user_all_holdings(user_id)
    symbol_holdings = [h for h in holdings if h.get("symbol", "").upper() == symbol.upper()]

    # Enrich with live prices
    enriched = await self.enrich_holdings_with_prices(symbol_holdings)

    # Compute dividends received per account
    divs = self.portfolio_repo.get_dividends_for_symbol(user_id, symbol)
    divs_by_account = defaultdict(float)
    for d in divs:
        divs_by_account[d.get("account_id")] += float(d.get("amount") or 0)

    result = []
    for h in enriched:
        shares = float(h.get("quantity") or 0)
        cost = float(h.get("total_cost") or 0)
        value = float(h.get("current_value") or 0)
        gl = value - cost
        gl_pct = (gl / cost * 100) if cost > 0 else 0
        result.append({
            "account_id": h["account_id"],
            "account_name": h.get("account_name", "Unknown"),
            "account_type": h.get("account_type", ""),
            "shares_held": shares,
            "total_cost": round(cost, 2),
            "current_value": round(value, 2),
            "unrealized_gain_loss": round(gl, 2),
            "unrealized_gain_loss_pct": round(gl_pct, 2),
            "dividends_received": round(divs_by_account.get(h["account_id"], 0), 2),
        })

    return result
```

### 11.6 P-06: Pre-Purchase Period Shows "No Data"

**Problem:** When the selected period starts before the first purchase, users see a flat zero line without context.

**Implementation:** The snapshots engine already produces `position_value=0` and `cost_basis=0` for dates before any lots exist. The UI should detect this and show a clear indicator:

```typescript
// In StockPerformancePanel chart rendering
const firstNonZeroSnapshot = perf.snapshots.find(s => s.position_value > 0);
const hasPrePurchaseData = firstNonZeroSnapshot && chartData.some(d => d.date < firstNonZeroSnapshot.date);

// Show pre-purchase zone indicator
{hasPrePurchaseData && (
  <div className="text-xs text-white/20 text-center py-1">
    ⸻ No position held before {firstNonZeroSnapshot.date} ⸻
  </div>
)}
```

### 11.7 P-07: Clarify Gain/Loss Card Labels

**Problem:** The gain/loss cards show dollar and percentage values but do not explain the formula used.

**Implementation:**
```typescript
<MetricItem
  label="Gain/Loss (Cost vs Value)"
  subtitle={`Cost Basis: $${lastCostBasis.toLocaleString()}`}
  // ...
/>
<MetricItem
  label="Return on Invested Capital"
  subtitle={`Total Invested: $${lastCumulativeInvested.toLocaleString()}`}
  // ...
/>
```

### 11.8 Updated Data Flow

After implementing P-01 through P-07, the data flow becomes:

```
StockPerformancePanel [ENHANCED]
├─ SummaryCards (5 cards: Value, Invested, Gain/Loss $, Gain/Loss %, Dividends)
│   └─ useHoldingPerformance(symbol, period)
│
├─ TransactionHistory [NEW]
│   └─ useHoldingTransactions(symbol)
│       └─ GET /portfolio/holdings/{symbol}/transactions
│
├─ AccountBreakdown [NEW]
│   └─ useHoldingAccounts(symbol)
│       └─ GET /portfolio/holdings/{symbol}/accounts
│
├─ PerformanceChart
│   ├─ useHoldingPerformance(symbol, period) ← chart starts from first purchase
│   ├─ useHoldingBenchmarkCompare(symbol, period, benchmarks) [NEW — P-03]
│   │   └─ GET /portfolio/holdings/{symbol}/performance/compare
│   ├─ Chart: position_value area (from first purchase date)
│   ├─ Chart: cost_basis line
│   ├─ Chart: benchmark lines (holding-cash-flow adjusted)
│   └─ Pre-purchase: "No position held" indicator
│
└─ DividendChart
    └─ useHoldingDividends(symbol)
```

### 11.9 Implementation Order

| Priority | Item | Complexity | Dependencies |
|----------|------|-----------|--------------|
| 1 | P-01: Total Invested Card | Low (1 line UI change) | None |
| 2 | P-02: Chart Start from Purchase | Medium (backend + test update) | None |
| 3 | P-06: Pre-Purchase "No Data" | Low (UI indicator) | P-02 |
| 4 | P-07: Clarify Card Labels | Low (label change) | None |
| 5 | P-03: Holding-Level Benchmark Compare | High (new endpoint + hook) | P-02 |
| 6 | P-04: Transaction History | Medium (new endpoint + table) | None |
| 7 | P-05: Per-Account Breakdown | Medium (new endpoint + table) | None |

---

## 12. Performance Summary Card + Tab Overflow Fix

> **Version:** 1.0
> **Date:** 2026-06-07
> **Status:** Proposed for review
> **Design Goals:** Professional grade, maximum reuse, single source of truth, minimal frontend computation

### 12.1 UI Mockup

The summary card sits at the **top** of the Performance tab, replacing the existing 5 metric cards with a single unified card organized into clear sections:

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  Gain/Loss  -$748.48  ·  -5.1%                                                     │
│                                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────┐                                │
│  │  Price change         │  │  Dividends            │                                │
│  │  -$782.90             │  │  +$34.42              │                                │
│  │  (from price movement)│  │  (received to date)   │                                │
│  └──────────────────────┘  └──────────────────────┘                                │
│                                                                                     │
│  Avg Cost $182.40  ·  Last Price $195.70  ·  +7.3% from cost                       │
│                                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  ┌────────────────────┐    │
│  │  Best month   │  │  Worst month  │  │  Max drawdown  │  │  Volatility (30d)  │    │
│  │  Jan 2026     │  │  Feb 2026     │  │  -44.1%        │  │  28.4% ANNUALIZED  │    │
│  │  +4.2%        │  │  -18.7%       │  │  Peak → trough │  │                    │    │
│  └──────────────┘  └──────────────┘  └────────────────┘  └────────────────────┘    │
│                                                                                     │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────────────┐    │
│  │  Days above cost basis           │  │  Longest drawdown                    │    │
│  │  31 of 213 days                  │  │  14 weeks (Feb → now)                │    │
│  │  Since Nov 2025                  │  │  Ongoing                             │    │
│  └──────────────────────────────────┘  └──────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Organization rationale:**
| Section | What | Why |
|---------|------|-----|
| **Header** | Gain/Loss $ · % | The single most important number — prominent, colored, immediately answers "am I up or down?" |
| **Row 1** | Price change + Dividends | Attribution — answers "what caused it?" Two cards only, no clutter |
| **Context line** | Avg Cost · Last Price · % diff | Cost basis context — not a full card row, compact single line with $\textcolor{var(--indigo-400)}{\longrightarrow}$ arrow visual |
| **Row 2** | Best/Worst month + Max drawdown + Volatility | Risk & performance quadrants — uniform 4-column grid, all %-based metrics |
| **Row 3** | Days above cost basis + Longest drawdown | Extended metrics — wider cards for text-heavy stats, duration-based |

**What was removed and why:**
| Removed from earlier draft | Reason |
|---------------------------|--------|
| "What's driving the ..." header title | Redundant with the breakdown below it. Gain/Loss is the headline, breakdown is the detail. |
| Separate Gain/Loss line | Repeated the same combined_return. Now merged into the header. |
| Avg Cost as a 3rd card in Row 1 | Out of place in the "return attribution" group. Moved to its own compact line. |
| Longest drawdown in 4-column grid | Duration text is long ("Feb → now") — needs wider column. Moved to Row 3. |
| Volatility in Row 3 | It's a % metric that fits a narrow card. Moved to the 4-column risk grid. |

### 12.2 Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Where to compute metrics** | Backend (`get_holding_performance()`) | Avoids re-fetching price_history / re-running FIFO logic on frontend. Single source of truth. |
| **New fields vs new endpoint** | New fields in `HoldingPerformanceResponse` | Represents summary OF the same performance data — not a separate concern. Zero extra network requests. |
| **Reuse existing stats module** | `from backend.shared.portfolio_stats import ...` | `compute_max_drawdown`, `compute_drawdown_series`, `compute_annualized_volatility`, `compute_daily_returns` — all exist and are used by `PortfolioRiskService`. |
| **Monthly returns computation** | Backend helper `_compute_monthly_returns()` | Groups position_value snapshots by calendar month; returns sorted list of `{month, return_pct}`. |
| **Volatility data source** | `price_history` table (30 trailing days) | Snapshots may be weekly/monthly — too coarse for daily vol. Use separate daily price query. |
| **Days above cost basis** | From snapshot position_value vs cost_basis | Only count days where position is held (cost_basis > 0). Gives fraction and raw count. |
| **Avg cost vs current price** | From `snapshots[-1].avg_cost_per_share` + `useLivePrice(symbol)` hook | `current_price` does NOT exist in `HoldingPerformanceSnapshot`. Use `useLivePrice` instead — already called in the parent `AnalysisPage` and can be passed as prop or called inside `StockPerformancePanel`. % diff = (live_price − avg_cost) / avg_cost × 100. |
| **Gain/Loss $ + % combined** | Single header: `-$748.48 · -5.1%` | Replaces two separate MetricItem cards and the redundant "What's driving" title. Combined return shown ONCE as the headline. Attribution (price vs dividends) shown below. |
| **Monthly returns limitation** | Only computed for periods ≤1Y | For "ALL" period, snapshots are monthly → 1 data point per month → cannot compute monthly return. Show "—" for monthly metrics when period is "ALL". Fall back to "Period not available" label. |
| **Tab overflow** | Visible thin scrollbar (custom CSS) | Removes `no-scrollbar` from tab container, adds themed thin scrollbar. Zero layout change, works at all widths. |

### 12.3 Reuse Map

Every metric reuses an existing function or data field:

| Metric | Data Source | Computation | Reuses? |
|--------|------------|-------------|---------|
| Price return | `total_return` (already computed) | Direct field | ✅ Yes |
| Dividend return | `total_dividends` (already computed) | Direct field | ✅ Yes |
| Combined return | `total_return + total_dividends` | Simple sum | ✅ Yes (no new queries) |
| Best/worst month | Snapshots' `position_value` | `_compute_monthly_returns()` — new helper, ~25 lines | ⚠ New, but uses already-in-memory snapshots |
| Max drawdown | Snapshots' `position_value` | `portfolio_stats.compute_max_drawdown(values)` | ✅ Yes |
| Drawdown duration | Drawdown series dates | `portfolio_stats.compute_drawdown_series()` + new duration calc | ✅ Yes (partially) |
| Days above cost basis | Snapshots' `position_value > cost_basis` | Simple iteration | ✅ Yes (no new queries) |
| Volatility | `price_history` table (30 trailing days) | `portfolio_stats.compute_annualized_volatility(daily_returns)` | ✅ Yes |
| Avg cost vs current price | `snapshots[-1].avg_cost_per_share` + `useLivePrice(symbol)` | `avg_cost_per_share` is in snapshots; `current_price` is NOT — use existing `useLivePrice` hook from parent | ⚠ `current_price` not in schema; must use live price hook |
| Gain/Loss $ + % combined | `total_return` + `total_return_pct` | Direct fields | ✅ Yes (already computed) |

**What's truly new:** only `_compute_monthly_returns()` and `_compute_drawdown_duration()` — both are ~20-line helpers.

**Known gap:** `total_return + total_dividends` = unrealized P&L + dividends only. Realized gains from sells during the period are not included. For a true total economic return (what brokerage statements show), realized gains need to be tracked. This is acceptable for v1 — the user's mockup treats "Price loss" as the unrealized component, which matches this design.

### 12.4 Schema Changes

**File:** `backend/schemas_portfolio.py`

```python
class MonthlyReturnSummary(BaseModel):
    month: str          # "Jan 2026"
    return_pct: float   # 4.2 or -18.7 (not percentage points — actual % return)

class DrawdownInfo(BaseModel):
    max_drawdown_pct: float              # -44.1
    max_drawdown_peak_date: Optional[str] = None
    max_drawdown_trough_date: Optional[str] = None
    longest_drawdown_weeks: float = 0   # 14.0
    longest_drawdown_start: Optional[str] = None
    longest_drawdown_end: Optional[str] = None  # None if ongoing

class DaysAboveCostBasis(BaseModel):
    above_count: int     # 31
    total_days: int      # 213
    start_date: str      # "2025-11-01" (first purchase date)

class HoldingPerformanceResponse(BaseModel):
    success: bool = True
    symbol: str
    period: str
    snapshots: List[HoldingPerformanceSnapshot] = []
    total_return: float = 0
    total_return_pct: float = 0
    total_dividends: float = 0
    total_dividends_pct: float = 0
    # ── NEW ──
    combined_return: float = 0                       # total_return + total_dividends
    best_month: Optional[MonthlyReturnSummary] = None
    worst_month: Optional[MonthlyReturnSummary] = None
    drawdown: Optional[DrawdownInfo] = None
    days_above_cost_basis: Optional[DaysAboveCostBasis] = None
    volatility_30d: float = 0                        # annualized, e.g. 28.4
    # ──────────
    error: Optional[str] = None
```

**Note:** `current_price` is intentionally NOT added to the schema. The frontend reuses the existing `useLivePrice(symbol)` hook instead — it's already called in the `AnalysisPage` parent component and provides real-time price data. Keeps the backend response focused on historical performance data.

### 12.5 Backend Implementation

**File:** `backend/application/services/portfolio_service.py`

In `get_holding_performance()`, after snapshots are computed (line ~2073), insert:

```python
# ── Compute summary metrics ─────────────────────────────────────
summary = self._compute_performance_summary(
    snapshots=result["snapshots"],
    symbol=symbol,
    user_id=user_id,
    total_return=result["total_return"],
    total_dividends=result["total_dividends"],
)
result.update(summary)
```

New helper methods:

```python
def _compute_performance_summary(self, snapshots, symbol, user_id, total_return, total_dividends):
    """Compute all summary metrics from computed snapshots."""
    import numpy as np
    from backend.shared.portfolio_stats import (
        compute_max_drawdown,
        compute_drawdown_series,
        compute_annualized_volatility,
        compute_daily_returns,
    )

    values = np.array([s["position_value"] for s in snapshots], dtype=float)
    cost_bases = np.array([s["cost_basis"] for s in snapshots], dtype=float)

    # 1. Combined return
    combined_return = round(total_return + total_dividends, 2)

    # 2. Monthly returns
    # ⚠ Only meaningful when snapshot interval ≤ 1 week (periods ≤ 1Y).
    #    For "ALL"/"5Y" snapshots are monthly → 1 data point per month → 0% return.
    #    Frontend uses showMonthlyMetrics flag to hide these for long periods.
    monthly = self._compute_monthly_returns(snapshots)
    best_month = max(monthly, key=lambda m: m["return_pct"]) if monthly else None
    worst_month = min(monthly, key=lambda m: m["return_pct"]) if monthly else None

    # 3. Drawdown
    dd_value, dd_pct, peak_idx, trough_idx = compute_max_drawdown(values)
    dd_series = compute_drawdown_series(values)
    dates = [s["date"] for s in snapshots]
    longest_dd = self._compute_longest_drawdown(dd_series, dates)

    # 4. Days above cost basis
    above = 0
    total_days_with_cost = 0
    for v, c in zip(values, cost_bases):
        if c > 0:
            total_days_with_cost += 1
            if v > c:
                above += 1
    first_purchase = dates[0] if dates and cost_bases[0] > 0 else None

    # 5. Volatility (30d annualized)
    vol = self._compute_30d_volatility(user_id, symbol)

    return {
        "combined_return": combined_return,
        "best_month": best_month,
        "worst_month": worst_month,
        "drawdown": {
            "max_drawdown_pct": round(float(dd_pct * 100), 1),
            "max_drawdown_peak_date": dates[peak_idx] if peak_idx < len(dates) else None,
            "max_drawdown_trough_date": dates[trough_idx] if trough_idx < len(dates) else None,
            "longest_drawdown_weeks": longest_dd["weeks"],
            "longest_drawdown_start": longest_dd["start_date"],
            "longest_drawdown_end": longest_dd["end_date"],
        },
        "days_above_cost_basis": {
            "above_count": above,
            "total_days": total_days_with_cost,
            "start_date": first_purchase,
        },
        "volatility_30d": round(float(vol * 100), 1),
    }


def _compute_monthly_returns(self, snapshots):
    """Group position_value by calendar month and compute % return per month.
    NOTE: Requires at least 2 snapshots per month. For periods with monthly
    snapshot granularity (ALL, 5Y), the result will be empty because each
    month has only 1 data point. The frontend hides monthly metrics for
    those periods via showMonthlyMetrics."""
    from collections import OrderedDict
    monthly = OrderedDict()
    for s in snapshots:
        dt = date.fromisoformat(s["date"])
        key = (dt.year, dt.month)
        if key not in monthly:
            monthly[key] = {"first_value": None, "last_value": None}
        if monthly[key]["first_value"] is None:
            monthly[key]["first_value"] = s["position_value"]
        monthly[key]["last_value"] = s["position_value"]

    results = []
    for (year, month), v in monthly.items():
        if v["first_value"] and v["first_value"] > 0:
            ret = (v["last_value"] - v["first_value"]) / v["first_value"] * 100
            label = date(year, month, 1).strftime("%b %Y")
            results.append({"month": label, "return_pct": round(ret, 1)})
    return results


def _compute_longest_drawdown(self, dd_series, dates):
    """Find the longest drawdown in weeks from drawdown series."""
    if len(dd_series) < 2:
        return {"weeks": 0, "start_date": None, "end_date": None}

    in_drawdown = False
    start_idx = 0
    longest_weeks = 0
    longest_start = None
    longest_end = None

    for i, dd in enumerate(dd_series):
        if dd < 0 and not in_drawdown:
            in_drawdown = True
            start_idx = i
        elif dd == 0 and in_drawdown:
            in_drawdown = False
            weeks = (date.fromisoformat(dates[i]) - date.fromisoformat(dates[start_idx])).days / 7
            if weeks > longest_weeks:
                longest_weeks = weeks
                longest_start = dates[start_idx]
                longest_end = dates[i]

    # Ongoing drawdown
    if in_drawdown:
        weeks = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[start_idx])).days / 7
        if weeks > longest_weeks:
            longest_weeks = weeks
            longest_start = dates[start_idx]
            longest_end = None

    return {
        "weeks": round(longest_weeks, 1),
        "start_date": longest_start,
        "end_date": longest_end,
    }


def _compute_30d_volatility(self, user_id, symbol):
    """Fetch 30 trailing days of price_history and compute annualized vol."""
    end = date.today()
    start = end - timedelta(days=60)  # 60-day window to ensure 30 trading days
    prices = self.portfolio_repo.get_price_history_for_symbol(
        user_id, symbol, start.isoformat(), end.isoformat()
    )
    if len(prices) < 10:
        return 0.0
    close_values = np.array([float(p["close_price"]) for p in prices], dtype=float)
    if len(close_values) < 2:
        return 0.0
    daily_ret = compute_daily_returns(close_values)
    if len(daily_ret) < 2:
        return 0.0
    # Use last 30 trading days
    last_30 = daily_ret[-30:] if len(daily_ret) >= 30 else daily_ret
    vol = compute_annualized_volatility(last_30, periods_per_year=252)
    return vol
```

### 12.6 Frontend Implementation

**File:** `web/src/features/analysis/components/stock-performance-panel.tsx`

**Approach — Replace existing 5 metric cards with the summary card (recommended):**
- The existing 5 cards (Total Value, Total Invested, Gain/Loss $, Gain/Loss %, Dividends) are replaced by the new unified card
- Gain/Loss $ and % are **combined** into a single headline — matches brokerage statement convention
- Avg cost vs current price uses `useLivePrice()` hook (already available) — no backend schema change for `current_price`
- Monthly returns are only shown for periods ≤1Y; hidden with fallback text for "ALL"/"5Y" where snapshot granularity is too coarse
- Net result: **1 card replaces 5**, adds 8 new metrics, same vertical space, zero new endpoints, zero new hooks

**Component structure:**
```tsx
function PerformanceSummaryCard({
  perf,
  symbol,
}: {
  perf: HoldingPerformanceResponse;
  symbol: string;
}) {
  const { price: livePrice } = useLivePrice(symbol);
  const lastSnapshot = perf.snapshots?.[perf.snapshots.length - 1];
  const avgCost = lastSnapshot?.avg_cost_per_share;
  const costVsPriceDiff = avgCost && livePrice
    ? ((livePrice - avgCost) / avgCost * 100).toFixed(1)
    : null;

  const isLongPeriod = perf.period === 'ALL' || perf.period === '5Y';
  const showMonthlyMetrics = !isLongPeriod;

  return (
    <div className="glass-panel rounded-lg p-5 space-y-5">

      {/* Header: Combined Gain/Loss */}
      <div className="flex items-baseline gap-3">
        <span className="text-xs font-bold text-white/40 uppercase tracking-wider">Gain/Loss</span>
        <span className={cn('text-2xl font-black tracking-tight', perf.combined_return >= 0 ? 'text-green-400' : 'text-red-400')}>
          {perf.combined_return >= 0 ? '+' : ''}${Math.abs(perf.combined_return).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className={cn('text-lg font-bold', perf.total_return_pct >= 0 ? 'text-green-400/80' : 'text-red-400/80')}>
          {perf.total_return_pct >= 0 ? '+' : ''}{perf.total_return_pct.toFixed(2)}%
        </span>
      </div>

      {/* Row 1: Return Attribution (2 columns) */}
      <div className="grid grid-cols-2 gap-4">
        <AttributionBox
          label={perf.total_return >= 0 ? 'Price Gain' : 'Price Loss'}
          value={`${perf.total_return >= 0 ? '+' : ''}$${Math.abs(perf.total_return).toLocaleString()}`}
          subtitle="from price movement"
          isPositive={perf.total_return >= 0}
        />
        <AttributionBox
          label="Dividends"
          value={`+$${perf.total_dividends.toLocaleString()}`}
          subtitle="received to date"
          isPositive={true}
        />
      </div>

      {/* Context line: Avg Cost vs Current Price */}
      <div className="flex items-center gap-2 px-1 py-1.5 border-t border-white/5 text-xs">
        <span className="text-white/40 font-medium">Avg Cost</span>
        <span className="text-white font-bold">${avgCost?.toFixed(2) ?? '—'}</span>
        <span className="text-white/20">→</span>
        <span className="text-white/40 font-medium">Last Price</span>
        <span className="text-white font-bold">${livePrice?.toFixed(2) ?? '—'}</span>
        {costVsPriceDiff != null && (
          <>
            <span className="text-white/20 mx-1">·</span>
            <span className={cn('font-bold', Number(costVsPriceDiff) >= 0 ? 'text-green-400' : 'text-red-400')}>
              {Number(costVsPriceDiff) >= 0 ? '+' : ''}{costVsPriceDiff}%
            </span>
          </>
        )}
      </div>

      {/* Row 2: 4-column Risk & Performance Quadrants */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {showMonthlyMetrics ? (
          <>
            <StatCol label="Best month" value={perf.best_month?.month} sub={perf.best_month?.return_pct} isPct positive />
            <StatCol label="Worst month" value={perf.worst_month?.month} sub={perf.worst_month?.return_pct} isPct negative />
          </>
        ) : (
          <>
            <StatCol label="Best period" value="—" sub="unavailable for ALL" />
            <StatCol label="Worst period" value="—" sub="unavailable for ALL" />
          </>
        )}
        <StatCol label="Max drawdown"
          value={`${perf.drawdown?.max_drawdown_pct}%`}
          sub={perf.drawdown?.max_drawdown_peak_date ? `${perf.drawdown.max_drawdown_peak_date} → ${perf.drawdown.max_drawdown_trough_date || 'now'}` : '—'}
          isPct negative />
        <StatCol label="Volatility (30d)"
          value={`${perf.volatility_30d}%`}
          sub="annualized" />
      </div>

      {/* Row 3: 2-column Extended Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ExtendedStat
          label="Days above cost basis"
          main={`Since ${perf.days_above_cost_basis?.start_date ? new Date(perf.days_above_cost_basis.start_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}`}
          value={`${perf.days_above_cost_basis?.above_count ?? 0} of ${perf.days_above_cost_basis?.total_days ?? 0} days`}
        />
        <ExtendedStat
          label="Longest drawdown"
          main={`${perf.drawdown?.longest_drawdown_start ?? '—'} → ${perf.drawdown?.longest_drawdown_end ?? 'now'}`}
          value={`${perf.drawdown?.longest_drawdown_weeks ?? 0} weeks${perf.drawdown?.longest_drawdown_end == null ? ' · Ongoing' : ''}`}
        />
      </div>

    </div>
  );
}
```

**Key frontend patterns:**
| Pattern | Why |
|---------|-----|
| `useLivePrice(symbol)` for current price | Reuses existing hook. No backend change needed. Price updates live when SSE pushes new data. |
| `showMonthlyMetrics` flag | Hides best/worst month for ALL/5Y periods where snapshot granularity is too coarse. Shows "unavailable" fallback. |
| `combined_return` as headline | Single prominent number — no redundancy. Attribution below is the decomposition. |
| `Avg Cost → Last Price` inline | Saves a full card row. Arrow visual (`→`) implies directionality. Color on % diff only. |
| `4-column → 2-column` responsive grid | Best/worst month + drawdown + vol in a tight grid. Extended stats below in wider cards. |

### 12.7 Tab Overflow Fix

**Root cause:** `web/src/app/(authenticated)/analysis/[symbol]/page.tsx:203`

```tsx
<div className="glass-segmented overflow-x-auto no-scrollbar w-full">
```

- `BASE_TABS` has 9 items
- When `isHeld=true`, "Performance" is **spliced at index 5**, making 10 tabs
- On screens narrower than ~1100px, the tabs overflow the container's `w-full`
- `no-scrollbar` hides the scrollbar **and the overflow** — last tab(s) are clipped with no user feedback

**Fix — `page.tsx`:**

```tsx
<div className="glass-segmented overflow-x-auto w-full
                scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10">
```

Alternatively, add custom CSS in `globals.css`:

```css
.glass-segmented {
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.15) transparent;
}
.glass-segmented::-webkit-scrollbar {
  height: 4px;
}
.glass-segmented::-webkit-scrollbar-track {
  background: transparent;
}
.glass-segmented::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.15);
  border-radius: 99px;
}
```

This gives a **subtle, themed thin scrollbar** — visible only when the tabs overflow. On Windows it's a thin bar, on Mac it auto-hides after scrolling. The glass-segmented container keeps its exact current appearance — only the scroll indicator is added.

### 12.8 Files Changed Summary

| File | Change Type | Lines Changed |
|------|------------|---------------|
| `backend/schemas_portfolio.py` | Add 3 new models + update `HoldingPerformanceResponse` | ~25 new lines |
| `backend/application/services/portfolio_service.py` | Add `_compute_performance_summary()` + 3 helpers + call in `get_holding_performance()` | ~120 new lines |
| `backend/infrastructure/repositories/portfolio_repository.py` | Optional: `get_price_history_for_symbol()` if not exists | ~15 lines |
| `web/src/features/portfolio/types/portfolio.types.ts` | New frontend types for summary fields (MonthlyReturnSummary, DrawdownInfo, DaysAboveCostBasis, HoldingPerformanceResponse fields) | ~30 lines |
| `web/src/features/analysis/components/stock-performance-panel.tsx` | Add `PerformanceSummaryCard` component (inline or separate), replace top 5 metric cards, import `useLivePrice` | ~130 lines |
| `web/src/app/(authenticated)/analysis/[symbol]/page.tsx` | Remove `no-scrollbar` from tab container | 1 line |
| `web/src/app/globals.css` | Add `.glass-segmented` thin scrollbar styles | ~10 lines |

**Total:** ~295 lines added/modified across 6 files, zero new endpoints, zero new hooks, zero new queries.

### 12.9 Verification

After implementation, verify:

1. **Backend tests:** Existing test suite passes (10 tests), plus new tests for `_compute_monthly_returns()`, `_compute_longest_drawdown()`, `_compute_30d_volatility()`
2. **Frontend tests:** Existing 10 HoldingsTab tests pass, new tests for `PerformanceSummaryCard` rendering with mock data
3. **Tab overflow:** Open analysis page for a held stock at 1024px width — all 10 tabs visible or scrollable with thin scrollbar
4. **Empty states:** New summary fields gracefully handle missing data (no monthly data, no drawdown, zero volatility)
