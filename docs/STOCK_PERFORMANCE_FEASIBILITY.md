# Stock Performance Tab — Feasibility Analysis

> **Date:** 2026-06-03
> **Scope:** Add clickable navigation from Portfolio holdings to `/analysis/{symbol}`, and introduce a new "Performance" tab on the analysis page that shows portfolio-specific metrics for stocks the user holds.
> **Methodology:** Trace each requirement back to existing code, identify reuse opportunities, and document the gaps.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Requirement 1 — Click-to-Navigate from Portfolio to Analysis](#3-requirement-1--click-to-navigate-from-portfolio-to-analysis)
4. [Requirement 2 — New Performance Tab on Analysis Page](#4-requirement-2--new-performance-tab-on-analysis-page)
5. [API Design](#5-api-design)
6. [Database Schema](#6-database-schema)
7. [Frontend State & Caching](#7-frontend-state--caching)
8. [Reuse Opportunities](#8-reuse-opportunities)
9. [Implementation Effort Estimate](#9-implementation-effort-estimate)
10. [Recommended Phasing](#10-recommended-phasing)

---

## 1. Executive Summary

**Verdict: FEASIBLE** — roughly 60% of the required infrastructure already exists. The navigation pattern from Watchlist → Analysis is well-established and directly replicable. The portfolio backend already has FIFO-based cost basis tracking and per-holding P&L data. The frontend already has Recharts-based performance charts and dividend displays that can be adapted.

**What exists today (reusable):**
- Click-to-navigate pattern in `StockCard`/`StockListRow` → `/analysis/{symbol}` — direct copy for Portfolio holdings
- `OverviewTab` summary cards pattern (Total Value, Gain/Loss, Dividends) — reusable component structure
- `PortfolioPerformanceChart` — Recharts `ComposedChart` with benchmark overlay — directly adaptable for single-stock
- `BenchmarkSelector` UI component — reusable as-is
- `useLivePrice(symbol)` — already used by analysis page, provides real-time price
- Price history endpoint (`/stocks/{symbol}/price-history`) — provides OHLCV for charting
- `DividendPanel` on analysis page — already shows dividend data for any stock
- `StockVsIndexPanel` on analysis page — already shows normalized price vs benchmarks
- Portfolio holdings endpoint returns `unrealized_gain_loss`, `unrealized_gain_loss_pct`, `total_cost`, `current_value` — the core performance metrics for a holding

**What must be built:**
1. **HoldingsTab/SegmentDrillDown click handler** — add `router.push(\`/analysis/${h.symbol}\`)` to holding rows
2. **New Performance tab** on analysis page (appears conditionally when stock is in user's portfolio)
3. **New backend endpoint** `GET /portfolio/holdings/{symbol}/performance` — returns per-stock performance summary and time-series
4. **New frontend types** for stock-level performance response
5. **Recharts-based component** `StockPerformancePanel` — adapted from `PortfolioPerformanceChart`

---

## 2. Architecture Walkthrough

### 2.1 Existing Navigation Pattern (Watchlist → Analysis)

```
StockCard.tsx                          StockListRow.tsx
└─ onClick → router.push(              └─ "Analyse" button → router.push(
     /analysis/${stock.symbol})              /analysis/${stock.symbol})
                │
                ▼
         analysis/[symbol]/page.tsx
              ┌─ TOP_TABS (9 tabs)
              │  ├─ intrinsic, health, moat, dividend
              │  ├─ comparison, technical, risk
              │  ├─ investors, others
              │  └─ ← NEW: performance (conditional)
              │
              └─ useLivePrice(symbol)
                 prefetchAllValuations(symbol)
```

### 2.2 Portfolio Holding Row (current state)

```
HoldingsTab.tsx / SegmentDrillDown.tsx
   └─ holding row: <div key={symbol}>
        ├─ icon + symbol + shares
        ├─ current_value + weight %
        └─ unrealized_gain_loss_pct
        └─ ← NO click handler (this is the gap)
```

### 2.3 Target Architecture

```
portfolio/ page
   └─ PortfolioTabShell
        └─ HoldingsTab / SegmentDrillDown
             └─ holding row: onClick → router.push(/analysis/{symbol}?from=portfolio)

analysis/[symbol]/page.tsx
   ├─ TOP_TABS (9 existing + 1 new conditional)
   │    └─ "Performance" tab (shown only when stock is in user's portfolio)
   │
   └─ [new] StockPerformancePanel
        ├─ Summary Cards (Total Value, Gain/Loss, Gain/Loss %, Dividends)
        ├─ Performance Chart (Area + benchmark overlay, adapted from PortfolioPerformanceChart)
        └─ Dividend History Bar Chart (Recharts BarChart)
```

---

## 3. Requirement 1 — Click-to-Navigate from Portfolio to Analysis

### 3.1 Files to Modify

| File | Change |
|------|--------|
| `web/src/features/portfolio/components/HoldingsTab.tsx` | Add `router.push` to holding row `<div>` |
| `web/src/features/portfolio/components/SegmentDrillDown.tsx` | Add `router.push` to holding row `<div>` |

### 3.2 Implementation

In both `HoldingsTab.tsx` (line ~123) and `SegmentDrillDown.tsx` (line ~42), wrapping the holding row `<div>` with an `onClick`:

```tsx
import { useRouter } from 'next/navigation';

const router = useRouter();

// Inside the holding row map:
<div
  key={`${h.symbol}-${h.holding_id}`}
  className="glass-panel rounded-lg p-4 flex items-center justify-between cursor-pointer hover:bg-white/[0.04] transition-colors"
  onClick={() => router.push(`/analysis/${h.symbol}`)}
  role="button"
  tabIndex={0}
  onKeyDown={(e) => { if (e.key === 'Enter') router.push(`/analysis/${h.symbol}`); }}
>
```

**Effort:** ~30 min. Straightforward — same pattern as `StockCard.tsx:83`.

---

## 4. Requirement 2 — New Performance Tab on Analysis Page

### 4.1 Conditional Tab Logic

The Performance tab must only appear when the logged-in user holds the stock in their portfolio. Two approaches:

| Approach | Pros | Cons |
|----------|------|------|
| **A. API check** — new lightweight endpoint `GET /portfolio/holdings/{symbol}/exists` | Clean separation, no data leak | Extra API call on analysis page load |
| **B. Client-side lookup** — prefetch all holdings on analysis page mount and check locally | No extra endpoint, fast | Must prefetch all holdings on every analysis page visit |

**Recommendation: Approach A** — lightweight boolean endpoint, integrated into the analysis page's existing prefetch pattern.

### 4.2 New Tab Definition

In `web/src/app/(authenticated)/analysis/[symbol]/page.tsx`:

```typescript
const [isHeld, setIsHeld] = useState(false);

useEffect(() => {
  fetch(`/api/proxy/portfolio/holdings/${upperSymbol}/exists`)
    .then(r => r.json())
    .then(d => setIsHeld(d.held));
}, [upperSymbol]);
```

Extend `TOP_TABS` conditionally:

```typescript
const TOP_TABS = useMemo(() => {
  const tabs = [ ...existingTabs ];
  if (isHeld) {
    tabs.splice(5, 0, { id: "performance", label: "Performance", icon: TrendingUp });
  }
  return tabs;
}, [isHeld]);
```

### 4.3 StockPerformancePanel Component

**File:** `web/src/features/analysis/components/stock-performance-panel.tsx`

#### 4.3.1 Summary Cards

Replicating the `OverviewTab` card pattern (`web/src/features/portfolio/components/OverviewTab.tsx:40-75`):

| Metric | Source | Formula |
|--------|--------|---------|
| Total Value | `holding.current_value` | `quantity × current_price` |
| Total Gain/Loss | `holding.unrealized_gain_loss` | Already computed by portfolio_service |
| Gain/Loss % | `holding.unrealized_gain_loss_pct` | Already computed by portfolio_service |
| Total Dividends | `SUM(portfolio_dividends.amount)` WHERE symbol = stock | Aggregate from portfolio_dividends table |

##### Data Structure

```typescript
interface StockPerformanceOverview {
  symbol: string;
  total_value: number;
  total_cost_basis: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  total_dividends: number;
  total_quantity: number;
  avg_cost_per_share: number;
  accounts: { account_id: number; account_name: string; quantity: number; value: number; gain_loss: number }[];
}
```

#### 4.3.2 Performance Chart (Stock vs Benchmark)

**File:** `web/src/features/analysis/components/stock-performance-panel.tsx` (continued)

Adapted from `PortfolioPerformanceChart.tsx` (`web/src/features/portfolio/components/PortfolioPerformanceChart.tsx`).
Key changes vs portfolio version:

| Aspect | Portfolio Chart | Stock Chart |
|--------|----------------|-------------|
| Data source | `usePortfolioPerformance(period, accountIds)` via `portfolio_performance` table | Reconstructed from `price_history` + FIFO lots, normalized to cost basis |
| Y-axis label | Dollar value | Dollar value (total position value) |
| Benchmark | Optional overlay via `BenchmarkSelector` | Same — reuse `BenchmarkSelector` |
| Net Deposits Area | Shows cumulative deposits | **Not applicable** (single stock) — replace with cost basis line |
| Period selector | `TimePeriodSelector` | Same — reuse |

##### Backend Data Source

The portfolio service already has a `get_portfolio_performance` method (line 1498) that processes FIFO lots for the full portfolio. For a single stock:

**New endpoint:** `GET /portfolio/holdings/{symbol}/performance?period=1Y`

The service would:
1. Get all transactions for the user's accounts for this symbol
2. Run FIFO lot tracking (same logic as `portfolio_service.py:1498-1779`)
3. Use `price_history` to value holdings at each snapshot date
4. Return time-series of position value + cost basis

Response schema:
```typescript
interface StockPerformanceResponse {
  symbol: string;
  period: string;
  snapshots: {
    date: string;
    position_value: number;   // quantity_at_time × close_price
    cost_basis: number;        // total cost of remaining lots
    cumulative_invested: number;  // total money put in (buys - sells)
  }[];
  total_return: number;
  total_return_pct: number;
  total_dividends: number;
  total_dividends_pct: number;  // dividends / total_invested
}
```

##### Chart Implementation

```tsx
<ComposedChart data={chartData}>
  <Area dataKey="position_value" stroke="#818cf8" fill="#818cf8" fillOpacity={0.15} name="Position Value" />
  <Line dataKey="cost_basis" stroke="#34d399" strokeWidth={2} strokeDasharray="4 2" name="Cost Basis" dot={false} />
  {selectedBenchmarks.map((sym, i) => (
    <Line key={sym} dataKey={sym} stroke={BENCHMARK_COLORS[sym]} strokeWidth={2} strokeDasharray="6 3" name={sym} dot={false} />
  ))}
</ComposedChart>
```

**Benchmark comparison** reuses the existing `BenchmarkCompareResponse` endpoint (`GET /portfolio/performance/compare`), but replaces the portfolio series with the single-stock value series. A simpler approach: compute benchmark data client-side by fetching `GET /analysis/{symbol}/stock-vs-index?benchmarks=SPY,QQQ` — this already exists and returns normalized price data.

#### 4.3.3 Dividend Bar Chart (Historical)

**Data source:** Two options:

| Option | Source | Pros | Cons |
|--------|--------|------|------|
| A. Existing `GET /analysis/{symbol}/dividend` | Returns yield_history[] + overview | Already exists, no new endpoint | Yield data not raw dividend amounts |
| B. New portfolio-based endpoint | Aggregate from `portfolio_dividends` table | Actual amounts user received | New endpoint needed |

**Recommendation: Combination** — Use the analysis dividend endpoint for company-level data (dividend per share history) and the portfolio dividend table for amounts received.

For the bar chart:

```tsx
interface DividendBarPoint {
  year: number;
  quarter: string;    // "Q1 2024"
  amount: number;     // total dividends received in that period
  amount_per_share: number;
}
```

Recharts `BarChart`:

```tsx
<BarChart data={dividendData}>
  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
  <XAxis dataKey="quarter" />
  <YAxis />
  <Tooltip />
  <Bar dataKey="amount" fill="#34d399" name="Dividends Received" radius={[4, 4, 0, 0]} />
</BarChart>
```

---

## 5. API Design

### 5.1 New Endpoint: Stock Existence Check

```python
# backend/api/portfolio.py

@router.get("/portfolio/holdings/{symbol}/exists")
@limiter.limit("60/minute")
async def check_holding_exists(
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    """Check if the user holds this stock in their portfolio."""
    auth_id = user["sub"]
    db_user_id = _resolve_db_user_id(auth_id)
    service = _get_portfolio_service()
    held = await service.check_holding_exists(db_user_id, symbol)
    return {"symbol": symbol.upper(), "held": held}
```

### 5.2 New Endpoint: Stock Performance

```python
# backend/api/portfolio.py

@router.get("/portfolio/holdings/{symbol}/performance")
@limiter.limit("20/minute")
async def get_holding_performance(
    symbol: str,
    period: str = "1Y",
    user=Depends(get_current_user_dep),
) -> dict:
    """Time-series performance for a single stock in user's portfolio."""
    auth_id = user["sub"]
    db_user_id = _resolve_db_user_id(auth_id)
    service = _get_portfolio_service()
    return await service.get_holding_performance(db_user_id, symbol, period)
```

### 5.3 New Service Method

In `portfolio_service.py`:

```python
async def check_holding_exists(self, user_id: int, symbol: str) -> bool:
    """Check if user holds a position in the given symbol."""
    holdings = self.portfolio_repo.get_user_all_holdings(user_id)
    return any(h.get("symbol", "").upper() == symbol.upper() for h in holdings)

async def get_holding_performance(self, user_id: int, symbol: str, period: str) -> dict:
    """
    Compute time-series performance for a single stock.
    Leverages existing FIFO lot logic from get_portfolio_performance()
    but filtered to a single symbol.
    """
    # 1. Get user accounts
    # 2. Get transactions for this symbol across all accounts
    # 3. Apply FIFO lot tracking (same engine as get_portfolio_performance)
    # 4. Fetch price_history for valuation at each snapshot
    # 5. Return snapshots + summary
```

This method can extract the FIFO logic from `get_portfolio_performance` into a shared helper:

```python
def _compute_fifo_snapshots(
    self, txns: List[Dict], price_map: Dict[str, Dict[str, float]],
    start_date: date, end_date: date, step: timedelta
) -> List[Dict]:
    """Shared FIFO snapshot engine — used by both portfolio and single-stock."""
    # ... existing logic from lines 1595-1779 extracted here
```

### 5.4 Pydantic Schemas

```python
# schemas_portfolio.py (additions)

class HoldingPerformanceSnapshot(BaseModel):
    date: str
    position_value: float
    cost_basis: float
    cumulative_invested: float

class HoldingPerformanceResponse(BaseModel):
    success: bool
    symbol: str
    period: str
    snapshots: List[HoldingPerformanceSnapshot]
    total_return: float
    total_return_pct: float
    total_dividends: float
    total_dividends_pct: float
    error: Optional[str] = None

class HoldingExistsResponse(BaseModel):
    symbol: str
    held: bool
```

---

## 6. Database Schema

### 6.1 Existing Tables — No New Tables Required

| Table | Usage | Status |
|-------|-------|--------|
| `portfolio_holdings` | Current position data (quantity, avg_cost, current_value, unrealized_gain_loss) | **Exists** |
| `portfolio_transactions` | All trades for FIFO lot tracking | **Exists** |
| `portfolio_dividends` | Dividend payments received per symbol | **Exists** |
| `portfolio_performance` | Portfolio-level daily snapshots (not per-stock) | **Exists** (not directly used) |
| `price_history` | OHLCV for valuation at snapshot dates | **Exists** |
| `companies` | Symbol → company_id resolution | **Exists** |
| `dividend_history` | Company-level dividend per share history (for chart) | **Exists** |

The single-stock performance is computed dynamically from `portfolio_transactions` + `price_history` — no additional storage needed.

### 6.2 Data Dependency Diagram

```
portfolio_transactions (BUY/SELL for symbol)
         │
         ▼
    FIFO Lot Engine ──► lots[] with quantity + cost_per_share
         │
         ▼
price_history ──► position_value = sum(lot.qty) × close_price
         │
         ▼
    snapshot { date, position_value, cost_basis, cumulative_invested }
```

---

## 7. Frontend State & Caching

### 7.1 Query Key Additions

```typescript
// lib/query-keys.ts (additions)

holdingExists: (symbol: string) =>
  ["portfolio", "holding", "exists", symbol.toUpperCase()] as const,
holdingPerformance: (symbol: string, period: string) =>
  ["portfolio", "holding", "performance", symbol.toUpperCase(), period] as const,
```

### 7.2 New React Query Hooks

```typescript
// hooks/usePortfolio.ts (additions)

export function useHoldingExists(symbol: string) {
  const { portfolioService } = useServices();
  return useQuery({
    queryKey: QK.holdingExists(symbol),
    queryFn: () => portfolioService.checkHoldingExists(symbol),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
  });
}

export function useHoldingPerformance(symbol: string, period: string = "1Y") {
  const { portfolioService } = useServices();
  return useQuery({
    queryKey: QK.holdingPerformance(symbol, period),
    queryFn: () => portfolioService.getHoldingPerformance(symbol, period),
    staleTime: STALE.PORTFOLIO,
    gcTime: GC.PORTFOLIO,
  });
}
```

### 7.3 PortfolioService Additions

```typescript
// services/portfolio.service.ts (additions)

async checkHoldingExists(symbol: string): Promise<{ symbol: string; held: boolean }> {
  const res = await this.api.get(`/portfolio/holdings/${symbol}/exists`);
  return res.data;
}

async getHoldingPerformance(symbol: string, period: string = "1Y"): Promise<HoldingPerformanceResponse> {
  const res = await this.api.get(`/portfolio/holdings/${symbol}/performance`, { params: { period } });
  return res.data;
}
```

---

## 8. Reuse Opportunities

### 8.1 Directly Reusable Components

| Component | Source | Use Case |
|-----------|--------|----------|
| `BenchmarkSelector` | `web/src/components/ui/benchmark-selector.tsx` | Benchmark selection in stock performance chart |
| `TimePeriodSelector` | `web/src/features/portfolio/components/TimePeriodSelector.tsx` | Period filter for stock chart |
| `Metric` (shared-ui) | `web/src/features/analysis/components/shared-ui.tsx` | Summary metric display cards |
| `BENCHMARK_COLORS` | `web/src/lib/colors.ts` | Consistent chart colors |
| `SectionHeader` | `web/src/features/analysis/components/shared-ui.tsx` | Panel section headers |

### 8.2 Reusable Patterns

| Pattern | Source | Adaptation |
|---------|--------|------------|
| Summary cards grid | `OverviewTab.tsx:40-75` | Same 4-card grid, different data source |
| Performance chart with benchmarks | `PortfolioPerformanceChart.tsx` | Replace `portfolio` area with `position_value`, replace `netDeposits` with `cost_basis` line |
| Dividend bar chart | `DividendsTab.tsx` monthly summary | Switch from list to bar chart using Recharts |
| Click-to-navigate | `StockCard.tsx:83` | Copy the `router.push` + `cursor-pointer` pattern |
| Conditional tab visibility | — | New pattern (no existing conditional tabs in analysis page) |

### 8.3 Shared Code Extraction

The FIFO lot tracking logic in `portfolio_service.py:1498-1779` should be extracted into a shared helper `_compute_fifo_snapshots` to avoid duplication between portfolio and single-stock performance.

---

## 9. Implementation Effort Estimate

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | Add click handler to HoldingsTab rows | `HoldingsTab.tsx` | 0.5 hr |
| 2 | Add click handler to SegmentDrillDown rows | `SegmentDrillDown.tsx` | 0.5 hr |
| 3 | Backend: holding exists endpoint | `portfolio.py`, `portfolio_service.py` | 1 hr |
| 4 | Backend: single-stock performance endpoint + FIFO refactor | `portfolio.py`, `portfolio_service.py`, `schemas_portfolio.py` | 4 hr |
| 5 | Frontend: performance types + service methods | `portfolio.types.ts`, `portfolio.service.ts` | 1 hr |
| 6 | Frontend: query keys + hooks | `query-keys.ts`, `usePortfolio.ts` | 0.5 hr |
| 7 | Frontend: conditional tab on analysis page | `analysis/[symbol]/page.tsx` | 1 hr |
| 8 | Frontend: StockPerformancePanel (summary cards + chart) | `stock-performance-panel.tsx` (new) | 4 hr |
| 9 | Frontend: dividend bar chart in panel | `stock-performance-panel.tsx` | 2 hr |
| 10 | Integration testing + edge cases | — | 2 hr |
| **Total** | | | **~16 hr** |

---

## 10. Recommended Phasing

### Phase 1 (Day 1) — Navigation + Conditional Tab

| Deliverable | Description |
|-------------|-------------|
| HoldingsTab click handler | Route to `/analysis/{symbol}` |
| SegmentDrillDown click handler | Route to `/analysis/{symbol}` |
| Holding exists API endpoint | `GET /portfolio/holdings/{symbol}/exists` |
| Analysis page conditional tab | "Performance" tab appears when stock is held |
| Placeholder panel | "Coming soon" state for tab content |

**Verification:** Click a holding in Portfolio → lands on analysis page → sees "Performance" tab → sees placeholder.

### Phase 2 (Days 2-3) — Backend Data + Frontend Display

| Deliverable | Description |
|-------------|-------------|
| FIFO refactor | Extract shared helper from `get_portfolio_performance` |
| Holding performance API | `GET /portfolio/holdings/{symbol}/performance` |
| Pydantic schemas | `HoldingPerformanceResponse`, `HoldingPerformanceSnapshot` |
| Frontend types + hooks | `useHoldingPerformance`, `useHoldingExists` |
| Summary cards | Total Value, Gain/Loss, Gain/Loss %, Dividends |

**Verification:** Performance tab shows correct numbers matching Holdings tab values.

### Phase 3 (Days 4-5) — Charts

| Deliverable | Description |
|-------------|-------------|
| Stock performance chart | Recharts ComposedChart with position value + cost basis + benchmarks |
| Benchmark selector | Reuse `BenchmarkSelector` component |
| Time period selector | Reuse `TimePeriodSelector` component |
| Dividend bar chart | Recharts BarChart with quarterly/annual dividend amounts |
| Period range filter | Time range selector for dividend chart |

**Verification:** Charts render correctly, benchmark comparison works, dividend history shows bars.
