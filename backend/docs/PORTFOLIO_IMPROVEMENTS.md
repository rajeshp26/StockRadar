# StockerPro — Portfolio UI Redesign Spec
### Morningstar-Style Navigation Model · v1.0

> **Document Purpose:** This document captures the full redesign of the Portfolio module from a flat single-page layout into a Morningstar-inspired account-centric navigation model. Each screen is described with its layout, components, data fields, and interaction patterns.

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Proposed Navigation Architecture](#2-proposed-navigation-architecture)
3. [Screen-by-Screen Design Specification](#3-screen-by-screen-design-specification)
4. [Component Library & Design Tokens](#4-component-library--design-tokens)
5. [Interaction Patterns & State Management](#5-interaction-patterns--state-management)
6. [Responsive Design Breakpoints](#6-responsive-design-breakpoints)
7. [Implementation Notes](#7-implementation-notes-stockerpro-stack)
8. [Open Questions & Decisions Needed](#8-open-questions--decisions-needed)

---

## 1. Current State Analysis

### 1.1 Current Layout Overview

The existing portfolio screen is a single, scrollable page combining all accounts, all holdings, and a portfolio-level performance chart into one dense view. While functional, it lacks the account-level drill-down and tabbed analysis that professional investors expect.

### Existing Components (from screenshot)

| Component | Location | Data Shown |
|---|---|---|
| Portfolio Performance Chart | Top section | Portfolio Value vs Net Deposits over time (1D/1W/1M/3M/1Y/YTD/ALL) |
| Net Worth Card | Summary row | $111,291.26 · Cost basis $77,307 |
| Total Gain/Loss Card | Summary row | +$33,984.75 (+43.96%) |
| YTD Dividends Card | Summary row | $2,156.38 (2026 year-to-date) |
| Holdings Count Card | Summary row | 144 across 3 accounts |
| Account Breakdown | Middle section | 3 accounts with value + gain/loss each |
| Holdings List | Bottom section | 144 positions sorted by value, top 10 visible |

### Account Breakdown (current data)

| Account | Broker | Positions | Value (CAD) | Gain/Loss | Return |
|---|---|---|---|---|---|
| TFSA (5ZHK5CAD) | Wealthsimple | 76 | $62,490 | +$18,345 | +41.6% |
| RRSP (K9R43CAD) | Wealthsimple | 34 | $33,207 | +$10,484 | +46.1% |
| Non-Registered (12403CAD) | Wealthsimple | 34 | $15,594 | +$5,156 | +49.4% |
| **TOTAL** | | **144** | **$111,291** | **+$33,984** | **+43.96%** |

### Top Holdings (sorted by market value)

| Ticker | Name | Shares | Price | Market Value | Gain $ | Gain % |
|---|---|---|---|---|---|---|
| TNXP | Tonix Pharmaceuticals | 865.49 | $0.28 | $12,039 | +$11,793 | +4,789.4% |
| DGS | WisdomTree EM SmallCap Div. | 110.00 | $4.96 | $7,062 | +$6,518 | +1,184.4% |
| PLTR (TFSA) | Palantir Technologies | 40.00 | $12.15 | $5,508 | +$5,022 | +1,033.0% |
| HOOD | Robinhood Markets | 67.00 | $10.89 | $5,111 | +$4,381 | +600.3% |
| PLTR (RRSP) | Palantir Technologies | 25.00 | $10.00 | $3,442 | +$3,192 | +1,277.5% |
| ETHY | Purpose Ether Yield ETF | 1,949.00 | $2.23 | $3,040 | -$1,312 | -30.1% |
| T | AT&T Inc. | 120.00 | $20.94 | $3,037 | +$524 | +20.8% |
| PBR | Petróleo Brasileiro | 128.00 | $13.68 | $2,531 | +$810 | +47.1% |
| NFLX | Netflix, Inc. | 73.00 | $7.87 | $2,412 | +$1,837 | +319.6% |
| INTC | Intel Corporation | 19.00 | $45.12 | $2,245 | +$1,388 | +161.9% |

### Pain Points with the Current Design

- All accounts are merged — no way to analyse a single account's performance in isolation
- No tabbed navigation — performance, holdings, and dividends are all on one scrolling page
- Holdings list requires scrolling through 144 positions with no grouping by account
- No dedicated dividend, transactions, or allocation views per account
- The account breakdown section acts as a summary but cannot be drilled into

---

## 2. Proposed Navigation Architecture

### 2.1 Navigation Hierarchy

The redesigned UI adopts a two-level navigation model inspired by Morningstar's portfolio tool:

| Level | Element | Description |
|---|---|---|
| Global | Account Selector (top bar) | Dropdown or tab strip: 'All Accounts', TFSA, RRSP, Non-Registered |
| Account | Tab Bar | Overview · Performance · Holdings · Dividends · Transactions · Allocation |
| Holdings | Holdings Table | Searchable, filterable, sortable list of positions within the selected account |
| Position | Position Detail (future) | Individual stock deep-dive with valuation models |

### 2.2 Account Selector Behaviour

- Persists across all tab views — changing account refreshes all tabs simultaneously
- `All Accounts` is the default on first load, showing aggregated data
- Each account chip shows: account type (TFSA/RRSP/Non-Reg), broker name, and quick value badge
- Active account is highlighted with a filled blue pill; inactive accounts are outlined
- On mobile, the selector collapses into a dropdown with account name + value

### 2.3 Tab Bar Definition

| Tab | Icon | Available For | Core Purpose |
|---|---|---|---|
| Overview | Grid/dashboard | All Accounts + Each Account | At-a-glance summary KPIs and chart |
| Performance | Line chart | All Accounts + Each Account | Return over time, benchmarks, period returns |
| Holdings | List rows | All Accounts + Each Account | Full position list with P&L and sorting |
| Dividends | Dollar coin | All Accounts + Each Account | Dividend income history and projections |
| Transactions | Receipt | Each Account only | Buy/sell/dividend transaction ledger |
| Allocation | Pie chart | All Accounts + Each Account | Sector, geography, asset type breakdown |

---

## 3. Screen-by-Screen Design Specification

### 3.1 Overview Tab — All Accounts

> This is the landing screen — the first thing a user sees after login. It mirrors Morningstar's portfolio summary page.

#### Layout Zones

**Zone A — Page Header**
- Left: `Portfolio` title + subtitle `3 accounts · 144 positions`
- Right: `+ Add Trade` (secondary button) and `Import CSV` (primary button)

**Zone B — Account Selector Strip**
- Horizontally scrollable chip strip: `All Accounts` | `TFSA $62,490` | `RRSP $33,207` | `Non-Registered $15,594`
- Selecting a chip filters all content below

**Zone C — Tab Bar**
- Overview (active) | Performance | Holdings | Dividends | Transactions | Allocation

**Zone D — KPI Summary Cards (4-up)**

| NET WORTH | TOTAL GAIN / LOSS | YTD DIVIDENDS | HOLDINGS |
|---|---|---|---|
| **$111,291.26** | **+$33,984.75** | **$2,156.38** | **144** |
| Cost basis $77,307 | +43.96% all-time | 2026 year-to-date | Across 3 accounts |

**Zone E — Portfolio Performance Mini-Chart**
- Line chart: Portfolio Value (blue/teal) vs Net Deposits (green)
- Time-range selector: `1D` · `1W` · `1M` · `3M` · `1Y` (default) · `YTD` · `ALL`
- Y-axis: 0 → 120k · Grid lines every 30k
- X-axis: date labels (Jun 8 → May 25)
- On hover: tooltip showing date, portfolio value, net deposits, gain/loss at that point

**Zone F — Account Breakdown Table**

| Account | Type | Broker | Positions | Value | Gain/Loss | Return | Actions |
|---|---|---|---|---|---|---|---|
| TFSA | Tax-Free Savings | Wealthsimple | 76 | $62,490 | +$18,345 | +41.6% | View → |
| RRSP | Retirement Savings | Wealthsimple | 34 | $33,207 | +$10,484 | +46.1% | View → |
| Non-Reg | Non-Registered | Wealthsimple | 34 | $15,594 | +$5,156 | +49.4% | View → |

> `View →` links navigate to that account's Overview tab, auto-selecting the account in the selector strip.

---

### 3.2 Overview Tab — Single Account (e.g. TFSA)

#### Differences from All-Accounts Overview

- Account Selector: `TFSA` chip is highlighted; others are dimmed
- Header subtitle changes to: `TFSA (5ZHK5CAD) · Wealthsimple · 76 positions`
- KPI cards reflect only TFSA values:

| ACCOUNT VALUE | TOTAL GAIN | YTD DIVIDENDS | POSITIONS |
|---|---|---|---|
| **$62,490** | **+$18,345** | **—** | **76** |
| TFSA (5ZHK5CAD) | +41.6% all-time | Per-account coming soon | In this account |

- Chart shows only TFSA account value over time (one line, no All Accounts comparison)
- Account Breakdown Table is replaced by a **Top 5 Holdings** mini-table for quick context
- A `See all holdings` link at the bottom routes to the Holdings tab

---

### 3.3 Performance Tab

> Deepens the chart from the Overview. Morningstar equivalent: the 'Returns' tab within a portfolio.

#### A — Time-Range Selector
- Segmented control: `1D` · `1W` · `1M` · `3M` · `6M` · `1Y` · `YTD` · `3Y` · `5Y` · `ALL`
- `1Y` is default

#### B — Benchmark Comparison Toggle
- `+ Compare` dropdown: S&P 500, TSX Composite, NASDAQ, Custom ticker
- When a benchmark is added, a second line appears on the chart (dotted, gold)

#### C — Main Performance Chart
- Large area chart: Portfolio Value (blue fill) vs Net Deposits (green line)
- Optional benchmark overlay (gold dashed line)
- Full-width, taller than the overview mini-chart (min 300px)
- Hover tooltip: date · portfolio value · deposits · absolute gain · % gain

#### D — Period Return Summary Cards

| Period | Return (%) | Absolute ($) | vs Benchmark |
|---|---|---|---|
| 1 Day | +0.42% | +$468 | — |
| 1 Week | +1.8% | +$2,003 | — |
| 1 Month | +3.2% | +$3,561 | — |
| 3 Months | +9.1% | +$10,128 | — |
| 1 Year | +43.96% | +$33,985 | Compare adds this |
| YTD (2026) | +12.4% | +$13,800 | — |
| All-Time | +43.96% | +$33,985 | — |

#### E — Monthly Return Heatmap (optional / future)
- Calendar-style grid: Jan–Dec rows · years as columns
- Green shading = positive month · Red shading = negative month
- Intensity proportional to magnitude of return

---

### 3.4 Holdings Tab

> The primary research and monitoring screen. Equivalent to Morningstar's 'Holdings' view within a portfolio or watchlist.

#### 3.4.1 Toolbar
- Left: Search box (`Filter by ticker or name...`)
- Left: `Group: None ▾` dropdown — options: None, Sector, Asset Type, Account, Country
- Right: `Sort: Value ▾` dropdown — options: Value, Gain %, Gain $, Name, Shares, Price
- Right: View toggle — Table view | Card view (icon buttons)
- Right: Column picker — show/hide optional columns

#### 3.4.2 Holdings Table Columns

| Column | Type | Notes |
|---|---|---|
| Symbol | Text + badge | Ticker with market badge (US, CA, OTHER) and account badge (TFSA, RRSP, NR) |
| Name | Text | Full company name |
| Shares | Number | Quantity held |
| Avg Cost | Currency | Average cost per share |
| Current Price | Currency | Live or delayed price |
| Market Value | Currency (bold) | Shares × Current Price |
| Book Value | Currency | Shares × Avg Cost |
| Gain / Loss $ | Currency (coloured) | Green = profit, Red = loss |
| Gain / Loss % | Percentage (coloured) | Colour-coded same as $ |
| Day Change | Currency + % | Intraday change |
| Weight % | Percentage | % of selected account / portfolio |
| Actions | Icon buttons | View detail, Add to watchlist, Add trade |

#### 3.4.3 Holdings Data (Top 10)

| Symbol | Name | Shares | Price | Value | Gain $ | Gain % | Acct |
|---|---|---|---|---|---|---|---|
| TNXP | Tonix Pharmaceuticals | 865.49 | $0.28 | $12,039 | +$11,793 | +4,789.4% | TFSA |
| DGS | WisdomTree EM SmallCap | 110.00 | $4.96 | $7,062 | +$6,518 | +1,184.4% | OTHER |
| PLTR | Palantir Technologies | 40.00 | $12.15 | $5,508 | +$5,022 | +1,033.0% | TFSA |
| HOOD | Robinhood Markets | 67.00 | $10.89 | $5,111 | +$4,381 | +600.3% | TFSA |
| PLTR | Palantir Technologies | 25.00 | $10.00 | $3,442 | +$3,192 | +1,277.5% | RRSP |
| ETHY | Purpose Ether Yield ETF | 1,949.00 | $2.23 | $3,040 | -$1,312 | -30.1% | TFSA |
| T | AT&T Inc. | 120.00 | $20.94 | $3,037 | +$524 | +20.8% | OTHER |
| PBR | Petróleo Brasileiro | 128.00 | $13.68 | $2,531 | +$810 | +47.1% | OTHER |
| NFLX | Netflix, Inc. | 73.00 | $7.87 | $2,412 | +$1,837 | +319.6% | RRSP |
| INTC | Intel Corporation | 19.00 | $45.12 | $2,245 | +$1,388 | +161.9% | NR |

_Total shown: 10 of 144 · `Show all 144` button loads full paginated list_

---

### 3.5 Dividends Tab

> Modelled on Morningstar's dividend income view, showing income received and projected forward income.

#### 3.5.1 KPI Summary Row

| YTD RECEIVED | PROJECTED ANNUAL | YIELD ON COST | PAYING POSITIONS |
|---|---|---|---|
| **$2,156.38** | **—** | **—** | **—** |
| Jan 1 – today (2026) | Based on current holdings | Annual income / book value | # of dividend-paying stocks |

#### 3.5.2 Dividend Calendar Chart
- Bar chart: monthly dividend income bars for the trailing 12 months
- X-axis: months · Y-axis: income ($)
- Hover: list of dividends received in that month with ticker and amount
- Toggle: `Received` vs `Projected` — projected uses forward yield estimates

#### 3.5.3 Dividend History Table

| Date | Ticker | Name | Shares | Amount/Share | Total Received | Account |
|---|---|---|---|---|---|---|
| Most recent first | From holdings | Full name | Held at ex-div | Per-share rate | Net income | TFSA / RRSP / NR |

> **Withholding Tax Note:** US dividends held in non-registered accounts are subject to 15% US withholding tax. TFSA and RRSP accounts are WHT-exempt for US dividends under the Canada-US tax treaty.

---

### 3.6 Transactions Tab — Per-Account Only

> Not shown in the All Accounts view. Selecting a specific account reveals this tab. Shows a full ledger of all activity.

#### 3.6.1 Toolbar
- Date range picker (default: last 90 days)
- Type filter: `All` | `Buy` | `Sell` | `Dividend` | `Deposit` | `Withdrawal` | `Fee`
- Search by ticker
- Export to CSV button

#### 3.6.2 Transaction Table Columns

| Column | Notes |
|---|---|
| Date | Transaction settlement date |
| Type | Badge: BUY (green) · SELL (red) · DIV (teal) · DEP (blue) · WD (orange) |
| Ticker / Asset | Symbol + name; empty for deposits/withdrawals |
| Shares / Units | Quantity bought or sold; blank for cash transactions |
| Price | Per-share price at execution |
| Total Value | Shares × Price + fees |
| Fees | Commission or FX fees |
| Running Balance | Account value after the transaction |
| Notes | User-editable memo field |

---

### 3.7 Allocation Tab

> Shows how the portfolio (or account) is distributed by sector, geography, asset class, and account type.

#### 3.7.1 Allocation Breakdown Views

The tab contains four sub-sections, each with a donut chart and supporting table:

| Sub-Section | Grouping Key | Example Segments |
|---|---|---|
| By Sector | GICS Sector | Technology, Energy, Health Care, Financials, ETF/Fund, Crypto |
| By Geography | Country of listing / domicile | USA, Canada, Brazil, UK, EM-Other |
| By Asset Class | Security type | Equities, ETFs, Crypto, REITs, Bonds |
| By Account | Account type | TFSA 56%, RRSP 30%, Non-Reg 14% |

#### 3.7.2 Chart + Table Layout
- Left: animated donut/pie chart with colour-coded segments and hover tooltips
- Right: breakdown table — Segment · Value ($) · Weight (%) · # Positions · Gain/Loss
- Clicking a segment in the chart filters the Holdings tab to show only those positions

---

## 4. Component Library & Design Tokens

### 4.1 Account Selector Chip

| State | Background | Border | Label | Value Badge |
|---|---|---|---|---|
| Default (unselected) | Transparent / #1A2B4A10 | 1px #374151 | Account name | Subtle grey |
| Active (selected) | #2563EB | None | Account name (white bold) | White bold |
| Hover | #2563EB20 | 1px #2563EB | Account name | Blue |
| All Accounts default | #F3F4F6 | 1px #CCCCCC | 'All Accounts' | Total value |

### 4.2 Tab Bar

| State | Text | Indicator |
|---|---|---|
| Active | Bold, #2563EB | 2px bottom border, #2563EB |
| Inactive | Regular, #6B7280 | None |
| Hover | Regular, #1A2B4A | 2px bottom border, #A0AEC0 |
| Disabled | Regular, #D1D5DB | None — shown when tab not applicable |

### 4.3 KPI Card Anatomy
- Background: glass card — `rgba(255,255,255,0.05)` with `1px border #E5E7EB`
- Label: uppercase, 11px, `#6B7280`
- Value: 24–28px bold, colour-coded (navy = neutral, green = positive, red = negative)
- Sub-label: 13px, `#9CA3AF`
- Hover: subtle elevation shadow

### 4.4 Colour Palette

| Name | Hex | Usage |
|---|---|---|
| Navy | `#1A2B4A` | Primary headings, account selector background, table headers |
| Blue | `#2563EB` | Active states, links, primary CTA buttons |
| Teal | `#0D9488` | Secondary metrics, dividend indicators |
| Green | `#16A34A` | Positive gain/loss, buy indicators |
| Red | `#DC2626` | Negative gain/loss, sell indicators, warnings |
| Gold | `#D97706` | Benchmarks, warning states |
| Dark Grey | `#374151` | Body text, secondary labels |
| Mid Grey | `#6B7280` | Tertiary labels, inactive tabs |
| Light Grey | `#F3F4F6` | Alternating table rows, card backgrounds |
| White | `#FFFFFF` | Active chip text, table header text |

### 4.5 Typography Scale

| Role | Size | Weight | Colour |
|---|---|---|---|
| Page Title | 32–36px | Bold (700) | `#1A2B4A` |
| Section Heading (H2) | 24–28px | Bold (700) | `#2563EB` |
| Sub-heading (H3) | 18–20px | SemiBold (600) | `#374151` |
| KPI Value | 26–28px | Bold (700) | Context-dependent |
| Table Header | 11–12px | Bold (700) | UPPERCASE, `#FFFFFF` or `#6B7280` |
| Table Body | 13–14px | Regular (400) | `#111827` |
| Labels / Captions | 11–12px | Regular / SemiBold | `#6B7280` |

---

## 5. Interaction Patterns & State Management

### 5.1 Account Selection Flow

| User Action | System Response |
|---|---|
| Clicks 'TFSA' chip | All tabs re-render with TFSA-scoped data; URL updates to `?account=TFSA` |
| Clicks 'All Accounts' | All tabs aggregate all three accounts; URL params cleared |
| Navigates to a tab | Active account selection persists; tab state is URL-encoded (`?tab=holdings`) |
| Deep-links via URL | Account selector and active tab both restore from URL params |
| Clicks 'View →' in breakdown table | Navigates to that account's Overview tab |

### 5.2 Holdings Table Interactions
- Column headers are clickable to sort (ascending → descending → original)
- Sort state persists within the session for that tab
- `Group by Sector` inserts collapsible group header rows — click to collapse/expand
- Row click navigates to the Position Detail page (if implemented)
- Inline action icons: ⭐ Add to watchlist · ✏️ Add trade · 🔗 View on broker

### 5.3 Performance Chart Interactions
- Hover scrubber: vertical line snaps to nearest data point; tooltip shows all values at that date
- Click + drag to zoom into a sub-range; double-click to reset
- `+ Compare` adds a benchmark — comparison persists across time-range changes
- Time-range buttons are mutually exclusive; selecting a range animates the chart transition

### 5.4 Loading & Empty States

| State | Treatment |
|---|---|
| Loading (initial) | Skeleton shimmer on cards and chart; table rows replaced by grey bars |
| Loading (tab switch) | Spinner in tab content area; account selector stays active |
| Empty account | "No positions found. Import a CSV or add a trade to get started." |
| No dividends | "This account has no dividend history. Dividend-paying holdings will appear here." |
| No transactions | "No transactions found for the selected period. Try expanding the date range." |
| Error / API failure | Inline error banner with retry button; stale data shown with yellow badge |

---

## 6. Responsive Design Breakpoints

| Breakpoint | Width | Account Selector | Tab Bar | Holdings Table | KPI Cards |
|---|---|---|---|---|---|
| Desktop | ≥ 1280px | Chip strip (full) | Full horizontal | All columns visible | 4-up row |
| Laptop | 1024–1279px | Chip strip (scroll) | Full horizontal | Hide Day Change, Weight | 4-up row |
| Tablet | 768–1023px | Chip strip (scroll) | Scrollable | Symbol, Value, Gain only | 2×2 grid |
| Mobile | < 768px | Dropdown selector | Horizontal scroll | Symbol + Value (tap to expand) | Stack vertical |

---

## 7. Implementation Notes (StockerPro Stack)

### 7.1 Frontend (Next.js 15 + React 19)

| Feature | Recommended Approach |
|---|---|
| Account Selector | React context + URL search params (`?account=TFSA`) via `useSearchParams` |
| Tab Navigation | Next.js App Router parallel routes or shadcn/ui `Tabs` component |
| KPI Cards | React Server Components for static layout; client hydration for live values |
| Performance Chart | Recharts `AreaChart` with `ResponsiveContainer`; custom `Tooltip` component |
| Holdings Table | TanStack Table v8 (already in stack via React Query); virtualised for 144+ rows |
| Allocation Charts | Recharts `PieChart` or `RadialBarChart` for donut style |
| Data Fetching | TanStack React Query v5 (`useQuery` per tab + account); stale-while-revalidate |
| State / URL Sync | `nuqs` library for type-safe URL search params with React state binding |

### 7.2 Backend API Endpoints (FastAPI + Supabase)

| Endpoint | Method | Query Params | Response |
|---|---|---|---|
| `/portfolio/summary` | GET | `account_id` (optional) | KPIs: net_worth, gain_loss, ytd_dividends, holdings_count |
| `/portfolio/performance` | GET | `account_id`, `period` (1D–ALL) | Time-series `[{date, value, deposits}]` |
| `/portfolio/holdings` | GET | `account_id`, `sort`, `group` | Paginated positions with P&L |
| `/portfolio/dividends` | GET | `account_id`, `year` | Dividend history + projected annual |
| `/portfolio/transactions` | GET | `account_id`, `from`, `to`, `type` | Paginated transaction ledger |
| `/portfolio/allocation` | GET | `account_id`, `group_by` | Segment breakdown `[{name, value, weight, count}]` |

### 7.3 Supabase Query Patterns
- Account filter: `WHERE account_id = $1 OR $1 IS NULL` (NULL = All Accounts)
- Holdings join: `JOIN companies ON ticker` · `JOIN financial_ratios ON company_id` for sector data
- Performance series: aggregate daily closing values from `market_data` table grouped by date
- Allocation: `GROUP BY sector / country / security_type` with `SUM(market_value)`
- Transactions: `ORDER BY settled_at DESC` with cursor-based pagination

### 7.4 Phased Delivery

| Phase | Scope | Priority |
|---|---|---|
| Phase 1 | Account Selector + tab shell (URL routing) + Overview tab refactor | 🔴 High |
| Phase 2 | Performance tab with chart and period cards | 🔴 High |
| Phase 3 | Holdings tab refactor with TanStack Table, grouping, and sorting | 🔴 High |
| Phase 4 | Dividends tab with calendar chart and history table | 🟡 Medium |
| Phase 5 | Transactions tab with ledger and filters | 🟡 Medium |
| Phase 6 | Allocation tab with donut charts | 🟢 Lower |
| Phase 7 | Mobile responsive passes and breakpoint polish | 🟢 Lower |

---

## 8. Open Questions & Decisions Needed

| # | Question | Options | Owner |
|---|---|---|---|
| 1 | Should PLTR appear twice in Holdings (once per account) or merged with a tooltip showing split? | A) Two rows  B) Merged row with account breakdown on hover | Product |
| 2 | Should 'All Accounts' be the permanent default or should the app remember the last-selected account per user? | A) Always default All  B) Remember last selection via localStorage | Product |
| 3 | What is the data source for projected annual dividend yield? DefeatBeta / yfinance? | A) yfinance `.info['dividendYield']`  B) DefeatBeta field  C) Manual entry | Engineering |
| 4 | Should Transactions tab be surfaced for All Accounts (merged ledger) or restricted to single-account? | A) Per-account only  B) Also show merged All Accounts ledger | Product |
| 5 | Currency: are all values in CAD or does the app show USD positions in USD with a CAD total? | A) Normalise to CAD  B) Show native currency per position with CAD total | Product |
| 6 | Are there plans to add additional brokers beyond Wealthsimple, and how will multi-broker holdings of the same ticker be handled? | A) Single broker  B) Multi-broker: account_id distinguishes same-ticker holdings | Product |

---

_End of document — StockerPro Portfolio UI Redesign Spec v1.0_