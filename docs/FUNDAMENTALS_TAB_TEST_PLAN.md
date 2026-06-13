# Fundamentals Tab — Test Plan

> **Version:** 1.0  
> **Design:** Design improvements from `FUNDAMENTALS_TAB_DESIGN.md` vs code diff analysis  
> **Date:** 2026-06-12

---

## 1. Backend Unit Tests (`backend/tests/test_fundamentals_service.py`)

### 1.1 Trend Direction for Valuation Metrics

| # | Test | What It Verifies | Input | Expected |
|---|------|-----------------|-------|----------|
| 1 | `test_valuation_pe_trend_computed` | P/E series gets real trend from `_determine_trend` | qratios with 4 quarters of `trailing_pe = [20, 18, 15, 12]` | `trend_direction="down"`, `change_pct=-0.4`, `change_label="-40.0%"` |
| 2 | `test_valuation_ev_trend_computed` | EV/EBITDA series gets real trend | qratios with 4 quarters of `ev_ebitda = [8, 9, 10, 11]` | `trend_direction="up"` (worsening, since lower is better) |
| 3 | `test_valuation_pfcf_trend_computed` | P/FCF series gets real trend | qratios with 4 quarters of `price_to_fcf = [15, 15, 15, 15]` | `trend_direction="stable"`, `change_pct=None` |
| 4 | `test_valuation_trend_single_quarter` | Single quarter returns `stable` | qratios with 1 quarter | `trend_direction="stable"`, `change_pct=None` |
| 5 | `test_valuation_trend_no_quarters` | Empty quarters returns `stable` | qratios with no valuation data (all None) | `trend_direction="stable"`, `change_pct=None` |

### 1.2 buy_quarter_index Correctness

| # | Test | What It Verifies | Input | Expected |
|---|------|-----------------|-------|----------|
| 6 | `test_valuation_buy_idx_none` | `buy_quarter_index=None` when no purchase | `buy_idx=None` | All 3 MetricQuarterSeries have `buy_quarter_index=None` |
| 7 | `test_valuation_buy_idx_zero` | `buy_quarter_index=0` when purchase at first quarter | `buy_idx=0` | All 3 series have `buy_quarter_index=0` |

### 1.3 Tooltip Data (Backend Contract)

| # | Test | What It Verifies | Input | Expected |
|---|------|-----------------|-------|----------|
| 8 | `test_quarter_data_point_has_quarter_end_price` | `quarter_end_price` present in API response | Valid qratios row with quarter_end_price | `QuarterDataPoint.quarter_end_price` is populated |

---

## 2. Frontend Unit Tests (`web/src/__tests__/FundamentalsPanel.test.tsx`)

### 2.1 MetricRangeSlider Independence

| # | Test | What It Verifies | Mock Data | Expected |
|---|------|-----------------|-----------|----------|
| 9 | `renders MetricRangeSlider outside MetricBarChart` | Slider is a sibling of chart, not child | Normal PE data with 4 quarters | Slider has own testid or checking DOM structure shows slider div is before chart |
| 10 | `slider still shows avg + cur after extraction` | Separation didn't break slider rendering | Normal PE: values [10, 15, 12, 18] | `avg 13.8×` and `cur 18.0×` rendered |
| 11 | `slider handles all-N/A quarters after extraction` | Same edge case handling | All quarters `status="not_applicable"` | `not meaningful` text shown |

### 2.2 Tooltip — quarter_end_price

| # | Test | What It Verifies | Mock Data | Expected |
|---|------|-----------------|-----------|----------|
| 12 | `normal bar tooltip shows quarter-end price` | Price rendered in normal bar tooltip | Normal PE with `quarter_end_price=150.50` | `Quarter-end price: $150.50` in tooltip |
| 13 | `not_applicable bar tooltip shows quarter-end price` | Price rendered in N/A bar tooltip | N/A PE with `quarter_end_price=13.12` | `Quarter-end price: $13.12` in tooltip |
| 14 | `tooltip hides quarter-end price when null` | No price section when data missing | `quarter_end_price=null` | No "Quarter-end price" text rendered |

### 2.3 Tooltip — insufficient_data Details

| # | Test | What It Verifies | Mock Data | Expected |
|---|------|-----------------|-----------|----------|
| 15 | `insufficient_data shows quarter count` | "Only X of 4" text visible | 1 non-null + 3 null components | `Only 1 of 4 quarters on record` |
| 16 | `insufficient_data shows missing quarters list` | Missing quarter labels listed | Components: Q2'22=0.16, Q1'22=null, Q4'21=null, Q3'21=null | `Missing: Q1 2022, Q4 2021, Q3 2021` |
| 17 | `insufficient_data with no components shows basic label` | No crash when components absent | `components=[]`, `status="insufficient_data"` | Shows `insufficient data` label, no count text |

### 2.4 Buy Marker Position

| # | Test | What It Verifies | Mock Data | Expected |
|---|------|-----------------|-----------|----------|
| 18 | `buy marker renders below bar (not above)` | `▲` renders below chart baseline | buyQuarterIndex match | Arrow `▲` visible, positioned via `-bottom-3` class |
| 19 | `buy marker does not overlap x-axis labels` | Visual regression test | Standard data | Chart container height unchanged, X-axis labels below arrow |

### 2.5 Scroll Amount

| # | Test | What It Verifies | Mock Data | Expected |
|---|------|-----------------|-----------|----------|
| 20 | `scroll chevron scrolls by 168px` | Scroll amount matches design | 10+ quarters | `scrollBy` called with `left: 156` or `left: -156` |

### 2.6 MetricLabel Separation

| # | Test | What It Verifies | Mock Data | Expected |
|---|------|-----------------|-----------|----------|
| 21 | `metric label rendered at MetricChartSection level` | Label not rendered inside MetricBarChart | Normal data | Label `<span>` with metric name is a sibling of slider, not inside chart div |
| 22 | `no data state still shows metric label` | Label preserved in edge case | All null values | `No data` text shown, metric name visible |

---

## 3. Integration Tests (Backend → DB → API)

### 3.1 API Contract Tests

| # | Test | Method | What It Verifies | Criteria |
|---|------|--------|-----------------|----------|
| 23 | **API returns trend for valuation** | `curl /analysis/{symbol}/fundamentals` then `jq '.sections[] \| select(.section_id=="valuation") \| .metrics[] \| select(.metric_id=="pe_ratio") \| .trend_direction'` | Trend is computed, not "stable" placeholder | Value is `"up"`, `"down"`, or `"stable"` (one of three) |
| 24 | **API returns buy_quarter_index correctly** | Query symbol with AND without portfolio position | `None` when no purchase, proper index when purchased | `buy_quarter_index` is `null` for non-held symbols |
| 25 | **API returns quarter_end_price** | `jq '.sections[] \| select(.section_id=="valuation") \| .metrics[] \| select(.metric_id=="pe_ratio") \| .quarters[0].quarter_end_price'` | quarter_end_price present | Non-null value for populated quarters |
| 26 | **API returns status + components** | Same query for `status` and `components` | Correct status per quarter | `status` is one of `normal`, `not_applicable`, `insufficient_data` |

### 3.2 Full Flow Integration (Backend + DB)

| # | Test | Method | What It Verifies | Criteria |
|---|------|--------|-----------------|----------|
| 27 | **End-to-end: fundamentals fetch for held stock** | Real API call for a portfolio symbol | Full response model matches schema | 5 sections, 15+ metrics, composite score, quarters populated |
| 28 | **End-to-end: valuation section completeness** | Same response, valuation section only | 4 metrics present | `pe_ratio`, `ev_ebitda`, `price_to_fcf`, `price_vs_intrinsic` all present |
| 29 | **End-to-end: PE has correct shape** | `pe_ratio` quarters array | Multi-quarter data matching financial_ratios | Each quarter has: `value`, `status`, `ttm_eps`, `components`, `quarter_end_price` |

---

## 4. Test Data Fixtures

### 4.1 Backend Mock — Valuation Trend

```python
qratios_mock = [
    {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 20.0, "ev_ebitda": 8.0, "price_to_fcf": 15.0},
    {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 18.0, "ev_ebitda": 8.5, "price_to_fcf": 14.0},
    {"fiscal_year": 2024, "fiscal_quarter": 3, "trailing_pe": 15.0, "ev_ebitda": 9.0, "price_to_fcf": 13.0},
    {"fiscal_year": 2024, "fiscal_quarter": 4, "trailing_pe": 12.0, "ev_ebitda": 9.5, "price_to_fcf": 12.0},
]
# Expected: pe_ratio trend = "down" (improving, lower is better: -40%)
# Expected: ev_ebitda trend = "up" (worsening, +18.75%)
# Expected: price_to_fcf trend = "down" (improving, -20%)
```

### 4.2 Frontend Mock — Tooltip quarter_end_price

```typescript
const peQuarter = {
  fiscal_year: 2025, fiscal_quarter: 3, label: "Q3 2025",
  value: 10.25, status: "normal", ttm_eps: 1.16,
  quarter_end_price: 150.50,
  components: [
    { label: "Q3 2025", value: 0.60 },
    { label: "Q2 2025", value: -0.01 },
    { label: "Q1 2025", value: 0.12 },
    { label: "Q4 2024", value: 0.45 },
  ],
};
```

### 4.3 Frontend Mock — insufficient_data with Missing List

```typescript
const insufficientQuarter = {
  fiscal_year: 2022, fiscal_quarter: 2, label: "Q2 2022",
  value: null, status: "insufficient_data", ttm_eps: null,
  quarter_end_price: null,
  components: [
    { label: "Q2 2022", value: 0.16 },
    { label: "Q1 2022", value: null },
    { label: "Q4 2021", value: null },
    { label: "Q3 2021", value: null },
  ],
};
```

---

## 5. Execution

```bash
# Backend tests
cd backend
python -m pytest tests/test_fundamentals_service.py -v

# Frontend tests
cd web
npx vitest run src/__tests__/FundamentalsPanel.test.tsx

# Integration (requires running backend + DB)
curl -s "http://localhost:8001/api/proxy/analysis/AAPL/fundamentals" | python -m json.tool | grep -E '"trend_direction"|"buy_quarter_index"|"quarter_end_price"'
```
