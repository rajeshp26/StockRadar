# Improvements

## 1. Revenue Surprise Data Gap

### Problem

The Narrative section's Revenue Surprise card shows all dashes because `revenue_surprise_percent` is `NULL` for every earnings row in the database across all tested symbols (MSFT, AAPL, T, TSLA, JPM).

### Root Cause

The `earnings` table is populated exclusively through YFinance's `earnings_history` API, which only returns **4 columns**:

| Column | Populated? |
|--------|-----------|
| `epsActual` | Yes |
| `epsEstimate` | Yes |
| `epsDifference` | Yes |
| `surprisePercent` | Yes |

**Revenue data is not provided by this API.** The fields `revenue_reported`, `revenue_estimate`, `revenue_surprise_amount`, and `revenue_surprise_percent` are hardcoded to `None` in `YFinanceProvider.get_earnings_data()`.

### Provider Test Results (June 2026)

| Provider | Method | Revenue Data? | Detail |
|----------|--------|---------------|--------|
| `YFinanceProvider` | `get_earnings_data()` | ❌ Always None | 5 symbols tested, all 4 revenue fields None on every row |
| yfinance Ticker raw | `.earnings_history` | ❌ Not present | DataFrame columns: `epsActual`, `epsEstimate`, `epsDifference`, `surprisePercent` only |
| yfinance Ticker raw | `.quarterly_financials` | ⚠️ Actual only | Has "Total Revenue" (e.g., MSFT $82.9B) but no estimates — can't compute surprise |
| `StockdexMacrotrendsProvider` | No earnings method | ❌ | IS/BS/CF only |
| `EdgarToolsProvider` | No earnings method | ❌ | IS/BS/CF only |
| `DefeatBetaProvider` | `fetch_revenue_forecast()` | ❌ Returned `[]` | Forward-looking forecast API returned empty |
| `DefeatBetaProvider` | `get_all_financials_optimized()` | ❌ Always None | Falls through to YFinance, same result |

### Data Pipeline

```
scheduler_worker.py
  → EarningsRefreshScheduler (every 2h)
    → DefeatBetaProvider.get_all_financials_optimized()
      → DefeatBeta Ticker API removed Feb 2026 — falls through
      → YFinanceProvider.get_earnings_data()
        → yfinance Ticker.earnings_history  ← NO REVENUE DATA
        → yfinance Ticker.quarterly_financials  ← HAS REVENUE (actual only)
      → YFinanceProvider.get_quarterly_income_statement_df()
        → yfinance Ticker.quarterly_financials  ← HAS REVENUE (actual only)
    → SupabaseFinancialRepository.upsert_earnings()
      → earnings table: revenue fields always NULL
```

### DB Schema

The `EarningsRow` Pydantic model (`domain/model_types.py:195-225`) already defines all revenue fields:

```python
revenue_reported: Optional[Decimal] = None
revenue_estimate: Optional[Decimal] = None
revenue_surprise_amount: Optional[Decimal] = None
revenue_surprise_percent: Optional[Decimal] = None
```

The consumer code (`fundamentals_service.py`, `fundamentals_repository.py`) also already handles these fields — they just never receive data.

### Options to Fix

#### Option A: Compute from quarterly_financials (actual only)
- **What**: Read "Total Revenue" from yfinance `quarterly_financials` as `revenue_reported`
- **Problem**: No `revenue_estimate` available → can't compute surprise %
- **Effort**: Low
- **Outcome**: Revenue Surprise card would still show no data

#### Option B: Add a paid financial data API
- **What**: Integrate a provider that includes revenue estimates (e.g., Financial Modeling Prep, Intrinio, Alpha Vantage)
- **Examples**:
  - **Financial Modeling Prep**: `earnings_surprises/{symbol}` returns both EPS and revenue surprises
  - **Intrinio**: `historical_data` endpoint with `revenue_estimate` and `actual_revenue` fields
  - **Alpha Vantage**: `EARNINGS` function returns `reportedEPS`, `estimatedEPS` for both EPS and revenue
- **Effort**: Medium (new provider class, API key, error handling)
- **Outcome**: Revenue Surprise fully populated

#### Option C: Web scrape revenue estimates
- **What**: Scrape revenue estimates from sites like Yahoo Finance or MarketBeat
- **Effort**: High (fragile, maintenance burden)
- **Outcome**: Unreliable long-term

#### Option D: Derive from income statement + SEC filings
- **What**: Use EDGAR/Stockdex income statement data for actual revenue, cross-reference with analyst estimate data from an alternative source
- **Effort**: High
- **Outcome**: Complex, two-source reconciliation needed

### Recommendation

**Option B** — integrate a data provider that natively returns revenue estimates alongside earnings. Financial Modeling Prep's `earnings_surprises` endpoint is the simplest drop-in since it mirrors the yfinance data structure with added revenue fields.

---

## 2. Gauge Component Unification

### Problem

Two different gauge implementations produce inconsistent visuals across sections:

| Section | Component | Gauge Type | Label Style | Value Position |
|---------|-----------|------------|-------------|----------------|
| Financial Health | `MoatGaugeCard` | `HealthArc` (180° semicircle) | `text-[13px] text-white/80 font-bold uppercase` | Below arc as HTML `<div>` |
| Valuation | `MetricCard` → `ValuationGauge` | `GaugeSvg` (arc with zone labels) | Was `text-[10px] text-[#71767b] font-semibold`, now unified to match above | Was inside SVG, now below as HTML `<div>` |
| Slider mode | `SliderTrack` | Horizontal slider bar | Varies | Inline on slider |

Zone labeling also differs:
- `HealthArc`: zone labels **inside** the arc (red/amber/green text on the arc background)
- `GaugeSvg`: zone labels **inside** the arc ("Undervalued" / "Fair" / "Overvalued")

### Current State (after partial fix)

The label font and value position have been unified:
- Both `MoatGaugeCard` and `MetricCard` now use `text-[13px] text-white/80 font-bold uppercase tracking-wider` for labels
- Both now show the current value as a large HTML element below the gauge
- `GaugeSvg` no longer renders the value and label inside the SVG coordinate system

### Remaining Inconsistencies

| Aspect | HealthArc | GaugeSvg | SliderTrack |
|--------|-----------|----------|-------------|
| Zone labels inside arc | "Strong" / "Fair" / "Weak" (colored per zone) | "Undervalued" / "Fair" / "Overvalued" (colored per zone) | N/A |
| Needle | White dot + line from center to arc | White dot + line from center to arc | N/A |
| Arc background | Dark track (#2f3336) | Light track (#B4B2A9) | N/A |
| Tick marks + scale values | 4 ticks with min/bandLow/bandHigh/max labels | 4 ticks with min/avg/threshold/max labels | N/A |
| Gauge width | Fixed 220px | Fixed 270px (250px compact) | Full width |
| Health badge (label card) | Colored pill next to title ("Strong") | Valuation pill below gauge ("Undervalued") | N/A |
| Sparkline | `MiniSparkline` below value | `MiniSparkline` below percentile | N/A |
| History table | `MoatHistoryTable` below sparkline | `HistoryTable` below sparkline | N/A |

### Goals for Full Refactor

1. **Single `GaugeCard` wrapper component** — shared card shell (header, gauge slot, value, footer) used by all sections
2. **Pluggable gauge types** — `HealthArc`, `GaugeSvg`, `SliderTrack` receive unified props and render inside the card
3. **Consistent zone labels** — same font, position, and color scheme across all arc gauges
4. **Consistent arc styling** — same track color, arc width, tick marks
5. **Consistent dimensions** — same width/height for all arc gauges
6. **Reusable header** — label font, badge position, badge style unified

### Proposed Architecture

```
GaugeCard (shared wrapper)
├── Header
│   ├── Label (text-[13px] font-bold text-white/80 uppercase)
│   └── Badge slot (health label / valuation label / benchmark toggle)
├── Gauge slot
│   ├── GaugeSvg (valuation metrics — EV/EBITDA, P/FCF, etc.)
│   ├── HealthArc (financial health — Piotroski, Altman, Int. Cov.)
│   └── SliderTrack (narrative, quality, growth — sparkline mode)
├── Value display (large text below gauge)
├── Footer
│   ├── MiniSparkline (quarterly trend)
│   └── History table (quarterly/yearly data grid)
└── Optional extras
    ├── StatPill row (Min / Avg / Max / Current)
    ├── Percentile badge
    └── Benchmark toggle
```

### Component Interface

```typescript
interface GaugeCardProps {
  // Shared
  label: string;
  metricId: string;
  unit: string;
  quarters: QuarterDataPoint[];
  config: GaugeConfig;

  // Gauge type selection (inferred from config.display_mode)
  // "gauge" | "compact_gauge" → GaugeSvg or HealthArc
  // "slider" → SliderTrack

  // Variant (determines which arc gauge + badge style)
  variant: "valuation" | "health";

  // Valuation-specific
  benchmark?: "history" | "sector";
}
```

### Migration Path

1. **Create `GaugeCard` component** in a new file `gauge-card.tsx` with the shared wrapper
2. **Refactor `HealthArc`** → accept unified prop interface, consistent dimensions and styling
3. **Refactor `GaugeSvg`** → accept unified prop interface, consistent dimensions and styling
4. **Update `MoatGaugeCard`** → delegate to `GaugeCard` with `variant="health"`
5. **Update `MetricCard`** → delegate to `GaugeCard` with `variant="valuation"`
6. **Update `MetricChartSection`** (slider mode) → delegate to `GaugeCard` with `variant="slider"`

### Effort Estimate

| Step | Complexity | Files touched |
|------|-----------|---------------|
| Create `GaugeCard` wrapper | Low | 1 new file |
| Unify arc dimensions + styling | Medium | `valuation-gauge.tsx` |
| Refactor `HealthArc` props | Low | `valuation-gauge.tsx` |
| Refactor `GaugeSvg` props | Low | `valuation-gauge.tsx` |
| Update `MoatGaugeCard` → use `GaugeCard` | Medium | `valuation-gauge.tsx`, `fundamentals-panel.tsx` |
| Update `MetricCard` → use `GaugeCard` | Medium | `valuation-gauge.tsx`, `fundamentals-panel.tsx` |
| Update slider usage | Low | `fundamentals-panel.tsx` |
| Testing + visual verification | Medium | All sections |
| **Total** | **Medium (4-6h)** | **~4 files** |

### Risks

- **Layout regression**: Changing gauge widths from 220px/270px to a single size could break card wrapping in the flex grid
- **HealthArc zone label positions**: Moving zone labels from inside the arc to outside (to match GaugeSvg) would change the look significantly — may not be desired
- **Slider mode**: `SliderTrack` is fundamentally different from arc gauges — the `GaugeCard` wrapper needs to accommodate both without awkward conditionals
