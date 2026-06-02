# Portfolio Analysis — Information Architecture & Visual Design Guide

---

## 1. The Problem: Redundancies in the Current 7-Page Structure

The original page set — **Overview, Performance, Holdings, Dividends, Transactions, Allocation, Risk** — contains three structural overlaps that cause user confusion and duplicated development effort.

| Overlap | Pages Involved | Issue |
|---|---|---|
| Return numbers | Overview ↔ Performance | Two places show the same P&L and return figures |
| Position data | Holdings ↔ Allocation | Same underlying data, split across two nav items |
| Risk metrics | Risk ↔ Performance ↔ Holdings | Beta, concentration, and drawdown scattered across pages |

---

## 2. Recommended Structure: 6 Pages

Merge **Holdings + Allocation** into one page. Tighten the scope of the remaining pages so each owns its content exclusively.

```
Overview → Performance → Holdings & Allocation → Dividends → Transactions → Risk
```

---

## 3. Page-by-Page Content Ownership

### 3.1 Overview — "Right Now"
**Purpose:** Fastest page to parse. Answers: *how am I doing today?*

**Own:**
- Total portfolio value (large, prominent)
- Today's P&L (dollar + percentage)
- Top movers (3–5 positions, gainers and losers)
- Mini sparkline — 7-day or 30-day only
- Alerts and notable news for held positions

**Do not include:**
- Historical performance charts (belongs in Performance)
- Allocation pie or treemap (belongs in Holdings & Allocation)
- Any metric that requires more than a glance to understand

> **Visual priority:** One number should dominate the page. Everything else is supporting context.

---

### 3.2 Performance — "How I've Done Over Time"
**Purpose:** Deep analytical view of all return history. Answers: *am I beating the market?*

**Own:**
- Time-weighted return (TWR) and money-weighted return (MWR)
- Benchmark comparison (S&P 500, custom index)
- Alpha and beta relative to benchmark
- Rolling returns (1M, 3M, 6M, 1Y, 3Y, 5Y)
- Cumulative return chart with benchmark overlay
- Drawdown chart (peak-to-trough periods)
- Best / worst periods table

**Do not include:**
- Beta is a *performance characteristic* — it lives here, not in Risk
- Position-level P&L belongs in Holdings, not here

> **Visual priority:** One primary chart (cumulative returns vs benchmark) should anchor the page. All other charts are secondary.

---

### 3.3 Holdings & Allocation — "What I Own"
**Purpose:** Two views of the same data — tabular and visual. Answers: *what am I exposed to?*

**Own (Table view — Holdings):**
- Symbol, company name, sector
- Shares held, average cost, current price
- Market value, unrealized gain/loss ($ and %)
- Weight in portfolio (%)

**Own (Visual view — Allocation):**
- Sector treemap or pie chart
- Geographic allocation (US, International, EM)
- Asset class breakdown (equities, fixed income, cash)
- Top 10 concentration chart

**Interaction model:**
- Toggle between Table and Visual at the top of the page
- Or use a split-panel layout (table left, charts right) on wide screens

**Do not include:**
- Concentration risk score belongs here, not in Risk
- Cost-basis lots (transaction-level detail) belong in Transactions

> **Visual priority:** The toggle/tab between views should be the most visible UI element. On wide screens, show both simultaneously.

---

### 3.4 Dividends — "My Income Stream"
**Purpose:** Everything income-related in one place. Answers: *when do I get paid and how safe is it?*

**Own:**
- Upcoming dividend calendar (next 90 days)
- Annual projected income
- Yield on cost vs current yield
- Payout ratio and coverage (safety score)
- Dividend growth history per holding (CAGR 1Y, 3Y, 5Y)
- Ex-dividend date tracker

> **Visual priority:** The income calendar is the hero element. Safety scores should use clear visual encoding (green/amber/red) without requiring the user to read numbers.

---

### 3.5 Transactions — "What Happened"
**Purpose:** A complete ledger of activity. Answers: *what did I buy, sell, and realize?*

**Own:**
- Trade history (date, action, symbol, quantity, price, total)
- Realized gains and losses (short-term vs long-term)
- Cost-basis lots (FIFO, LIFO, specific lot)
- Tax-year summary (total realized, estimated tax impact)
- Dividend payments received (as transactions)
- Deposit / withdrawal history

> **Visual priority:** Filterable, sortable table is the core. Date range picker and symbol/type filters should be immediately visible, not hidden in a menu.

---

### 3.6 Risk — "What Could Go Wrong"
**Purpose:** Exclusive home for risk analytics not derivable from return history or position size. Answers: *how bad could it get?*

**Own:**
- Value at Risk (VaR) — 95% and 99% confidence, 1-day and 10-day
- Conditional VaR (CVaR / Expected Shortfall)
- Correlation matrix across holdings
- Drawdown scenario analysis (2008, 2020, custom)
- Stress test results (rate shock, sector crash, currency move)
- Portfolio volatility vs benchmark volatility

**Do not include:**
- Beta → Performance page
- Sector concentration → Holdings & Allocation
- Individual position drawdown → Holdings or Performance

> **Visual priority:** The correlation matrix is the hardest element to read — use a heatmap with clear color scale, not raw numbers. Scenario results should show dollar impact prominently, not just percentages.

---

## 4. Visual Design Principles Per Page

### 4.1 Information Hierarchy Rules

Every page should have exactly three levels of visual weight:

```
Level 1 — Hero metric    : largest, highest contrast, one per page
Level 2 — Supporting KPIs: medium size, grouped, scannable
Level 3 — Detail / table : smallest, dense, accessible on demand
```

### 4.2 Chart Type Guide

| Data Type | Recommended Chart | Avoid |
|---|---|---|
| Return over time | Line chart with benchmark overlay | Bar chart |
| Portfolio composition | Treemap (>6 items) or Pie (≤5 items) | Stacked bar |
| Drawdown periods | Area chart, filled below zero | Line only |
| Correlation matrix | Heatmap | Table of numbers |
| Dividend calendar | Timeline / calendar grid | List |
| Rolling returns | Small multiples (sparklines) | Single crowded line |
| P&L per position | Horizontal bar (sorted) | Unsorted table |
| VaR distribution | Histogram with tail shading | Single number |

### 4.3 Color Encoding — Use Consistently Across All Pages

| Meaning | Color |
|---|---|
| Positive / gain | Green |
| Negative / loss | Red |
| Neutral / unchanged | Gray |
| Benchmark / reference | Blue (muted) |
| Portfolio / primary | Your brand accent |
| Warning / watch | Amber |
| Danger / high risk | Red (same as loss) |

> **Rule:** Never use green/red for anything other than gain/loss. Reserve them strictly so users build intuition fast.

### 4.4 Density Guidelines

| Page | Density | Reason |
|---|---|---|
| Overview | Low | Glanceable, daily use |
| Performance | Medium | Research mode, time spent |
| Holdings & Allocation | Medium–High | Both table and visual needed |
| Dividends | Medium | Calendar + table |
| Transactions | High | It is a ledger — density is appropriate |
| Risk | Medium | Complex concepts need breathing room |

---

## 5. Navigation Design

### Recommended Tab Order
```
[Overview]  [Performance]  [Holdings & Allocation]  [Dividends]  [Transactions]  [Risk]
```

### Mobile Considerations
- On mobile, **Holdings & Allocation** should default to the visual view (treemap/pie), not the table
- **Transactions** should show the last 10 by default with a "load more" — never paginate
- **Risk** correlation matrix should collapse to a ranked list on narrow screens

---

## 6. Cross-Page Linking (Contextual Drilldown)

Reduce redundancy further by linking between pages instead of duplicating data:

| From | Trigger | To |
|---|---|---|
| Overview — top mover | Click position | Holdings row for that symbol |
| Performance — drawdown period | Click period | Risk — scenario matching that date range |
| Holdings — position row | Click "risk" icon | Risk — filtered to that symbol's correlation |
| Dividends — upcoming payment | Click | Transactions — pre-filtered to that symbol |
| Risk — scenario result | Click | Performance — chart zoomed to that period |

---

## 7. Summary: What Changed and Why

| Decision | Rationale |
|---|---|
| Merge Holdings + Allocation | Same data, two views — one nav item with a toggle is cleaner |
| Strip Overview of history | Overview should be < 3 seconds to parse; charts require attention |
| Move beta to Performance | Beta is a return characteristic, not a standalone risk metric |
| Move concentration to Holdings | Concentration is a position characteristic, not a tail-risk metric |
| Keep Dividends standalone | Income analysis has a distinct workflow and calendar-based UX |
| Keep Transactions standalone | Ledger UX is categorically different from analytical views |
| Scope Risk to VaR + correlation + scenarios | These are the only metrics with no better home elsewhere |