# Risk Assessment Tab — Detailed Design Document

> **Version:** 1.1
> **Date:** 2026-05-26
> **Status:** Implementation Complete
> **Scope:** Full-stack design of the Risk Assessment tab on the Stock Analysis page (`/analysis/[symbol]`)

---

## Table of Contents

1. [Use Cases](#1-use-cases)
2. [Backend Design](#2-backend-design)
3. [Frontend Design](#3-frontend-design)
4. [Sequence Diagrams](#4-sequence-diagrams)
5. [Test Plans](#5-test-plans)

---

## 1. Use Cases

### UC-1: View Composite Risk Score

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user on `/analysis/[symbol]` |
| **Trigger** | User selects "Risk Assessment" tab |
| **Precondition** | User is viewing a valid stock symbol |
| **Postcondition** | Composite risk score and MEL displayed across 5 risk layers |
| **Priority** | P0 — MVP |

**Flow:**
1. Page loads with tab=risk, triggers prefetch
2. `RiskAssessmentService` fetches and computes all 5 risk layers
3. Composite score is calculated from weighted layer scores
4. MEL is derived from bear-case scenario
5. Frontend renders the hero ring gauge + 5 layer cards

**Acceptance criteria:**
- Composite score (0–100) displayed as ring gauge
- MEL percentage displayed prominently
- 5 layer cards each show score (0–10) and category label
- AI summary section rendered at bottom

---

### UC-2: View Business Fragility Analysis

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads |
| **Precondition** | Company exists with sector classification |
| **Postcondition** | Moat score, revenue recurrence, pricing power, and cyclicality displayed |
| **Priority** | P0 |

**Flow:**
1. `RiskAssessmentService` calls `MoatAnalysisService.get_moat_analysis()` to retrieve cached moat score
2. Sector/industry fetched from `companies` table
3. Revenue recurrence classified via sector heuristic
4. Pricing power proxied via gross margin trend
5. Layer 1 score computed from all sub-metrics

**Acceptance criteria:**
- Moat score (0–100) shown with category badge (Wide/Narrow/None)
- ROIC vs WACC spread displayed
- Sector classification shown
- Revenue recurrence classification shown (High/Medium/Low)
- Diagnostic flags from moat service surfaced

---

### UC-3: View Balance Sheet Risk

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads |
| **Precondition** | Debt/EBITDA columns exist in financial_ratios (post-migration) |
| **Postcondition** | Debt/EBITDA, Interest Coverage, FCF stability, and leverage ratios displayed |
| **Priority** | P0 |

**Flow:**
1. `BalanceSheetRiskAnalyzer` fetches latest `financial_ratios` row
2. Debt/EBITDA, Net Debt/EBITDA, Interest Coverage scored against thresholds
3. FCF stability computed from multi-year cash flow history
4. Current Ratio, Quick Ratio, Debt-to-Equity evaluated
5. Layer 2 score computed

**Acceptance criteria:**
- Debt/EBITDA displayed with color-coded risk threshold
- Interest Coverage displayed
- FCF Stability (years positive / total years) shown
- Leverage trend arrow shown (improving/stable/deteriorating)

---

### UC-4: View Valuation Compression Risk

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads |
| **Precondition** | company_summary has 5+ years of snapshots |
| **Postcondition** | P/E percentile, EV/EBITDA percentile, and PEG displayed |
| **Priority** | P0 |

**Flow:**
1. `ValuationRiskAnalyzer` queries `company_summary` time series
2. Current P/E ranked against 5-year historical distribution
3. Current EV/EBITDA ranked against 5-year historical distribution
4. PEG ratio evaluated (expensive vs reasonable threshold)
5. Layer 3 score computed

**Acceptance criteria:**
- P/E percentile gauge (0–100, colored by zone)
- EV/EBITDA percentile gauge
- 5-year min/median/max displayed for both metrics
- PEG ratio with status indicator

---

### UC-5: View Earnings / Cash Flow Stress

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads |
| **Precondition** | Income and cash flow statements available |
| **Postcondition** | CAGR trends and margin stability metrics displayed |
| **Priority** | P0 |

**Flow:**
1. `EarningsStressAnalyzer` computes EPS CAGR (3y, 5y) from `income_statements`
2. Revenue CAGR (3y, 5y) computed
3. Net/Operating/FCF margin trends evaluated
4. EPS volatility and drawdown computed
5. Analyst forecast growth rates included
6. Layer 4 score computed

**Acceptance criteria:**
- EPS and Revenue CAGR displayed with direction arrows
- Margin trend chart (net, operating, FCF over 5 years)
- EPS stability indicator (consistent/volatile)
- Surprise trend (positive/negative/mixed) shown

---

### UC-6: View Historical Drawdown Risk

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads |
| **Precondition** | Price history available |
| **Postcondition** | Max drawdown, beta, crisis drawdowns, and recovery time displayed |
| **Priority** | P0 |

**Flow:**
1. `DrawdownAnalyzer` (reuses `_max_drawdown()` from `stock_index_comparison_service.py`)
2. Computes 1y/3y/5y max drawdown from `price_history`
3. Fetches beta from `company_summary.beta`
4. Computes crisis-period drawdowns (COVID, 2022 rate hike)
5. Computes current drawdown from peak
6. Layer 5 score computed

**Acceptance criteria:**
- Max drawdown percentages for 1y/3y/5y displayed
- Beta (5y) shown
- Crisis drawdown labels (e.g., "COVID Crash: -38%")
- Peak-to-trough recovery time shown

---

### UC-7: View Scenario Modeling

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads (bottom section) |
| **Precondition** | Current EPS and price available |
| **Postcondition** | Bull/Base/Bear/Severe scenarios displayed with probability-weighted MEL |
| **Priority** | P1 — Phase 3 |

**Flow:**
1. `ScenarioModeler` fetches current EPS, price, and historical CAGRs
2. Computes 4 scenarios with configurable growth and exit multiples
3. Calculates total return and downside for each
4. Computes probability-weighted expected return and MEL
5. Returns scenarios for frontend display

**Acceptance criteria:**
- 4 scenario cards (Bull/Base/Bear/Severe) with return %
- Probability weights displayed
- MEL computed and shown as worst-case expected loss
- Sensitivity controls (future phase)

---

### UC-8: View Maximum Expected Loss (MEL)

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | Risk Assessment tab loads |
| **Precondition** | All 5 layers computed |
| **Postcondition** | MEL displayed as percentage in hero section |
| **Priority** | P0 |

**Flow:**
1. Composite score computed from weighted layer scores
2. Bear-case return extracted from scenario modeler
3. MEL displayed as primary downside metric

**Acceptance criteria:**
- MEL shown prominently near composite score
- Bear case scenario shown (Future EPS, Exit P/E, Future Value, Downside %)

---

### UC-9: Regenerate AI Summary

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User clicks "Regenerate" on AI summary section |
| **Precondition** | Risk assessment data computed |
| **Postcondition** | New AI summary generated and displayed |
| **Priority** | P1 |

**Flow:**
1. User clicks "Regenerate AI Summary"
2. Frontend calls `POST /analysis/{symbol}/risk-assessment/ai`
3. Backend builds prompt with all layer scores, moat data, and key metrics
4. Calls OpenRouter API (reuses pattern from `moat_analysis_service.py`)
5. Caches and returns new narrative
6. Frontend updates display

**Acceptance criteria:**
- Loading state during generation
- New narrative displayed after completion
- Error state shown if API fails

---

### UC-10: View EDGAR Moat Evidence

| Aspect | Detail |
|---|---|
| **Actor** | Authenticated user |
| **Trigger** | User opens "Moat Evidence" section in Business Fragility card |
| **Precondition** | Moat analysis has been computed and EDGAR text has been analyzed |
| **Postcondition** | Keyword matches from 10-K displayed grouped by moat source |
| **Priority** | P2 |

**Flow:**
1. User clicks "Moat Evidence" expandable section
2. Frontend calls `GET /analysis/{symbol}/moat/evidence`
3. Backend returns keyword matches from `moat_keyword_evidence` table
4. Frontend displays grouped by moat source category

**Acceptance criteria:**
- Evidence grouped by moat source (intangibles, switching costs, network effects, etc.)
- Snippet preview with keyword highlighted
- Filing date and section metadata shown

---

## 2. Backend Design

### 2.1 Domain Models (Pydantic v2)

#### File: `backend/domain/models/risk_assessment.py`

```python
from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import date


# ── Shared Enums / Literals ──

RiskCategory = Literal[
    "Very Low Downside",
    "Moderate",
    "Elevated",
    "High Risk",
]

RiskSeverity = Literal["low", "moderate", "elevated", "high", "severe"]

LayerName = Literal[
    "business_fragility",
    "balance_sheet",
    "valuation_compression",
    "earnings_stress",
    "drawdown_risk",
]


# ── Sub-metric ──

class RiskMetric(BaseModel):
    name: str
    value: Optional[float] = None
    label: str                          # human-readable display value
    status: Literal["pass", "caution", "fail", "na"]
    weight: float = 1.0
    evidence: Optional[Dict[str, Any]] = None
    threshold_description: Optional[str] = None


# ── Layer Base ──

class RiskLayer(BaseModel):
    name: LayerName
    display_name: str
    score: float                        # 0-10
    category: RiskSeverity
    metrics: List[RiskMetric]
    weight: float                       # contribution to composite


# ── Concrete Layers ──

class BusinessFragility(RiskLayer):
    moat_score: Optional[float] = None          # 0-100 (from MoatAnalysisService)
    moat_category: Optional[str] = None         # Wide / Narrow / None / Unknown
    roic_minus_wacc: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    recurrence_classification: Optional[str] = None  # High / Medium / Low
    pricing_power_assessment: Optional[str] = None


class BalanceSheetRisk(RiskLayer):
    debt_to_ebitda: Optional[float] = None
    net_debt_to_ebitda: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    fcf_conversion: Optional[float] = None
    fcf_stability_pct: Optional[float] = None    # years positive / total years


class ValuationCompressionRisk(RiskLayer):
    pe_current: Optional[float] = None
    pe_percentile: Optional[float] = None        # 0-100 (100 = most expensive)
    pe_5y_min: Optional[float] = None
    pe_5y_max: Optional[float] = None
    pe_5y_median: Optional[float] = None
    ev_ebitda_current: Optional[float] = None
    ev_ebitda_percentile: Optional[float] = None
    peg_ratio: Optional[float] = None


class EarningsStressRisk(RiskLayer):
    eps_cagr_3y: Optional[float] = None
    eps_cagr_5y: Optional[float] = None
    revenue_cagr_3y: Optional[float] = None
    revenue_cagr_5y: Optional[float] = None
    net_margin_current: Optional[float] = None
    operating_margin_trend: Optional[Literal["expanding", "stable", "contracting"]] = None
    revenue_eps_alignment: Optional[Literal["aligned", "diverging", "volatile"]] = None
    eps_volatility: Optional[float] = None


class DrawdownRisk(RiskLayer):
    max_drawdown_1y: Optional[float] = None
    max_drawdown_3y: Optional[float] = None
    max_drawdown_5y: Optional[float] = None
    beta_5y: Optional[float] = None
    current_drawdown: Optional[float] = None
    crisis_drawdowns: Optional[List[CrisisDrawdown]] = None
    recovery_time_days: Optional[int] = None


class CrisisDrawdown(BaseModel):
    crisis_name: str
    start_date: date
    end_date: date
    max_drawdown: float
    start_value: float
    end_value: float


# ── Scenario Modeling ──

class ScenarioInput(BaseModel):
    name: str                               # bull / base / bear / severe
    eps_growth: float
    exit_pe: float
    probability: float                      # sum = 1.0


class ScenarioResult(BaseModel):
    scenario: str
    probability: float
    eps_growth: float
    exit_pe: float
    future_eps: float
    future_value: float
    total_return: float                     # decimal
    downside: float                         # min(0, total_return)


class BearCase(BaseModel):
    eps_growth_assumption: float
    exit_pe_ratio: float
    future_value: float
    current_price: float
    downside_pct: float


# ── Composite ──

class CompositeScore(BaseModel):
    score: float                            # 0-100
    category: RiskCategory
    maximum_expected_loss_pct: float
    bear_case: BearCase


# ── AI Narrative ──

class RiskAiNarrative(BaseModel):
    narrative: str
    model: str = "openrouter/default"
    generated_at: str = ""
    generation_time_ms: Optional[int] = None


# ── Top-Level Response ──

class RiskAssessmentResponse(BaseModel):
    symbol: str
    company_id: int
    currency: str
    composite: CompositeScore
    layers: Dict[LayerName, RiskLayer]      # keyed by layer name
    scenarios: Optional[List[ScenarioResult]] = None
    ai_narrative: Optional[RiskAiNarrative] = None
    data_quality: RiskDataQuality


class RiskDataQuality(BaseModel):
    data_sources: str = "database"
    fiscal_year_end: Optional[int] = None
    days_since_update: Optional[int] = None
    fallbacks_used: bool = False
    last_computed_at: str = ""
```

---

### 2.2 Services

#### File: `backend/application/services/risk_assessment_service.py`

```
┌──────────────────────────────────────────────────────────────────┐
│                    RiskAssessmentService                         │
│                    (Orchestrator)                                │
├──────────────────────────────────────────────────────────────────┤
│ - _repo: RiskRepository                                         │
│ - _moat_service: MoatAnalysisService                             │
│ - _wacc_service: MoatWaccService                                 │
├──────────────────────────────────────────────────────────────────┤
│ + get_risk_assessment(symbol, force?) -> RiskAssessmentResponse  │
│ + get_ai_narrative(symbol) -> RiskAiNarrative                    │
│ + generate_ai_narrative(symbol) -> RiskAiNarrative               │
│                                                                  │
│ # Internal helpers:                                              │
│ # _compute_all_layers(ctx, ratios, prices) -> Dict[LayerName, float] │
│ # _compute_composite(layers) -> CompositeScore                   │
│ # _compute_scenarios(ctx, current_price) -> ScenarioResults      │
│ # _compute_mel(scenarios) -> float                               │
│ # _build_ai_prompt(layers, scenarios, moat) -> str               │
└──────────────────────────────────────────────────────────────────┘
```

**Orchestration logic:**

```
get_risk_assessment(symbol):
  1. ctx = repo.get_company_context(symbol)
  2. moat = moat_service.get_moat_analysis(symbol)   # reuse existing
  3. ratios = repo.get_latest_financial_ratios(company_id)
  4. ratios_history = repo.get_financial_ratios_history(company_id, years=5)
  5. prices = repo.get_price_history_range(company_id, years=5)
  6. income = repo.get_income_statements_annual(company_id, years=5)
  7. cash_flow = repo.get_cash_flow_latest(company_id)
  8. current_price = repo.get_current_market_price(company_id)
  
  9. layer1 = self._analyze_business_fragility(ctx, moat, ratios_history)
  10. layer2 = self._analyze_balance_sheet(ratios, cash_flow)
  11. layer3 = self._analyze_valuation_compression(company_id)
  12. layer4 = self._analyze_earnings_stress(income)
  13. layer5 = self._analyze_drawdown_risk(prices, ctx)
  
  14. composite = self._compute_composite([layer1..layer5])
  15. scenarios = self._compute_scenarios(ctx, income, current_price)
  16. mel = self._compute_mel(scenarios)
  
  17. return RiskAssessmentResponse(...)
```

#### File: `backend/application/services/risk_assessment_service.py` — Layer Analyzers

Each analyzer is a method on `RiskAssessmentService` (or could be factored into separate classes if complexity warrants). The current design keeps them as methods for simplicity:

```python
class RiskAssessmentService:
    # ... constructor with repo, moat_service, wacc_service ...

    async def _analyze_business_fragility(
        self,
        ctx: Dict[str, Any],
        moat: Optional[MoatResponse],
        ratios_history: List[Dict[str, Any]],
    ) -> BusinessFragility:
        """Layer 1: Competitive position + sector dynamics."""
        sector = ctx.get("sector", "")
        industry = ctx.get("industry", "")

        # Moat score from existing MoatAnalysisService
        moat_score = moat.valuation.moat_score if moat else None
        moat_category = moat.valuation.moat_category if moat else None
        roic_spread = moat.valuation.roic_minus_wacc if moat else None

        # Revenue recurrence (sector heuristic)
        recurrence = self._classify_recurrence(sector)

        # Pricing power (gross margin trend)
        pricing = self._assess_pricing_power(ratios_history)

        metrics = [
            RiskMetric(name="Moat Durability", value=moat_score, label=str(moat_category or "N/A"), status=self._moat_status(moat_category)),
            RiskMetric(name="Revenue Recurrence", label=recurrence, status=self._recurrence_status(recurrence)),
            RiskMetric(name="Pricing Power", label=pricing, status=self._pricing_status(pricing)),
        ]
        score = self._compute_layer_score(metrics, weights={"moat": 5, "recurrence": 3, "pricing": 2})
        return BusinessFragility(
            name="business_fragility", display_name="Business Fragility",
            score=score, category=self._score_to_severity(score),
            metrics=metrics, weight=0.20,
            moat_score=moat_score, moat_category=moat_category,
            roic_minus_wacc=roic_spread, sector=sector, industry=industry,
            recurrence_classification=recurrence, pricing_power_assessment=pricing,
        )

    async def _analyze_balance_sheet(
        self,
        ratios: Optional[Dict[str, Any]],
        cash_flow: Optional[Dict[str, Any]],
    ) -> BalanceSheetRisk:
        """Layer 2: Leverage, liquidity, FCF stability."""

    async def _analyze_valuation_compression(
        self,
        company_id: int,
    ) -> ValuationCompressionRisk:
        """Layer 3: Historical percentile ranking."""

    async def _analyze_earnings_stress(
        self,
        income_statements: List[Dict[str, Any]],
    ) -> EarningsStressRisk:
        """Layer 4: CAGR trends, margin stability, EPS volatility."""

    async def _analyze_drawdown_risk(
        self,
        prices: List[Dict[str, Any]],
        ctx: Dict[str, Any],
    ) -> DrawdownRisk:
        """Layer 5: Max drawdown, beta, crisis periods."""
```

**Reuse of existing services:**

| Existing Service | How RiskAssessmentService consumes it |
|---|---|
| `MoatAnalysisService.get_moat_analysis()` | Called directly — returns cached or fresh moat score + category |
| `MoatWaccService` | Not called directly — WACC is embedded in moat response |
| `StockIndexComparisonService._max_drawdown()` | Reused as `DrawdownAnalyzer._max_drawdown()` or imported |
| `AnalysisRepository.get_revenue_and_eps_growth()` | Used by Earnings Stress analyzer |
| Existing CAGR helpers | Reused for EPS/Revenue CAGR computation |

---

### 2.3 Repository

#### File: `backend/infrastructure/repositories/risk_repository.py`

```
┌──────────────────────────────────────────────────────────────┐
│                    RiskRepository                             │
├──────────────────────────────────────────────────────────────┤
│ # Composition: wraps ValuationRepository for base queries    │
│ - _repo: ValuationRepository                                 │
├──────────────────────────────────────────────────────────────┤
│ + get_company_context(symbol) -> Dict | None                 │
│ + get_latest_financial_ratios(company_id) -> Dict | None     │
│ + get_financial_ratios_history(company_id, years) -> List    │
│ + get_income_statements_annual(company_id, years) -> List    │
│ + get_cash_flow_latest(company_id) -> Dict | None           │
│ + get_price_history_range(company_id, start, end) -> List   │
│ + get_current_market_price(company_id) -> float | None      │
│ + get_company_summary_history(company_id, years) -> List    │
│ # AI narrative caching                                       │
│ + upsert_risk_ai_narrative(company_id, payload) -> None     │
│ + get_risk_ai_narrative(company_id) -> Dict | None          │
└──────────────────────────────────────────────────────────────┘
```

Most queries already exist in `ValuationRepository` or `AnalysisRepository`. `RiskRepository` delegates to them:

```python
class RiskRepository:
    def __init__(self, repo: ValuationRepository) -> None:
        self._repo = repo

    async def get_company_context(self, symbol: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_company_context(symbol)

    async def get_latest_financial_ratios(self, company_id: int) -> Optional[Dict[str, Any]]:
        return await self._repo.get_derived_metrics_latest(company_id)

    async def get_financial_ratios_history(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        # Custom query: financial_ratios ordered by fiscal_year DESC
        cutoff_year = date.today().year - years
        resp = (
            supabase.table("financial_ratios")
            .select("*")
            .eq("company_id", company_id)
            .gte("fiscal_year", cutoff_year)
            .order("fiscal_year", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_company_summary_history(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
        resp = (
            supabase.table("company_summary")
            .select("snapshot_date, trailing_pe, enterprise_to_ebitda, peg_ratio, beta")
            .eq("company_id", company_id)
            .not_.is_("trailing_pe", "null")
            .gte("snapshot_date", cutoff)
            .order("snapshot_date", desc=False)
            .execute()
        )
        return resp.data or []
```

---

### 2.4 Backend Class Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RiskAssessmentResponse                       │
├─────────────────────────────────────────────────────────────────────┤
│ symbol: str                                                         │
│ company_id: int                                                     │
│ currency: str                                                       │
│ composite: CompositeScore                                           │
│ layers: Dict[LayerName, RiskLayer]                                  │
│ scenarios: List[ScenarioResult] | None                              │
│ ai_narrative: RiskAiNarrative | None                                │
│ data_quality: RiskDataQuality                                       │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ composed of
          ┌─────────────┼─────────────┬──────────────────────┐
          ▼             ▼             ▼                      ▼
┌─────────────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────────┐
│  CompositeScore │ │ RiskLayer│ │ScenarioResult│ │ RiskDataQuality  │
├─────────────────┤ │ (abstract│ ├──────────────┤ ├──────────────────┤
│ score: float    │ │  base)   │ │ scenario: str│ │ data_sources: str│
│ category: enum  │ ├──────────┤ │ probability  │ │ fiscal_year_end  │
│ mel_pct: float  │ │ score    │ │ future_eps   │ │ fallbacks_used   │
│ bear_case       │ │ severity │ │ total_return │ │ last_computed_at │
└─────────────────┘ │ metrics  │ │ downside     │ └──────────────────┘
                    │ weight   │ └──────────────┘
                    └────┬─────┘
                         │ extends
         ┌───────────────┼───────────────┬───────────────┐
         ▼               ▼               ▼               ▼
┌─────────────────┐ ┌───────────┐ ┌──────────────┐ ┌───────────────┐
│ BusinessFragility│ │BalanceShee│ │ValuationCompr│ │EarningsStress│
├─────────────────┤ │tRisk     │ │essionRisk    │ │Risk           │
│ moat_score       │ ├──────────┤ ├──────────────┤ ├───────────────┤
│ moat_category    │ │d/e        │ │pe_current    │ │eps_cagr_3y    │
│ roic_minus_wacc  │ │interest_cv│ │pe_percentile │ │revenue_cagr   │
│ recurrence_class │ │current_r  │ │ev_ebitda     │ │margin_trend   │
│ pricing_power    │ │fcf_stable │ │peg_ratio     │ │eps_volatility │
└─────────────────┘ └──────────┘ └──────────────┘ └───────────────┘

┌─────────────────────────────┐
│      DrawdownRisk           │
├─────────────────────────────┤
│ max_drawdown_1y/3y/5y       │
│ beta_5y                     │
│ crisis_drawdowns: List      │
│ recovery_time_days          │
└─────────────────────────────┘

┌─────────────────────────────────────────────┐
│           RiskAssessmentService              │
├─────────────────────────────────────────────┤
│ - _repo: RiskRepository                     │
│ - _moat_service: MoatAnalysisService        │
│ - _wacc_service: MoatWaccService            │
├─────────────────────────────────────────────┤
│ + get_risk_assessment(symbol, force?)       │
│ + get_ai_narrative(symbol)                  │
│ + generate_ai_narrative(symbol)             │
│ - _analyze_business_fragility(...)          │
│ - _analyze_balance_sheet(...)               │
│ - _analyze_valuation_compression(...)       │
│ - _analyze_earnings_stress(...)             │
│ - _analyze_drawdown_risk(...)               │
│ - _compute_composite(layers)                │
│ - _compute_scenarios(ctx, price)            │
│ - _compute_mel(scenarios)                   │
│ - _compute_layer_score(metrics, weights)    │
│ - _score_to_severity(score)                 │
└──────────────────────┬──────────────────────┘
                       │ uses
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌─────────────────┐ ┌──────────┐ ┌──────────────────┐
│  RiskRepository  │ │MoatAnaly│ │  ScenarioModeler  │
│                  │ │sisServic│ │  (internal)       │
│ Delegates to     │ │e        │ │                    │
│ ValuationRepo    │ │(existing)│ │ BEAR = EPS*(1+g)^n│
└─────────────────┘ └──────────┘ │ * exit_PE          │
                                 └────────────────────┘
```

### 2.5 API Endpoint

Added to `backend/api/analysis.py` following the existing lazy-factory pattern:

```python
# ── Risk Assessment ─────────────────────────────────────────────

def _get_risk_service():
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from infrastructure.repositories.risk_repository import RiskRepository
    from application.services.moat_wacc_service import MoatWaccService
    from application.services.moat_analysis_service import MoatAnalysisService
    from application.services.risk_assessment_service import RiskAssessmentService
    repo = ValuationRepository()
    risk_repo = RiskRepository(repo)
    wacc = MoatWaccService(risk_repo)
    moat = MoatAnalysisService(risk_repo, wacc)
    return RiskAssessmentService(risk_repo, moat, wacc)


@router.get(
    "/{symbol}/risk-assessment",
    summary="Risk Assessment: composite downside risk across 5 layers.",
)
@limiter.limit("30/minute")
async def get_risk_assessment(
    request: Request,
    symbol: str,
    force: bool = Query(False, description="Bypass cache and recompute"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_risk_service()
        result = await service.get_risk_assessment(sym, force=force)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_risk_assessment failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Risk assessment failed.",
        )


@router.post(
    "/{symbol}/risk-assessment/ai",
    summary="Generate AI summary for risk assessment.",
)
@limiter.limit("5/minute")
async def generate_risk_ai_narrative(
    request: Request,
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    """See UC-9 for flow details."""
    try:
        sym = _normalize(symbol)
        service = _get_risk_service()
        # Recompute risk layers first to get fresh data, then generate AI
        assessment = await service.get_risk_assessment(sym, force=True)
        narrative = await service.generate_ai_narrative(sym, assessment)
        return {"narrative": narrative.narrative, "model": narrative.model}
    except Exception as exc:
        logger.error("generate_risk_ai failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="AI narrative generation failed.")
```

---

## 3. Frontend Design

### 3.1 TypeScript Types

#### File: `web/src/features/analysis/types/analysis.types.ts`

Add the following types (lines ~950+):

```typescript
// ── Risk Assessment Types ──

export type RiskCategory =
  | "Very Low Downside"
  | "Moderate"
  | "Elevated"
  | "High Risk";

export type RiskSeverity = "low" | "moderate" | "elevated" | "high" | "severe";

export type LayerName =
  | "business_fragility"
  | "balance_sheet"
  | "valuation_compression"
  | "earnings_stress"
  | "drawdown_risk";

export interface RiskMetric {
  name: string;
  value?: number | null;
  label: string;
  status: "pass" | "caution" | "fail" | "na";
  weight: number;
  evidence?: Record<string, unknown> | null;
  threshold_description?: string | null;
}

export interface RiskLayer {
  name: LayerName;
  display_name: string;
  score: number;
  category: RiskSeverity;
  metrics: RiskMetric[];
  weight: number;
}

export interface BusinessFragility extends RiskLayer {
  moat_score?: number | null;
  moat_category?: string | null;
  roic_minus_wacc?: number | null;
  sector?: string | null;
  industry?: string | null;
  recurrence_classification?: string | null;
  pricing_power_assessment?: string | null;
}

export interface BalanceSheetRisk extends RiskLayer {
  debt_to_ebitda?: number | null;
  net_debt_to_ebitda?: number | null;
  interest_coverage?: number | null;
  current_ratio?: number | null;
  quick_ratio?: number | null;
  debt_to_equity?: number | null;
  fcf_conversion?: number | null;
  fcf_stability_pct?: number | null;
}

export interface ValuationCompressionRisk extends RiskLayer {
  pe_current?: number | null;
  pe_percentile?: number | null;
  pe_5y_min?: number | null;
  pe_5y_max?: number | null;
  pe_5y_median?: number | null;
  ev_ebitda_current?: number | null;
  ev_ebitda_percentile?: number | null;
  peg_ratio?: number | null;
}

export interface EarningsStressRisk extends RiskLayer {
  eps_cagr_3y?: number | null;
  eps_cagr_5y?: number | null;
  revenue_cagr_3y?: number | null;
  revenue_cagr_5y?: number | null;
  net_margin_current?: number | null;
  operating_margin_trend?: "expanding" | "stable" | "contracting" | null;
  revenue_eps_alignment?: "aligned" | "diverging" | "volatile" | null;
  eps_volatility?: number | null;
}

export interface DrawdownRisk extends RiskLayer {
  max_drawdown_1y?: number | null;
  max_drawdown_3y?: number | null;
  max_drawdown_5y?: number | null;
  beta_5y?: number | null;
  current_drawdown?: number | null;
  crisis_drawdowns?: CrisisDrawdown[] | null;
  recovery_time_days?: number | null;
}

export interface CrisisDrawdown {
  crisis_name: string;
  start_date: string;
  end_date: string;
  max_drawdown: number;
  start_value: number;
  end_value: number;
}

export interface ScenarioResult {
  scenario: string;
  probability: number;
  eps_growth: number;
  exit_pe: number;
  future_eps: number;
  future_value: number;
  total_return: number;
  downside: number;
}

export interface BearCase {
  eps_growth_assumption: number;
  exit_pe_ratio: number;
  future_value: number;
  current_price: number;
  downside_pct: number;
}

export interface CompositeScore {
  score: number;
  category: RiskCategory;
  maximum_expected_loss_pct: number;
  bear_case: BearCase;
}

export interface RiskDataQuality {
  data_sources: string;
  fiscal_year_end?: number | null;
  days_since_update?: number | null;
  fallbacks_used: boolean;
  last_computed_at: string;
}

export interface RiskAiNarrative {
  narrative: string;
  model: string;
  generated_at: string;
  generation_time_ms?: number | null;
}

export interface RiskAssessmentResponse {
  symbol: string;
  company_id: number;
  currency: string;
  composite: CompositeScore;
  layers: Record<LayerName, RiskLayer>;
  scenarios?: ScenarioResult[] | null;
  ai_narrative?: RiskAiNarrative | null;
  data_quality: RiskDataQuality;
}
```

### 3.2 Frontend Class Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     RiskAssessmentResponse                          │
│                     (TypeScript Interface)                          │
├─────────────────────────────────────────────────────────────────────┤
│ symbol: string                                                      │
│ company_id: number                                                   │
│ currency: string                                                    │
│ composite: CompositeScore                                           │
│ layers: Record<LayerName, RiskLayer>                                │
│ scenarios: ScenarioResult[] | null                                  │
│ ai_narrative: RiskAiNarrative | null                                 │
│ data_quality: RiskDataQuality                                        │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
          ┌─────────────┼──────────────────┐
          ▼             ▼                  ▼
┌─────────────────┐ ┌─────────────┐ ┌──────────────────┐
│ CompositeScore  │ │  RiskLayer  │ │  ScenarioResult  │
├─────────────────┤ │  (extends)  │ ├──────────────────┤
│ score: number   │ └──────┬──────┘ │ scenario: string │
│ category: string│        │        │ probability: num │
│ maximum_expected_loss_pct: number  │   ┌────┼────┐   │ total_return: num │
│ bear_case        │   │    │    │   │ downside: number │
└─────────────────┘   ▼    ▼    ▼   └──────────────────┘
               ┌──────┐ ┌────┐ ┌──────┐
               │Business│ │Bala│ │Valua.│  ...
               │Fragilit│ │nce │ │Comp. │
               │y       │ │Shee│ │      │
               └────────┘ └────┘ └──────┘

┌──────────────────────────────────────────────────────┐
│                  RiskPanel (Component)                │
├──────────────────────────────────────────────────────┤
│ Props: { symbol: string }                            │
│                                                      │
│ Local state:                                         │
│ - recomputing: boolean                               │
│ - showDiagnostics: boolean                           │
│ - expandedLayer: LayerName | null                    │
├──────────────────────────────────────────────────────┤
│ Renders:                                             │
│ - HeroSection (ScoreRing + MEL + BearCase)           │
│ - LayerCardGrid (5 cards, 2+3 layout)                │
│   - BusinessFragilityCard (with moat badge)          │
│   - BalanceSheetCard                                 │
│   - ValuationCompressionCard (with percentile gauge) │
│   - EarningsStressCard                               │
│   - DrawdownRiskCard                                 │
│ - ScenarioSection (4 scenario cards)                 │
│ - AiNarrativeSection (expandable)                    │
│ - DataQualityFooter                                  │
└──────────────────────┬───────────────────────────────┘
                       │ uses
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌─────────────────┐ ┌──────────┐ ┌──────────────────┐
│  useRiskAssessment│ │RiskServi│ │  Shared UI        │
│  (Hook)          │ │ce       │ │  Components       │
├─────────────────┤ ├──────────┤ ├──────────────────┤
│ Returns:         │ │ fetchRisk│ │ ScoreRing         │
│ data, loading,   │ │ Assess.. │ │ LayerCard         │
│ error, notComp,  │ │ fetchRisk│ │ MetricRow         │
│ recompute        │ │ AiNarr.. │ │ StatusBadge       │
│ generateAi       │ │ generate│ │ ScenarioCard      │
└─────────────────┘ │ RiskAi.. │ │ AiNarrativeBlock  │
                    └──────────┘ └──────────────────┘
```

### 3.3 Service Layer

#### File: `web/src/features/analysis/services/analysis.service.ts`

Add following the existing two-function pattern:

```typescript
// ── Risk Assessment ──

export type RiskCachedOutcome =
  | { status: "ok"; payload: RiskAssessmentResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

export async function fetchRiskCached(symbol: string): Promise<RiskCachedOutcome> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/risk-assessment`);
  let res: Response;
  try { res = await doFetch(url, { method: "GET" }); }
  catch (err: any) { return { status: "error", message: err?.message || "Network error." }; }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<RiskAssessmentResponse>(res);
    if (!body || !body.composite) return { status: "error", message: "Invalid response.", httpStatus: 502 };
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return { status: "error", message: (errorBody?.detail as string) || `Failed with status ${res.status}`, httpStatus: res.status };
}

export async function fetchRiskAssessment(symbol: string, options?: { force?: boolean }): Promise<RiskAssessmentResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/risk-assessment${qs}`);
  let res: Response;
  try { res = await doFetch(url, { method: "GET" }); }
  catch (err: any) { throw new Error(err?.message || "Network error."); }
  if (res.ok) {
    const body = await readJsonSafe<RiskAssessmentResponse>(res);
    if (!body || !body.composite) throw new Error("Invalid response.");
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error((errorBody?.detail as string) || `Failed with status ${res.status}`);
}

export async function fetchRiskAiNarrative(symbol: string): Promise<{ narrative: string; model: string }> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/risk-assessment/ai`);
  let res: Response;
  try { res = await doFetch(url, { method: "POST" }); }
  catch (err: any) { throw new Error(err?.message || "Network error."); }
  if (res.ok) {
    const body = await readJsonSafe<{ narrative: string; model: string }>(res);
    if (!body || !body.narrative) throw new Error("Invalid response.");
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error((errorBody?.detail as string) || `Failed with status ${res.status}`);
}
```

### 3.4 Query Key

```typescript
// In web/src/lib/query-keys.ts
QK.riskAssessment = (symbol: string) => ["analysis", "risk-assessment", symbol.toUpperCase()] as const,
```

### 3.5 React Query Hook

#### File: `web/src/features/analysis/hooks/useRiskAssessment.ts`

```typescript
"use client";

import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { fetchRiskCached, fetchRiskAssessment, fetchRiskAiNarrative } from "../services/analysis.service";
import type { RiskAssessmentResponse } from "../types/analysis.types";

export type RiskQueryData =
  | { notComputed: true }
  | (RiskAssessmentResponse & { notComputed: false });

export async function riskQueryFn(symbol: string): Promise<RiskQueryData> {
  const outcome = await fetchRiskCached(symbol);
  if (outcome.status === "not_computed") return { notComputed: true };
  if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
  throw new Error(outcome.message || "Failed to load risk assessment.");
}

export function useRiskAssessment(symbol: string) {
  const upperSymbol = (symbol ?? "").toUpperCase();
  const queryClient = useQueryClient();

  const { data, isPending, error } = useQuery<RiskQueryData, Error>({
    queryKey: QK.riskAssessment(upperSymbol),
    queryFn: () => riskQueryFn(upperSymbol),
    enabled: !!upperSymbol,
    staleTime: STALE.VALUATION,
    gcTime: GC.VALUATION,
    retry: 1,
  });

  const recompute = useCallback(async (): Promise<void> => {
    if (!upperSymbol) return;
    const fresh = await fetchRiskAssessment(upperSymbol, { force: true });
    queryClient.setQueryData<RiskQueryData>(QK.riskAssessment(upperSymbol), {
      ...fresh,
      notComputed: false,
    });
  }, [upperSymbol, queryClient]);

  const generateAi = useCallback(async (): Promise<void> => {
    if (!upperSymbol) return;
    const result = await fetchRiskAiNarrative(upperSymbol);
    // Update the AI narrative in the cached data
    queryClient.setQueryData<RiskQueryData>(QK.riskAssessment(upperSymbol), (old) => {
      if (!old || old.notComputed) return old;
      return {
        ...old,
        ai_narrative: {
          narrative: result.narrative,
          model: result.model,
          generated_at: new Date().toISOString(),
        },
        notComputed: false,
      };
    });
  }, [upperSymbol, queryClient]);

  const notComputed = data?.notComputed ?? false;
  const responseData = notComputed ? null : (data as RiskAssessmentResponse & { notComputed: false }) ?? null;

  return {
    data: responseData,
    loading: isPending,
    error: error?.message ?? null,
    notComputed,
    recompute,
    generateAi,
  };
}
```

### 3.6 UI Component

#### File: `web/src/features/analysis/components/risk-panel.tsx`

```
┌─────────────────────────────────────────────────────────────┐
│                    RiskPanel                                 │
├─────────────────────────────────────────────────────────────┤
│  STATE: loading                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  [Skeleton] Hero Ring  [Skeleton] MEL Badge          │   │
│  │  [Skeleton] Layer Cards (5x shimmer)                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  STATE: notComputed                                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  "Risk assessment not yet run for {symbol}"           │   │
│  │  [ Run Analysis ]  button                             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  STATE: error                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ⚠ {error message}                                  │   │
│  │  [ Retry ] button                                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  STATE: data loaded                                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ┌────────────────────┐  ┌────────────────────┐      │   │
│  │  │  Composite Score   │  │  Maximum Expected  │      │   │
│  │  │  [ScoreRing 85]    │  │  Loss: 12%         │      │   │
│  │  │  "Moderate"        │  │  Bear Case: -16%   │      │   │
│  │  └────────────────────┘  └────────────────────┘      │   │
│  │                                                       │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │   │
│  │  │ Business     │ │ Balance      │ │ Valuation    │  │   │
│  │  │ Fragility    │ │ Sheet        │ │ Compression  │  │   │
│  │  │ 8.2 / 10     │ │ 9.1 / 10     │ │ 6.5 / 10     │  │   │
│  │  │ Moat: Wide   │ │ D/E: 0.2    │ │ P/E pctl: 75│  │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘  │   │
│  │  ┌──────────────┐ ┌──────────────┐                   │   │
│  │  │ Earnings     │ │ Drawdown     │                   │   │
│  │  │ Stress       │ │ Risk         │                   │   │
│  │  │ 7.8 / 10     │ │ 7.0 / 10     │                   │   │
│  │  │ EPS CAGR:15% │ │ Max DD:-38%  │                   │   │
│  │  └──────────────┘ └──────────────┘                   │   │
│  │                                                       │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │  Scenario Modeling (Bull/Base/Bear/Severe)   │    │   │
│  │  │  [ScenarioCard] [ScenarioCard] ...           │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  │                                                       │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │  AI Summary (expandable) [Regenerate]        │    │   │
│  │  │  "Microsoft shows fortress-level..."         │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  │                                                       │   │
│  │  Data Quality: database | 3 fallbacks used           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.7 Tab Wiring

**File: `web/src/app/(authenticated)/analysis/[symbol]/page.tsx`**

Add to `TOP_TABS`:
```typescript
{ id: "risk", label: "Risk Assessment", icon: AlertTriangle },
```

Add to tab rendering (alongside existing tabs):
```typescript
{tab === "risk" && (
  <div className="space-y-6 animate-fade-up">
    <RiskPanel symbol={upperSymbol} />
  </div>
)}
```

**File: `web/src/lib/query-keys.ts`** — already covered in §3.4.

**File: `web/src/features/analysis/utils/prefetch-valuations.ts`** — add:
```typescript
queryClient.prefetchQuery({
  queryKey: QK.riskAssessment(upper),
  queryFn: () => riskQueryFn(upper),
  staleTime: STALE.VALUATION,
  gcTime: GC.VALUATION,
});
```

---

## 4. Sequence Diagrams

### 4.1 SD-1: Page Load → Prefetch → Data Display

```
┌────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
│ Browser │   │ page.tsx     │   │ useRiskAs- │   │ RiskService  │   │ Backend  │   │ Supabase │
│         │   │ [symbol]     │   │ sessment   │   │ (frontend)   │   │ FastAPI  │   │          │
└────┬────┘   └──────┬───────┘   └──────┬─────┘   └──────┬───────┘   └────┬─────┘   └────┬─────┘
     │               │                  │                │                │              │
     │  click "Risk" │                  │                │                │              │
     │──────────────>│                  │                │                │              │
     │               │                  │                │                │              │
     │               │ useEffect:       │                │                │              │
     │               │ prefetchAllValuations()           │                │              │
     │               │─────────────────────────────────>│                │              │
     │               │                  │                │                │              │
     │               │                  │  useQuery()    │                │              │
     │               │                  │  QK.risk       │                │              │
     │               │                  │────────────────>│               │              │
     │               │                  │                │                │              │
     │               │                  │ fetchRiskCached(symbol)        │              │
     │               │                  │                │──────────────>│              │
     │               │                  │                │   GET /risk-assessment        │
     │               │                  │                │                │              │
     │               │                  │                │                │  supabase    │
     │               │                  │                │                │  queries     │
     │               │                  │                │                │─────────────>│
     │               │                  │                │                │              │
     │               │                  │                │                │  ratios,     │
     │               │                  │                │                │  prices,     │
     │               │                  │                │                │  moat data   │
     │               │                  │                │                │<─────────────│
     │               │                  │                │                │              │
     │               │                  │                │                │ Compute 5    │
     │               │                  │                │                │ layers,      │
     │               │                  │                │                │ composite,   │
     │               │                  │                │                │ scenarios    │
     │               │                  │                │                │              │
     │               │                  │                │  RiskResponse  │              │
     │               │                  │                │<──────────────│              │
     │               │                  │                │                │              │
     │               │                  │  cached by     │                │              │
     │               │                  │  React Query   │                │              │
     │               │                  │<───────────────│                │              │
     │               │                  │                │                │              │
     │               │                  │  {data,loading │                │              │
     │               │                  │   =false}      │                │              │
     │               │                  │────────────────>│               │              │
     │               │                  │                │                │              │
     │               │  <RiskPanel />   │                │                │              │
     │               │  renders with    │                │                │              │
     │               │  all 5 layer     │                │                │              │
     │               │  cards + hero    │                │                │              │
     │<──────────────│                  │                │                │              │
     │               │                  │                │                │              │
```

### 4.2 SD-2: Force Recompute (User clicks "Run Analysis")

```
┌────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐
│ Browser │   │  RiskPanel   │   │ useRiskAss-  │   │ RiskService│   │ Backend      │
│         │   │              │   │ essment      │   │ (frontend) │   │ FastAPI      │
└────┬────┘   └──────┬───────┘   └──────┬───────┘   └─────┬──────┘   └──────┬───────┘
     │               │                  │                  │                │
     │  [Run Analysis]                  │                  │                │
     │──────────────>│                  │                  │                │
     │               │                  │                  │                │
     │               │  recompute()     │                  │                │
     │               │─────────────────>│                  │                │
     │               │                  │                  │                │
     │               │                  │  fetchRiskAssessment(sym, {force: true})
     │               │                  │─────────────────>│                │
     │               │                  │                  │  GET /risk-assessment?force=true
     │               │                  │                  │───────────────>│
     │               │                  │                  │                │
     │               │                  │                  │                │
     │               │                  │                  │  [Same backend flow as SD-1,
     │               │                  │                  │   but bypasses any in-memory
     │               │                  │                  │    cache and recomputes]
     │               │                  │                  │                │
     │               │                  │                  │  RiskResponse  │
     │               │                  │                  │<───────────────│
     │               │                  │                  │                │
     │               │                  │  setQueryData()  │                │
     │               │                  │  updates React  │                │
     │               │                  │  Query cache    │                │
     │               │<─────────────────│                  │                │
     │               │                  │                  │                │
     │               │  Re-renders with │                  │                │
     │               │  fresh data,     │                  │                │
     │               │  shows metrics   │                  │                │
     │<──────────────│                  │                  │                │
```

### 4.3 SD-3: AI Summary Generation

```
┌────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────────┐
│ Browser │   │  RiskPanel   │   │ useRiskAss-  │   │ RiskService│   │ Backend          │
│         │   │              │   │ essment      │   │ (frontend) │   │ FastAPI + OpenRouter
└────┬────┘   └──────┬───────┘   └──────┬───────┘   └─────┬──────┘   └────────┬─────────┘
     │               │                  │                  │                  │
     │  [Generate AI Summary]           │                  │                  │
     │──────────────>│                  │                  │                  │
     │               │                  │                  │                  │
     │               │  Show loading    │                  │                  │
     │               │  state on button │                  │                  │
     │               │                  │                  │                  │
     │               │  generateAi()    │                  │                  │
     │               │─────────────────>│                  │                  │
     │               │                  │                  │                  │
     │               │                  │ fetchRiskAiNarrative(sym)          │
     │               │                  │─────────────────>│                  │
     │               │                  │                  │ POST /risk-assessment/ai
     │               │                  │                  │─────────────────>│
     │               │                  │                  │                  │
     │               │                  │                  │  Build prompt   │
     │               │                  │                  │  with:          │
     │               │                  │                  │  - layer scores │
     │               │                  │                  │  - key metrics  │
     │               │                  │                  │  - moat data    │
     │               │                  │                  │  - bear case    │
     │               │                  │                  │                  │
     │               │                  │                  │  POST OpenRouter│
     │               │                  │                  │─────────────────>│
     │               │                  │                  │                  │
     │               │                  │                  │  AI response    │
     │               │                  │                  │<────────────────│
     │               │                  │                  │                  │
     │               │                  │                  │  Cache result   │
     │               │                  │                  │  in DB          │
     │               │                  │                  │                  │
     │               │                  │  {narrative,     │                  │
     │               │                  │   model}         │                  │
     │               │                  │<─────────────────│                  │
     │               │                  │                  │                  │
     │               │                  │  setQueryData()  │                  │
     │               │                  │  patches ai     │                  │
     │               │                  │  Narrative in   │                  │
     │               │                  │  cached response│                  │
     │               │                  │                  │                  │
     │               │  Re-renders with │                  │                  │
     │               │  AI narrative    │                  │                  │
     │               │  text visible    │                  │                  │
     │<──────────────│                  │                  │                  │
```

### 4.4 SD-4: Error Flow (Backend Exception)

```
┌────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────┐
│ Browser │   │  RiskPanel   │   │ useRiskAss-  │   │ RiskService│   │ Backend      │   │ Supabase │
│         │   │              │   │ essment      │   │ (frontend) │   │ FastAPI      │   │          │
└────┬────┘   └──────┬───────┘   └──────┬───────┘   └─────┬──────┘   └──────┬───────┘   └────┬─────┘
     │               │                  │                  │                │              │
     │  Load page    │                  │                  │                │              │
     │──────────────>│                  │                  │                │              │
     │               │  useQuery fires  │                  │                │              │
     │               │─────────────────>│                  │                │              │
     │               │                  │ fetchRiskCached  │                │              │
     │               │                  │─────────────────>│                │              │
     │               │                  │                  │  GET request   │              │
     │               │                  │                  │───────────────>│              │
     │               │                  │                  │                │              │
     │               │                  │                  │  Query fails   │              │
     │               │                  │                  │  (e.g. Supabase│              │
     │               │                  │                  │   timeout)     │              │
     │               │                  │                  │<───────────────│              │
     │               │                  │                  │                │              │
     │               │                  │                  │  Exception →   │              │
     │               │                  │                  │  500 Internal  │              │
     │               │                  │                  │  Server Error  │              │
     │               │                  │                  │                │              │
     │               │                  │  {status:"error",│                │              │
     │               │                  │   message:"Risk  │                │              │
     │               │                  │   assessment     │                │              │
     │               │                  │   failed."}      │                │              │
     │               │                  │<─────────────────│                │              │
     │               │                  │                  │                │              │
     │               │                  │  useQuery        │                │              │
     │               │                  │  returns error   │                │              │
     │               │<─────────────────│                  │                │              │
     │               │                  │                  │                │              │
     │               │  Renders error   │                  │                │              │
     │               │  banner:         │                  │                │              │
     │               │  "⚠ Risk assessment│                │                │              │
     │               │   failed. [Retry]"│                 │                │              │
     │               │                  │                  │                │              │
     │               │  User clicks     │                  │                │              │
     │               │  [Retry]         │                  │                │              │
     │               │─────────────────>│                  │                │              │
     │               │                  │  refetch()       │                │              │
     │               │                  │  (React Query    │                │              │
     │               │                  │   auto-retry)    │                │              │
     │               │                  │─────────────────>│                │              │
     │               │                  │                  │  Same GET flow │              │
     │               │                  │                  │  as SD-1       │              │
     │               │                  │                  │                │              │
```

---

## 5. Test Plans

### 5.1 Backend Unit Tests

#### File: `backend/tests/test_risk_assessment_service.py`

```
TEST SUITE: RiskAssessmentService
======================================

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B1: Constructor & Dependency Injection                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock RiskRepository, MoatAnalysisService, MoatWaccService            │
│ When:  RiskAssessmentService constructed                                   │
│ Then:  All dependencies stored correctly                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B2: get_risk_assessment — Happy Path (all data available)                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock repo returns valid company context, ratios, prices, income      │
│        Mock moat service returns valid MoatResponse                         │
│ When:  get_risk_assessment("AAPL") called                                  │
│ Then:  Returns RiskAssessmentResponse                                       │
│        composite.score is float 0-100                                       │
│        composite.category is valid RiskCategory                             │
│        composite.maximum_expected_loss_pct is float                            │
│        layers contains all 5 LayerName keys                                 │
│        each layer has score 0-10, valid severity, metrics list non-empty    │
│        bear_case has downside_pct <= 0                                       │
│        data_quality.data_sources is set                                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B3: get_risk_assessment — Unknown Symbol                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock repo.get_company_context returns None                           │
│ When:  get_risk_assessment("UNKNOWN") called                                │
│ Then:  Raises ValueError with "not found"                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B4: get_risk_assessment — Partial Ratios (null values)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock repo returns ratios with null roic, null margins               │
│        Moat service returns None                                            │
│ When:  get_risk_assessment("AAPL") called                                   │
│ Then:  Response returned (no exception)                                     │
│        BusinessFragility.moat_score is None                                 │
│        BusinessFragility.score is computed from available metrics only      │
│        data_quality.fallbacks_used = True                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B5: get_risk_assessment — Empty Price History                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock repo returns empty price_history list                           │
│ When:  get_risk_assessment("AAPL") called                                   │
│ Then:  DrawdownRisk.max_drawdown_5y is None                                 │
│        DrawdownRisk.crisis_drawdowns is None or empty                       │
│        Other layers unaffected                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B6: _analyze_business_fragility — With Valid Moat Data                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: MoatAnalysisService returns moat_score=85, category="Wide"           │
│        Sector = "Technology"                                                │
│ When:  _analyze_business_fragility called                                   │
│ Then:  moat_score = 85                                                      │
│        moat_category = "Wide"                                               │
│        "Moat Durability" metric has status "pass"                           │
│        recurrence_classification is computed from sector                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B7: _analyze_business_fragility — With Null Moat Data                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: MoatAnalysisService returns None (not computed)                      │
│ When:  _analyze_business_fragility called                                   │
│ Then:  moat_score is None                                                   │
│        moat_category is None                                                │
│        "Moat Durability" metric has status "na"                             │
│        Layer score is computed from remaining metrics only                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B8: _analyze_balance_sheet — Debt/EBITDA Thresholds                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Test each threshold:                                                        │
│   debt_to_ebitda = 0.5  → status "pass", metric value 0.5                  │
│   debt_to_ebitda = 2.5  → status "pass", metric value 2.5                  │
│   debt_to_ebitda = 4.5  → status "caution", metric value 4.5               │
│   debt_to_ebitda = 7.0  → status "fail", metric value 7.0                  │
│   debt_to_ebitda = None → status "na"                                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B9: _analyze_valuation_compression — Percentile Computation              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock company_summary history with 1000 rows of P/E data              │
│        Current P/E at 75th percentile value                                 │
│ When:  _analyze_valuation_compression called                                │
│ Then:  pe_percentile ≈ 75 (±2)                                              │
│        pe_5y_min = min of historical values                                 │
│        pe_5y_max = max of historical values                                 │
│        pe_5y_median = median of historical values                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B10: _analyze_valuation_compression — Sparse Data (< 2 rows)             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock company_summary with only 1 row                                 │
│ When:  _analyze_valuation_compression called                                │
│ Then:  pe_percentile = 50 (neutral default)                                 │
│        pe_5y_min = pe_5y_max = pe_5y_median = that single value            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B11: _analyze_earnings_stress — CAGR Computation                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock income_statements with 5 years of EPS data                      │
│        EPS: 1.00, 1.15, 1.32, 1.52, 1.75 (15% CAGR)                        │
│ When:  _analyze_earnings_stress called                                      │
│ Then:  eps_cagr_5y ≈ 0.15 (±0.01)                                          │
│        eps_cagr_3y ≈ 0.15 (±0.01)                                          │
│        revenue_cagr values computed similarly                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B12: _analyze_drawdown_risk — Max Drawdown                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock price_history with known peak $200 → trough $120 → $180        │
│ When:  _analyze_drawdown_risk called                                        │
│ Then:  max_drawdown_5y ≈ -0.40 (($120-$200)/$200)                          │
│        current_drawdown differs from max drawdown                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B13: _analyze_drawdown_risk — Crisis Periods                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock price_history spanning COVID crash period                       │
│ When:  _analyze_drawdown_risk called                                        │
│ Then:  crisis_drawdowns has at least 1 entry for COVID Crash (2020)         │
│        crisis_drawdowns[0].max_drawdown matches computed from window        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B14: _compute_composite — Weighted Scoring                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: All 5 layers with specific scores:                                   │
│        BF=8, BS=9, VC=6, ES=7, DR=8                                        │
│        Weights: BF=0.20, BS=0.25, VC=0.20, ES=0.25, DR=0.10               │
│ When:  _compute_composite called                                            │
│ Then:  Composite = 8*0.20 + 9*0.25 + 6*0.20 + 7*0.25 + 8*0.10             │
│               = 1.6 + 2.25 + 1.20 + 1.75 + 0.80 = 7.60                     │
│        score = 7.60 * 10 = 76 (mapped to 0-100)                            │
│        Verify category mapping (76 → "Moderate")                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B15: _compute_scenarios — Bear Case Downside                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Current EPS = $10, Current Price = $200                              │
│        Bear scenario: eps_growth=0.02, exit_pe=15, prob=0.20               │
│        Severe scenario: eps_growth=0.00, exit_pe=12, prob=0.05             │
│ When:  _compute_scenarios called                                            │
│ Then:  Bear future_eps = 10 * (1.02)^5 = 11.04                              │
│        Bear future_value = 11.04 * 15 = 165.62                              │
│        Bear total_return = (165.62/200) - 1 = -0.172                        │
│        Bear downside = -0.172                                               │
│        Expected return = sum(p * total_return) across all scenarios         │
│        MEL = worst weighted downside                                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B16: _score_to_severity — Threshold Mapping                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ score 9-10 → "low"                                                          │
│ score 7-8.9 → "moderate"                                                    │
│ score 5-6.9 → "elevated"                                                    │
│ score 3-4.9 → "high"                                                        │
│ score 0-2.9 → "severe"                                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B17: generate_ai_narrative — Happy Path                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: RiskAssessmentResponse fully populated                               │
│        Mock httpx client returns valid OpenRouter response                  │
│ When:  generate_ai_narrative called                                         │
│ Then:  Returns RiskAiNarrative with non-empty narrative                     │
│        model = "openrouter/default"                                         │
│        generated_at is ISO timestamp                                        │
│        generation_time_ms is set                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-B18: generate_ai_narrative — API Failure                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Mock httpx client raises Exception                                  │
│ When:  generate_ai_narrative called                                         │
│ Then:  Returns RiskAiNarrative with fallback error message                  │
│        No exception propagates                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Backend Integration Tests

#### File: `backend/tests/test_risk_api_endpoints.py`

```
TEST SUITE: Risk Assessment API Endpoints
=============================================

┌─────────────────────────────────────────────────────────────────────────────┐
│ IT-B1: GET /analysis/{symbol}/risk-assessment — 200 OK                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Valid symbol "AAPL" in database                                      │
│ When:  GET /analysis/AAPL/risk-assessment                                   │
│ Then:  Status 200                                                            │
│        Response matches RiskAssessmentResponse shape                        │
│        composite.score is present                                           │
│        layers has 5 entries                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ IT-B2: GET /analysis/{symbol}/risk-assessment — 404 Unknown Symbol          │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Invalid symbol "ZZZZZ"                                               │
│ When:  GET /analysis/ZZZZZ/risk-assessment                                  │
│ Then:  Status 404                                                           │
│        detail contains "not found"                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┤
│ IT-B3: GET /analysis/{symbol}/risk-assessment?force=true — Force Recompute  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Valid symbol with existing cached analysis                           │
│ When:  GET /analysis/AAPL/risk-assessment?force=true                        │
│ Then:  Status 200                                                           │
│        computed_at in response is recent (within last 10 seconds)           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ IT-B4: POST /analysis/{symbol}/risk-assessment/ai — 200 OK                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Valid symbol with existing risk assessment                           │
│ When:  POST /analysis/AAPL/risk-assessment/ai                               │
│ Then:  Status 200                                                           │
│        Response has "narrative" (non-empty string)                          │
│        Response has "model" (non-empty string)                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ IT-B5: Rate Limiting — 429 Too Many Requests                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: 31 rapid requests to /analysis/AAPL/risk-assessment (limit=30/min)  │
│ When:  31st request sent                                                    │
│ Then:  Status 429                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ IT-B6: Unauthenticated — 401                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: No auth token in request                                             │
│ When:  GET /analysis/AAPL/risk-assessment                                   │
│ Then:  Status 401                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Frontend Unit Tests

#### File: `web/src/__tests__/RiskPanel.test.tsx`

```
TEST SUITE: RiskPanel Component
=====================================

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F1: Render Loading Skeleton                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useRiskAssessment returns {loading: true, data: null}               │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  Skeleton/shimmers visible                                           │
│        No metric text displayed                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F2: Render Not Computed State with Run Button                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useRiskAssessment returns {notComputed: true, loading: false}       │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  "Risk assessment not yet run" text visible                          │
│        "Run Analysis" button visible                                        │
│        Clicking button calls recompute()                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F3: Render Error Banner with Retry                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useRiskAssessment returns {error: "Failed to load", data: null}     │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  Error message "Failed to load" visible in banner                    │
│        Retry button visible                                                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F4: Render Full Data — Hero Section                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useRiskAssessment returns full data with composite score 85         │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  ScoreRing visible with score                                        │
│        MEL displayed prominently                                           │
│        Bear case downside shown                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F5: Render Full Data — All 5 Layer Cards                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useRiskAssessment returns full data with all 5 layers               │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  5 layer cards visible with correct titles:                          │
│        "Business Fragility", "Balance Sheet", "Valuation Compression",      │
│        "Earnings Stress", "Drawdown Risk"                                   │
│        Each card shows score and severity badge                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F6: Business Fragility Card Shows Moat Badge                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with moat_category = "Wide", moat_score = 85              │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  Moat badge visible with "Wide" text                                  │
│        ROIC spread displayed                                                │
│        Sector classification shown                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F7: Balance Sheet Card Shows Debt/EBITDA                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with balance_sheet.debt_to_ebitda = 0.2                     │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  Debt/EBITDA row visible with value 0.2                              │
│        Interest Coverage row visible                                        │
│        Status indicator (pass/caution/fail) shown                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F8: Valuation Card Shows Percentile Gauge                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with pe_percentile = 75                                    │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  P/E percentile gauge visible                                        │
│        EV/EBITDA percentile visible                                        │
│        PEG ratio displayed                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F9: Earnings Stress Card Shows CAGRs                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with eps_cagr_5y = 0.15                                     │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  EPS CAGR (5y) visible with formatted percentage                     │
│        Revenue CAGR visible                                                 │
│        Margin trend indicator shown                                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F10: Drawdown Card Shows Max Drawdown                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with max_drawdown_5y = -0.38                                │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  Max Drawdown (5y) visible as "−38%"                                 │
│        Beta visible                                                         │
│        Crisis drawdown labels visible (if present)                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F11: Scenario Cards Rendered                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with 4 scenarios (bull/base/bear/severe)                  │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  4 scenario cards visible                                            │
│        Each shows scenario name, probability, total return                 │
│        Bear and Severe cards show downside highlighted                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F12: AI Narrative Section — Collapsible                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with ai_narrative present                                  │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  AI summary section visible with narrative text                      │
│        "Regenerate" button visible                                         │
│        Clicking "Regenerate" calls generateAi()                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F13: AI Narrative Section — Empty State                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with ai_narrative = null                                   │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  "Generate AI Summary" button visible (not "Regenerate")            │
│        No narrative text displayed                                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F14: Data Quality Footer                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: Full data with data_quality.data_sources = "database"                 │
│        data_quality.fallbacks_used = false                                    │
│ When:  <RiskPanel symbol="AAPL" /> rendered                                │
│ Then:  Footer visible with data source label                                │
│        "No fallbacks used" text shown                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-F15: Computed State — Recompute Button Loading                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useRiskAssessment returns full data                                 │
│        recompute is an async function                                       │
│ When:  User clicks "Recompute" in header                                   │
│ Then:  Button shows spinner during recompute                                │
│        After recompute completes, button returns to normal                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.4 Frontend Hook Tests

#### File: `web/src/__tests__/useRiskAssessment.test.ts`

```
TEST SUITE: useRiskAssessment Hook
=======================================

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-FH1: Returns loading state on initial fetch                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: useQuery returns isPending=true                                      │
│ Then:  loading=true, data=null, error=null, notComputed=false               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-FH2: Returns notComputed on 404                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: fetchRiskCached returns {status:"not_computed"}                     │
│ Then:  notComputed=true, data=null                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-FH3: Returns parsed data on success                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: fetchRiskCached returns {status:"ok", payload: riskResponse}        │
│ Then:  notComputed=false                                                    │
│        data matches riskResponse                                            │
│        data.notComputed = false                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-FH4: recompute() updates cache                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: fetchRiskAssessment returns fresh data                               │
│ When:  recompute() called                                                   │
│ Then:  setQueryData called with new data                                    │
│        notComputed becomes false                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ UT-FH5: generateAi() patches AI narrative into cache                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ Given: fetchRiskAiNarrative returns {narrative, model}                     │
│        Current cached data has ai_narrative = null                          │
│ When:  generateAi() called                                                  │
│ Then:  setQueryData called with updater function                            │
│        Updated data has ai_narrative.narrative = returned narrative          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.5 End-to-End Test Scenarios

```
TEST SUITE: Risk Assessment E2E
====================================

┌─────────────────────────────────────────────────────────────────────────────┐
│ E2E-1: Full Page Load — Navigate to Risk Tab                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Steps:                                                                      │
│ 1. Navigate to /analysis/AAPL                                              │
│ 2. Click "Risk Assessment" tab                                             │
│ 3. Wait for data to load                                                    │
│                                                                             │
│ Asserts:                                                                    │
│ - Composite score ring gauge is visible and shows a number                  │
│ - MEL percentage is visible                                                 │
│ - 5 layer cards are visible (Business Fragility, Balance Sheet, etc.)      │
│ - Each card shows a score and status badge                                  │
│ - AI Summary section is present (with either content or generate button)   │
│ - Data quality footer is visible                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ E2E-2: First-Time Visit — Not Computed → Run Analysis                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Steps:                                                                      │
│ 1. Navigate to /analysis/AAPL for a symbol never computed                  │
│ 2. Click "Risk Assessment" tab                                             │
│ 3. See "Not yet computed" state                                            │
│ 4. Click "Run Analysis"                                                     │
│ 5. Wait for backend to compute and return data                              │
│                                                                             │
│ Asserts:                                                                    │
│ - Loading state shown during computation                                    │
│ - After completion, full metrics display replaces "Not yet computed"        │
│ - Composite score is displayed                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ E2E-3: Force Recompute — Click Recompute Button                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Steps:                                                                      │
│ 1. Navigate to /analysis/AAPL with existing cached analysis                │
│ 2. Click "Recompute" button in header                                       │
│ 3. Wait for data to refresh                                                 │
│                                                                             │
│ Asserts:                                                                    │
│ - Button shows loading spinner during recompute                             │
│ - Data updates after recompute completes                                    │
│ - computed_at timestamp is recent                                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ E2E-4: Generate AI Summary                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Steps:                                                                      │
│ 1. Navigate to /analysis/AAPL with existing risk assessment               │
│ 2. Click "Generate AI Summary" (or "Regenerate")                           │
│ 3. Wait for AI generation                                                  │
│                                                                             │
│ Asserts:                                                                    │
│ - Loading state shown during generation                                     │
│ - AI narrative text appears after generation                                │
│ - Button text changes from "Generate" to "Regenerate"                       │
│ - Narrative references metrics from the assessment                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ E2E-5: Error Recovery — Backend Down                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Steps:                                                                      │
│ 1. Simulate backend error (stop API server)                                │
│ 2. Navigate to /analysis/AAPL → Risk tab                                   │
│ 3. See error banner                                                        │
│ 4. Restart API server                                                       │
│ 5. Click "Retry"                                                            │
│                                                                             │
│ Asserts:                                                                    │
│ - Error banner displays "Risk assessment failed" message                   │
│ - Retry button is visible                                                   │
│ - After retry, data loads successfully                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ E2E-6: Cross-Tab Moat Evidence                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Steps:                                                                      │
│ 1. Navigate to /analysis/AAPL → "Moat" tab first                            │
│ 2. Run moat analysis and verify moat score                                 │
│ 3. Switch to "Risk Assessment" tab                                         │
│ 4. Verify Business Fragility card shows same moat score/category           │
│                                                                             │
│ Asserts:                                                                    │
│ - Moat score matches between tabs                                          │
│ - No additional moat computation needed (cached data reused)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.6 Test Fixtures

#### Backend Conftest (`backend/tests/conftest.py` additions):

```python
@pytest.fixture
def mock_risk_repo():
    """Mock RiskRepository with all methods returning sensible defaults."""
    repo = MagicMock(spec=RiskRepository)
    repo.get_company_context = MagicMock(return_value={
        "company_id": 1, "symbol": "AAPL", "sector": "Technology",
        "industry": "Consumer Electronics", "currency": "USD",
    })
    repo.get_latest_financial_ratios = AsyncMock(return_value={
        "roic": 0.35, "gross_margin": 0.45, "operating_margin": 0.30,
        "net_margin": 0.25, "debt_to_ebitda": 0.5,
        "interest_coverage": 25.0, "current_ratio": 1.5,
        "debt_to_equity": 0.8, "fcf_conversion": 0.85,
    })
    repo.get_financial_ratios_history = AsyncMock(return_value=[
        {"fiscal_year": 2021, "roic": 0.30, "gross_margin": 0.44},
        {"fiscal_year": 2022, "roic": 0.32, "gross_margin": 0.44},
        {"fiscal_year": 2023, "roic": 0.33, "gross_margin": 0.45},
        {"fiscal_year": 2024, "roic": 0.34, "gross_margin": 0.45},
        {"fiscal_year": 2025, "roic": 0.35, "gross_margin": 0.45},
    ])
    repo.get_price_history_range = AsyncMock(return_value=[
        {"close_price": 150.0, "price_date": "2023-01-01"},
        {"close_price": 200.0, "price_date": "2024-01-01"},
        {"close_price": 180.0, "price_date": "2025-01-01"},
    ])
    repo.get_income_statements_annual = AsyncMock(return_value=[
        {"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps": 5.0},
        {"fiscal_year": 2023, "net_income": 150, "revenue": 1500, "eps": 7.5},
    ])
    repo.get_current_market_price = AsyncMock(return_value=200.0)
    return repo


@pytest.fixture
def mock_moat_service():
    """Mock MoatAnalysisService returning known scores."""
    svc = MagicMock(spec=MoatAnalysisService)
    svc.get_moat_analysis = AsyncMock(return_value=MagicMock(
        symbol="AAPL", company_id=1,
        valuation=MagicMock(
            moat_score=85.0, moat_category="Wide",
            roic_minus_wacc=0.15, roic=0.35, wacc=0.10,
            roic_5y_avg=0.32, roic_stability_score=90.0,
            capital_efficiency_score=85.0,
        ),
        industry_context=MagicMock(sector="Technology"),
    ))
    return svc
```

#### Frontend Test Factory (`web/src/__tests__/factories.ts`):

```typescript
export function makeRiskResponse(overrides: Partial<RiskAssessmentResponse> = {}): RiskAssessmentResponse {
  return {
    symbol: "AAPL",
    company_id: 1,
    currency: "USD",
    composite: {
      score: 76,
      category: "Moderate",
      maximum_expected_loss_pct: 12.5,
      bear_case: {
        eps_growth_assumption: 0.02,
        exit_pe_ratio: 15,
        future_value: 165.62,
        current_price: 200.0,
        downside_pct: -0.172,
      },
    },
    layers: {
      business_fragility: {
        name: "business_fragility",
        display_name: "Business Fragility",
        score: 8.2,
        category: "low",
        weight: 0.20,
        metrics: [
          { name: "Moat Durability", value: 85, label: "Wide", status: "pass", weight: 5 },
          { name: "Revenue Recurrence", label: "High", status: "pass", weight: 3 },
        ],
        moat_score: 85,
        moat_category: "Wide",
        roic_minus_wacc: 0.15,
        sector: "Technology",
        industry: "Consumer Electronics",
        recurrence_classification: "High",
        pricing_power_assessment: "Strong",
      },
      balance_sheet: {
        name: "balance_sheet",
        display_name: "Balance Sheet",
        score: 9.1,
        category: "low",
        weight: 0.25,
        metrics: [
          { name: "Debt/EBITDA", value: 0.2, label: "0.2x", status: "pass", weight: 4 },
          { name: "Interest Coverage", value: 52, label: "52.0x", status: "pass", weight: 3 },
        ],
        debt_to_ebitda: 0.2,
        interest_coverage: 52,
        current_ratio: 2.5,
        debt_to_equity: 0.5,
        fcf_stability_pct: 1.0,
      },
      valuation_compression: {
        name: "valuation_compression",
        display_name: "Valuation Compression",
        score: 6.5,
        category: "moderate",
        weight: 0.20,
        metrics: [
          { name: "P/E Percentile (5y)", value: 75, label: "75th", status: "caution", weight: 3 },
          { name: "EV/EBITDA Percentile", value: 65, label: "65th", status: "caution", weight: 3 },
        ],
        pe_current: 35,
        pe_percentile: 75,
        pe_5y_min: 20,
        pe_5y_max: 45,
        pe_5y_median: 30,
        peg_ratio: 2.1,
      },
      earnings_stress: {
        name: "earnings_stress",
        display_name: "Earnings Stress",
        score: 7.8,
        category: "low",
        weight: 0.25,
        metrics: [
          { name: "EPS CAGR (5y)", value: 0.15, label: "15%", status: "pass", weight: 3 },
          { name: "Revenue CAGR (5y)", value: 0.12, label: "12%", status: "pass", weight: 3 },
        ],
        eps_cagr_5y: 0.15,
        revenue_cagr_5y: 0.12,
        net_margin_current: 0.25,
        operating_margin_trend: "expanding",
        revenue_eps_alignment: "aligned",
      },
      drawdown_risk: {
        name: "drawdown_risk",
        display_name: "Drawdown Risk",
        score: 7.0,
        category: "moderate",
        weight: 0.10,
        metrics: [
          { name: "Max Drawdown (5y)", value: -0.38, label: "−38%", status: "caution", weight: 3 },
          { name: "Beta (5y)", value: 0.94, label: "0.94", status: "pass", weight: 2 },
        ],
        max_drawdown_5y: -0.38,
        beta_5y: 0.94,
        current_drawdown: -0.05,
      },
    },
    scenarios: [
      { scenario: "bull", probability: 0.25, eps_growth: 0.15, exit_pe: 28, future_eps: 20.11, future_value: 563.08, total_return: 1.815, downside: 0 },
      { scenario: "base", probability: 0.50, eps_growth: 0.08, exit_pe: 22, future_eps: 14.69, future_value: 323.18, total_return: 0.616, downside: 0 },
      { scenario: "bear", probability: 0.20, eps_growth: 0.02, exit_pe: 15, future_eps: 11.04, future_value: 165.62, total_return: -0.172, downside: -0.172 },
      { scenario: "severe", probability: 0.05, eps_growth: 0.00, exit_pe: 12, future_eps: 10.00, future_value: 120.00, total_return: -0.400, downside: -0.400 },
    ],
    data_quality: {
      data_sources: "financial_ratios + income_statements + company_summary",
      fallbacks_used: false,
      last_computed_at: "2026-05-26T10:00:00Z",
    },
    ...overrides,
  };
}
```

---

## Appendix A: File Manifest

| File | Action | Purpose |
|---|---|---|
| `backend/domain/models/risk_assessment.py` | **Create** | All Pydantic models from §2.1 |
| `backend/application/services/risk_assessment_service.py` | **Create** | Orchestrator service from §2.2 |
| `backend/infrastructure/repositories/risk_repository.py` | **Create** | Risk-specific data queries from §2.3 |
| `backend/api/analysis.py` | Modify | Add 2 endpoints from §2.5 |
| `backend/scripts/migrate_add_risk_ratios.sql` | **Create** (from feasibility doc) | Add debt_to_ebitda columns |
| `backend/application/jobs/derived_financial_metrics_job.py` | Modify | Add debt_to_ebitda computation |
| `web/src/features/analysis/types/analysis.types.ts` | Modify | Add all types from §3.1 |
| `web/src/features/analysis/services/analysis.service.ts` | Modify | Add 3 fetch functions from §3.3 |
| `web/src/features/analysis/hooks/useRiskAssessment.ts` | **Create** | Hook from §3.5 |
| `web/src/features/analysis/components/risk-panel.tsx` | **Create** | UI component from §3.6 |
| `web/src/features/analysis/components/risk-layer-card.tsx` | **Create** | Reusable layer card sub-component |
| `web/src/features/analysis/components/risk-hero.tsx` | **Create** | Hero section (score ring + MEL) |
| `web/src/app/(authenticated)/analysis/[symbol]/page.tsx` | Modify | Add `risk` tab from §3.7 |
| `web/src/lib/query-keys.ts` | Modify | Add `QK.riskAssessment` from §3.4 |
| `web/src/features/analysis/utils/prefetch-valuations.ts` | Modify | Add risk prefetch from §3.7 |
| `backend/tests/test_risk_assessment_service.py` | **Create** | Unit tests from §5.1 |
| `backend/tests/test_risk_api_endpoints.py` | **Create** | Integration tests from §5.2 |
| `web/src/__tests__/RiskPanel.test.tsx` | **Create** | Component tests from §5.3 |
| `web/src/__tests__/useRiskAssessment.test.ts` | **Create** | Hook tests from §5.4 |
