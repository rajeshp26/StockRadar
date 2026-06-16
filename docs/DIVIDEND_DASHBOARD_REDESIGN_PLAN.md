# Dividend Dashboard Redesign — Implementation & Impact Analysis

> **Date**: 2026-06-15
> **Scope**: Convert the current 4-tab dividend analysis panel into a single-page dividend dashboard.
> **Current**: `web/src/features/analysis/components/dividend-panel.tsx` (956 lines, 4 sub-tabs)
> **Target**: Single scrollable page with 12-column grid layout, Recharts charts, and the project's existing glass-* design system

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Target State Analysis](#3-target-state-analysis)
4. [Content Gap Analysis](#4-content-gap-analysis)
5. [Backend Changes Required](#5-backend-changes-required)
6. [Frontend Changes Required](#6-frontend-changes-required)
7. [CSS/Style Changes Required](#7-cssstyle-changes-required)
8. [Implementation Order](#8-implementation-order)
9. [File Impact Summary](#9-file-impact-summary)
10. [Risk Assessment](#10-risk-assessment)

---

## 1. Executive Summary

### Current Architecture
The dividend analysis is rendered as one tab ("Dividend") within the stock analysis page at `/(authenticated)/analysis/[symbol]/page.tsx`. It contains 4 internal sub-tabs (Overview, Safety, Growth, Yield) that the user must click between. Data is fetched via React Query from `GET /api/proxy/analysis/{symbol}/dividend`, which proxies to the FastAPI backend at `GET /analysis/{symbol}/dividend`.

### Target Architecture
A single-page dashboard showing all dividend information at once, organized in a 12-column CSS grid. Uses the **project's existing design system** — glass-* CSS classes, `ScoreRing` component, `Metric` component, `SectionHeader`, Recharts, and Tailwind utility classes. No new chart library is needed. No new score circle components are needed. Minimal new CSS.

### Design Alignment Decision
The target HTML provided uses a standalone dark theme (solid gradient panels, Chart.js, conic-gradient circles). **This deviates from StockerPro's glassmorphism system**. The plan below adapts the target's **layout and data organization** to use the existing design system, ensuring visual consistency with Fundamentals, Moat, Risk, DCF, and every other analysis panel.

### Key Differences
| Aspect | Current | Target |
|---|---|---|
| Navigation | 4 sub-tabs with tab switching | Single scrollable page |
| Charts | Custom SVG sparkline | Recharts (already in project) |
| Score circles | SVG `ScoreRing` component | **Same `ScoreRing` component** (no change) |
| CSS | Tailwind + glass-* classes | **Same Tailwind + glass-* classes** |
| Data per view | Loaded per sub-tab selection | All data loaded at once from single API call |
| Layout | Tab content area | 12-column CSS grid using existing classes |

---

## 2. Current State Analysis

### 2.1 Frontend Files

| File | Path | Lines | Role |
|---|---|---|---|
| Dividend Panel | `web/src/features/analysis/components/dividend-panel.tsx` | 956 | Main UI component (4 sub-tabs) |
| Shared UI | `web/src/features/analysis/components/shared-ui.tsx` | 416 | ScoreRing, Metric, SectionHeader, etc. |
| React Hook | `web/src/features/analysis/hooks/useDividendAnalysis.ts` | 48 | React Query hook |
| Types | `web/src/features/analysis/types/analysis.types.ts` | 1199 (lines 364–467 for dividends) | TypeScript interfaces |
| Analysis Page | `web/src/app/(authenticated)/analysis/[symbol]/page.tsx` | 336 | Renders DividendPanel on "dividend" tab |
| Global CSS | `web/src/app/globals.css` | 432 | Glass-morphism CSS classes |

### 2.2 Current UI Structure (dividend-panel.tsx)

```
DividendPanel (exported component)
├── Error banner
├── Sub-tab bar (4 buttons: Overview, Safety, Growth, Yield)
├── OverviewPanel
│   ├── KPI cards (4: Annual Dividend, Yield, Payout Ratio, Frequency)
│   ├── Schedule (Last Increase, Ex-Dividend Date)
│   ├── Secondary metrics (FCF Payout, GAAP Payout)
│   └── Sparkline (custom SVG)
├── SafetyPanel
│   ├── ScoreRing (SVG, 0–100)
│   ├── Metrics table (8 metrics in 2-column grid)
│   ├── Earnings Stability
│   ├── Dividend Policy
│   ├── Strengths list
│   └── Key Risks list
├── GrowthPanel
│   ├── ScoreRing (SVG, 0–100)
│   ├── CAGR grid (1Y, 3Y, 5Y, 10Y, Consecutive Increases)
│   └── Recent Changes table
└── YieldPanel
    ├── KPI tiles (4: Current, 5Y Avg, 5Y High, 5Y Low)
    ├── Yield Range Bar (custom component)
    ├── Yield Theory Signal
    └── Relative Positioning
```

### 2.3 Current Backend API Response Shape

The backend at `GET /analysis/{symbol}/dividend` returns:

```json
{
  "symbol": "AAPL",
  "pays_dividend": true,
  "overview": {
    "annual_dividend": 1.08,
    "per_period_amount": 0.27,
    "dividend_yield": 0.0531,
    "payout_ratio_adj_eps": 0.48,
    "payout_ratio_gaap": 0.45,
    "payout_ratio_fcf": 0.29,
    "gaap_negative_eps": false,
    "frequency": "quarterly",
    "frequency_multiplier": 4,
    "ex_dividend_date": "2026-02-11",
    "payment_date": null,
    "last_increase_date": "2024-11-05",
    "status": "growing",
    "sparkline": [{"date": "...", "amount": 0.27}, ...],
    "current_price": 20.35
  },
  "safety": {
    "composite_score": 65,
    "composite_category": "Caution",
    "metrics": [
      {"name": "Div Payout (Adj EPS)", "benchmark": "<60%", "value": 0.48, "formatted": "48%", "rating": "safe"},
      ...
    ],
    "earnings_stability": "volatile",
    "dividend_policy": {
      "growth_trend": "growing",
      "cut_history": "Major cut (2023)",
      "has_cut": true,
      "cut_year": 2023,
      "retention_rate": null
    },
    "strengths": ["..."],
    "key_risks": ["..."]
  },
  "growth": {
    "growth_score": 4,
    "growth_category": "Poor",
    "cagr_1y": 0.0,
    "cagr_3y": -0.201,
    "cagr_5y": -0.08,
    "cagr_10y": null,
    "consecutive_increases": 0,
    "annual_totals": null,          // ← type defines it, backend does NOT send it
    "recent_changes": [...]         // max 6 entries
  },
  "yield_analysis": {
    "current_yield": 0.0531,
    "avg_yield_5y": 0.0243,
    "yield_min_5y": 0.0032,
    "yield_max_5y": 0.0592,
    "yield_percentile_5y": 89,
    "yield_vs_sector": null,
    "yield_vs_market": null,
    "theory_signal": "Yield is currently above its 5-year average...",
    "yield_history": [{"date": "...", "yield": 0.05, "price": 20.0, "ttm_dividend": 1.08}, ...]
  }
}
```

### 2.4 Backend Service Structure

**File**: `backend/application/services/dividend_analysis_service.py` (690 lines)

Key data fetchers (all run in parallel via `asyncio.gather`):
- `_fetch_dividend_history(company_id)` — gets dividend_history table (up to 120 rows)
- `repo.get_dividend_metrics_latest(company_id)` — pre-computed metrics
- `repo.get_income_statement_latest(company_id)` — latest income statement
- `repo.get_income_statements_annual(company_id)` — annual income statements
- `repo.get_cash_flow_latest(company_id)` — latest cash flow
- `_fetch_dividends_paid(company_id)` — direct query for dividends_paid
- `repo.get_balance_sheet_latest(company_id)` — latest balance sheet
- `repo.get_current_market_price(company_id)` — current price
- `repo.get_fcf_history(company_id)` — FCF history
- `_fetch_price_history(company_id)` — price history (6 years)

---

## 3. Target State Analysis

### 3.1 Layout Structure (Adapted to StockerPro Design System)

The target HTML's layout is adapted to use existing StockerPro components and CSS:

```
<div className="space-y-6 animate-fade-up">
  ─── Top Bar ──────────────────────────────
  <div className="flex justify-between items-start gap-5 flex-wrap">
    <div>
      <h1>Dividend Dashboard</h1>
      <p className="text-white/35 text-sm">Current distribution metrics...</p>
      <div className="flex gap-2 flex-wrap mt-3">
        <span className="glass-badge glass-badge-buy">Growing</span>
        <span className="glass-badge glass-badge-hold">Safety: Caution</span>
        <span className="glass-badge glass-badge-sell">Major Cut (2023)</span>
        <span className="glass-badge bg-indigo-500/10 border-indigo-500/25 text-indigo-400">Quarterly Payer</span>
      </div>
    </div>
    <div className="flex gap-2 flex-wrap">
      <span className="glass-chip">Overview</span>
      <span className="glass-chip">Safety</span>
      <span className="glass-chip">Growth</span>
      <span className="glass-chip">Yield</span>
      <span className="glass-chip">History</span>
    </div>
  </div>

  ─── 12-Column Grid ────────────────────────
  <div className="grid grid-cols-12 gap-4">
    ── Hero: span-12 (2-col inner grid) ────
    <div className="glass-panel p-8 col-span-12 relative overflow-hidden">
      <div className="grid md:grid-cols-[2fr_1fr] gap-6">
        <SectionHeader ... />
        <Metric tiles (4) />
        ── Schedule + Signal box ──
      </div>
    </div>

    ── Dividend History Chart: span-8 ──────
    <div className="glass-panel p-8 col-span-8">
      <SectionHeader ... />
      <ResponsiveContainer> ... Recharts BarChart ... </ResponsiveContainer>
    </div>

    ── Growth Score: span-4 ────────────────
    <div className="glass-panel p-8 col-span-4">
      <ScoreRing score={4} category="Poor" size={110} />
      ── mini-list ──
    </div>

    ── Safety: span-8 ──────────────────────
    <div className="glass-panel p-8 col-span-8">
      <div className="flex gap-6">
        <ScoreRing score={65} category="Caution" size={110} />
        ── 8 ratio cards in 2-col grid ──
      </div>
    </div>

    ── Strengths & Risks: span-4 ───────────
    <div className="glass-panel p-8 col-span-4"> ... </div>

    ── Growth Momentum: span-12 ───────────
    <div className="glass-panel p-8 col-span-12">
      ── 5 stat tiles + Recharts LineChart ──
    </div>

    ── Recent Changes: span-6 ──────────────
    <div className="glass-panel p-8 col-span-6"> ── timeline ── </div>

    ── Yield Analysis: span-6 ──────────────
    <div className="glass-panel p-8 col-span-6">
      ── 4 yield stats + range bar + insight ──
    </div>
  </div>
</div>
```

### 3.2 Adapted Component Mapping (Target → StockerPro)

| Target HTML Element | StockerPro Equivalent |
|---|---|
| `.card` (gradient bg, 20px radius, ::before accent) | `glass-panel p-8 relative overflow-hidden` + `AccentLine` div |
| `.section-title h2` (18px, 750 weight) | `SectionHeader` (text-lg font-black) |
| `.metric` (label + 30px value + sub) | `Metric` (glass-stat with text-3xl font-black) |
| `.badge` (green/yellow/red/blue variants) | `glass-badge-buy` / `glass-badge-hold` / `glass-badge-sell` / custom indigo |
| `.chip` filter pills | `glass-chip` (or inline `glass-segmented-item` style) |
| `.score-circle` (conic-gradient) | **`ScoreRing`** component from shared-ui.tsx |
| `.ratio-card` `.tag` | `glass-stat` with inline `RatingBadge` (existing) |
| `.list-box.good` / `.bad` | Existing strengths/risks pattern from SafetyPanel |
| `.range-bar` | Existing `YieldRangeBar` component (visual refresh only) |
| `.timeline` items | Existing `ChangeRow` pattern (visual refresh only) |
| Chart.js bar/line | **Recharts** `BarChart` + `LineChart` |
| `.signal-box` / `.insight` | Existing `AiNote` style pattern |
| `.growth-stats` stat boxes | `Metric` components in a 5-column grid |
| `.metric-grid` (4 tiles) | `Metric` components in `grid grid-cols-4` |
| Canvas with Chart.js | `ResponsiveContainer` + Recharts |

### 3.3 Design Consistency Checklist

| Check | Match | Notes |
|---|---|---|
| Uses `glass-panel` for cards | ✅ | Same as all other panels |
| Uses `ScoreRing` for scores | ✅ | Same as DCF, Moat, Risk panels |
| Uses Recharts for charts | ✅ | Same as Performance, Stock-vs-Index panels |
| Uses `Metric` for stat tiles | ✅ | Same as all panels |
| Uses `SectionHeader` for headings | ✅ | Same as all panels |
| Uses `glass-badge-*` for tag pills | ✅ | Same as all panels |
| Uses `glass-divider` for dividers | ✅ | Same as all panels |
| Uses `lucide-react` icons if needed | ✅ | Same as all panels |
| Uses Tailwind spacing/color scale | ✅ | Same as all panels |
| Uses `font-black` for headings | ✅ | Same as all panels |
| Does NOT add Chart.js dependency | ✅ | Recharts already installed |
| Does NOT add conic-gradient score circles | ✅ | ScoreRing already exists |
| Does NOT add new CSS variables | ✅ | Uses existing `--glass-*` system |
| Does NOT add custom panel styles | ✅ | Uses existing `glass-panel` |
| Does NOT add custom badge styles | ✅ | Uses existing `glass-badge-*` |

---

## 4. Content Gap Analysis

### 4.1 Data Currently Available (No Changes Needed)

| Target Section | Backend Field | Status |
|---|---|---|
| Hero: Annual Dividend | `overview.annual_dividend`, `overview.per_period_amount` | ✅ Available |
| Hero: Dividend Yield | `overview.dividend_yield` | ✅ Available |
| Hero: Payout Ratio | `overview.payout_ratio_adj_eps` | ✅ Available |
| Hero: Frequency | `overview.frequency`, `overview.frequency_multiplier` | ✅ Available |
| Schedule: Last Increase | `overview.last_increase_date` | ✅ Available |
| Schedule: Ex-Dividend Date | `overview.ex_dividend_date` | ✅ Available |
| Schedule: FCF Payout | `overview.payout_ratio_fcf` | ✅ Available |
| Schedule: GAAP Payout | `overview.payout_ratio_gaap` | ✅ Available |
| Safety: Composite Score | `safety.composite_score` | ✅ Available |
| Safety: Composite Category | `safety.composite_category` | ✅ Available |
| Safety: 8 ratio cards | `safety.metrics[0..7]` | ✅ Available |
| Safety: Dividend Policy | `safety.dividend_policy` | ✅ Available |
| Safety: Strengths | `safety.strengths` | ✅ Available |
| Safety: Key Risks | `safety.key_risks` | ✅ Available |
| Growth: CAGR values | `growth.cagr_1y`, `growth.cagr_3y`, `growth.cagr_5y`, `growth.cagr_10y` | ✅ Available |
| Growth: Score/Category | `growth.growth_score`, `growth.growth_category` | ✅ Available |
| Growth: Consecutive Increases | `growth.consecutive_increases` | ✅ Available |
| Growth: Recent Changes | `growth.recent_changes` | ✅ Available |
| Yield: All yield values | `yield_analysis.current_yield`, `avg_yield_5y`, `yield_min_5y`, `yield_max_5y`, `yield_percentile_5y` | ✅ Available |
| Yield: Theory Signal | `yield_analysis.theory_signal` | ✅ Available |
| Yield: Relative positioning | `yield_analysis.yield_vs_sector`, `yield_vs_market` | ✅ Available (both null) |

### 4.2 Data Gaps

| # | Target Field | Backend Status | Root Cause |
|---|---|---|---|
| **GAP-1** | Dividend history bar chart & growth line chart data (annual totals) | `growth.annual_totals` is defined in `DividendGrowthData` interface (line 437) but **backend's `_compute_growth()` omits it from the return dict** (lines 540–549) | The backend already computes annual totals internally in `_compute_cagr_from_history()` and `_count_consecutive_increases()`, but never exposes them. ~15 line fix. |

### 4.3 GAP-1 Backend Verification

**Confirmed — `annual_totals` is ABSENT from the backend response.**

Checked against:
- `dividend_analysis_service.py` line 540–549: The return dict of `_compute_growth()` has: `growth_score`, `growth_category`, `cagr_1y`, `cagr_3y`, `cagr_5y`, `cagr_10y`, `consecutive_increases`, `recent_changes`. **No `annual_totals`.**
- `analysis.types.ts` line 437: `annual_totals: Record<string, number>` is defined as a required field.

**Can it be computed?** Yes. The raw data exists in `sorted_desc` (dividend_history table, up to 120 rows). The backend already has the same aggregation logic in `_compute_cagr_from_history()` (lines 566–575) and `_count_consecutive_increases()` (lines 593–599). Both build an `annual: Dict[int, float]` locally. Adding `annual_totals` is straightforward: add the same aggregation to `_compute_growth()` and include it in the return dict.

**Has it been tested?** No direct API test was run, but a code audit confirms the return dict explicitly excludes `annual_totals`. The TypeScript type would cause the frontend to receive `undefined` for this field.

### 4.4 No Other Backend Gaps

All other data points in the target are already present in the current API response.

### 4.5 Frontend Composition (No Backend Changes)

These target elements can be composed from existing data on the frontend:

| Target Element | Data Source | Composition Rule |
|---|---|---|
| Badge: "Growing" | `overview.status` | Direct mapping (growing → badge-buy) |
| Badge: "Safety: Caution" | `safety.composite_category` | Prefix "Safety: " to category |
| Badge: "Major Cut (2023)" | `safety.dividend_policy.cut_history` or `has_cut` + `cut_year` | Format as `Major cut ({year})` |
| Badge: "Quarterly Payer" | `overview.frequency` | Capitalize frequency + " Payer" |
| Investor Signal box text | `yield_analysis.current_yield`, `safety.metrics` (FCF payout), `safety.dividend_policy.has_cut` | Compose from yield + coverage + cut history |
| Retention Rate in Growth section | `safety.dividend_policy.retention_rate` | Already available, just display in growth section |

---

## 5. Backend Changes Required

### 5.1 Add `annual_totals` to Growth Response

**File**: `backend/application/services/dividend_analysis_service.py`

**Function**: `_compute_growth()` (line 492)

**Current** (lines 540–549):
```python
return {
    "growth_score":          score,
    "growth_category":       growth_category,
    "cagr_1y":               round(cagr_1y, 4)  if cagr_1y  is not None else None,
    "cagr_3y":               round(cagr_3y, 4)  if cagr_3y  is not None else None,
    "cagr_5y":               round(cagr_5y, 4)  if cagr_5y  is not None else None,
    "cagr_10y":              round(cagr_10y, 4) if cagr_10y is not None else None,
    "consecutive_increases": consecutive_increases,
    "recent_changes":        recent_changes[:6],
}
```

**Required change**: Add `annual_totals`:
```python
# Aggregate annual totals from dividend history
annual_totals: Dict[str, float] = {}
for d in sorted_desc:
    raw = d.get("ex_dividend_date", "")
    try:
        year = str(raw)[:4]
    except:
        continue
    amt = safe_float(d.get("dividend_amount"))
    if amt:
        annual_totals[year] = annual_totals.get(year, 0.0) + amt

return {
    # ... existing fields ...
    "annual_totals":        annual_totals,         # NEW
    "recent_changes":       recent_changes[:6],
}
```

**No new DB queries needed** — data is already in `sorted_desc`.

### 5.2 No Other Backend Changes

All other data is already present. The `annual_totals` gap is the only structural data gap.

---

## 6. Frontend Changes Required

### 6.1 Design System Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Chart library | **Recharts** (existing) | Already in `package.json`, used by 3+ analysis panels. No new dependency. |
| Score display | **ScoreRing** component | Used by DCF, Moat, Risk, Safety, Growth panels already. No new component needed. |
| Panel container | **`glass-panel p-8`** | Standard container across all analysis panels. |
| Stat tiles | **`Metric`** component | Standard across all panels. |
| Badges | **`glass-badge-buy/hold/sell`** | Existing badge system. Add one custom indigo variant if needed. |
| Loading state | **`glass-shimmer` / `Skeleton`** | Existing patterns across all panels. |
| Layout | **Tailwind grid** (`grid grid-cols-12 gap-4`) | Responsive, no new CSS. |
| Icons | **lucide-react** | Already in project. Target HTML has no icons; we can add them. |

### 6.2 Component Structure (New dividend-panel.tsx)

The rewrite removes the 4 sub-tabs and composes everything in a single scrollable page:

```
DividendPanel (rewritten, ~800 lines)
├── TopBar
│   ├── Title + description
│   ├── Status badges (4 badges from overview.status, safety.category, etc.)
│   └── Decorative filter chips
├── Error banner (preserved from current)
├── NoDividendState (preserved, restyled)
└── 12-column grid (shown only if paysDividend)
    ├── HeroSection (span-12)
    │   ├── Left: SectionHeader + 4 Metric tiles + schedule mini-cards
    │   └── Right: Schedule list + Signal box (composed from data)
    ├── DividendHistoryChart (span-8)
    │   ├── SectionHeader
    │   └── Recharts BarChart (annual totals from growth.annual_totals)
    ├── GrowthScoreCard (span-4)
    │   ├── ScoreRing (growth_score, growth_category)
    │   └── Mini-list (growth_trend, cut_history, consecutive, retention)
    ├── SafetySection (span-8)
    │   ├── ScoreRing (composite_score, composite_category)
    │   └── 8 ratio cards in 2-col grid (safety.metrics)
    ├── StrengthsRisksCard (span-4)
    │   ├── Strengths list (safety.strengths)
    │   └── Risks list (safety.key_risks)
    ├── GrowthMomentum (span-12)
    │   ├── 5 stat boxes (cagr_1y/3y/5y/10y + consecutive)
    │   └── Recharts LineChart (annual_totals)
    ├── RecentChangesTimeline (span-6)
    │   └── Timeline list (growth.recent_changes)
    └── YieldAnalysisSection (span-6)
        ├── 4 yield Metric tiles
        ├── YieldRangeBar (existing component)
        ├── Theory signal (existing AiNote style)
        └── Relative positioning
```

### 6.3 Components to Keep (No Changes)

| Component | File | Reason |
|---|---|---|
| `ScoreRing` | `shared-ui.tsx` | Reused as-is for Safety and Growth scores |
| `Metric` | `shared-ui.tsx` | Reused for all stat tiles |
| `SectionHeader` | `shared-ui.tsx` | Reused for all section headings |
| `fmtCurrency`, `fmtPct` | `shared-ui.tsx` | Reused formatting |
| `useDividendAnalysis` | `hooks/useDividendAnalysis.ts` | No change to hook or API |
| `YieldRangeBar` | `dividend-panel.tsx` (current) | Keep and adapt styling |

### 6.4 New Reusable Sub-Components to Create

| Component | Approx Lines | Purpose |
|---|---|---|
| `StatusBadgeRow` | 30 | Renders 4 status badges from overview + safety + policy data |
| `ScheduleMiniList` | 40 | Last Increase, Ex-Date, FCF Payout, GAAP Payout |
| `SignalBox` | 30 | Composed insight text from yield + safety data |
| `SafetyRatioCard` | 50 | Single ratio card with name, benchmark, value, tag |
| `GrowthStatBox` | 30 | Single stat box with label + value (green/red/gray) |
| `ChangeTimelineItem` | 40 | Single timeline row with date, event, amount, delta |

### 6.5 Chart Components (Recharts)

Already in project — no `npm install` needed.

**Dividend History Bar Chart** (in DividendHistoryChart section):
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

<ResponsiveContainer width="100%" height={250}>
  <BarChart data={chartData}>
    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
    <XAxis dataKey="year" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
    <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toFixed(2)}`} />
    <Tooltip
      contentStyle={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 8 }}
    />
    <Bar dataKey="amount" radius={[8, 8, 0, 0]} fill="url(#barGradient)" />
  </BarChart>
</ResponsiveContainer>
```

**Growth Line Chart** (in GrowthMomentum section):
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

<ResponsiveContainer width="100%" height={250}>
  <LineChart data={chartData}>
    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
    <XAxis dataKey="year" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
    <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toFixed(2)}`} />
    <Tooltip
      contentStyle={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 8 }}
    />
    <Line dataKey="amount" stroke="#22c55e" strokeWidth={3} dot={{ r: 4 }} type="monotone" />
  </LineChart>
</ResponsiveContainer>
```

Follows the same Recharts styling pattern used in `stock-performance-panel.tsx` and `stock-vs-index-panel.tsx` (lines 118, 161–163, 203–205).

### 6.6 Sub-components Dropped

| Current Component | Reason for Removal |
|---|---|
| `DivTab` / `DIV_TABS` | No more sub-tabs |
| `OverviewPanel` | Replaced by Hero section |
| `SafetyPanel` | Replaced by Safety section + Strengths/Risks card |
| `GrowthPanel` | Replaced by Growth Score + Momentum sections |
| `YieldPanel` | Replaced by Yield Analysis section |
| `DividendSparkline` | Replaced by Recharts bar + line charts |
| `MetricSkeleton` | Replace with `Skeleton` from shadcn |
| `StatusBadge` (single) | Replaced by `StatusBadgeRow` (4 badges) |
| `SafetyRow` | Replaced by `SafetyRatioCard` |
| `ChangeRow` | Replaced by `ChangeTimelineItem` |
| `RatingBadge` | Replaced by inline tag spans |
| `AiNote` | Replaced by `SignalBox` |
| `AccentLine` (inline div) | Already available in current code; reused |

---

## 7. CSS/Style Changes Required

### 7.1 Minimal New CSS

The target HTML uses ~350 lines of custom CSS. **We don't need most of it** because we're using the existing glass-* system.

**What we DO need to add** (estimate ~50-80 lines):

1. **`.glass-chip`** class for decorative filter pills (follows existing badge/segmented patterns):
   ```css
   .glass-chip {
     @apply glass-badge;
     background: var(--glass-1);
     border-color: var(--glass-border);
     color: rgba(255,255,255,0.4);
     cursor: default;
   }
   ```

2. **Responsive grid helpers** for the 12-column layout at breakpoints (if needed):
   ```css
   @media (max-width: 1100px) {
     .span-md-full { grid-column: span 12; }
   }
   @media (max-width: 800px) {
     .span-sm-full { grid-column: span 12; }
   }
   ```

3. **ScoreRing inline size adjustments** — the target uses 110px circles vs current 120px. Pass `size={110}` prop.

### 7.2 What We DON'T Need to Add

| Target CSS | Why Not Needed |
|---|---|
| `--bg`, `--panel`, `--border` variables | Use existing `--glass-*` variables |
| `.card` gradient backgrounds | Use existing `glass-panel` |
| `.card::before` accent | Use existing `AccentLine` div pattern |
| `.score-circle` (conic-gradient) | Use existing `ScoreRing` component |
| `.badge` classes | Use existing `glass-badge-buy/hold/sell` |
| `.metric` classes | Use existing `Metric` component |
| `.ratio-card` | Use existing `glass-stat` |
| `.tag` classes | Use existing `RatingBadge` or inline |
| `.range-bar` | Already implemented in `YieldRangeBar` |
| Chart.js init code | Replaces with Recharts JSX |
| `.green`, `.yellow`, `.red`, `.blue` variants | Use existing semantic badge colors |
| `body` background / global styles | Project's existing background handles this |

### 7.3 Existing CSS Reused

| Style | Source |
|---|---|
| Panel container | `.glass-panel` |
| Stat tiles | `.glass-stat` (via `Metric` component) |
| Badges | `.glass-badge-buy`, `.glass-badge-hold`, `.glass-badge-sell` |
| Dividers | `.glass-divider` |
| Overline labels | `.glass-overline` |
| Buttons | `.glass-btn` |
| Loading shimmer | `.glass-shimmer` |
| Section header | `SectionHeader` component |
| Score ring | `ScoreRing` component |

---

## 8. Implementation Order

### Phase 1: Backend (~15 min)

| Step | File | Change |
|---|---|---|
| 1.1 | `dividend_analysis_service.py` | Add `annual_totals` aggregation and return in `_compute_growth()` |

### Phase 2: Frontend Components (~2-3 hours)

| Step | Component | Approx Lines | Details |
|---|---|---|---|
| 2.1 | `dividend-panel.tsx` (rewrite) | ~800 | Replace entire file with single-page dashboard |
| 2.2 | Inline: `StatusBadgeRow` | ~30 | Compose 4 badges from data |
| 2.3 | Inline: `ScheduleMiniList` | ~40 | 4 schedule items |
| 2.4 | Inline: `SignalBox` | ~30 | Insight text composition |
| 2.5 | Inline: `SafetyRatioCard` | ~50 | Single ratio card |
| 2.6 | Inline: `GrowthStatBox` | ~30 | Single stat box |
| 2.7 | Inline: `ChangeTimelineItem` | ~40 | Single timeline row |
| 2.8 | Recharts BarChart | ~40 | Dividend history chart |
| 2.9 | Recharts LineChart | ~40 | Growth trend chart |

### Phase 3: CSS (~15 min)

| Step | File | Change |
|---|---|---|
| 3.1 | `globals.css` | Add `.glass-chip` class (~10 lines) |
| 3.2 | `globals.css` | Add responsive grid helpers (~20 lines) |

### Phase 4: Verification (~30 min)

| Step | Action |
|---|---|
| 4.1 | Run: `npm run build` (or `npm run lint` + `npm run typecheck`) |
| 4.2 | Test with a dividend-paying stock (e.g., AAPL, O) |
| 4.3 | Test with a non-dividend stock (verify NoDividendState) |
| 4.4 | Test loading state (slow network) |
| 4.5 | Test with null/missing data (partial API response) |
| 4.6 | Verify responsive layout at 1100px, 800px, 700px |

---

## 9. File Impact Summary

### Files Modified

| # | File | Change Type | Impact |
|---|---|---|---|
| 1 | `web/src/features/analysis/components/dividend-panel.tsx` | 🔴 **Rewrite** | 956 lines → ~800 lines, complete restructure |
| 2 | `backend/application/services/dividend_analysis_service.py` | 🟢 **Edit** | ~15 lines to add `annual_totals` to growth response |
| 3 | `web/src/app/globals.css` | 🟢 **Append** | ~30 lines: `.glass-chip` + responsive helpers |

### Files Created

| # | File | Purpose |
|---|---|---|
| None | — | All components are inline in dividend-panel.tsx |

### Files Unchanged (No Impact)

| File | Reason |
|---|---|
| `web/src/features/analysis/hooks/useDividendAnalysis.ts` | API shape unchanged (additive field only) |
| `web/src/features/analysis/types/analysis.types.ts` | `annual_totals` already defined |
| `web/src/features/analysis/components/shared-ui.tsx` | ScoreRing, Metric, SectionHeader remain unchanged |
| `web/src/app/(authenticated)/analysis/[symbol]/page.tsx` | Only renders `<DividendPanel>`, interface unchanged |
| `backend/api/analysis.py` | Routes unmodified |
| `backend/infrastructure/repositories/*.py` | No new queries |
| `web/src/features/portfolio/components/DividendsTab.tsx` | Separate feature, not in scope |
| `package.json` | No new dependencies (Recharts already installed) |

### Total Estimated Effort

| Category | Files | Lines |
|---|---|---|
| Backend change | 1 | ~15 lines |
| CSS additions | 1 | ~30 lines |
| Frontend rewrite | 1 | ~800 lines |
| **Total** | **3 files** | **~845 lines** |

---

## 10. Risk Assessment

### Risk 1: CSS Conflicts (Low)
**Concern**: Adding `.glass-chip` class could conflict with future additions.
**Mitigation**: Follow existing naming convention (`glass-*` prefix). The class is small and self-contained.

### Risk 2: Recharts Styling Consistency (Low)
**Concern**: Charts may look different from other Recharts in the app.
**Mitigation**: Copy the exact `CartesianGrid`, `XAxis`, `YAxis`, and `Tooltip` styling from `stock-vs-index-panel.tsx` (lines 161–163) and `stock-performance-panel.tsx` (line 118).

### Risk 3: Data Availability (Low)
**Concern**: `annual_totals` returns empty for stocks with no dividend history.
**Mitigation**: The bar chart and line chart should handle empty data gracefully — render `ResponsiveContainer` with fallback "No data" text.

### Risk 4: Performance (Low)
**Concern**: Single-page layout loads all data at once.
**Mitigation**: Current implementation already fetches all 4 sections in one API call. There is no additional data fetching. The 12-column grid simply shows everything simultaneously.

### Risk 5: Loss of Sub-tab Functionality (None)
**Concern**: Users may miss the sub-tab navigation.
**Mitigation**: The target's filter chips are position-based navigation markers. If users want scrolling navigation, we could add `scroll-margin-top` to each section for anchor-based jumping. This can be added as a follow-up.

### Risk 6: Responsive Layout at 1400px (Low)
**Concern**: The analysis page wrapper already has its own max-width.
**Mitigation**: Omit any outer max-width container. Let the grid fill the available tab content area naturally.

---

## Appendix A: Section-by-Section Data Mapping

| Target Section | Target Elements | Backend Data Source | New Code? |
|---|---|---|---|
| Top Bar: Title | "Dividend Dashboard" | Static | No |
| Top Bar: Description | "Current distribution metrics..." | Static | No |
| Top Bar: Badges | 4 badges | `overview.status`, `safety.composite_category`, `safety.dividend_policy`, `overview.frequency` | Frontend composition |
| Top Bar: Chips | 5 decorative pills | Static | No |
| Hero: Metrics | 4 tiles | `overview.*` | No |
| Hero: Schedule | 4 mini-items | `overview.last_increase_date`, `ex_dividend_date`, `payout_ratio_fcf`, `payout_ratio_gaap` | No |
| Hero: Signal Box | Text with yield + coverage + leverage + cut | Yield + safety data | Frontend composition |
| Dividend History | Bar chart (annual totals) | `growth.annual_totals` | **Backend GAP-1** + Recharts |
| Growth Score | ScoreRing + mini-list | `growth.growth_score`, `growth.growth_category` + `safety.dividend_policy` | No |
| Safety | ScoreRing + 8 ratio cards | `safety.composite_score`, `safety.metrics[0..7]` | No |
| Strengths & Risks | Split good/bad lists | `safety.strengths`, `safety.key_risks` | No |
| Growth Momentum | 5 stat boxes + line chart | `growth.cagr_*`, `consecutive_increases` + `annual_totals` | **Backend GAP-1** |
| Recent Changes | 6 timeline items | `growth.recent_changes[0..5]` | No |
| Yield: 4 cards | Current, 5Y Avg, 5Y High, 5Y Low | `yield_analysis.*` | No |
| Yield: Range bar | Range bar + percentile | `yield_analysis.*` | No |
| Yield: Insight | Theory signal text | `yield_analysis.theory_signal` | No |
| Yield: Relative | vs Sector / vs Market | `yield_analysis.yield_vs_sector/market` | No |

---

## Appendix B: `annual_totals` Verification

**Question**: Is `annual_totals` truly missing from the backend?

**Answer**: Yes. Verified by reading the source code directly.

### What the TypeScript type expects (`analysis.types.ts:437`):
```typescript
export interface DividendGrowthData {
  growth_score: number;
  growth_category: SuitabilityCategory;
  cagr_1y: number | null;
  cagr_3y: number | null;
  cagr_5y: number | null;
  cagr_10y: number | null;
  consecutive_increases: number;
  annual_totals: Record<string, number>;   // ← Required field
  recent_changes: DividendGrowthChange[];
}
```

### What the backend actually returns (`dividend_analysis_service.py:540-549`):
```python
return {
    "growth_score":          score,
    "growth_category":       growth_category,
    "cagr_1y":               ...,
    "cagr_3y":               ...,
    "cagr_5y":               ...,
    "cagr_10y":              ...,
    "consecutive_increases": consecutive_increases,
    "recent_changes":        recent_changes[:6],
    # NO "annual_totals" field
}
```

### The data is already in the backend's memory:
- `sorted_desc` (dividend history, up to 120 rows) is available in `_compute_growth()`
- The same aggregation logic already exists in `_compute_cagr_from_history()` (lines 566–575):
  ```python
  annual: Dict[int, float] = {}
  for d in sorted_desc:
      year = int(str(d["ex_dividend_date"])[:4])
      amt = safe_float(d.get("dividend_amount"))
      if amt:
          annual[year] = annual.get(year, 0.0) + amt
  ```
- It just needs to be added to the return dict.

### Fix:
Add ~8 lines of aggregation code to `_compute_growth()` and add `"annual_totals": annual_totals` to the return dict. No new DB queries. No schema changes.

---

## Appendix C: Integration Test Plan

### C.1 Test File

**File**: `web/src/__tests__/DividendPanel.test.tsx` (new file)

### C.2 Test Setup

Follow the established patterns from `RiskPanel.test.tsx` and `FundamentalsPanel.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";

// Required for Recharts ResponsiveContainer
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as any;
});

// Mock shared-ui components
vi.mock("@/features/analysis/components/shared-ui", () => {
  const React = require("react");
  return {
    Metric: ({ label, value, hint, accent }: any) =>
      React.createElement("div", { "data-testid": `metric-${label}`, "data-accent": accent },
        React.createElement("span", null, label),
        React.createElement("span", null, value),
        hint ? React.createElement("span", { "data-testid": "hint" }, hint) : null,
      ),
    SectionHeader: ({ title, subtitle }: any) =>
      React.createElement("div", { "data-testid": "section-header" },
        React.createElement("h3", null, title),
        subtitle ? React.createElement("p", null, subtitle) : null,
      ),
    ScoreRing: ({ score, category, size }: any) =>
      React.createElement("div", { "data-testid": "score-ring", "data-score": score, "data-category": category, "data-size": size },
        `${score} ${category}`,
      ),
  };
});

// Mock the hook
const mockUseDividendAnalysis = vi.fn();
vi.mock("@/features/analysis/hooks/useDividendAnalysis", () => ({
  useDividendAnalysis: (...args: any[]) => mockUseDividendAnalysis(...args),
}));
```

### C.3 Mock Data Factory

```typescript
function makeDividendData(overrides: Record<string, any> = {}) {
  return {
    symbol: "AAPL",
    pays_dividend: true,
    overview: {
      annual_dividend: 1.08,
      per_period_amount: 0.27,
      dividend_yield: 0.0531,
      payout_ratio_adj_eps: 0.48,
      payout_ratio_gaap: 0.45,
      payout_ratio_fcf: 0.29,
      gaap_negative_eps: false,
      frequency: "quarterly",
      frequency_multiplier: 4,
      ex_dividend_date: "2026-02-11",
      payment_date: null,
      last_increase_date: "2024-11-05",
      status: "growing",
      sparkline: [
        { date: "2026-02-11", amount: 0.27 },
        { date: "2025-11-05", amount: 0.27 },
      ],
      current_price: 20.35,
    },
    safety: {
      composite_score: 65,
      composite_category: "Caution",
      metrics: [
        { name: "Div Payout (Adj EPS)", benchmark: "<60%", value: 0.48, formatted: "48%", rating: "safe" },
        { name: "Div Payout (GAAP)", benchmark: "—", value: 0.45, formatted: "45%", rating: "info" },
        { name: "Cash Div Payout", benchmark: "<80%", value: 0.19, formatted: "19%", rating: "safe" },
        { name: "FCF Payout Ratio", benchmark: "<80%", value: 0.29, formatted: "29%", rating: "safe" },
        { name: "Div Coverage (FCF)", benchmark: "≥2×", value: 3.4, formatted: "3.4×", rating: "safe" },
        { name: "Net Debt / EBITDA", benchmark: "<3×", value: 4.6, formatted: "4.6×", rating: "risk" },
        { name: "Interest Coverage", benchmark: "≥3×", value: 3.3, formatted: "3.3×", rating: "safe" },
        { name: "Earnings Stability", benchmark: "5-year trend analysis", value: null, formatted: "Earnings fluctuate", rating: "caution", info_note: "Volatile" },
      ],
      earnings_stability: "volatile",
      dividend_policy: {
        growth_trend: "growing",
        cut_history: "Major cut (2023)",
        has_cut: true,
        cut_year: 2023,
        retention_rate: null,
      },
      strengths: [
        "Dividend well-covered by adjusted earnings",
        "Free cash flow generation supports the distribution",
        "Strong interest coverage provides debt service buffer",
      ],
      key_risks: [
        "Prior dividend cut impairs reliability track record",
        "Leverage at 4.6× Net Debt/EBITDA constrains growth",
      ],
    },
    growth: {
      growth_score: 4,
      growth_category: "Poor",
      cagr_1y: 0.0,
      cagr_3y: -0.201,
      cagr_5y: -0.08,
      cagr_10y: null,
      consecutive_increases: 0,
      annual_totals: { "2020": 0.02, "2021": 0.03, "2022": 0.05, "2023": 0.03, "2024": 1.08, "2025": 1.08, "2026": 1.08 },
      recent_changes: [
        { date: "2026-02-11", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
        { date: "2025-11-05", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
        { date: "2025-08-08", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
        { date: "2025-05-09", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
        { date: "2025-02-07", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
        { date: "2024-11-05", amount: 0.27, change_pct: 8.0, label: "+800.0%", direction: "increase" },
      ],
    },
    yield_analysis: {
      current_yield: 0.0531,
      avg_yield_5y: 0.0243,
      yield_min_5y: 0.0032,
      yield_max_5y: 0.0592,
      yield_percentile_5y: 89,
      yield_vs_sector: null,
      yield_vs_market: null,
      theory_signal: "Yield is currently above its 5-year average, suggesting potential undervaluation relative to historical norms.",
      yield_history: [
        { date: "2024-01-15", yield: 0.021, price: 25.0, ttm_dividend: 1.08 },
        { date: "2024-06-15", yield: 0.035, price: 30.0, ttm_dividend: 1.08 },
      ],
    },
    ...overrides,
  };
}
```

### C.4 Integration Test Cases (IT-01 through IT-18)

#### Loading & Error States

| ID | Test | Assertion |
|---|---|---|
| **IT-01** | Loading skeleton renders when data is loading | `useDividendAnalysis` returns `loading: true` → verify shimmer/`Skeleton` elements exist in the DOM |
| **IT-02** | Error banner renders on fetch failure | `error: "Failed to load"` → verify error text and retry button are visible |
| **IT-03** | No-dividend state renders | `pays_dividend: false` → verify "No Dividend" heading and descriptive text |
| **IT-04** | Null data shows empty state | `data: null, loading: false` → verify fallback empty state or graceful degradation |

#### Top Bar

| ID | Test | Assertion |
|---|---|---|
| **IT-05** | Dashboard title and description render | Verify "Dividend Dashboard" heading and description paragraph exist |
| **IT-06** | All 4 status badges render with correct labels | Verify "Growing", "Safety: Caution", "Major Cut (2023)", "Quarterly Payer" badges are visible |
| **IT-07** | Badge colors match status semantics | Verify "Growing" uses `glass-badge-buy`, "Safety: Caution" uses `glass-badge-hold`, "Major Cut" uses `glass-badge-sell` |
| **IT-08** | 5 filter chips render | Verify "Overview", "Safety", "Growth", "Yield", "History" chips are present |

#### Hero Section

| ID | Test | Assertion |
|---|---|---|
| **IT-09** | 4 hero metric tiles render with correct values | Verify "Annual Dividend" shows `$1.08`, "Dividend Yield" shows `5.31%`, "Payout Ratio" shows `48%`, "Frequency" shows `Quarterly` |
| **IT-10** | Schedule mini-list shows correct dates | Verify "Nov 5, 2024" for last increase, "Feb 11, 2026" for ex-dividend date |
| **IT-11** | Schedule shows FCF Payout and GAAP Payout | Verify `29%` and `45%` appear |
| **IT-12** | Signal box is rendered with composed text | Verify text mentions "5.31%", "cash flow coverage", and "cut history" |

#### Safety Section

| ID | Test | Assertion |
|---|---|---|
| **IT-13** | ScoreRing renders with correct score | `ScoreRing` receives `score=65` and `category="Caution"` |
| **IT-14** | All 8 ratio cards render with names and values | Verify "Div Payout (Adj EPS): 48%", "Net Debt / EBITDA: 4.6×", etc. |
| **IT-15** | Ratio card tags reflect rating | Verify "Safe" tags on good ratios, "Risk" tag on Net Debt/EBITDA, "Caution" on Earnings Stability |

#### Strengths & Risks

| ID | Test | Assertion |
|---|---|---|
| **IT-16** | All 3 strengths render | Verify text of each strength string from mock data |
| **IT-17** | All 2 key risks render | Verify text of each risk string from mock data |

#### Growth & Yield

| ID | Test | Assertion |
|---|---|---|
| **IT-18** | ScoreRing in growth receives correct score | `ScoreRing` receives `score=4` and `category="Poor"` |
| **IT-19** | 5 growth statistics render with correct CAGR formatting | Verify "1-Year Growth: +0.0%", "3-Year CAGR: -20.1%", "5-Year CAGR: -8.0%", "10-Year CAGR: —", "Consecutive: None" |
| **IT-20** | Recent changes timeline renders 6 entries | Verify each date (Feb 11, 2026, etc.) appears with corresponding amount and delta label |
| **IT-21** | 4 yield metric tiles render | Verify "Current Yield: 5.31%", "5-Year Avg Yield: 2.43%", "5-Year High: 5.92%", "5-Year Low: 0.32%" |
| **IT-22** | Yield range bar renders with percentile | Verify "89th percentile" text is present |
| **IT-23** | Yield theory signal renders | Verify theory signal text matches mock data |
| **IT-24** | Relative positioning shows fallback text | Verify "Sector & market comparison data coming soon" text |

#### Chart Rendering

| ID | Test | Assertion |
|---|---|---|
| **IT-25** | Bar chart renders with Recharts `ResponsiveContainer` | Verify the bar chart section contains a Recharts wrapper (check for `.recharts-responsive-container` or similar) |
| **IT-26** | Line chart renders with Recharts `ResponsiveContainer` | Verify the line chart section contains a Recharts wrapper |
| **IT-27** | Charts render empty state when no `annual_totals` | `annual_totals: {}` → verify fallback text or empty chart without errors |

#### Data Edge Cases

| ID | Test | Assertion |
|---|---|---|
| **IT-28** | Null payout ratios render as "—" | Set `payout_ratio_adj_eps: null` → verify metric shows "—" |
| **IT-29** | Null CAGR values render as "—" | Set `cagr_10y: null` → verify stat shows "—" |
| **IT-30** | Negative CAGR renders in red | Set `cagr_3y: -0.201` → verify text has red color class and shows "-20.1%" |
| **IT-31** | Zero growth renders in gray | Set `cagr_1y: 0.0` → verify text has gray/muted color class and shows "+0.0%" |
| **IT-32** | Missing ex-dividend date renders as "—" | Set `ex_dividend_date: null` → verify schedule shows "—" |
| **IT-33** | Empty strengths/risks arrays render fallback | Set `strengths: []`, `key_risks: []` → verify fallback text like "No notable strengths identified" |
| **IT-34** | No recent changes shows empty state | Set `recent_changes: []` → verify "No recent dividend data available" text |

---

## Appendix D: Performance Test Plan

### D.1 Performance Requirements

| Metric | Target | Measurement Method |
|---|---|---|
| **Time to First Paint (TTFP)** | < 500ms | `performance.mark()` in component |
| **Time to Interactive** | < 1000ms | React DevTools Profiler |
| **API response time (p95)** | < 2000ms | Backend logs / `asyncio.gather` timing |
| **React commit time** | < 50ms | React DevTools Profiler |
| **Recharts render time** | < 100ms per chart | `console.time()` around chart render |
| **Bundle size impact** | 0 KB (no new deps) | `npm run build` bundle analyzer |
| **Cache hit rate** | > 90% on revisit | React Query DevTools |

### D.2 Caching Performance (PF-01 to PF-05)

| ID | Test | Method | Success Criteria |
|---|---|---|---|
| **PF-01** | React Query stale time is sufficient | Verify `useDividendAnalysis` uses `STALE.VALUATION` (10 min) | No network request on tab switch within 10 min |
| **PF-02** | Cache persists after navigating away | Navigate to another tab and back | Dividend data renders instantly from `GC.VALUATION` (30 min) cache |
| **PF-03** | No redundant API calls on symbol change | Mock two different symbols, verify only 2 total API calls | Each symbol fetched exactly once per stale window |
| **PF-04** | `refetchOnWindowFocus` is disabled | Check query client defaults | Verify `false` — no refetch on tab re-focus |
| **PF-05** | AbortController prevents stale responses | Verify 15s timeout in `fetchDividendAnalysis` | Slow requests don't overwrite newer data |

### D.3 Render Performance (PF-06 to PF-10)

| ID | Test | Method | Success Criteria |
|---|---|---|---|
| **PF-06** | First render completes within 1000ms | Use `performance.now()` before/after render in test | `render(<DividendPanel />)` completes < 1000ms with mock data |
| **PF-07** | Chart components use `React.memo` | Code review of chart wrappers | BarChart and LineChart wrapped in `React.memo` |
| **PF-08** | Data transformations memoized with `useMemo` | Code review of `chartData` computation | Annual totals mapped to chart format inside `useMemo` |
| **PF-09** | No unnecessary re-renders on prop changes | Wrap `DividendPanel` in `React.memo`, verify with `renderCount` ref | `symbol` prop change triggers exactly 1 re-render |
| **PF-10** | All 8 safety ratio cards render within single commit | React DevTools Profiler trace | Single commit, no cascading renders |

### D.4 API Performance (PF-11 to PF-14)

| ID | Test | Method | Success Criteria |
|---|---|---|---|
| **PF-11** | Backend parallel fetchers complete under 2s | Check `asyncio.gather` execution time via logging | p95 < 2000ms for 10 concurrent DB queries |
| **PF-12** | Backend timeout doesn't block UI | Network throttle to 5s, verify loading shimmer appears | Loading state shown immediately; no UI freeze |
| **PF-13** | `annual_totals` aggregation is O(n) | Code review — single pass over sorted_desc | Linear scan, no nested loops |
| **PF-14** | Backend `get_company_context` uses index | Check EXPLAIN ANALYZE on company lookup query | Index scan, not seq scan |

### D.5 Layout Performance (PF-15 to PF-17)

| ID | Test | Method | Success Criteria |
|---|---|---|---|
| **PF-15** | CSS grid renders without layout shift | Lighthouse / manual visual check | No Cumulative Layout Shift (CLS) on data load |
| **PF-16** | Responsive breakpoints trigger single reflow | Resize window 1400px→800px→500px | No layout thrashing; smooth transitions |
| **PF-17** | Charts use `ResponsiveContainer` with fixed aspect | Code review of chart wrappers | `aspect={4/3}` or `height={250}` set explicitly |

### D.6 Load Test Scenarios

| Scenario | Setup | Expected |
|---|---|---|
| Cold load (first visit) | Clear cache, slow 3G throttle | Loading shimmer visible, data appears within 5s |
| Warm load (cached) | Pre-populated React Query cache | Instant render, no network request |
| Error recovery | API returns 500 on first attempt, 200 on retry | Error banner shows, retry succeeds |
| Rapid symbol switching | Switch between 5 symbols in 2s | Each transition shows cached data or loading state |
| Low-end device | CPU throttled 6× slowdown | Scrolling is smooth, no jank |

### D.7 Performance Monitoring Checklist

Items to verify during implementation:

- [ ] `useMemo` wraps `chartData` transformation (`annual_totals` → Recharts format)
- [ ] `useMemo` wraps safety ratio cards data
- [ ] `useMemo` wraps badge composition (status + category + policy → 4 badges)
- [ ] `React.memo` on `StatusBadgeRow`, `SafetyRatioCard`, `ChangeTimelineItem`
- [ ] `React.memo` on BarChart and LineChart wrappers
- [ ] No `useState` that triggers full re-render on scroll
- [ ] Charts use fixed `height` (250px) in `ResponsiveContainer`
- [ ] CSS `will-change: transform` on `.glass-panel` (already present)
- [ ] No `setInterval` or polling for dividend data
- [ ] `Suspense` boundary considered for chart-heavy sections (optional)

### D.8 Current Performance Baseline

The existing component already meets key performance requirements:

| Metric | Current Value | Target | Status |
|---|---|---|---|
| React Query stale time | 10 min (`STALE.VALUATION`) | ≥ 5 min | ✅ Already met |
| React Query GC time | 30 min (`GC.VALUATION`) | ≥ 10 min | ✅ Already met |
| `refetchOnWindowFocus` | `false` | `false` | ✅ Already met |
| API fetch timeout | 15s (AbortController) | ≤ 30s | ✅ Already met |
| Number of API calls | 1 per symbol load | 1 | ✅ Already met |
| Backend parallel queries | 10 via `asyncio.gather` | Parallel | ✅ Already met |
| Bundle dependency | Recharts (existing) | No new deps | ✅ Already met |

### D.9 Performance Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Recharts renders twice on mount due to `ResponsiveContainer` resize detection | Medium | Low | Acceptable — React StrictMode double-renders during dev only |
| 12-column grid causes layout thrashing on resize | Low | Medium | Use `will-change: transform` on panels, avoid JS-based layout |
| All 8 safety ratio cards + 2 charts + metric tiles overload single render frame | Low | Medium | If needed, `useDeferredValue` on below-fold sections or `Suspense` with `lazy()` |
| Annual totals with 20+ years of data causes large SVG in chart | Low | Low | Dividend history is typically ≤ 10 years; no pagination needed |
| Backend async gather with 10 queries hits DB connection pool limit | Low | High | Monitor p95 latency; add connection pooling if needed |

---

*End of Document*
