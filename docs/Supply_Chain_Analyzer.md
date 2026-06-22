# StockerPro — Supply Chain Bottleneck Analyser
## Technical Design Document v3.0

**Version:** 3.0  
**Date:** June 2026  
**Author:** StockerPro Engineering  
**Stack:** Next.js 15 / React 19 / TypeScript · FastAPI / Python · Supabase (PostgreSQL)  
**Supersedes:** v2.0 — adds OpenRouter integration, complete implementations, environment config, UI error states, full schema, all previously-stubbed methods

---

## Table of Contents

1. [Overview and Purpose](#1-overview-and-purpose)
2. [Core Architectural Principle](#2-core-architectural-principle)
3. [Environment Configuration](#3-environment-configuration)
4. [Use Cases](#4-use-cases)
5. [High-Level Architecture](#5-high-level-architecture)
6. [Database Schema](#6-database-schema)
7. [Dependent Libraries](#7-dependent-libraries)
8. [Path A — Background Pipeline](#8-path-a--background-pipeline)
9. [Path B — UI Read Layer](#9-path-b--ui-read-layer)
10. [Sequence Diagrams](#10-sequence-diagrams)
11. [Class Diagram](#11-class-diagram)
12. [API Contract](#12-api-contract)
13. [Implementation Plan](#13-implementation-plan)
14. [Open Risks and Limitations](#14-open-risks-and-limitations)

---

## 1. Overview and Purpose

StockerPro's Supply Chain Bottleneck Analyser identifies layers within an industry value chain where supply is structurally constrained, then decomposes companies in those layers recursively to fundamental physics and manufacturing constraints — and maps those constraints to the upstream oligopoly stacks that control them.

**Question 1 — Supply chain layer:** Which layer in the AI Infrastructure theme is the structural bottleneck?

**Question 2 — Capability depth:** Why is Hamamatsu Photonics hard to replicate? What physical constraints underlie its moat, and which upstream companies control those constraints?

Both questions are answered entirely by a background pipeline. The UI reads pre-built results. No LLM calls occur in the user request path.

### What changed from v2.0

- LLM provider changed from Anthropic API to **OpenRouter** with primary/fallback model strategy
- `openrouter_client.py` replaces `anthropic_client.py` — full implementation provided
- OpenRouter rate limit (20 req/min free tier) handled via `AsyncLimiter`
- All environment variables documented with descriptions
- `layer_config` JSONB structure fully defined with seed data for all 5 themes
- `sc_capability_nodes` adds `llm_error` and `llm_model_used` columns
- `_persist_tree`, `_parse_nodes`, `_build_prompt`, `_check_new_filings`, `_build_nested_tree` all fully implemented
- Tree endpoint shows exact assembly from flat DB rows
- `useCapabilityTree` and `useRecompute` React hooks fully specified
- UI error states (State 5) for missing or failed trees
- Failure and retry sequence diagrams added

---

## 2. Core Architectural Principle

**The pipeline owns all intelligence. The UI owns only navigation.**

Every LLM call, every external API request, every concentration calculation happens in Path A on a background schedule. By the time a user opens the UI, the following are already in Supabase:

- Supply chain graph for every active theme — nodes, edges, HHI, CR3, betweenness, bottleneck flags
- Financial scores for every company in a bottleneck layer — gross margin trend, ROIC spread, backlog ratio, confidence flag
- Full capability tree for every bottleneck company — decomposed recursively to root constraints
- Controlling company oligopoly stacks at every depth — including private companies with roles
- Financial enrichment for public companies in controlling stacks — stored at build time, not fetched live
- Root constraint label, rationale, and cross-industry applications for each company

The UI receives the entire tree in one `<200ms` DB read. All expand, collapse, and companies drawer interactions are pure React state changes — zero network calls after the initial load.

---

## 3. Environment Configuration

### 3.1 Backend (.env in FastAPI root)

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # Service role key — NOT anon key. Required for pipeline writes (bypasses RLS).

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_PRIMARY_MODEL=deepseek/deepseek-r1:free
OPENROUTER_FALLBACK_MODEL=google/gemma-4-31b-it:free
OPENROUTER_SITE_URL=https://stockerpro.app   # Sent as HTTP-Referer header
OPENROUTER_SITE_NAME=StockerPro              # Sent as X-Title header

# External data APIs
OPENBB_API_KEY=...
COMTRADE_API_KEY=...     # Register at comtradeplus.un.org

# Pipeline behaviour
PIPELINE_MAX_DEPTH=4                    # Maximum capability tree depth (default 4)
PIPELINE_MAX_COMPANIES_PER_THEME=8     # Max companies to build trees for per theme
PIPELINE_LLM_RATE_LIMIT_PER_MIN=18    # Stay under OpenRouter 20/min free limit
PIPELINE_WEEKLY_RUN_DAY=sun
PIPELINE_WEEKLY_RUN_HOUR=2
PIPELINE_TIMEZONE=America/Toronto

# Admin
PIPELINE_ADMIN_KEY=...   # For POST /supply-chain/admin/* endpoints only
```

### 3.2 Frontend (.env.local in Next.js root)

```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_BASE_URL=https://api.stockerpro.app
```

### 3.3 OpenRouter free tier notes

The free tier enforces **20 requests per minute** globally per API key. `PIPELINE_LLM_RATE_LIMIT_PER_MIN=18` leaves 2 req/min headroom. Both `deepseek/deepseek-r1:free` and `google/gemma-4-31b-it:free` support `response_format: {"type": "json_object"}`. To upgrade to paid, remove `:free` suffix and add credits at openrouter.ai — no code changes required.

---

## 4. Use Cases

### UC-01 — Browse supply chain themes
**Actor:** Investor | **Trigger:** Navigate to `/supply-chain`  
**Flow:** System displays 5 predefined theme cards. Each shows: display name, last run date, companies analysed, bottleneck nodes found, capability trees built, freshness in days, status badge, recompute-pending indicator.  
**Outcome:** User selects a theme.

### UC-02 — View supply chain map
**Actor:** Investor | **Trigger:** User selects a theme (default tab is Chain Map)  
**Flow:** Loads `sc_supply_chain_graph` for latest completed run. Renders directed SVG graph: nodes by `layer_index`, area proportional to `hhi_score`, red border on `is_bottleneck=true`. Clicking a node filters Scorecard tab to that layer.  
**Outcome:** User sees which layer is the structural constraint.

### UC-03 — View company scorecard
**Actor:** Investor | **Trigger:** Click bottleneck node or switch to Scorecard tab  
**Flow:** Loads `sc_company_scores` ordered by `bottleneck_score DESC`. Each row: ticker (linked), bottleneck score bar, gross margin sparkline, ROIC badge, backlog ratio, confidence chip with `data_gaps` tooltip, `max_depth_reached` chip, `build_status` badge, "Explore capabilities →" button.  
**Outcome:** User sees ranked investable companies.

### UC-04 — Open capability tree
**Actor:** Investor | **Trigger:** Click "Explore capabilities →"  
**Flow:** `useCapabilityTree` fires GET request. FastAPI assembles nested tree from flat DB rows and returns in one response. Panel opens with depth-1 nodes collapsed. `RootConstraintCard` pinned at bottom immediately.  
**Outcome:** Primary capability domains and root constraint visible in under 200ms.

### UC-05 — Expand a capability node
**Actor:** Investor | **Trigger:** Click ▶ on any node  
**Flow:** Node expands inline. Children render with 24px indent and connecting left border. Parent collapses to one-line summary. `can_go_deeper=false` nodes show "Physics limit" label instead of ▶. Re-collapse retains children in React state — instant re-expand.  
**Outcome:** Sub-constraints visible with zero network latency.

### UC-06 — View controlling companies
**Actor:** Investor | **Trigger:** Click "Companies ▾" on any node  
**Flow:** Inline drawer reads `controlling_companies` from already-loaded node data. Public companies: ticker, name, role, `gross_margin`, `roic_vs_wacc` (stored at build time), "View in StockerPro" link, "Add to watchlist" button. Private companies: name, role, "Private — no financial data" chip.  
**Outcome:** Oligopoly stack with financials, instantly.

### UC-07 — Add company to watchlist
**Actor:** Investor | **Trigger:** Click "Add to watchlist" in companies drawer  
**Flow:** `POST /watchlist` with `{ ticker, source: 'supply-chain-drill-down', theme_slug, node_id, node_label }`. Toast confirms. Button changes to "Added ✓".  
**Outcome:** Ticker in watchlist with full discovery context.

### UC-08 — View root constraint
**Actor:** Investor | **Trigger:** `RootConstraintCard` always visible from State 3  
**Flow:** Reads `root_constraint_label`, `root_constraint_rationale`, `cross_industry_applications`, `root_controlling_companies` from tree response. Not collapsible.  
**Outcome:** Deepest moat driver visible without expanding any node.

### UC-09 — Request recompute
**Actor:** Investor | **Trigger:** Click "Request recompute" on theme header  
**Flow:** `POST /supply-chain/recompute/{theme_slug}`. Sets `force_recompute=TRUE`. Returns 202. Banner shows. `fast_recompute_check` picks up flag within 15 min. On completion, `useRecompute` polling detects new `run_id` and invalidates all queries. Banner disappears.  
**Outcome:** Fresh run queued; current data stays visible until ready.

### UC-10 — Inspect pipeline audit log
**Actor:** Investor / Developer | **Trigger:** Switch to Pipeline Log tab  
**Flow:** Loads `sc_pipeline_runs` (last 10) with `sc_pipeline_logs`. Shows: run date, trigger reason, stage, duration, LLM call count (primary vs fallback), status. Expandable accordion per run shows step logs.  
**Outcome:** Full transparency on data freshness and pipeline health.

---

## 5. High-Level Architecture

```
PATH A — BACKGROUND PIPELINE
================================================================================
SmartOrchestrator (APScheduler)
  Job 1: weekly_full_refresh   Sun 02:00 Toronto
  Job 2: daily_filing_check    06:00 daily
  Job 3: fast_recompute_check  Every 15 minutes (handles UC-09)
                |
                v (for each active theme where _should_run() = True)
ThemePipelineRunner

STAGE 1 — Supply chain graph
  UniverseBuilder
    -> OpenBB: equity search by SIC codes from sc_themes.layer_config
    -> Comtrade: HS code trade flows -> geo_hhi per node
    -> edgartools: confirm 10-K exists per ticker
  GraphBuilder
    -> edgartools: extract Business + Risk Factors from 10-K
    -> spaCy en_core_web_sm + EntityRuler: NLP supplier extraction
    -> NetworkX DiGraph: nodes=layers, edges=supplier relationships
    -> concentrationMetrics: HHI + CR3 per layer node
    -> nx.betweenness_centrality: identify structural choke points
    -> bottleneck flag: HHI > 0.25 AND betweenness >= 75th percentile
    -> Output: sc_supply_chain_graph

STAGE 2 — Company financial scores (bottleneck companies only)
  Scorer
    -> yfinance: gross margin 3yr, ROIC components
    -> edgartools: backlog from 10-K MD&A regex
    -> concentrationMetrics: HHI component per node
    -> score = HHI*0.35 + margin*0.25 + ROIC*0.25 + backlog*0.15
    -> Output: sc_company_scores

STAGE 3 — Capability trees (top N by bottleneck_score)
  CapabilityTreeBuilder per company
    Provider: OpenRouterClient
      Primary:  deepseek/deepseek-r1:free
      Fallback: google/gemma-4-31b-it:free
      Rate:     AsyncLimiter(18/min)
      Retry:    tenacity exponential backoff, max 3 attempts
      JSON:     response_format json_object + correction retry
    Algorithm: breadth-first recursive decomposition
      depth-1: one LLM call -> 3-6 CapabilityNodes
      depth-2+: asyncio.gather parallel calls per expandable parent
      repeat until all leaves can_go_deeper=False or MAX_DEPTH
      root synthesis: one LLM call on all leaf nodes
    Enrichment: yfinance at build time for public controlling companies
    Error handling: llm_error=True nodes, tree continues as build_status=partial
    Output: sc_capability_trees + sc_capability_nodes

PipelineLogger -> sc_pipeline_runs + sc_pipeline_logs (every step)
================================================================================

                     | pure SELECT only
                     v

PATH B — UI READ LAYER
================================================================================
Next.js 15 / React 19 / TanStack Query v5

Routes:
  /supply-chain           -> Theme grid (UC-01)
  /supply-chain/[theme]   -> 3-tab shell (UC-02, 03, 10)
  CapabilityPanel         -> Tree navigator slide-over (UC-04-08)

FastAPI endpoints:
  GET  /supply-chain/themes
  GET  /supply-chain/{theme}/graph
  GET  /supply-chain/{theme}/scorecard
  GET  /supply-chain/{theme}/company/{ticker}/tree  <- full nested tree
  GET  /supply-chain/{theme}/pipeline-log
  POST /supply-chain/recompute/{theme_slug}          <- sets flag only, 202

All read endpoints: pure SELECT, no computation, target <200ms
Panel transitions after State 2: pure React state, zero network calls
================================================================================
```

---

## 6. Database Schema

### 6.1 sc_themes

```sql
CREATE TABLE sc_themes (
    id               SERIAL PRIMARY KEY,
    slug             TEXT UNIQUE NOT NULL,
    display_name     TEXT NOT NULL,
    description      TEXT,
    hs_codes         TEXT[],
    sic_codes        TEXT[],
    layer_config     JSONB NOT NULL,
    is_active        BOOLEAN DEFAULT TRUE,
    force_recompute  BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

**`layer_config` JSONB structure** — defines supply chain layers. `UniverseBuilder` reads `sic_ranges` to assign tickers to layers. `GraphBuilder` creates one graph node per layer entry:

```json
{
  "layers": [
    {
      "node_id": "semiconductor_equipment",
      "label": "Semiconductor Equipment",
      "layer_index": 2,
      "sic_ranges": [
        {"from": "3559", "to": "3559", "description": "Special industry machinery"},
        {"from": "3674", "to": "3674", "description": "Semiconductors"}
      ],
      "description": "Tools and equipment for chip fabrication"
    }
  ]
}
```

**Seed data for all 5 themes:**

```sql
INSERT INTO sc_themes (slug, display_name, description, hs_codes, sic_codes, layer_config) VALUES
('ai-infrastructure', 'AI Infrastructure',
 'Hardware stack enabling AI model training and inference',
 ARRAY['8541','8542','8473','8504'], ARRAY['3674','3672','3559','7372'],
 '{"layers":[
   {"node_id":"raw_materials","label":"Raw Materials","layer_index":0,
    "sic_ranges":[{"from":"2800","to":"2899","description":"Specialty chemicals"}],
    "description":"Upstream materials suppliers"},
   {"node_id":"wafer_substrate","label":"Wafer and Substrate","layer_index":1,
    "sic_ranges":[{"from":"3674","to":"3674","description":"Semiconductor wafers"}],
    "description":"Silicon and substrate suppliers"},
   {"node_id":"semiconductor_equipment","label":"Semiconductor Equipment","layer_index":2,
    "sic_ranges":[{"from":"3559","to":"3559","description":"Fab equipment"}],
    "description":"CVD, ALD, etch, lithography tools"},
   {"node_id":"advanced_packaging","label":"Advanced Packaging","layer_index":3,
    "sic_ranges":[{"from":"3672","to":"3672","description":"Packaging"}],
    "description":"TSMC, OSAT, substrate packaging"},
   {"node_id":"datacenter_oem","label":"Data Centre OEM","layer_index":4,
    "sic_ranges":[{"from":"3577","to":"3577","description":"Computer peripherals"}],
    "description":"Server and rack manufacturers"}
 ]}'::jsonb),
('ev-batteries', 'EV Batteries',
 'Supply chain for electric vehicle battery systems',
 ARRAY['8507','2804','2819','2869'], ARRAY['3691','2819','3714','2869'],
 '{"layers":[
   {"node_id":"lithium_mining","label":"Lithium and Cobalt Mining","layer_index":0,
    "sic_ranges":[{"from":"1040","to":"1099","description":"Metal mining"}],
    "description":"Raw material extraction"},
   {"node_id":"cathode_anode","label":"Cathode and Anode Materials","layer_index":1,
    "sic_ranges":[{"from":"2819","to":"2819","description":"Industrial inorganic chemicals"}],
    "description":"Processed battery chemistry"},
   {"node_id":"cell_manufacturing","label":"Cell Manufacturing","layer_index":2,
    "sic_ranges":[{"from":"3691","to":"3691","description":"Storage batteries"}],
    "description":"Lithium-ion cell producers"},
   {"node_id":"pack_assembly","label":"Pack Assembly and BMS","layer_index":3,
    "sic_ranges":[{"from":"3714","to":"3714","description":"Motor vehicle parts"}],
    "description":"Battery pack integration"}
 ]}'::jsonb),
('defence-electronics', 'Defence Electronics',
 'Electronic systems for defence applications',
 ARRAY['8803','8526','8543','8542'], ARRAY['3812','3679','3699'],
 '{"layers":[
   {"node_id":"specialty_materials","label":"Specialty Materials","layer_index":0,
    "sic_ranges":[{"from":"3350","to":"3357","description":"Specialty metals"}],
    "description":"Titanium, tungsten, specialty alloys"},
   {"node_id":"electronic_components","label":"Electronic Components","layer_index":1,
    "sic_ranges":[{"from":"3679","to":"3679","description":"Electronic components NEC"}],
    "description":"Passive and active components"},
   {"node_id":"defence_systems","label":"Defence Systems","layer_index":2,
    "sic_ranges":[{"from":"3812","to":"3812","description":"Defence electronics"}],
    "description":"EW, radar, comms systems"}
 ]}'::jsonb),
('energy-transition', 'Energy Transition',
 'Equipment and materials enabling grid-scale clean energy',
 ARRAY['8502','8504','8541','2818'], ARRAY['3612','3699','3559','3350'],
 '{"layers":[
   {"node_id":"rare_earth_materials","label":"Rare Earth Materials","layer_index":0,
    "sic_ranges":[{"from":"2819","to":"2819","description":"Inorganic chemicals"}],
    "description":"Rare earth oxides and metals"},
   {"node_id":"magnets_transformers","label":"Magnets and Transformers","layer_index":1,
    "sic_ranges":[{"from":"3612","to":"3612","description":"Power transformers"}],
    "description":"Permanent magnets, grid transformers"},
   {"node_id":"grid_equipment","label":"Grid Equipment","layer_index":2,
    "sic_ranges":[{"from":"3699","to":"3699","description":"Electrical apparatus"}],
    "description":"Switchgear, inverters, grid systems"}
 ]}'::jsonb),
('biotech-cdmo', 'Biotech CDMO',
 'Contract development and manufacturing for biologics',
 ARRAY['3002','2941','2836','2835'], ARRAY['2836','2835','8731','2869'],
 '{"layers":[
   {"node_id":"raw_biologics","label":"Raw Biologics Materials","layer_index":0,
    "sic_ranges":[{"from":"2836","to":"2836","description":"Pharmaceutical preparations"}],
    "description":"Cell culture media, lipid nanoparticles"},
   {"node_id":"cdmo_services","label":"CDMO Services","layer_index":1,
    "sic_ranges":[{"from":"8731","to":"8731","description":"Commercial physical research"}],
    "description":"Contract biologic manufacturing"},
   {"node_id":"drug_delivery","label":"Drug Delivery Systems","layer_index":2,
    "sic_ranges":[{"from":"2835","to":"2835","description":"In vitro diagnostics"}],
    "description":"Formulation and delivery platforms"}
 ]}'::jsonb);
```

### 6.2 sc_pipeline_runs

```sql
CREATE TABLE sc_pipeline_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    theme_id            INTEGER REFERENCES sc_themes(id),
    triggered_by        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'running',
    current_stage       TEXT,
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_secs       INTEGER,
    error_message       TEXT,
    failed_at_step      TEXT,
    llm_call_count      INTEGER DEFAULT 0,
    llm_primary_calls   INTEGER DEFAULT 0,
    llm_fallback_calls  INTEGER DEFAULT 0,
    stats               JSONB
);
CREATE INDEX ON sc_pipeline_runs (theme_id, status, completed_at DESC);
CREATE INDEX ON sc_pipeline_runs (theme_id, status) WHERE status = 'completed';
```

### 6.3 sc_pipeline_logs

```sql
CREATE TABLE sc_pipeline_logs (
    id        BIGSERIAL PRIMARY KEY,
    run_id    UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    step      TEXT NOT NULL,
    status    TEXT NOT NULL,
    message   TEXT NOT NULL,
    payload   JSONB,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON sc_pipeline_logs (run_id, logged_at);
CREATE INDEX ON sc_pipeline_logs (run_id, step);
```

### 6.4 sc_supply_chain_graph

```sql
CREATE TABLE sc_supply_chain_graph (
    id            BIGSERIAL PRIMARY KEY,
    run_id        UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    theme_id      INTEGER REFERENCES sc_themes(id),
    node_id       TEXT NOT NULL,
    node_label    TEXT NOT NULL,
    layer_index   INTEGER NOT NULL,
    hhi_score     NUMERIC(6,4),
    cr3_score     NUMERIC(6,4),
    betweenness   NUMERIC(8,6),
    is_bottleneck BOOLEAN DEFAULT FALSE,
    company_count INTEGER,
    geo_hhi       NUMERIC(6,4),
    edges         JSONB,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON sc_supply_chain_graph (theme_id, run_id);
CREATE INDEX ON sc_supply_chain_graph (run_id, is_bottleneck);
```

### 6.5 sc_company_scores

```sql
CREATE TABLE sc_company_scores (
    id                BIGSERIAL PRIMARY KEY,
    run_id            UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    theme_id          INTEGER REFERENCES sc_themes(id),
    ticker            TEXT NOT NULL,
    company_name      TEXT,
    node_id           TEXT NOT NULL,
    bottleneck_score  NUMERIC(5,2),
    hhi_component     NUMERIC(5,2),
    margin_component  NUMERIC(5,2),
    roic_component    NUMERIC(5,2),
    backlog_component NUMERIC(5,2),
    margin_trend_3yr  NUMERIC(6,4),
    roic_vs_wacc      NUMERIC(6,4),
    backlog_ratio     NUMERIC(6,4),
    confidence_flag   TEXT DEFAULT 'low',
    data_gaps         TEXT[],
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON sc_company_scores (theme_id, run_id, bottleneck_score DESC);
CREATE INDEX ON sc_company_scores (run_id, node_id);
CREATE INDEX ON sc_company_scores (ticker, theme_id);
```

### 6.6 sc_capability_trees

```sql
CREATE TABLE sc_capability_trees (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                     UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    theme_id                   INTEGER REFERENCES sc_themes(id),
    ticker                     TEXT NOT NULL,
    company_name               TEXT,
    node_id                    TEXT NOT NULL,
    max_depth_reached          INTEGER,
    total_nodes                INTEGER,
    root_constraint_label      TEXT,
    root_constraint_rationale  TEXT,
    root_controlling_companies JSONB,
    cross_industry_applications TEXT[],
    build_status               TEXT DEFAULT 'completed',
    created_at                 TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON sc_capability_trees (theme_id, run_id);
CREATE INDEX ON sc_capability_trees (ticker, run_id);
CREATE UNIQUE INDEX ON sc_capability_trees (run_id, ticker);
```

### 6.7 sc_capability_nodes

```sql
CREATE TABLE sc_capability_nodes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    tree_id                 UUID REFERENCES sc_capability_trees(id) ON DELETE CASCADE,
    theme_id                INTEGER REFERENCES sc_themes(id),
    ticker                  TEXT NOT NULL,
    node_id                 TEXT NOT NULL,
    parent_node_id          TEXT,
    depth                   INTEGER NOT NULL,
    label                   TEXT NOT NULL,
    description             TEXT,
    why_hard                TEXT,
    replicability_score     NUMERIC(3,1),
    replicability_rationale TEXT,
    controlling_companies   JSONB,
    can_go_deeper           BOOLEAN DEFAULT TRUE,
    is_root_constraint      BOOLEAN DEFAULT FALSE,
    llm_error               BOOLEAN DEFAULT FALSE,
    llm_prompt_tokens       INTEGER,
    llm_completion_tokens   INTEGER,
    llm_model_used          TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON sc_capability_nodes (tree_id, depth);
CREATE INDEX ON sc_capability_nodes (ticker, run_id, parent_node_id);
CREATE INDEX ON sc_capability_nodes (run_id, is_root_constraint);
CREATE INDEX ON sc_capability_nodes (tree_id, node_id);
```

---

## 7. Dependent Libraries

### 7.1 Python backend

```bash
pip install httpx>=0.27 aiolimiter>=1.1 tenacity>=8.3 openbb>=4.3 \
            edgartools>=2.0 yfinance>=0.2 networkx>=3.3 spacy>=3.7 \
            concentrationMetrics>=0.5 comtradeapiclient>=1.0 \
            apscheduler>=3.10 pandas>=2.2 pydantic>=2.7 supabase>=2.5
python -m spacy download en_core_web_sm
```

| Library | Version | Role |
|---|---|---|
| `httpx` | >=0.27 | Async HTTP for OpenRouter API calls |
| `aiolimiter` | >=1.1 | Async rate limiter — 18 req/min |
| `tenacity` | >=8.3 | Retry with exponential backoff |
| `openbb` | >=4.3 | Financial data hub |
| `edgartools` | >=2.0 | SEC 10-K extraction and filing detection |
| `yfinance` | >=0.2 | Gross margin, ROIC, balance sheet |
| `networkx` | >=3.3 | Directed graph, betweenness centrality |
| `spacy` | >=3.7 | NLP for supplier relationship extraction |
| `concentrationMetrics` | >=0.5 | HHI, CR3 computation |
| `comtradeapiclient` | >=1.0 | UN Comtrade trade flow data |
| `apscheduler` | >=3.10 | 3 scheduler jobs |
| `pandas` | >=2.2 | Data manipulation |
| `pydantic` | >=2.7 | Model validation |
| `supabase-py` | >=2.5 | Supabase client |

### 7.2 Frontend (no new npm dependencies)

| Library | Role |
|---|---|
| Next.js 15 / React 19 | Routing, server components |
| TanStack Query v5 | Caching, background refetch, polling |
| Recharts | Sparklines, score bars, SVG graph |
| Tailwind CSS | Glass design system |

---

## 8. Path A — Background Pipeline

### 8.1 File structure

```
backend/
  supply_chain/
    scheduler.py              # SmartOrchestrator
    pipeline.py               # ThemePipelineRunner
    logger.py                 # PipelineLogger
    models.py                 # All Pydantic models
    stages/
      stage1_universe.py      # UniverseBuilder
      stage1_graph.py         # GraphBuilder
      stage2_scorer.py        # Scorer
      stage3_tree.py          # CapabilityTreeBuilder
    providers/
      openrouter_client.py    # PRIMARY LLM provider (replaces anthropic_client.py)
      openbb_client.py
      comtrade.py
      edgar_nlp.py
      yfinance_client.py
      concentration.py
    router.py
```

### 8.2 OpenRouterClient — complete implementation

```python
# providers/openrouter_client.py
import os, json, logging
from typing import Any
import httpx
from tenacity import (retry, stop_after_attempt, wait_exponential,
                      retry_if_exception_type, before_sleep_log)
from aiolimiter import AsyncLimiter

logger = logging.getLogger(__name__)
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

class OpenRouterError(Exception): pass
class OpenRouterRateLimitError(OpenRouterError): pass
class OpenRouterJSONError(OpenRouterError): pass


class OpenRouterClient:
    def __init__(self):
        self.api_key  = os.environ["OPENROUTER_API_KEY"]
        self.primary  = os.environ.get("OPENROUTER_PRIMARY_MODEL",
                                        "deepseek/deepseek-r1:free")
        self.fallback = os.environ.get("OPENROUTER_FALLBACK_MODEL",
                                        "google/gemma-4-31b-it:free")
        self.site_url  = os.environ.get("OPENROUTER_SITE_URL", "https://stockerpro.app")
        self.site_name = os.environ.get("OPENROUTER_SITE_NAME", "StockerPro")
        rate = int(os.environ.get("PIPELINE_LLM_RATE_LIMIT_PER_MIN", "18"))
        self._limiter = AsyncLimiter(rate, 60)
        self._use_fallback = False

    async def complete(self, system: str, user: str,
                       max_tokens: int = 2000) -> tuple[str, int, int, str]:
        model = self.fallback if self._use_fallback else self.primary
        try:
            content, pt, ct = await self._call_with_retry(model, system, user, max_tokens)
            self._use_fallback = False
            return content, pt, ct, model
        except OpenRouterError as e:
            if not self._use_fallback:
                logger.warning(f"Primary failed, switching to fallback: {e}")
                self._use_fallback = True
                content, pt, ct = await self._call_with_retry(
                    self.fallback, system, user, max_tokens)
                return content, pt, ct, self.fallback
            raise

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=2, min=4, max=60),
           retry=retry_if_exception_type(OpenRouterRateLimitError),
           before_sleep=before_sleep_log(logger, logging.WARNING),
           reraise=True)
    async def _call_with_retry(self, model: str, system: str,
                                user: str, max_tokens: int) -> tuple[str, int, int]:
        async with self._limiter:
            return await self._raw_call(model, system, user, max_tokens)

    async def _raw_call(self, model: str, system: str,
                         user: str, max_tokens: int) -> tuple[str, int, int]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": user}],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload)
        if resp.status_code == 429:
            raise OpenRouterRateLimitError(f"Rate limit on {model}: {resp.text}")
        if resp.status_code >= 500:
            raise OpenRouterError(f"Server error {resp.status_code} on {model}")
        if resp.status_code >= 400:
            raise OpenRouterError(f"Client error {resp.status_code}: {resp.text}")
        data  = resp.json()
        usage = data.get("usage", {})
        return (data["choices"][0]["message"]["content"],
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0))

    async def complete_json(self, system: str, user: str,
                             max_tokens: int = 2000) -> tuple[Any, int, int, str]:
        content, pt, ct, model = await self.complete(system, user, max_tokens)
        try:
            return json.loads(content), pt, ct, model
        except json.JSONDecodeError:
            logger.warning(f"JSON parse failed for {model}, retrying with correction")
            correction = (
                "Your previous response was not valid JSON. "
                "Return ONLY a valid JSON array with no other text.\n\n"
                f"Original request:\n{user}"
            )
            content2, pt2, ct2, model2 = await self.complete(system, correction, max_tokens)
            try:
                return json.loads(content2), pt+pt2, ct+ct2, model2
            except json.JSONDecodeError as e:
                raise OpenRouterJSONError(f"JSON parse failed twice: {e}") from e
```

### 8.3 SmartOrchestrator — complete implementation

```python
# scheduler.py
import os, logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dateutil.parser import parse
import edgar

logger = logging.getLogger(__name__)


class SmartOrchestrator:
    def __init__(self, db):
        self.db = db
        self.scheduler = AsyncIOScheduler(
            timezone=os.environ.get("PIPELINE_TIMEZONE", "America/Toronto"))

    def start(self):
        tz  = os.environ.get("PIPELINE_TIMEZONE", "America/Toronto")
        day = os.environ.get("PIPELINE_WEEKLY_RUN_DAY", "sun")
        hr  = int(os.environ.get("PIPELINE_WEEKLY_RUN_HOUR", "2"))
        self.scheduler.add_job(self.run_all_themes,
            CronTrigger(day_of_week=day, hour=hr, timezone=tz),
            id="weekly_full_refresh", replace_existing=True)
        self.scheduler.add_job(self.run_all_themes,
            CronTrigger(hour=6, timezone=tz),
            id="daily_filing_check", replace_existing=True)
        self.scheduler.add_job(self.run_queued_recomputes,
            IntervalTrigger(minutes=15),
            id="fast_recompute_check", replace_existing=True)
        self.scheduler.start()

    async def run_all_themes(self):
        themes = (self.db.table("sc_themes").select("id,slug")
                  .eq("is_active", True).execute().data)
        for t in themes:
            should, reason = await self._should_run(t["id"])
            if should:
                from supply_chain.pipeline import ThemePipelineRunner
                await ThemePipelineRunner(t["id"], reason, self.db).execute()

    async def run_queued_recomputes(self):
        themes = (self.db.table("sc_themes").select("id,slug")
                  .eq("is_active", True).eq("force_recompute", True).execute().data)
        for t in themes:
            self.db.table("sc_themes").update({"force_recompute": False})                .eq("id", t["id"]).execute()
            from supply_chain.pipeline import ThemePipelineRunner
            await ThemePipelineRunner(t["id"], "user_recompute", self.db).execute()

    async def _should_run(self, theme_id: int) -> tuple[bool, str]:
        result = (self.db.table("sc_pipeline_runs").select("completed_at")
                  .eq("theme_id", theme_id).eq("status", "completed")
                  .order("completed_at", desc=True).limit(1).execute().data)
        if not result:
            return True, "no_prior_run"
        last = parse(result[0]["completed_at"]).replace(tzinfo=None)
        if (datetime.utcnow() - last).days >= 7:
            return True, "weekly_cadence"
        ticker = await self._check_new_filings(theme_id, last)
        if ticker:
            return True, f"new_filing:{ticker}"
        return False, "data_current"

    async def _check_new_filings(self, theme_id: int, since: datetime) -> str | None:
        last_run = (self.db.table("sc_pipeline_runs").select("id")
                    .eq("theme_id", theme_id).eq("status", "completed")
                    .order("completed_at", desc=True).limit(1).execute().data)
        if not last_run:
            return None
        tickers = (self.db.table("sc_company_scores").select("ticker")
                   .eq("run_id", last_run[0]["id"]).execute().data)
        for row in tickers:
            try:
                filings = edgar.Company(row["ticker"]).get_filings(form="10-K")
                if filings:
                    dt = datetime.combine(filings[0].filing_date, datetime.min.time())
                    if dt > since:
                        return row["ticker"]
            except Exception as e:
                logger.warning(f"Filing check failed for {row['ticker']}: {e}")
        return None
```

### 8.4 ThemePipelineRunner — complete implementation

```python
# pipeline.py
import logging, os
from datetime import datetime
from supply_chain.logger import PipelineLogger
from supply_chain.stages.stage1_universe import UniverseBuilder
from supply_chain.stages.stage1_graph import GraphBuilder
from supply_chain.stages.stage2_scorer import Scorer
from supply_chain.stages.stage3_tree import CapabilityTreeBuilder

logger = logging.getLogger(__name__)
MAX_CO = int(os.environ.get("PIPELINE_MAX_COMPANIES_PER_THEME", "8"))


class ThemePipelineRunner:
    def __init__(self, theme_id: int, triggered_by: str, db):
        self.theme_id     = theme_id
        self.triggered_by = triggered_by
        self.db           = db
        self.log          = PipelineLogger(db)

    async def execute(self):
        run_id = await self.log.start_run(self.theme_id, self.triggered_by)
        start  = datetime.utcnow()
        total = primary = fallback = 0
        try:
            # STAGE 1
            await self.log.set_stage(run_id, "stage_1")
            universe = await UniverseBuilder(self.theme_id, self.db).run()
            await self.log.log(run_id, "universe_build", "ok",
                f"{len(universe.tickers)} tickers, {len(universe.layers)} layers",
                {"ticker_count": len(universe.tickers), "filings_found": universe.filings_read})
            graph = await GraphBuilder(universe, self.db).run()
            await self.log.log(run_id, "graph_build", "ok",
                f"{graph.node_count} nodes, {graph.edge_count} edges, "
                f"{graph.bottleneck_count} bottleneck nodes",
                {"bottleneck_nodes": [n.node_id for n in graph.nodes if n.is_bottleneck]})
            await self._persist_graph(run_id, graph)

            # STAGE 2
            await self.log.set_stage(run_id, "stage_2")
            scores = await Scorer(self.theme_id, universe, graph, self.db).run()
            await self.log.log(run_id, "score_calc", "ok", f"{len(scores)} companies scored",
                {"high_confidence": sum(1 for s in scores if s.confidence_flag == "high")})
            await self._persist_scores(run_id, scores)

            # STAGE 3
            await self.log.set_stage(run_id, "stage_3")
            bottleneck = sorted(
                [s for s in scores if graph.is_bottleneck(s.node_id)],
                key=lambda s: s.bottleneck_score, reverse=True)[:MAX_CO]

            for company in bottleneck:
                await self.log.log(run_id, f"tree_build:{company.ticker}",
                                   "started", f"Building tree for {company.company_name}")
                tree, lc, pc, fc = await CapabilityTreeBuilder(
                    company, self.theme_id, run_id, self.db).run()
                total += lc; primary += pc; fallback += fc
                await self._persist_tree(run_id, tree)
                status = "warn" if tree.build_status == "partial" else "ok"
                await self.log.log(run_id, f"tree_build:{company.ticker}", status,
                    f"{tree.total_nodes} nodes, depth {tree.max_depth_reached}, "
                    f"{lc} LLM calls ({pc} primary, {fc} fallback), "
                    f"status={tree.build_status}",
                    {"total_nodes": tree.total_nodes, "max_depth": tree.max_depth_reached,
                     "build_status": tree.build_status})

            await self.log.update_llm_counts(run_id, total, primary, fallback)
            duration = int((datetime.utcnow() - start).total_seconds())
            await self.log.complete_run(run_id, duration, {
                "tickers_processed": len(universe.tickers),
                "bottleneck_companies": len(bottleneck),
                "edges_extracted": graph.edge_count,
                "trees_built": len(bottleneck),
                "total_llm_calls": total,
            })
        except Exception as e:
            logger.exception(f"Pipeline failed theme {self.theme_id}")
            await self.log.fail_run(run_id, str(e))
            raise

    async def _persist_graph(self, run_id, graph):
        rows = [{"run_id": str(run_id), "theme_id": self.theme_id,
                 "node_id": n.node_id, "node_label": n.label,
                 "layer_index": n.layer_index,
                 "hhi_score": float(n.hhi_score) if n.hhi_score else None,
                 "cr3_score": float(n.cr3_score) if n.cr3_score else None,
                 "betweenness": float(n.betweenness) if n.betweenness else None,
                 "is_bottleneck": n.is_bottleneck,
                 "company_count": n.company_count,
                 "geo_hhi": float(n.geo_hhi) if n.geo_hhi else None,
                 "edges": n.edges} for n in graph.nodes]
        self.db.table("sc_supply_chain_graph").insert(rows).execute()

    async def _persist_scores(self, run_id, scores):
        rows = [{"run_id": str(run_id), "theme_id": self.theme_id,
                 "ticker": s.ticker, "company_name": s.company_name,
                 "node_id": s.node_id,
                 "bottleneck_score": float(s.bottleneck_score),
                 "hhi_component": float(s.hhi_component),
                 "margin_component": float(s.margin_component),
                 "roic_component": float(s.roic_component),
                 "backlog_component": float(s.backlog_component),
                 "margin_trend_3yr": float(s.margin_trend_3yr) if s.margin_trend_3yr else None,
                 "roic_vs_wacc": float(s.roic_vs_wacc) if s.roic_vs_wacc else None,
                 "backlog_ratio": float(s.backlog_ratio) if s.backlog_ratio else None,
                 "confidence_flag": s.confidence_flag,
                 "data_gaps": s.data_gaps} for s in scores]
        self.db.table("sc_company_scores").insert(rows).execute()

    async def _persist_tree(self, run_id, tree):
        result = self.db.table("sc_capability_trees").insert({
            "run_id": str(run_id), "theme_id": self.theme_id,
            "ticker": tree.ticker, "company_name": tree.company_name,
            "node_id": tree.node_id,
            "max_depth_reached": tree.max_depth_reached,
            "total_nodes": tree.total_nodes,
            "root_constraint_label": tree.root_constraint_label,
            "root_constraint_rationale": tree.root_constraint_rationale,
            "root_controlling_companies": tree.root_controlling_companies,
            "cross_industry_applications": tree.cross_industry_applications,
            "build_status": tree.build_status,
        }).execute()
        tree_id = result.data[0]["id"]
        node_rows = [{
            "run_id": str(run_id), "tree_id": tree_id,
            "theme_id": self.theme_id, "ticker": tree.ticker,
            "node_id": n.node_id, "parent_node_id": n.parent_node_id,
            "depth": n.depth, "label": n.label,
            "description": n.description, "why_hard": n.why_hard,
            "replicability_score": float(n.replicability_score) if n.replicability_score else None,
            "replicability_rationale": n.replicability_rationale,
            "controlling_companies": n.controlling_companies,
            "can_go_deeper": n.can_go_deeper,
            "is_root_constraint": n.is_root_constraint,
            "llm_error": n.llm_error,
            "llm_prompt_tokens": n.llm_prompt_tokens,
            "llm_completion_tokens": n.llm_completion_tokens,
            "llm_model_used": n.llm_model_used,
        } for n in tree.nodes]
        for i in range(0, len(node_rows), 500):
            self.db.table("sc_capability_nodes").insert(node_rows[i:i+500]).execute()
```

### 8.5 CapabilityTreeBuilder — complete implementation

```python
# stages/stage3_tree.py
import asyncio, logging, os
from supply_chain.providers.openrouter_client import OpenRouterClient, OpenRouterJSONError
from supply_chain.models import CapabilityNode, CapabilityTree, ScoreResult
from supply_chain.providers.yfinance_client import YFinanceClient

logger  = logging.getLogger(__name__)
MAX_D   = int(os.environ.get("PIPELINE_MAX_DEPTH", "4"))

SYSTEM_PROMPT = (
    "You are a technical investment analyst specialising in supply chain "
    "capability analysis at the physics and materials science level.\n\n"
    "Decompose capabilities into fundamental physical and manufacturing "
    "constraints — not business categories or product lines.\n\n"
    "Replicability score (0-10):\n"
    "  10 = bounded by physics\n"
    "   9 = requires decades of process knowledge\n"
    "   7 = hard but replicable with 10+ years capital\n"
    "   5 = replicable in 5 years\n"
    "  <5 = commodity\n\n"
    "controlling_companies: list the real oligopoly including private.\n"
    "  Each: ticker (str or null), name, role, public (bool).\n\n"
    "can_go_deeper: true only if non-obvious deeper physical constraints exist.\n"
    "  false if at a fundamental physical or quantum limit.\n\n"
    "Return ONLY a JSON array. Each element must have exactly:\n"
    '{"node_id":"snake_case","label":"Name","description":"physical role",'
    '"why_hard":"specific constraint","replicability_score":8.5,'
    '"replicability_rationale":"one sentence",'
    '"controlling_companies":[{"ticker":"X","name":"Y","role":"Z","public":true}],'
    '"can_go_deeper":true}\n'
    "No preamble. No markdown. No text outside the JSON array."
)


class CapabilityTreeBuilder:
    def __init__(self, company: ScoreResult, theme_id: int, run_id: str, db):
        self.company   = company
        self.theme_id  = theme_id
        self.run_id    = run_id
        self.db        = db
        self.client    = OpenRouterClient()
        self.yf        = YFinanceClient()
        self.all_nodes: list[CapabilityNode] = []
        self.llm = self.primary = self.fallback = 0

    async def run(self) -> tuple[CapabilityTree, int, int, int]:
        build_status = "completed"
        root = CapabilityNode(
            node_id=f"{self.company.ticker.lower()}_root", parent_node_id=None,
            depth=0, label=self.company.company_name,
            description=f"Root node for {self.company.company_name}",
            why_hard=None, replicability_score=None, replicability_rationale=None,
            controlling_companies=[], can_go_deeper=True,
            is_root_constraint=False, llm_error=False)
        self.all_nodes.append(root)
        nodes_to_expand = [root]
        max_depth = 0

        for depth in range(1, MAX_D + 1):
            parents = [n for n in nodes_to_expand if n.can_go_deeper]
            if not parents:
                break
            results = await asyncio.gather(
                *[self._generate_children(p, depth) for p in parents],
                return_exceptions=True)
            new_nodes = []
            for parent, result in zip(parents, results):
                if isinstance(result, Exception):
                    logger.error(f"Children failed {parent.node_id}: {result}")
                    new_nodes.append(CapabilityNode(
                        node_id=f"{parent.node_id}_error",
                        parent_node_id=parent.node_id, depth=depth,
                        label="Analysis unavailable", description=None,
                        why_hard=None, replicability_score=None,
                        replicability_rationale=None, controlling_companies=[],
                        can_go_deeper=False, is_root_constraint=False, llm_error=True))
                    build_status = "partial"
                else:
                    new_nodes.extend(result)
            await self._enrich_controlling_companies(new_nodes)
            self.all_nodes.extend(new_nodes)
            nodes_to_expand = new_nodes
            max_depth = depth

        child_parents = {n.parent_node_id for n in self.all_nodes if n.parent_node_id}
        for node in self.all_nodes:
            if node.node_id not in child_parents and node.depth > 0 and not node.llm_error:
                node.is_root_constraint = True

        leaves = [n for n in self.all_nodes if n.is_root_constraint]
        root_c = await self._synthesise_root_constraint(leaves)

        tree = CapabilityTree(
            ticker=self.company.ticker, company_name=self.company.company_name,
            node_id=self.company.node_id, max_depth_reached=max_depth,
            total_nodes=len(self.all_nodes),
            root_constraint_label=root_c.get("root_constraint_label"),
            root_constraint_rationale=root_c.get("root_constraint_rationale"),
            cross_industry_applications=root_c.get("cross_industry_applications", []),
            root_controlling_companies=self._extract_root_companies(leaves),
            build_status=build_status, nodes=self.all_nodes)
        return tree, self.llm, self.primary, self.fallback

    async def _generate_children(self, parent: CapabilityNode,
                                  depth: int) -> list[CapabilityNode]:
        prompt = self._build_prompt(parent, depth)
        try:
            data, pt, ct, model = await self.client.complete_json(
                SYSTEM_PROMPT, prompt, max_tokens=2000)
        except OpenRouterJSONError as e:
            raise RuntimeError(f"LLM JSON failure: {e}") from e
        self.llm += 1
        if "gemma" in model:
            self.fallback += 1
        else:
            self.primary += 1
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        return self._parse_nodes(data, parent.node_id, depth, pt, ct, model)

    def _build_prompt(self, parent: CapabilityNode, depth: int) -> str:
        c = self.company
        if depth == 1:
            return (
                f"Company: {c.company_name} ({c.ticker})\n"
                f"Supply chain layer: {c.node_id}, theme_id={self.theme_id}\n"
                f"Bottleneck score: {c.bottleneck_score:.1f}/100, "
                f"Gross margin trend: {c.margin_trend_3yr:+.1f}pp (3yr)\n\n"
                "Decompose this company's moat into 3-6 primary physical and "
                "manufacturing capability domains. Each must be a distinct "
                "physical constraint, not a business category.\n\n"
                "Return a JSON array at depth=1."
            )
        return (
            f"Company: {c.company_name} ({c.ticker})\n"
            f"Parent: {parent.label} (depth {parent.depth})\n"
            f"Parent description: {parent.description}\n"
            f"Parent why_hard: {parent.why_hard}\n\n"
            f"Decompose '{parent.label}' into constituent physical sub-constraints. "
            "Go one level deeper — do not restate the parent. Find the specific "
            "material physics, fabrication physics, or measurement physics.\n\n"
            "If at a fundamental physical limit, set can_go_deeper=false "
            "and explain in why_hard.\n\n"
            f"Return a JSON array at depth={depth}."
        )

    def _parse_nodes(self, data: list, parent_id: str, depth: int,
                     pt: int, ct: int, model: str) -> list[CapabilityNode]:
        nodes, per = [], max(len(data), 1)
        for item in data:
            if not isinstance(item, dict):
                continue
            nodes.append(CapabilityNode(
                node_id=item.get("node_id", f"node_{depth}_{len(nodes)}"),
                parent_node_id=parent_id, depth=depth,
                label=item.get("label", "Unknown"),
                description=item.get("description"),
                why_hard=item.get("why_hard"),
                replicability_score=item.get("replicability_score"),
                replicability_rationale=item.get("replicability_rationale"),
                controlling_companies=item.get("controlling_companies", []),
                can_go_deeper=bool(item.get("can_go_deeper", True)),
                is_root_constraint=False, llm_error=False,
                llm_prompt_tokens=pt // per,
                llm_completion_tokens=ct // per,
                llm_model_used=model))
        return nodes

    async def _enrich_controlling_companies(self, nodes: list[CapabilityNode]):
        for node in nodes:
            for co in node.controlling_companies:
                if co.get("public") and co.get("ticker"):
                    try:
                        fin = await self.yf.get_key_ratios(co["ticker"])
                        co["gross_margin"] = fin.get("gross_margin")
                        co["roic_vs_wacc"] = fin.get("roic_vs_wacc")
                    except Exception:
                        pass

    async def _synthesise_root_constraint(self, leaves: list[CapabilityNode]) -> dict:
        if not leaves:
            return {}
        summary = "\n".join(f"- {n.label}: {n.why_hard}" for n in leaves[:10])
        prompt = (
            f"Company: {self.company.company_name} ({self.company.ticker})\n\n"
            f"Deepest capability constraints:\n{summary}\n\n"
            "Return a single JSON object with exactly:\n"
            '{"root_constraint_label":"one sentence",'
            '"root_constraint_rationale":"2-3 sentences",'
            '"cross_industry_applications":["list"]}'
        )
        try:
            data, _, _, _ = await self.client.complete_json(
                SYSTEM_PROMPT, prompt, max_tokens=500)
            self.llm += 1
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"Root synthesis failed: {e}")
            return {}

    def _extract_root_companies(self, leaves: list[CapabilityNode]) -> list[dict]:
        seen, result = set(), []
        for node in leaves:
            for co in node.controlling_companies:
                key = co.get("ticker") or co.get("name")
                if key and key not in seen:
                    seen.add(key); result.append(co)
        return result
```

### 8.6 LLM prompt costs and cadence

| Call type | When | Est. tokens (prompt/completion) | Parallel? |
|---|---|---|---|
| depth-1 decomposition | Once per company | ~800 / ~600 | No |
| depth-N decomposition | Once per expandable parent node | ~600 / ~400 | Yes — asyncio.gather |
| root synthesis | Once per company | ~400 / ~200 | No |

Typical: 5–15 LLM calls per company. 8 companies × 10 calls = 80 calls per theme per run.

---

## 9. Path B — UI Read Layer

### 9.1 FastAPI endpoints — complete implementations

```python
# router.py
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

router = APIRouter(prefix="/supply-chain", tags=["supply-chain"])


def _days_since(dt_str: str | None) -> int | None:
    if not dt_str: return None
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days

def _latest_run_id(db, theme_id: int) -> str | None:
    r = (db.table("sc_pipeline_runs").select("id")
         .eq("theme_id", theme_id).eq("status", "completed")
         .order("completed_at", desc=True).limit(1).execute().data)
    return r[0]["id"] if r else None

def _theme_or_404(db, slug: str) -> dict:
    r = (db.table("sc_themes").select("*")
         .eq("slug", slug).eq("is_active", True).execute().data)
    if not r: raise HTTPException(404, f"Theme '{slug}' not found")
    return r[0]

def _build_nested_tree(flat: list[dict]) -> dict | None:
    if not flat: return None
    m = {n["node_id"]: {**n, "children": []} for n in flat}
    root = None
    for n in flat:
        pid = n.get("parent_node_id")
        if pid is None: root = m[n["node_id"]]
        elif pid in m:  m[pid]["children"].append(m[n["node_id"]])
    return root


@router.get("/themes")
async def list_themes(db=Depends(get_db)):
    themes = (db.table("sc_themes")
              .select("id,slug,display_name,description,force_recompute")
              .eq("is_active", True).execute().data)
    out = []
    for t in themes:
        run = (db.table("sc_pipeline_runs")
               .select("id,completed_at,status,stats,llm_call_count")
               .eq("theme_id", t["id"])
               .order("completed_at", desc=True).limit(1).execute().data)
        latest = run[0] if run else None
        trees = 0
        if latest:
            trees = (db.table("sc_capability_trees").select("id", count="exact")
                     .eq("run_id", latest["id"]).execute().count or 0)
        stats = (latest or {}).get("stats") or {}
        out.append({
            "slug": t["slug"], "display_name": t["display_name"],
            "description": t["description"],
            "last_run_at": latest["completed_at"] if latest else None,
            "data_freshness_days": _days_since(latest["completed_at"]) if latest else None,
            "companies_analysed": stats.get("tickers_processed", 0),
            "bottleneck_nodes_found": stats.get("bottleneck_nodes", 0),
            "capability_trees_built": trees,
            "status": latest["status"] if latest else "never_run",
            "recompute_pending": t["force_recompute"],
        })
    return out


@router.get("/{theme_slug}/company/{ticker}/tree")
async def get_tree(theme_slug: str, ticker: str, db=Depends(get_db)):
    theme  = _theme_or_404(db, theme_slug)
    run_id = _latest_run_id(db, theme["id"])
    if not run_id:
        raise HTTPException(404, "No completed pipeline run found for this theme")

    meta = (db.table("sc_capability_trees").select("*")
            .eq("run_id", run_id).eq("ticker", ticker.upper()).execute().data)
    if not meta:
        raise HTTPException(404,
            f"No capability tree found for {ticker} in theme {theme_slug}. "
            "The company may not be in a bottleneck layer, or the pipeline "
            "may still be building this analysis.")
    tree = meta[0]

    flat = (db.table("sc_capability_nodes").select("*")
            .eq("tree_id", tree["id"]).order("depth").execute().data)
    nested = _build_nested_tree(flat)

    info = (db.table("sc_pipeline_runs").select("completed_at,triggered_by")
            .eq("id", run_id).execute().data)[0]

    return {
        "ticker": ticker.upper(), "company_name": tree["company_name"],
        "run_id": run_id, "computed_at": info["completed_at"],
        "triggered_by": info["triggered_by"],
        "data_freshness_days": _days_since(info["completed_at"]),
        "max_depth_reached": tree["max_depth_reached"],
        "total_nodes": tree["total_nodes"],
        "build_status": tree["build_status"],
        "root_constraint_label": tree["root_constraint_label"],
        "root_constraint_rationale": tree["root_constraint_rationale"],
        "cross_industry_applications": tree["cross_industry_applications"],
        "root_controlling_companies": tree["root_controlling_companies"],
        "tree": nested,
    }


@router.post("/recompute/{theme_slug}")
async def recompute(theme_slug: str, db=Depends(get_db)):
    theme = _theme_or_404(db, theme_slug)
    db.table("sc_themes").update({"force_recompute": True})        .eq("id", theme["id"]).execute()
    latest = (db.table("sc_pipeline_runs").select("completed_at")
              .eq("theme_id", theme["id"]).eq("status", "completed")
              .order("completed_at", desc=True).limit(1).execute().data)
    return JSONResponse(status_code=202, content={
        "status": "queued",
        "message": f"Recompute queued for {theme_slug}. Will begin within 15 minutes.",
        "current_data_from": latest[0]["completed_at"] if latest else None,
    })
```

### 9.2 useCapabilityTree hook

```typescript
// _hooks/useCapabilityTree.ts
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface ControllingCompany {
  ticker: string | null; name: string; role: string
  public: boolean; gross_margin: number | null; roic_vs_wacc: number | null
}
export interface CapabilityNode {
  node_id: string; parent_node_id: string | null; depth: number
  label: string; description: string | null; why_hard: string | null
  replicability_score: number | null; replicability_rationale: string | null
  controlling_companies: ControllingCompany[]
  can_go_deeper: boolean; is_root_constraint: boolean
  llm_error: boolean; llm_model_used: string | null
  children: CapabilityNode[]
}
export interface CapabilityTreeResponse {
  ticker: string; company_name: string; run_id: string
  computed_at: string; data_freshness_days: number
  max_depth_reached: number; total_nodes: number
  build_status: 'completed' | 'partial'
  root_constraint_label: string | null
  root_constraint_rationale: string | null
  cross_industry_applications: string[]
  root_controlling_companies: ControllingCompany[]
  tree: CapabilityNode | null
}

export function useCapabilityTree(themeSlug: string, ticker: string | null) {
  return useQuery<CapabilityTreeResponse>({
    queryKey: ['capability-tree', themeSlug, ticker],
    queryFn: () => api.get(`/supply-chain/${themeSlug}/company/${ticker}/tree`),
    enabled: !!ticker,
    staleTime: 60 * 60 * 1000,
    gcTime: 4 * 60 * 60 * 1000,
    retry: 2,
  })
}
```

### 9.3 useRecompute hook

```typescript
// _hooks/useRecompute.ts
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'

export function useRecompute(themeSlug: string) {
  const qc = useQueryClient()
  const [bannerVisible, setBannerVisible] = useState(false)
  const [currentDataFrom, setCurrentDataFrom] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.post(`/supply-chain/recompute/${themeSlug}`),
    onSuccess: (data) => { setBannerVisible(true); setCurrentDataFrom(data.current_data_from) },
  })

  const { data: themes } = useQuery({
    queryKey: ['themes'],
    queryFn: () => api.get('/supply-chain/themes'),
    refetchInterval: bannerVisible ? 5 * 60 * 1000 : false,
  })

  useEffect(() => {
    if (!bannerVisible || !themes) return
    const theme = themes.find((t: any) => t.slug === themeSlug)
    if (!theme?.last_run_at || !currentDataFrom) return
    if (new Date(theme.last_run_at) > new Date(currentDataFrom)) {
      qc.invalidateQueries({ queryKey: ['supply-chain', themeSlug] })
      qc.invalidateQueries({ queryKey: ['capability-tree', themeSlug] })
      setBannerVisible(false)
    }
  }, [themes, bannerVisible, currentDataFrom, themeSlug, qc])

  return { requestRecompute: mutation.mutate, isRequesting: mutation.isPending, bannerVisible }
}
```

### 9.4 Capability panel — 5 UI states

```
State 1: CLOSED
  Scorecard row shows "Explore capabilities ->" button
  ticker state = null -> useCapabilityTree disabled

State 2: LOADING
  useCapabilityTree fires on ticker set
  Panel opens with TreeLoadingState:
    - Company name in header (from scorecard row, instantly available)
    - 3 skeleton node rows with pulse animation
    - RootConstraintCard skeleton pinned at bottom
  Typical duration: <200ms

State 3: LOADED (default)
  All depth-1 nodes collapsed
  Each node: label, NodeScoreBadge, one-line why_hard
  ">" if can_go_deeper=true; "Physics limit" label if false
  "Companies v" button on every node
  RootConstraintCard always visible at bottom (not collapsible):
    root_constraint_label, root_constraint_rationale,
    cross_industry_applications chips, root_controlling_companies
  Panel header: company name, ticker, freshness, "Expand all", "x"

State 4A: NODE EXPANDED
  Children render inline with 24px indent + connecting left border
  Parent collapses to one-line summary (hover for full content)
  Parent ">" becomes "v" — collapse retains children in state (instant re-expand)
  Multiple branches can be expanded simultaneously

State 4B: COMPANIES DRAWER
  Inline expansion below node — not a modal, not a second panel
  Public: ticker badge, name, role, gross_margin, roic_vs_wacc badge,
    "View in StockerPro" link, "Add to watchlist" button
  Private: name, role, "Private — no financial data" chip
  Close with "Companies ^"

State 5: ERROR
  404: "Capability analysis not yet available for {ticker}. The company
        may not be in a bottleneck layer, or the pipeline may still be
        building this analysis." + [Request recompute] button
  500: "Analysis failed to load." + [Try again] button
  RootConstraintCard NOT shown in error state
```

### 9.5 NodeScoreBadge colour rules

| Score | Colour | Label |
|---|---|---|
| 9.0–10.0 | Red `#991B1B` | Physics-bounded |
| 7.5–8.9 | Orange `#C2410C` | Process-bounded |
| 5.0–7.4 | Amber `#B45309` | Capital-solvable |
| 0.0–4.9 | Green `#065F46` | Commodity |

---

## 10. Sequence Diagrams

### 10.1 Full pipeline — all 3 stages (happy path)

```
APScheduler  ThemePipelineRunner  Providers        OpenRouter   Supabase
     |               |                |                 |            |
     |--weekly------>|                |                 |            |
     |               |--INSERT run------------------------------------>|
     |        [STAGE 1]              |                 |            |
     |               |--OpenBB SIC-->|                 |            |
     |               |--Comtrade---->|                 |            |
     |               |--edgartools-->|                 |            |
     |               |--spaCy NLP--->|                 |            |
     |               |--NetworkX---->|                 |            |
     |               |--INSERT graph---------------------------------->|
     |        [STAGE 2]              |                 |            |
     |               |--yfinance---->|                 |            |
     |               |--INSERT scores--------------------------------->|
     |        [STAGE 3 per company]  |                 |            |
     |               |--INSERT tree record------------------------------>|
     |               |               | depth-1 prompt->|            |
     |               |               |<--JSON nodes----|            |
     |               |--INSERT nodes depth-1-------------------------->|
     |               | [asyncio.gather parallel depth-2]              |
     |               |               | depth-2 prompts>|            |
     |               |               |<--JSON batches--|            |
     |               |--INSERT nodes depth-2-------------------------->|
     |               | [repeat until all can_go_deeper=false]         |
     |               |               | root synthesis->|            |
     |               |               |<--root JSON-----|            |
     |               |--UPDATE tree (root)------------------------------>|
     |               |--UPDATE run status=completed-------------------->|
```

### 10.2 OpenRouter primary failure and fallback

```
CapabilityTreeBuilder  OpenRouterClient  Primary model  Fallback model
        |                     |               |               |
        |--_generate_children>|               |               |
        |                     |--POST-------->|               |
        |                     |<--429 --------|               |
        |                     | [tenacity wait 4s, retry]     |
        |                     |--POST-------->|               |
        |                     |<--429 --------|               |
        |                     | [tenacity wait 8s, retry]     |
        |                     |--POST-------->|               |
        |                     |<--429 --------|               |
        |                     | [3 retries exhausted]         |
        |                     | [_use_fallback=True]          |
        |                     |--POST---------------------------->|
        |                     |<--200 OK JSON--------------------|
        |<--(content, tokens, "google/gemma-4-31b-it:free")       |
        | [fallback_calls += 1]                                    |
```

### 10.3 User opens capability panel

```
User    CapabilityPanel  useCapabilityTree  FastAPI      Supabase
  |           |                |               |              |
  |--click--->|                |               |              |
  | "Explore" |--set ticker--->|               |              |
  |           | panel opens    |--GET /tree--->|              |
  |           | TreeLoading    |               |--SELECT tree->|
  |           |                |               |--SELECT nodes>|
  |           |                |               |<--flat rows---|
  |           |                |               |_build_nested_tree()
  |           |                |<--nested JSON-|              |
  |           |<--tree data----|               |              |
  |<--panel open (depth-1 + RootConstraintCard always visible)
  |                            |               |              |
  |--click "> expand"          |               |              |
  |  [pure React setState]                     |              |
  |<--children visible (instant, 0ms network)                |
  |                            |               |              |
  |--click "Companies v"       |               |              |
  |  [reads node.controlling_companies from loaded cache]    |
  |<--drawer opens (instant, 0ms network)                    |
```

### 10.4 Recompute and auto-refresh

```
User   useRecompute  FastAPI   Supabase   APScheduler (15-min)
  |         |            |         |             |
  |--click  |            |         |             |
  |"Recompute"---------->|         |             |
  |         |            |--UPDATE force_recompute=TRUE
  |         |            |<--202---|             |
  |         | setBannerVisible=true              |
  |<--banner |  poll /themes 5min               |
  |                                       --fires>
  |                                  |--SELECT force_recompute=TRUE
  |                                  |--UPDATE force_recompute=FALSE
  |                                  |  ThemePipelineRunner (all 3 stages)
  |                                  |  UPDATE status=completed
  |         |  [polling detects new last_run_at]             |
  |         |--invalidateQueries supply-chain                |
  |         |--invalidateQueries capability-tree             |
  |<--all tabs refresh, banner disappears                    |
```

### 10.5 Partial tree build (llm_error node)

```
ThemePipelineRunner  CapabilityTreeBuilder   OpenRouter   Supabase
        |                    |                   |             |
        |--tree_build:AMAT-->|                   |             |
        |                    |--depth-1 prompt-->|             |
        |                    |<--JSON nodes------|             |
        |                    |--INSERT depth-1 nodes---------->|
        |                    |--depth-2 [asyncio.gather]       |
        |                    |<--OpenRouterJSONError (2 retries failed)
        |                    | create llm_error=True node      |
        |                    | build_status = "partial"        |
        |                    | [other branches continue]       |
        |                    |--root synthesis----------------->|
        |                    |<--root JSON-------------------  |
        |<--(tree,"partial")-|                   |             |
        |--_persist_tree (build_status="partial")------------>|
        |--LOG warn "partial build"-------------------------->|
        | [continues to next company, does NOT abort run]     |
```

---

## 11. Class Diagram

```
SmartOrchestrator
  - db: SupabaseClient
  - scheduler: AsyncIOScheduler
  + start()
  + run_all_themes()
  + run_queued_recomputes()
  - _should_run(theme_id) -> (bool, str)
  - _check_new_filings(theme_id, since) -> str | None
        | creates
        v
ThemePipelineRunner
  - theme_id: int; triggered_by: str; log: PipelineLogger
  + execute()
  - _persist_graph(run_id, GraphResult)
  - _persist_scores(run_id, list[ScoreResult])
  - _persist_tree(run_id, CapabilityTree)
        |
        +-- UniverseBuilder:  run() -> Universe
        +-- GraphBuilder:     run() -> GraphResult
        +-- Scorer:           run() -> list[ScoreResult]
        +-- CapabilityTreeBuilder
              - company: ScoreResult
              - client: OpenRouterClient
              - yf: YFinanceClient
              - all_nodes: list[CapabilityNode]
              - llm / primary / fallback: int
              + run() -> (CapabilityTree, int, int, int)
              - _generate_children(parent, depth) -> list[CapabilityNode]
              - _build_prompt(parent, depth) -> str
              - _parse_nodes(data, parent_id, depth, pt, ct, model)
              - _enrich_controlling_companies(nodes)
              - _synthesise_root_constraint(leaves) -> dict
              - _extract_root_companies(leaves) -> list[dict]

OpenRouterClient
  - primary: str   # deepseek/deepseek-r1:free
  - fallback: str  # google/gemma-4-31b-it:free
  - _limiter: AsyncLimiter(18, 60)
  - _use_fallback: bool
  + complete(system, user, max_tokens) -> (str, int, int, str)
  + complete_json(system, user, max_tokens) -> (Any, int, int, str)
  - _call_with_retry(model, ...) -> (str, int, int)
  - _raw_call(model, ...) -> (str, int, int)

PipelineLogger
  + start_run(theme_id, triggered_by) -> UUID
  + set_stage(run_id, stage)
  + log(run_id, step, status, message, payload?)
  + update_llm_counts(run_id, total, primary, fallback)
  + complete_run(run_id, duration, stats)
  + fail_run(run_id, error_message)

Pydantic models (models.py):
  LayerConfig(node_id, label, layer_index, sic_ranges, description)
  TickerInfo(symbol, company_name, sic_code, layer_id, revenue_ttm, has_10k)
  Universe(theme_id, tickers, layers, filings_read, geo_concentration)
  GraphNode(node_id, label, layer_index, hhi_score, cr3_score,
            betweenness, is_bottleneck, company_count, geo_hhi, edges)
  GraphResult(nodes, node_count, edge_count, bottleneck_count)
    method: is_bottleneck(node_id) -> bool
  ScoreResult(ticker, node_id, company_name, bottleneck_score,
              hhi_component, margin_component, roic_component,
              backlog_component, margin_trend_3yr, roic_vs_wacc,
              backlog_ratio, confidence_flag, data_gaps)
  CapabilityNode(node_id, parent_node_id, depth, label, description,
                 why_hard, replicability_score, replicability_rationale,
                 controlling_companies, can_go_deeper, is_root_constraint,
                 llm_error, llm_prompt_tokens, llm_completion_tokens,
                 llm_model_used)
  CapabilityTree(ticker, company_name, node_id, max_depth_reached,
                 total_nodes, root_constraint_label, root_constraint_rationale,
                 cross_industry_applications, root_controlling_companies,
                 build_status, nodes: list[CapabilityNode])
```

---

## 12. API Contract

### GET /supply-chain/themes
```json
[{"slug":"ai-infrastructure","display_name":"AI Infrastructure",
  "last_run_at":"2026-06-08T06:22:11Z","data_freshness_days":7,
  "companies_analysed":34,"bottleneck_nodes_found":2,
  "capability_trees_built":8,"status":"completed","recompute_pending":false}]
```

### GET /supply-chain/{theme}/scorecard
```json
{"theme_slug":"ai-infrastructure","run_id":"a3f2...",
 "companies":[{"ticker":"AMAT","company_name":"Applied Materials Inc",
   "node_id":"semiconductor_equipment","bottleneck_score":87.4,
   "margin_trend_3yr":4.2,"roic_vs_wacc":8.1,"backlog_ratio":1.8,
   "confidence_flag":"high","data_gaps":[],
   "tree_available":true,"max_depth_reached":4,"build_status":"completed"}]}
```

### GET /supply-chain/{theme}/company/{ticker}/tree
```json
{"ticker":"AMAT","company_name":"Applied Materials Inc",
 "run_id":"a3f2...","computed_at":"2026-06-08T06:22:11Z",
 "data_freshness_days":7,"max_depth_reached":4,"total_nodes":22,
 "build_status":"completed",
 "root_constraint_label":"Atomic-scale uniformity in plasma-material interaction",
 "root_constraint_rationale":"All AMAT constraints trace back to...",
 "cross_industry_applications":["EUV optics","HBM memory","power semiconductors"],
 "root_controlling_companies":[
   {"ticker":"LIN","name":"Linde plc","role":"Ultra-pure process gases",
    "public":true,"gross_margin":42.1,"roic_vs_wacc":6.3},
   {"ticker":null,"name":"Mitsui Chemicals","role":"Specialty precursors",
    "public":false,"gross_margin":null,"roic_vs_wacc":null}],
 "tree":{"node_id":"amat_root","label":"Applied Materials Inc","depth":0,
   "children":[{"node_id":"cvd_ald_deposition","label":"CVD/ALD Deposition Physics",
     "depth":1,"replicability_score":9.0,
     "why_hard":"Atomic layer uniformity requires plasma chemistry control...",
     "controlling_companies":[...],"can_go_deeper":true,
     "is_root_constraint":false,"llm_error":false,
     "llm_model_used":"deepseek/deepseek-r1:free",
     "children":[{"node_id":"plasma_chemistry_control",
       "label":"Plasma Chemistry Control","depth":2,
       "replicability_score":9.5,"can_go_deeper":false,
       "is_root_constraint":true,"llm_error":false,"children":[]}]}]}}
```

### POST /supply-chain/recompute/{theme_slug}
```json
{"status":"queued",
 "message":"Recompute queued for ai-infrastructure. Will begin within 15 minutes.",
 "current_data_from":"2026-06-08T06:22:11Z"}
```

### Error responses
```json
{"detail":"Theme 'unknown' not found"}
{"detail":"No capability tree found for AMAT in theme ai-infrastructure. The company may not be in a bottleneck layer, or the pipeline may still be building this analysis."}
{"detail":"No completed pipeline run found for this theme"}
```

---

## 13. Implementation Plan

### Phase 1 — Foundation

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 1 | .env files from Section 3 | 1h | `python -c "import os; print(os.environ['OPENROUTER_API_KEY'])"` succeeds |
| 2 | Supabase migration: all 7 tables + indexes | 3h | Tables exist; `sc_themes` has 5 rows with parseable `layer_config` JSONB |
| 3 | `models.py`: all Pydantic models | 2h | All models import; `GraphResult.is_bottleneck()` unit test passes |
| 4 | `logger.py`: PipelineLogger with `update_llm_counts` | 2h | `start_run -> set_stage -> log -> update_llm_counts -> complete_run` writes correct rows |

**Gate:** Synthetic pipeline writes valid rows to all 7 tables.

### Phase 2 — Stages 1 and 2

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 5 | `openbb_client.py`: `search_by_sic(sic_codes)` | 2h | Returns >=5 tickers for `['3674','3559']` |
| 6 | `comtrade.py`: `get_trade_flows(hs_codes)` | 2h | Returns country share dict for `['8541']` summing ~1.0 |
| 7 | `UniverseBuilder` | 3h | For `ai-infrastructure`: >=10 tickers with `layer_id`, `filings_read > 0` |
| 8 | `edgar_nlp.py`: `extract_supplier_edges(ticker, nlp)` | 3h | Returns >=1 edge tuple for AMAT; no crash on tickers with no disclosure |
| 9 | `GraphBuilder` | 5h | >=5 nodes; HHI 0.0–1.0; >=1 `is_bottleneck=True` |
| 10 | `yfinance_client.py`: `get_key_ratios(ticker)` | 2h | AMAT returns `{gross_margin: float, roic_vs_wacc: float}`; unknown ticker returns `{}` |
| 11 | `Scorer` | 4h | All bottleneck companies scored 0–100; `confidence_flag` set; `data_gaps` populated |

**Gate:** ThemePipelineRunner through Stages 1–2 for `ai-infrastructure` completes without error.

### Phase 3 — OpenRouter client and Stage 3

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 12 | `OpenRouterClient`: rate limiter, retry, fallback | 4h | `complete_json()` returns parsed JSON; AsyncLimiter enforces 18/min; fallback triggers after 3 primary failures; `llm_model_used` reflects actual model |
| 13 | `CapabilityTreeBuilder._generate_children()` — depth-1 only | 3h | For AMAT: returns 3–6 valid `CapabilityNode` objects with all fields populated |
| 14 | `CapabilityTreeBuilder.run()` — full breadth-first build | 5h | For AMAT: multiple depth levels; >=1 `is_root_constraint=True` node |
| 15 | `_enrich_controlling_companies()` | 2h | Public companies have `gross_margin` and `roic_vs_wacc` populated |
| 16 | `_synthesise_root_constraint()` | 2h | Returns dict with `root_constraint_label`, `root_constraint_rationale`, `cross_industry_applications` |
| 17 | `_persist_tree()` + Stage 3 integration in ThemePipelineRunner | 2h | After full run: `sc_capability_trees` has 1 row per bottleneck company; `sc_capability_nodes` has all nodes; `llm_primary_calls` and `llm_fallback_calls` populated |

**Gate:** Full pipeline run for `ai-infrastructure` completes all 3 stages. `sc_capability_trees` has >=1 row with non-null `root_constraint_label`.

### Phase 4 — Orchestration

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 18 | `SmartOrchestrator`: all 3 jobs with `_check_new_filings` | 4h | `_should_run()` correct for all 3 trigger conditions; `force_recompute=TRUE` triggers run within 15 min |

**Gate:** Set `force_recompute=TRUE` on one theme. Confirm run starts within 15 minutes with `triggered_by='user_recompute'`.

### Phase 5 — API read layer

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 19 | All 5 read endpoints + recompute + `_build_nested_tree()` | 4h | Tree endpoint returns nested JSON with `children` arrays in <200ms; 404 returns descriptive message; recompute returns 202 and sets flag |

**Gate:** Call tree endpoint after completed pipeline run. Validate nested structure with children arrays.

### Phase 6 — Frontend

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 20 | `useCapabilityTree` and `useRecompute` hooks | 3h | Tree hook disabled when `ticker=null`; recompute hook polls, auto-refreshes, dismisses banner |
| 21 | Theme grid + `ThemeHeader` + `RecomputeBanner` | 3h | 5 theme cards; freshness data correct; banner shows and hides |
| 22 | `ChainMapTab` + `ScorecardTab` with tree chip | 4h | Graph renders; scorecard shows `max_depth_reached` chip; "Explore" button present |
| 23 | `CapabilityPanel` — all 5 states | 6h | State 2→3 <200ms; State 4A expand/collapse instant (0 network); State 4B public financials from stored data, private label; State 5 error copy correct for 404 vs 500 |
| 24 | `NodeCompaniesDrawer` + `RootConstraintCard` + watchlist | 4h | Public financials from stored data (no live call); private label correct; "Add to watchlist" posts with `node_id` context; `RootConstraintCard` visible from State 3 |
| 25 | `PipelineLogTab` with LLM breakdown | 2h | Run history shows all 3 stages; `llm_primary_calls` and `llm_fallback_calls` visible per run |

**Final gate:** Pipeline ran all 3 stages. All 5 panel states reachable. "Add to watchlist" appears in watchlist with `source='supply-chain-drill-down'` and `node_id`. `TreeErrorState` renders for a company with no tree.

### Effort summary

| Phase | Description | Hours |
|---|---|---|
| Phase 1 | Foundation | 8h |
| Phase 2 | Stages 1 and 2 | 21h |
| Phase 3 | OpenRouter + Stage 3 | 18h |
| Phase 4 | Orchestration | 4h |
| Phase 5 | API read layer | 4h |
| Phase 6 | Frontend | 22h |
| **Total** | | **77h** |

---

## 14. Open Risks and Limitations

### 14.1 OpenRouter free tier constraints

**Rate limit:** 20 req/min globally per API key. Pipeline uses 18/min. If key is shared with other uses, reduce `PIPELINE_LLM_RATE_LIMIT_PER_MIN` further and monitor via `llm_call_count` in `sc_pipeline_runs`.

**Model availability:** Free models can become unavailable without notice. Fallback handles 3 consecutive primary failures by switching to `google/gemma-4-31b-it:free`. If fallback also fails, affected nodes are marked `llm_error=True` and the tree continues as `build_status=partial`. Pipeline does not abort.

**Upgrading to paid:** Remove `:free` suffix from model names in `.env`. No code changes required.

### 14.2 LLM output quality

Physics accuracy is not guaranteed. Treat as research starting point. `response_format: {"type": "json_object"}` guarantees valid JSON at the top level but not schema compliance — `_parse_nodes` handles all missing fields with `.get()` and defaults. Tree inconsistency across runs is inherent; the UI always shows the tree from the latest `run_id`.

### 14.3 Stage 1 data quality

Sparse 10-K supplier disclosure produces a partial graph. Stage 3 is not affected — it uses LLM training knowledge, not NLP graph edges. Private companies invisible to Stage 1 appear in Stage 3 `controlling_companies` with `public: false` and null financial data. All yfinance calls handle `NaN` by returning `None` — missing fields go into `data_gaps`.

### 14.4 Pipeline duration

Stage 3 adds 20–60 minutes per theme. Five themes sequentially: 8–20 hours total. Sunday 02:00 start provides a 20-hour window. If this is insufficient, run themes in parallel using separate FastAPI `BackgroundTasks` rather than sequential APScheduler jobs.

---

*End of design document v3.0*  
*Key changes from v2.0: OpenRouter primary/fallback client with rate limiting and retry, complete implementations of all previously-stubbed methods, full environment configuration, layer_config JSONB structure with seed data for all 5 themes, complete FastAPI handler code including tree assembly algorithm, full React hooks, UI error states (State 5), failure sequence diagrams, NodeScoreBadge colour rules.*

---

## 15. Theme Management

### 15.1 Design principle

Theme definitions are version-controlled in a YAML config file. The database owns runtime state only (is the theme active, does it need recomputing, when did it last run). This means:

- Adding, editing, or disabling a theme is a YAML change plus one CLI command
- Theme definitions are reviewable in git history
- No SQL migrations are needed when theme definitions change
- All historical pipeline data is retained when a theme is disabled

### 15.2 What delete actually means

**Soft disable** — stops the theme running in the scheduler and hides it from the UI, but retains all historical data. This is the correct operation in 99% of cases. Achieved by setting `is_active: false` in the YAML and running the sync script.

**Hard delete** — permanently removes the theme and cascade-deletes all associated data (`ON DELETE CASCADE` on all child tables). Irreversible. Intentionally not exposed as a script or API endpoint — it requires a conscious decision executed directly in the Supabase SQL editor:

```sql
DELETE FROM sc_themes WHERE slug = 'ev-batteries';
-- Cascades to all pipeline runs, graph nodes, scores, trees
```

### 15.3 File structure addition

```
backend/
  supply_chain/
    themes_config.yaml        # source of truth for all theme definitions
    sync_themes.py            # CLI script: upserts sc_themes from YAML
    router.py                 # add PATCH /admin/themes/{slug}
```

### 15.4 themes_config.yaml — complete file

```yaml
# supply_chain/themes_config.yaml
# Source of truth for theme definitions.
# To add a theme:    add an entry, run python sync_themes.py
# To edit a theme:   edit in place, run python sync_themes.py
# To disable:        set is_active: false, run python sync_themes.py
# Hard delete:       DELETE FROM sc_themes WHERE slug='...' in Supabase SQL only

themes:

  - slug: ai-infrastructure
    display_name: AI Infrastructure
    description: Hardware stack enabling AI model training and inference
    is_active: true
    hs_codes: ["8541", "8542", "8473", "8504"]
    sic_codes: ["3674", "3672", "3559", "7372"]
    layer_config:
      layers:
        - node_id: raw_materials
          label: Raw Materials
          layer_index: 0
          description: Upstream materials suppliers
          sic_ranges:
            - {from: "2800", to: "2899", description: Specialty chemicals}
        - node_id: wafer_substrate
          label: Wafer and Substrate
          layer_index: 1
          description: Silicon and substrate suppliers
          sic_ranges:
            - {from: "3674", to: "3674", description: Semiconductor wafers}
        - node_id: semiconductor_equipment
          label: Semiconductor Equipment
          layer_index: 2
          description: CVD, ALD, etch, lithography tools
          sic_ranges:
            - {from: "3559", to: "3559", description: Special industry machinery}
        - node_id: advanced_packaging
          label: Advanced Packaging
          layer_index: 3
          description: TSMC, OSAT, substrate packaging
          sic_ranges:
            - {from: "3672", to: "3672", description: Packaging}
        - node_id: datacenter_oem
          label: Data Centre OEM
          layer_index: 4
          description: Server and rack manufacturers
          sic_ranges:
            - {from: "3577", to: "3577", description: Computer peripherals}

  - slug: ev-batteries
    display_name: EV Batteries
    description: Supply chain for electric vehicle battery systems
    is_active: true
    hs_codes: ["8507", "2804", "2819", "2869"]
    sic_codes: ["3691", "2819", "3714", "2869"]
    layer_config:
      layers:
        - node_id: lithium_mining
          label: Lithium and Cobalt Mining
          layer_index: 0
          description: Raw material extraction
          sic_ranges:
            - {from: "1040", to: "1099", description: Metal mining}
        - node_id: cathode_anode
          label: Cathode and Anode Materials
          layer_index: 1
          description: Processed battery chemistry
          sic_ranges:
            - {from: "2819", to: "2819", description: Industrial inorganic chemicals}
        - node_id: cell_manufacturing
          label: Cell Manufacturing
          layer_index: 2
          description: Lithium-ion cell producers
          sic_ranges:
            - {from: "3691", to: "3691", description: Storage batteries}
        - node_id: pack_assembly
          label: Pack Assembly and BMS
          layer_index: 3
          description: Battery pack integration
          sic_ranges:
            - {from: "3714", to: "3714", description: Motor vehicle parts}

  - slug: defence-electronics
    display_name: Defence Electronics
    description: Electronic systems for defence applications
    is_active: true
    hs_codes: ["8803", "8526", "8543", "8542"]
    sic_codes: ["3812", "3679", "3699"]
    layer_config:
      layers:
        - node_id: specialty_materials
          label: Specialty Materials
          layer_index: 0
          description: Titanium, tungsten, specialty alloys
          sic_ranges:
            - {from: "3350", to: "3357", description: Specialty metals}
        - node_id: electronic_components
          label: Electronic Components
          layer_index: 1
          description: Passive and active components
          sic_ranges:
            - {from: "3679", to: "3679", description: Electronic components NEC}
        - node_id: defence_systems
          label: Defence Systems
          layer_index: 2
          description: EW, radar, comms systems
          sic_ranges:
            - {from: "3812", to: "3812", description: Defence electronics}

  - slug: energy-transition
    display_name: Energy Transition
    description: Equipment and materials enabling grid-scale clean energy
    is_active: true
    hs_codes: ["8502", "8504", "8541", "2818"]
    sic_codes: ["3612", "3699", "3559", "3350"]
    layer_config:
      layers:
        - node_id: rare_earth_materials
          label: Rare Earth Materials
          layer_index: 0
          description: Rare earth oxides and metals
          sic_ranges:
            - {from: "2819", to: "2819", description: Inorganic chemicals}
        - node_id: magnets_transformers
          label: Magnets and Transformers
          layer_index: 1
          description: Permanent magnets, grid transformers
          sic_ranges:
            - {from: "3612", to: "3612", description: Power transformers}
        - node_id: grid_equipment
          label: Grid Equipment
          layer_index: 2
          description: Switchgear, inverters, grid systems
          sic_ranges:
            - {from: "3699", to: "3699", description: Electrical apparatus}

  - slug: biotech-cdmo
    display_name: Biotech CDMO
    description: Contract development and manufacturing for biologics
    is_active: true
    hs_codes: ["3002", "2941", "2836", "2835"]
    sic_codes: ["2836", "2835", "8731", "2869"]
    layer_config:
      layers:
        - node_id: raw_biologics
          label: Raw Biologics Materials
          layer_index: 0
          description: Cell culture media, lipid nanoparticles
          sic_ranges:
            - {from: "2836", to: "2836", description: Pharmaceutical preparations}
        - node_id: cdmo_services
          label: CDMO Services
          layer_index: 1
          description: Contract biologic manufacturing
          sic_ranges:
            - {from: "8731", to: "8731", description: Commercial physical research}
        - node_id: drug_delivery
          label: Drug Delivery Systems
          layer_index: 2
          description: Formulation and delivery platforms
          sic_ranges:
            - {from: "2835", to: "2835", description: In vitro diagnostics}
```

### 15.5 sync_themes.py — complete implementation

```python
#!/usr/bin/env python3
# sync_themes.py
# Usage:  python sync_themes.py
# Run after any change to themes_config.yaml.
# Safe to run repeatedly — upserts on slug, never hard-deletes.
# Soft-disables any theme in DB that is absent from the YAML.

import yaml, json, os, sys
from pathlib import Path
from supabase import create_client

YAML_PATH = Path(__file__).parent / "themes_config.yaml"


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    db = create_client(url, key)

    with open(YAML_PATH) as f:
        config = yaml.safe_load(f)

    yaml_slugs = set()

    for theme in config["themes"]:
        slug = theme["slug"]
        yaml_slugs.add(slug)

        row = {
            "slug":         slug,
            "display_name": theme["display_name"],
            "description":  theme.get("description"),
            "hs_codes":     theme.get("hs_codes", []),
            "sic_codes":    theme.get("sic_codes", []),
            "layer_config": json.dumps(theme["layer_config"]),
            "is_active":    theme.get("is_active", True),
            # force_recompute is runtime state — deliberately excluded
            # so upsert never overwrites a pending recompute request
        }

        db.table("sc_themes").upsert(row, on_conflict="slug").execute()

        status = "active" if theme.get("is_active", True) else "disabled"
        print(f"  Upserted [{status}]: {slug}")

    # Soft-disable any DB theme no longer present in the YAML
    db_themes = db.table("sc_themes").select("slug,is_active").execute().data
    for t in db_themes:
        if t["slug"] not in yaml_slugs and t["is_active"]:
            db.table("sc_themes")\
                .update({"is_active": False})\
                .eq("slug", t["slug"])\
                .execute()
            print(f"  Soft-disabled (removed from YAML): {t['slug']}")

    print("Sync complete.")


if __name__ == "__main__":
    main()
```

### 15.6 Admin endpoint — runtime toggle

The YAML and sync script are the primary mechanism. This endpoint exists only for emergency runtime overrides without a redeploy — for example, disabling a theme if a data provider is having issues. Running `sync_themes.py` after this call will restore the YAML value.

```python
# Add to router.py
@router.patch("/admin/themes/{slug}")
async def toggle_theme_active(
    slug: str,
    body: dict,
    x_admin_key: str = Header(None, alias="X-Admin-Key"),
    db=Depends(get_db)
):
    if x_admin_key != os.environ.get("PIPELINE_ADMIN_KEY"):
        raise HTTPException(403, "Invalid admin key")
    if "is_active" not in body or not isinstance(body["is_active"], bool):
        raise HTTPException(422, detail='Body must be {"is_active": true|false}')
    theme = _theme_or_404(db, slug)
    db.table("sc_themes")\
        .update({"is_active": body["is_active"]})\
        .eq("id", theme["id"])\
        .execute()
    action = "enabled" if body["is_active"] else "disabled"
    return {
        "slug": slug,
        "is_active": body["is_active"],
        "message": (
            f"Theme '{slug}' {action} at runtime. "
            "Running sync_themes.py will restore the YAML value."
        )
    }
```

### 15.7 Operations reference

| Operation | How | Effect |
|---|---|---|
| Add a new theme | Add entry to YAML, run `python sync_themes.py` | Row inserted into `sc_themes`; scheduler picks it up on next cadence |
| Edit a theme (layers, codes, name) | Edit YAML entry, run `python sync_themes.py` | Row updated; next pipeline run uses new definition; existing data retained by `run_id` |
| Disable a theme | Set `is_active: false` in YAML, run `python sync_themes.py` | Scheduler skips it; UI hides it; all historical data retained |
| Re-enable a theme | Set `is_active: true` in YAML, run `python sync_themes.py` | Scheduler picks it up on next cadence; no data loss |
| Emergency disable (no redeploy) | `PATCH /admin/themes/{slug}` with `{"is_active": false}` and `X-Admin-Key` | Runtime disable; overwritten on next `sync_themes.py` run |
| Hard delete | `DELETE FROM sc_themes WHERE slug='...'` in Supabase SQL editor | Permanent; cascades to all pipeline runs, scores, graph nodes, capability trees |

### 15.8 Phase 1 update — Step 1a

The seed SQL in Section 6.1 is superseded by `sync_themes.py`. The migration creates the table structure only. `sync_themes.py` populates it.

Insert as Step 1a in Section 13, Phase 1:

| Step | Deliverable | Hours | Acceptance criterion |
|---|---|---|---|
| 1a | `themes_config.yaml` with all 5 themes; `sync_themes.py` | 1h | `python sync_themes.py` upserts all 5 rows into `sc_themes`; running it twice is idempotent; setting `is_active: false` in YAML and re-running soft-disables the theme in DB without deleting data |

---

*Section 15 added in v3.1 — Theme Management via YAML config file and sync script.*