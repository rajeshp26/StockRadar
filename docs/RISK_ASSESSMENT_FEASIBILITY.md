# Risk Assessment Tab — Feasibility Analysis

> **Date:** 2026-05-25
> **Scope:** Full-stack feasibility of implementing a "Risk Assessment" tab on the Stock Analysis page (`/analysis/[symbol]`)
> **Methodology:** Trace each required metric from the professional downside framework back to existing database columns, API endpoints, services, and types

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Walkthrough](#2-architecture-walkthrough)
3. [Layer-by-Layer Data Availability](#3-layer-by-layer-data-availability)
4. [Gap Solutions — How to Fill Each Gap](#4-gap-solutions--how-to-fill-each-gap)
5. [Framework Component Analysis](#5-framework-component-analysis)
6. [Implementation Effort Estimate](#6-implementation-effort-estimate)
7. [Complete Gap Inventory](#7-complete-gap-inventory)
8. [Recommended Phasing](#8-recommended-phasing)

---

## 1. Executive Summary

**Verdict: FEASIBLE** — ~90% of required data is already available in the database or computable from existing tables (the previously identified moat gap is now fully implemented as a dedicated service — see `docs/MOAT_ANALYSIS_FEASIBILITY.md`).

The five-layer professional downside framework can be implemented as a new tab with:
- **Backend:** A new `RiskAssessmentService` + endpoint under `GET /analysis/{symbol}/risk-assessment`
- **Frontend:** A new `RiskPanel` component + hook + service functions following the existing pattern
- **Estimate:** ~3 weeks of effort (phased approach recommended)
- **Primary gaps** and how they'll be filled:
  - **Debt/EBITDA** → Add to `derived_financial_metrics_job.py` + migration to add column to `financial_ratios`
  - **Historical P/E percentile** → On-demand computation in `RiskAssessmentService` (query `company_summary` time series)
   - **Moat score** → Fully implemented via `MoatAnalysisService` (Stage 1 quant scoring: ROIC vs WACC spread, ROIC 5yr avg, margin durability, ROIC stability, capital efficiency; Stage 2 EDGAR keyword analysis; AI narrative generation) — see `docs/MOAT_ANALYSIS_FEASIBILITY.md` and `backend/application/services/moat_analysis_service.py`
  - **Permanent impairment assessment** → AI-generated via existing `ai_service.py`

### Data Availability by Layer

| Layer | Availability | Direct DB Columns | Needs Computation |
|---|---|---|---|
| 1. Business Fragility | 85% | sector, industry, margins, moat_analysis table | Revenue recurrence classification |
| 2. Balance Sheet Risk | 90% | interest_coverage, debt_to_equity, current_ratio | Debt/EBITDA (after adding to derived_metrics_job) |
| 3. Valuation Compression | 85% | trailing_pe, peg_ratio, enterprise_to_ebitda | Historical percentile ranking (on-demand) |
| 4. Earnings/Cash Flow Stress | 100% | All in income_statements + cash_flow_statements | CAGR computations exist |
| 5. Historical Drawdown | 95% | price_history | _max_drawdown() exists in StockIndexComparisonService |

---

## 2. Architecture Walkthrough

### 2.1 Existing Pattern (to replicate)

Every analysis tab follows a 4-layer architecture:

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (Next.js / TypeScript)                             │
│                                                             │
│  page.tsx                                                   │
│    └─ TOP_TABS array + conditional rendering                │
│         └─ RiskPanel (new) ← { symbol }                    │
│              └─ useRiskAssessment (new hook)                │
│                   └─ fetchRiskAssessmentCached (new)        │
│                        └─ GET /api/proxy/analysis/{symbol}/risk-assessment
│                                                             │
│  React Query Cache (QK.riskAssessment symbol)               │
│    - Prefetched on page mount via prefetchAllValuations()   │
└──────────────────────────────┬──────────────────────────────┘
                               │ same-origin proxy
                               │ (web/src/app/api/proxy/[...path]/route.ts)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (FastAPI / Python)                                  │
│                                                             │
│  api/analysis.py                                            │
│    └─ GET /analysis/{symbol}/risk-assessment                │
│         └─ RiskAssessmentService                            │
│              ├─ BusinessFragilityAnalyzer (new)             │
│              ├─ BalanceSheetRiskAnalyzer (new)              │
│              ├─ ValuationRiskAnalyzer (new)                 │
│              ├─ EarningsStressAnalyzer (new)                │
│              ├─ DrawdownAnalyzer (reuses existing)          │
│              └─ ScenarioModeler (new)                       │
│                   │                                         │
│                   └─ ValuationRepository (existing)         │
│                        └─ supabase queries                  │
│                             └─ PostgreSQL (Supabase)        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Key Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| `backend/api/analysis.py` | Modify | Add `GET /{symbol}/risk-assessment` endpoint |
| `backend/application/services/risk_assessment_service.py` | **Create** | Orchestrator: fetches all data, computes layers, returns MEL |
| `backend/domain/models/risk_assessment.py` | **Create** | Pydantic response models (Pydantic v2) |
| `backend/infrastructure/repositories/analysis_repository.py` | Modify | Add risk-specific data queries |
| `backend/application/jobs/derived_financial_metrics_job.py` | Modify | Add `debt_to_ebitda`, `net_debt_to_ebitda` computation |
| `backend/scripts/migrate_add_risk_ratios.sql` | **Create** | ALTER TABLE to add new columns to `financial_ratios` |
| `web/src/features/analysis/types/analysis.types.ts` | Modify | Add `RiskAssessmentResponse` + sub-types |
| `web/src/features/analysis/services/analysis.service.ts` | Modify | Add `fetchRiskAssessmentCached()` + `fetchRiskAssessment()` |
| `web/src/features/analysis/hooks/useRiskAssessment.ts` | **Create** | TanStack Query hook |
| `web/src/features/analysis/components/risk-panel.tsx` | **Create** | UI component |
| `web/src/app/(authenticated)/analysis/[symbol]/page.tsx` | Modify | Add `risk` to `TOP_TABS`, wire rendering |
| `web/src/lib/query-keys.ts` | Modify | Add `QK.riskAssessment(symbol)` |
| `web/src/features/analysis/utils/prefetch-valuations.ts` | Modify | Add risk assessment to prefetch list |

---

## 3. Layer-by-Layer Data Availability

### 3.1 Business Fragility (Layer 1)

| Metric | Source | Status | Details |
|---|---|---|---|
| Sector / Industry classification | `companies.sector`, `companies.industry` | **Available** | Direct column |
| Competitive moat assessment | `moat_analysis` table (cached) + `moat_analysis_service.py` | **Available** | Full implementation: Stage 1 quant scoring (ROIC vs WACC spread, ROIC 5yr avg, margin durability, ROIC stability, capital efficiency), Stage 2 EDGAR keyword evidence, AI narrative. See `backend/application/services/moat_analysis_service.py` |
| Revenue recurrence classification | `companies.sector` heuristic | **Computable (see §4.4)** | SaaS, Utilities → high recurrence; Cyclicals → low |
| Pricing power proxy | `financial_ratios.gross_margin` trend | **Computable** | Stable/expanding margins → strong pricing power |
| Industry cyclicality | `companies.sector` heuristic | **Computable (see §4.5)** | Map sector → cyclicality bucket |
| Customer switching cost proxy | — | **Not computed (low impact)** | Hard to measure quantitatively; proxy via gross margin stability |

**Partial score with existing data** using ROIC consistency, margin stability, and sector-based classification.

**Existing reusable code:** `moat_analysis_service.py` computes the full Stage 1 quant score (ROIC vs WACC spread, ROIC 5yr avg, margin durability, ROIC stability, capital efficiency), `moat_keyword_analyzer.py` provides Stage 2 EDGAR keyword evidence, and `moat_wacc_service.py` computes WACC via CAPM. Also `rule1_suitability.py` computes revenue CAGR, EPS volatility, ROIC average, FCF conversion — all relevant as supplementary inputs.

---

### 3.2 Balance Sheet Risk (Layer 2)

| Metric | Source | Status | Details |
|---|---|---|---|
| Total Debt | `balance_sheets.total_debt` | **Available** | Direct column |
| EBITDA | `income_statements.ebitda` | **Available** | Direct column |
| **Debt / EBITDA** | `financial_ratios.debt_to_ebitda` | ⚠️ **Gap — see §4.1** | Will add to `derived_financial_metrics_job.py` + migration |
| **Net Debt / EBITDA** | `financial_ratios.net_debt_to_ebitda` | ⚠️ **Gap — see §4.1** | Will add alongside debt_to_ebitda |
| Interest Coverage | `financial_ratios.interest_coverage` | **Available** | Pre-computed in job |
| Cash & Equivalents | `balance_sheets.cash_and_cash_equivalents` | **Available** | Direct column |
| Current Ratio | `financial_ratios.current_ratio` | **Available** | Pre-computed |
| Quick Ratio | `financial_ratios.quick_ratio` | **Available** | Pre-computed |
| FCF | `cash_flow_statements.free_cash_flow` or computed | **Available** | `_fcf()` helper in job |
| FCF Conversion | `financial_ratios.fcf_conversion` | **Available** | Pre-computed |
| Debt to Equity | `financial_ratios.debt_to_equity` | **Available** | Pre-computed |
| FCF Stability (multi-year) | computed from `free_cash_flow` history | **Computable** | Positive-years check (done in DCF suitability) |

**Risk thresholds already implemented** in `dcf_suitability.py`:
```python
# Debt/EBITDA: < 3x pass, 3-5x caution, > 5x fail
# Interest Coverage: > 4x pass, 2-4x caution, < 2x fail
```

---

### 3.3 Valuation Compression Risk (Layer 3)

| Metric | Source | Status | Details |
|---|---|---|---|
| Current P/E | `company_summary.trailing_pe` | **Available** | Direct column |
| Forward P/E | `company_summary.forward_pe` | **Available** | Direct column |
| EV/EBITDA | `company_summary.enterprise_to_ebitda` | **Available** | Direct column |
| PEG Ratio | `company_summary.peg_ratio` | **Available** | Direct column |
| Enterprise Value | `company_summary.enterprise_value` | **Available** | Direct column |
| Current Price | Live fetch / `price_history` latest | **Available** | via `get_current_market_price()` |
| Market Cap | `company_summary.market_cap` | **Available** | Direct column |
| **Historical P/E percentile** | `company_summary` time series | ⚠️ **Gap — see §4.2** | On-demand computation |
| **Historical EV/EBITDA percentile** | `company_summary` time series | ⚠️ **Gap — see §4.2** | Same pattern as P/E |

---

### 3.4 Earnings / Cash Flow Stress (Layer 4)

| Metric | Source | Status | Details |
|---|---|---|---|
| EPS CAGR (3y, 5y) | `income_statements` | **Available** | Already in `stock_index_comparison_service` |
| Revenue CAGR (3y, 5y) | `income_statements` | **Available** | Same |
| Net Margin trend | `financial_ratios.net_margin` | **Available** | Pre-computed |
| Operating Margin trend | `financial_ratios.operating_margin` | **Available** | Pre-computed |
| FCF Margin trend | `financial_ratios.fcf_margin` | **Available** | Pre-computed |
| EPS volatility / drawdown | `income_statements` | **Available** | Used in `rule1_suitability.py` |
| Revenue vs EPS alignment | computed | **Available** | Used in `rule1_suitability.py` |
| Revenue forecast growth | `revenue_forecast.estimate_revenue_growth` | **Available** | Analyst consensus |
| EPS forecast growth | `earnings_forecast.estimate_eps_growth` | **Available** | Analyst consensus |
| Earnings surprise trend | `earnings.eps_surprise_percent` | **Available** | Historical surprise data |

**100% available** — all metrics are either pre-computed in `financial_ratios` or computable from existing repository methods.

---

### 3.5 Historical Drawdown (Layer 5)

| Metric | Source | Status | Details |
|---|---|---|---|
| Max Drawdown (1y, 3y, 5y) | `price_history` | **Available** | `_max_drawdown()` in `stock_index_comparison_service.py:396` |
| Beta (5y) | `company_summary.beta` | **Available** | Direct column |
| Drawdown during crisis periods | `price_history` | **Computable** | Date-range filtered drawdown |
| Peak-to-trough recovery time | `price_history` | **Computable** | New logic needed |
| Current drawdown from peak | `price_history` + current price | **Computable** | Latest close vs historical peak |
| Drawdown series for chart | `price_history` | **Available** | `_drawdown_series()` already implemented |
| Number of down years | `income_statements` / `price_history` | **Computable** | Compare YoY prices |

**95% available** — drawdown calculation and beta are directly reusable. Only recovery time logic needs to be written.

---

## 4. Gap Solutions — How to Fill Each Gap

### 4.1 G1: Debt/EBITDA and Net Debt/EBITDA

**Problem:** `financial_ratios` table has `debt_to_equity`, `debt_to_assets`, `interest_coverage`, but no `debt_to_ebitda` or `net_debt_to_ebitda`.

**Solution:** Add both as pre-computed ratios to the `derived_financial_metrics_job.py` and persist in `financial_ratios`.

#### Step 1: SQL Migration — Add columns to `financial_ratios`

**File:** `backend/scripts/migrate_add_risk_ratios.sql`

```sql
-- Add risk-specific ratios to financial_ratios for the Risk Assessment tab
ALTER TABLE public.financial_ratios
  ADD COLUMN IF NOT EXISTS debt_to_ebitda numeric(15, 4) NULL,
  ADD COLUMN IF NOT EXISTS net_debt_to_ebitda numeric(15, 4) NULL;
```

#### Step 2: Add computation to `derived_financial_metrics_job.py`

In the main loop body (after existing ratio computations, around line 303, after `interest_coverage`), insert:

```python
# Debt / EBITDA
debt_to_ebitda = None
if total_debt is not None and ebitda is not None and ebitda != 0:
    debt_to_ebitda = total_debt / abs(ebitda)

# Net Debt / EBITDA (Net Debt = Total Debt - Cash)
net_debt = (total_debt - cash) if (total_debt is not None and cash is not None) else None
net_debt_to_ebitda = None
if net_debt is not None and ebitda is not None and ebitda != 0:
    net_debt_to_ebitda = net_debt / abs(ebitda)
```

Then add to the `out.append()` dict (around line 400, after `interest_coverage`):

```python
"debt_to_ebitda":      debt_to_ebitda,
"net_debt_to_ebitda":  net_debt_to_ebitda,
```

#### Step 3: Update source payload version tag

Add the two new fields to the `source_payload` "bs" dict (around line 358):

```python
"bs": {k: bsr.get(k) for k in [
    ..., "total_debt", "long_term_debt", "shareholders_equity",
    "cash_and_cash_equivalents",  # already included — used for net debt
    ...
]},
```

Also add `ebitda` verification to the "is" dict if not already there — it's already present.

#### Step 4: Update repository queries

Update `get_derived_metrics_latest()` in `valuation_repository.py:1695` to include the new columns:

```python
debt_to_ebitda, net_debt_to_ebitda,  # add alongside existing debt_to_equity, etc.
```

#### Verification

| Metric | Formula | Risk Thresholds |
|---|---|---|
| `debt_to_ebitda` | Total Debt / EBITDA | <1 very safe, 1-2 safe, 2-4 moderate, 4-6 dangerous, >6 severe |
| `net_debt_to_ebitda` | (Total Debt - Cash) / EBITDA | Same thresholds, more conservative |

---

### 4.2 G2: Historical P/E and EV/EBITDA Percentile

**Problem:** Need to know where current valuation stands vs. historical range. Not pre-computed.

**Solution:** Compute on-demand in `RiskAssessmentService`. Do NOT store in database.

**Rationale for on-demand vs stored approach:**

| Approach | Pros | Cons |
|---|---|---|
| **On-demand** (recommended) | Always current, flexible lookback (3y/5y/10y), no stale data | Slightly slower (~50ms extra query) |
| **Pre-computed column** in company_summary | Fast retrieval | Stale until next snapshot refresh, fixed lookback window |
| **Separate percentiles table** | Dedicated, can track over time | More complexity, needs scheduler job, overkill for MVP |

On-demand is ~20 lines of code and avoids schema changes for a metric that's computed once per page load.

#### Implementation in `RiskAssessmentService`:

```python
async def _compute_valuation_percentiles(
    self, company_id: int, years: int = 5
) -> Dict[str, Any]:
    """
    Rank current valuation metrics vs historical distribution.
    Returns percentile (0-100) where 100 = most expensive ever.
    """
    cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
    resp = supabase.table("company_summary") \
        .select("snapshot_date, trailing_pe, enterprise_to_ebitda, peg_ratio") \
        .eq("company_id", company_id) \
        .not_.is_("trailing_pe", "null") \
        .gte("snapshot_date", cutoff) \
        .order("snapshot_date", desc=False) \
        .execute()
    
    rows = resp.data or []
    if not rows:
        return None
    
    current = rows[-1]  # most recent snapshot
    pe_values = sorted([float(r["trailing_pe"]) for r in rows if r.get("trailing_pe")])
    ev_ebitda_values = sorted([
        float(r["enterprise_to_ebitda"]) for r in rows 
        if r.get("enterprise_to_ebitda")
    ])
    
    current_pe = float(current["trailing_pe"])
    
    def percentile(sorted_vals, val):
        if not sorted_vals or len(sorted_vals) < 2:
            return 50  # neutral default
        count = sum(1 for v in sorted_vals if v <= val)
        return round(count / len(sorted_vals) * 100)
    
    return {
        "pe_percentile": percentile(pe_values, current_pe),
        "pe_current": current_pe,
        "pe_5y_min": pe_values[0] if pe_values else None,
        "pe_5y_max": pe_values[-1] if pe_values else None,
        "pe_5y_median": pe_values[len(pe_values)//2] if pe_values else None,
        "ev_ebitda_percentile": percentile(ev_ebitda_values, ...),
        # similar for EV/EBITDA
    }
```

#### Performance consideration:

`company_summary` has an index `idx_company_summary_company_date` on `(company_id, snapshot_date desc)`. The query filters by `company_id` and `snapshot_date` — both covered by the index. For 5 years of daily data (~1826 rows), this query returns in <10ms.

#### Alternative (for future optimization):

If the on-demand approach proves too slow, create a materialized view:

```sql
CREATE MATERIALIZED VIEW public.valuation_percentiles AS
SELECT 
    company_id,
    PERCENT_RANK() OVER (PARTITION BY company_id ORDER BY trailing_pe) AS pe_percentile,
    snapshot_date,
    trailing_pe
FROM public.company_summary
WHERE trailing_pe IS NOT NULL;

REFRESH MATERIALIZED VIEW public.valuation_percentiles;  -- run daily
```

This is **NOT recommended for MVP** — the on-demand query is fast enough.

---

### 4.3 G3: Moat Score — ✅ IMPLEMENTED

**Status:** The moat analysis system is **fully implemented** and no longer a gap. See `docs/MOAT_ANALYSIS_FEASIBILITY.md` for the complete feasibility study and `backend/application/services/moat_analysis_service.py` for the full implementation.

#### What exists:

| Component | File | Details |
|---|---|---|
| **WACC computation** | `moat_wacc_service.py` | CAPM-based cost of equity (risk-free rate 4.5%, ERP 5.5%, beta from DB), market-cap weighted debt/equity structure, default cost of debt 5%, tax rate 21% |
| **Stage 1 Quant Scoring** | `moat_analysis_service.py:384` | 5 sub-scores: ROIC vs WACC spread (0–35 pts), ROIC 5yr avg (0–20), margin durability (0–20), ROIC stability (0–15), capital efficiency (0–10). Composite mapped to 0–100 score. Categories: Wide (≥70), Narrow (≥40), None (≥10), Unknown |
| **Sector adjustments** | `moat_analysis_service.py:31` | 12-sector adjustment map (e.g., Utilities -0.08, Technology 0.0, Consumer Defensive +0.03) |
| **Diagnostic flags** | `moat_analysis_service.py:530` | 5 flag types: MOAT-ROIC-BELOW-WACC, MOAT-ROIC-EXTREME, MOAT-ROIC-HIGH-VOLATILITY, MOAT-LOW-ASSET-TURNOVER, MOAT-SECTOR-REGULATED |
| **EDGAR Keyword Analyzer (Stage 2)** | `moat_keyword_analyzer.py` | Regex scanner with 5 moat source groups (intangible_assets, switching_costs, network_effects, cost_advantages, scale_efficiencies), deduplication, group scoring |
| **AI narrative generation** | `moat_analysis_service.py:708` | Prompt with quant summary + evidence → OpenRouter GPT-4o-mini → structured assessment |
| **Database schema** | `migrate_moat_analysis.sql` | 3 tables: `moat_analysis` (cached scores, 24h TTL), `moat_keyword_evidence` (EDGAR snippets), `moat_ai_narratives` (cached AI output) |
| **API endpoints** | `analysis.py:247` | `GET /{symbol}/moat`, `GET /{symbol}/moat/evidence`, `GET /{symbol}/moat/ai`, `POST /{symbol}/moat/ai` |
| **Frontend panel** | `moat-panel.tsx` | Full UI: core metrics grid, margin durability, stability, industry context, EDGAR evidence section, AI narrative section, diagnostics toggle |
| **Tests** | `backend/tests/test_moat_*.py` (8 files) | Unit tests for service, API, keyword analyzer, EDGAR, WACC, repository |
| **Frontend tests** | `web/src/__tests__/MoatPanel.test.tsx` | 15 test cases covering loading, error, data display, evidence, AI narrative, diagnostics, sector exclusion |

#### How the Risk Assessment tab should consume moat data:

Rather than re-computing the moat score internally, the `RiskAssessmentService` should call the existing `MoatAnalysisService.get_moat_analysis()` to retrieve the cached (or compute fresh) moat score, category, and diagnostic flags. The key fields to consume:

```python
# From moat_analysis table / MoatResponse:
moat_score         # 0-100 composite
moat_category      # "Wide" | "Narrow" | "None" | "Unknown"
roic_minus_wacc    # Economic spread
moat_category weight for Risk Assessment composite:
# Wide = 10pts, Narrow = 7pts, None = 3pts, Unknown = 0pts
```

This avoids duplicating computation and keeps moat as a single source of truth shared across tabs.

---

### 4.4 G4: Revenue Recurrence Classification

**Problem:** Need to classify whether revenue is recurring vs project-based to assess business stability.

**Solution:** Sector-based heuristic with margin cross-check.

| Sector | Recurrence Classification | Confidence |
|---|---|---|
| Software (SaaS) | High | High |
| Internet Services | High | High |
| Healthcare | Medium-High | Medium |
| Insurance | High (premiums) | High |
| Utilities | High | High |
| Consumer Staples | Medium | Medium |
| Banks | Medium | Low |
| Manufacturing | Low | High |
| Energy | Low | High |
| Cyclicals (Auto, Airlines) | Low | High |

**Implementation:**
```python
SECTOR_RECURRENCE_MAP = {
    "Technology": 0.8,
    "Healthcare": 0.6,
    "Financial Services": 0.5,
    "Consumer Defensive": 0.6,
    "Utilities": 0.9,
    "Communication Services": 0.5,
    "Energy": 0.1,
    "Basic Materials": 0.1,
    "Industrials": 0.2,
    "Consumer Cyclical": 0.2,
    "Real Estate": 0.7 (rents),
}

def classify_recurrence(sector: str) -> Dict:
    score = SECTOR_RECURRENCE_MAP.get(sector, 0.3)
    return {"score": score, "classification": "High" if score >= 0.7 else "Medium" if score >= 0.4 else "Low"}
```

---

### 4.5 G5: Crisis Period Drawdown Labels

**Problem:** Cannot auto-label "COVID drawdown was -38%".

**Solution:** Define named crisis date ranges, compute drawdown within each window.

```python
CRISIS_PERIODS = [
    {"name": "COVID Crash (2020)", "start": "2020-02-19", "end": "2020-03-23"},
    {"name": "Rate Hike Selloff (2022)", "start": "2022-01-03", "end": "2022-10-12"},
    {"name": "2008 Financial Crisis", "start": "2007-10-09", "end": "2009-03-09"},
]

async def _compute_crisis_drawdowns(
    self, company_id: int
) -> List[Dict]:
    results = []
    for crisis in CRISIS_PERIODS:
        prices = await self.repo.get_price_history_range(
            company_id, 
            date.fromisoformat(crisis["start"]),
            date.fromisoformat(crisis["end"])
        )
        if prices and len(prices) >= 2:
            closes = [float(p["close_price"]) for p in prices]
            dd = self._max_drawdown(closes)
            results.append({
                "crisis": crisis["name"],
                "max_drawdown": round(dd, 4),
                "start_value": closes[0],
                "end_value": closes[-1],
            })
    return results
```

Reuses `_max_drawdown()` from `stock_index_comparison_service.py:396`.

---

### 4.6 G6: Management Capital Allocation Score

**Problem:** 10% weighting in the composite framework. No pre-computed score.

**Solution:** Proxy using share buybacks, debt reduction, and ROIC trend.

```python
def _compute_capital_allocation_score(
    share_repurchases_history: List[float],  # from cash_flow_statements
    debt_to_equity_history: List[float],      # from financial_ratios
    roic_history: List[float]                  # from financial_ratios
) -> float:
    score_components = []
    
    # Share buyback consistency (buybacks → shareholder-friendly)
    if share_repurchases_history:
        buyback_years = sum(1 for v in share_repurchases_history if v and v > 0)
        buyback_ratio = buyback_years / len(share_repurchases_history)
        score_components.append(buyback_ratio * 10 * 0.4)
    
    # Debt reduction trend (lower leverage → prudent management)
    if debt_to_equity_history and len(debt_to_equity_history) >= 2:
        dte_trend = debt_to_equity_history[-1] - debt_to_equity_history[0]
        if dte_trend < 0:  # decreasing leverage
            score_components.append(min(10, abs(dte_trend) * 5) * 0.3)
    
    # ROIC trend (improving → good capital allocation)
    if roic_history and len(roic_history) >= 2:
        roic_slope = roic_history[-1] - roic_history[0]
        if roic_slope > 0.01:  # improving >1%
            score_components.append(min(10, roic_slope * 100) * 0.3)
    
    return round(sum(score_components), 1) if score_components else None
```

**Data sources:**
- `share_repurchases` from `cash_flow_statements`
- `debt_to_equity` from `financial_ratios` (pre-computed)
- `roic` from `financial_ratios` (pre-computed), already has `get_roic_history()` in repo

---

### 4.7 G7: Regulatory / Disruption Risk Score

**Problem:** 5% weight in composite. Requires qualitative assessment.

**Solution:** Sector-based classification with AI summary augmentation.

```python
SECTOR_REGULATORY_RISK = {
    "Healthcare": 0.8,       # FDA, CMS, drug pricing
    "Financial Services": 0.7,  # SEC, Fed, Basel
    "Utilities": 0.6,        # EPA, state regulators
    "Technology": 0.4,       # antitrust, privacy (increasing)
    "Energy": 0.5,           # EPA, DOE
    "Consumer Defensive": 0.3,
    "Communication Services": 0.4,
    "Real Estate": 0.3,
    "Industrials": 0.3,
    "Basic Materials": 0.3,
    "Consumer Cyclical": 0.2,
}

SECTOR_DISRUPTION_RISK = {
    "Technology": 0.7,       # rapid innovation cycles
    "Consumer Cyclical": 0.5,
    "Energy": 0.5,           # renewable disruption
    "Healthcare": 0.4,
    "Communication Services": 0.5,
    "Basic Materials": 0.2,
    "Utilities": 0.1,
    "Consumer Defensive": 0.2,
    "Real Estate": 0.2,
    "Financial Services": 0.3,
    "Industrials": 0.3,
}
```

---

### 4.8 G8: Permanent Impairment Risk (AI Summary)

**Problem:** The most subjective assessment — "can this business permanently lose capital?"

**Solution:** Use the existing `ai_service.py` infrastructure to generate a qualitative summary, similar to how `suitabilitySummary` works for valuation methods.

The AI prompt would receive:
- Balance sheet metrics (Debt/EBITDA, Interest Coverage)
- Earnings stability (years of positive EPS, FCF)
- Sector/industry context
- Historical drawdown severity
- Moat score

And generate:
```json
{
  "permanentImpairmentRisk": "Low",
  "reasoning": "Microsoft has fortress-level balance sheet with 0.2x Debt/EBITDA...",
  "primaryRisk": "Valuation compression if AI capex fails to generate expected returns"
}
```

**Existing infrastructure to reuse:**
- `ai_service.py` has `generate_suitability_summary()` and `generate_overview_summary()` methods
- `prompts/suitability.py` has template patterns for structured AI output
- Can add a new prompt in `prompts/risk_assessment.py`

---

## 5. Framework Component Analysis

### 5.1 Scenario Model (Bull / Base / Bear)

```
Intrinsic Value = Future EPS × Exit P/E
```

| Input | Source | Status |
|---|---|---|
| Current EPS | `company_summary.trailing_eps` or `income_statements` latest | Available |
| EPS Growth (Bull/Base/Bear) | Analyst consensus + historical CAGR | Available |
| Exit P/E (Bull/Base/Bear) | Historical percentile + industry median | Computable |
| Current Price | Live price service | Available |

**Implementation:**
```python
DEFAULT_SCENARIOS = {
    "bull": {"eps_growth": 0.15, "exit_pe": 28, "probability": 0.25},
    "base": {"eps_growth": 0.08, "exit_pe": 22, "probability": 0.50},
    "bear": {"eps_growth": 0.02, "exit_pe": 15, "probability": 0.20},
    "severe": {"eps_growth": 0.00, "exit_pe": 12, "probability": 0.05},
}

def compute_scenario(current_eps, current_price, scenarios, years=5):
    results = []
    for name, params in scenarios.items():
        future_eps = current_eps * (1 + params["eps_growth"]) ** years
        future_value = future_eps * params["exit_pe"]
        total_return = (future_value / current_price) - 1
        results.append({
            "scenario": name,
            "probability": params["probability"],
            "eps_growth": params["eps_growth"],
            "exit_pe": params["exit_pe"],
            "future_eps": round(future_eps, 2),
            "future_value": round(future_value, 2),
            "total_return": round(total_return, 4),
            "downside": min(0, round(total_return, 4)),
        })
    
    # Expected value
    expected = sum(r["total_return"] * r["probability"] for r in results)
    # Maximum expected loss (worst case, weighted)
    mel = abs(min(r["downside"] * r["probability"] for r in results))
    
    return {"scenarios": results, "expected_return": expected, "mel": mel}
```

### 5.2 Composite Scoring (Weighted Model)

| Factor | Weight | Filled By |
|---|---|---|
| Balance Sheet | 25% | Debt/EBITDA, Interest Coverage, FCF Stability (all pre-computed after §4.1) |
| Earnings Stability | 25% | EPS CAGR, Revenue CAGR, Margin Trends (100% available) |
| Valuation | 20% | P/E percentile, PEG, EV/EBITDA percentile (§4.2) |
| Industry Cyclicality | 15% | Sector-based (§4.5) |
| Management Capital Allocation | 10% | Buybacks, debt trend, ROIC (§4.6) |
| Regulatory/Disruption Risk | 5% | Sector-based (§4.7) |

**Pattern:** Reuse existing `MetricResult` dataclass from `dcf_suitability.py`:

```python
@dataclass
class MetricResult:
    code: str
    name: str
    status: str  # "pass" | "caution" | "fail" | "na"
    points: int  # 2 for pass, 1 for caution, 0 for fail
    weight: float
    evidence: dict

# Final composite 0-100
category_map = {
    (90, 100): "Very Low Downside",
    (70, 89):  "Moderate",
    (50, 69):  "Elevated",
    (0, 49):   "High Risk",
}
```

### 5.3 Maximum Expected Loss (MEL)

```
MEL = Earnings Risk + Multiple Compression + Balance Sheet Risk
```

Each component scored 0-10, combined into percentage estimate. The bear case scenario provides the numerical downside estimate directly.

---

## 6. Implementation Effort Estimate

### Phase 1: Backend Core (Week 1-2)

| Task | Files | Effort | Dependencies |
|---|---|---|---|
| 1. SQL migration script | `backend/scripts/migrate_add_risk_ratios.sql` | 0.5 day | None |
| 2. Add Debt/EBITDA to metrics job | `derived_financial_metrics_job.py` | 0.5 day | Task 1 |
| 3. Pydantic models | `domain/models/risk_assessment.py` | 1 day | None |
| 4. Repository queries | `analysis_repository.py` (+ valuation_repo) | 2 days | Tasks 1-2 |
| 5. Risk assessment service | `application/services/risk_assessment_service.py` | 4 days | Tasks 3-4 |
| 6. API endpoint | `api/analysis.py` | 0.5 day | Task 5 |
| 7. AI summary prompt | `prompts/risk_assessment.py` | 1 day | Task 5 |

**Note:** The `MoatAnalysisService` is already fully implemented and deployed, so the Risk Assessment tab does NOT need to re-implement moat scoring — it calls `MoatAnalysisService.get_moat_analysis()` directly and maps the results. This reduces the `RiskAssessmentService` effort by ~1 day vs the original estimate.

**Phase 1 subtotal: ~8.5 days**

### Phase 2: Frontend (Week 3)

| Task | Files | Effort | Dependencies |
|---|---|---|---|
| 8. TypeScript types | `analysis.types.ts` | 0.5 day | Task 3 |
| 9. Service functions | `analysis.service.ts` | 1 day | Task 8 |
| 10. React Query hook | `hooks/useRiskAssessment.ts` | 1 day | Task 9 |
| 11. Risk panel component | `components/risk-panel.tsx` | 3 days | Task 10 |
| 12. Tab wiring | `page.tsx`, `query-keys.ts`, `prefetch-valuations.ts` | 0.5 day | Task 11 |

**Phase 2 subtotal: ~6 days**

### Phase 3: Polish (Week 4, partial)

| Task | Effort | Dependencies |
|---|---|---|
| 13. Edge case handling | 1 day | Phase 2 complete |
| 14. Chart visualizations (drawdown) | 2 days | Phase 2 complete |
| 15. Testing & verification | 1 day | All complete |

**Phase 3 subtotal: ~4 days**

### Total Estimated Effort: **~18.5 working days (~3 weeks)**

---

## 7. Complete Gap Inventory

### Critical Gaps (Must Fix — ~35 lines total)

| # | Gap | Fix | Lines of Code | Files Touched |
|---|---|---|---|---|
| G1 | `debt_to_ebitda` not in `financial_ratios` | Add to `derived_financial_metrics_job.py` + SQL migration (see §4.1) | ~10 + 2 SQL | 3 files |
| G2 | No historical P/E percentile | On-demand query in `RiskAssessmentService` (see §4.2) | ~25 | 1 file |

### Moderate Gaps (Nice-to-Have for Accuracy — ~50 lines total)

| # | Gap | Fix | Lines of Code | Files Touched |
|---|---|---|---|---|
| G4 | No revenue recurrence classification | Sector-based lookup table | ~15 | 1 file |
| G5 | No crisis drawdown labels | Date-range filter with named periods | ~30 | 1 file |
| G6 | No capital allocation score | Function from buybacks, debt trend, ROIC | ~25 | 1 file |
| G7 | No regulatory/disruption score | Sector-based lookup table | ~15 | 1 file |

### Qualitative Gaps (AI-Powered)

| # | Gap | Fix |
|---|---|---|
| G8 | Permanent impairment risk assessment | AI summary via existing `ai_service.py` |
| G9 | Plain-English risk explanation | AI summary (same mechanism) |

### What's NOT Available (Deferred)

| Feature | Reason | Future Phase |
|---|---|---|
| Monte Carlo simulation | Requires stochastic modeling infra | Phase 3+ |
| 10-K SEC filing analysis | Built as part of moat analysis (`edgar_filing_service.py` + `moat_keyword_analyzer.py`) | Available for risk assessment via moat evidence API |
| Bond / Credit rating | Not stored in DB | Needs data provider |
| Real-time VaR | Requires daily return distribution | Could add later |

---

## 8. Recommended Phasing

### Phase 1 (MVP) — Core Risk Assessment Tab

**Backend response shape:**
```
GET /analysis/{symbol}/risk-assessment

{
  "symbol": "MSFT",
  "composite": {
    "score": 85,
    "category": "Moderate",
    "maximumExpectedLoss": "10-20%"
  },
  "layers": {
    "businessFragility": {
      "score": 9.2,
      "category": "Low",
      "metrics": [
        {"name": "Moat Durability", "value": 9.5, "status": "pass", "evidence": {...}},
        {"name": "Revenue Stability", "value": 0.8, "status": "pass"}
      ]
    },
    "balanceSheet": {
      "score": 9.5,
      "category": "Very Low",
      "metrics": [
        {"name": "Debt/EBITDA", "value": 0.2, "status": "pass", "threshold": "<1x very safe"},
        {"name": "Interest Coverage", "value": 52, "status": "pass"},
        {"name": "FCF Stability (5y)", "value": "100% positive", "status": "pass"}
      ]
    },
    "valuationCompression": {
      "score": 6.5,
      "category": "Moderate",
      "metrics": [
        {"name": "P/E Percentile (5y)", "value": 75, "status": "caution"},
        {"name": "PEG Ratio", "value": 2.1, "status": "caution"}
      ]
    },
    "earningsStress": {
      "score": 8.0,
      "category": "Low",
      "metrics": [
        {"name": "EPS CAGR (5y)", "value": "15%", "status": "pass"}
      ]
    },
    "drawdownRisk": {
      "score": 7.0,
      "category": "Moderate",
      "metrics": [
        {"name": "Max Drawdown (5y)", "value": "-38%", "status": "caution"},
        {"name": "Beta (5y)", "value": 0.94, "status": "pass"}
      ]
    }
  },
  "bearCase": {
    "epsGrowthAssumption": 0.03,
    "exitPERatio": 18,
    "futureValue": 351,
    "currentPrice": 419,
    "downside": -0.16
  },
  "aiSummary": "Microsoft shows fortress-level financial strength...",
  "dataQuality": {...}
}
```

**Frontend layout:**
- Hero section: Composite score (ring gauge) + MEL + category
- 5 metric cards in grid (2 rows: fragility + balance sheet top, valuation + earnings + drawdown bottom)
- Each card: scored ring/bar + key metric list with status indicators
- Bear case box with prominent downside percentage
- AI summary section at bottom

### Phase 2 — Charts & History

- Drawdown history chart (reuses `_drawdown_series()` from `stock_index_comparison_service.py`)
- Valuation percentile gauge (current P/E vs 5-year range)
- Balance sheet trend (Debt/EBITDA over time)
- EPS stability chart

### Phase 3 — Scenario Modeling

- "What-if" controls (adjust growth rate, exit P/E, see downside update)
- Peer comparison (via `industry_multiples` table)
- Historical crisis drawdown labels

---

## Appendix A: Existing Code Reference

### Reusable Functions

| Function | File | Line | Purpose |
|---|---|---|---|---|
| `_max_drawdown()` | `stock_index_comparison_service.py` | 396 | Peak-to-trough decline |
| `_calculate_beta()` | `stock_index_comparison_service.py` | 316 | Covariance/variance beta |
| `_drawdown_series()` | `stock_index_comparison_service.py` | 425 | Full drawdown timeline |
| `safe_div()` | `shared/finance_math.py` | — | Null-safe division |
| `_fcf()` | `derived_financial_metrics_job.py` | 55 | Sign-aware FCF |
| Interest Coverage | `derived_financial_metrics_job.py` | 301 | EBIT / abs(Interest) |
| `MetricResult` pattern | `dcf_suitability.py` | — | pass/caution/fail scoring |
| EPS/Revenue CAGR | `analysis_repository.py` | 433 | 3-year CAGR |
| EPS Drawdown | `rule1_suitability.py` | — | EPS peak-to-trough |
| AI Summary | `ai_service.py` | — | Plain-English generation |
| Revenue Recurrence | — | — | New, sector-based |
| **MoatAnalysisService** | `moat_analysis_service.py` | 47 | Full moat orchestration: quant scoring + EDGAR evidence + AI narrative |
| **compute_stage1_score()** | `moat_analysis_service.py` | 384 | 5-factor quant moat score (ROIC spread, margins, stability, efficiency) |
| **MoatKeywordAnalyzer** | `moat_keyword_analyzer.py` | 65 | Regex EDGAR text scanner across 5 moat source groups |
| **MoatWaccService** | `moat_wacc_service.py` | — | CAPM-based WACC computation |
| **MoatRepository** | `moat_repository.py` | — | CRUD for moat_analysis, moat_keyword_evidence, moat_ai_narratives |
| **Moat Panel (UI)** | `moat-panel.tsx` | — | Frontend panel with metrics grid, evidence, AI narrative, diagnostics |

### Key Data Queries

| Query | File | Purpose |
|---|---|---|
| `get_income_statements_annual()` | `valuation_repository.py` | Annual financials |
| `get_balance_sheet_latest()` | `valuation_repository.py` | Latest balance sheet |
| `get_cash_flow_latest()` | `valuation_repository.py` | Latest cash flow |
| `get_fcf_history()` | `valuation_repository.py` | FCF time series |
| `get_price_history_range()` | `analysis_repository.py:412` | Price data for drawdown |
| `get_company_summary_latest()` | `valuation_repository.py:1348` | Latest valuation snapshot |
| `get_derived_metrics_latest()` | `valuation_repository.py:1695` | Pre-computed ratios |
| `get_company_context()` | `valuation_repository.py` | Company metadata |
| `get_revenue_and_eps_growth()` | `analysis_repository.py:433` | CAGR computation |
| `get_industry_multiples()` | `valuation_repository.py` | Peer benchmarks |
| `get_current_market_price()` | `valuation_repository.py` | Live price |

## Appendix B: Database Schema (Risk-Relevant Columns)

### `financial_ratios` (after adding new columns)

Pre-computed ratios per fiscal year. All columns exist **except** the two marked with `[NEW]`:

```sql
-- Profitability
roic, roe, roa,
gross_margin, operating_margin, ebitda_margin, net_margin, fcf_margin,

-- Cash Flow
free_cash_flow, fcf_conversion,

-- Dividend
dividend_payout_ratio, fcf_dividend_payout_ratio, dividend_coverage_fcf,

-- Leverage (BALANCE SHEET RISK)
debt_to_equity, debt_to_assets,
long_term_debt_to_equity, long_term_debt_to_assets,
interest_coverage,
debt_to_ebitda             [NEW] -- Total Debt / EBITDA
net_debt_to_ebitda         [NEW] -- (Total Debt - Cash) / EBITDA

-- Liquidity
current_ratio, quick_ratio,

-- Efficiency
asset_turnover, inventory_turnover,

-- Per Share
revenue_ps, ocf_ps, fcf_ps, ebit_ps, ebitda_ps, bvps,
tangible_bvps, cash_ps, total_debt_ps, wc_ps, capex_ps,
```

### `company_summary`

Daily snapshot, used for valuation percentile:

```sql
trailing_pe         numeric(10,4),    -- Current P/E
forward_pe          numeric(10,4),    -- Forward P/E
enterprise_to_ebitda numeric(10,4),   -- EV/EBITDA
peg_ratio           numeric(10,4),    -- PEG
beta                numeric(8,4),     -- 5y beta
enterprise_value    numeric(20,2),    -- EV
market_cap          numeric(20,2),    -- Market Cap
snapshot_date       date,             -- Indexed + sorted
-- UNIQUE ON: (company_id, snapshot_date, provider)
```

### `companies`

Sector and industry for cyclicality/recurrence classification:

```sql
sector    varchar(100),   -- e.g. "Technology", "Healthcare"
industry  varchar(100),   -- e.g. "Software—Infrastructure"
```

### `cash_flow_statements`

For capital allocation scoring:

```sql
share_repurchases   numeric(15,2),   -- Buyback activity
free_cash_flow      numeric(15,2),   -- Cash generation
cash_from_operating_activities       -- Operating cash flow
```

### `moat_analysis` (IMPLEMENTED)

Cached composite moat scores per company (24h TTL):

```sql
moat_score              DOUBLE PRECISION,  -- 0-100 composite
moat_category           TEXT,              -- Wide / Narrow / None / Unknown
roic                    DOUBLE PRECISION,  -- Latest ROIC
wacc                    DOUBLE PRECISION,  -- Computed WACC
roic_minus_wacc         DOUBLE PRECISION,  -- Economic spread
gross_margin_pct        DOUBLE PRECISION,
operating_margin_pct    DOUBLE PRECISION,
net_margin_pct          DOUBLE PRECISION,
roic_5y_avg             DOUBLE PRECISION,
roic_5y_std             DOUBLE PRECISION,
roic_stability_score    DOUBLE PRECISION,  -- 0-100
capital_efficiency_score DOUBLE PRECISION, -- 0-100
text_analysis_available BOOLEAN,
keyword_matches_count   INTEGER,
sector                  TEXT,
sector_adjustment       DOUBLE PRECISION,
ai_narrative_available  BOOLEAN,
computed_at             TIMESTAMPTZ,
-- UNIQUE ON: company_id
```

### `moat_keyword_evidence` (IMPLEMENTED)

Keyword match snippets from EDGAR 10-K text analysis:

```sql
keyword         TEXT,              -- e.g. 'patent', 'switching_cost'
keyword_group   TEXT,              -- e.g. 'intangible_assets', 'network_effects'
snippet         TEXT,              -- surrounding context (~200 chars)
section         TEXT,              -- filing section (item_1, item_1a, item_7)
filing_type     TEXT,              -- '10-K'
filing_date     DATE,
relevance_score DOUBLE PRECISION,  -- 0-1 weight
-- UNIQUE ON: (company_id, filing_date, section, keyword, snippet)
```

### `moat_ai_narratives` (IMPLEMENTED)

Cached AI-generated moat narratives:

```sql
narrative           TEXT,              -- Full AI assessment
summary             TEXT,              -- Optional summary
model               TEXT,              -- 'openrouter/default'
quant_snapshot      JSONB,             -- Scores used as context
evidence_count      INTEGER,
generated_at        TIMESTAMPTZ,
generation_time_ms  INTEGER,
-- UNIQUE ON: company_id
```

## Appendix C: SQL Migration Script

**File:** `backend/scripts/migrate_add_risk_ratios.sql`

```sql
-- Migration: Add risk-specific ratios to financial_ratios
-- Required by the Risk Assessment tab

ALTER TABLE public.financial_ratios
  ADD COLUMN IF NOT EXISTS debt_to_ebitda numeric(15, 4) NULL,
  ADD COLUMN IF NOT EXISTS net_debt_to_ebitda numeric(15, 4) NULL;

COMMENT ON COLUMN public.financial_ratios.debt_to_ebitda IS 'Total Debt / EBITDA — leverage risk metric for Risk Assessment tab';
COMMENT ON COLUMN public.financial_ratios.net_debt_to_ebitda IS '(Total Debt - Cash & Equivalents) / EBITDA — net leverage metric';
```
