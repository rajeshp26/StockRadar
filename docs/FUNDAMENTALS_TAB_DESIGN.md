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
| Valuation multiples | ✅ **Exists** | In `company_summary` table |
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
| | `ev_ebitda` | `company_summary` | Direct read (current-period only — no historical enterprise_value) |
| | `price_to_fcf` | `company_summary` + `cash_flow_statements` | EV / FCF (current-period only — no historical enterprise_value) |
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

##### ev_ebitda, price_to_fcf — Current-Period Only

`ev_ebitda` and `price_to_fcf` require `enterprise_value`, which is only available as a current daily snapshot from `company_summary`. Historical enterprise_value is not stored. These metrics remain single-snapshot (current period only), using the same `_flat_series` approach as before.

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
| `company_summary` irregular snapshots | EV/EBITDA and P/FCF are current-period only | No historical enterprise_value stored |
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
| EV/EBITDA, P/FCF | Remain single-snapshot from `company_summary` | ✅ No change |
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
| `docs/FUNDAMENTALS_TAB_DESIGN.md` | This document |
