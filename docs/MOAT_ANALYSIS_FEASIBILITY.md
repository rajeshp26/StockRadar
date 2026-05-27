# MOAT Analysis — Feasibility Study

## 1. Executive Summary

This report evaluates the feasibility of implementing a **professional-grade Economic Moat Analysis** tab within the existing Stock Analysis page. The proposed framework follows institutional methodology (Morningstar, Greenblatt, Damodaran) structured across 4 stages:

- **Stage 1 — Economic Moat Detection** (quantitative: ROIC, margins, FCF conversion, incremental ROIC)
- **Stage 2 — Moat Source Identification** (qualitative: switching costs, network effects, cost advantage, intangibles, efficient scale)
- **Stage 3 — Moat Durability Model** (disruption risk, competitive erosion)
- **Stage 4 — Capital Allocation Quality** (management skill)

**Verdict: FEASIBLE with moderate effort (~2–3 weeks).** Approximately 80% of required quantitative data already exists in the Supabase schema. Critically, the existing **edgartools library (`v5.30.0`) can extract full 10-K/10-Q text sections** (Business Description, Risk Factors, MD&A, Proxy Statements) — capabilities that are **completely untapped** in the current codebase. This unlocks direct access to moat-relevant narrative disclosures (switching costs, customer concentration, competitive positioning, risk factors) that previously appeared unobtainable. The implementation requires one new database table, a WACC computation service, an EDGAR text extraction engine, keyword-based scoring, and frontend panel — all buildable within existing patterns.

---

## 2. Current State Assessment

### 2.1 Existing Architecture

```
Frontend: Next.js → /analysis/[symbol]/page.tsx → tab="moat" → ComingSoonPanel (empty)
Backend:  FastAPI → /api/analysis/{symbol}/moat (NOT YET IMPLEMENTED)
Database: 38 tables across portfolio, financials, market data, derived metrics, valuation, watchlists
Providers: 
  ├── DefeatBeta (primary) — financial statements, ratios, forecasts, market data
  ├── Stockdex/Macrotrends (fallback 1) — financial statements
  ├── EDGAR/SEC (fallback 2) — XBRL financial statements ONLY (95% of edgartools capability UNUSED)
  │     └── UNUSED: 10-K text sections, DEF 14A proxy, full-text search, segment reporting
  └── YFinance (fallback 3) — prices, statements, summary data
Hooks:    useAnalysis, useDcfAnalysis, useDdmAnalysis, etc. (no Moat hook exists)
```

### 2.2 MOAT Tab — Current Implementation

| Aspect | Status |
|--------|--------|
| UI Tab | Exists, renders `ComingSoonPanel` with icon & description |
| Frontend Route | `/analysis/[symbol]/page.tsx` — `tab === "moat"` case |
| TypeScript Types | None |
| React Hook | None |
| Backend API Endpoint | None |
| Backend Service | None |
| DB Queries | None |
| Cache Layer | None |

### 2.3 Existing Pattern (to replicate)

Every analysis tab follows a 5-layer architecture that must be replicated:

| Layer | File Pattern | Example (CANSlim) |
|-------|-------------|-------------------|
| Types | `analysis.types.ts` | `CANSlimResponse`, `LetterScore`, etc. |
| Service | `analysis.service.ts` | `fetchCANSlimValuation(symbol)` |
| Hook | `hooks/use*.ts` | `useCANSlim(symbol)` |
| Panel | `components/*-panel.tsx` | `CANSlimPanel({ symbol })` |
| Page | `page.tsx` | `{tab === "others" && othersMethod === "canslim" && <CANSlimPanel />}` |

Backend pattern: **API Router** → **Service** → **Repository** → **Supabase**

---

## 3. MOAT Framework — Data Requirements Analysis

### 3.0 Critical Discovery: EDGAR Text Analysis Is Vastly Underutilized

The current `EdgarToolsProvider` implementation (at `backend/providers/edgar_provider.py`) only extracts **XBRL financial statements** (IS, BS, CF) from SEC filings. However, `edgartools==5.30.0` can parse the **full text content** of 10-K, 10-Q, and DEF 14A filings — including narrative sections that contain direct moat disclosures. This capability is completely untapped.

**Available (but unused) SEC textual data sources for moat analysis:**

| SEC Section | edgartools Accessor | Moat Data It Contains |
|-------------|-------------------|-----------------------|
| **Item 1 — Business** | `TenK.business` or `Document.get_sec_section("Item 1")` | Business description, competitive position, customer concentrations, segment breakdown, switching-cost disclosures, ecosystem references, distribution network |
| **Item 1A — Risk Factors** | `TenK.risk_factors` or `Document.get_sec_section("Item 1A")` | Threats to moat: technological disruption, regulatory risk, competition, customer concentration risk, supply chain risk |
| **Item 7 — MD&A** | `TenK.management_discussion` | Management's discussion of competitive advantages, pricing power, margin trends, reinvestment plans, market share trends |
| **Financial Notes (XBRL)** | `XBRL.get_statements_by_category("note")` | Segment reporting (revenue by product/region), customer concentration disclosures, intangible asset details, pension obligations |
| **DEF 14A (Proxy Statement)** | `filing.obj()` → `ProxyStatement` | Executive compensation alignment, insider ownership, pay-vs-performance, beneficial ownership |
| **Audit/Controls (Item 9A)** | `TenK.auditor` | Auditor identity, audit fees, internal control assessments |
| **Full-text search across ALL filings** | `search_filings("customer concentration", ticker="AAPL")` or `Filing.grep("switching costs")` | Cross-filing search for specific moat keywords |

**Key insight:** Many moat indicators that appeared "NOT AVAILABLE" in the quantitative analysis (Section 3.2) can be partially or fully extracted from SEC filing text. This transforms the feasibility landscape significantly.

### 3.1 Stage 1: Economic Moat Detection (Quantitative)

#### 3.1.1 ROIC Analysis (PRIMARY METRIC)

| Input | Needed? | Available? | Source Table | Column |
|-------|---------|------------|-------------|--------|
| NOPAT = EBIT × (1 − tax_rate) | Yes | **Computed in job, NOT stored** | `income_statements` | `ebit`, `pretax_income`, `tax_expense` |
| Invested Capital | Yes | **YES** (DefeatBeta populates) | `balance_sheets` | `invested_capital` |
| ROIC | Yes | **YES** (computed by scheduler) | `financial_ratios` | `roic` |
| Tax Rate | For NOPAT calc | Partial — computed in job only | `income_statements` | `pretax_income`, `tax_expense` |
| WACC | For Economic Profit | **NOT available** — no CAPM calc exists | N/A | N/A |

**Gap:** WACC is not computed anywhere. DCF service uses a config parameter (default 10%). For proper Economic Profit = (ROIC − WACC) × Invested Capital, we need a WACC computation service.

#### 3.1.2 Margin Structure Analysis

| Input | Needed? | Available? | Source Table | Column |
|-------|---------|------------|-------------|--------|
| Gross Margin (10yr) | Yes | **YES** | `financial_ratios` | `gross_margin` |
| Operating Margin (10yr) | Yes | **YES** | `financial_ratios` | `operating_margin` |
| Revenue (10yr) | Yes | **YES** | `income_statements` | `revenue` |
| Operating Income (10yr) | Yes | **YES** | `income_statements` | `operating_income` |

**Status: FULLY AVAILABLE.** All 10-year margin history exists. Standard deviation and stability analysis need to be computed in the service layer.

#### 3.1.3 Free Cash Flow Conversion

| Input | Needed? | Available? | Source Table | Column |
|-------|---------|------------|-------------|--------|
| FCF (10yr) | Yes | **YES** | `cash_flow_statements` | `free_cash_flow` |
| Net Income (10yr) | Yes | **YES** | `income_statements` | `net_income_to_common` |
| FCF Conversion | Yes | **YES** (computed by scheduler) | `financial_ratios` | `fcf_conversion` |

**Status: FULLY AVAILABLE.**

#### 3.1.4 Incremental ROIC

| Input | Needed? | Available? | Source Table | Column |
|-------|---------|------------|-------------|--------|
| ΔNOPAT (year-over-year) | Yes | Partial — need to compute from raw data | `income_statements` | `ebit`, `pretax_income`, `tax_expense` |
| ΔInvested Capital (year-over-year) | Yes | Partial — need to compute from raw data | `balance_sheets` | `invested_capital` |
| Incremental ROIC | Yes | **NOT stored** — must compute in service | N/A | N/A |

**Gap:** Must compute delta-based metric from year-over-year statement data. No existing computation.

### 3.2 Stage 2: Moat Source Identification (Qualitative/Heuristic)

#### 3.2.1 Switching Costs

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| Retention Rate | Yes | **PARTIAL — via EDGAR text** | Item 1 (Business) often discloses customer retention for subscription businesses |
| Gross Revenue Retention | Yes | **PARTIAL — via EDGAR text** | SaaS companies disclose GRR/NRR in MD&A (Item 7) |
| Net Revenue Retention | Yes | **PARTIAL — via EDGAR text** | Increasingly disclosed in 10-K for subscription models |
| Customer Acquisition Payback | Yes | **NOT AVAILABLE** | Rarely disclosed in filings |
| Multi-product Adoption | Yes | **PARTIAL — via EDGAR text + segments** | Segment reporting (XBRL detailed view + Item 1) shows product-line revenue |
| Switching-cost language (e.g. "proprietary platform", "deeply integrated") | Yes | **VIA EDGAR TEXT** | Grep/Keyword search within 10-K Item 1, Item 7 |

**EDGAR text approach:** Parse Item 1 (Business) and Item 7 (MD&A) for:
- Keywords: "retention", "renewal rate", "switching costs", "sticky", "lock-in", "deeply integrated"
- Customer concentration disclosures (often in Item 1 or financial notes)
- Contract duration references (long-term contracts → high switching costs)
- Platform/ecosystem language (multi-product adoption signal)

**Fallback proxies:** High gross margins > 60% + low SG&A/Revenue < 20% + high customer concentration.

#### 3.2.2 Network Effects

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| User Growth | Yes | **PARTIAL — via EDGAR text** | MD&A often discusses user/subscriber trends |
| Operating Leverage (increasing margins with scale) | Yes | **YES** (compute from financial_ratios) | Can derive from margin trends |
| Market Share | Yes | **PARTIAL — via EDGAR text** | Item 1 often cites market position or industry rankings |
| Transaction Volume | Yes | **PARTIAL — via EDGAR text + segments** | Payment processors/exchanges disclose volumes in MD&A |
| Network-effect language (e.g. "ecosystem", "platform", "two-sided") | Yes | **VIA EDGAR TEXT** | Grep/Keyword within 10-K Item 1, Item 7 |

**EDGAR text approach:** Parse Item 1 (Business) and Item 7 (MD&A) for:
- Keywords: "network effect", "ecosystem", "platform", "two-sided", "marketplace"
- User/subscriber metrics disclosures (not standardized but common for tech companies)
- Market share claims (e.g., "largest", "#1", "market leader")
- Scale references (distribution network size, merchant count, active users)

**Fallback proxies:** Operating margin expansion rate + revenue growth rate over 5 years.

#### 3.2.3 Cost Advantage

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| SG&A % of Revenue | Yes | **YES** | `income_statements` has `sga_expenses` |
| Scale Efficiency | Yes | Partial | `asset_turnover` in `financial_ratios` |
| Unit Cost vs Peers | Yes | **PARTIAL — via EDGAR text** | Cost advantage claims in Item 1, peer comparison via MD&A |
| Cost-advantage language (e.g. "lowest cost producer", "scale advantage") | Yes | **VIA EDGAR TEXT** | Grep/Keyword within 10-K Item 1 |

**EDGAR text approach:** Parse Item 1 for:
- Keywords: "cost advantage", "low-cost producer", "scale economies", "efficient"
- Operating metrics: store count, warehouse count, fleet size (disclosed in Item 1)
- Supply chain efficiency references

**Fallback proxies:** SG&A/Revenue + Asset Turnover + Operating Margin vs industry median.

#### 3.2.4 Intangible Assets (Brand, IP, Patents)

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| Gross Margin Resilience | Yes | **YES** | Compute from `financial_ratios` |
| Pricing Power (margin stability) | Yes | **YES** | Margin std dev from historical data |
| R&D Intensity (R&D/Revenue) | Yes | **YES** | `income_statements` has `rd_expenses` |
| Brand Premium | Yes | **PARTIAL — via EDGAR text** | Pricing power references in MD&A |
| Patent Portfolio | Yes | **PARTIAL — via EDGAR text** | Item 1 often lists material patents |
| Regulatory Licenses / Approvals | Yes | **VIA EDGAR TEXT** | Item 1 (Business) discloses regulatory barriers |
| Brand / Intangible language (e.g. "brand recognition", "IP portfolio") | Yes | **VIA EDGAR TEXT** | Grep/Keyword within 10-K Item 1 |

**EDGAR text approach:** Parse Item 1 for:
- Keywords: "patent", "trademark", "IP", "proprietary technology", "brand recognition"
- Patent counts, expiry dates, and competitive moat from IP
- Regulatory barriers: "licensed", "approved", "regulated"
- Pricing power language: "price increases", "pricing power", "premium pricing"

**XBRL detailed view:** Setting `view="detailed"` on balance sheet reveals intangible asset breakdowns (patents, trademarks, customer relationships, software).

**Fallback proxies:** Gross margin level + R&D/Revenue ratio + Intangible Assets/Total Assets.

#### 3.2.5 Efficient Scale

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| Market Concentration | Yes | **PARTIAL — via EDGAR text** | Item 1 often discusses competitive landscape |
| Barriers to Entry | Yes | **VIA EDGAR TEXT** | Item 1 (Business) explicitly discusses barriers |
| Niche Dominance | Yes | **PARTIAL — via EDGAR text** | "Leading provider", "largest" claims in Item 1 |
| Efficient-scale language (e.g. "limited competition", "niche") | Yes | **VIA EDGAR TEXT** | Grep/Keyword within 10-K Item 1, Item 7 |

**EDGAR text approach:** Parse Item 1 for:
- Keywords: "barriers to entry", "limited competition", "niche", "specialized market"
- Number of competitors mentioned
- Market size estimates (often disclosed in MD&A)
- Regulatory barriers to entry

**Fallback proxies:** Low capital intensity + stable market share + sector classification.

### 3.3 Stage 3: Moat Durability Model

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| R&D Intensity | Yes | **YES** | `rd_expenses` / `revenue` |
| Capital Intensity | Yes | **YES** | `capex` / `revenue` from cash flow |
| Debt Level | Yes | **YES** | `debt_to_equity` in `financial_ratios` |
| Customer Concentration | Yes | **PARTIAL — via EDGAR text** | Item 1 discloses >10% customers |
| Regulatory Risk | Yes | **VIA EDGAR TEXT** | Item 1A (Risk Factors) details regulatory risks |
| Technological Disruption Risk | Yes | **VIA EDGAR TEXT** | Item 1A explicitly lists competitive/disruption risks |
| Risk Factor density (how many risks are listed?) | Yes | **VIA EDGAR TEXT** | Item 1A section can be analyzed for moat threat themes |
| Competition language intensity | Yes | **VIA EDGAR TEXT** | Count competitive mentions vs. moat language in Item 1 |

**EDGAR text approach:** Parse Item 1A (Risk Factors) for:
- Keywords: "competition", "technological change", "disruption", "substitute", "regulation"
- Count and categorize risk factors into: technological, regulatory, competitive, macro
- Parse Item 1 (Business) for customer concentration: "one customer accounted for", "10% of revenue", "major customer"
- Parse Item 7 (MD&A) for competitive threats management explicitly acknowledges

**Fallback proxies:**
- Customer concentration: Look for R&D intensity + gross margin volatility + sector
- Regulatory risk: Sector-based heuristics (financials, healthcare, energy have higher regulatory risk)
- Disruption risk: Asset-light + high R&D = higher disruption potential; asset-heavy + low R&D = lower

**Status: SIGNIFICANTLY IMPROVED with EDGAR text.**

### 3.4 Stage 4: Capital Allocation Quality

| Input | Needed? | Available? | Notes |
|-------|---------|------------|-------|
| Buyback Yield | Yes | **YES** | `share_repurchases` in `cash_flow_statements` |
| Dividend Yield | Yes | **YES** | `dividend_metrics` table |
| SBC Dilution | Yes | **YES** | `stock_based_compensation` in `cash_flow_statements` |
| ROIC Trend Post-Acquisition | Yes | **NOT AVAILABLE** | Would need event-study analysis |
| FCF/Share Growth | Yes | **YES** | `fcf_per_share` in `financial_ratios` |

**Status: MOSTLY AVAILABLE.** M&A effectiveness is the only gap (cannot be reliably measured without acquisition-level data).

---

## 4. Data Gap Summary & New Table Design

### 4.1 Gap Analysis (Updated With EDGAR Text Capabilities)

| Category | Quant Data | EDGAR Text Data | Overall | Key Improvement |
|----------|-----------|----------------|---------|-----------------|
| **ROIC Analysis** | 90% | N/A | **90%** | WACC gap remains (quant-only) |
| **Margin Structure** | 100% | N/A | **100%** | — |
| **FCF Conversion** | 100% | N/A | **100%** | — |
| **Incremental ROIC** | 70% | N/A | **70%** | Computation logic only |
| **Switching Costs** | 20% | +50% from 10-K text | **70%** | Retention, contract language, ecosystem references now extractable |
| **Network Effects** | 30% | +40% from 10-K text | **70%** | Platform/ecosystem language, user metrics, market share claims |
| **Cost Advantage** | 60% | +20% from 10-K text | **80%** | Cost-leadership claims, scale references, operational metrics |
| **Intangible Assets** | 60% | +25% from 10-K + DEF 14A | **85%** | Patent details, brand references, regulatory barriers now accessible |
| **Efficient Scale** | 20% | +40% from 10-K text | **60%** | Barrier-to-entry language, niche claims, competition descriptions |
| **Capital Allocation** | 80% | +10% from DEF 14A | **90%** | Insider ownership, pay alignment from proxy statements |
| **Disruption Risk** | 50% | +40% from 10-K Item 1A | **90%** | Risk factors directly extracted; technological, regulatory, competitive risks |

### 4.2 New Table: `moat_analysis`

The primary storage for computed moat metrics:

```sql
CREATE TABLE moat_analysis (
    -- Primary key
    analysis_id       INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    company_id        INTEGER NOT NULL REFERENCES companies(company_id),
    fiscal_year       INTEGER,           -- NULL if using latest/consolidated

    -- Timestamps
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_source       TEXT DEFAULT 'computed',

    ────────────────────────────────────────────────────────────
    -- STAGE 1: Economic Moat Detection (quantitative scores)
    ────────────────────────────────────────────────────────────

    -- ROIC Analysis
    roic_10yr_median           NUMERIC,   -- median ROIC over 10 years
    roic_10yr_stability        NUMERIC,   -- low std dev = stable moat
    roic_vs_wacc_spread        NUMERIC,   -- ROIC - WACC (WACC from defaults)
    economic_profit            NUMERIC,   -- (ROIC - WACC) × Invested Capital
    incremental_roic_5yr       NUMERIC,   -- ΔNOPAT / ΔInvested Capital (5yr)
    roic_recession_performance NUMERIC,   -- ROIC during worst year

    -- Margin Analysis
    gross_margin_10yr_median   NUMERIC,
    gross_margin_10yr_stability NUMERIC,  -- lower = more pricing power
    operating_margin_10yr_median NUMERIC,
    operating_margin_10yr_stability NUMERIC,
    margin_resilience_score    NUMERIC,   -- composite (0-100)

    -- FCF Quality
    fcf_conversion_10yr_median NUMERIC,
    fcf_conversion_10yr_stability NUMERIC,
    fcf_quality_score          NUMERIC,   -- composite (0-100)

    -- Composite Stage 1 Score
    excess_return_score        NUMERIC,   -- ROIC-based score (0-100)

    ────────────────────────────────────────────────────────────
    -- STAGE 2: Moat Source Identification (heuristic scores)
    ────────────────────────────────────────────────────────────

    switching_cost_score       NUMERIC,   -- 0-5, based on proxies
    network_effect_score       NUMERIC,   -- 0-5, based on operating leverage
    cost_advantage_score       NUMERIC,   -- 0-5, based on SG&A efficiency
    intangible_asset_score     NUMERIC,   -- 0-5, based on R&D + margin stability
    efficient_scale_score      NUMERIC,   -- 0-5, based on sector + asset intensity

    primary_moat_source        TEXT,      -- the highest-scoring moat type
    secondary_moat_source      TEXT,      -- second-highest

    ────────────────────────────────────────────────────────────
    -- STAGE 3: Moat Durability & Disruption Risk
    ────────────────────────────────────────────────────────────

    disruption_risk_score      NUMERIC,   -- 0-100 (higher = more at risk)
    technological_risk         NUMERIC,   -- R&D intensity based
    regulatory_risk            NUMERIC,   -- sector-based
    commoditization_risk       NUMERIC,   -- margin trend based
    customer_concentration_risk NUMERIC,  -- (limited data, proxy-based)
    capital_intensity_risk     NUMERIC,   -- capex/revenue based

    ────────────────────────────────────────────────────────────
    -- STAGE 4: Capital Allocation Quality
    ────────────────────────────────────────────────────────────

    buyback_yield_5yr_avg      NUMERIC,
    dividend_payout_5yr_avg    NUMERIC,
    sbc_dilution_5yr_avg       NUMERIC,   -- stock-based comp / market cap proxy
    fcf_per_share_growth_5yr   NUMERIC,
    capital_allocation_score   NUMERIC,   -- composite (0-100)

    ────────────────────────────────────────────────────────────
    -- FINAL COMPOSITE SCORE
    ────────────────────────────────────────────────────────────

    moat_composite_score       NUMERIC,   -- weighted final score
    moat_rating                TEXT,       -- 'wide', 'narrow', 'weak', 'none'

    ────────────────────────────────────────────────────────────
    -- Metadata & Lineage
    ────────────────────────────────────────────────────────────

    input_snapshot             JSONB,     -- snapshot of source data version tags
    confidence_score           NUMERIC DEFAULT 1.0,

    UNIQUE(company_id, fiscal_year)
);
```

**Why a new table instead of adding to `financial_ratios`:**
- Conceptual separation: `financial_ratios` = raw computed ratios; `moat_analysis` = higher-order composite scores
- `moat_analysis` includes qualitative/heuristic scores, not just math
- Avoids bloating `financial_ratios` with 30+ additional columns
- Easier to version and invalidate independently

### 4.3 Supporting Computation: WACC Service

A lightweight WACC computation function is needed. Since the codebase already has CAPM-based cost of equity in ResidualIncomeService, we can extend it to compute proper WACC:

```
WACC = (E/V) × Re + (D/V) × Rd × (1 − Tc)
```

Where:
- **Re** = Risk-free rate + Beta × ERP (already computed in ResidualIncomeService)
- **Rd** = Interest expense / Total debt (can compute from `income_statements` + `balance_sheets`)
- **E/V** = Market cap / (Market cap + Total debt) (market cap from `company_summary`)
- **D/V** = Total debt / (Market cap + Total debt)
- **Tc** = Effective tax rate
- **Risk-free rate** = US 10Y Treasury yield (configurable, ~4.5% currently)
- **ERP** = Equity Risk Premium (~5.5% currently)

All inputs for WACC are **AVAILABLE** in existing tables.

---

## 5. EDGAR Text Extraction Architecture

### 5.1 Current State vs. Untapped Potential

```
                    CURRENT                             UNTAPPED
┌─────────────────────────────────┐       ┌─────────────────────────────────────────────┐
│  EdgarToolsProvider             │       │  EdgarTextMoatService (new)                  │
│  ┌───────────────────────────┐  │       │  ┌───────────────────────────────────────┐  │
│  │ XBRL Financial Statements │  │       │  │ 10-K Section Extraction:              │  │
│  │ - Income Statement        │  │       │  │ ├─ Item 1: Business Description       │  │
│  │ - Balance Sheet           │  │       │  │ ├─ Item 1A: Risk Factors              │  │
│  │ - Cash Flow               │  │       │  │ ├─ Item 7: MD&A                      │  │
│  │                          │  │       │  │ └─ Item 9A: Audit & Controls          │  │
│  │ USED AS: Fallback for    │  │       │  ├───────────────────────────────────────┤  │
│  │ DefeatBeta financials    │  │       │  │ DEF 14A Proxy Statement Extraction:   │  │
│  └───────────────────────────┘  │       │  │ ├─ Executive Compensation             │  │
│                                  │       │  │ ├─ Pay-vs-Performance                │  │
│  Library: edgartools==5.30.0    │       │  │ ├─ Beneficial Ownership              │  │
│  Only uses: Company,            │       │  │ └─ CEO Pay Ratio                     │  │
│  Financials, to_dataframe()     │       │  ├───────────────────────────────────────┤  │
│                                  │       │  │ XBRL Detailed View (segments):       │  │
│                                  │       │  │ ├─ Operating segment P&L            │  │
│                                  │       │  │ ├─ Geographic revenue breakdown     │  │
│                                  │       │  │ └─ Product-line data                │  │
│                                  │       │  ├───────────────────────────────────────┤  │
│                                  │       │  │ Full-text Search:                    │  │
│                                  │       │  │ ├─ Filing.grep("moat keyword")       │  │
│                                  │       │  │ └─ search_filings("topic") global    │  │
│                                  │       │  └───────────────────────────────────────┘  │
│                                  │       └─────────────────────────────────────────────┘
```

### 5.2 EDGAR Moat Text Extraction: Technical Blueprint

The text extraction should be built as a **layered service**, not a replacement for EdgarToolsProvider:

```
MoatAnalysisService
    │
    ├── MoatQuantService (Stage 1) — uses existing financial_ratios + income_statements etc.
    │
    └── MoatTextService (Stage 2-3) — NEW: EDGAR 10-K/10-Q text analysis
            │
            ├── EdgarFilingService — wraps edgartools for filing retrieval
            │   ├── get_tenk(symbol, year) → TenK object
            │   ├── get_proxy(symbol, year) → ProxyStatement
            │   └── get_xbrl_detailed(symbol, year) → segment data
            │
            ├── SectionExtractor — extracts and caches sections
            │   ├── extract_business(symbol, year) → Item 1 text
            │   ├── extract_risk_factors(symbol, year) → Item 1A text
            │   ├── extract_mda(symbol, year) → Item 7 text
            │   └── extract_compensation(symbol, year) → Proxy data
            │
            ├── MoatKeywordAnalyzer — rule-based text scoring
            │   ├── analyze_switching_costs(text) → score 0-5
            │   ├── analyze_network_effects(text) → score 0-5
            │   ├── analyze_cost_advantage(text) → score 0-5
            │   ├── analyze_intangible_assets(text) → score 0-5
            │   ├── analyze_efficient_scale(text) → score 0-5
            │   └── analyze_disruption_risk(text) → score 0-100
            │
            └── (Optional) AIAnalyzer — LLM-based narrative assessment
                └── generate_moat_narrative(text_facts, scores) → explanation
```

### 5.3 Keyword-Based Scoring Methodology

For each moat type, define weighted keyword dictionaries and scoring rules:

#### Switching Costs Score (0-5)

| Keyword / Phrase | Weight | Category |
|-----------------|--------|----------|
| "retention rate" / "renewal rate" / "retention" | 1.5 | Direct evidence |
| "switching costs" / "lock-in" / "sticky" | 1.5 | Direct evidence |
| "long-term contracts" / "multi-year" / "subscription" | 1.0 | Supporting |
| "deeply integrated" / "mission critical" / "embedded" | 1.0 | Supporting |
| "replacement cost" / "conversion cost" / "migration" | 1.0 | Supporting |
| "standardization" / "industry standard" / "proprietary" | 0.5 | Weak signal |
| "churn" / "attrition" | 0.5 | Negative if high |

#### Network Effects Score (0-5)

| Keyword / Phrase | Weight | Category |
|-----------------|--------|----------|
| "network effect" / "two-sided" | 1.5 | Direct evidence |
| "ecosystem" / "platform" | 1.0 | Supporting |
| "marketplace" / "exchange" | 1.0 | Supporting |
| "largest" / "#1" / "market leader" / "leading" | 0.5 | Market position |
| "users" / "merchants" / "developers" / "partners" | 0.5 | Ecosystem signal |
| "scale" / "scales" / "scalability" | 0.5 | Scale signal |

#### Cost Advantage Score (0-5)

| Keyword / Phrase | Weight | Category |
|-----------------|--------|----------|
| "lowest cost" / "low-cost" / "cost leader" | 1.5 | Direct evidence |
| "scale advantage" / "economies of scale" | 1.0 | Supporting |
| "efficient" / "efficiency" / "productivity" | 0.5 | Weak signal |
| "supply chain" / "logistics" / "distribution" | 0.5 | Infrastructure |
| "proprietary process" / "trade secret" | 0.5 | Process advantage |

#### Intangible Assets Score (0-5)

| Keyword / Phrase | Weight | Category |
|-----------------|--------|----------|
| "patent" / "patents" / "patented" | 1.0 | IP moat |
| "brand" / "brand recognition" / "brand equity" | 1.0 | Brand moat |
| "trademark" / "copyright" / "intellectual property" | 0.5 | IP supporting |
| "regulatory" / "licensed" / "approved" / "FDA" | 1.0 | Regulatory moat |
| "pricing power" / "price increases" / "premium" | 1.0 | Pricing power |
| "R&D" / "research and development" / "innovation" | 0.5 | Innovation signal |
| "proprietary technology" / "proprietary" | 1.0 | Technology moat |

#### Efficient Scale Score (0-5)

| Keyword / Phrase | Weight | Category |
|-----------------|--------|----------|
| "barriers to entry" / "barrier to entry" | 1.5 | Direct evidence |
| "limited competition" / "few competitors" / "niche" | 1.0 | Supporting |
| "natural monopoly" / "regulated monopoly" | 1.5 | Direct evidence |
| "capital intensive" / "significant investment required" | 0.5 | Capital barrier |
| "difficult to replicate" / "hard to replicate" | 1.0 | Supporting |
| "unique" / "only company" / "sole provider" | 1.0 | Market position |

#### Disruption Risk Score (0-100, higher = more at risk)

| Keyword / Phrase | Weight | Category |
|-----------------|--------|----------|
| "rapid technological change" / "technological change" | +10 | Technological |
| "disruption" / "disruptive" | +10 | General |
| "new entrants" / "new competitors" | +8 | Competitive |
| "substitute" / "alternative" | +8 | Substitution |
| "price competition" / "pricing pressure" | +6 | Pricing |
| "regulation" / "regulatory" / "government" | +6 | Regulatory |
| "commoditization" / "commodity" | +8 | Commoditization |
| "customer concentration" / "one customer" | +6 | Customer risk |
| "supply chain" / "supply disruption" | +4 | Supply risk |

### 5.4 Caching Strategy

EDGAR filings are static documents — they don't change after filing. Cache aggressively:

| Data Type | Cache Strategy | Freshness |
|-----------|---------------|-----------|
| Filing text (10-K sections) | Cache in `moat_analysis` JSONB or separate text cache table | Annual (refetch only when new 10-K filed) |
| Keyword analysis scores | Store directly in `moat_analysis` table | Annual (recompute only when new filing available) |
| Filing metadata (CIK, filing date) | `companies` table (existing) | Perpetual |
| Raw filing objects | NOT cached in DB — fetched on-demand via edgartools | Each request fetches fresh from SEC |

### 5.5 Text Storage Consideration

10-K Item 1 sections can be 10,000+ words. Options:

1. **Store compressed text in DB** — Add `edgar_filing_texts` table with `company_id, fiscal_year, section (text), raw_text (text)`. Simple but storage-heavy (~100KB per section).
2. **Store only keyword analysis results** — Extract keywords on-the-fly during computation, store only scores in `moat_analysis`. Lighter but recomputes on every cache miss.
3. **Hybrid** — Store compressed keyword hits + sentence snippets in JSONB within `moat_analysis`, and re-fetch full text from SEC on demand.

**Recommended: Option 2 (keyword results only)** for Phase 2, with Option 3 as Phase 3 enhancement.

---

## 6. Data Provider Coverage Analysis

### 6.1 Provider Capabilities

| Data Need | DefeatBeta | Stockdex | EDGAR/SEC (XBRL) | EDGAR/SEC (TEXT) | YFinance | Available? |
|-----------|-----------|----------|-----------------|-----------------|----------|-----------|
| Income Statement (10yr) | ✅ | ✅ | ✅ | ❌ | ✅ | **YES** |
| Balance Sheet (10yr) | ✅ | ✅ | ✅ | ❌ | ✅ | **YES** |
| Cash Flow (10yr) | ✅ | ✅ | ✅ | ❌ | ✅ | **YES** |
| Segment Reporting | ❌ | ❌ | ✅ (detailed view) | ✅ (Item 1) | ❌ | **YES — UNUSED** |
| Customer Concentration | ❌ | ❌ | ❌ | ✅ (Item 1 text) | ❌ | **YES — UNUSED** |
| Switching Cost Disclosures | ❌ | ❌ | ❌ | ✅ (Item 1, 7) | ❌ | **YES — UNUSED** |
| Risk Factors | ❌ | ❌ | ❌ | ✅ (Item 1A) | ❌ | **YES — UNUSED** |
| Competitive Positioning | ❌ | ❌ | ❌ | ✅ (Item 1, 7) | ❌ | **YES — UNUSED** |
| Market Share Claims | ❌ | ❌ | ❌ | ✅ (Item 1) | ❌ | **YES — UNUSED** |
| Insider Ownership | ❌ | ❌ | ❌ | ✅ (DEF 14A) | ❌ | **YES — UNUSED** |
| Comp Alignment (PvP) | ❌ | ❌ | ❌ | ✅ (DEF 14A) | ❌ | **YES — UNUSED** |
| Audit Quality | ❌ | ❌ | ❌ | ✅ (Item 9A) | ❌ | **YES — UNUSED** |
| Financial Ratios | ✅ | ❌ | ❌ | ❌ | ❌ | **YES** (computed) |
| Market Cap / EV | ✅ | ❌ | ❌ | ❌ | ✅ | **YES** |
| Beta | ✅ | ❌ | ❌ | ❌ | ✅ | **YES** |
| Price History | ✅ | ❌ | ❌ | ❌ | ✅ | **YES** |
| Revenue Forecast | ✅ | ❌ | ❌ | ❌ | ❌ | **YES** (DefeatBeta) |

### 6.2 Data NOT Available — True Gaps (Even With EDGAR Text)

| Data | Why Still Missing | Fallback |
|------|------------------|----------|
| **Precise Market Share (%)** | EDGAR text has directional claims ("leading", "largest"), not precise percentages | Use sector + revenue trends; flag as heuristic |
| **Customer Acquisition Cost (CAC)** | Not disclosed in SEC filings for most companies | Use SG&A/New Customers (not directly computable) |
| **Net Promoter Score (NPS)** | Operational metric, not SEC-disclosed | Omit; cannot proxy reliably |
| **True Brand Equity Valuation** | Requires consumer surveys | Use gross margin + R&D intensity as weak proxy |
| **Peer Unit Cost Comparison** | Would need all peers' cost structures parsed | Use industry_multiples table |
| **User Growth (MAU/DAU)** | Only Meta, Twitter, etc. disclose; most don't | Use revenue growth as proxy |
| **Detailed Run-rate / Bookings** | SaaS metrics not in SEC filings | Not available |

### 6.3 AI + EDGAR Text: Combined Augmentation

The combination of EDGAR text extraction + AI (OpenRouter) creates a powerful pipeline:

```
Step 1: Extract sections from 10-K/10-Q via edgartools
         ├── Item 1 (Business) — full text
         ├── Item 1A (Risk Factors) — full text
         └── Item 7 (MD&A) — full text

Step 2: Run keyword analysis (rule-based)
         └── Produce: moat source scores, disruption risk score

Step 3: (Optional) Send text + scores to OpenRouter AI
         ├── Prompt: "Given this business description, risk factors, and MD&A,
         │            what is the primary source of economic moat?"
         └── Result: AI-generated narrative with moat assessment
```

**This hybrid approach (keyword heuristics + AI narrative) is significantly more powerful than either alone:**

| Aspect | Rule-Based Keyword Analysis | AI (LLM) | Hybrid |
|--------|---------------------------|----------|--------|
| Deterministic | ✅ Yes | ❌ No | ✅ Scores are fixed |
| Nuance understanding | ❌ No | ✅ Yes | ✅ AI adds context |
| Latency | ✅ Fast | ❌ Slow (2-5s) | ✅ Fast path for scores |
| Cost | ✅ Free | ❌ API cost | ✅ AI optional, can be cached |
| Explainability | ✅ Clear which keywords matched | ❌ Black box | ✅ Both |
| Coverage of novel patterns | ❌ Limited | ✅ Strong | ✅ AI catches what rules miss |

**Recommendation:** Implement keyword scoring as the primary (always-on) engine. Add AI narrative generation as an optional enhancement that can be toggled by users or triggered on-demand.

OpenRouter integration already exists (`backend/providers/ai_provider.py`). Cost is near-zero using `openai/gpt-oss-120b:free` model.

---

## 7. Implementation Plan

### 7.1 Phased Approach

#### Phase 1 — Backend Core (Week 1)
**Effort:** 4–5 days

| Task | Files | Dependencies |
|------|-------|-------------|
| WACC computation service | `backend/domain/services/wacc_service.py` | None |
| Historical data aggregation queries | `backend/infrastructure/repositories/analysis_repository.py` | None |
| Moat analysis service (Stage 1 — quantitative) | `backend/application/services/moat_analysis_service.py` | WACC service, repo |
| Moat analysis API endpoint | `backend/api/analysis.py` | Moat service |
| `moat_analysis` DB table creation | SQL migration script | — |

#### Phase 2 — EDGAR Text Extraction Engine (Week 1–2)
**Effort:** 3–4 days

| Task | Files | Dependencies |
|------|-------|-------------|
| `EdgarFilingService` — filing retrieval wrapper | `backend/application/services/edgar_filing_service.py` | edgartools |
| `TenKSectionExtractor` — parse 10-K sections | `backend/application/services/edgar_section_extractor.py` | Filing service |
| Moat keyword analysis engine (all 5 types + disruption) | `backend/application/services/moat_text_service.py` | Section extractor |
| Proxy statement parser (comp, insider ownership) | `backend/application/services/edgar_proxy_service.py` | edgartools |
| Integration with `MoatAnalysisService` | `backend/application/services/moat_analysis_service.py` | Text service |

**Key implementation details:**
- `EdgarFilingService` uses `Company(symbol).get_financials()` (already exists) but also calls `Company.get_filings(form="10-K").latest()` → `filing.obj()` → `TenK` for text sections
- `TenKSectionExtractor` accesses `tenk["Item 1"]`, `tenk["Item 1A"]`, `tenk["Item 7"]` — these are dict-style accessors built into edgartools
- Keyword analysis is deterministic string matching — no ML required
- Proxy statement via `Company.get_filings(form="DEF 14A").latest()` → `filing.obj()` → `ProxyStatement`

#### Phase 3 — Moat Source Heuristics + Scoring (Week 2)
**Effort:** 2–3 days

| Task | Files | Dependencies |
|------|-------|-------------|
| EDGAR text scores → weighted moat source scores | `backend/application/services/moat_analysis_service.py` | Phase 1–2 |
| Disruption risk composite (text + quant) | `backend/application/services/moat_analysis_service.py` | Phase 1–2 |
| Capital allocation scoring | `backend/application/services/moat_analysis_service.py` | Phase 1 |
| Composite scoring, rating, caching | `backend/application/services/moat_analysis_service.py` | Above |
| AI integration for narrative (optional) | `backend/application/services/moat_analysis_service.py` + `ai_provider.py` | Optional |

#### Phase 4 — Frontend (Week 2–3)
**Effort:** 3–4 days

| Task | Files | Dependencies |
|------|-------|-------------|
| TypeScript types | `analysis.types.ts` | Phase 1–3 |
| Service function | `analysis.service.ts` | Phase 1–3 |
| React Query hook | `hooks/useMoatAnalysis.ts` | Service |
| Moat panel component | `components/moat-panel.tsx` | Hook |
| Page integration | `page.tsx` | Panel |
| Prefetch integration | `prefetch-valuations.ts` | Hook |

### 7.2 Scoring Model Weights (Proposed)

| Category | Weight | Source |
|----------|--------|--------|
| ROIC Durability (Stage 1) | 25% | `financial_ratios` ROIC history |
| Competitive Structure — Text (Stage 2) | 15% | EDGAR 10-K keyword analysis |
| Competitive Structure — Financial (Stage 2) | 10% | Financial proxy scores |
| Margin Resilience (Stage 1) | 15% | Margin std dev over 10 years |
| Reinvestment Ability (Stage 1 + 4) | 10% | Incremental ROIC + FCF/share growth |
| Balance Sheet Resilience (Stage 3) | 10% | Debt/equity, interest coverage |
| Disruption Risk (Stage 3) | 10% | EDGAR Item 1A risk factor analysis |
| Management Allocation (Stage 4) | 5% | Buyback + dividend + SBC discipline |

### 7.3 Final Moat Rating Model

| Composite Score | Rating | Display |
|----------------|--------|---------|
| 85–100 | Wide Moat | 🟢 |
| 70–84 | Narrow Moat | 🟡 |
| 50–69 | Weak Moat | 🟠 |
| <50 | No Moat | 🔴 |

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **WACC accuracy**: Using default risk-free rate + ERP may not reflect company-specific risk | Medium | Medium | Document assumptions, make parameters configurable, show WACC sensitivity |
| **Qualitative scoring subjectivity**: Moat source scores are heuristic, not empirical | High | Medium | Use conservative scoring, show evidence for each score, allow AI augmentation |
| **Incremental ROIC noise**: Year-over-year delta can produce extreme values with small denominator changes | Medium | Low | Use rolling multi-year deltas, clamp extreme values, show confidence intervals |
| **Data freshness**: Old balance sheet data leads to stale moat scores | Low | Medium | Use `computed_at` timestamps, show staleness warnings |
| **Sector inapplicability**: Moat framework doesn't apply equally to financials, REITs, utilities | Medium | Medium | Sector-aware applicability checks (like Magic Formula does) |
| **EDGAR text parsing fragility**: 10-K HTML formats vary between filers | Medium | Medium | Use edgartools' built-in parsers (handle variation); fall back gracefully to quant-only scores; log parse failures |
| **10-K not available**: Recent 10-K may not be filed yet or company may not file with SEC | Medium | Medium | Fall back to quant-only mode; show "text analysis unavailable" with explanation |
| **Keyword false positives**: "platform" ≠ network effects for all companies | High | Low | Use multi-keyword context scoring; weight phrases over single words; show matched keywords for transparency |
| **Rate limiting**: SEC EDGAR has fair-use rate limits | Low | Medium | Cache text aggressively; use identity string; implement retry with backoff (pattern exists in DefeatBetaProvider) |

---

## 9. Effort & Timeline Summary

| Phase | Components | Estimated Effort | Dependencies |
|-------|-----------|-----------------|-------------|
| Phase 1 | WACC service, DB queries, Stage 1 quant, API endpoint, DB migration | **4–5 days** | None |
| Phase 2 | EDGAR text extraction engine (filing service, section extractor, keyword analyzer) | **3–4 days** | edgartools library (already installed) |
| Phase 3 | Moat source heuristics, disruption risk, capital allocation, composite scoring | **2–3 days** | Phase 1–2 |
| Phase 4 | Frontend: types, service, hook, panel, page integration | **3–4 days** | Phase 1–3 |
| **Total** | **Full implementation** | **~12–16 days** | — |

**Note:** Phases 2 and 3 can be partially parallelized — the quantitative scoring (Phase 3 capital allocation) doesn't depend on EDGAR text. However, fully integrated scoring should wait until text inputs are available.

---

## 10. Key Recommendations

1. **Start with Stage 1 (quantitative)** — 80% of data already exists, highest confidence, delivers immediate value. Build this first as the foundation.

2. **Phase 2 (EDGAR text extraction) is the highest-ROI addition** — It transforms the moat analysis from "financial ratio dashboard" to "true competitive analysis" by extracting direct moat evidence from SEC disclosures. The edgartools library is already installed — no new dependencies needed.

3. **Keyword scoring first, AI augmentation second** — Rule-based keyword analysis is deterministic, debuggable, and fast. Add AI narrative generation as an optional enhancement after the core framework is stable.

4. **WACC can use a simplified model** — start with configurable default (8-10%), add CAPM-based computation when needed.

5. **Qualitative scores should be transparent** — In the UI, show which EDGAR keywords were matched and their contribution to each score. Don't hide the heuristic nature.

6. **Sector filtering is critical** — Moat analysis framework doesn't apply equally to financials, utilities, REITs. Apply methodology adjustments for these sectors.

7. **Cache EDGAR text results aggressively** — 10-K text is static once filed. Store keyword analysis results in `moat_analysis` table; refetch text only when a new 10-K is filed (annually). Use `Filing.filing_date` to track freshness.

8. **Fall back gracefully** — If EDGAR text extraction fails (either filing not found or parsing error), the system should still produce quant-only moat scores with a clear "Text analysis unavailable" indicator.

---

## 11. Detailed Design: EDGAR Text Extraction — Python vs AI

### 11.1 Approach Comparison

| Dimension | Python Rule-Based (Keyword Matching) | AI/LLM (OpenRouter) | Hybrid (Recommended) |
|-----------|--------------------------------------|---------------------|---------------------|
| **Speed** | <100ms per filing section | 2-5s per prompt | Fast path: <100ms; AI: on-demand |
| **Cost** | Free | ~$0.001–0.005 per analysis (free model available) | Free for primary; AI optional |
| **Determinism** | ✅ Same input → same output every time | ❌ Non-deterministic; varies with model/temperature | ✅ Scores deterministic; AI adds narrative |
| **Debuggability** | ✅ Exact match visible; easy to trace | ❌ Black box; hard to explain decisions | ✅ Keyword matches are traceable |
| **Nuance** | ❌ Misses sarcasm, implied meaning, context | ✅ Understands business context, can reason | ✅ AI catches what rules miss |
| **Coverage** | ❌ Only pre-defined keywords | ✅ Can identify novel patterns | ✅ Rules cover 80%; AI covers edge cases |
| **Maintenance** | Medium — add keywords over time | Low — prompt improvements | Low — prompt + keyword library |
| **Offline-capable** | ✅ Yes | ❌ Requires API call | ✅ Core works offline |
| **Hallucination risk** | ✅ None | ❌ Can invent evidence | ✅ Scores grounded in keywords; AI narrative is clearly marked |

### 11.2 Recommended Hybrid Architecture

```
                    ┌─────────────────────────────────────┐
                    │        MoatTextService               │
                    │  (Always-on, deterministic)          │
                    │                                     │
                    │  ┌───────────────────────────────┐  │
                    │  │ 1. Fetch 10-K sections         │  │
                    │  │    via edgartools              │  │
                    │  └──────────────┬────────────────┘  │
                    │                 ▼                    │
                    │  ┌───────────────────────────────┐  │
                    │  │ 2. Run keyword analysis        │  │
                    │  │    (5 moat types + disruption) │  │
                    │  │    → deterministic scores      │  │
                    │  └──────────────┬────────────────┘  │
                    │                 ▼                    │
                    │  ┌───────────────────────────────┐  │
                    │  │ 3. Store scores in            │  │
                    │  │    moat_analysis table        │  │
                    │  └───────────────────────────────┘  │
                    └─────────────────────────────────────┘
                                      │
                    ┌─────────────────▼─────────────────────┐
                    │     MoatAiService (Optional)           │
                    │                                       │
                    │  ┌───────────────────────────────┐    │
                    │  │ 1. Collect keyword hits +     │    │
                    │  │    quant scores               │    │
                    │  └──────────────┬────────────────┘    │
                    │                 ▼                      │
                    │  ┌───────────────────────────────┐    │
                    │  │ 2. Send to OpenRouter with    │    │
                    │  │    crafted prompt             │    │
                    │  └──────────────┬────────────────┘    │
                    │                 ▼                      │
                    │  ┌───────────────────────────────┐    │
                    │  │ 3. Receive narrative          │    │
                    │  │    assessment + store         │    │
                    │  └───────────────────────────────┘    │
                    └───────────────────────────────────────┘
```

### 11.3 Python Rule-Based Engine Detail

```python
# ── Keyword definitions ──────────────────────────────────────
# Each keyword has: weight, category, and whether it's a phrase (multi-word)
KeywordDef = {
    "text": str,        # keyword or phrase to match
    "weight": float,    # contribution to score (0.5-2.0)
    "category": str,    # "direct", "supporting", "weak"
    "is_phrase": bool,  # if True, match as whole phrase; if False, word-boundary match
}

MOAT_KEYWORDS = {
    "switching_costs": [
        KeywordDef("retention rate", 1.5, "direct", True),
        KeywordDef("renewal rate", 1.5, "direct", True),
        KeywordDef("switching costs", 1.5, "direct", True),
        KeywordDef("lock-in", 1.5, "direct", True),
        KeywordDef("sticky", 1.0, "supporting", False),
        KeywordDef("long-term contracts", 1.0, "supporting", True),
        KeywordDef("multi-year", 1.0, "supporting", True),
        KeywordDef("subscription", 0.5, "supporting", False),
        KeywordDef("deeply integrated", 1.0, "supporting", True),
        KeywordDef("mission critical", 1.0, "supporting", True),
        KeywordDef("embedded", 0.5, "supporting", False),
        KeywordDef("replacement cost", 1.0, "supporting", True),
        KeywordDef("conversion cost", 1.0, "supporting", True),
        KeywordDef("migration", 0.5, "weak", False),
        KeywordDef("proprietary", 0.5, "weak", False),
        KeywordDef("industry standard", 0.5, "weak", True),
        KeywordDef("churn", -0.5, "negative", False),   # negative signal
        KeywordDef("attrition", -0.5, "negative", False),
    ],
    # ... same pattern for network_effects, cost_advantage, intangible_assets, efficient_scale
}
```

**Matching algorithm:**
1. Convert filing text to lowercase
2. For each keyword, check if it exists in text (phrase matching for multi-word, word-boundary for single)
3. Count unique sections where keyword appears (Item 1, Item 1A, Item 7 — multi-section evidence is stronger)
4. Compute raw score: `sum(matches * weight)` for each moat type
5. Normalize to 0-5 scale using: `min(5, raw_score / normalization_factor)`
6. Apply sector adjustments (e.g., tech companies score higher on network effects by default)

### 11.4 AI Prompt Design

When AI augmentation is enabled, send this structured prompt:

```
You are a professional equity analyst evaluating a company's economic moat.

COMPANY: {symbol} ({company_name})
SECTOR: {sector}
INDUSTRY: {industry}

KEYWORD ANALYSIS RESULTS (rule-based scores 0-5):
- Switching Costs: {switching_cost_score}
- Network Effects: {network_effect_score}  
- Cost Advantage: {cost_advantage_score}
- Intangible Assets: {intangible_asset_score}
- Efficient Scale: {efficient_scale_score}
- Disruption Risk: {disruption_risk_score}/100

MATCHED KEYWORDS BY MOAT TYPE:
{json_of_matched_keywords_with_section_context}

QUANTITATIVE METRICS:
- 10yr median ROIC: {roic_pct}
- ROIC vs WACC spread: {spread_pct}
- 10yr gross margin stability: {gm_stability}
- FCF conversion rate: {fcf_conversion}
- Debt/Equity: {de_to_ratio}

INSTRUCTIONS:
1. Assess whether the rule-based scores seem reasonable
2. Identify any moat sources the keyword analysis may have missed
3. Provide a concise assessment (2-3 paragraphs) of the company's competitive advantage
4. Rate: Wide Moat / Narrow Moat / Weak Moat / No Moat
```

This prompt structure grounds the AI in deterministic data, reducing hallucination risk.

---

## 12. User Experience & UI/UX Design

### 12.1 Page Layout

The MOAT tab is accessed via the top tab bar in the analysis page (`/analysis/{symbol}`), between "Financial Health" and "Dividend".

```
┌─────────────────────────────────────────────────────────────────┐
│  [Intrinsic Value] [Health] [MOAT ✓] [Dividend] [Comparison] ... │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  MOAT ANALYSIS — AAPL                         WIDE MOAT  │   │
│  │  Apple Inc · Technology · Consumer Electronics           │   │
│  │  Composite Score: 87/100                      ● 🟢       │   │
│  │  Last Updated: May 15, 2026 · Data: 10-K (Sep 2025)     │   │
│  │  [+ View Evidence Details]  [⟳ Recompute]                │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ STAGE 1: ECONOMIC MOAT DETECTION              Score: 82  │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │   │
│  │ │  ROIC    │ │  Margin  │ │  FCF     │ │  Incremental │  │   │
│  │ │  vs WACC │ │ Strength │ │ Quality  │ │  ROIC        │  │   │
│  │ │          │ │          │ │          │ │              │  │   │
│  │ │  🟢 92   │ │  🟢 88   │ │  🟡 75   │ │  🟢 85       │  │   │
│  │ │  10yr    │ │  High    │ │  95%     │ │  +12%        │  │   │
│  │ │  median  │ │  stable  │ │  conv.   │ │  YoY         │  │   │
│  │ └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │   │
│  │                                                           │   │
│  │ ROIC TREND (10 Year)                                      │   │
│  │ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁  ████████████  Stable upward trend      │   │
│  │ Median ROIC: 32.4% · WACC: 9.2% · Spread: +23.2%        │   │
│  │ Economic Profit: $48.2B                                  │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ STAGE 2: MOAT SOURCE IDENTIFICATION          Score: 85   │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ ┌─────────────────────────────────────────────────────┐   │   │
│  │ │ ★ PRIMARY: Intangible Assets (Score: 4.8/5)       │   │   │
│  │ │   • Brand recognition: "premium brand" (Item 1)    │   │   │
│  │ │   • Patents: "extensive IP portfolio" (Item 1)     │   │   │
│  │ │   • Pricing power: "price increases" (MD&A)        │   │   │
│  │ │   • R&D Intensity: 6.2% of revenue (financials)    │   │   │
│  │ └─────────────────────────────────────────────────────┘   │   │
│  │                                                           │   │
│  │ ┌─────────────────────────────────────────────────────┐   │   │
│  │ │ ◆ SECONDARY: Switching Costs (Score: 3.5/5)        │   │   │
│  │ │   • Ecosystem: "deeply integrated" (Item 1)         │   │   │
│  │ │   • Retention: "high customer retention" (MD&A)     │   │   │
│  │ │   • "App Store ecosystem" (Item 1)                  │   │   │
│  │ └─────────────────────────────────────────────────────┘   │   │
│  │                                                           │   │
│  │ ▶ Network Effects: 2.1/5 · ▶ Cost Advantage: 1.5/5      │   │   │
│  │ ▶ Efficient Scale: 1.0/5                                 │   │   │
│  │                                                           │   │
│  │ [ⓘ Scores are derived from SEC 10-K keyword analysis]     │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ STAGE 3: MOAT DURABILITY & RISK              Score: 78   │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ ┌────────────────────┐ ┌────────────────────┐            │   │
│  │ │ DISRUPTION RISK    │ │ FINANCIAL RESILIENCE│           │   │
│  │ │ Score: 25/100      │ │ Score: 90/100       │           │   │
│  │ │ (Low risk)         │ │ (Strong)            │           │   │
│  │ │                    │ │                     │           │   │
│  │ │ Technological: Low │ │ Debt/Equity: 1.8x   │           │   │
│  │ │ Regulatory: Medium │ │ Interest Cov: 28x   │           │   │
│  │ │ Competitive: Medium│ │ Current Ratio: 1.5x │           │   │
│  │ │                    │ │ Capex/Rev: 4.5%     │           │   │
│  │ └────────────────────┘ └────────────────────┘            │   │
│  │                                                           │   │
│  │ KEY RISK FACTORS (from 10-K Item 1A):                     │   │
│  │ ⚠ "Global economic conditions could impact demand"       │   │
│  │ ⚠ "Supply chain concentration in Asia"                   │   │
│  │ ⚠ "Increasing regulatory scrutiny of App Store"          │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ STAGE 4: CAPITAL ALLOCATION              Score: 72        │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ Buyback Yield (5yr avg): 3.2%         ● Strong           │   │
│  │ Dividend Growth (5yr CAGR): 8.5%      ● Growing          │   │
│  │ SBC Dilution (5yr avg): 0.8%          ● Low dilution     │   │
│  │ FCF/Share Growth (5yr CAGR): 11.2%    ● Strong           │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ TEXT EVIDENCE GALLERY                                      │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ The following excerpts from Apple's 10-K support the      │   │
│  │ moat assessment:                                          │   │
│  │                                                           │   │
│  │ 📄 Item 1 — Business                                      │   │
│  │ > "The Company's ability to compete successfully ...      │   │
│  │ > depends heavily on its ability to ensure a consistent   │   │
│  │ > and compelling user experience across its ecosystem."   │   │
│  │   → Keywords: ecosystem (network effects)                 │   │
│  │                                                           │   │
│  │ 📄 Item 7 — MD&A                                          │   │
│  │ > "The Company has a large installed base of active       │   │
│  │ > devices and a high level of customer retention."        │   │
│  │   → Keywords: retention (switching costs)                 │   │
│  │                                                           │   │
│  │ [View Full Analysis Details ▸]                            │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ AI INSIGHT (Optional — click to generate)                 │   │
│  │                                                           │   │
│  │ [✨ Generate AI Moat Assessment]                          │   │
│  │                                                           │   │
│  │ AI analysis provides context-aware narrative explaining   │   │
│  │ the company's competitive advantages and risks. Generated │   │
│  │ using keyword analysis results + quantitative metrics.    │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 12.2 User Interaction States

| State | Trigger | UI Treatment |
|-------|---------|-------------|
| **Loading** | Initial page load or recompute | Skeleton shimmer for each stage card; pulsing indicators |
| **First Visit (No Moat Data)** | Never computed before | All stages show "Compute Moat Analysis" CTA button in center |
| **Complete** | Data exists and is fresh | Full dashboard as shown above |
| **Stale** | Data older than 24h (quant) or new 10-K filed (text) | Show warning banner: "Data may be stale. New 10-K filed on [date]. [Recompute]" |
| **EDGAR Text Unavailable** | No 10-K found or parse failed | Stage 2 shows: "SEC text analysis unavailable for this company. Scores based on financial proxies." with quant-only scores |
| **Error** | Unexpected error | Error banner with retry button; fall back to quant-only if possible |
| **AI Generating** | User clicked "Generate AI Moat Assessment" | Streaming text generation with typewriter effect |
| **Sector Excluded** | Financials/Utilities/REITs | Show methodology adjustment notice; adjust scoring accordingly |

### 12.3 Responsive Behavior

- **Desktop (>1024px):** Full 4-column layout for Stage 1 metric cards; side-by-side for Stage 3
- **Tablet (768-1024px):** 2-column layout; text evidence gallery collapsible
- **Mobile (<768px):** Single column; all sections collapsible accordion; scores shown as horizontal bars

### 12.4 Key UX Principles

1. **Transparency first:** Every score is clickable to reveal which metrics/keywords contributed
2. **Evidence-backed:** Keyword matches show the actual SEC excerpt, not just a score
3. **Graceful degradation:** If any data source is unavailable, show partial results rather than nothing
4. **Explainability:** "Why this score?" tooltip on every metric explains the calculation method
5. **Actionability:** The capital allocation stage should give clear signals about shareholder value creation

---

## 13. Use Cases & Information Requirements

### 13.1 Use Case Catalog

| UC# | Use Case | Actor | Description | Data Required |
|-----|----------|-------|-------------|---------------|
| UC-01 | View Moat Overview | User | See composite moat rating and score for a stock | Aggregated from all stages |
| UC-02 | View Quantitative Moat Metrics | User | See ROIC, margins, FCF conversion trends | `financial_ratios` (10yr), WACC, NOPAT |
| UC-03 | View Moat Source Analysis | User | See which moat types apply and why | EDGAR text keyword scores + quant proxies |
| UC-04 | View Disruption Risk | User | See threats to the moat | EDGAR Item 1A risk factors + balance sheet |
| UC-05 | View Capital Allocation Quality | User | See management's capital discipline | `cash_flow_statements`, `dividend_metrics` |
| UC-06 | View EDGAR Text Evidence | User | See actual SEC excerpts supporting scores | EDGAR 10-K text (cached keyword matches + snippets) |
| UC-07 | Recompute Moat Analysis | User | Force refresh all moat data | All data sources re-fetched |
| UC-08 | Generate AI Narrative | User | Get LLM-generated moat assessment | Keyword scores, quant metrics, AI prompt |
| UC-09 | View Score Breakdown | User | Click any score to see contributing factors | Score calculation trace |
| UC-10 | Auto-refresh on Schedule | System | Background refresh moat data periodically | Scheduler integration |

### 13.2 Information Requirements by Stage

#### Stage 1: Economic Moat Detection

| Output Metric | Formula / Source | Input Data |
|--------------|-----------------|------------|
| ROIC 10yr Median | median(ROIC_year1..ROIC_year10) | `financial_ratios.roic` |
| ROIC 10yr Stability | 1 / (1 + std(ROIC_values)) normalized to 0-100 | `financial_ratios.roic` |
| ROIC vs WACC Spread | ROIC_median - WACC | ROIC (above) + WACC (computed) |
| Economic Profit | (ROIC - WACC) × Invested Capital | ROIC, WACC, `balance_sheets.invested_capital` |
| Incremental ROIC 5yr | ΔNOPAT_5yr / ΔInvestedCapital_5yr | `income_statements.ebit`, tax, `balance_sheets.invested_capital` |
| ROIC Recession Performance | min(ROIC across all years) | `financial_ratios.roic` |
| Gross Margin 10yr Median | median(gross_margin_year1..10) | `financial_ratios.gross_margin` |
| Gross Margin Stability | 1 / (1 + std(gross_margin)) | `financial_ratios.gross_margin` |
| Operating Margin 10yr Median | median(op_margin_year1..10) | `financial_ratios.operating_margin` |
| Operating Margin Stability | 1 / (1 + std(op_margin)) | `financial_ratios.operating_margin` |
| FCF Conversion 10yr Median | median(FCF/NI_year1..10) | `financial_ratios.fcf_conversion` |
| FCF Conversion Stability | 1 / (1 + std(FCF_conversion)) | `financial_ratios.fcf_conversion` |

#### Stage 2: Moat Source Identification

| Output Metric | Formula / Source | Input Data |
|--------------|-----------------|------------|
| Switching Cost Score (0-5) | Normalized keyword match score | EDGAR Item 1, Item 7 text |
| Network Effect Score (0-5) | Normalized keyword match score | EDGAR Item 1, Item 7 text |
| Cost Advantage Score (0-5) | Normalized keyword match + quant proxy | EDGAR text + SG&A/Rev, Asset Turnover |
| Intangible Asset Score (0-5) | Normalized keyword match + quant proxy | EDGAR text + R&D/Rev, Gross Margin |
| Efficient Scale Score (0-5) | Normalized keyword match + sector | EDGAR text + sector + capex intensity |
| Primary Moat Source | max(5 scores) | All above |
| Secondary Moat Source | second_max(5 scores) | All above |

#### Stage 3: Moat Durability & Risk

| Output Metric | Formula / Source | Input Data |
|--------------|-----------------|------------|
| Disruption Risk Score (0-100) | Normalized keyword risk count | EDGAR Item 1A risk factors |
| Technological Risk | Risk keyword density in technology categories | EDGAR Item 1A text |
| Regulatory Risk | Risk keyword density in regulatory categories | EDGAR Item 1A text + sector |
| Commoditization Risk | margin_trend_slope (negative = higher risk) | `financial_ratios.gross_margin` 10yr |
| Customer Concentration Risk | Text match for customer concentration keywords | EDGAR Item 1 text |
| Capital Intensity Risk | Capex/Revenue ratio (higher = higher risk) | `cash_flow_statements` |
| Debt/Equity Ratio | From financial_ratios | `financial_ratios.debt_to_equity` |
| Interest Coverage | EBIT / Interest Expense | `financial_ratios.interest_coverage` |

#### Stage 4: Capital Allocation

| Output Metric | Formula / Source | Input Data |
|--------------|-----------------|------------|
| Buyback Yield 5yr Avg | avg(|share_repurchases| / market_cap) × 100 | `cash_flow_statements`, `company_summary` |
| Dividend Growth 5yr | CAGR of DPS over 5 years | `dividend_metrics.dividend_growth_rate_5yr` |
| SBC Dilution 5yr Avg | avg(stock_based_comp / market_cap) × 100 | `cash_flow_statements` |
| FCF/Share Growth 5yr | CAGR of FCF/share over 5 years | `financial_ratios.fcf_per_share` |

---

## 14. Backend & Frontend Architecture

### 14.1 Complete Class Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BACKEND LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────┐                                          │
│  │    MoatAnalysisRouter        │  ← FastAPI APIRouter                     │
│  │  (backend/api/analysis.py)   │                                          │
│  ├──────────────────────────────┤                                          │
│  │  + GET /{symbol}/moat       │  → MoatAnalysisResponse                   │
│  │  + GET /{symbol}/moat/evidence│ → MoatEvidenceResponse                  │
│  │  + POST /{symbol}/moat/ai   │  → MoatAiResponse (optional)             │
│  └──────────┬───────────────────┘                                          │
│             │                                                               │
│             ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    MoatAnalysisService                               │   │
│  │  (backend/application/services/moat_analysis_service.py)            │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  + get_moat_analysis(symbol, force=False) → MoatAnalysisResponse    │   │
│  │  + get_text_evidence(symbol) → MoatEvidenceResponse                  │   │
│  │  + generate_ai_narrative(symbol) → MoatAiResponse                    │   │
│  │                                                                     │   │
│  │  - _compute_stage1_quantitative(company_id) → Stage1Result          │   │
│  │  - _compute_stage2_moat_sources(company_id) → Stage2Result          │   │
│  │  - _compute_stage3_durability(company_id) → Stage3Result            │   │
│  │  - _compute_stage4_allocation(company_id) → Stage4Result            │   │
│  │  - _compute_composite_score(s1, s2, s3, s4) → CompositeScore       │   │
│  │  - _check_cache(company_id) → Optional[MoatAnalysisResponse]        │   │
│  │  - _save_to_cache(company_id, response)                             │   │
│  └──────┬────────────────────┬──────────────────────┬──────────────────┘   │
│         │                    │                      │                       │
│         ▼                    ▼                      ▼                       │
│  ┌──────────────┐   ┌────────────────┐   ┌────────────────────┐            │
│  │WaccService   │   │MoatQuantService│   │  MoatTextService   │            │
│  ├──────────────┤   ├────────────────┤   ├────────────────────┤            │
│  │+ compute(    │   │+ calc_roic_    │   │+ analyze_moat_     │            │
│  │  company_id) │   │  analysis(id)  │   │  sources(symbol)   │            │
│  │ → WaccResult │   │+ calc_margin_  │   │  → MoatSourcesResult│           │
│  │              │   │  analysis(id)  │   │+ analyze_disruption │            │
│  │ Uses: CAPM:  │   │+ calc_fcf_     │   │  risk(symbol)      │            │
│  │  Rf+β×ERP    │   │  analysis(id)  │   │  → RiskResult      │            │
│  │ + debt adj   │   │+ calc_increm_  │   │+ get_text_evidence │            │
│  └──────┬───────┘   │  roic(id)     │   │  (symbol)           │            │
│         │           └───────┬────────┘   │  → EvidenceResult   │            │
│         │                   │            └──────────┬─────────┘            │
│         ▼                   ▼                       ▼                      │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │              AnalysisRepository                              │          │
│  │  (backend/infrastructure/repositories/analysis_repository.py) │          │
│  ├──────────────────────────────────────────────────────────────┤          │
│  │  + get_financial_ratios_10yr(company_id) → List[Dict]        │          │
│  │  + get_income_statements_annual(company_id) → List[Dict]     │          │
│  │  + get_balance_sheets_annual(company_id) → List[Dict]        │          │
│  │  + get_cash_flow_annual(company_id) → List[Dict]             │          │
│  │  + get_company_summary(company_id) → Dict                    │          │
│  │  + get_company_context(symbol) → Dict                        │          │
│  │  + get_current_market_price(company_id) → float              │          │
│  │  + upsert_moat_analysis(moat_data: MoatAnalysisRow)          │          │
│  │  + get_moat_analysis(company_id) → Optional[MoatAnalysisRow] │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │           EdgarFilingService                                 │          │
│  │  (backend/application/services/edgar_filing_service.py)       │          │
│  ├──────────────────────────────────────────────────────────────┤          │
│  │  + get_latest_tenk(symbol) → Optional[TenK]                  │          │
│  │  + get_latest_proxy(symbol) → Optional[ProxyStatement]       │          │
│  │  + get_section_text(tenk, section) → str                     │          │
│  │  - _get_company(symbol) → Company                            │          │
│  │  - _get_latest_filing(company, form) → Optional[Filing]      │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │           MoatKeywordAnalyzer                                │          │
│  │  (backend/application/services/moat_text_service.py)          │          │
│  ├──────────────────────────────────────────────────────────────┤          │
│  │  + analyze_switching_costs(text: str) → KeywordResult        │          │
│  │  + analyze_network_effects(text: str) → KeywordResult        │          │
│  │  + analyze_cost_advantage(text: str) → KeywordResult         │          │
│  │  + analyze_intangible_assets(text: str) → KeywordResult      │          │
│  │  + analyze_efficient_scale(text: str) → KeywordResult        │          │
│  │  + analyze_disruption_risk(text: str) → RiskKeywordResult    │          │
│  │  - _match_keywords(text, keyword_defs) → List[Match]         │          │
│  │  - _compute_score(matches) → float (0-5)                     │          │
│  │  - _extract_snippets(text, matches, context_chars=120)       │          │
│  │                                                              │          │
│  │  KEYWORD_DEFS: Dict[str, List[KeywordDef]]                   │          │
│  │    (loaded from YAML or Python dict)                         │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │           MoatAiService (Optional)                           │          │
│  │  (backend/application/services/moat_ai_service.py)            │          │
│  ├──────────────────────────────────────────────────────────────┤          │
│  │  + generate_moat_narrative(keyword_scores, quant_data)       │          │
│  │    → str (narrative text)                                    │          │
│  │  - _build_prompt(symbol, scores, data) → str                 │          │
│  │  - _call_openrouter(prompt) → str                            │          │
│  │  - _parse_response(response) → str (strips markdown)        │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │            Pydantic Models (schemas)                         │          │
│  │  (backend/domain/models/analysis_moat.py)                    │          │
│  ├──────────────────────────────────────────────────────────────┤          │
│  │  class MoatAnalysisResponse(BaseModel):                      │          │
│  │    symbol: str                                               │          │
│  │    company_id: int                                           │          │
│  │    company_name: str                                         │          │
│  │    sector: Optional[str]                                     │          │
│  │    industry: Optional[str]                                   │          │
│  │    composite_score: int                                      │          │
│  │    moat_rating: Literal["wide", "narrow", "weak", "none"]    │          │
│  │    currency: str                                             │          │
│  │                                                              │          │
│  │    stage1_quant: Stage1Result                                │          │
│  │    stage2_sources: Stage2Result                              │          │
│  │    stage3_durability: Stage3Result                           │          │
│  │    stage4_allocation: Stage4Result                           │          │
│  │                                                              │          │
│  │    text_analysis_available: bool                             │          │
│  │    ai_narrative_available: bool                              │          │
│  │    data_quality: MoatDataQuality                             │          │
│  │    last_computed_at: str                                     │          │
│  │                                                              │          │
│  │  class Stage1Result(BaseModel):                              │          │
│  │    excess_return_score: int                                  │          │
│  │    margin_resilience_score: int                              │          │
│  │    fcf_quality_score: int                                    │          │
│  │    composite_score: int                                      │          │
│  │                                                              │          │
│  │    roic_analysis: RoicMetrics                                │          │
│  │    margin_analysis: MarginMetrics                            │          │
│  │    fcf_analysis: FcfMetrics                                  │          │
│  │    incremental_roic: Optional[float]                         │          │
│  │                                                              │          │
│  │  class RoicMetrics(BaseModel):                               │          │
│  │    median_10yr: float                                        │          │
│  │    stability: float                                          │          │
│  │    wacc: float                                               │          │
│  │    spread: float                                             │          │
│  │    economic_profit: Optional[float]                          │          │
│  │    recession_roic: Optional[float]                           │          │
│  │    score: int                                                │          │
│  │                                                              │          │
│  │  class Stage2Result(BaseModel):                              │          │
│  │    composite_score: int                                      │          │
│  │    sources: List[MoatSourceScore]                            │          │
│  │    primary: Optional[MoatSourceScore]                        │          │
│  │    secondary: Optional[MoatSourceScore]                      │          │
│  │    text_analysis_used: bool                                  │          │
│  │                                                              │          │
│  │  class MoatSourceScore(BaseModel):                           │          │
│  │    source_type: Literal["switching_costs", "network_effects",│          │
│  │                        "cost_advantage", "intangible_assets",│          │
│  │                        "efficient_scale"]                    │          │
│  │    score: float  # 0-5                                       │          │
│  │    matched_keywords: List[KeywordMatch]                      │          │
│  │    quant_proxy_score: Optional[float]                        │          │
│  │    description: str                                          │          │
│  │                                                              │          │
│  │  class KeywordMatch(BaseModel):                              │          │
│  │    keyword: str                                              │          │
│  │    section: str  # "Item 1", "Item 1A", "Item 7"            │          │
│  │    snippet: str  # 120 chars context                         │          │
│  │    count: int                                                │          │
│  │                                                              │          │
│  │  class Stage3Result(BaseModel):                              │          │
│  │    composite_score: int                                      │          │
│  │    disruption_risk: DisruptionRiskMetrics                    │          │
│  │    financial_resilience: FinancialResilienceMetrics          │          │
│  │                                                              │          │
│  │  class DisruptionRiskMetrics(BaseModel):                     │          │
│  │    overall: int  # 0-100                                     │          │
│  │    technological: int                                        │          │
│  │    regulatory: int                                           │          │
│  │    commoditization: int                                      │          │
│  │    customer_concentration: int                               │          │
│  │    capital_intensity: int                                    │          │
│  │    risk_factors: List[RiskFactorEvidence]                    │          │
│  │                                                              │          │
│  │  class Stage4Result(BaseModel):                              │          │
│  │    composite_score: int                                      │          │
│  │    buyback_yield_5yr: Optional[float]                        │          │
│  │    dividend_growth_5yr: Optional[float]                      │          │
│  │    sbc_dilution_5yr: Optional[float]                         │          │
│  │    fcf_per_share_growth_5yr: Optional[float]                 │          │
│  │    metrics: List[AllocationMetric]                           │          │
│  │                                                              │          │
│  │  class MoatDataQuality(BaseModel):                           │          │
│  │    quant_data_freshness_days: int                            │          │
│  │    tenk_filing_date: Optional[str]                           │          │
│  │    text_analysis_available: bool                             │          │
│  │    fallbacks_used: List[str]                                 │          │
│  │    confidence_score: float                                   │          │
│  │                                                              │          │
│  │  class MoatEvidenceResponse(BaseModel):                      │          │
│  │    symbol: str                                               │          │
│  │    tenk_filing_date: Optional[str]                           │          │
│  │    primary_moat_evidence: List[MoatSourceDetail]             │          │
│  │    risk_factor_excerpts: List[RiskExcerpt]                   │          │
│  │                                                              │          │
│  │  class MoatAiResponse(BaseModel):                            │          │
│  │    narrative: str                                            │          │
│  │    model: str                                                │          │
│  │    generated_at: str                                         │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  page.tsx  →  {tab === "moat" && <MoatPanel symbol={symbol} />}    │   │
│  └──────────────────────────┬──────────────────────────────────────────┘   │
│                             │                                               │
│                             ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MoatPanel ({ symbol: string })                                     │   │
│  │  (web/src/features/analysis/components/moat-panel.tsx)              │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  Uses: useMoatAnalysis(symbol) → { data, loading, error }          │   │
│  │  Uses: useMoatTextEvidence(symbol) → evidence (on demand)           │   │
│  │  Uses: useMoatAi(symbol) → ai_narrative (on demand)                │   │
│  │                                                                     │   │
│  │  Renders:                                                           │   │
│  │  ├── <MoatHeader rating score company_info />                       │   │
│  │  ├── <Stage1QuantPanel data={stage1} />                             │   │
│  │  │   ├── <RoicCard roic_metrics />                                  │   │
│  │  │   ├── <MarginCard margin_metrics />                              │   │
│  │  │   ├── <FcfCard fcf_metrics />                                    │   │
│  │  │   └── <IncrementalRoicCard incremental_roic />                   │   │
│  │  ├── <Stage2MoatSourcesPanel data={stage2} />                       │   │
│  │  │   ├── <MoatSourceCard primary_source expanded />                 │   │
│  │  │   ├── <MoatSourceCard secondary_source />                        │   │
│  │  │   └── <OtherSourcesAccordion remaining_sources />               │   │
│  │  ├── <Stage3DurabilityPanel data={stage3} />                        │   │
│  │  │   ├── <DisruptionRiskCard risk_data />                           │   │
│  │  │   └── <FinancialResilienceCard resilience_data />                │   │
│  │  ├── <Stage4CapitalAllocationPanel data={stage4} />                 │   │
│  │  ├── <TextEvidenceGallery evidence={evidence} />                    │   │
│  │  └── <AiNarrativeCard ai_data />                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Hooks                                                              │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  useMoatAnalysis(symbol)                                            │   │
│  │  ├── useQuery({ queryKey: QK.moat(symbol), queryFn })              │   │
│  │  ├── return { data, loading, error, recompute }                     │   │
│  │  └── QK.moat = ["analysis", "moat", symbol]                        │   │
│  │                                                                     │   │
│  │  useMoatTextEvidence(symbol)                                        │   │
│  │  ├── useQuery({ queryKey: QK.moatEvidence(symbol), ... })          │   │
│  │  └── (only called when user clicks "View Evidence Details")         │   │
│  │                                                                     │   │
│  │  useMoatAiNarrative(symbol)                                         │   │
│  │  ├── useMutation({ mutationFn, onSuccess: invalidate })            │   │
│  │  └── (only called when user clicks "Generate AI Assessment")       │   │
│  │                                                                     │   │
│  │  prefetchMoatAnalysis(symbol, queryClient)                          │   │
│  │  └── Added to prefetchAllValuations() in page.tsx                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Services (analysis.service.ts)                                     │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  async fetchMoatCached(symbol)                                      │   │
│  │  → { status: "ok" | "not_computed" | "error", data?: ... }        │   │
│  │                                                                     │   │
│  │  async fetchMoatAnalysis(symbol, force=false)                       │   │
│  │  → MoatAnalysisResponse                                             │   │
│  │                                                                     │   │
│  │  async fetchMoatTextEvidence(symbol)                                │   │
│  │  → MoatEvidenceResponse                                             │   │
│  │                                                                     │   │
│  │  async generateMoatAiNarrative(symbol)                              │   │
│  │  → MoatAiResponse                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Types (analysis.types.ts)                                           │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  (Mirrors all backend Pydantic models above)                        │   │
│  │  MoatAnalysisResponse, Stage1Result, RoicMetrics,                   │   │
│  │  Stage2Result, MoatSourceScore, KeywordMatch,                      │   │
│  │  Stage3Result, DisruptionRiskMetrics, etc.                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 14.2 Database Schema (Extended)

```sql
-- Primary moat analysis storage table
CREATE TABLE moat_analysis (
    analysis_id           INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    company_id            INTEGER NOT NULL REFERENCES companies(company_id),
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_source           TEXT DEFAULT 'computed',

    -- Composite
    moat_composite_score  NUMERIC,
    moat_rating           TEXT CHECK (moat_rating IN ('wide', 'narrow', 'weak', 'none')),

    -- Stage 1: Quantitative (top-level scores)
    stage1_composite_score NUMERIC,
    excess_return_score   NUMERIC,
    margin_resilience_score NUMERIC,
    fcf_quality_score     NUMERIC,

    roic_10yr_median      NUMERIC,
    roic_10yr_stability   NUMERIC,
    roic_vs_wacc_spread   NUMERIC,
    economic_profit       NUMERIC,
    incremental_roic_5yr  NUMERIC,
    wacc_used             NUMERIC,

    gross_margin_10yr_median   NUMERIC,
    gross_margin_10yr_stability NUMERIC,
    operating_margin_10yr_median NUMERIC,
    operating_margin_10yr_stability NUMERIC,

    fcf_conversion_10yr_median NUMERIC,
    fcf_conversion_10yr_stability NUMERIC,

    -- Stage 2: Moat Sources (text-derived scores)
    stage2_composite_score NUMERIC,
    switching_cost_score   NUMERIC,
    network_effect_score   NUMERIC,
    cost_advantage_score   NUMERIC,
    intangible_asset_score NUMERIC,
    efficient_scale_score  NUMERIC,
    primary_moat_source    TEXT,
    secondary_moat_source  TEXT,

    -- Stage 3: Durability & Risk
    stage3_composite_score NUMERIC,
    disruption_risk_score  NUMERIC,
    technological_risk     NUMERIC,
    regulatory_risk        NUMERIC,
    commoditization_risk   NUMERIC,
    customer_concentration_risk NUMERIC,
    capital_intensity_risk NUMERIC,

    -- Stage 4: Capital Allocation
    stage4_composite_score NUMERIC,
    buyback_yield_5yr_avg  NUMERIC,
    dividend_growth_5yr    NUMERIC,
    sbc_dilution_5yr_avg   NUMERIC,
    fcf_per_share_growth_5yr NUMERIC,

    -- Metadata & Lineage
    text_analysis_available   BOOLEAN DEFAULT FALSE,
    tenk_filing_date          DATE,
    tenk_fiscal_year          INTEGER,
    ai_narrative_available    BOOLEAN DEFAULT FALSE,
    confidence_score          NUMERIC DEFAULT 1.0,
    fallbacks_used            TEXT[],
    input_version_tag         TEXT,

    UNIQUE(company_id)
);

-- Detailed keyword evidence (separate table for expandability)
CREATE TABLE moat_keyword_evidence (
    evidence_id       INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    company_id        INTEGER NOT NULL REFERENCES companies(company_id),
    moat_source_type  TEXT NOT NULL CHECK (moat_source_type IN (
                          'switching_costs', 'network_effects', 'cost_advantage',
                          'intangible_assets', 'efficient_scale', 'disruption_risk'
                      )),
    keyword           TEXT NOT NULL,
    section           TEXT NOT NULL CHECK (section IN ('Item 1', 'Item 1A', 'Item 7', 'Proxy')),
    snippet           TEXT NOT NULL,
    match_count       INTEGER DEFAULT 1,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(company_id, moat_source_type, keyword, section)
);

-- AI narrative storage (optional, cached)
CREATE TABLE moat_ai_narratives (
    narrative_id    INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    model           TEXT NOT NULL,
    narrative       TEXT NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(company_id, model)
);
```

### 14.3 Data Flow: End-to-End Sequence

```
Frontend                          Backend API                        Service Layer                    Repositories / Providers            Supabase
─────────                        ───────────                        ─────────────                    ────────────────────────            ────────
                                                                                                                                   
 │                                  │                                    │                                    │                      │
 │  User navigates to               │                                    │                                    │                      │
 │  /analysis/AAPL                  │                                    │                                    │                      │
 │      │                           │                                    │                                    │                      │
 │      ▼                           │                                    │                                    │                      │
 │  page.tsx mounts                 │                                    │                                    │                      │
 │  prefetchAllValuations()         │                                    │                                    │                      │
 │  → prefetchMoatAnalysis()        │                                    │                                    │                      │
 │      │                           │                                    │                                    │                      │
 │      ▼                           │                                    │                                    │                      │
 │  useQuery QK.moat("AAPL")        │                                    │                                    │                      │
 │  GET /api/proxy/analysis/        │                                    │                                    │                      │
 │       AAPL/moat                  │                                    │                                    │                      │
 │      │──────────────────────────►│                                    │                                    │                      │
 │                                  │  _get_moat_service()              │                                    │                      │
 │                                  │  → MoatAnalysisService            │                                    │                      │
 │                                  │  get_moat_analysis("AAPL")        │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  get_company_context("AAPL")      │                                    │                      │
 │                                  │───────────────────────────────────────────────────────────────────────►                      │
 │                                  │                                    │   SELECT company_id, sector,     │                      │
 │                                  │                                    │   industry, currency, company_name│                      │
 │                                  │◄───────────────────────────────────────────────────────────────────────                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  _check_cache(company_id)         │                                    │                      │
 │                                  │───────────────────────────────────────────────────────────────────────►                      │
 │                                  │                                    │   SELECT * FROM moat_analysis     │                      │
 │                                  │                                    │   WHERE company_id = ?           │                      │
 │                                  │◄───────────────────────────────────────────────────────────────────────                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼ (cache miss or stale)      │                                    │                      │
 │                                  │                                    │                                    │                      │
 │  ────── PARALLEL COMPUTATION ────│────────────────────────────────────│────────────────────────────────────│──────────────────────│
 │                                  │                                    │                                    │                      │
 │                                  │  _compute_stage1_quantitative()    │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ├─ WaccService.compute()      │                                    │                      │
 │                                  │      │     │                       │   SELECT beta, market_cap,         │                      │
 │                                  │      │     │                       │   total_debt, interest_expense,    │                      │
 │                                  │      │     │                       │   pretax_income, tax_expense      │                      │
 │                                  │      │     │───────────────────────────────────────────────────────────►                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     │                       │   WACC = E/V × Re + D/V × Rd×(1-Tc)│                      │
 │                                  │      │     │◄───────────────────────────────────────────────────────────                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      ├─ get_financial_ratios_10yr()│                                    │                      │
 │                                  │      │     │                       │   SELECT roic, gross_margin,       │                      │
 │                                  │      │     │                       │   operating_margin, fcf_conversion │                      │
 │                                  │      │     │                       │   WHERE fiscal_quarter IS NULL     │                      │
 │                                  │      │     │                       │   ORDER BY fiscal_year            │                      │
 │                                  │      │     │───────────────────────────────────────────────────────────►                      │
 │                                  │      │     │◄───────────────────────────────────────────────────────────                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     │   Compute:            │                                    │                      │
 │                                  │      │     │   • median, std dev   │                                    │                      │
 │                                  │      │     │   • economic profit   │                                    │                      │
 │                                  │      │     │   • incremental ROIC  │                                    │                      │
 │                                  │      │     │   • recession ROIC    │                                    │                      │
 │                                  │      │     │   • margin stability  │                                    │                      │
 │                                  │      │     │   • FCF quality       │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      ▼    │                       │                                    │                      │
 │                                  │  _compute_stage2_moat_sources()    │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ├─ MoatTextService.analyze_   │                                    │                      │
 │                                  │      │     moat_sources(symbol)    │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     │  EdgarFilingService   │                                    │                      │
 │                                  │      │     │  .get_latest_tenk()   │                                    │                      │
 │                                  │      │     │──────────────────────────────────────►                     │                      │
 │                                  │      │     │                       │   Company("AAPL")                 │                      │
 │                                  │      │     │                       │   .get_filings(form="10-K")       │                      │
 │                                  │      │     │                       │   .latest() → Filing              │                      │
 │                                  │      │     │                       │   .obj() → TenK                  │                      │
 │                                  │      │     │◄───────────────────────────────────────                     │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     │  Extract sections:    │                                    │                      │
 │                                  │      │     │  • Item 1 = tenk["Item 1"]                                  │                      │
 │                                  │      │     │  • Item 1A = tenk["Item 1A"]                                │                      │
 │                                  │      │     │  • Item 7 = tenk["Item 7"]                                  │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     │  MoatKeywordAnalyzer   │                                    │                      │
 │                                  │      │     │  .analyze_*() ×5      │                                    │                      │
 │                                  │      │     │  → scores + keywords  │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     │  Save keyword evidence│                                    │                      │
 │                                  │      │     │───────────────────────────────────────────────────────────►                      │
 │                                  │      │     │                       │   INSERT INTO moat_keyword_evidence │                      │
 │                                  │      │     │◄───────────────────────────────────────────────────────────                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      ▼     │                       │                                    │                      │
 │                                  │  _compute_stage3_durability()      │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ├─ MoatTextService            │                                    │                      │
 │                                  │      │    .analyze_disruption_risk │                                    │                      │
 │                                  │      │    (Item 1A text)           │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      ├─ get_financial_ratios       │                                    │                      │
 │                                  │      │    (debt/equity,            │                                    │                      │
 │                                  │      │     interest coverage,      │                                    │                      │
 │                                  │      │     capex/revenue)          │                                    │                      │
 │                                  │      │──────────────────────────────────────────────────────────────────►                      │
 │                                  │      │◄──────────────────────────────────────────────────────────────────                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  _compute_stage4_allocation()      │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ├─ get_cash_flow_annual()     │                                    │                      │
 │                                  │      ├─ get_dividend_metrics()     │                                    │                      │
 │                                  │      ├─ get_company_summary()      │                                    │                      │
 │                                  │      │──────────────────────────────────────────────────────────────────►                      │
 │                                  │      │◄──────────────────────────────────────────────────────────────────                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  _compute_composite_score()        │                                    │                      │
 │                                  │    weighted_avg of 4 stages        │                                    │                      │
 │                                  │    → 0-100 → rating               │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  _save_to_cache()                 │                                    │                      │
 │                                  │───────────────────────────────────────────────────────────────────────►                      │
 │                                  │                                    │   UPSERT INTO moat_analysis       │                      │
 │                                  │                                    │   (all columns)                   │                      │
 │                                  │◄───────────────────────────────────────────────────────────────────────                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  return MoatAnalysisResponse       │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │◄──────────────────────────────────│      │                            │                                    │                      │
 │      │                            │                                    │                                    │                      │
 │      ▼                            │                                    │                                    │                      │
 │  React Query caches response      │                                    │                                    │                      │
 │  → MoatPanel renders              │                                    │                                    │                      │
 │  → Stage1QuantPanel,              │                                    │                                    │                      │
 │    Stage2MoatSourcesPanel, etc.    │                                    │                                    │                      │
 │      │                            │                                    │                                    │                      │
 │      ▼ (optional)                 │                                    │                                    │                      │
 │  User clicks "Generate AI"        │                                    │                                    │                      │
 │  → useMoatAiNarrative mutation    │                                    │                                    │                      │
 │  POST /api/proxy/analysis/        │                                    │                                    │                      │
 │       AAPL/moat/ai                │                                    │                                    │                      │
 │      │──────────────────────────►│                                    │                                    │                      │
 │                                  │  generate_ai_narrative(symbol)      │                                    │                      │
 │                                  │      │                            │                                    │                      │
 │                                  │      ├─ MoatAiService              │                                    │                      │
 │                                  │      │  .generate_moat_narrative    │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     ├─ Collect keyword      │                                    │                      │
 │                                  │      │     │  scores + quant data  │                                    │                      │
 │                                  │      │     │  from moat_analysis   │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     ├─ Build prompt         │                                    │                      │
 │                                  │      │     │  (see Section 11.4)   │                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     ├─ Call OpenRouter      │                                    │                      │
 │                                  │      │     │  POST /v1/chat/       │                                    │                      │
 │                                  │      │     │  completions          │                                    │                      │
 │                                  │      │     │──── OpenRouter ───►   │                                    │                      │
 │                                  │      │     │◄─── AI response ─────│                                    │                      │
 │                                  │      │     │                       │                                    │                      │
 │                                  │      │     └─ Parse + cache        │                                    │                      │
 │                                  │      │        → MoatAiNarrative    │                                    │                      │
 │                                  │      │                             │                                    │                      │
 │                                  │      ▼                            │                                    │                      │
 │                                  │  return MoatAiResponse             │                                    │                      │
 │◄──────────────────────────────────│      │                            │                                    │                      │
 │      │                            │                                    │                                    │                      │
 │      ▼                            │                                    │                                    │                      │
 │  MoatPanel renders AI section     │                                    │                                    │                      │
 │  with narrative text              │                                    │                                    │                      │
 │                                    │                                    │                                    │                      │
```

---

## 15. Performance Requirements

This section defines the non-negotiable performance SLAs for the MOAT analysis feature. These targets govern the implementation and must be validated by the performance tests in §16.7.

### 15.1 API & Computation SLAs

| ID | Operation | Target (P95) | Max (P99) | Measurement | Notes |
|----|-----------|-------------|-----------|-------------|-------|
| PR-01 | Fresh moat computation (cache miss, full pipeline incl. EDGAR text) | ≤ 8 s | ≤ 15 s | Server-side wall clock | EDGAR text fetch is the bottleneck; quant-only path must be ≤ 2 s |
| PR-02 | Cached moat response (no text re-fetch) | ≤ 500 ms | ≤ 1 s | Server-side wall clock | Standard React Query cache hit; single DB query |
| PR-03 | EDGAR 10-K text fetch + parse | ≤ 5 s | ≤ 10 s | Server-side wall clock | Circuit breaker triggers after 10 s; fallback to quant-only |
| PR-04 | Keyword analysis on 50K+ word text | ≤ 500 ms | ≤ 1 s | Server-side wall clock | Entirely in-memory; no I/O beyond input read |
| PR-05 | WACC computation | ≤ 200 ms | ≤ 500 ms | Server-side wall clock | Reuses pre-computed beta, Rf, ERP from DB |
| PR-06 | AI narrative generation (OpenRouter) | ≤ 8 s | ≤ 15 s | Server-side wall clock | Network-bound; user sees loading state |
| PR-07 | DB upsert (`moat_analysis` row) | ≤ 100 ms | ≤ 250 ms | Query execution time | Single-row upsert with index on (symbol, computed_at) |
| PR-08 | DB read (`moat_analysis` by symbol) | ≤ 50 ms | ≤ 100 ms | Query execution time | Indexed lookup; returns latest row by computed_at |

### 15.2 Frontend SLAs

| ID | Metric | Target | Measurement | Notes |
|----|--------|--------|-------------|-------|
| PR-09 | Initial render (loading skeleton) | ≤ 200 ms | Lighthouse TTI | Skeleton shimmer must appear immediately; no layout shift |
| PR-10 | Full render with all 4 stages + evidence | ≤ 500 ms | Lighthouse TTI | React Query cache hydrate + DOM paint |
| PR-11 | Score ring animation (0 → final %) | ≤ 600 ms | requestAnimationFrame | CSS transition; not JS-blocked |
| PR-12 | Expand/collapse keyword evidence | ≤ 50 ms | User-perceived | Instant; no network call |
| PR-13 | AI narrative loading state → text render | ≤ 300 ms after API response | User-perceived | Minimal re-render; no spinner stuck after data arrives |
| PR-14 | Bundle size contribution | ≤ 50 KB (gzip) | Webpack/Rollup analyze | No heavy charting libs; score rings are pure SVG |

### 15.3 Concurrent Load & Throughput

| ID | Scenario | Requirement | Notes |
|----|----------|-------------|-------|
| PR-15 | 10 concurrent fresh computations (different symbols) | All complete within 30 s, zero errors | EDGAR rate limiting is primary risk; circuit breaker + queue |
| PR-16 | 100 concurrent cached reads (same symbol) | All respond ≤ 500 ms, zero errors | Connection pool sizing; cached path must not touch EDGAR |
| PR-17 | 50 concurrent reads (mixed symbols, mixed cache states) | 95th percentile ≤ 1 s, error rate < 1% | Representative real-world load |
| PR-18 | Sustained load (100 req/min for 5 min) | No degradation; no OOM; no connection pool exhaustion | Longevity test |

### 15.4 Resource Constraints

| Resource | Limit | Trigger | Action |
|----------|-------|---------|--------|
| EDGAR calls per minute | 10 req/min (SEC guideline) | 11th request in rolling window | Queue/wait; if queue > 50, return 429 |
| EDGAR concurrent calls | 2 simultaneous | 3rd concurrent request | Serialize; queue remaining |
| OpenRouter API calls | $10/month budget | Monthly spend > $8 | Auto-disable AI narrative; return 503 "AI unavailable" |
| Worker memory per moat computation | ≤ 512 MB RSS | > 512 MB | Abort computation; log metric; return 500 |
| Worker CPU per computation | ≤ 30 s CPU time | > 30 s | Timeout; return 503 "Computation timed out" |

### 15.5 Caching Requirements

| Cache Layer | Object | TTL | Invalidation |
|-------------|--------|-----|--------------|
| React Query (browser) | MoatAnalysisResponse | 5 min | On manual recompute |
| React Query (browser) | MoatEvidenceResponse | Session (tab close) | N/A (user-triggered only) |
| React Query (browser) | MoatAiResponse | Session | N/A (user-triggered only) |
| Backend DB | moat_analysis row | 24 h | Replaced on re-compute; never invalidated early |
| Backend DB | moat_keyword_evidence rows | Indefinite (until new 10-K filing_date) | New row inserted on re-compute; old rows orphaned |
| Backend DB | moat_ai_narratives row | Indefinite | Regenerated only on user demand |
| EDGAR text (in-memory) | Raw 10-K sections | Request-scoped | Discarded after keyword analysis completes |

### 15.6 Performance Budget Summary

```
┌────────────────────────────────────────────────┐
│          MOAT Performance Budget               │
├────────────────────────────────────────────────┤
│  P95 fresh compute:         8s                │
│  P95 cached fetch:          500ms             │
│  P95 EDGAR fetch+parse:     5s                │
│  P95 keyword analysis:      500ms             │
│  P95 WACC compute:          200ms             │
│  Frontend TTI (full):       500ms             │
│  Bundle contribution:       50KB gzip         │
│  Concurrent compute (10):   all ≤30s, 0 err   │
└────────────────────────────────────────────────┘
```

---

## 16. Comprehensive Test Plan

### 16.1 Test Strategy Overview

| Test Level | Scope | Automation | Who Runs |
|-----------|-------|-----------|----------|
| Unit Tests | Individual service methods, keyword analyzer, WACC calc | pytest (backend), Vitest (frontend) | CI + Dev |
| Integration Tests | Service + Repository + Supabase | pytest with test DB | CI |
| API Tests | FastAPI endpoints (mock services) | pytest + httpx | CI |
| Component Tests | Individual React components | Vitest + React Testing Library | CI |
| E2E Tests | Full UI → Backend → Supabase pipeline | Playwright/Cypress | CI + Pre-release |
| Edge Case Tests | Error states, empty states, sector exclusions | pytest parameterized | Dev |
| Performance Tests | Latency under load, EDGAR text extraction timing | locust / custom script | Pre-release |

### 16.2 Backend Unit Tests

#### Test Suite: TestWaccService

| ID | Test Case | Input | Expected Output | Validates |
|----|-----------|-------|-----------------|-----------|
| UT-WACC-01 | Standard WACC with all inputs | company with beta=1.2, D/E=0.5, Tc=21%, Rf=4.5%, ERP=5.5% | WACC ≈ 8.9% (±0.01) | Correct formula application |
| UT-WACC-02 | Zero debt company | beta=1.0, D/E=0, Tc=21% | WACC = Rf + β×ERP = 10.0% | Debt-free company WACC = Re |
| UT-WACC-03 | Negative beta | beta=-0.5 | WACC = max(Rf + β×ERP, 3%) floor | Beta floor protection |
| UT-WACC-04 | Missing beta | beta=None | Uses default beta=1.0 | Graceful fallback |
| UT-WACC-05 | Missing tax rate | tax_rate=None | Assumes Tc=21% | Default assumption |

#### Test Suite: TestMoatKeywordAnalyzer

| ID | Test Case | Input | Expected Output | Validates |
|----|-----------|-------|-----------------|-----------|
| UT-KWD-01 | Strong switching cost signals | Text containing "retention rate", "lock-in", "long-term contracts", "mission critical" | Score ≥ 4.0, 4+ keyword matches with snippets | Multi-keyword detection |
| UT-KWD-02 | Weak/no switching costs | Generic text: "We sell products to customers" | Score ≤ 1.0, 0-1 matches | No false positives |
| UT-KWD-03 | Negative signal (churn mentioned) | "churn rate increased to 15%" | Lower score than without churn | Negative weighting |
| UT-KWD-04 | Multiple section coverage | Same keyword in Item 1 AND Item 7 | Higher score than single section | Section multiplier |
| UT-KWD-05 | Network effects detection | "two-sided platform connecting users and merchants" | Score ≥ 3.5, network_effect_type detected | Category-specific matching |
| UT-KWD-06 | Empty text input | text="" | Score = 0, empty matches list | Edge case handling |
| UT-KWD-07 | Very long text (entire 10-K) | Full 10-K text (50,000+ words) | Completes in <500ms, returns results | Performance requirement |
| UT-KWD-08 | Case insensitivity | "Switching Costs", "SWITCHING COSTS", "switching costs" | All match identically | Normalization |
| UT-KWD-09 | Phrase boundary matching | "plat" in "platform" vs "platform" keyword | Does not match partial word | Word boundary integrity |
| UT-KWD-10 | All 5 moat types scored simultaneously | Full 10-K Item 1, 1A, 7 text | All 5 scores returned within 2s | Multi-type performance |

#### Test Suite: TestMoatQuantService

| ID | Test Case | Input | Expected Output | Validates |
|----|-----------|-------|-----------------|-----------|
| UT-QUANT-01 | ROIC analysis with 10yr data | 10 years of financial_ratios | Median, stability, spread computed correctly | Statistical accuracy |
| UT-QUANT-02 | ROIC with missing years | Only 3 years of data | Computed with available data, confidence reduced | Graceful degradation |
| UT-QUANT-03 | Economic profit calculation | ROIC=15%, WACC=8%, IC=$10B | EP = $700M | Formula correctness |
| UT-QUANT-04 | Incremental ROIC with growth | NOPAT: 800→900→1000, IC: 4000→4200→4500 | Incr ROIC ≈ 28-33% range | Delta calculation |
| UT-QUANT-05 | Incremental ROIC with declining | NOPAT decreasing, IC increasing | Negative/missing incremental ROIC | Handles value destruction |
| UT-QUANT-06 | Margin stability with volatile | Margins: 20%, 15%, 25%, 10%, 18% | Stability score < 50 (high volatility) | Volatility detection |
| UT-QUANT-07 | Perfect margin stability | All margins = 20% for 10 years | Stability score = 100 | Perfect stability detection |
| UT-QUANT-08 | FCF conversion edge cases | NI=0, FCF>0; NI>0, FCF=-100M | Returns None with fallback note | Division by zero protection |

### 16.3 Integration Tests

#### Test Suite: TestMoatAnalysisService

| ID | Test Case | Input | Expected Output | Validates |
|----|-----------|-------|-----------------|-----------|
| IT-MOAT-01 | Full analysis for well-known stock | Symbol="AAPL" (Apple) | Wide moat (75-95), Intangible Assets primary, score > 70 | End-to-end pipeline |
| IT-MOAT-02 | Analysis for no-moat company | Symbol="SNAP" or similar weak-moat candidate | Narrow/weak moat (30-50), lower text scores | Discriminating power |
| IT-MOAT-03 | Analysis for Canadian stock | Symbol="SHOP" (TSX-listed) | Completes successfully, EDGAR text may be unavailable for Canadian filers (20-F vs 10-K) | Canadian/non-US handling |
| IT-MOAT-04 | Sector-excluded company | Symbol="JPM" (Financial) | Adjusted scoring for financial sector, methodology note displayed | Sector applicability |
| IT-MOAT-05 | Cache hit returns cached data | First call, wait 1s, second call | Second call returns same data, no recomputation | Cache working |
| IT-MOAT-06 | Force recompute | force=true | New computation, updated computed_at | Force refresh |
| IT-MOAT-07 | Company with no 10-K on EDGAR | Small foreign company | Quant scores available; text_analysis_available=false | Graceful degradation |
| IT-MOAT-08 | Company with recent 10-K | Filed within last 3 months | tenk_filing_date populated, text_analysis_available=true | Filing freshness |

#### Test Suite: TestEdgarFilingService

| ID | Test Case | Input | Expected Output | Validates |
|----|-----------|-------|-----------------|-----------|
| IT-EDGAR-01 | Fetch latest 10-K for AAPL | "AAPL" | TenK object returned, non-empty Item 1 text, Item 1A text, Item 7 text | Section extraction |
| IT-EDGAR-02 | Fetch 10-K for non-EDGAR company | Non-existent symbol | Returns None, logs warning | Graceful failure |
| IT-EDGAR-03 | Extract section by name | TenK, "Item 1" | Returns business description text (1000+ words) | Section accessor |
| IT-EDGAR-04 | Extract section Item 1A | TenK, "Item 1A" | Returns risk factors text | Risk factor extraction |
| IT-EDGAR-05 | Extract section Item 7 | TenK, "Item 7" | Returns MD&A text | MD&A extraction |
| IT-EDGAR-06 | Performance: filing fetch + parse | Any symbol | Completes in <5 seconds | Performance requirement |
| IT-EDGAR-07 | Proxy statement (DEF 14A) fetch | "AAPL" | ProxyStatement with executive_compensation data | Proxy parsing |

### 16.4 API Tests

| ID | Test Case | Endpoint | Expected Status | Validates |
|----|-----------|----------|-----------------|-----------|
| API-01 | Get moat analysis for valid symbol | GET /{symbol}/moat | 200, MoatAnalysisResponse | Happy path |
| API-02 | Get moat analysis for unknown symbol | GET /ZZZZZ/moat | 404, detail message | Error handling |
| API-03 | Get moat analysis with force=true | GET /{symbol}/moat?force=true | 200, fresh computed_at | Force parameter |
| API-04 | Get moat evidence for valid symbol | GET /{symbol}/moat/evidence | 200, MoatEvidenceResponse | Evidence endpoint |
| API-05 | Get moat evidence without text | GET /{symbol}/moat/evidence (no 10-K) | 200, text_analysis_available=false | Graceful text missing |
| API-06 | Generate AI narrative | POST /{symbol}/moat/ai | 200, MoatAiResponse with narrative | AI endpoint |
| API-07 | Generate AI narrative when AI disabled | POST /{symbol}/moat/ai (AI disabled) | 503, "AI analysis not available" | Feature flag |
| API-08 | Invalid symbol format | GET /INVALID@@@/moat | 422, validation error | Input sanitization |
| API-09 | Rate limiting | 31 requests in 1 minute | 429, rate limit exceeded | Rate limiter |

### 16.5 Frontend Component Tests

| ID | Test Case | Component | Input | Expected Behavior |
|----|-----------|-----------|-------|-------------------|
| FT-01 | Render loading state | MoatPanel | loading=true | Shows skeleton shimmer (4 cards animating) |
| FT-02 | Render error state | MoatPanel | error="Failed to load" | Red error banner with "Retry" button |
| FT-03 | Render full analysis | MoatPanel | valid MoatAnalysisResponse | All 4 stages rendered, header with rating |
| FT-04 | Render "not computed" state | MoatPanel | notComputed=true | CTA button "Compute Moat Analysis" centered |
| FT-05 | Click recompute | MoatPanel | user clicks "⟳ Recompute" | Loading state shown, API called with force=true |
| FT-06 | Score ring colors | ScoreRing | score=92 (Wide) | Green color (#22c55e) |
| FT-07 | Score ring colors | ScoreRing | score=45 (None) | Red color (#ef4444) |
| FT-08 | Expand/collapse keyword evidence | MoatSourceCard | user clicks "▶" | Keyword list expands with snippets |
| FT-09 | View evidence details | MoatPanel | user clicks "View Evidence Details" | TextEvidenceGallery opens as modal or section |
| FT-10 | Generate AI narrative | AiNarrativeCard | user clicks "✨ Generate AI" | Loading spinner, then narrative text appears |
| FT-11 | Stale data warning | MoatHeader | data stale > 24h | Warning banner "Data may be stale" |
| FT-12 | Responsive layout (mobile) | MoatPanel | viewport < 768px | Single column, all sections collapsible |
| FT-13 | Sector excluded notice | MoatPanel | sector="Financials" | Methodology adjustment notice displayed |
| FT-14 | Tooltip on score hover | RoicCard | user hovers on score | Tooltip shows "10yr median ROIC: 32.4%" |
| FT-15 | Accessibility: keyboard nav | MoatPanel | Tab through all interactive elements | All buttons/links reachable, visible focus |

### 16.6 End-to-End Tests

| ID | Test Scenario | Steps | Expected Result | Validates |
|----|--------------|-------|-----------------|-----------|
| E2E-01 | First-time user views moat analysis | 1. Navigate to /analysis/AAPL<br>2. Click "Moat" tab<br>3. Wait for loading to complete | Full moat dashboard renders with all 4 stages, wide moat rating | Full pipeline |
| E2E-02 | EDGAR evidence details | 1. Follow E2E-01<br>2. Click "View Evidence Details" | Evidence gallery shows Item 1, Item 1A, Item 7 excerpts with keyword highlights | Text extraction |
| E2E-03 | AI narrative generation | 1. Follow E2E-01<br>2. Click "Generate AI Moat Assessment"<br>3. Wait for text to appear | Narrative text appears in AI section, stored for future visits | AI integration |
| E2E-04 | Recompute analysis | 1. Follow E2E-01<br>2. Click "⟳ Recompute"<br>3. Observe loading then refresh | Data refreshes, computed_at updates | Force recompute |
| E2E-05 | Mobile responsive | 1. Open /analysis/AAPL on mobile viewport<br>2. Click "Moat" tab | Single column layout, all sections readable | Responsive design |
| E2E-06 | Error recovery | 1. Navigate to /analysis/INVALID<br>2. Click "Moat" tab | Error message displayed, "Retry" or "Go Back" option | Error handling |
| E2E-07 | Sector excluded company | 1. Navigate to /analysis/JPM<br>2. Click "Moat" tab | Scores computed with financial sector adjustment, methodology note visible | Sector handling |
| E2E-08 | No 10-K available | 1. Find a non-SEC-filing company<br>2. Click "Moat" tab | Quant scores shown, text analysis section shows "unavailable" | Graceful degradation |

### 16.7 Performance Tests

| ID | Test Case | Scenario | Acceptable Threshold | Measurement |
|----|-----------|----------|---------------------|-------------|
| PERF-01 | First time moat computation | Cache miss, full pipeline | < 8 seconds (incl EDGAR text fetch) | P95 latency |
| PERF-02 | Cached moat response | Cache hit, return stored data | < 500ms | P95 latency |
| PERF-03 | EDGAR text extraction only | Fetch and parse 10-K | < 5 seconds | P95 latency |
| PERF-04 | Keyword analysis only | Analyze 50K chars text | < 500ms | P50 latency |
| PERF-05 | Concurrent requests (10 users) | 10 simultaneous moat requests | < 30s for all to complete, no errors | Throughput |
| PERF-06 | Frontend render time | MoatPanel with full data | < 200ms initial render | Lighthouse score |
| PERF-07 | AI narrative generation | OpenRouter API call | < 8 seconds | P95 latency |
| PERF-08 | Database query time | moat_analysis upsert | < 100ms | Query execution time |

### 16.8 Edge Case & Negative Tests

| ID | Test Case | Expected Behavior |
|----|-----------|------------------|
| NEG-01 | Company with negative equity | WACC computation adjusts; ROE is None; moat score based on available metrics |
| NEG-02 | Company with no income statements | Stage 1 quant scores = None; Stage 2 text still works; overall = "Insufficient data" |
| NEG-03 | Company with zero debt | WACC = Re (cost of equity only); capital structure risk = 0 |
| NEG-04 | Company with 100+ year existence | 10yr median works fine; history beyond 10 years not needed |
| NEG-05 | Penny stock / micro-cap | EDGAR may not have XBRL filings (smaller filers exempt); falls back to quant-only or unavailable |
| NEG-06 | Company just IPO'd (< 2 years public) | Limited financial history; confidence score reduced |
| NEG-07 | Company in bankruptcy proceedings | EDGAR may have delinquent filing status; data may be stale |
| NEG-08 | Dual-listed company (e.g., trading on NYSE + TSX) | Uses primary ticker from companies table; should handle correctly |
| NEG-09 | Company changed fiscal year | Income statement data has gap year; median calculation handles missing years |
| NEG-10 | 10-K text with extensive tables/HTML | HTML tags stripped; tables may lose formatting; keyword analysis on cleaned text |
| NEG-11 | 10-K in foreign language (e.g., Canadian French) | Will still match English keywords poorly; lower scores expected |
| NEG-12 | Multiple 10-K filings in same year (restatement) | Uses latest filing date; text from restated filing |
| NEG-13 | EDGAR rate limit hit | Circuit breaker; waits; retries with backoff; falls back to quant-only |
| NEG-14 | OpenRouter API timeout | AI narrative returns timeout error; user can retry later |
| NEG-15 | Company name mismatch (EDGAR vs DB) | Uses ticker symbol for EDGAR lookup; if fails, tries CIK mapping |

### 16.9 Test Data Requirements

| Data Type | Test Fixture | Purpose |
|-----------|-------------|---------|
| Mock financial_ratios (10yr) | 5 companies: Apple, Microsoft, Snap, JPMorgan, small_unknown | Unit test quant calculation |
| Mock EDGAR 10-K text | Pre-extracted sections for Apple, Microsoft, Snap | Unit test keyword analysis (no live API calls) |
| Mock company_context | 5 companies with varying sectors | Test sector handling |
| Mock OpenRouter response | Pre-recorded JSON for AI prompt | Test AI narrative parsing |
| Integration test DB | Supabase test project with seeded data | Integration tests |
| E2E test companies | AAPL, MSFT, SNAP, JPM, TEST | End-to-end tests |
| EDGAR test cache | Cached TenK objects (pickled) | Avoid rate limits in CI |

### 16.10 Test Automation & CI Pipeline

```
Pre-commit → Backend: ruff + mypy
            Frontend: prettier + eslint
                  ↓
PR → Backend Unit Tests (pytest -m "not integration")
   → Frontend Unit Tests (vitest)
   → TypeScript type check
                  ↓
Merge → Backend All Tests (pytest, including integration with test Supabase)
      → Frontend All Tests (vitest + component tests)
      → E2E Tests (Playwright) [scheduled, not blocking]
                  ↓
Release → Performance Tests (locust)
        → Full E2E Suite (Playwright)
        → Security Scan
```

---

## 17. Moats vs Existing Pattern: Key Differences

| Aspect | Other Tabs (CANSlim, Magic Formula) | Moat Tab |
|--------|--------------------------------------|----------|
| **Primary data source** | Financial DB tables only | Financial DB + EDGAR text extraction |
| **External API calls** | None (data already in DB) | EDGAR text fetch (10-K filing) |
| **External API (optional)** | None | OpenRouter AI for narrative |
| **Cache strategy** | 24h via valuation_runs table | 24h quant cache + indefinite text cache (until new 10-K) |
| **Computation complexity** | Single-pass calculations | Multi-stage weighted composite scoring |
| **Response size** | ~5-15KB | ~20-50KB (includes keyword evidence) |
| **New DB tables** | None needed | `moat_analysis`, `moat_keyword_evidence`, `moat_ai_narratives` |
| **Fallback complexity** | Simple (data available or not) | Layered (quant available, text may or may not be) |
| **Sector handling** | Simple exclusion (financials) | Scoring adjustments per sector |
| **User interaction** | View-only | View + "View Evidence" + "Generate AI" |
| **AI dependency** | None | Optional, toggled by user |

---

## 18. Summary: Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Text extraction approach | Python keyword-based (primary) + AI (optional) | Deterministic, fast, debuggable; AI adds nuance without replacing core |
| Text caching | Store only scores + keyword snippets in DB; fetch raw text from SEC on recompute | Minimizes storage; text is static and fast to re-fetch |
| Score storage | Dedicated `moat_analysis` table (not `financial_ratios`) | Conceptual separation; independent cache lifetime |
| Keyword evidence storage | Separate `moat_keyword_evidence` table | Expandable; can add new keyword types without schema changes |
| AI narrative storage | `moat_ai_narratives` table (one per company per model) | Cached indefinitely; regenerated only on demand |
| WACC computation | CAPM-based service (existing ResidualIncomeService pattern) | Reuses existing beta, Rf, ERP infrastructure |
| Sector adjustments | Scoring modifiers, not hard exclusions | More nuanced than Magic Formula's binary exclusion |
| EDGAR filing access | New `EdgarFilingService` (not extending `EdgarToolsProvider`) | Separation of concerns: text extraction ≠ financial statement fallback |
| Frontend state | React Query with 3 separate queries (analysis, evidence, AI) | Analysis auto-loads; evidence and AI are user-triggered |
| Responsive design | CSS Grid with breakpoint-based column count | Clean layout at all screen sizes |


