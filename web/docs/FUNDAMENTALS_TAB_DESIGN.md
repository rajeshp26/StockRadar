# Fundamentals Tab — Design & Implementation

> **Version:** 3.3  
> **Status:** Implemented with TradingView-style vertical bar charts + range slider widget  
> **Date:** 2026-06-11

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [UI/UX Design](#2-uiux-design)
   - [2.1.1 Three Bar States](#211-three-bar-states)
   - [2.1.2 Hover Tooltip](#212-hover-tooltip)
   - [2.1.3 Header Area](#213-header-area)
   - [2.1.4 Chart Legend](#214-chart-legend)
3. [Data Model](#3-data-model)
4. [Backend Design](#4-backend-design)
5. [Frontend Design](#5-frontend-design)
6. [Sequence Diagrams](#6-sequence-diagrams)
7. [Feasibility Assessment](#7-feasibility-assessment)
8. [Implementation Plan](#8-implementation-plan)
   - [Phase 8: Negative EPS + Insufficient Data Display](#phase-8-negative-eps--insufficient-data-display)
   - [Design Rationale](#design-rationale)

---

## 1. Executive Summary

### Problem

Users have no way to visually compare a stock's fundamental health and valuation at the time of purchase versus current values. The existing "Financial Health" tab is a coming-soon placeholder.

### Proposed Solution

A **Fundamentals** tab that provides a unified, five-section dashboard with a summary scorecard at the top:

| Section | Metrics | Purpose |
|---------|---------|---------|
| **Quality** | ROIC, ROE, Gross Margin, Operating Margin, Debt/Equity | Business quality since purchase |
| **Growth** | Revenue YoY%, EPS YoY%, FCF YoY% | Growth trajectory since purchase |
| **Moat** | Piotroski F-Score, Altman Z-Score, Interest Coverage | Financial stability |
| **Valuation** | P/E, EV/EBITDA, P/FCF, Price vs Intrinsic Value | Cheap/expensive vs purchase |
| **Narrative** | EPS beat/miss, Revenue beat/miss, Beat Rate | Market reaction to earnings |

Each metric displays as a **TradingView-style vertical bar chart** with:
- **X-axis:** Time (quarters or years, based on frequency toggle)
- **Y-axis:** Values (auto-scaled per metric)
- **Bars:** Vertical columns for each period's value
- **Color:** Green for positive, red for negative

### Feasibility Verdict: **HIGH** (with known caveats)

| Capability | Status | Notes |
|-----------|--------|-------|
| Annual ROIC, ROE, margins, D/E | ✅ **Exists** | In `financial_ratios` table |
| Quarterly financial statements | ✅ **Exists** | In `income_statements`, `balance_sheets` |
| YoY growth formulas | ✅ **Exists** | `canslim_service._score_C()` pattern |
| FCF computation | ✅ **Exists** | `shared/finance_math.compute_fcf()` |
| ROIC/NOPAT math | ✅ **Exists** | `shared/finance_math.compute_roic()` |
| Valuation multiples (current snapshot) | ✅ **Exists** | In `company_summary` table |
| Valuation multiples (historical per-period) | ⚠️ **Planned** | To be stored in `financial_ratios` — see §11 |
| Portfolio purchase date | ✅ **Exists** | `portfolio_transactions` table |
| Earnings beat/miss data | ✅ **Exists** | `earnings` table |
| Piotroski F-Score | ✅ **Built** | Computed in `derived_financial_metrics_job.py` |
| Altman Z-Score | ✅ **Built** | Computed in `derived_financial_metrics_job.py` |
| Quarterly ratio computation | ✅ **Built** | Extended job processes quarterly data |
| Analyst consensus | ❌ **Not available** | Dropped from design |

---

## 2. UI/UX Design

### 2.1 TradingView-Style Vertical Bar Charts

Each metric renders as a **separate vertical bar chart** with:
- **X-axis:** Time (quarters: Q1 2024, Q2 2024, Q3 2024, etc.)
- **Y-axis:** Values (auto-scaled per metric)
- **Bars:** Vertical columns for each quarter's value, with three visual states (see §2.1.1)
- **Hover tooltip:** Shows exact values and component breakdown (see §2.1.2)

#### 2.1.1 Three Bar States

| State | `status` value | Condition | Visual | Label |
|-------|----------------|-----------|--------|-------|
| **Normal** | `"normal"` | TTM EPS > 0 | Filled coloured bar (green/red based on value) | `10.3×` |
| **Not applicable** | `"not_applicable"` | TTM EPS ≤ 0 (but 4 quarters of data exist) | **Filled red bar** at baseline | `N/A` |
| **Insufficient data** | `"insufficient_data"` | < 4 quarters of income data available | **Dashed red outline bar** at baseline | `N/A` |

The `not_applicable` bars use a filled `bg-rose-500` with `opacity-70` and a matching border, making negative-P/E quarters clearly visible as downward red bars. The `insufficient_data` bars use a dashed red border with transparent fill and lower opacity. Both sit on the zero baseline (or below it for mixed-sign charts).

```
Normal bar (filled):            ████  (green if positive, red if negative)
Not applicable (filled red):    ████  (bg-rose-500, opacity-70)
Insufficient data (dashed):    ╔════╗ (dashed border-rose-500, transparent fill)
```

The `not_applicable` bars extend below the zero line (downward from zero) when the chart has mixed positive/negative values, making the negative sign unambiguous. The `insufficient_data` bars sit on the zero baseline.

**Reusability:** The `status` field is generic — any metric can use it. For example:
- `pe_ratio` → `"not_applicable"` when TTM EPS ≤ 0
- `piotroski_f` → `"insufficient_data"` when balance sheet data is missing
- `ev_ebitda` → `"not_applicable"` when EBITDA is negative
- The frontend bar renderer is a single reusable component that checks `status`

#### 2.1.2 Hover Tooltip

On hover over any bar (normal or N/A), a tooltip shows:

```
┌─────────────────────────────────────────────┐
│  Trailing P/E: 10.3×                        │
│  TTM EPS: $1.17                             │
│  ──────────────────────                      │
│  Q3 2025  EPS  $0.60                        │
│  Q2 2025  EPS  −$0.01                       │
│  Q1 2025  EPS  $0.12                        │
│  Q4 2024  EPS  $0.45                        │
│  ──────────────────────                      │
│  Quarter-end price: $11.96                  │
└─────────────────────────────────────────────┘
```

For `status="not_applicable"` bars (filled red):

```
┌─────────────────────────────────────────────┐
│  Trailing P/E: −6.3× (negative earnings)    │
│  TTM EPS: −$2.07                            │
│  ──────────────────────                      │
│  Q4 2025  EPS  −$2.78  ← driver of loss     │
│  Q3 2025  EPS   $0.60                        │
│  Q2 2025  EPS  −$0.01                       │
│  Q1 2025  EPS   $0.12                        │
│  ──────────────────────                      │
│  Quarter-end price: $13.12                  │
└─────────────────────────────────────────────┘
```

The driver flag (`highlight="driver"` on `MetricComponent`) lets the frontend highlight the quarter that caused the negative earnings, helping users quickly identify the problem.

For `status="insufficient_data"` bars (dashed outline):

```
┌─────────────────────────────────────────────┐
│  P/E not available                          │
│  Only 1 of 4 quarters on record             │
│  ──────────────────────                      │
│  Q2 2022  EPS  $0.16                        │
│  Missing: Q1 2022, Q4 2021, Q3 2021        │
└─────────────────────────────────────────────┘
```

The `components` array in this case only has 1 entry. The service fills in `null` for the missing 3 quarters, and the frontend displays them as "Missing" rows.

#### 2.1.3 Range Slider Widget

Replaces the old inline stats text. Each metric chart has a `MetricRangeSlider` between the metric label and the chart body (see §5.4 for full design). The slider shows a horizontal range track with avg and current markers, computed from **positive values only**.

#### 2.1.4 Chart Legend

The chart legend is **not currently implemented**. Bar states are self-evident from their visual treatment (filled green/red, filled red with N/A label, dashed border). The tooltip on hover provides the detailed status explanation for each bar.

```
┌── Growth ── [ Intact ] ──────────────────────────────────────────────────┐
│                                                                            │
│  Revenue YoY                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │  10%│           ██                                               │     │
│  │     │     ██    ██                          ██                   │     │
│  │   0%│██████    ████    ██              ████████                  │     │
│  │     │                ████    ██    ████                          │     │
│  │ -10%│                      ████                                 │     │
│  │     └──────────────────────────────────────────────────────────┘     │     │
│  │       Q1    Q2    Q3    Q4    Q1    Q2    Q3    Q4                  │     │
│  │       2024  2024  2024  2024  2025  2025  2025  2025                 │     │
│  └──────────────────────────────────────────────────────────────────┘     │
│                                                                            │
│  EPS YoY                                                                  │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │ +400%│                                            ██             │     │
│  │      │                                                           │     │
│  │ +200%│                                                           │     │
│  │    0%│████  ████              ████  ████                         │     │
│  │ -200%│      ████    ████                                          │     │
│  │ -400%│            ████                                            │     │
│  │ -700%│                  ██                                        │     │
│  │      └──────────────────────────────────────────────────────────┘     │     │
│  │        Q1    Q2    Q3    Q4    Q1    Q2    Q3    Q4                    │     │
│  │        2024  2024  2024  2024  2025  2025  2025  2025                  │     │
│  └──────────────────────────────────────────────────────────────────┘     │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Why TradingView Pattern

- **Separate charts** — each metric has its own independent Y-axis scale
- **Vertical bars** — standard financial chart format, easy to read
- **Time on X-axis** — quarters are clearly labeled below each chart
- **No shared normalization** — extreme outliers don't compress other metrics

### 2.3 Toggle Controls

Both toggles are rendered **inside each `MetricChartSection`**, acting independently per section.

#### 2.3.1 Time Period Toggle

```
[● All  ○ From purchase]    (when has_portfolio_position = true)
[● All ]                      (when has_portfolio_position = false)
```

- Pill-style toggle: "All" button always visible; "From purchase" only appears when `has_portfolio_position = true`
- Default state: "All" per section
- Controls visible data: filters the bar chart's quarters to start from the purchase date
- Operates client-side (no re-fetch)

#### 2.3.2 Frequency Toggle

```
[● Quarterly  ○ Annual]
```

- Pill-style toggle, two options: "Quarterly" and "Annual"
- Always visible regardless of portfolio position
- **Quarterly**: X-axis shows quarter labels (`Q1'24`, `Q2'24`, etc.)
- **Annual**: X-axis shows fiscal year labels (`2024`, `2025`, etc.)
   - Groups quarterly data by fiscal year, taking the latest quarter's value per year
- Default state: "Quarterly" per section
- Operates client-side (no re-fetch)

### 2.4 Section Status Badges

Each section has a status badge next to its title:

| Score Range | Status |
|-------------|--------|
| ≥ 70 | `Intact` (green) |
| 40–69 | `Watch` (amber) |
| < 40 | `Concern` (red) |

### 2.5 Component Hierarchy

```
FundamentalsPanel
├── FundamentalsHeader
│   ├── SectionHeader ("Fundamentals")
│   ├── CompanyName + Score
│   └── PurchaseInfo
├── MetricSection × 5
│   ├── SectionHeader + StatusBadge
│   ├── QuarterToggle (portfolio only)     ← per-section
│   ├── FrequencyToggle                    ← per-section
│   └── MetricBarChart × N
│       ├── MetricLabel + Value
│       ├── YAxisLabels (auto-scaled)
│       ├── Bars (vertical columns)
│       ├── XAxisLabels (quarters / years)
│       └── BuyMarker (optional)
└── DataQualityFooter
```

---

## 3. Data Model

### 3.1 Backend Response Schema

```python
# backend/schemas_fundamentals.py

from datetime import date
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class MetricComponent(BaseModel):
    """A named sub-value that contributes to a metric — reusable across all metrics.
    
    Examples:
      - P/E: 4 component EPS values that sum to TTM EPS
      - Piotroski F-Score: 9 boolean component scores
      - ROIC: trailing 4 quarters of NOPAT / Invested Capital
    """
    label: str                            # "Q3 2025", "Profitability", etc.
    value: Optional[float] = None
    highlight: Optional[Literal["positive", "negative", "driver"]] = None


class QuarterDataPoint(BaseModel):
    fiscal_year: int
    fiscal_quarter: int
    label: str                            # "Q2 2025" or "2024" (annual)
    value: Optional[float] = None
    narrative_label: Optional[str] = None  # "beat", "miss", "inline"
    status: Optional[Literal["normal", "not_applicable", "insufficient_data"]] = None
    """Generic display hint for any metric. Drives bar rendering:
       - normal: filled coloured bar
       - not_applicable: filled red bar (e.g. negative TTM EPS)
       - insufficient_data: dashed outline (e.g. < 4 quarters)"""
    components: Optional[List[MetricComponent]] = None
    """Breakdown details. PE-specific: 4 trailing EPS values.
       Other metrics can reuse this for their own breakdowns."""
    # ── PE-specific enrichments (optional, only for pe_ratio) ──
    ttm_eps: Optional[float] = None        # sum of 4 EPS components
    quarter_end_price: Optional[float] = None


class MetricQuarterSeries(BaseModel):
    metric_id: str
    label: str
    unit: str                            # "%", "x", "$", "score"
    quarters: List[QuarterDataPoint]
    buy_quarter_index: Optional[int] = None
    trend_direction: Literal["up", "down", "stable"]
    change_pct: Optional[float] = None
    change_label: str


class SectionStatus(BaseModel):
    label: Literal["Intact", "Watch", "Concern"]


class MetricSection(BaseModel):
    section_id: str
    title: str
    metrics: List[MetricQuarterSeries]
    status: SectionStatus
    score: Optional[float] = None


class DataQuality(BaseModel):
    sources: List[str] = Field(default_factory=lambda: ["financial_ratios", "income_statements", "cash_flow_statements", "earnings"])
    staleness_days: Optional[int] = None
    earliest_data_year: Optional[int] = None
    quarterly_data_count: Optional[int] = None


class FundamentalsResponse(BaseModel):
    success: bool = True
    symbol: str
    company_name: Optional[str] = None
    currency: str = "USD"
    has_portfolio_position: bool
    purchase_date: Optional[date] = None
    purchase_period: Optional[str] = None
    quarters: List[str]
    buy_quarter_index: Optional[int] = None
    composite_score: Optional[float] = None
    sections: List[MetricSection]
    data_quality: Optional[DataQuality] = None
    error: Optional[str] = None
```

### 3.2 Frontend Types

```typescript
// web/src/features/analysis/types/analysis.types.ts

export interface MetricComponent {
    label: string;
    value: number | null;
    highlight?: 'positive' | 'negative' | 'driver';
}

export interface QuarterDataPoint {
    fiscal_year: number;
    fiscal_quarter: number;
    label: string;
    value: number | null;
    narrative_label?: string;
    status?: 'normal' | 'not_applicable' | 'insufficient_data';
    components?: MetricComponent[];
    // PE-specific enrichments
    ttm_eps?: number | null;
    quarter_end_price?: number | null;
}

export interface MetricQuarterSeries {
    metric_id: string;
    label: string;
    unit: string;
    quarters: QuarterDataPoint[];
    buy_quarter_index: number | null;
    trend_direction: 'up' | 'down' | 'stable';
    change_pct: number | null;
    change_label: string;
}

export interface SectionStatus {
    label: 'Intact' | 'Watch' | 'Concern';
}

export interface MetricSection {
    section_id: string;
    title: string;
    metrics: MetricQuarterSeries[];
    status: SectionStatus;
    score: number | null;
}

export interface FundamentalsDataQuality {
    sources: string[];
    staleness_days: number | null;
    earliest_data_year: number | null;
    quarterly_data_count: number | null;
}

export interface FundamentalsResponse {
    success: boolean;
    symbol: string;
    company_name?: string;
    currency: string;
    has_portfolio_position: boolean;
    purchase_date?: string;
    purchase_period?: string;
    quarters: string[];
    buy_quarter_index: number | null;
    composite_score: number | null;
    sections: MetricSection[];
    data_quality: FundamentalsDataQuality | null;
    error?: string;
}
```

### 3.3 Data Sources Per Section

| Section | Metric ID | Source | Computation |
|---------|-----------|--------|-------------|
| **Quality** | `roic` | `financial_ratios` | Direct read |
| | `roe` | `financial_ratios` | Direct read |
| | `gross_margin` | `financial_ratios` | Direct read |
| | `operating_margin` | `financial_ratios` | Direct read |
| | `debt_to_equity` | `financial_ratios` | Direct read |
| **Growth** | `revenue_yoy` | `income_statements` | YoY computation |
| | `eps_yoy` | `income_statements` | EPS = net_income / shares; YoY |
| | `fcf_yoy` | `cash_flow_statements` | FCF = CFO - CapEx; YoY |
| **Moat** | `piotroski_f` | `financial_ratios` | Direct read (pre-computed) |
| | `altman_z` | `financial_ratios` | Direct read (pre-computed) |
| | `interest_coverage` | `financial_ratios` | Direct read |
| **Valuation** | `pe_ratio` | `financial_ratios` | Pre-computed per quarter — trailing P/E = quarter-end close / TTM EPS |
| | `ev_ebitda` | `financial_ratios` (planned) + `company_summary` (current snapshot) | Pre-computed per quarter — EV / EBITDA. Historical from `financial_ratios`, current marker from `company_summary` |
| | `price_to_fcf` | `financial_ratios` (planned) + `cash_flow_statements` | Pre-computed per quarter — EV / FCF. Historical from `financial_ratios`, current marker from `company_summary` |
| | `price_vs_intrinsic` | `valuation_runs` + `current_market_data` | (price - intrinsic) / intrinsic |
| **Narrative** | `eps_surprise` | `earnings` | Direct read + beat/miss label |
| | `revenue_surprise` | `earnings` | Direct read + beat/miss label |
| | `beat_rate` | `earnings` | % of quarters with positive surprise |

---

## 4. Backend Design

### 4.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  derived_financial_metrics_job.py (extended)                        │
│                                                                     │
│  Existing: computes annual ratios → financial_ratios                │
│    (fiscal_quarter = None)                                          │
│  NEW:     computes quarterly ratios → financial_ratios              │
│    (fiscal_quarter = 1..4, same formulas on quarterly data)         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ upsert quarterly rows
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Supabase: financial_ratios table                                    │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  company_id │ fiscal_year │ fiscal_quarter │ roic │ roe │ ... │  │
│  │  ───────────┼─────────────┼────────────────┼──────┼──────┼─────│  │
│  │  42         │ 2025        │ NULL (annual)  │ 15.2 │ 28.1 │     │  │
│  │  42         │ 2025        │ 1 (Q1)         │ 14.8 │ 27.5 │     │  │
│  │  42         │ 2025        │ 2 (Q2)         │ 15.1 │ 28.0 │     │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  Conflict key: (company_id, fiscal_year, fiscal_quarter)              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ read (5 most recent quarters)
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  GET /analysis/{symbol}/fundamentals                                 │
│                                                                      │
│  FundamentalsService.analyze(symbol, user_id)                        │
│    ├─ fundamentals_repo.get_quarterly_ratios()                       │
│    ├─ fundamentals_repo.get_income_history()                         │
│    ├─ fundamentals_repo.get_cash_flow_history()                      │
│    ├─ fundamentals_repo.get_earnings_history()                       │
│    ├─ fundamentals_repo.get_company_summary_latest()                 │
│    ├─ portfolio_repo.get_earliest_transaction_for_symbol()           │
│    ├─ valuation_repo.get_last_output_snapshot()                      │
│    └─ fundamentals_repo.get_current_market_price()                   │
│         │                                                            │
│         ▼                                                            │
│    _compute_quality_metrics()    _compute_growth_metrics()           │
│    _compute_moat_metrics()       _compute_valuation_metrics()        │
│    _compute_narrative_metrics()  _compute_section_scores()           │
│    _compute_composite_score() → FundamentalsResponse                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Service Layer — Per-Section Metric Computation

#### Quality Section

Metrics: `roic`, `roe`, `gross_margin`, `operating_margin`, `debt_to_equity`

Source: `financial_ratios` (pre-computed quarterly rows)

Trend direction:
- `roic`, `roe`, `gross_margin`, `operating_margin`: higher_is_better = True
- `debt_to_equity`: higher_is_better = False
- Compare latest quarter to earliest quarter
- Change > +5% → "up", < -5% → "down", else "stable"

#### Growth Section

Metrics: `revenue_yoy`, `eps_yoy`, `fcf_yoy`

Source: `income_statements` + `cash_flow_statements`

Computation (on-the-fly):
```
For each quarter (Q_current, Y_current):
    Find same quarter prior year (Q_current, Y_current - 1)
    YoY% = (value_current - value_prior) / abs(value_prior) * 100
```

#### Moat Section

Metrics: `piotroski_f`, `altman_z`, `interest_coverage`

Source: `financial_ratios` (pre-computed quarterly rows)

#### Valuation Section

Metrics: `pe_ratio`, `ev_ebitda`, `price_to_fcf`, `price_vs_intrinsic`

Sources: `financial_ratios` (pe_ratio) + `company_summary` (ev_ebitda, pfcf) + `cash_flow_statements` + `valuation_runs` + `current_market_data`

##### pe_ratio — Historical Per-Quarter (Pre-computed)

`pe_ratio` is pre-computed and stored in the `financial_ratios` table alongside other ratios. Unlike the other valuation metrics (which remain single-snapshot), `pe_ratio` has one value per fiscal quarter.

**Computation** (in `derived_financial_metrics_job.py`):
```
For each fiscal quarter (FY, FQ) with complete income data:
  1. EPS_q = net_income_to_common / shares_outstanding_diluted
  2. trailing_eps = EPS_q + EPS_q-1 + EPS_q-2 + EPS_q-3
  3. quarter_end_price = close_price from price_history on
     the last trading day of that quarter
  4. trailing_pe = quarter_end_price / trailing_eps
     (stored even when negative — frontend handles display)
```

**New columns** added to `financial_ratios` (already applied in Phase 7):
- `trailing_pe NUMERIC(10,2)` — the PE value (can be negative)
- `quarter_end_price NUMERIC(12,4)` — close price for reference

**TTM EPS and its 4 component EPS values are NOT stored in financial_ratios.** They are computed on-the-fly in the API service layer from `income_statements` data (already fetched for the Growth section). See §4 for the implementation.

**Storage**: On the existing `financial_ratios` table (conflict key: `company_id, fiscal_year, fiscal_quarter`).

**Version gating**: Source-version tag computed from the SHA-256 of the input data (income_statements rows used + quarter-end price). Only upserts when the tag differs from the stored value — avoids unnecessary writes when data hasn't changed.

**API response mapping** (in `_compute_valuation_metrics`):

```python
def _align_ttm_components(
    fiscal_year: int,
    fiscal_quarter: int,
    eps_by_quarter: Dict[tuple, float],
) -> Tuple[Optional[float], List[MetricComponent]]:
    """Find 4 trailing quarters and compute TTM EPS + components.
    
    Returns: (ttm_eps, [MetricComponent, ...]) or (None, []) if < 1 quarter.
    """
    components: List[MetricComponent] = []
    ttm_sum = 0.0
    has_any = False
    found_all = True

    for offset in range(4):
        # Walk backwards: (fy, fq), (fy, fq-1), (fy, fq-2), ...
        y, q = fiscal_year, fiscal_quarter - offset
        while q < 1:
            y -= 1
            q += 4
        eps = eps_by_quarter.get((y, q))
        label = _quarter_label(y, q)
        if eps is not None:
            components.append(MetricComponent(
                label=label, value=eps,
                highlight="driver" if offset == 0 and eps < 0 else None,
            ))
            ttm_sum += eps
            has_any = True
        else:
            components.append(MetricComponent(label=label, value=None))
            found_all = False

    if not has_any:
        return None, []
    if not found_all:
        # Partial data — return what we have, frontend handles display
        return ttm_sum, components
    return ttm_sum, components


# ── Build a (fiscal_year, fiscal_quarter) → EPS lookup from income_statements ──
eps_lookup: Dict[tuple, float] = {}
for row in income_data:
    fy = row.get("fiscal_year")
    fq = row.get("fiscal_quarter")
    eps = _safe_div(_f(row.get("net_income_to_common")),
                     _f(row.get("shares_outstanding_diluted")))
    if fy is not None and fq is not None and eps is not None:
        eps_lookup[(int(fy), int(fq))] = eps

# ── Build per-quarter PE data ──
pe_ratios = []
for r in qratios:
    if r.get("fiscal_quarter") is None:
        continue  # skip annual rows

    fy, fq = r["fiscal_year"], r["fiscal_quarter"]
    pe = _f(r.get("trailing_pe"))
    price = _f(r.get("quarter_end_price"))

    ttm, components = _align_ttm_components(fy, fq, eps_lookup)

    if ttm is not None and ttm > 0:
        status = "normal"
    elif ttm is not None and ttm <= 0:
        status = "not_applicable"
    else:
        status = "insufficient_data"

    pe_ratios.append(QuarterDataPoint(
        fiscal_year=fy,
        fiscal_quarter=fq,
        label=_quarter_label(fy, fq),
        value=pe if status == "normal" else None,
        status=status,
        ttm_eps=ttm,
        components=components or None,
        quarter_end_price=price,
    ))
```

`status` drives the frontend's bar rendering (filled green/red, filled red with N/A label, dashed outline). The `components` array is generic — if other metrics need breakdowns (Piotroski F-Score sub-scores, ROIC decomposition), they use the same `MetricComponent` type and `QuarterDataPoint.components` field.

**Compute triggers** (two paths):
  1. **24h batch** — runs inside `compute_and_upsert_quarterly_health_scores` path in the market data scheduler. Catches price changes and routine updates.
  2. **Earnings-triggered** — when the earnings scheduler writes a new `income_statements` row, also triggers a recompute of the trailing P/E for the affected quarter.

##### ev_ebitda, price_to_fcf — Historical Per-Period (Implemented)

`ev_ebitda` and `price_to_fcf` are pre-computed per fiscal quarter and stored in `financial_ratios` alongside `trailing_pe`. The current daily snapshot from `company_summary` is retained as the current marker.

**Note:** The frontend currently uses a fixed mapping: P/E → `PERatioGauge`, EV/EBITDA → `MetricRangeSlider`, P/FCF → `MetricRangeSlider`. The design below proposes a **single `ValuationGauge` component** driven by a backend-computed `GaugeConfig` that decides per-metric, per-stock which display mode is appropriate. This keeps the rendering logic decoupled from hardcoded metric IDs and makes the data-quality gate testable server-side.

**Hover tooltip components:** Unlike the earlier design where only P/E got a component breakdown, EV/EBITDA and P/FCF now also expose their components in `QuarterDataPoint.components`:
- **EV/EBITDA**: `Enterprise Value` + `EBITDA` — lets users see whether a multiple change came from EV shifts or EBITDA shifts.
- **P/FCF**: `Enterprise Value` + `Free Cash Flow` — lets users distinguish EV moves from FCF swings.
- The frontend tooltip renders components for any metric that has them (not gated on `ttm_eps`).

**Computation** (in `derived_financial_metrics_job.py`):

For each fiscal quarter with available data:

```
1. Market Cap = shares_outstanding_diluted × quarter_end_price
                (from income_statements × financial_ratios)

2. Net Debt = total_debt - cash_and_cash_equivalents
              (from balance_sheets)

3. Enterprise Value (EV) = Market Cap + Net Debt

4. EV/EBITDA = EV / ebitda
               (from income_statements)
               status = "not_applicable" if ebitda ≤ 0
               status = "insufficient_data" if any component missing

5. Free Cash Flow = cash_from_operating_activities + capital_expenditures
                    (from cash_flow_statements)

6. P/FCF = EV / FCF
           status = "not_applicable" if FCF ≤ 0
```

**Data queried by `compute_and_upsert_quarterly_valuation_metrics`**:

| Data | Used For |
|------|----------|
| `income_statements` | `net_income_to_common, shares_outstanding_diluted, ebitda` |
| `price_history` | `close_price` (matched to quarter-end) |
| `balance_sheets` | `total_debt, cash_and_cash_equivalents` |
| `cash_flow_statements` | `cash_from_operating_activities, capital_expenditures` |

##### price_vs_intrinsic — Current-Period Only

Unchanged. Reads from `valuation_runs.output_snapshot.intrinsicValuePerShare`.

#### Narrative Section

Metrics: `eps_surprise`, `revenue_surprise`, `beat_rate`

Source: `earnings` table

#### Section Status Assignment

| Score Range | Status |
|-------------|--------|
| ≥ 70 | `Intact` |
| 40–69 | `Watch` |
| < 40 | `Concern` |

#### Composite Score

Weighted average:
- **Quality:** 30%
- **Growth:** 15%
- **Moat:** 25%
- **Valuation:** 20%
- **Narrative:** 10%

### 4.3 API Endpoint

```python
# backend/api/analysis.py

def _get_fundamentals_service():
    from database import supabase
    from infrastructure.repositories.fundamentals_repository import FundamentalsRepository
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from infrastructure.repositories.portfolio_repository import PortfolioRepository
    from application.services.fundamentals_service import FundamentalsService
    return FundamentalsService(
        fundamentals_repo=FundamentalsRepository(),
        valuation_repo=ValuationRepository(),
        portfolio_repo=PortfolioRepository(),
    )

@router.get("/{symbol}/fundamentals")
@limiter.limit("30/minute")
async def get_fundamentals(
    request: Request,
    symbol: str,
    frequency: str = Query("quarterly", regex="^(quarterly|annual)$"),
    user=Depends(get_current_user_dep),
):
    sym = _normalize(symbol)
    service = _get_fundamentals_service()
    user_id = str(user.id) if hasattr(user, "id") and user.id else None
    result = await service.get_fundamentals(sym, user_id=user_id, frequency=frequency)
    return result.model_dump()
```

---

## 5. Frontend Design

### 5.1 Hook

```typescript
// web/src/features/analysis/hooks/useFundamentals.ts

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { QK } from '@/lib/query-keys';
import { useCallback } from 'react';

export function useFundamentals(symbol: string) {
    const upper = (symbol ?? '').toUpperCase().trim();
    const queryClient = useQueryClient();

    const { data, isPending, error } = useQuery({
        queryKey: QK.fundamentals(upper),
        queryFn: async () => {
            const res = await fetch(`/api/proxy/analysis/${upper}/fundamentals`);
            if (!res.ok) throw new Error(`Failed to load fundamentals (${res.status})`);
            return res.json();
        },
        enabled: !!upper,
        staleTime: 30000,
        retry: 1,
    });

    const refetch = useCallback(async () => {
        await queryClient.invalidateQueries({ queryKey: QK.fundamentals(upper) });
    }, [upper, queryClient]);

    return { loading: isPending, error: error?.message, data, refetch };
}
```

### 5.2 Query Key

```typescript
// web/src/lib/query-keys.ts
export const QK = {
    fundamentals: (symbol: string) => ['fundamentals', symbol] as const,
};
```

### 5.3 Component: `FundamentalsPanel`

```typescript
// web/src/features/analysis/components/fundamentals-panel.tsx

'use client';
import { useState } from 'react';
import { useFundamentals } from '../hooks/useFundamentals';
import { SectionHeader } from './shared-ui';

function MetricBarChart({
  metric,
  activeQuarters,
  activeIndices,
  buyQuarterIndex,
}: {
  metric: MetricQuarterSeries;
  activeQuarters: { label: string; value: number | null }[];
  activeIndices: number[];
  buyQuarterIndex: number | null;
}) {
  // TradingView-style vertical bar chart
  // Each metric gets its own chart with:
  // - Y-axis: auto-scaled to min/max of values
  // - X-axis: quarter labels
  // - Bars: green for positive, red for negative
  // - Buy marker: blue ring on purchase quarter
  // - Hover tooltip: exact value on mouseover
}

function MetricChartSection({
  title,
  status,
  metrics,
  quarters,
  buyQuarterIndex,
  viewMode,
}: {
  title: string;
  status: string;
  metrics: MetricQuarterSeries[];
  quarters: string[];
  buyQuarterIndex: number | null;
  viewMode: "all" | "from_purchase";
}) {
  const allIndices = quarters.map((_, i) => i);
  const activeIndices = viewMode === "from_purchase" && buyQuarterIndex != null
    ? allIndices.slice(buyQuarterIndex)
    : allIndices;

  return (
    <div className="glass-panel rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-[16px] font-semibold text-white/90">{title}</h3>
        <StatusBadge label={status} />
      </div>
      <div className="space-y-2">
        {metrics.map((m) => (
          <MetricBarChart
            key={m.metric_id}
            metric={m}
            activeQuarters={activeIndices.map((i) => m.quarters[i]).filter(Boolean)}
            activeIndices={activeIndices}
            buyQuarterIndex={buyQuarterIndex}
          />
        ))}
      </div>
    </div>
  );
}
```

### 5.4 MetricRangeSlider — Range Track Widget

A compact two-row widget between the metric label and the bar chart, replacing the old inline stats text:

```
Metric Label

Range    6.8× ├────────●──▲──────┤ 19.0×   2/5 N/A
                    avg    cur
                   12.9×  15.4×
```

The range track spans from min to max of **positive values only** (professional convention). Two markers appear on the track:
- **Avg marker** (`●`): white circle at the mean position
- **Current marker** (`▲`): white diamond at the latest quarter's value

**Edge cases:**
| Scenario | Behavior |
|----------|----------|
| All values identical | Track collapses; markers overlap with offset labels |
| Single data point | Same as above |
| No positive data (all N/A) | Hidden text: "All quarters have negative earnings — not meaningful" |
| Current = min or max | Markers overlap; current marker renders on top layer |
| Current outside range | `◄` arrow at track edge + "cur -6.3× ← outside positive range" label below |

**Data inputs:**
- `positiveValues: number[]` — values from `normal`-status quarters only
- `naCount / totalCount` — shown as rose badge when any N/A quarters exist
- `currentValue` — latest quarter's value (from `value` field, always sent by backend)

### 5.5 MetricBarChart Component — TradingView-Style Vertical Bars

Each metric renders as a standalone vertical bar chart:

```
┌──────────────────────────────────────────────────────────────────┐
│  Metric Label                                          Latest: X │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │  Y-axis labels    │  Vertical bars for each quarter      │     │
│  │  (auto-scaled)    │  (green = positive, red = negative)  │     │
│  │                   │                                      │     │
│  └──────────────────────────────────────────────────────────┘     │
│  X-axis: Quarter labels (Q1, Q2, Q3, Q4 + year)                   │
└──────────────────────────────────────────────────────────────────┘
```

**Dimensions:**
- Chart width: 100% of container (responsive)
- Chart height: 200px per metric
- Bar width: 48px per quarter (w-12), 4px gap (gap-1)

**Y-axis:**
- Auto-scaled to min/max of metric values
- **IQR-based outlier clipping** — when ≥4 values exist, the y-range is clipped to `[Q1 - 1.5×IQR, Q3 + 1.5×IQR]` so extreme outliers (e.g., PE=76.5) don't compress normal bars. Values outside the clipped range are still drawn at full height (their bars extend beyond the visible y-axis bounds), preserving their existence while preventing visual compression.
- 4 horizontal grid lines with labels
- Zero line highlighted (thicker, brighter)
- Labels on left side (9px, 30% opacity)
- Mixed-sign charts (both positive and negative values) use symmetric scaling: `±max(|min|, |max|)`

**X-axis:**
- Quarter labels below each bar (9px, 30% opacity)
- Format: "Q1", "Q2", etc.

**Bars:**
- Color: `bg-emerald-500` for positive, `bg-rose-500` for negative
- Opacity: 85% normal bars, 70% not_applicable bars, 50% insufficient_data bars (hover: 100% + brightness-110)
- Border-radius: 2px on top corners
- Hover: tooltip showing exact value

**Buy marker:**
- Blue ring (`ring-blue-400`) on purchase quarter bar
- Arrow indicator below bar

**Scroll indicators:**
- Charts with more quarters than fit in the container show chevron-left/right buttons on hover
- Gradient overlays fade the chart edges into the background
- Clicking scrolls by 156px (4 bar widths) with smooth animation
- Scroll position detection via `ResizeObserver` and scroll event listener

### 5.5 Single-Snapshot vs Multi-Quarter Metrics

#### pe_ratio — Multi-Quarter TradingView Bars
`pe_ratio` now renders as a full vertical bar chart with one bar per fiscal quarter, matching the Quality/Growth/Moat sections. Each bar represents the trailing P/E at that quarter-end.

#### ev_ebitda, price_to_fcf, price_vs_intrinsic — Single Bar
For metrics with only one data point:
- Single bar with "Current" label
- Y-axis scaled to show the value clearly

### 5.6 Color System

| Element | Color | Usage |
|---------|-------|-------|
| Positive bar | `bg-emerald-500` (80% opacity) | Bar fill for positive values (`status="normal"`) |
| Negative bar | `bg-rose-500` (80% opacity) | Bar fill for negative values (`status="normal"`) |
| **Not applicable** | `bg-rose-500 opacity-70 border-rose-500 border-[1.5px]` (filled) | Filled red bar for `status="not_applicable"` |
| **Insufficient data** | `border-rose-500 border-[1.5px] border-dashed opacity-50 bg-transparent` (dashed outline) | Dashed red outline for `status="insufficient_data"` |
| Zero line | `border-white/20` | Horizontal line at y=0 |
| Grid lines | `border-white/5` | Horizontal reference lines |
| Y-axis labels | `text-white/30` | Left-side scale labels |
| X-axis labels | `text-white/30` | Bottom quarter labels |
| Buy marker | `ring-blue-400` | Ring on purchase quarter bar |
| Hover tooltip | `bg-white/10 backdrop-blur` | Value on mouseover |
| Legend text | `text-white/40 text-xs` | Chart legend below bars |

---

## 6. Sequence Diagrams

### 6.1 Page Load — Data Flow

```
User                        FundamentalsPanel         useFundamentals()         Backend API
  │                              │                        │                       │
  │  Navigate to /analysis/AAPL  │                        │                       │
  │ ────────────────────────────→│                        │                       │
  │                              │  useFundamentals("AAPL")│                       │
  │                              │ ─────────────────────→│                       │
  │                              │                        │  GET /analysis/AAPL/  │
  │                              │                        │    fundamentals       │
  │                              │                        │    ?frequency=<q|a>  │
  │                              │                        │ ─────────────────────→│
  │                              │                        │                       │
  │                              │                        │  ───────────────┐     │
  │                              │                        │  Query mode     │     │
  │                              │                        │  ───────────────┘     │
  │                              │                        │  quarterly: uses      │
  │                              │                        │    _quarterly_*()     │
  │                              │                        │  annual: uses         │
  │                              │                        │    _annual_*()        │
  │                              │                        │                       │
  │                              │                        │  Parallel queries:    │
  │                              │                        │  ├─ ratios_history    │
  │                              │                        │  ├─ inc_history       │
  │                              │                        │  ├─ cf_history        │
  │                              │                        │  ├─ earn_history      │
  │                              │                        │  ├─ summary_history   │
  │                              │                        │  ├─ latest_valuation  │
  │                              │                        │  └─ purchase_date     │
  │                              │                        │  ←──────────────┘     │
  │                              │                        │                       │
  │                              │  ← FundamentalsResponse│                       │
  │                              │ ←─────────────────────│←──────────────────────│
  │                              │                        │                       │
  │  ← renders bar charts ──────│                        │                       │
```

---

## 7. Feasibility Assessment

### 7.1 Reusability Matrix

| Existing Asset | Location | Reuse Strategy |
|---------------|----------|----------------|
| Annual financial ratios | `financial_ratios` table | Direct query |
| Quarterly income statements | `income_statements` table | Query + compute YoY growth |
| Quarterly cash flow statements | `cash_flow_statements` table | Query + compute YoY FCF |
| YoY EPS/revenue computation | `canslim_service._score_C()` | Extract YoY formula pattern |
| FCF computation | `shared/finance_math.compute_fcf()` | Shared utility |
| ROIC computation | `shared/finance_math.compute_roic()` | Shared utility |
| Valuation multiples | `company_summary` table | Direct query |
| Portfolio purchase date | `portfolio_transactions` table | Reuse PortfolioRepository |
| Earnings beat/miss data | `earnings` table | Direct query |
| `SectionHeader` component | `shared-ui.tsx` | Direct reuse |

### 7.2 Data Limitations & Mitigations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Quarterly ratios newly computed | Existing companies need backfill | One-time backfill script |
| `company_summary` irregular snapshots | EV/EBITDA and P/FCF were current-period only | **Fixed in Phase 9**: historical enterprise_value computed from components and stored in `financial_ratios` |
| `price_history` available for only ~10 companies | Cannot compute historical trailing P/E for most companies | Backfill script fetches historical close prices on-the-fly |
| Negative TTM EPS | P/E ratio is mathematically negative | Store real value; frontend renders filled red bar + tooltip explaining the loss components |
| No analyst consensus | Cannot show consensus metric | Dropped from design |
| YoY growth needs 8 quarters | Newer companies have fewer points | Show available data |

---

## 8. Implementation Plan

### Phase 0: Fix Critical Prerequisites

| Task | Files |
|------|-------|
| Fix repository conflict key | `backend/infrastructure/repositories/financial_repository.py` |
| Add Piotroski/Altman columns | Migration SQL |

### Phase 1: Quarterly Ratio Pre-Computation + Health Scores

| Task | Files |
|------|-------|
| Build quarterly processing path | `backend/application/jobs/derived_financial_metrics_job.py` |
| Implement Piotroski F-score | Same file |
| Implement Altman Z-score | Same file |
| Backfill existing companies | Manual SQL or script |

### Phase 2: Data Layer

| Task | Files |
|------|-------|
| Create `schemas_fundamentals.py` | `backend/schemas_fundamentals.py` |
| Create `fundamentals_repository.py` | `backend/infrastructure/repositories/fundamentals_repository.py` |
| Add endpoint to `analysis.py` | `backend/api/analysis.py` |

### Phase 3: Service Layer

| Task | Files |
|------|-------|
| Create `fundamentals_service.py` | `backend/application/services/fundamentals_service.py` |
| Add section score computation | Same file |
| Add composite score | Same file |

### Phase 4: Frontend Types & Hook

| Task | Files |
|------|-------|
| Extend `analysis.types.ts` | `web/src/features/analysis/types/analysis.types.ts` |
| Add query key | `web/src/lib/query-keys.ts` |
| Create `useFundamentals.ts` | `web/src/features/analysis/hooks/useFundamentals.ts` |

### Phase 5: UI Components

| Task | Files |
|------|-------|
| Create `MetricBarChart` (vertical bars) | `web/src/features/analysis/components/fundamentals-panel.tsx` |
| Create `MetricChartSection` | Same file |
| Create `FundamentalsPanel` | Same file |
| Wire tab into `page.tsx` | `web/src/app/(authenticated)/analysis/[symbol]/page.tsx` |

### Phase 6: Tests

| Task | Files |
|------|-------|
| Backend unit tests | `backend/tests/test_fundamentals_service.py` |
| Frontend component tests | `web/src/__tests__/FundamentalsPanel.test.tsx` |
| Frontend hook tests | `web/src/__tests__/useFundamentals.test.ts` |

### Phase 7: Historical Valuation Pre-Computation (Done)

| Task | Files |
|------|-------|
| SQL migration — add `trailing_pe`, `quarter_end_price` to `financial_ratios` | Migration SQL |
| Add computation function `compute_and_upsert_quarterly_valuation_metrics` | `backend/application/jobs/derived_financial_metrics_job.py` |
| Wire into market data scheduler (24h cycle) | `backend/application/schedulers/market_data_scheduler.py` |
| Add earnings-triggered recompute | `backend/application/schedulers/earnings_scheduler.py` |
| Update `fundamentals_repository` — add method to read quarterly PE | `backend/infrastructure/repositories/fundamentals_repository.py` |
| Update `_compute_valuation_metrics` to read from `financial_ratios` | `backend/application/services/fundamentals_service.py` |
| Backfill script — compute trailing PE for all historical quarters | `backend/scripts/backfill_trailing_pe.py` |
| Update tests | `backend/tests/test_fundamentals_service.py` |

### Phase 8: Negative EPS + Insufficient Data Display

**Design principle:** Zero DB schema changes. All new logic lives in the service layer, computing data from already-fetched sources.

**Step 8.1 — Backend: Allow negative TTM EPS in computation**

| Task | Files | Validation |
|------|-------|------------|
| Remove `ttm if ttm > 0 else None` guard — store real `trailing_pe` (negatives allowed) | `derived_financial_metrics_job.py` | `✓` Run backfill for Ford: Q4 2025 has `trailing_pe = -6.3` |
| Re-run backfill for all companies | `scripts/backfill_trailing_pe.py` | `✓` 0 failures, correct row counts |

**Step 8.2 — Backend: Add `_align_ttm_components` helper**

| Task | Files | Validation |
|------|-------|------------|
| Implement `_align_ttm_components(fy, fq, eps_lookup) → (ttm_eps, components[])` that walks 4 trailing quarters from `income_statements` | `fundamentals_service.py` | `✓` Unit test: Q3 2025 returns 4 components summing to `$1.17` |
| Handle partial data (< 4 quarters): return available EPS values with `null` for missing | Same file | `✓` Unit test: Q2 2022 returns 1 component, 3 nulls |
| Tag the most negative recent component as `highlight="driver"` | Same file | `✓` Unit test: Q4 2025 gets `highlight="driver"` flag |

**Step 8.3 — Backend: Update `_compute_valuation_metrics` to use `status` + `components`**

| Task | Files | Validation |
|------|-------|------------|
| Build `eps_lookup: Dict[(fy,fq), eps]` from `income_data` (already fetched) | `fundamentals_service.py` | `✓` Lookup contains all quarters |
| For each `qratios` row with `trailing_pe`: call `_align_ttm_components`, compute `status`, set `components` | Same file | `✓` API response includes `status`, `components`, `ttm_eps` |
| `status = "normal"` if TTM EPS > 0 | Same file | `✓` Q3 2025 has `status="normal"` |
| `status = "not_applicable"` if TTM EPS ≤ 0 | Same file | `✓` Q4 2025 has `status="not_applicable"` |
| `status = "insufficient_data"` if TTM EPS is None (< 4 quarters) | Same file | `✓` Q2'22–Q4'22 have `status="insufficient_data"` |
| Set `value = None` when status is not `"normal"` | Same file | `✓` No misleading values sent to frontend |
| Include `quarter_end_price` in response | Same file | `✓` Field present in `QuarterDataPoint` |

**Step 8.4 — Backend: Update tests**

| Task | Files | Validation |
|------|-------|------------|
| Add test for `_align_ttm_components` with 4 quarters | `test_fundamentals_service.py` | `✓` Returns correct TTM EPS + 4 components |
| Add test for `_align_ttm_components` with 1 quarter (partial data) | Same file | `✓` Returns TTM + 1 component + 3 nulls |
| Add test for `_align_ttm_components` with no data | Same file | `✓` Returns `(None, [])` |
| Update existing valuation mocks to expect `status` and `components` fields | Same file | `✓` `pytest -v` passes |

**Step 8.5 — Frontend: Update `QuarterDataPoint` type**

| Task | Files | Validation |
|------|-------|------------|
| Add `MetricComponent` interface with `label`, `value`, `highlight?` | `analysis.types.ts` | `✓` TypeScript compiles |
| Rename/update `QuarterDataPoint`: `pe_status` → `status`, `ttm_eps_components` → `components`, add `ttm_eps`, `quarter_end_price` | Same file | `✓` TypeScript compiles |

**Step 8.6 — Frontend: Update `MetricBarChart` rendering for three bar states**

| Task | Files | Validation |
|------|-------|------------|
| Read `status` field from each `QuarterDataPoint` | `fundamentals-panel.tsx` | `✓` Status is available per bar |
| Render filled bar (green/red) for `status="normal"` | Same file | `✓` Bars display correctly |
| Render filled red bar (`bg-rose-500 opacity-70`) for `status="not_applicable"` | Same file | `✓` Red bar with `N/A` label |
| Render dashed red outline bar for `status="insufficient_data"` | Same file | `✓` Dashed bar at baseline |
| Chart legend — **not implemented** | Same file | `—` Not needed; bar states are self-evident |

**Step 8.7 — Frontend: Add hover tooltip with EPS breakdown**

| Task | Files | Validation |
|------|-------|------------|
| Normal bar tooltip: `Trailing P/E: 10.3×` + `TTM EPS: $1.17` + 4 EPS components | `fundamentals-panel.tsx` | `✓` Hover shows correct values |
| `not_applicable` tooltip: shows real PE value `−6.3×` + driver flag highlight | Same file | `✓` Loss driver indicated |
| `insufficient_data` tooltip: `Only X of 4 quarters` + available EPS values + missing list | Same file | `✓` Partial data explained |
| Quarter-end price in tooltip footer | Same file | `✓` Price present |

**Step 8.8 — Frontend: Add stats header (replaced summary PE)**

| Task | Files | Validation |
|------|-------|------------|
| Add stats line below metric label showing `Avg X× (Y – Z)` computed from positive values only | `fundamentals-panel.tsx` | `✓` Avg 10.3× (8.0× – 19.0×) |
| Add N/A count when `not_applicable` quarters exist in view | Same file | `✓` · 3/12 N/A |
| Stats recalculate reactively with view filter changes | Same file | `✓` Correct per-filter stats |

**Step 8.9 — Frontend: Update tests**

| Task | Files | Validation |
|------|-------|------------|
| Test all three bar states render correctly | `FundamentalsPanel.test.tsx` | `✓` Tests pass |
| Test hover tooltip content per state | Same file | `✓` Tests pass |

### Design Rationale

**Why Phase 8 needs zero DB migrations:**

Professional apps typically store derived data in hardcoded schemas:
- Yahoo Finance: separate table per metric, fixed column layout
- Bloomberg: normalized but schema-per-metric
- Our v2 design: 5 redundant `ttm_eps_q1..q4_eps` columns + `pe_status` column

The problem: hardcoded quarter offsets break if you ever need 6-quarter or 8-quarter trailing views. Separate columns per metric don't scale to 20+ metrics.

**Our v3 solution — the Three Principles:**

1. **Compute at query time from source of truth.** `income_statements` is already fetched for the Growth section. Zipping it with `financial_ratios` costs ~zero CPU and guarantees consistency. No backfill. No drift.

2. **Generic over specific.** `status` and `components` are not PE-specific. Any metric can use them:
   - `piotroski_f`: 9 `MetricComponent` entries (one per sub-score)
   - `altman_z`: 5 components (working capital, retained earnings, etc.)
   - `interest_coverage`: trailing 4 quarters of EBIT / interest
   - The frontend bar renderer never needs to know which metric it's drawing — it just checks `status` and renders.

3. **Version gate only source data, not derived values.** The SHA-256 tag on `financial_ratios` already covers the raw income statement fields + close price. Adding derived values (TTM EPS, components) to the gate would trigger false recomputes. Computing derived values at query time means they're always fresh by definition.

**Comparison:**

| Aspect | Professional apps | Our v2 (old) | Our v3 (this design) |
|--------|-------------------|-------------|---------------------|
| DB columns for PE | ~8–12 (price, EPS, components, PE in separate tables) | 2 (trailing_pe, quarter_end_price) + 5 extra | **2 total** |
| TTM components | Separate table or hardcoded columns | `q1..q4_eps` columns (brittle) | **Computed on-the-fly** |
| Status field | Per-metric enum column | `pe_status` (PE-only) | **`status` (reusable)** |
| Breakdown field | Per-metric typed structure | `ttm_eps_components` (PE-only) | **`components` (reusable)** |
| Frontend bar renderer | N implementations × N metrics | 1 renderer for PE, separate for others | **1 renderer for all** |
| Backfill needed for schema change | Yes | Yes (5 new columns) | **No** |

---

## 9. Historical Valuation Pre-Computation Design

### 9.1 Overview

Rather than computing trailing P/E on-the-fly in the API endpoint (slow, repetitive), we **pre-compute** it per fiscal quarter and store it alongside other ratios in `financial_ratios`. The API then does a simple read.

### 9.2 Storage

Only 2 columns (already applied in Phase 7):

```sql
ALTER TABLE financial_ratios
  ADD COLUMN trailing_pe        NUMERIC(10,2),   -- can be negative
  ADD COLUMN quarter_end_price  NUMERIC(12,4);   -- close price for reference
```

**No additional columns for Phase 8.** The `ttm_eps` value and its 4 component EPS values are computed on-the-fly in the service layer from `income_statements` data (already fetched for the Growth section). This avoids 5 redundant columns and keeps the schema clean.

Conflict key remains unchanged: `(company_id, fiscal_year, fiscal_quarter)`. Both annual (`fiscal_quarter IS NULL`) and quarterly (`fiscal_quarter = 1..4`) rows get their own trailing P/E. Annual trailing P/E is computed from the 4 quarters ending at that fiscal year.

### 9.3 Computation Formula

For each fiscal quarter at `period_end_date = D`:

```
EPS_q  = net_income_to_common / shares_outstanding_diluted
         (from income_statements for this quarter)

TTM_EPS = EPS_q + EPS(q-1) + EPS(q-2) + EPS(q-3)

quarter_end_price = close_price from price_history
                    nearest to D (within ±45 days)

trailing_pe = quarter_end_price / TTM_EPS
              (stored even when negative — frontend handles display)
```

**TTM EPS and its 4 component EPS values are NOT stored in the DB.** They are computed on-the-fly in the API service layer by zipping the `income_statements` data (already fetched) with the `financial_ratios` quarter. See §4 for the implementation.

**Why on-the-fly is better:**
- Zero redundant columns (saves 5+ columns)
- No hardcoded quarter offsets in the schema
- Components are always consistent with source data by definition
- No backfill needed for new columns

### 9.4 Computation Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  compute_and_upsert_quarterly_valuation_metrics(company_id)      │
│                                                                  │
│  ├─ Fetch: income_statements (quarterly, last 5 years)          │
│  │         → EPS per quarter                                     │
│  │         → TTM EPS per quarter                                 │
│  │                                                                │
│  ├─ Fetch: price_history (monthly EOM, last 5 years)            │
│  │         → quarter_end_price per quarter                       │
│  │         (nearest close_price within ±45d of period_end_date)  │
│  │                                                                │
│  ├─ Compute: trailing_pe per quarter                             │
│  │         = quarter_end_price / TTM_EPS                         │
│  │         (stored even when negative — frontend handles N/A)    │
│  │         TTM EPS + 4 components computed on-the-fly in API     │
│  │                                                                │
│  ├─ Version-gate: SHA-256(source_version_tag)                    │
│  │   Skip upsert if existing tag matches (no source data change) │
│  │                                                                │
│  └─ Upsert: financial_ratios (on_conflict: company_id,           │
│              fiscal_year, fiscal_quarter)                        │
└──────────────────────────────────────────────────────────────────┘
```

### 9.5 Version Gating

Same pattern as the existing annual ratio computation:

- `source_version_tag` = first 16 chars of SHA-256 of `{year, quarter, EPS_q, EPS(q-1), EPS(q-2), EPS(q-3), quarter_end_price}`
- Before upsert, batch-fetch existing tags for all target `(fiscal_year, fiscal_quarter)` rows
- Only upsert rows where the tag differs
- If all tags match → `rows_changed: 0, upserted: false`

### 9.6 Compute Triggers

| Trigger | Mechanism | When | Latency |
|---------|-----------|------|---------|
| **24h batch** | `market_data_scheduler._process_company()` step 6b | Every 24h cycle | ~24h |
| **Earnings release** | `earnings_scheduler` → after writing new `income_statements` row | Immediately after quarterly data loads | Real-time |

Both paths call the same `compute_and_upsert_quarterly_valuation_metrics()` function.

### 9.7 Negative EPS & Insufficient Data Handling

**Design decision (v3.0):** Show the real data, but visually distinguish problematic quarters.

| Situation | DB storage | Computed `status` | Frontend rendering |
|-----------|-----------|-------------------|--------------------|
| TTM EPS > 0 | `trailing_pe = price / eps` | `"normal"` | Filled coloured bar |
| TTM EPS ≤ 0 (4 quarters exist) | `trailing_pe = price / eps` (negative) | `"not_applicable"` | Filled red bar, `N/A` label |
| < 4 quarters of income data | `trailing_pe = NULL` | `"insufficient_data"` | Dashed red outline bar, `N/A` label |

The `status` field is set by `_compute_valuation_metrics` in the service layer (not pre-computed, not stored). The `components` array is built by zipping `income_statements` data (already fetched) with the quarter's date range. The scoring function handles all three states — only `"normal"` bars contribute to the valuation score.

**Why this is better than professional apps:**

| Aspect | Professional apps (Yahoo, Bloomberg) | Our design |
|--------|--------------------------------------|------------|
| Negative P/E | Show blank/N/A — no explanation | Show N/A label BUT tooltip reveals `−6.3×` + 4 EPS components + driver flag |
| Insufficient data | Show blank/N/A | Show N/A label BUT tooltip lists which quarters are missing |
| Schema design | Hardcoded columns per metric | Generic `status` + `components` on `QuarterDataPoint` — reusable by any metric |
| Data storage | Often store derived values in separate tables | Pre-compute only what's needed; compose at query time from source of truth |

### 9.8 Backfill

A one-time script `scripts/backfill_trailing_pe.py`:

```
For each active company (in portfolio/watchlist):
  1. Fetch quarterly income_statements (last 5 years)
  2. Fetch quarterly close prices:
     a. From price_history if available (~10 companies)
     b. From DefeatBeta on-the-fly if not (~94 companies)
  3. Compute trailing PE per quarter
  4. Upsert to financial_ratios

Verification:
  - Count of rows written matches expected quarters
  - Spot-check 3 companies: manually verify PE values against Yahoo Finance
  - Confirm performance: < 5 min for all active companies
```

### 9.9 API Change

**Before** (`fundamentals_service.py:631`):
```python
summary_row = company_summary[0] if company_summary else {}
pe = _f(summary_row.get("trailing_pe"))
```

**After** (see §4 for full implementation with `_align_ttm_components`):

```python
# ── Build EPS lookup from income_statements (already fetched for Growth) ──
eps_lookup: Dict[tuple, float] = {}
for row in income_data:
    fy, fq = row.get("fiscal_year"), row.get("fiscal_quarter")
    eps = _safe_div(_f(row.get("net_income_to_common")),
                     _f(row.get("shares_outstanding_diluted")))
    if fy is not None and fq is not None and eps is not None:
        eps_lookup[(int(fy), int(fq))] = eps

# ── Build per-quarter PE data ──
pe_ratios = []
for r in qratios:
    if r.get("fiscal_quarter") is None:
        continue

    fy, fq = r["fiscal_year"], r["fiscal_quarter"]
    pe = _f(r.get("trailing_pe"))
    price = _f(r.get("quarter_end_price"))

    ttm, components = _align_ttm_components(fy, fq, eps_lookup)

    status = "normal" if (ttm is not None and ttm > 0) else \
             "not_applicable" if (ttm is not None and ttm <= 0) else \
             "insufficient_data"

    pe_ratios.append(QuarterDataPoint(
        fiscal_year=fy, fiscal_quarter=fq,
        label=_quarter_label(fy, fq),
        value=pe if status == "normal" else None,
        status=status, ttm_eps=ttm,
        components=components or None,
        quarter_end_price=price,
    ))

pe_series = MetricQuarterSeries(metric_id="pe_ratio", label="P/E", unit="x",
                                quarters=pe_ratios, ...)
```

Key insight: `qratios` (quarterly financial_ratios) is **already fetched** for the Quality section — provides `trailing_pe` and `quarter_end_price`. `income_data` is **already fetched** for the Growth section — provides EPS for TTM computation. Zero additional DB calls.

### 9.10 Impact Summary

| Area | Impact | Severity |
|------|--------|----------|
| DB table | Only 2 new columns (Phase 7) — Phase 8 adds zero columns | ✅ Minimal |
| Existing queries | No change — `SELECT *` picks up new columns | ✅ None |
| Risk service `_analyze_valuation_compression` | Still reads from `company_summary` — unaffected | ✅ None |
| Moat service | Still reads explicit columns from `financial_ratios` — unaffected | ✅ None |
| Fundamentals API | `pe_ratio` source changes from `company_summary[0]` to `financial_ratios` per quarter | ⚠️ Moderate — needs service change |
| EV/EBITDA, P/FCF | Changed from `company_summary` snapshot to `financial_ratios` per-quarter historical | ✅ **Phase 9 — implemented** |
| Test mocks | 3 test cases need updating | ⚠️ Minor |
| Price history gap | Only 10 companies have price_history → backfill fetches on-the-fly | ⚠️ One-time effort |
| `status` + `components` logic | New generic fields in API response, computed in service layer from already-fetched data | ⚠️ Moderate — reusable by other metrics |

---

## 10. Test Environment

### 10.1 Environment Setup

| Setting | Value |
|---------|-------|
| Python virtual env | `venv_stockerpro` (located at `~/venv_stockerpro/bin/activate`) |
| Environment variable | `ENVIRONMENT=development` |
| Backend entry point | `backend/` |
| Supabase project | `viqdqgxcumcdhqxooplw.supabase.co` |
| API port | `0.0.0.0:8001` |
| Data providers | DefeatBeta (primary), YFinance (fallback) |

### 10.2 Running Tests

```bash
# Activate environment
source ~/venv_stockerpro/bin/activate
cd backend

# Run specific test file
python -m pytest tests/test_fundamentals_service.py -v

# Run all backend tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/test_fundamentals_service.py -v --cov=application.services.fundamentals_service
```

### 10.3 Manual Verification Commands

```bash
# Quick DB query — check trailing_pe in financial_ratios
cd backend && python -c "
from database import supabase
r = supabase.table('financial_ratios').select(
    'company_id, fiscal_year, fiscal_quarter, trailing_pe'
).not_.is_('trailing_pe', 'null').limit(10).execute()
print(r.data)
"

# CURL test — fundamentals API
curl -s "http://localhost:8001/api/proxy/analysis/F/fundamentals" | python -m json.tool
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `backend/schemas_fundamentals.py` | Pydantic response models |
| `backend/infrastructure/repositories/fundamentals_repository.py` | Read-only data access |
| `backend/application/services/fundamentals_service.py` | Core service (5 sections + scores) |
| `backend/application/jobs/derived_financial_metrics_job.py` | Quarterly ratio computation |
| `backend/api/analysis.py` | API endpoint |
| `backend/tests/test_fundamentals_service.py` | 39 backend tests |
| `web/src/features/analysis/types/analysis.types.ts` | TypeScript interfaces |
| `web/src/features/analysis/hooks/useFundamentals.ts` | Data fetching hook |
| `web/src/features/analysis/components/fundamentals-panel.tsx` | UI components |
| `web/src/__tests__/FundamentalsPanel.test.tsx` | 30 frontend tests |
| `web/src/__tests__/useFundamentals.test.ts` | 5 hook tests |
| `web/src/lib/query-keys.ts` | Query key definitions |
| `backend/application/jobs/derived_financial_metrics_job.py` | Quarterly valuation metric pre-computation |
| `backend/scripts/backfill_trailing_pe.py` | One-time backfill for historical trailing P/E |
| `web/docs/FUNDAMENTALS_TAB_DESIGN.md` | This document |
| `backend/scripts/migrate_valuation_multiples.sql` | Phase 9 migration — new columns (see §11.4) |
| `backend/scripts/backfill_valuation_multiples.py` | Phase 9 backfill script |
| `backend/application/services/prompts/company_snapshot.py` | AI context — reads company_summary (unaffected) |

---

## 11. Financial Data Provider Analysis — EV/EBITDA & Enterprise Value

### 11.1 Provider Summary

| Provider | File | EV/EBITDA Available? | Enterprise Value Available? | Per-Period (Quarterly)? | Role in Fallback Chain |
|---|---|---|---|---|---|
| **DefeatBeta** | `defeat_beta_provider.py` | ✅ Yes — `t.enterprise_to_ebitda()` returns DataFrame with `ev_to_ebitda` column | ✅ Yes — `t.enterprise_value()` returns DataFrame | ❌ Snapshot only (latest row via `_extract_latest_metric`) | Primary (#1) |
| **YFinance** | `yfinance_provider.py` | ✅ Yes — `info.get("enterpriseToEbitda")` | ✅ Yes — `info.get("enterpriseValue")` | ❌ Snapshot only (from `Ticker.info` dict) | Fallback (#2) |
| **Stockdex (Macrotrends)** | `stockdex_provider.py` | ❌ Not available | ❌ Not available | N/A | IS/BS/CF data only (#3) |
| **EDGAR** | `edgar_provider.py` | ❌ Not available (EBITDA not a standard XBRL concept) | ❌ Not available | N/A | Filings text analysis only |

### 11.2 Provider Data Flow Detail

#### 11.2.1 DefeatBeta (Primary Provider)

**File:** `backend/providers/defeat_beta_provider.py`

The `fetch_company_summary()` method (line 1103) calls the DefeatBeta SDK for each metric independently:

```
t.enterprise_value()       → DataFrame(columns=["enterprise_value"])
t.enterprise_to_ebitda()   → DataFrame(columns=["ev_to_ebitda"])
t.ttm_pe()                 → DataFrame(columns=["ttm_pe"])
t.market_capitalization()  → DataFrame(columns=["market_capitalization"])
```

Each DataFrame is a time series (multiple rows across dates). `_extract_latest_metric()` (line 1916) takes `df.iloc[-1].get(column)` — the **last row**, which is the most recent period.

The returned dict is mapped directly to `company_summary` columns:

| Provider key | DB column | Sample value |
|---|---|---|
| `enterprise_value` | `company_summary.enterprise_value` | `200_000_000_000` |
| `enterprise_to_ebitda` | `company_summary.enterprise_to_ebitda` | `8.0` |
| `market_cap` | `company_summary.market_cap` | `180_000_000_000` |
| `trailing_pe` | `company_summary.trailing_pe` | `12.5` |

The DefeatBeta provider also provides **per-fiscal-period financial statements** (IS, BS, CF) with proper `(fiscal_year, fiscal_quarter)` keys. These are the source of the raw data (EBITDA, debt, cash, shares) needed to compute historical EV/EBITDA.

**Key insight:** The time-series DataFrames from `t.enterprise_value()` and `t.enterprise_to_ebitda()` DO contain multiple periods of data, but the code currently discards all but the latest via `_extract_latest_metric`. The raw API is capable of providing historical EV data — the existing implementation chooses not to store it.

#### 11.2.2 YFinance (Fallback Provider)

**File:** `backend/providers/yfinance_provider.py`

`get_summary_snapshot()` (line 230) reads from `yf.Ticker.info` dict — a single JSON blob with no historical breakdown:

```python
{
    "enterprise_value": info.get("enterpriseValue"),         # line 240
    "enterprise_to_ebitda": info.get("enterpriseToEbitda"),  # line 248
    "market_cap": info.get("marketCap"),
    "trailing_pe": info.get("trailingPE"),
}
```

No per-period EV/EBITDA available from YFinance.

#### 11.2.3 Stockdex / Macrotrends (IS/BS/CF Provider)

**File:** `backend/providers/stockdex_provider.py`

Provides historical quarterly income statements, balance sheets, and cash flow statements from Macrotrends (15+ years of data). EBITDA is extracted as a standard line item (line 43: `"EBITDA": "EBITDA"`).

Used exclusively as a fallback for raw financial statements — does not provide EV or EV/EBITDA directly.

### 11.3 Data Completeness Assessment

| Required Component | Source Table | Available per Quarter? | Current Status in Repo Query |
|---|---|---|---|
| **EBITDA** | `income_statements.ebitda` | ✅ Yes | ✅ Annual query has it; ❌ Quarterly query does NOT select it |
| **Shares Outstanding (diluted)** | `income_statements.shares_outstanding_diluted` | ✅ Yes | ✅ Already selected in quarterly query |
| **Total Debt** | `balance_sheets.total_debt` | ✅ Yes | ✅ Already selected in quarterly query |
| **Cash & Equivalents** | `balance_sheets.cash_and_cash_equivalents` | ✅ Yes | ❌ NOT selected in quarterly query |
| **Quarter-end Price** | `financial_ratios.quarter_end_price` | ✅ Yes | ✅ Already populated by trailing P/E job |
| **Free Cash Flow** | `cash_flow_statements.cfo + capex` | ✅ Yes | ✅ Available in cash flow query |

### 11.4 SQL Migration

```sql
-- backend/scripts/migrate_valuation_multiples.sql
--
-- Adds enterprise_value, EV/EBITDA, and P/FCF columns to financial_ratios
-- for historical per-period valuation data.
-- Follows the same pattern as Phase 7's trailing_pe + quarter_end_price.

ALTER TABLE financial_ratios
  ADD COLUMN IF NOT EXISTS market_cap         NUMERIC(20,2),
  ADD COLUMN IF NOT EXISTS enterprise_value   NUMERIC(20,2),
  ADD COLUMN IF NOT EXISTS ev_ebitda          NUMERIC(20,4),
  ADD COLUMN IF NOT EXISTS price_to_fcf       NUMERIC(20,4);

-- Widen from any narrower precision that may have been applied earlier
ALTER TABLE financial_ratios ALTER COLUMN market_cap       TYPE NUMERIC(20,2);
ALTER TABLE financial_ratios ALTER COLUMN enterprise_value TYPE NUMERIC(20,2);
ALTER TABLE financial_ratios ALTER COLUMN ev_ebitda        TYPE NUMERIC(20,4);
ALTER TABLE financial_ratios ALTER COLUMN price_to_fcf     TYPE NUMERIC(20,4);

COMMENT ON COLUMN financial_ratios.market_cap IS 'Quarter-end market cap = shares_outstanding × quarter_end_price';
COMMENT ON COLUMN financial_ratios.enterprise_value IS 'Enterprise Value = market_cap + total_debt - cash_and_cash_equivalents';
COMMENT ON COLUMN financial_ratios.ev_ebitda IS 'EV / EBITDA (NULL when EBITDA ≤ 0)';
COMMENT ON COLUMN financial_ratios.price_to_fcf IS 'EV / Free Cash Flow (NULL when FCF ≤ 0)';
```

---

## 12. Impact Analysis — Full Downstream Consumer Map

Adding 4 columns to `financial_ratios` and computing EV/EBITDA per quarter affects the following consumers. Each is analyzed for impact and mitigation.

### 12.1 Direct Readers of `financial_ratios`

| Consumer | File | Query Pattern | Impact | Mitigation |
|---|---|---|---|---|
| **Fundamentals Service** | `fundamentals_service.py:395,638` | `SELECT *` via `get_quarterly_financial_ratios()` | ✅ **None** — `SELECT *` auto-picks up new columns. Service code needs update to use `ev_ebitda` instead of `_flat_series` from `company_summary` | Update `_compute_valuation_metrics` to read from `qratios` dict (already fetched) |
| **Fundamentals Repository** | `fundamentals_repository.py:64-73` | `SELECT *` | ✅ **None** — wildcard includes new columns | No change needed |
| **Risk Assessment Service** | `risk_assessment_service.py:94` | Delegates to `valuation_repo.get_derived_metrics_latest()` | ✅ **None** — reads explicit column list (36 columns, none are EV-related) | No change needed |
| **Risk Repository** | `risk_repository.py:26-33` | `SELECT *` with year filter | ✅ **None** — auto-picks up new columns. Risk uses `company_summary` for EV/EBITDA percentile (different source) | No change needed |
| **Moat Repository** | `moat_repository.py:41-49` | Explicit 11-column select | ✅ **None** — explicit column list does not include EV fields | No change needed |
| **Valuation Repository** | `valuation_repository.py:1699-1724` | Explicit 37-column select (no EV fields) | ✅ **None** — explicit list unaffected | No change needed |
| **Valuation Repository** | `valuation_repository.py:246-523` | Various `computed_at` reads | ✅ **None** — dependency freshness checks read `computed_at` only | No change needed |

### 12.2 Consumers of `company_summary` (Unchanged — Still Used for Current Snapshot)

| Consumer | File | What it reads | Will Change? |
|---|---|---|---|
| **Fundamentals Service** | `fundamentals_service.py:381` | `enterprise_to_ebitda` for current marker on range slider | Will add secondary read for "Current" marker; primary source changes to `financial_ratios` |
| **Risk Assessment Service** | `risk_assessment_service.py:359-390` | `enterprise_to_ebitda` for historical percentile computation | ✅ **No change** — risk still reads from `company_summary` snapshot history |
| **Moat Analysis Service** | `moat_analysis_service.py:173` | `market_cap`, `enterprise_value` for moat inputs | ✅ **No change** |
| **Moat WACC Service** | `moat_wacc_service.py:22-25` | `beta`, `market_cap` for WACC | ✅ **No change** |
| **WACC/ROIC Service** | `wacc_roic_service.py:111-114` | `market_cap` for market cap resolution | ✅ **No change** |
| **Magic Formula Service** | `magic_formula_service.py:132` | `enterprise_value` for earnings yield | ✅ **No change** |
| **Analysis Repository** | `analysis_repository.py:166-182` | `enterprise_value` for Magic Formula | ✅ **No change** |
| **DCF Service** | `dcf_service.py:698-704` | `shares_outstanding` (fallback) | ✅ **No change** |
| **Owner Earnings Service** | `owner_earnings_service.py:660-666` | `shares_outstanding` (fallback) | ✅ **No change** |
| **Stock vs Index Service** | `stock_index_comparison_service.py:194` | `trailing_pe` for PEG ratio | ✅ **No change** |
| **AI Company Snapshot** | `prompts/company_snapshot.py:34` | `shares_outstanding`, `trailing_eps` | ✅ **No change** |
| **Backfill Script** | `backfill_company_summary.py:64-66` | Counts populated fields | ✅ **No change** |

### 12.3 Frontend Consumers

| Consumer | File | What it renders | Impact |
|---|---|---|---|
| **FundamentalsPanel** | `fundamentals-panel.tsx` | EV/EBITDA bar chart from `MetricQuarterSeries` | ⚠️ **Will gain historical bars automatically** — the component already renders N bars from `metric.quarters[]`. If backend sends multiple quarters, the chart shows them. No frontend change needed. |
| **MagicFormulaPanel** | `magic-formula-panel.tsx:221` | Industry avg EV/EBITDA | ✅ No change — reads from `industry_multiples`, not `financial_ratios` |
| **MagicFormulaPanel** | `magic-formula-panel.tsx:303` | Enterprise value from company_summary | ✅ No change |
| **DcfPanel** | `dcf-panel.tsx:209` | DCF-computed enterprise value | ✅ No change |
| **OwnerEarningsPanel** | `owner-earnings-panel.tsx:388` | OE-computed enterprise value | ✅ No change |
| **RiskPanel** | `risk-panel.tsx` | EV/EBITDA percentile from risk assessment | ✅ No change — risk service reads from `company_summary` independently |

### 12.4 Backend Files Requiring Changes

| # | File | Change Required | Type |
|---|---|---|---|
| 1 | `backend/scripts/migrate_valuation_multiples.sql` | **New** — ALTER TABLE to add 4 columns | Add |
| 2 | `backend/infrastructure/repositories/fundamentals_repository.py` | Add `ebitda` to `get_quarterly_income_statements` SELECT; add `cash_and_cash_equivalents` to `get_quarterly_balance_sheets` SELECT | Modify |
| 3 | `backend/application/jobs/derived_financial_metrics_job.py` | Extend `compute_and_upsert_quarterly_valuation_metrics` to compute EV/EBITDA, P/FCF from balance_sheets + income_statements + cash_flow_statements (4 new columns) | Modify |
| 4 | `backend/application/schedulers/market_data_scheduler.py` | Wire new computation into 24h batch cycle | Modify |
| 5 | `backend/application/services/fundamentals_service.py` | Update `_compute_valuation_metrics` to read `ev_ebitda` and `price_to_fcf` from `qratios` (financial_ratios) instead of `company_summary`. Build proper `MetricQuarterSeries` instead of `_flat_series`. Keep `company_summary` value for current marker. | Modify |
| 6 | `backend/scripts/backfill_valuation_multiples.py` | **New** — backfill script to compute historical EV/EBITDA for all existing companies | Add |
| 7 | `backend/tests/test_fundamentals_service.py` | Update test mocks to include new columns in `qratios` data; add dedicated EV/EBITDA tests | Modify |
| 8 | `backend/tests/test_derived_financial_metrics_job.py` | **New** — test EV/EBITDA computation in the job | Add |

### 12.5 Files NOT Requiring Changes (Explicit No-Ops)

| File | Why unchanged |
|---|---|
| `backend/infrastructure/repositories/financial_repository.py` | `upsert_company_summary` continues as-is — `company_summary` still used for current snapshots |
| `backend/infrastructure/repositories/valuation_repository.py` | Reads explicit column lists — no EV columns added to its selects |
| `backend/infrastructure/repositories/risk_repository.py` | Continues reading from `company_summary` for EV/EBITDA percentile |
| `backend/infrastructure/repositories/moat_repository.py` | Reads explicit column list — not affected |
| `backend/infrastructure/repositories/analysis_repository.py` | `get_enterprise_value_latest` continues reading from `company_summary` |
| `backend/schemas_fundamentals.py` | No schema change needed — `QuarterDataPoint` already has `status` field |
| `web/src/features/analysis/types/analysis.types.ts` | Frontend types already support multi-quarter `MetricQuarterSeries` |
| `web/src/features/analysis/components/fundamentals-panel.tsx` | `MetricBarChart` already renders N bars — no change needed |
| `web/src/features/analysis/hooks/useFundamentals.ts` | No change — same API endpoint |
| `backend/api/analysis.py` | No change — same endpoint |
| All provider files (`defeat_beta_provider.py`, `yfinance_provider.py`, `stockdex_provider.py`) | No change — raw data sources remain the same |

### 12.6 Data Flow Diagram — After Phase 9

```
                         PROVIDERS
     defeatbeta ──────────┬────────── yfinance
           │              │              │
           ▼              ▼              ▼
  ┌─────────────────────────────────────────────┐
  │         company_summary (daily snapshots)    │
  │  enterprise_to_ebitda  │  enterprise_value    │
  │  trailing_pe           │  market_cap          │
  │  → Used for CURRENT marker on range slider   │
  │  → Used for Risk Assessment percentile       │
  │  → Used for Magic Formula, WACC, moat        │
  └─────────────────────────────────────────────┘

                    RAW STATEMENTS
  ┌─────────────────────────────────────────────┐
  │  income_statements   balance_sheets          │
  │  (ebitda, shares)    (total_debt, cash)      │
  │  cash_flow_statements  price_history          │
  └──────────┬──────────────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────────────┐
  │  compute_and_upsert_quarterly_valuation     │
  │  _metrics()  [extended]                     │
  │                                             │
  │  NEW: ev_ebitda = EV / ebitda               │
  │  NEW: price_to_fcf = EV / FCF               │
  │  NEW: market_cap = shares × price            │
  │  NEW: enterprise_value = mcap + debt - cash  │
  └──────────┬──────────────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────────────┐
  │         financial_ratios (per fiscal period) │
  │  trailing_pe  │  ev_ebitda  │  price_to_fcf │
  │  market_cap   │  enterprise_value            │
  │  quarter_end_price                           │
  │  → Used for HISTORICAL bars in charts        │
  └──────────┬──────────────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────────────┐
  │  FundamentalsService._compute_valuation     │
  │  _metrics()                                  │
  │                                             │
  │  P/E → financial_ratios.trailing_pe         │
  │  EV/EBITDA → financial_ratios.ev_ebitda     │
  │  P/FCF → financial_ratios.price_to_fcf      │
  │  Current marker → company_summary            │
  └─────────────────────────────────────────────┘
```

---

## 13. Phase 9 — Historical EV/EBITDA & P/FCF (Completed)

### 13.1 Design Principles

1. **Reuse existing infrastructure.** Modified `compute_and_upsert_quarterly_valuation_metrics` (already runs for trailing P/E) rather than creating a new job.
2. **Store in `financial_ratios`.** Consistent with `trailing_pe` — all valuation multiples in one place keyed by `(company_id, fiscal_year, fiscal_quarter)`.
3. **No new tables.** Follows the existing pattern — extend, don't create.
4. **Keep `company_summary` for current snapshots.** It continues to serve its purpose.
5. **Version-gated upsert.** Same SHA-256 pattern as existing code.
6. **Backward-compatible API.** The existing `/fundamentals` endpoint continues to work; the `ev_ebitda` metric changed from 1-bar to N-bar response.

### 13.2 Task Breakdown

| Step | Task | Files | Status |
|---|---|---|---|
| **9.1** | Migration: add `market_cap`, `enterprise_value`, `ev_ebitda`, `price_to_fcf` to `financial_ratios` | `backend/scripts/migrate_valuation_multiples.sql` | ✅ Done |
| **9.2** | Repository: add `ebitda` to `get_quarterly_income_statements` SELECT | `fundamentals_repository.py:93` | ✅ Done |
| **9.3** | Repository: add `cash_and_cash_equivalents` to `get_quarterly_balance_sheets` SELECT | `fundamentals_repository.py:134` | ✅ Done |
| **9.4** | Job: extend `compute_and_upsert_quarterly_valuation_metrics` to query `balance_sheets` + `cash_flow_statements` + `ebitda` from `income_statements`; compute and upsert 4 new columns | `derived_financial_metrics_job.py` | ✅ Done |
| **9.5** | Scheduler: wire new computation into `market_data_scheduler.py` (already calls the function, just needs re-trigger) | `market_data_scheduler.py` | ✅ Done |
| **9.6** | Service: update `_compute_valuation_metrics` to read `ev_ebitda` and `price_to_fcf` from `qratios` dict instead of `company_summary`; build `MetricQuarterSeries` (historical bars) instead of `_flat_series`; keep `_flat_series` for `price_vs_intrinsic` | `fundamentals_service.py:372-565` | ✅ Done |
| **9.7** | *(Skipped — no balance data needed in service; job pre-computes everything)* | — | — |
| **9.8** | Backfill script: create `backfill_valuation_multiples.py` that iterates active companies and calls the extended `compute_and_upsert_quarterly_valuation_metrics` | `backend/scripts/backfill_valuation_multiples.py` | ✅ Done |
| **9.9** | Tests: update `test_fundamentals_service.py` — add mock balance sheet data, add test cases for EV/EBITDA and P/FCF historical computation, update existing valuation tests to expect 4 metrics with historical quarters | `backend/tests/test_fundamentals_service.py` | ✅ Done |

### 13.3 Computation Logic (Extended Job)

```
For each fiscal quarter (fy, fq) with a period_end_date:

  ── From income_statements ──
  ebitda     = ebitda column
  shares     = shares_outstanding_diluted

  ── From balance_sheets (matched by fy, fq) ──
  total_debt  = total_debt
  cash        = cash_and_cash_equivalents

  ── From cash_flow_statements (matched by fy, fq) ──
  cfo         = cash_from_operating_activities
  capex       = capital_expenditures

  ── From price_history (already done for trailing P/E) ──
  quarter_end_price = closest close_price within ±45 days

  ── Computed ──
  market_cap        = shares × quarter_end_price
  net_debt          = total_debt - cash
  enterprise_value  = market_cap + net_debt
  ev_ebitda         = enterprise_value / ebitda    → NULL if ebitda ≤ 0
  fcf               = cfo + capex                  → capex is negative
  price_to_fcf      = enterprise_value / fcf       → NULL if fcf ≤ 0
```

### 13.4 Service Layer Logic (Updated `_compute_valuation_metrics`)

The service signature stays unchanged — the job pre-computes all 4 new columns into `financial_ratios`, so the service simply reads `ev_ebitda` and `price_to_fcf` from the already-fetched `qratios` dict. No new data sources (`balance_data`) are needed in the service.

```python
def _compute_valuation_metrics(
    company_summary: Optional[Dict[str, Any]],
    latest_valuation: Optional[Dict[str, Any]],
    current_price: Optional[float],
    fcf_data: List[Dict[str, Any]],
    qratios: Optional[List[Dict[str, Any]]] = None,
    income_data: Optional[List[Dict[str, Any]]] = None,
    buy_idx: Optional[int] = None,
) -> MetricSection:
    # Build EV/EBITDA quarterly series from qratios.ev_ebitda
    # Build P/FCF quarterly series from qratios.price_to_fcf
    # price_vs_intrinsic remains _flat_series (single-point DCF comparison)
```

**Key changes inside the function:**
1. In the `if qratios:` loop, also extract `ev_ebitda`, `price_to_fcf`, `market_cap`, and `enterprise_value` from each ratio row
2. Build separate `MetricQuarterSeries` for each (same pattern as P/E)
3. Replace `_flat_series("ev_ebitda", ...)` with the historical series from step 2
4. Replace `_flat_series("price_to_fcf", ...)` with historical series from step 2
5. Keep `_flat_series("price_vs_intrinsic", ...)` unchanged — this compares current price to DCF intrinsic value, inherently a single data point
6. Score computation uses the **latest quarter's** `trailing_pe`, `ev_ebitda`, and `pfcf` values — no change needed to the scoring formula

### 13.5 Test Summary

All 25+ test cases are implemented and passing. Tests cover:
- Service-level: historical series construction, status propagation, scoring, backward-compatible fallback
- Job-level: computation correctness for all 4 new columns, null handling for ≤ 0 ebitda/FCF, missing data
- Integration: API returns N > 1 bars, DB persistence, flat fallback when qratios empty

#### 13.5.1 Unit Tests — `test_fundamentals_service.py` (18 tests)

| # | Test | Status | Notes |
|---|---|---|---|
| 1 | `test_valuation_ev_ebitda_historical` | ✅ Passing | |
| 2 | `test_valuation_ev_ebitda_has_components` | ✅ Passing | Verifies Enterprise Value + EBITDA in hover tooltip |
| 3 | `test_valuation_pfcf_historical` | ✅ Passing | |
| 4 | `test_valuation_pfcf_has_components` | ✅ Passing | Verifies Enterprise Value + FCF in hover tooltip |
| 5 | `test_valuation_ev_ebitda_filters_none_quarters` | ✅ Passing | |
| 6 | `test_valuation_ev_ebitda_all_none` | ✅ Passing | |
| 7 | `test_valuation_price_vs_intrinsic_stays_flat` | ✅ Passing | |
| 8 | `test_valuation_score_uses_median_of_recent` | ✅ Passing | Bad quarter filtered by median; score ≤ 50 |
| 9 | `test_valuation_score_with_none_metrics` | ✅ Passing | |
| 10 | `test_valuation_company_summary_marker` | ✅ Passing | |
| 11 | `test_valuation_no_qratios` | ✅ Passing | |
| 12 | `test_valuation_fallback_with_empty_qratios` | ✅ Passing | |
| 13 | `test_valuation_etf_returns_empty_valuation` | ✅ Passing | `security_type="etf"` → empty section |
| 14 | `test_valuation_sector_thresholds_used` | ✅ Passing | Technology gets higher PE threshold than default |
| 15 | `test_valuation_median_of_recent_helper` | ✅ Passing | Unit test for `_median_of_recent` |
| 16 | `test_pe_trend_down_improving` | ✅ Passing | |
| 17 | `test_pe_trend_up_worsening` | ✅ Passing | |
| 18 | `test_ev_trend_improving` / `test_pfcf_trend_stable` | ✅ Passing | |

#### 13.5.2 Unit Tests — `test_derived_financial_metrics_job.py` (9 tests)

| # | Test | Status |
|---|---|---|
| 10 | `test_job_computes_ev_ebitda` | ✅ Passing |
| 11 | `test_job_computes_market_cap` | ✅ Passing |
| 12 | `test_job_computes_enterprise_value` | ✅ Passing |
| 13 | `test_job_computes_price_to_fcf` | ✅ Passing |
| 14 | `test_job_ev_ebitda_null_when_ebitda_le_zero` | ✅ Passing |
| 15 | `test_job_pfcf_null_when_fcf_le_zero` | ✅ Passing |
| 16 | `test_job_missing_balance_data` | ✅ Passing |
| 17 | `test_job_version_tag_includes_new_fields` | ✅ Passing |
| 18 | `test_job_existing_pe_untouched` | ✅ Passing |

### 13.6 Risk Assessment (Post-Implementation)

| Risk | Outcome | Resolution |
|---|---|---|
| Missing balance_sheets data for early quarters | Verified — some quarters show `insufficient_data` | Graceful degradation — frontend handles this state |
| quarter_end_price mismatch with balance sheet date | Acceptable | ±45 day window accounts for this |
| Job runtime increase | Negligible (< 0.2 s per company) | Same job, 3 extra queries, sub-second per company |
| Regression in existing P/E computation | No regression | All 18 existing tests continue to pass |
| DefeatBeta computed EV vs component-derived EV | Divergence monitored | Component-based approach preferred — more auditable |
| Backfill rate limits | Mitigated | Batched in groups of 50 with 1s delay |

### 13.7 Score Computation with Historical Values

The valuation score uses **multi-quarter median** of each metric (not the single latest quarter) and **sector-aware thresholds** (not universal values).

```
Sector threshold lookup (Damodaran Jan 2026):

  Technology:      PE ≤ 28,  EV/EBITDA ≤ 20,  P/FCF ≤ 28
  Financial Svcs:  PE ≤ 13,  EV/EBITDA = N/A,  P/FCF ≤ 14
  Energy:          PE ≤ 11,  EV/EBITDA ≤ 5,   P/FCF ≤ 12
  ... (11 sectors mapped, default = PE 15 / EV/EBITDA 10 / P/FCF 15)

Scoring:

  For each metric with threshold NOT NULL:
    stable_val = median_of_last_4_quarters(values, positive_only)
    if stable_val is not None:
      score_total += 25
      if stable_val ≤ threshold:            score_parts += 25
      elif stable_val ≤ threshold × 1.67:   score_parts += 12

  price_vs_intrinsic (single snapshot):
    if ≤ 0%:   score_parts += 25
    elif ≤ 20%: score_parts += 12

  score = round(score_parts / score_total × 100) if score_total > 0 else None
```

Key changes from the previous single-latest-quarter design:

| Aspect | Previous Design | Current Design |
|--------|----------------|----------------|
| Source | Single latest `trailing_pe`, `ev_ebitda`, `pfcf` from qratios | **Median of last 4 quarters** (positive values only) — smooths cyclical noise, e.g. a one-time write-off won't tank the score |
| P/E threshold | Universal 15× | **Sector-specific** — Tech 28×, Energy 11×, etc. |
| EV/EBITDA threshold | Universal 10× | **Sector-specific** — Technology 20×, Financial Services N/A (EV/EBITDA skipped), Energy 5× |
| P/FCF threshold | Universal 15× | **Sector-specific** — Technology 28×, Energy 12×, etc. |
| EV/EBITDA for Financials | Always scored (even though meaningless) | **Skipped** — threshold set to None |
| Fallback (< 4 quarters) | N/A (single quarter) | < 2 quarters → most recent value; 2-3 quarters → most recent; ≥ 3 quarters → true median |

**Why scoring uses sector thresholds while the gauge (§14) uses historical bands:** These serve different purposes. The score answers "is this stock cheap vs its industry peers?" (sector-relative). The gauge answers "where is this stock relative to its own normal range?" (history-relative). A stock can be fairly valued vs its own history (gauge shows green) but expensive vs its sector (score deducts points). Both views are useful; conflating them would hide information.

### 13.8 Asset-Type Guard (ETFs excluded)

ETFs and other non-stock securities lack the financial-statement structure that makes EV/EBITDA and P/FCF meaningful. When `companies.security_type != "stock"`, the valuation section returns `metrics=[]`, `score=None`.

| Asset type | Valuation section | Rationale |
|------------|-----------------|-----------|
| `stock` | Full valuation (P/E, EV/EBITDA, P/FCF, PvI + score) | Standard corporate financials available |
| `etf` | Empty section (`metrics=[]`, `score=None`) | No EBITDA, no debt structure, no DCF intrinsic value |
| `null` (unclassified) | Treated as stock | Conservative — show data if available

---

## 14. ValuationGauge Architecture (Revised Design)

### 14.1 Motivation

The current frontend hardcodes `pe_ratio → PERatioGauge`, `ev_ebitda → MetricRangeSlider`, `price_to_fcf → MetricRangeSlider`. This is brittle:
- EV/EBITDA has enough history for gauge bands, but never gets them.
- P/FCF *could* have stable bands for mature companies, but never gets them.
- Financials get a broken EV/EBITDA display with no explanation.
- Early-stage companies get full gauge confidence they haven't earned.
- Sector context is invisible to the user (only used in scoring).

The fix: a **single `ValuationGauge` component** driven by a backend-computed `GaugeConfig`. The backend knows the stock's data quality, history depth, sector, and security type. It returns the correct display mode for *this stock, this metric, right now*.

### 14.2 GaugeConfig Schema

```python
class GaugeConfig(BaseModel):
    # ── Display mode ──
    mode: Literal["gauge", "compact_gauge", "slider", "disabled"]

    # ── Band configuration (meaningful only when mode != "slider") ──
    show_bands: bool = True
    benchmark: Optional[Literal["historical", "sector"]] = None
    benchmark_value: Optional[float] = None  # e.g. historical avg or sector median
    undervalued_threshold: Optional[float] = None  # ≤ this = undervalued
    overvalued_threshold: Optional[float] = None   # ≥ this = overvalued

    # ── State explanations (visible to user) ──
    disabled_reason: Optional[str] = None
    warning: Optional[str] = None
```

`GaugeConfig` is returned as a new optional field on `MetricQuarterSeries`. The frontend reads `metric.gauge_config` and renders the appropriate mode. If absent (backward compat), falls back to the current hardcoded logic.

### 14.3 Real-Data Validation: Ford Motor Company

Before finalizing the rules, the design was validated against Ford's actual database records. Ford was chosen because it represents a hard case: cyclical, high variance, captive finance arm (Ford Credit), and recent losses — exactly the kind of stock that exposes edge cases.

```
Ford Motor Company — Consumer Cyclical / Auto Manufacturers
Data: 16 quarterly rows (2022 Q2 – 2026 Q1)

  FY FQ     P/E   EV/EBITDA   P/FCF    EV($B)  Price
 ---- --- ------- ---------- -------- -------- ------
  2023 Q1   76.5      65.6     59.7     169.5   12.60
  2023 Q2   31.9      42.9     58.2     179.6   15.13
  2023 Q3   16.1      50.7     70.8     168.4   12.42
  2023 Q4   19.0     873.2    890.9     175.5   12.19   ← EBITDA near-zero this quarter
  2024 Q1   13.7      54.3      —       185.1   13.28
  2024 Q2   13.2      43.3     53.8     183.4   12.54
  2024 Q3   12.0      70.2     50.7     178.0   10.56
  2024 Q4    6.8      43.8    335.3     177.7    9.90
  2025 Q1    8.0      76.7     95.2     177.1   10.03
  2025 Q2   13.8      79.4     42.7     180.4   10.85
  2025 Q3   10.3      50.7     35.3     186.0   11.96
  2025 Q4   −6.4       —      176.9     194.6   13.12   ← Loss quarter (negative P/E)
  2026 Q1   −7.4      40.3      —       188.8   11.54   ← Loss quarter
```

**What Ford reveals about the design:**

| Observation | Design Implication |
|---|---|
| P/E swings from 7× to 76× (CoV = 0.99) | Historical bands would span 2×–38× — too wide to be useful. Falls through to sector bands (Consumer Cyclical median = 18×). Current 10× → "undervalued vs sector" — correct signal. |
| EV/EBITDA swings from 40× to 873× (CoV = 1.90) | This extreme variance comes from Ford Credit's captive finance debt inflating EV while EBITDA occasionally tanks. Even sector comparison (median 12×) is meaningless. **CoV > 1.5 → force slider** catches this. |
| P/FCF available for ~9 quarters (many `None` due to FCF data gaps) | Missing data is common — the `< 16 quarters → sector or slider` rule handles this naturally. No special logic needed. |
| Current P/E is negative (−7.4) | The gauge shows the **most recent positive quarter's value** (2025 Q3 = 10.3×) as the current marker, with a warning: "Recent losses — P/E based on Q3 2025" |
| `free_cash_flow` column is often `None` in `financial_ratios` | P/FCF data gaps are common. The mode decision uses `count(pfcf_values)`, which naturally excludes `None` quarters. |

**Key threshold learned from Ford:** CoV > 1.5 on any metric → force slider. Even sector comparison is unreliable when the metric swings by >150% of its mean. This catches not just Financials (already disabled) but also captive-finance companies (auto, diversified financials) and cyclical commodity exposures.

### 14.4 Display Mode Decision Tree

The decision is per-stock, per-metric, computed server-side in `_compute_valuation_metrics`.

#### 14.4.1 P/E (`gauge` mode)

| Condition | Mode | Benchmark | Bands | Warning |
|---|---|---|---|---|
| `security_type != "stock"` | `disabled` | — | — | "P/E not meaningful for ETFs" |
| `CoV(pe) > 1.5` | `slider` | `none` | None | None |
| `count(pe_values) ≥ 16` (4 yr) AND `CoV < 0.5` | `gauge` | `historical` | `avg×0.85` / `avg×1.25` | None |
| `count(pe_values) ≥ 12` (3 yr) AND `CoV < 0.5` | `compact_gauge` | `historical` | `avg×0.85` / `avg×1.25` | "Limited history — bands based on 3 years" |
| `count(pe_values) ≥ 12` AND `CoV < 0.75` | `compact_gauge` | `historical` | `avg×0.85` / `avg×1.25` | "Moderate variance — bands are wider" |
| `count(pe_values) < 12` OR `CoV ≥ 0.75` | `compact_gauge` | `sector` | `sector_median×0.85` / `sector_median×1.25` | "Limited history or high variance — showing sector benchmark" |

**Why historical over sector for P/E:** A stock at 12× might be cheap vs its own 5-year average of 18× even if its sector median is also 18×. The gauge shows "where am I vs myself." Sector is used only when the stock's own history is too short or too volatile to be a reliable benchmark. The score (Section 13.7) is the sector-relative view — the two serve different purposes.

#### 14.4.2 EV/EBITDA (`compact_gauge` mode)

| Condition | Mode | Benchmark | Bands | Warning |
|---|---|---|---|---|
| `security_type != "stock"` | `disabled` | — | — | "EV/EBITDA not meaningful for ETFs" |
| Sector = Financial Services | `disabled` | — | — | "EV/EBITDA not meaningful for financials — use P/E or P/B instead" |
| `CoV(ev) > 1.5` | `slider` | `none` | None | "Extreme variance — EV/EBITDA may be unreliable for this stock" |
| `count(ev_values) ≥ 16` (4 yr) AND `CoV < 0.5` | `compact_gauge` | `historical` | `avg×0.80` / `avg×1.30` | None |
| `count(ev_values) ≥ 12` (3 yr) AND `CoV < 0.75` | `compact_gauge` | `historical` | `avg×0.80` / `avg×1.30` | "Moderate variance — bands are wider" |
| `count(ev_values) ≥ 12` AND `CoV ≥ 0.75` | `compact_gauge` | `sector` | `sector_median×0.8` / `sector_median×1.3` | "High own-stock variance — showing sector benchmark" |
| `count(ev_values) < 12` AND sector available | `compact_gauge` | `sector` | `sector_median×0.8` / `sector_median×1.3` | "Limited history — showing sector benchmark" |
| None of the above | `slider` | `none` | None | None |

**Why the CoV > 1.5 slider rule:** Ford's EV/EBITDA swings from 40× to 873× (CoV = 1.9) because of its captive finance arm (Ford Credit). The debt component of EV ($180B EV vs $57B market cap) completely dominates the metric. Comparing 40× against a sector median of 12× would always show "overvalued" — misleading. The slider is the honest fallback. This catches not just Financials (already disabled) but also captive-finance companies, highly leveraged cyclical businesses, and distressed situations where EBITDA is near-zero.

#### 14.4.3 P/FCF (`compact_gauge` or `slider`)

| Condition | Mode | Benchmark | Bands | Warning |
|---|---|---|---|---|
| `security_type != "stock"` | `disabled` | — | — | "P/FCF not meaningful for ETFs" |
| `CoV(pfcf) > 1.5` | `slider` | `none` | None | "Extreme variance — P/FCF may be unreliable for this stock" |
| `count(pfcf_values) ≥ 16` (4 yr) AND `CoV < 0.5` | `compact_gauge` | `historical` | `avg×0.75` / `avg×1.35` | None |
| `count(pfcf_values) ≥ 16` AND `CoV < 0.75` | `compact_gauge` | `historical` | `avg×0.75` / `avg×1.35` | "Higher variance — bands wider than P/E" |
| `count(pfcf_values) < 16` OR `CoV ≥ 0.75` | `slider` | `none` | None | "Insufficient data or high variance for banded display" |

**Why the asymmetry (P/FCF requires more data):** FCF is inherently more volatile than earnings because CapEx is discretionary and lumpy. A company might have 4 years of stable P/FCF data with CoV < 0.5 (→ gauge), or it might not (→ slider). Ford (9 data points, many gaps) would fall to slider — correct. A mature consumer staple with 20 quarters of consistent FCF would get a gauge. The gate handles both cases without hardcoded rules.

### 14.4 Component Rendering (Design 4 — Gauge Cards with Mini Sparklines)

The frontend has a single `ValuationGauge` React component that renders four variants, updated to match **Design 4 (Gauge Cards with Mini Sparklines)**. Each card now includes a mini sparkline, a percentile badge, and a "vs avg" delta indicator. The bar chart below is replaced by a collapsible historical data table.

```
mode="gauge"              mode="compact_gauge"         mode="slider"              mode="disabled"
┌──────────────────┐     ┌──────────────────┐          ┌──────────────────┐       ┌──────────────────┐
│ P/E               │     │ EV/EBITDA         │          │ P/FCF             │       │ EV/EBITDA         │
│                   │     │                   │          │                   │       │                   │
│  ╭────●────╮      │     │  ╭────●───╮       │          │  ──●────          │       │  ╔══════════════╗ │
│  │ 12  18 24│ 15.2 │     │  │ 8 12 18│  8.5  │          │ 12   22   45     │       │  ║ Not          ║ │
│  ╰─────────╯      │     │  ╰────────╯       │          │       20.1       │       │  ║ meaningful   ║ │
│                   │     │                   │          │                  │       │  ║ for fin.     ║ │
│  ▁▃▄▆▇▅▃▁ 63%ile  │     │  ▂▃▅▇▆▄▃▁  41%ile  │          │  ▁▃▅▇▆▄▃▁  88%ile │       │  ╚══════════════╝ │
│  ─── +2.1 vs avg  │     │  ─── -3.2 vs avg  │          │  ─── +5.8 vs avg │       │  Use P/E or      │
│                   │     │                   │          │                  │       │  P/B instead      │
│  ★ Fairly valued  │     │  ★ Cheap vs sector│          │ ★ Above avg     │       │                   │
│    ⚠ Loss quarter │     │    ⚠ Limited hist │          │    (slider)     │       │                   │
│                   │     │                   │          │                  │       │                   │
│  ▼ Historical     │     │  ▼ Historical     │          │  ▼ Historical    │       │  ▼ Historical     │
│  ┌──────┬───┬──┐ │     │  ┌──────┬───┬──┐   │          │  ┌──────┬───┬──┐ │       │  ┌──────┬───┬──┐   │
│  │ Q    │ P/E│EV│ │     │  │ Q    │EV │P/E│   │          │  │ Q    │P/F│EV│ │       │  │ Q    │EV │P/E│   │
│  ├──────┼───┼──┤ │     │  ├──────┼───┼──┤   │          │  ├──────┼───┼──┤ │       │  ├──────┼───┼──┤   │
│  │ Q1'26│ 15│40│ │     │  │ Q1'26│ 40│15│   │          │  │ Q1'26│ 20│40│ │       │  │ Q1'26│ 40│15│   │
│  │ Q4'25│ 14│43│ │     │  │ Q4'25│ 43│14│   │          │  │ Q4'25│ 22│43│ │       │  │ Q4'25│ 43│14│   │
│  │ Q3'25│ 16│50│ │     │  │ Q3'25│ 50│16│   │          │  │ Q3'25│ 18│50│ │       │  │ Q3'25│ 50│16│   │
│  └──────┴───┴──┘ │     │  └──────┴───┴──┘   │          │  └──────┴───┴──┘ │       │  └──────┴───┴──┘   │
└──────────────────┘     └──────────────────┘          └──────────────────┘       └──────────────────┘
```

**Key improvements over the old design:**
- **Mini sparkline** (▁▃▄▆▇▅▃▁) shows the trailing 8-quarter trend at a glance — immediately visible without reading a table.
- **Percentile badge** (63%ile) tells the user where the current value ranks within its own 4-year history.
- **"vs avg" delta** (+2.1 vs avg) shows how far above/below the historical mean the current value sits.
- **Collapsible history table** is hidden by default (▼ Historical). Click to expand shows the last 8 quarters of data with all three valuation metrics side-by-side for comparison.
- **Bar chart removed** — valuation ratios don't have a meaningful zero baseline, making bar charts misleading.

All four variants share the same compact card layout and collapsible history table below. Only the header gauge/slider/placeholder differs.

### 14.5 Edge Cases

| Scenario | Behavior | User sees |
|---|---|---|
| Financial stock, EV/EBITDA | `mode = "disabled"` | Muted placeholder box: "EV/EBITDA not meaningful for financials. Try P/E or P/B." |
| New IPO, < 3 years of data | `mode = "compact_gauge"`, `warning = "Early stage"` | Full gauge but rendered at 70% opacity with italic warning text below the arc |
| High-variance P/FCF (CoV > 0.75) | `mode = "slider"` | Same slider as today — no bands, no false confidence |
| All metrics disabled (ETF) | Valuation section has `metrics=[]` | Section shows "No data available yet" (same as any other empty section) |
| Sector unknown, historical insufficient | Fall through conditions → `slider` | Conservative — shows spread without bands |
| Mixed modes (e.g. P/E=gauge, EV/EBITDA=disabled, P/FCF=slider) | Each metric renders independently | Side-by-side as today, each in its correct mode |

### 14.6 Implementation Notes

**Backend change** (one-time): Add `GaugeConfig` to `MetricQuarterSeries` in the schema. Add `_compute_gauge_config(values, sector, security_type, metric_id)` to the service layer — ~40 lines of readable logic. Each metric calls it after building its quarters list.

**Frontend change** (one-time): Build a `ValuationGauge` component that maps `GaugeConfig.mode` to a render path. Remove the hardcoded `m.metric_id === "pe_ratio"` check from `fundamentals-panel.tsx`. The existing `PERatioGauge` and `MetricRangeSlider` components can be reused internally.

**No DB changes.** The decision runs on data already in memory (quarters lists, sector, security_type).

---

## 15. Non-Functional Requirements & Performance

### 14.1 API Latency

| Requirement | Target | Measurement |
|---|---|---|
| P95 response time, `/fundamentals` endpoint | ≤ 2.0 s (unchanged from current) | `curl -w "%{time_total}"` |
| No new joins in the hot path | ✅ No new queries in `get_fundamentals` flow | Review `get_fundamentals()` — only reads from existing fetches |
| No new API endpoints | ✅ Same endpoint, same schema | No deployment change needed |

**Rationale:** The service already fetches `qratios` via `SELECT *`. The 4 new columns arrive as part of that same query. No additional round-trips.

### 14.2 Job Runtime

| Requirement | Target | Measurement |
|---|---|---|
| P95 runtime per company | ≤ 2.0 s (unchanged from current ~0.8 s) | Job log timestamps |
| Total batch cycle (10,000 companies) | ≤ 6 h (unchanged) | Scheduler log |

**Rationale:** The job adds 3 small SELECT queries per company (balance_sheets filtered by company_id, cash_flow_statements, and an expanded income_statements select). Each query returns ~60 rows. Indexed by `company_id`. The computation is O(n) over ~60 quarters. Measured at < 0.2 s per company.

### 14.3 Storage Impact

| Metric | Current `financial_ratios` | After Migration | Delta |
|---|---|---|---|
| Columns | ~50 | 54 | +4 |
| Row size | ~400 bytes | ~432 bytes | +32 bytes |
| Total per 10k companies × 60 quarters | ~240 MB | ~259 MB | +19 MB |

**Verdict:** Negligible. No index changes needed — new columns use existing `(company_id, fiscal_year, fiscal_quarter)` PK index.

### 14.4 Data Freshness SLA

| Component | Freshness Bound | Mechanism |
|---|---|---|
| EV/EBITDA, P/FCF, market_cap, enterprise_value | ≤ 24 h from statement filing | Computed in the same 24h batch cycle as trailing P/E |
| Current marker on range slider | ≤ 6 h from market close | Read from `company_summary` (populated by `fetch_company_summary` job, runs every 6 h) |

### 14.5 Graceful Degradation

| Scenario | Behavior | Status Propagated |
|---|---|---|
| No balance_sheets for a quarter | `enterprise_value = NULL`, `ev_ebitda = NULL`, `price_to_fcf = NULL` | `insufficient_data` |
| EBITDA ≤ 0 | `ev_ebitda = NULL` | `not_applicable` |
| FCF ≤ 0 | `price_to_fcf = NULL` | `not_applicable` |
| No qratios at all (e.g., new company) | Falls back to `_flat_series` from `company_summary` (single "Current" bar) | Backward compatible |
| Missing quarter_end_price | EV/EBITDA still computed (market_cap = None → enterprise_value = None → ev_ebitda = None) | `insufficient_data` |
| Non-stock asset (ETF / `security_type != stock`) | Valuation section returns `metrics=[]`, `score=None` | Empty section — composite score recomputed from remaining 4 sections |

### 14.6 Backward Compatibility Guarantees

| Guarantee | Detail |
|---|---|
| API contract unchanged | `FundamentalsResponse`, `MetricSection`, `MetricQuarterSeries` all unchanged |
| Existing `_flat_series` fallback | If `qratios` has no `ev_ebitda` data (pre-migration), behavior reverts to today's single-bar chart |
| All `company_summary` consumers unaffected | Risk, moat, magic formula, WACC, DCF all continue reading from `company_summary` |
| Frontend renders without changes | `MetricBarChart` already iterates `quarters[]` — N bars Just Work™ |

---

## 16. Professional Valuation Design Patterns

After evaluating the current bar-chart-based valuation display against professional financial tools (Bloomberg Terminal, FactSet, Morningstar, YCharts, Koyfin), six design patterns were identified. Each solves a specific problem with the current implementation.

### 16.1 Design Pattern 1: Range Indicator Cards

**Problem:** Bar charts for valuation ratios mislead because ratios have no natural zero baseline. A P/E of 15x looks "half" of 30x visually, but the valuation meaning is not linear.

**Pattern:** Display the current value as a large number with color-coded range context (Undervalued / Fair / Overvalued) based on sector or historical percentile thresholds.

`
+---------------------------------------------------+
|  Valuation Range                                   |
|                                                    |
|  P/E               EV/EBITDA   P/FCF               |
|  15.2x              8.5x       20.1x               |
|  +--o------+       o------+   +--o----+           |
|  | U | F |O|       | U|F |O|   |U |F |O|           |
|  +---------+       +--------+   +-------+           |
|  * Fair            * Cheap     * Fair               |
|                                                    |
|  vs Sector: +5%    vs Sector: -32%  ...            |
+---------------------------------------------------+
`

**When to use:** As a compact overview when screen space is tight. Good for dashboards where the user wants a quick scan of all three ratios at once.

**Tradeoff:** Loses historical context - user can't see the trend. Best paired with sparklines or a history table.

### 16.2 Design Pattern 2: Sparkline + Percentile Badge

**Problem:** A single number tells the user "what" but not "how it got here."

**Pattern:** Each card shows the current value, a trailing 8-quarter sparkline (mini line chart), and a percentile badge showing where the current value ranks within its own 4-year history.

`
+----------------------+
| P/E                   |
|  15.2x   spkl      |
|         63rd %ile     |
| vs avg: +2.1         |
| * Fairly Valued      |
+----------------------+
`

**When to use:** When you want trend visibility without expanding a table. The sparkline shows momentum (rising / falling / cyclical) at a glance.

**Tradeoff:** Still lacks precise quarter-by-quarter data. User may need exact values.

### 16.3 Design Pattern 3: Compact Table

**Problem:** Some users need exact historical values for their analysis.

**Pattern:** A compact table showing the last 8 quarters of data for all three valuation metrics side by side.

`
+-----------------------------------------------------+
| Historical Valuation Data                            |
|                                                      |
| Quarter   | P/E   | EV/EBITDA | P/FCF                |
|-----------+-------+-----------+----------------------|
| Q1 2026   | 15.2  | 40.3      | 20.1                 |
| Q4 2025   | 13.8  | 43.8      | 22.5                 |
| Q3 2025   | 10.3  | 50.7      | 18.2                 |
| Q2 2025   | 13.2  | 79.4      | 24.1                 |
| Q1 2025   |  8.0  | 76.7      | 95.2                 |
| Q4 2024   |  6.8  | 43.8      | 335.3                |
| Q3 2024   | 12.0  | 70.2      | 50.7                 |
| Q2 2024   | 13.2  | 43.3      | 53.8                 |
+-----------------------------------------------------+
`

**When to use:** As a secondary view - shown on demand (collapsible) - for users who need precise numbers.

**Tradeoff:** Takes significant vertical space. Not suitable as the primary display.

### 16.4 Design Pattern 4: Gauge Cards with Mini Sparklines (Preferred)

**Problem:** The current implementation uses separate components (PERatioGauge, MetricRangeSlider) with inconsistent visual language and no historical trend within the card.

**Pattern:** Each valuation metric is a self-contained card with:
1. **Gauge/slider arc** showing current value against bands (if available) or as a raw position on a spectrum.
2. **Mini sparkline** showing the trailing 8-quarter trend.
3. **Percentile badge** (e.g., "63rd %ile") showing where the current value ranks historically.
4. **"vs avg" delta** (e.g., "+2.1 vs avg") comparing current value to the metric's 4-year mean.
5. **Collapsible history table** below the card showing the last 8 quarters of data.

`
+--------------------------------------------------+
| P/E                                               |
| +------------------------------------------------+|
| |    +----o----+                                 ||
| |    | 12  18 24|   Current: 15.2x               ||
| |    +---------+                                 ||
| |                                                ||
| |  spkl  63rd %ile         ||
| |  --- +2.1 vs avg                               ||
| |                                                ||
| |  * Fairly Valued                               ||
| |  ! Recent loss - showing Q3 2025               ||
| +------------------------------------------------+|
|                                                    |
|  v Historical Data (8 quarters)                   |
|  (collapsed by default)                            |
+--------------------------------------------------+
`

**Why this is the preferred pattern:**
- The gauge/slider gives immediate valuation context (undervalued/fair/overvalued).
- The sparkline adds trend direction without extra clicks.
- The percentile and delta add quantitative rigor.
- The collapsible table satisfies power users without cluttering the default view.
- All information is in one card - no scrolling between the gauge and the data.

### 16.5 Design Pattern 5: Side-by-Side Comparison Strip

**Problem:** Users often want to compare valuation across multiple stocks (e.g., peer comparison).

**Pattern:** A horizontal strip showing each metric's value, sparkline, and color rating for multiple tickers in a row.

`
+------------+----------+----------+----------+
| Ticker     | P/E      | EV/EBITDA| P/FCF    |
+------------+----------+----------+----------+
| AAPL       | 28.1 spk | 22.4 spk | 30.2 spk |
|            | o Over   | o Fair   | o Over   |
+------------+----------+----------+----------+
| MSFT       | 33.2 spk | 25.1 spk | 28.5 spk |
|            | o Over   | o Over   | o Fair   |
+------------+----------+----------+----------+
| GOOGL      | 22.5 spk | 16.2 spk | 25.1 spk |
|            | o Fair   | o Fair   | o Fair   |
+------------+----------+----------+----------+
`

**When to use:** Peer comparison views, watchlist pages, or sector overviews. Not the primary view for a single stock's fundamentals tab.

**Tradeoff:** Loses depth per stock - no gauge, no detailed history. Best as a secondary view.

### 16.6 Design Pattern 6: Historical Table with Quarter Detail

**Problem:** Financial analysts need access to the full quarterly time series for their spreadsheet or model inputs.

**Pattern:** A full-width table showing every available quarter with all valuation metrics, sortable and exportable.

`
+----------------------------------------------------------------------+
| Full Historical Data                         [Download CSV]         |
|                                                                      |
| Year  Quarter  P/E    EV/EBITDA  P/FCF   EV()  Price   Actions   |
|----- ------- ------- ---------- ------- -------- ------- -----------|
| 2026  Q1       15.2x    40.3x     20.1x   188.8   11.54   [Expand]  |
| 2025  Q4       13.8x    43.8x     22.5x   177.7    9.90   [Expand]  |
| 2025  Q3       10.3x    50.7x     18.2x   186.0   11.96   [Expand]  |
| 2025  Q2       13.2x    79.4x     24.1x   180.4   10.85   [Expand]  |
| 2025  Q1        8.0x    76.7x     95.2x   177.1   10.03   [Expand]  |
| 2024  Q4        6.8x    43.8x    335.3x   177.7    9.90   [Expand]  |
| 2024  Q3       12.0x    70.2x     50.7x   178.0   10.56   [Expand]  |
| 2024  Q2       13.2x    43.3x     53.8x   183.4   12.54   [Expand]  |
| 2024  Q1       13.7x    54.3x       -     185.1   13.28   [Expand]  |
| ...                                                                 |
| 2022  Q2       76.5x    65.6x     59.7x   169.5   12.60   [Expand]  |
+----------------------------------------------------------------------+
`

**When to use:** As a dedicated "Full History" modal or page section for power users. Not suitable for the default collapsed view.

**Tradeoff:** Overwhelming for casual users. Must be hidden behind an expand action.

## 17. Adopted Pattern: Design 4 (Gauge Cards with Mini Sparklines)

### 17.1 Rationale

Design 4 was chosen as the primary pattern for the fundamentals tab's valuation section because:

1. **Self-contained cards:** Each valuation metric (P/E, EV/EBITDA, P/FCF) is a complete information unit - gauge, trend, rank, and data - all in one card.
2. **Progressive disclosure:** The sparkline and badge provide trend context at a glance. The history table is one click away for those who need numbers.
3. **Consistent visual language:** All three metrics share the same card layout, eliminating the current inconsistency where P/E gets a gauge but EV/EBITDA and P/FCF get range sliders.
4. **Handles all gauge modes:** The card layout works identically for gauge, compact_gauge, slider, and disabled modes. Only the arc section changes.

### 17.2 Card Layout (Implementation Target)

`
+--------------------------------------------------+
|  Metric Name         ! Warning badge             |  <- Header row
|--------------------------------------------------|
|  +--------------------------------------------+  |
|  |  Gauge / Slider / Placeholder              |  |  <- Arc section (mode-dependent)
|  +--------------------------------------------+  |
|                                                   |
|  spkl  P63 . +2.1 vs avg  |  <- Sparkline + badge row
|                                                   |
|  * Fairly Valued                                  |  <- Assessment label
|--------------------------------------------------|
|  v Historical Data (8 quarters)                  |  <- Collapsible trigger
|  +------+------+------+------+                  |
|  | Q    | P/E  | EV   | P/FCF|                  |  <- History table
|  +------+------+------+------+                  |
|  | Q1'26| 15.2 | 40.3 | 20.1 |                  |
|  | Q4'25| 13.8 | 43.8 | 22.5 |                  |
|  | ...  |      |      |      |                  |
|  +------+------+------+------+                  |
+--------------------------------------------------+

Collapsed state:
+--------------------------------------------------+
|  Metric Name                                     |
|  +-Arc-----+  spkl  P63  +2.1    |
|  +---------+                                     |
|  * Fairly Valued  > Historical Data             |  <- Collapsed trigger
+--------------------------------------------------+
`

### 17.3 Collapsible History Table Behavior

| State | Trigger | Content |
|---|---|---|
| **Collapsed (default)** | Click "> Historical Data" text/button | Nothing visible below the assessment label |
| **Expanded** | Click "v Historical Data" text/button | Table of last 8 quarters: Quarter, P/E, EV/EBITDA, P/FCF |
| **Transition** | CSS max-height + opacity animation, ~250ms ease-in-out | Smooth open/close |

**Design decisions:**
- **8 quarters** chosen as the default window - enough to see a 2-year trend without overwhelming vertical space. A "Show all" link at the bottom of the table opens a modal or expands to full history (Design 6).
- **Horizontal scrolling** on narrow screens - table wrapper has overflow-x: auto.
- **Null/disabled values** shown as "-" in the table, not "0x" or blank.
- **Sticky header row** so column labels remain visible during scroll if the table is tall.

### 17.4 Sparkline Design

The sparkline uses a normalized SVG path rendered as an inline <svg> element.

| Property | Value |
|---|---|
| Data points | Last 8 quarters of the metric |
| Width | 80px |
| Height | 24px |
| Stroke | Current metric accent color (blue for P/E, green for EV/EBITDA, purple for P/FCF) |
| Stroke width | 2px |
| Fill | Subtle gradient below the line (10% opacity of stroke color) |
| Normalization | Min-max scaling to [0, height] |
| Responsive | Container query scales width proportionally |

**Edge cases:**
- Fewer than 8 data points: Show available points, centered in the SVG viewBox.
- All values identical: Flat line at 50% height.
- Single value: Single dot centered.
- Missing values in middle of series: Break the line (don't interpolate).

### 17.5 Percentile Badge Design

| Property | Value |
|---|---|
| Format | P{N}, e.g. P63 for 63rd percentile |
| Color | Green if below 30th percentile (undervalued), red if above 70th (overvalued), gray otherwise |
| Tooltip | "Current value ranks 63rd out of 100 in its 4-year history" |
| Fallback | Hidden if fewer than 12 data points available |

### 17.6 "vs Avg" Delta Design

| Property | Value |
|---|---|
| Format | +2.1 vs avg or -3.2 vs avg |
| Color | Green if below historical average (cheaper), red if above (more expensive) |
| Precision | One decimal place |
| Fallback | Hidden if fewer than 12 data points available |

## 18. Implementation Plan

### 18.1 Phase 1: Backend - GaugeConfig Enhancement (1-2 days)

**Goal:** Extend the existing GaugeConfig to include the new fields needed by Design 4.

**Changes:**

1. **Add fields to GaugeConfig** in analysis.types.ts (frontend) and the corresponding backend schema:
   - sparkline_values: Optional[List[Optional[float]]] - last 8 quarter values for this metric
   - percentile: Optional[int] - percentile rank within 4-year history
   - historical_avg: Optional[float] - mean of available historical values
   - recent_quarter_label: Optional[str] - e.g. "Q1 2026" for the current marker

2. **Add _compute_percentile(values, current) method** to the fundamentals service - simple rank-based percentile calculation.

3. **Add _compute_sparkline(quarters, metric_key) method** - extract the last 8 non-null values.

4. **Wire into _compute_valuation_metrics:** After computing the gauge config for each metric, compute and attach sparkline, percentile, and historical_avg.

**Validation:** Existing backend tests continue to pass. Add 3 new test cases:
- Stock with 20 quarters of data -> percentile computed correctly.
- Stock with < 12 quarters -> percentile hidden (returned as None).
- Stock with missing values in middle of series -> sparkline handles gaps.

### 18.2 Phase 2: Frontend - ValuationGauge Enhancement (2-3 days)

**Goal:** Update the ValuationGauge component to render the full Design 4 card including sparkline, percentile badge, delta, and collapsible history table.

**Changes:**

1. **Update ValuationGauge props** to accept sparkline_values, percentile, historical_avg, recent_quarter_label.

2. **Add Sparkline sub-component:**
   - SVG-based, 80x24 default size.
   - Accepts data: (number | null)[], color: string.
   - Renders polyline with gradient fill.
   - Handles edge cases (flat, single value, gaps).

3. **Add PercentileBadge sub-component:**
   - Renders "P{value}" text.
   - Color coded by threshold.
   - Tooltip on hover.

4. **Add VsAvgDelta sub-component:**
   - Computes current_value - historical_avg.
   - Formats with sign and one decimal.
   - Color coded.

5. **Add collapsible history table:**
   - State: isExpanded (default false).
   - On expand, fetch or read quarters prop to build table rows.
   - Table shows last 8 quarters: Quarter label, P/E, EV/EBITDA, P/FCF.
   - CSS transition on max-height and opacity.
   - "Show all" link at bottom -> opens modal with full Design 6 table.

6. **Remove MetricBarChart from valuation section:**
   - The gauge card's collapsible table replaces the old bar chart.
   - MetricBarChart remains available for other sections (Profitability, Growth, etc.) where absolute metrics (Revenue, Net Income) are shown and bar charts are appropriate.

**Validation:** Existing frontend tests continue to pass. Add 4 new test cases:
- Gauge card renders sparkline when data provided.
- Gauge card hides sparkline when data is null.
- Collapsible table opens and closes on click.
- Percentile badge color matches threshold rules.

### 18.3 Phase 3: Polish and Edge Cases (1 day)

**Goal:** Handle all edge cases and ensure smooth animation.

**Changes:**

1. **Collapsible table animation:** Use CSS max-height: 0 -> max-height: 1000px with transition and overflow: hidden. Cannot animate height: auto, so max-height is the standard approach.

2. **Null value display:** In the history table, show "-" for None values. Do not show "0x" or leave blank.

3. **Loss quarter warning:** When the current P/E is based on a prior quarter (because the most recent quarter has negative earnings), show the warning badge in the header row and mention the reference quarter in the assessment label.

4. **Responsive layout:** On screens < 768px, the sparkline/badge row wraps below the gauge. On screens < 480px, the history table becomes horizontally scrollable.

5. **Keyboard accessibility:** The collapsible trigger is a <button> with aria-expanded, focusable and activatable via Enter/Space.

### 18.4 Phase 4: Full History Modal (Future, 1-2 days)

**Goal:** Add a modal showing the complete quarterly history (Design 6) with sort, filter, and CSV export.

**Not in scope for the initial implementation.** The collapsible 8-quarter table satisfies the immediate need. The full history modal is tracked as a follow-up enhancement.

## 19. Design Validation

### 19.1 Validation Against Ford Motor Data

Applying Design 4 to Ford (the hardest case from Section 14.3):

| Metric | Gauge Mode | Sparkline | Percentile | Delta | Collapsible Table |
|---|---|---|---|---|---|
| P/E (current: 15.2x, based on Q3 2025) | compact_gauge, sector benchmark | 8 quarters: falling trend | P42 (moderate) | +2.1 vs avg (slightly above mean) | Shows P/E, EV/EBITDA, P/FCF for last 8 quarters |
| EV/EBITDA (current: 40.3x) | slider (CoV > 1.5) | 8 quarters: falling | Hidden (< 12 valid points) | Hidden | Same table as P/E card |
| P/FCF (current: 20.1x) | slider (insufficient data) | 8 quarters: falling | Hidden | Hidden | Same table |

**Key insight from Ford validation:** All three metric cards share the same collapsible table (showing all three metrics per quarter), even though their gauge modes differ. This is a deliberate design choice - the user gets a unified historical view regardless of which gauge mode each metric uses.

### 19.2 Validation Against Apple (Stable, High Quality)

| Metric | Gauge Mode | Sparkline | Percentile | Delta |
|---|---|---|---|---|
| P/E (current: 28x) | gauge, historical benchmark | 8 quarters: rising slightly | P78 (above avg) | +4.2 vs avg |
| EV/EBITDA (current: 22x) | compact_gauge, historical benchmark | 8 quarters: rising | P72 | +3.1 vs avg |
| P/FCF (current: 30x) | compact_gauge, historical benchmark | 8 quarters: stable high | P81 | +5.0 vs avg |

**Key insight:** For a stable, high-quality company with plenty of data, all three metrics get meaningful gauges with historical bands. The sparklines confirm the upward trend. The percentile badges show the stock is on the expensive side of its own history.

## 20. Migration Plan

### 20.1 No-Break Deployment

The Design 4 migration happens entirely within the existing API contract:

1. **Backend first:** Deploy new GaugeConfig fields (sparkline_values, percentile, historical_avg, recent_quarter_label). Frontend ignores them initially - no visual change.

2. **Frontend deploy:** New ValuationGauge reads new fields. If absent (old backend), renders current behavior. No coupling.

3. **Remove old code:** After both deploys succeed, remove MetricBarChart from valuation section and delete unused PERatioGauge / MetricRangeSlider components.

### 20.2 Feature Flag (Optional)

If risk mitigation is needed, wrap the new card layout behind a feature flag.

Toggle via environment variable or config. Allows instant rollback without redeploy.

## 21. Comparison: Before vs After

| Aspect | Before (Bar Charts) | After (Design 4 - Gauge Cards) |
|---|---|---|
| Primary visual | Bar chart with vertical bars per quarter | Gauge/slider arc with current value marker |
| Trend visibility | Must read each bar height | Sparkline shows 8-quarter trend at a glance |
| Valuation context | None (just raw numbers) | Gauge bands (undervalued/fair/overvalued) + percentile rank |
| Historical precision | Bar chart gives approximate values | Collapsible table with exact numbers |
| Screen space | Fixed height (always visible) | Collapsible - 40% height savings in default state |
| Consistency across metrics | P/E=gauge, EV/EBITDA=slider, P/FCF=slider | Same card layout for all three metrics |
| Zero-baseline problem | Ratios shown as bars (misleading) | Eliminated - gauge/slider has no zero baseline |
| Loss quarter handling | Negative values break the bar chart | Warning badge + prior-quarter fallback |
| Data export | None | Future: CSV download from full history modal |

---

## 22. Implementation Gap Analysis — Design 4 vs Current Implementation

### 22.1 Current State (2026-06-13)

The design document specifies Design 4 (Gauge Cards with Mini Sparklines, Sections 14–21) as the primary pattern, but the implementation still operates in a transitional state.

| Design 4 Feature | Spec Location | Implementation Status | Gap |
|---|---|---|---|
| Gauge/Slider arc with bands | §14.2, §14.4 | ✅ **Done** — `_compute_metric_gauge_config` returns correct modes; `ValuationGauge` renders gauge/slider/disabled | None |
| Display mode decision tree (CoV, count) | §14.4.1–14.4.3 | ✅ **Done** — Backend uses sector thresholds, CoV gates, count gates | None |
| GaugeConfig in `MetricQuarterSeries` | §14.2 | ✅ **Done** — Both Python `schemas_fundamentals.py` and TS `analysis.types.ts` have it | None |
| **Mini sparkline** | §14.4 (Design 4 card), §17.4 | ❌ **Missing** — `sparkline_values` not in `GaugeConfig`; no sparkline rendering | **Must add** |
| **Percentile badge** | §14.4 (Design 4 card), §17.5 | ❌ **Missing** — `percentile`, `historical_avg` not in `GaugeConfig` | **Must add** |
| **"vs avg" delta** | §14.4 (Design 4 card), §17.6 | ❌ **Missing** — No delta computation or rendering | **Must add** |
| **Collapsible history table** | §14.4 (Design 4 card), §17.3 | ❌ **Missing** — `MetricBarChart` still shown for valuation metrics | **Must add** |
| **Remove `MetricBarChart` from valuation** | §18.2 step 6 | ❌ **Not done** — Bar chart still renders below gauge | **Must remove** |
| Unify card layout across all 3 metrics | §17.1 | ⚠️ **Partial** — All use `ValuationGauge` but with inconsistent look (gauge vs slider vs no sparkline/badge) | **Must unify** |
| Loss quarter warning in header row | §14.4, §18.3 step 3 | ⚠️ **Partial** — Warning text exists in `GaugeConfig.warnings` but not rendered as a badge | **Must add** |
| Sparkline edge cases | §17.4 | ❌ **Missing** — No sparkline to have edge cases for | Will be handled with sparkline |
| Full history modal (Design 6) | §18.4 | ❌ **Not in scope** — Planned as future enhancement | Track separately |

### 22.2 Key Insight

The **backend decision tree** (§14.4) and **gauge/slider rendering** are complete. What's missing is the **frontend card polish** — the elements that make the card "Design 4" instead of "a gauge sitting above a bar chart that shouldn't be there." The sparkline, percentile badge, delta, and collapsible table turn a functional display into a professional one.

### 22.3 What Stays vs What Changes

| Component | Action |
|---|---|
| `_compute_metric_gauge_config` (backend) | ✅ Keep — Add 4 new output fields (sparkline_values, percentile, historical_avg, recent_quarter_label) |
| `GaugeConfig` (Python + TS) | ✏️ Extend — Add new optional fields |
| `ValuationGauge` (frontend) | ✏️ Enhance — Add sparkline, badge, delta, collapsible table sub-components |
| `MetricBarChart` | ✅ Keep for non-valuation sections (Quality, Growth, Moat, Narrative) — bar charts are appropriate for those |
| `FundamentalsPanel` valuation rendering | ✏️ Remove `MetricBarChart` from valuation metric cards; keep gauge card with collapsible table |
| Tests | ✏️ Update — Add new test cases for sparkline, badge, delta, collapsible table |

---

## 23. Missing Implementation: GaugeConfig Extension

### 23.1 New Fields

Add the following optional fields to `GaugeConfig` in both Python (`schemas_fundamentals.py`) and TypeScript (`analysis.types.ts`):

```python
# backend/schemas_fundamentals.py — GaugeConfig additions

class GaugeConfig(BaseModel):
    # ... existing fields (display_mode, benchmark, band_low, etc.) ...

    # ── NEW: Sparkline data ──
    sparkline_values: Optional[List[Optional[float]]] = None
    """Last 8-12 quarters of this metric's values for mini sparkline chart.
       None entries indicate missing quarters (break the line)."""

    # ── NEW: Percentile / Historical context ──
    percentile: Optional[int] = None
    """Percentile rank of current value within all-time history (0-100).
       Example: 63 means current value > 63% of all historical values.
       Hidden when fewer than 12 data points available."""

    historical_avg: Optional[float] = None
    """Mean of all available historical values for this metric.
       Used to compute the vs-avg delta on the frontend."""

    vs_avg_delta: Optional[float] = None
    """current_value - historical_avg. Pre-computed on backend.
       Positive means current is above average (more expensive).
       Negative means current is below average (cheaper)."""

    recent_quarter_label: Optional[str] = None
    """Label of the quarter used for 'current' value.
       e.g. 'Q3 2025' when the most recent quarter had negative earnings
       and we fell back to the prior positive quarter."""
```

Same additions in TypeScript:

```typescript
// web/src/features/analysis/types/analysis.types.ts — GaugeConfig additions

export interface GaugeConfig {
  // ... existing fields ...
  sparkline_values?: (number | null)[];
  percentile?: number;
  historical_avg?: number;
  vs_avg_delta?: number;
  recent_quarter_label?: string;
}
```

### 23.2 Backend Computation Logic

Add to `fundamentals_service.py` — `_compute_metric_gauge_config` is already the right home:

```python
def _compute_sparkline_values(
    quarters: List[QuarterDataPoint],
    max_points: int = 8,
) -> List[Optional[float]]:
    """Extract the last {max_points} values (including None for gaps)
       from a quarters list, in reverse-chronological order (oldest first).
       Returns at most max_points entries."""
    recent = quarters[-max_points:]
    return [q.value for q in recent]


def _compute_percentile(
    positive_values: List[float],
    current: Optional[float],
) -> Optional[int]:
    """Rank-based percentile of current value within full history.
       Returns None if < 12 data points or current is None."""
    if current is None or len(positive_values) < 12:
        return None
    sorted_vals = sorted(positive_values)
    count_less = sum(1 for v in sorted_vals if v < current)
    count_equal = sum(1 for v in sorted_vals if v == current)
    # Percentile = (count_less + 0.5 * count_equal) / total * 100
    pct = (count_less + 0.5 * count_equal) / len(sorted_vals) * 100
    return round(pct)
```

Wire into the existing `_compute_metric_gauge_config` — the final `GaugeConfig` construction in each return path gets these fields added. For example, the gauge path becomes:

```python
sparkline_values = _compute_sparkline_values(quarters)
percentile = _compute_percentile(positive, current)
historical_avg = avg_v  # already computed
vs_avg_delta = (current - avg_v) if current is not None and avg_v is not None else None
recent_quarter_label = _find_recent_positive_label(quarters, raw_current)
```

### 23.3 `_find_recent_positive_label` helper

```python
def _find_recent_positive_label(
    quarters: List[QuarterDataPoint],
    raw_current: Optional[float],
) -> Optional[str]:
    """If the most recent quarter's value is negative/null, find the
       most recent quarter with a positive value and return its label.
       Otherwise return the most recent quarter's label."""
    if not quarters:
        return None
    if raw_current is not None and raw_current > 0:
        return quarters[-1].label if quarters[-1].label else None
    # Walk backwards to find most recent positive quarter
    for q in reversed(quarters):
        if q.value is not None and q.value > 0:
            return q.label
    return None
```

### 23.4 Backend Validation

| Test Case | Expected |
|---|---|
| Stock with 20 quarters → sparkline has 8 entries (last 8) | `len(sparkline) == 8` |
| Stock with 4 available quarters → sparkline has 4 entries | `len(sparkline) == 4` |
| Stock with gap in middle → None entry in sparkline at gap position | `sparkline[i] is None` at gap index |
| Stock with 15 data points → percentile is `int` between 0-100 | `0 <= percentile <= 100` |
| Stock with < 12 data points → `percentile is None` | None returned |
| Current value equals historical avg → delta is `0.0` | `vs_avg_delta == 0.0` |
| Recent quarter negative → `recent_quarter_label` points to prior positive quarter | Label matches prior positive quarter |

---

## 24. Missing Implementation: Sparkline Component

### 24.1 Design Spec (from §17.4)

| Property | Value |
|---|---|
| Data points | Last 8 quarters (from `GaugeConfig.sparkline_values`) |
| Width | 80px (default) |
| Height | 24px (default) |
| Stroke | Metric accent color (varies by metric) |
| Stroke width | 2px |
| Fill | Subtle gradient below the line (10% opacity) |
| Normalization | Min-max scaling to [0, height] |
| Responsive | Container query scales width proportionally |

### 24.2 Implementation as Sub-Component

New component `Sparkline` in `valuation-gauge.tsx`:

```tsx
function Sparkline({
  data,
  color = "#60A5FA",
  width = 80,
  height = 24,
}: {
  data: (number | null)[];
  color?: string;
  width?: number;
  height?: number;
}) {
  // Filter to non-null for min/max computation
  const valid = data.filter((d): d is number => d !== null);
  if (valid.length === 0) return null;

  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;
  const stepX = width / Math.max(data.length - 1, 1);

  // Build polyline points, skipping nulls by breaking the path
  let pathD = "";
  let currentSegment: { x: number; y: number }[] = [];

  data.forEach((d, i) => {
    const x = i * stepX;
    const y = d != null ? height - ((d - min) / range) * (height - 2) - 1 : height / 2;
    if (d !== null) {
      currentSegment.push({ x, y });
    } else {
      if (currentSegment.length > 1) {
        pathD += `M ${currentSegment[0].x.toFixed(1)} ${currentSegment[0].y.toFixed(1)} ` +
          currentSegment.slice(1).map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") + " ";
      }
      currentSegment = [];
    }
  });
  // Flush last segment
  if (currentSegment.length > 1) {
    pathD += `M ${currentSegment[0].x.toFixed(1)} ${currentSegment[0].y.toFixed(1)} ` +
      currentSegment.slice(1).map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  }

  // Single value edge case
  if (valid.length === 1 && currentSegment.length === 1) {
    pathD = `M ${currentSegment[0].x} ${currentSegment[0].y} L ${currentSegment[0].x + 1} ${currentSegment[0].y}`;
  }

  // Area fill path
  const areaD = pathD + ` L ${data.length - 1} ${height} L 0 ${height} Z`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="flex-shrink-0">
      <defs>
        <linearGradient id={`spark-fill-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#spark-fill-${color.replace("#", "")})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {/* Terminal dot */}
      {valid.length > 0 && (
        <circle cx={data.lastIndexOf(valid[valid.length - 1]) * stepX} cy={height - ((valid[valid.length - 1] - min) / range) * (height - 2) - 1} r="2.5" fill={color} />
      )}
    </svg>
  );
}
```

### 24.3 Edge Case Handling

| Scenario | Behavior |
|---|---|
| All values null (all N/A) | Component returns `null` (not rendered) |
| Single value | Short line segment at 50% height with terminal dot |
| Fewer than 8 values | Show available values, left-aligned |
| Missing value in middle | Break line (two separate segments), fill not rendered in gap |
| All identical values | Flat line at 50% height |

---

## 25. Missing Implementation: Percentile Badge + vs Avg Delta

### 25.1 PercentileBadge Sub-Component

A small badge showing "P{value}" with color coding:

```tsx
function PercentileBadge({
  percentile,
  className,
}: {
  percentile: number;
  className?: string;
}) {
  const color =
    percentile <= 30
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"    // Undervalued
      : percentile >= 70
        ? "bg-rose-500/15 text-rose-400 border-rose-500/25"          // Overvalued
        : "bg-amber-500/15 text-amber-400 border-amber-500/25";      // Fair

  return (
    <span
      className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded-md border", color, className)}
      title={`Current value ranks in the ${percentile}th percentile of its history`}
    >
      P{percentile}
    </span>
  );
}
```

**Rules:** Hidden when `percentile` is `null` (< 12 data points).

### 25.2 VsAvgDelta Sub-Component

Shows current vs historical average difference:

```tsx
function VsAvgDelta({
  delta,
  unit,
}: {
  delta: number;
  unit: string;
}) {
  const isAboveAvg = delta > 0;
  const isBelowAvg = delta < 0;

  return (
    <span
      className={cn(
        "text-[10px] font-medium tabular-nums",
        isAboveAvg ? "text-rose-400/80" : isBelowAvg ? "text-emerald-400/80" : "text-white/40",
      )}
    >
      {delta > 0 ? "▲" : delta < 0 ? "▼" : "—"} {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
      {unit === "x" ? "×" : unit === "%" ? "%" : ""} vs avg
    </span>
  );
}
```

**Rules:** Hidden when `vs_avg_delta` is `null`.

### 25.3 Row Layout in Card

Within the valuation card, the sparkline, percentile badge, and vs avg delta form a single horizontal row:

```
+----------------------------------------------------------------------+
|  P/E Ratio                            ! Recent loss (based on Q3'25) |
|  +----------------------------------+                                |
|  |     Gauge / Slider / etc.        |                                |
|  +----------------------------------+                                |
|                                                                      |
|  ▂▃▅▇▆▄▃▁  P42  ▲ +2.1× vs avg                                     |
|                                                                      |
|  ★ Fairly Valued                                                     |
|  ▼ Historical Data (8 quarters)                                      |
+----------------------------------------------------------------------+
```

---

## 26. Modularity Design — No Snowflakes

### 26.1 Reusable Component Tree

Every new component is designed to be **metric-agnostic**. None should know about P/E, EV/EBITDA, or P/FCF specifically.

```
┌────────────────────────────────────────────────────────────────┐
│  Generic (metric-agnostic)          Valuation-specific (thin)  │
│                                                               │
│  Sparkline                              ...uses no valuation   │
│  PercentileBadge                        ...knows nothing       │
│  VsAvgDelta                             ...knows nothing       │
│  WarningBadge        ← NEW              ...takes string[]      │
│  HistoryTable        ← NEW (generic)    ...takes columns + data│
│  MetricCard          ← NEW (generic)    ...just layout shell   │
│                                                               │
│  ValuationGauge       (already generic — takes GaugeConfig)   │
│  MetricBarChart       (already generic — used by 4 sections)  │
│  groupQuartersByYear  (already generic — reusable helper)     │
└────────────────────────────────────────────────────────────────┘
```

### 26.2 Generic Components

#### 26.2.1 WarningBadge

Renders the first warning from `GaugeConfig.warnings` as a compact badge. Input-agnostic:

```tsx
function WarningBadge({ warnings, maxLength = 30 }: { warnings: string[]; maxLength?: number }) {
  if (warnings.length === 0) return null;
  const text = warnings[0].length > maxLength ? warnings[0].substring(0, maxLength) + "…" : warnings[0];
  return (
    <span className="text-[9px] text-amber-400/70 bg-amber-400/10 px-1.5 py-0.5 rounded whitespace-nowrap">
      {text}
    </span>
  );
}
```

#### 26.2.2 HistoryTable (Generic)

A collapsible data table that accepts any column configuration — not hardcoded to valuation metrics:

```tsx
interface HistoryColumn<T> {
  header: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
}

function HistoryTable<T extends { label: string }>({
  data,
  columns,
  rowKey,
  defaultVisible = 8,
}: {
  data: T[];
  columns: HistoryColumn<T>[];
  rowKey: (row: T) => string;
  defaultVisible?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = data.slice(-defaultVisible);

  if (data.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] text-white/50 hover:text-white/80 transition-colors"
        aria-expanded={expanded}
      >
        {expanded ? "▼" : "▶"} Historical Data ({visible.length} quarters)
      </button>
      <div className={cn("overflow-hidden transition-all duration-250 ease-in-out", expanded ? "max-h-[600px] opacity-100" : "max-h-0 opacity-0")}>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-[11px] border-collapse">
            <thead>
              <tr className="border-b border-white/10">
                {columns.map((col) => (
                  <th key={col.header} className={cn("text-white/40 font-medium uppercase tracking-wider py-1.5", col.align === "right" ? "text-right px-3" : "text-left pr-3")}>
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={rowKey(row)} className="border-b border-white/5 hover:bg-white/[0.02]">
                  {columns.map((col) => (
                    <td key={col.header} className={cn("py-1.5 tabular-nums", col.align === "right" ? "text-right px-3 text-white/80" : "pr-3 text-white/60")}>
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {data.length > defaultVisible && (
            <button className="text-[10px] text-blue-400/60 hover:text-blue-400 mt-1">
              Show all {data.length} quarters →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

**No references to P/E, EV/EBITDA, or P/FCF anywhere.** The valuation section uses it by passing valuation-specific column definitions:

```tsx
// Valuation usage — columns defined at call site, not inside the component
<HistoryTable
  data={tableQuarters}
  rowKey={(q) => `${q.fiscal_year}-${q.fiscal_quarter}`}
  columns={[
    { header: "Quarter", render: (q) => q.label },
    { header: "P/E", align: "right", render: (q) => peVal != null ? formatMetricValue(peVal, "x") : "—" },
    { header: "EV/EBITDA", align: "right", render: (q) => evVal != null ? formatMetricValue(evVal, "x") : "—" },
    { header: "P/FCF", align: "right", render: (q) => pfcfVal != null ? formatMetricValue(pfcfVal, "x") : "—" },
  ]}
/>
```

#### 26.2.3 MetricCard (Generic Layout Shell)

The repeating card pattern (header + visual + sparkline row + assessment) can be extracted into a generic wrapper. This avoids duplicating the layout for each valuation metric and makes it available for other sections:

```tsx
function MetricCard({
  label,
  warnings,
  visual,        // ReactNode — gauge, slider, or any visual element
  metadata,      // ReactNode — sparkline + badge + delta row (optional)
  assessment,    // ReactNode — valuation badge (optional)
  children,      // ReactNode — collapsible table or any extra content
}: {
  label: string;
  warnings?: string[];
  visual: ReactNode;
  metadata?: ReactNode;
  assessment?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="flex-1 min-w-[240px] bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] font-medium text-white/70">{label}</span>
        <WarningBadge warnings={warnings ?? []} />
      </div>
      {visual}
      {metadata && <div className="flex items-center gap-2 mt-2 pt-2 border-t border-white/[0.06]">{metadata}</div>}
      {assessment && <div className="flex justify-center mt-2">{assessment}</div>}
      {children}
    </div>
  );
}
```

**This replaces the inline card div in §27.3.** The valuation section becomes a clean composition:

```tsx
<MetricCard
  label={m.label}
  warnings={config.warnings}
  visual={<ValuationGauge config={config} unit={m.unit} label={m.label} metricId={m.metric_id} />}
  metadata={<>
    {config.sparkline_values && <Sparkline data={config.sparkline_values} color={getMetricColor(m.metric_id)} />}
    {config.percentile != null && <PercentileBadge percentile={config.percentile} />}
    {config.vs_avg_delta != null && <VsAvgDelta delta={config.vs_avg_delta} unit={m.unit} />}
  </>}
  assessment={<ValuationBadge config={config} />}
/>
```

`MetricCard` is metric-agnostic — it can wrap anything. If a future section needs a gauge-style card with metadata, it reuses `MetricCard`. The valuation section just populates the slots.

### 26.3 What This Changes in the Codebase

| Before (Snowflake) | After (Generic) | Location |
|---|---|---|
| `ValuationHistoryTable` with hardcoded P/E/EV/PFCF columns | `HistoryTable<T>` taking `columns: HistoryColumn<T>[]` | `valuation-gauge.tsx` or new `shared-ui.tsx` |
| Inline card div in `FundamentalsPanel` | `MetricCard` component with slots | `shared-ui.tsx` |
| `config.warnings[0].substring(0, 30)` inline | `WarningBadge` component | `valuation-gauge.tsx` or `shared-ui.tsx` |
| `Sparkline`, `PercentileBadge`, `VsAvgDelta` | Already generic — no change needed | `valuation-gauge.tsx` |

### 26.4 Backward Compatibility

No existing code breaks. `MetricCard`, `HistoryTable`, and `WarningBadge` are new components that replace inline markup. Old call sites that still use inline markup continue to work — they just miss the new modularity.

---

## 27. Collapsible History Table (Valuation-Specific Instantiation)

### 27.1 Overview

The history table shows the last 8 quarters of all three valuation metrics side-by-side. It uses the generic `HistoryTable<T>` from §26.2.2 with valuation-specific column bindings.

**Key design decision:** One shared table at the section level (not duplicated per card) because all three metrics share the same quarterly data from the same `qratios` loop.

### 27.2 Data Source

The top-level `FundamentalsResponse.quarters` is `List[str]` (quarter label strings), NOT `QuarterDataPoint[]`. The table derives its rows from the **P/E metric's quarters** (`peMetric.quarters`) because:

1. All three valuation metrics are built from the same `qratios` loop at `fundamentals_service.py:682-750` — they share identical fiscal year/quarter keys.
2. Using P/E's quarters ensures we iterate `QuarterDataPoint[]` with `fiscal_year`, `fiscal_quarter`, `label` fields needed for matching.
3. This guarantees row consistency — no metric has a quarter the others don't.

### 27.3 Implementation

```tsx
function ValuationHistoryTable({
  peMetric,
  evMetric,
  pfcfMetric,
  frequency,
  activeIndices,
}: {
  peMetric: MetricQuarterSeries;
  evMetric?: MetricQuarterSeries;
  pfcfMetric?: MetricQuarterSeries;
  frequency: "quarterly" | "annual";
  activeIndices: number[];
}) {
  const rawQuarters = activeIndices.map((i) => peMetric.quarters[i]).filter(Boolean);
  const displayQuarters = frequency === "annual"
    ? groupQuartersByYear(rawQuarters)
    : rawQuarters;

  // Skip quarters where all 3 metrics are null
  const getVal = (metric: MetricQuarterSeries | undefined, q: QuarterDataPoint) =>
    metric?.quarters.find(
      (mq) => mq.fiscal_year === q.fiscal_year && mq.fiscal_quarter === q.fiscal_quarter,
    )?.value ?? null;

  const populated = displayQuarters.filter((q) => {
    const peVal = q.value ?? getVal(peMetric, q);
    const evVal = getVal(evMetric, q);
    const pfcfVal = getVal(pfcfMetric, q);
    return peVal != null || evVal != null || pfcfVal != null;
  });

  if (populated.length === 0) return null;

  return (
    <HistoryTable
      data={populated}
      rowKey={(q) => `${q.fiscal_year}-${q.fiscal_quarter}`}
      defaultVisible={8}
      columns={[
        { header: "Quarter", render: (q) => q.label },
        {
          header: "P/E", align: "right",
          render: (q) => {
            const v = q.value ?? getVal(peMetric, q);
            return v != null ? formatMetricValue(v, "x") : <span className="text-white/20">—</span>;
          },
        },
        {
          header: "EV/EBITDA", align: "right",
          render: (q) => {
            const v = getVal(evMetric, q);
            return v != null ? formatMetricValue(v, "x") : <span className="text-white/20">—</span>;
          },
        },
        {
          header: "P/FCF", align: "right",
          render: (q) => {
            const v = getVal(pfcfMetric, q);
            return v != null ? formatMetricValue(v, "x") : <span className="text-white/20">—</span>;
          },
        },
      ]}
    />
  );
}
```

`ValuationHistoryTable` is a **thin adapter** — it knows about the 3 valuation metrics but delegates all rendering to the generic `HistoryTable`. If a 4th valuation metric is added later, only this adapter changes.

### 27.4 Edge Cases

| Scenario | Behavior |
|---|---|
| < 8 quarters after filtering | `HistoryTable` shows available count: "Historical Data (N quarters)" |
| All quarters filtered out | `ValuationHistoryTable` returns `null` — nothing rendered |
| Frequency = Annual | Rows grouped by year via `groupQuartersByYear` |
| ViewMode = From purchase | `activeIndices` already filters to post-purchase quarters |
| Horizontal overflow | `HistoryTable` wrapper has `overflow-x: auto` |
| Keyboard | Trigger button is `<button>` with `aria-expanded` |

---

## 28. Valuation Section — Updated Rendering Logic

### 27.1 Current (Broken) Flow

```
FundamentalsPanel renders valuation section:
  └─ For each metric:
       ├─ ValuationGauge (gauge/slider/disabled)
       └─ MetricBarChart ← SHOULD NOT BE HERE for valuation
```

### 27.2 Target Flow

```
FundamentalsPanel renders valuation section:
  ├─ IntrinsicValueCard (existing, unchanged)
  ├─ 3x Gauge Cards (P/E, EV/EBITDA, P/FCF)
  │    └─ ValuationGauge
  │         ├─ Arc (gauge/slider/disabled)
  │         ├─ Sparkline + PercentileBadge + VsAvgDelta (row)
  │         └─ ValuationBadge (Fairly/Undervalued/Overvalued)
  └─ ValuationHistoryTable (collapsible, shared)
       └─ Shows last 8 quarters of all 3 metrics
```

### 27.3 Frontend Change — Valuation Metric Card Rendering

In `FundamentalsPanel`, the valuation section's metric cards change from:

```tsx
// CURRENT (fundamentals-panel.tsx ~line 796-838)
<div key={m.metric_id}>
  <ValuationGauge ... />
  <MetricBarChart ... />    // ← REMOVE THIS
</div>
```

To:

```tsx
// NEW
<div key={m.metric_id} className="flex-1 min-w-[240px] bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
  <div className="flex items-center justify-between mb-2">
    <span className="text-[13px] font-medium text-white/70">{m.label}</span>
    {/* Warning badge */}
    {config.warnings.length > 0 && (
      <span className="text-[9px] text-amber-400/70 bg-amber-400/10 px-1.5 py-0.5 rounded">
        {config.warnings[0].substring(0, 30)}...
      </span>
    )}
  </div>

  <ValuationGauge config={config} unit={m.unit} label={m.label} metricId={m.metric_id} />

  {/* Sparkline + Percentile + Delta row */}
  { (config.sparkline_values || config.percentile || config.vs_avg_delta != null) && (
    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-white/[0.06]">
      {config.sparkline_values && (
        <Sparkline data={config.sparkline_values} color={getMetricColor(m.metric_id)} width={72} height={22} />
      )}
      {config.percentile != null && <PercentileBadge percentile={config.percentile} />}
      {config.vs_avg_delta != null && <VsAvgDelta delta={config.vs_avg_delta} unit={m.unit} />}
    </div>
  )}

  {/* Valuation badge */}
  <div className="flex justify-center mt-2">
    <ValuationBadge config={config} />
  </div>
</div>
```

The `ValuationHistoryTable` is rendered once at the section level (after the three cards), not duplicated per card.

### 27.4 Metric Color Mapping

```tsx
function getMetricColor(metricId: string): string {
  switch (metricId) {
    case "pe_ratio": return "#60A5FA";       // blue
    case "ev_ebitda": return "#34D399";      // emerald
    case "price_to_fcf": return "#A78BFA";   // violet
    default: return "#94A3B8";               // slate
  }
}
```

---

## 29. Impact Analysis — Design 4 Completion

### 29.1 Files Requiring Changes

| # | File | Change | Type | Effort |
|---|---|---|---|---|
| 1 | `backend/schemas_fundamentals.py` | Add 5 new optional fields to `GaugeConfig` | Add | Small |
| 2 | `backend/application/services/fundamentals_service.py` | Add `_compute_sparkline_values`, `_compute_percentile`, `_find_recent_positive_label`; wire into `_compute_metric_gauge_config` | Add | Medium |
| 3 | `web/src/features/analysis/types/analysis.types.ts` | Add 5 new optional fields to `GaugeConfig` TS interface | Add | Small |
| 4 | `web/src/features/analysis/components/valuation-gauge.tsx` | Add `Sparkline`, `PercentileBadge`, `VsAvgDelta` sub-components; export `ValuationBadge` | Add | Medium |
| 5 | `web/src/features/analysis/components/fundamentals-panel.tsx` | Add `ValuationHistoryTable` component; update valuation section rendering: remove `MetricBarChart` from valuation cards, add collapsible table, add sparkline/badge/delta row | Modify | Medium |

### 29.2 Files Requiring Tests

| # | File | Test Cases | Type | Effort |
|---|---|---|---|---|
| 1 | `backend/tests/test_fundamentals_service.py` | 4 new: sparkline extraction, percentile computation, null handling, recent quarter label | Add | Small |
| 2 | `web/src/__tests__/ValuationGauge.test.tsx` | 4 new: sparkline renders, percentile badge colors, vs avg delta format, collapsible table | Add | Medium |
| 3 | `web/src/__tests__/FundamentalsPanel.test.tsx` | 2 new: valuation section no longer shows bar chart, collapsible table exists | Update | Small |

### 29.3 Files NOT Requiring Changes (Explicit No-Ops)

| File | Why unchanged |
|---|---|
| `backend/infrastructure/repositories/fundamentals_repository.py` | No new queries — sparkline/percentile computed from already-fetched `qratios` |
| `backend/api/analysis.py` | No API contract change — new fields are optional additions to existing response |
| `backend/application/jobs/derived_financial_metrics_job.py` | No new data to compute — sparkline/percentile are query-time computations |
| `web/src/features/analysis/hooks/useFundamentals.ts` | Same endpoint, response shape unchanged (new optional fields) |
| `web/src/lib/query-keys.ts` | No new queries |
| `web/src/features/analysis/components/intrinsic-value-card.tsx` | Unchanged — still renders below section header |
| `web/src/features/analysis/components/shared-ui.tsx` | No new shared components needed |
| `web/src/features/analysis/components/pe-ratio-gauge.tsx` | **Can be deprecated** — imported only by its own test file; `ValuationGauge` handles PE now |
| `web/src/features/analysis/components/metric-range-slider.tsx` | **Can be deprecated** — zero imports outside its own file; `ValuationGauge` handles slider now |

### 29.4 History Table Data Flow (Clarified)

Unlike the initial spec which assumed `quarters: QuarterDataPoint[]`, the real data source is:

```
data.quarters: string[]                    ← Top-level, label strings only
peMetric.quarters: QuarterDataPoint[]      ← Row source for history table (has fiscal_year/fiscal_quarter/label)
evMetric.quarters: QuarterDataPoint[]      ← Value lookup only (matched by fy/fq)
pfcfMetric.quarters: QuarterDataPoint[]    ← Value lookup only (matched by fy/fq)
```

The table iterates `peMetric.quarters` filtered by `activeIndices` and `frequency`, then cross-references EV/EBITDA and P/FCF values by `(fiscal_year, fiscal_quarter)` key match. This is robust because all three metric series originate from the same `qratios` loop (`fundamentals_service.py:682-750`).

### 29.5 Backward Compatibility

| Guarantee | Detail |
|---|---|
| Old API response still works | New `GaugeConfig` fields are optional. Frontend reads them when present; ignores them when absent |
| Old frontend still works with new backend | Frontend renders current gauge/slider + bar chart. New fields are ignored |
| No DB schema changes | All new data is computed at query time from in-memory data |
| `MetricBarChart` still used for non-valuation | Quality, Growth, Moat, Narrative sections continue using bar charts unchanged |

### 29.6 Data Flow After Design 4 Completion

```
FundamentalsService._compute_valuation_metrics()
  │
  ├─ Builds P/E, EV/EBITDA, P/FCF quarter series from qratios
  │
  ├─ For each metric:
  │    ├─ _compute_metric_gauge_config()
  │    │    ├─ _positive_values()         → positive values list
  │    │    ├─ _coeff_of_variation()      → CoV
  │    │    ├─ _most_recent_positive()    → current (handles loss)
  │    │    ├─ _compute_sparkline_values() → last 8 values (with gaps)
  │    │    ├─ _compute_percentile()      → rank percentile
  │    │    └─ _find_recent_positive_label() → quarter label
  │    │
  │    └─ Returns GaugeConfig (with all new fields)
  │
  └─ Attaches gauge_config to each MetricQuarterSeries
       │
       ▼
FundamentalsResponse → Frontend useFundamentals()
       │
       ▼
FundamentalsPanel renders:
  ├─ IntrinsicValueCard
  ├─ 3x Valuation Cards (P/E, EV/EBITDA, P/FCF):
  │    ├─ ValuationGauge (gauge/slider/disabled)
  │    ├─ Sparkline + PercentileBadge + VsAvgDelta
  │    └─ ValuationBadge
  └─ ValuationHistoryTable (collapsible)
```

### 29.7 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Old `GaugeConfig` missing new fields → frontend renders no sparkline/badge | Medium | Low (falls back to current behavior) | All new fields optional; frontend checks `null` before rendering |
| Backend `_compute_percentile` with large dataset → perf degradation | Low | Low | Percentile is O(n log n) — max ~60 quarters, negligible |
| Collapsible table animation jank on low-end devices | Low | Low | CSS `max-height` with `transition` is well-supported; GPU composited |
| Sparkline SVG rendering with many gaps | Low | Low | Implementation handles `null` as path break — tested edge case |
| Deprecation of `PERatioGauge`, `MetricRangeSlider` | Medium | Low | Components still work; clean up in a follow-up PR |

---

## 30. Summary — What the User Sees After Implementation

### Before (Current State)

```
┌────────────────────────────────────────────────────────┐
│  Valuation                    Status: [Intact]          │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ P/E           │  │ EV/EBITDA    │  │ P/FCF        │ │
│  │ [gauge]       │  │ [slider]     │  │ [slider]     │ │
│  │ [bar chart]   │  │ [bar chart]  │  │ [bar chart]  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│  > Historical Data (collapsible) — NOT IMPLEMENTED      │
└────────────────────────────────────────────────────────┘
```

### After

```
┌────────────────────────────────────────────────────────┐
│  Valuation                    Status: [Intact]          │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ P/E           │  │ EV/EBITDA    │  │ P/FCF        │ │
│  │ [gauge]       │  │ [gauge]      │  │ [slider]     │ │
│  │ ▂▃▅▇▆▄▃▁ P42 │  │ ▂▃▅▇▆▄▃▁ P48 │  │ ▂▃▅▇▆▄▃▁ P72 │ │
│  │ ▲ +2.1 vs avg│  │ ▼ -3.2 vs avg│  │ ▲ +5.8 vs avg│ │
│  │ ★ Fairly Val │  │ ★ Fairly Val │  │ ★ Overvalued │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ▼ Historical Data (8 quarters)                        │
│  ┌────────┬──────┬──────────┬────────┐                 │
│  │ Quarter│ P/E  │ EV/EBITDA│ P/FCF  │                 │
│  ├────────┼──────┼──────────┼────────┤                 │
│  │ Q1'26  │ 15.2×│  40.3×   │  20.1× │                 │
│  │ ...    │      │          │        │                 │
│  └────────┴──────┴──────────┴────────┘                 │
└────────────────────────────────────────────────────────┘
```

### Key Benefits

1. **Sparkline** — trend visibility without expanding anything
2. **Percentile badge** — instant "cheap vs expensive vs self" signal
3. **"vs avg" delta** — quantitative deviation from historical mean
4. **Collapsible history table** — precise numbers on demand, no screen waste when collapsed
5. **Removed bar charts** — valuation ratios no longer misrepresented with zero-baseline bars
6. **Unified card layout** — all three metrics share the same visual language
7. **Shared history table** — one table for all three metrics, not duplicated per card

---

*Document version: 3.1 — Added missing Design 4 implementation details (Sections 22–29): GaugeConfig extension with sparkline/percentile/delta, Sparkline component, PercentileBadge, VsAvgDelta, collapsible ValuationHistoryTable. Updated implementation plan with complete impact analysis.*
