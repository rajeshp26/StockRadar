# StockerPro — Supply Chain Bottleneck Analyser
## Technical Design Document

**Version:** 1.0  
**Date:** June 2026  
**Author:** StockerPro Engineering  
**Stack:** Next.js 15 / React 19 / TypeScript · FastAPI / Python · Supabase (PostgreSQL)

---

## Table of Contents

1. [Overview and Purpose](#1-overview-and-purpose)
2. [Use Cases](#2-use-cases)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Database Schema](#4-database-schema)
5. [Dependent Libraries](#5-dependent-libraries)
6. [Path A — Background Pipeline Design](#6-path-a--background-pipeline-design)
7. [Path B — UI Read Layer Design](#7-path-b--ui-read-layer-design)
8. [Sequence Diagrams](#8-sequence-diagrams)
9. [Class Diagram](#9-class-diagram)
10. [API Contract](#10-api-contract)
11. [Implementation Plan](#11-implementation-plan)
12. [Open Risks and Limitations](#12-open-risks-and-limitations)

---

## 1. Overview and Purpose

Supply chain bottleneck analysis identifies layers within an industry's value chain where supply is structurally constrained relative to demand growth. Companies operating within these bottleneck layers command pricing power, expand margins, and generate excess returns on capital — making them compelling long-term investments before the market fully prices the constraint.

StockerPro's Supply Chain Bottleneck Analyser is a two-path feature:

- **Path A** — a background intelligence pipeline that runs continuously, ingesting public data (SEC 10-K filings, UN Comtrade trade flows, financial ratios), constructing supply chain graphs, computing concentration metrics, and persisting scored results to Supabase.
- **Path B** — a read-only UI layer that serves pre-computed results to the user with sub-200ms response times. The user selects a predefined theme and immediately sees a supply chain map, ranked company scorecard, and pipeline audit log.

The feature integrates directly with the existing StockerPro watchlist, allowing one-click promotion of a bottleneck candidate into the user's portfolio tracking workflow.

---

## 2. Use Cases

### UC-01 — Browse supply chain themes
**Actor:** Investor  
**Trigger:** User navigates to the Supply Chain section of StockerPro.  
**Flow:** The system displays a grid of predefined themes (e.g. AI Infrastructure, EV Batteries, Defence Electronics). Each card shows the theme name, last pipeline run date, number of companies analysed, and how many bottleneck nodes were detected.  
**Outcome:** User selects a theme to drill into.

### UC-02 — View the supply chain map
**Actor:** Investor  
**Trigger:** User selects a theme.  
**Flow:** The system renders an interactive directed graph. Each node represents a supply chain layer (e.g. Raw Material → Semiconductor Equipment → Advanced Packaging → Data Centre OEM). Node size is proportional to the HHI concentration score. Nodes flagged as bottlenecks are highlighted. Clicking a node shows the companies within that layer, their CR3 score, and geographic supply concentration.  
**Outcome:** User understands which layer is the structural constraint in the chosen theme.

### UC-03 — Review the company scorecard
**Actor:** Investor  
**Trigger:** User clicks a bottleneck node, or switches to the Scorecard tab.  
**Flow:** The system displays a ranked table of companies in the bottleneck layer. Each row shows ticker, bottleneck score (0–100), 3-year gross margin trend, ROIC vs WACC spread, backlog-to-revenue ratio, and a data confidence flag. Rows with incomplete data show which signals were unavailable (e.g. `backlog_not_found`).  
**Outcome:** User identifies the highest-scoring investable company in the bottleneck.

### UC-04 — Add a bottleneck candidate to watchlist
**Actor:** Investor  
**Trigger:** User clicks "Add to watchlist" on a scorecard row.  
**Flow:** The system calls the existing StockerPro `POST /watchlist` endpoint with the ticker and a context note indicating it was sourced from the bottleneck analyser.  
**Outcome:** Ticker appears in the user's watchlist with full fundamental and valuation tracking.

### UC-05 — Inspect the pipeline audit log
**Actor:** Investor / Developer  
**Trigger:** User switches to the Pipeline Log tab.  
**Flow:** The system shows the history of pipeline runs for the selected theme: run date, trigger reason (scheduler / new filing / manual), duration, number of companies processed, and step-level logs (universe build, graph build, score calculation). Failed steps show the error message.  
**Outcome:** User understands data freshness and can trust the scores.

### UC-06 — Background pipeline triggers automatically
**Actor:** System (APScheduler)  
**Trigger:** Sunday 02:00 America/Toronto (weekly full refresh) OR daily 06:00 check detects a new 10-K filing for a ticker in any active theme.  
**Flow:** The orchestrator evaluates each active theme against three trigger conditions. For themes that pass, it spawns a ThemePipelineRunner that executes three sequential steps: universe build, graph build, score calculation. Every step writes structured logs to `sc_pipeline_logs`. Results are written as a new versioned snapshot to Supabase.  
**Outcome:** Pre-computed results are refreshed; the UI serves the latest snapshot with no user-facing latency.

### UC-07 — Manual pipeline force run
**Actor:** Developer  
**Trigger:** `POST /supply-chain/admin/run/{theme_slug}` with valid API key.  
**Flow:** The system bypasses the staleness check and immediately spawns a ThemePipelineRunner for the requested theme. The run is logged with `triggered_by = 'manual'`.  
**Outcome:** Results are refreshed outside of the normal schedule.

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PATH A — BACKGROUND                       │
│                                                                   │
│  APScheduler                                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ SmartOrchestrator                                         │    │
│  │  • Weekly cron: Sun 02:00 Toronto                        │    │
│  │  • Daily check: 06:00 Toronto (new filing detector)      │    │
│  │  • Manual trigger via admin endpoint                      │    │
│  └────────────────────┬────────────────────────────────────┘    │
│                        │ for each active theme                    │
│  ┌─────────────────────▼────────────────────────────────────┐   │
│  │ ThemePipelineRunner                                        │   │
│  │                                                            │   │
│  │  Step 1: UniverseBuilder                                  │   │
│  │    └─ OpenBB (equity search by SIC)                       │   │
│  │    └─ Comtrade (HS code trade flows)                      │   │
│  │    └─ Output: ticker list + layer assignment              │   │
│  │                                                            │   │
│  │  Step 2: GraphBuilder                                      │   │
│  │    └─ edgartools (10-K text extraction)                   │   │
│  │    └─ spaCy (supplier relationship NLP)                   │   │
│  │    └─ NetworkX (directed graph + betweenness centrality)  │   │
│  │    └─ concentrationMetrics (HHI, CR3 per node)           │   │
│  │    └─ Output: DiGraph with scored nodes                   │   │
│  │                                                            │   │
│  │  Step 3: Scorer                                           │   │
│  │    └─ yfinance (gross margin, ROIC components)            │   │
│  │    └─ edgartools (backlog from 10-K MD&A)                 │   │
│  │    └─ concentrationMetrics (HHI component)               │   │
│  │    └─ Output: ranked company scores                       │   │
│  │                                                            │   │
│  │  PipelineLogger (writes every step to sc_pipeline_logs)   │   │
│  └────────────────────────────────────────────────────────────┘  │
│                        │                                          │
│                        ▼                                          │
│              Supabase (PostgreSQL)                                │
│              5 tables · versioned by run_id                       │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        │ pure SELECT
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│                        PATH B — UI READ LAYER                    │
│                                                                   │
│  FastAPI (3 read endpoints, <200ms, no computation)              │
│    GET /supply-chain/themes                                       │
│    GET /supply-chain/{theme}/graph                                │
│    GET /supply-chain/{theme}/scorecard                            │
│    GET /supply-chain/{theme}/pipeline-log                         │
│                        │                                          │
│  Next.js 15 / React 19                                           │
│  TanStack Query v5 (staleTime: 1hr, background refetch)          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ ChainMapTab  │  │ ScorecardTab │  │ PipelineLogTab        │   │
│  │ Recharts SVG │  │ Sortable     │  │ Run history +         │   │
│  │ node graph   │  │ table        │  │ step log accordion    │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key architectural decisions

**Pre-computation, not on-demand.** All expensive work (NLP, graph analysis, API calls) runs in the background. The user request path touches only Supabase SELECT queries. This means the UI is fast regardless of the pipeline's complexity.

**Versioned snapshots, not in-place updates.** Each pipeline run creates a new `run_id`. Old results remain queryable. The UI always reads the latest completed run. This enables audit trails and rollback inspection.

**Smart scheduling, not fixed intervals.** The orchestrator evaluates three trigger conditions before running. A theme only re-runs if the data is stale, a new filing was detected, or a manual force was issued. This avoids unnecessary API calls to edgartools and Comtrade.

**Confidence flags, not false precision.** When data is unavailable (e.g. a company doesn't disclose backlog), the scorer records the gap in `data_gaps[]` and downgrades the confidence flag. The UI surfaces this to the user rather than hiding incomplete data.

---

## 4. Database Schema

All tables live in the existing Supabase (PostgreSQL) instance alongside the StockerPro schema. Row-level security follows the same patterns as existing StockerPro tables.

### 4.1 sc_themes

Stores the predefined theme catalogue. Populated by migration seed, not by the pipeline.

```sql
CREATE TABLE sc_themes (
    id            SERIAL PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,   -- 'ai-infrastructure'
    display_name  TEXT NOT NULL,          -- 'AI Infrastructure'
    description   TEXT,
    hs_codes      TEXT[],                 -- ['8541','8542'] UN Comtrade HS codes
    sic_codes     TEXT[],                 -- ['3674','3672'] SEC SIC codes
    layer_config  JSONB,                  -- ordered layer definitions for graph
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Initial seed: 5 predefined themes
INSERT INTO sc_themes (slug, display_name, hs_codes, sic_codes, layer_config) VALUES
  ('ai-infrastructure',    'AI Infrastructure',      ARRAY['8541','8542','8473'],
   ARRAY['3674','3672','7372'], '{"layers":[...]}'),
  ('ev-batteries',         'EV Batteries',           ARRAY['8507','2804','2819'],
   ARRAY['3691','2819','3714'], '{"layers":[...]}'),
  ('defence-electronics',  'Defence Electronics',    ARRAY['8803','8526','8543'],
   ARRAY['3812','3812','3679'], '{"layers":[...]}'),
  ('energy-transition',    'Energy Transition',      ARRAY['8502','8504','2818'],
   ARRAY['3612','3699','3350'], '{"layers":[...]}'),
  ('biotech-cdmo',         'Biotech CDMO',           ARRAY['3002','2941','2836'],
   ARRAY['2836','2835','8731'], '{"layers":[...]}');
```

### 4.2 sc_pipeline_runs

One row per pipeline execution per theme. The UI reads this to show data freshness.

```sql
CREATE TABLE sc_pipeline_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    theme_id      INTEGER REFERENCES sc_themes(id),
    triggered_by  TEXT NOT NULL,   -- 'scheduler' | 'new_filing:{ticker}' | 'manual'
    status        TEXT NOT NULL,   -- 'running' | 'completed' | 'failed'
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    duration_secs INTEGER,
    error_message TEXT,
    stats         JSONB,           -- {tickers_processed, edges_extracted, filings_read}
    schema_version TEXT DEFAULT '1.0'
);

CREATE INDEX ON sc_pipeline_runs (theme_id, status, completed_at DESC);
```

### 4.3 sc_pipeline_logs

Step-level structured log. Every log call from every pipeline step writes here.

```sql
CREATE TABLE sc_pipeline_logs (
    id        BIGSERIAL PRIMARY KEY,
    run_id    UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    step      TEXT NOT NULL,   -- 'universe_build' | 'graph_build' | 'score_calc'
    status    TEXT NOT NULL,   -- 'started' | 'ok' | 'warn' | 'error'
    message   TEXT NOT NULL,
    payload   JSONB,           -- step-specific structured data
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON sc_pipeline_logs (run_id, logged_at);
```

### 4.4 sc_supply_chain_graph

One row per node per run. Edges are stored as JSONB on the source node.

```sql
CREATE TABLE sc_supply_chain_graph (
    id            BIGSERIAL PRIMARY KEY,
    run_id        UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    theme_id      INTEGER REFERENCES sc_themes(id),
    node_id       TEXT NOT NULL,       -- 'semiconductor_equipment'
    node_label    TEXT NOT NULL,       -- 'Semiconductor Equipment'
    layer_index   INTEGER NOT NULL,    -- 0=raw material, 1=component, 2=subsystem...
    hhi_score     NUMERIC(6,4),        -- 0.0 to 1.0
    cr3_score     NUMERIC(6,4),        -- top-3 market share, 0.0 to 1.0
    betweenness   NUMERIC(8,6),        -- NetworkX betweenness centrality
    is_bottleneck BOOLEAN DEFAULT FALSE,
    company_count INTEGER,
    edges         JSONB,               -- [{target, weight, evidence_tickers:[]}]
    geo_hhi       NUMERIC(6,4),        -- geographic concentration from Comtrade
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON sc_supply_chain_graph (theme_id, run_id);
CREATE INDEX ON sc_supply_chain_graph (run_id, is_bottleneck);
```

### 4.5 sc_company_scores

One row per company per run. This is the primary table the scorecard UI reads.

```sql
CREATE TABLE sc_company_scores (
    id                BIGSERIAL PRIMARY KEY,
    run_id            UUID REFERENCES sc_pipeline_runs(id) ON DELETE CASCADE,
    theme_id          INTEGER REFERENCES sc_themes(id),
    ticker            TEXT NOT NULL,
    node_id           TEXT NOT NULL,     -- matches sc_supply_chain_graph.node_id
    company_name      TEXT,
    bottleneck_score  NUMERIC(5,2),      -- 0 to 100, weighted composite
    hhi_component     NUMERIC(5,2),      -- 0 to 35 (weight 0.35)
    margin_component  NUMERIC(5,2),      -- 0 to 25 (weight 0.25)
    roic_component    NUMERIC(5,2),      -- 0 to 25 (weight 0.25)
    backlog_component NUMERIC(5,2),      -- 0 to 15 (weight 0.15)
    margin_trend_3yr  NUMERIC(6,4),      -- percentage point change
    roic_vs_wacc      NUMERIC(6,4),      -- ROIC minus WACC in percentage points
    backlog_ratio     NUMERIC(6,4),      -- backlog / trailing 12m revenue
    confidence_flag   TEXT DEFAULT 'low', -- 'high' | 'medium' | 'low'
    data_gaps         TEXT[],            -- ['backlog_not_found','roic_estimated']
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON sc_company_scores (theme_id, run_id, bottleneck_score DESC);
CREATE INDEX ON sc_company_scores (run_id, node_id);
```

---

## 5. Dependent Libraries

### 5.1 Python backend (pip install)

| Library | Version | Role | Licence |
|---|---|---|---|
| `openbb` | ≥4.3 | Financial data hub: equity search by SIC, fundamental ratios | MIT |
| `edgartools` | ≥2.0 | SEC EDGAR 10-K / 10-Q text extraction and filing detection | Apache 2.0 |
| `yfinance` | ≥0.2 | Gross margin, balance sheet, income statement retrieval | Apache 2.0 |
| `networkx` | ≥3.3 | Directed supply chain graph, betweenness centrality | BSD 3-Clause |
| `spacy` | ≥3.7 | NLP pipeline for supplier relationship extraction from 10-K text | MIT |
| `en_core_web_sm` | ≥3.7 | spaCy English small model — NER for company name recognition | MIT |
| `concentrationMetrics` | ≥0.5 | HHI, CR3, Gini concentration index computation | Apache 2.0 |
| `comtradeapiclient` | ≥1.0 | UN Comtrade trade flow data by HS code and country | MIT |
| `apscheduler` | ≥3.10 | Cron and interval job scheduling for the orchestrator | MIT |
| `pandas` | ≥2.2 | Data manipulation throughout the pipeline | BSD 3-Clause |
| `httpx` | ≥0.27 | Async HTTP client for external API calls | BSD 3-Clause |
| `pydantic` | ≥2.7 | Data validation for all pipeline step inputs and outputs | MIT |
| `supabase-py` | ≥2.5 | Supabase Python client for database reads and writes | MIT |

> **Note on `en_core_web_sm`:** This model recognises organisation entities but is not fine-tuned on financial SEC text. It will produce false positives (e.g. recognising product names as companies). A custom entity ruler with known company names from the universe significantly reduces this noise. The confidence flag in `sc_company_scores` accounts for edge quality degradation.

### 5.2 Frontend (npm / existing stack)

All libraries below are already present in the StockerPro frontend. No new npm dependencies are required.

| Library | Role |
|---|---|
| Next.js 15 / React 19 | Page routing, server components |
| TanStack Query v5 | Data fetching, caching, background refetch |
| Recharts | Score bar charts, margin trend sparklines |
| Tailwind CSS | Styling consistent with existing glass design system |

### 5.3 Infrastructure

| Component | Role |
|---|---|
| Supabase (PostgreSQL) | Persistent storage for all pipeline results and logs |
| FastAPI BackgroundTasks | Lightweight async task runner for single-theme ad-hoc runs |
| APScheduler (AsyncIOScheduler) | Cron-based orchestration for the weekly and daily schedules |

---

## 6. Path A — Background Pipeline Design

### 6.1 File structure

```
backend/
  supply_chain/
    __init__.py
    scheduler.py          # SmartOrchestrator — APScheduler setup and trigger logic
    pipeline.py           # ThemePipelineRunner — coordinates steps, handles errors
    logger.py             # PipelineLogger — writes to sc_pipeline_runs and sc_pipeline_logs
    models.py             # Pydantic models for Universe, GraphResult, ScoreResult
    steps/
      __init__.py
      universe.py         # UniverseBuilder — Step 1
      graph_builder.py    # GraphBuilder — Step 2
      scorer.py           # Scorer — Step 3
    providers/
      __init__.py
      openbb_client.py    # Wrapper around OpenBB equity search
      comtrade.py         # UN Comtrade HS code trade flow client
      edgar_nlp.py        # edgartools + spaCy edge extraction
      yfinance_client.py  # Gross margin, ROIC, balance sheet
      concentration.py    # concentrationMetrics HHI / CR3 wrappers
    router.py             # FastAPI router — admin endpoints + read endpoints
```

### 6.2 SmartOrchestrator (scheduler.py)

The orchestrator runs on two APScheduler jobs. Before spawning any pipeline run, it evaluates three trigger conditions to avoid unnecessary work.

**Trigger condition 1 — Weekly cadence:** The last completed run for this theme is more than 7 days old.

**Trigger condition 2 — New filing detected:** edgartools `Company(ticker).get_filings(form='10-K')` is checked for each ticker in the theme universe. If any ticker has filed a 10-K after `last_run.completed_at`, the theme is re-run. The specific triggering ticker is recorded in `triggered_by`.

**Trigger condition 3 — Manual force:** A `force_run` flag in `sc_themes` is set to TRUE. The orchestrator runs the theme and resets the flag.

If none of the three conditions are met, the theme is skipped with a log entry at INFO level.

```python
class SmartOrchestrator:
    """
    Manages two APScheduler jobs:
      - Weekly: full refresh of all active themes (Sun 02:00 Toronto)
      - Daily:  new filing check; only re-runs themes with a detected new filing (06:00 Toronto)
    """

    def __init__(self, db: SupabaseClient):
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone="America/Toronto")

    def start(self):
        self.scheduler.add_job(
            self.run_all_themes,
            CronTrigger(day_of_week="sun", hour=2),
            id="weekly_full_refresh",
            replace_existing=True
        )
        self.scheduler.add_job(
            self.run_all_themes,
            CronTrigger(hour=6),
            id="daily_filing_check",
            replace_existing=True
        )
        self.scheduler.start()

    async def run_all_themes(self):
        themes = self.db.table("sc_themes").select("id,slug") \
            .eq("is_active", True).execute().data

        for theme in themes:
            should, reason = await self._should_run(theme["id"])
            if should:
                runner = ThemePipelineRunner(theme["id"], reason, self.db)
                await runner.execute()

    async def _should_run(self, theme_id: int) -> tuple[bool, str]:
        last = self.db.table("sc_pipeline_runs") \
            .select("completed_at") \
            .eq("theme_id", theme_id) \
            .eq("status", "completed") \
            .order("completed_at", desc=True).limit(1).execute().data

        if not last:
            return True, "no_prior_run"

        last_completed = parse(last[0]["completed_at"])
        if (datetime.utcnow() - last_completed).days >= 7:
            return True, "weekly_cadence"

        new_filing_ticker = await self._check_new_filings(theme_id, last_completed)
        if new_filing_ticker:
            return True, f"new_filing:{new_filing_ticker}"

        force = self.db.table("sc_themes").select("force_run") \
            .eq("id", theme_id).execute().data[0].get("force_run", False)
        if force:
            self.db.table("sc_themes").update({"force_run": False}) \
                .eq("id", theme_id).execute()
            return True, "manual_force"

        return False, "data_current"
```

### 6.3 ThemePipelineRunner (pipeline.py)

Coordinates the three steps sequentially. Any step failure aborts the run and sets `status = 'failed'` with the error message. Steps do not partially commit — a failed run leaves the previous completed run as the latest valid snapshot.

```python
class ThemePipelineRunner:
    def __init__(self, theme_id: int, triggered_by: str, db: SupabaseClient):
        self.theme_id = theme_id
        self.triggered_by = triggered_by
        self.logger = PipelineLogger(db)
        self.db = db

    async def execute(self):
        run_id = await self.logger.start_run(self.theme_id, self.triggered_by)
        start = datetime.utcnow()

        try:
            # Step 1: Build the company universe for this theme
            await self.logger.log(run_id, "universe_build", "started",
                                  "Building company universe")
            universe = await UniverseBuilder(self.theme_id, self.db).run()
            await self.logger.log(run_id, "universe_build", "ok",
                                  f"Universe built: {len(universe.tickers)} tickers",
                                  {"ticker_count": len(universe.tickers),
                                   "filings_found": universe.filings_read})

            # Step 2: Construct directed supply chain graph
            await self.logger.log(run_id, "graph_build", "started",
                                  "Constructing supply chain graph")
            graph_result = await GraphBuilder(universe, self.db).run()
            await self.logger.log(run_id, "graph_build", "ok",
                                  f"Graph: {graph_result.node_count} nodes, "
                                  f"{graph_result.edge_count} edges",
                                  {"nodes": graph_result.node_count,
                                   "edges": graph_result.edge_count,
                                   "bottleneck_nodes": graph_result.bottleneck_count})

            # Step 3: Score companies within bottleneck nodes
            await self.logger.log(run_id, "score_calc", "started",
                                  "Computing bottleneck scores")
            scores = await Scorer(self.theme_id, universe, graph_result, self.db).run()
            await self.logger.log(run_id, "score_calc", "ok",
                                  f"Scored {len(scores)} companies",
                                  {"companies_scored": len(scores),
                                   "high_confidence": sum(1 for s in scores
                                                          if s.confidence_flag == "high")})

            # Persist graph and scores
            await self._persist_graph(run_id, graph_result)
            await self._persist_scores(run_id, scores)

            duration = int((datetime.utcnow() - start).total_seconds())
            await self.logger.complete_run(run_id, duration, {
                "tickers_processed": len(universe.tickers),
                "edges_extracted": graph_result.edge_count,
                "filings_read": universe.filings_read
            })

        except Exception as e:
            await self.logger.fail_run(run_id, str(e))
            raise
```

### 6.4 UniverseBuilder — Step 1 (steps/universe.py)

Produces a `Universe` Pydantic model containing a list of `TickerInfo` objects, each assigned to a supply chain layer defined in `sc_themes.layer_config`.

**Data sources used:**
- OpenBB `obb.equity.search(query="", sector=..., industry=...)` filtered by SIC code — returns ticker symbols and company names within the theme's SIC codes.
- `sc_themes.layer_config` (JSONB) — maps SIC ranges to layer names (e.g. SIC 3674 → "Semiconductor Fab", SIC 3559 → "Semiconductor Equipment").
- Comtrade API — called once per theme with the HS codes from `sc_themes.hs_codes`. Returns top exporting countries and their revenue share, which feeds into `geo_hhi` on the graph node.

**Output model:**
```python
class TickerInfo(BaseModel):
    symbol: str
    company_name: str
    sic_code: str
    layer_id: str           # matches node_id in layer_config
    revenue_ttm: float      # trailing 12m revenue for HHI calculation
    has_10k: bool           # whether edgartools found a recent 10-K

class Universe(BaseModel):
    theme_id: int
    tickers: list[TickerInfo]
    filings_read: int
    geo_concentration: dict[str, float]  # {country_iso: revenue_share}
    layers: list[LayerConfig]
```

### 6.5 GraphBuilder — Step 2 (steps/graph_builder.py)

Constructs a `nx.DiGraph` where nodes are supply chain layers and edges represent supplier-customer relationships extracted from 10-K text. Persists the graph structure to `sc_supply_chain_graph`.

**NLP edge extraction process:**

1. For each ticker in the universe, edgartools fetches the latest 10-K filing: `edgar.Company(ticker).get_filings(form='10-K').latest().document`.
2. The "Business" and "Risk Factors" sections are extracted using edgartools section parsing.
3. spaCy processes each section with `en_core_web_sm`. A custom `EntityRuler` is added to the pipeline with known company names from the universe, improving recognition precision.
4. Pattern matching searches for dependency structures indicating supply relationships: "we source X from [ORG]", "sole-source supplier [ORG]", "depend on [ORG] for", "agreement with [ORG] to supply". Each match produces a candidate edge `(supplier_layer, customer_layer, confidence)`.
5. Confidence is set to 1.0 for explicit named relationships and 0.5 for generic "limited number of suppliers" patterns.

**Bottleneck identification:**

- `concentrationMetrics.herfindahl_index()` is computed per layer using `[t.revenue_ttm for t in universe.tickers_in_layer(layer)]`.
- `nx.betweenness_centrality(G, weight='weight')` is computed on the fully constructed graph.
- A node is flagged `is_bottleneck = True` if: `hhi > 0.25` AND `betweenness >= 75th percentile of all node betweenness scores`.

**Output model:**
```python
class GraphResult(BaseModel):
    graph: nx.DiGraph       # not persisted directly; serialised to node-link JSON
    node_count: int
    edge_count: int
    bottleneck_count: int
    nodes: list[GraphNode]  # typed representation for Supabase write
```

### 6.6 Scorer — Step 3 (steps/scorer.py)

Computes a 0–100 bottleneck score for every company in a bottleneck-flagged node. Companies in non-bottleneck nodes are skipped. Persists results to `sc_company_scores`.

**Score formula:**

```
bottleneck_score = (
    hhi_component     * 0.35 +   # max 35 pts: node HHI rescaled 0–35
    margin_component  * 0.25 +   # max 25 pts: 3yr gross margin change, normalised
    roic_component    * 0.25 +   # max 25 pts: ROIC minus WACC spread, normalised
    backlog_component * 0.15     # max 15 pts: backlog / TTM revenue, normalised
)
```

**Data retrieval per component:**

- `hhi_component`: Already computed in Step 2 on the node. All companies in the same node share the same HHI-derived value — it reflects the layer's structural advantage, not individual company merit.
- `margin_component`: `yf.Ticker(ticker).financials` → gross profit / revenue for the past 3 annual periods. The trend (year 3 minus year 1 in percentage points) is normalised against the theme universe's distribution.
- `roic_component`: Computed from yfinance balance sheet (invested capital = total assets − current liabilities − cash) and income statement (NOPAT = operating income × (1 − effective tax rate)). WACC is estimated using a simplified model (risk-free rate from FRED via OpenBB + equity risk premium). The ROIC − WACC spread is normalised.
- `backlog_component`: edgartools searches the MD&A section of the 10-K for the string "backlog" and extracts the subsequent dollar figure using a regex. If not found, this component scores 0 and `'backlog_not_found'` is added to `data_gaps`.

**Confidence flag logic:**

- `high`: All four components have real data. Zero entries in `data_gaps`.
- `medium`: One or two components are estimated or missing.
- `low`: Three or four components are missing or estimated. Score should be treated as directional only.

---

## 7. Path B — UI Read Layer Design

### 7.1 FastAPI router (router.py)

Four endpoints. All are pure Supabase SELECT queries. No business logic executes in the request path.

```python
@router.get("/themes")
async def list_themes() -> list[ThemeSummary]:
    """
    Returns all active themes with summary stats from their latest completed run.
    Used to render the theme selector grid on the landing page.
    """

@router.get("/{theme_slug}/graph")
async def get_graph(theme_slug: str) -> GraphResponse:
    """
    Returns node-link JSON for the latest completed run's supply chain graph.
    Includes HHI, CR3, betweenness, is_bottleneck, and edge list per node.
    """

@router.get("/{theme_slug}/scorecard")
async def get_scorecard(theme_slug: str) -> ScorecardResponse:
    """
    Returns company scores ranked by bottleneck_score DESC for the latest run.
    Includes data_freshness_days and confidence flags.
    """

@router.get("/{theme_slug}/pipeline-log")
async def get_pipeline_log(theme_slug: str) -> PipelineLogResponse:
    """
    Returns last 10 pipeline runs with their step-level logs.
    """

@router.post("/admin/run/{theme_slug}", dependencies=[Depends(verify_admin_key)])
async def force_run(theme_slug: str, background_tasks: BackgroundTasks):
    """
    Sets force_run = TRUE on the theme and enqueues a pipeline run.
    Returns immediately; pipeline runs in background.
    """
```

### 7.2 Next.js page structure

```
app/
  supply-chain/
    page.tsx                     # Theme grid — UC-01
    [theme]/
      page.tsx                   # Three-tab shell — UC-02, UC-03, UC-05
      loading.tsx                # Skeleton while TanStack Query hydrates
      _components/
        ThemeGrid.tsx            # Landing: card per theme, last run date, bottleneck count
        ThemeHeader.tsx          # Theme name, last computed date, freshness badge
        ChainMapTab.tsx          # Supply chain graph visualisation
        ScorecardTab.tsx         # Company ranking table
        PipelineLogTab.tsx       # Run history and step log accordion
        BottleneckNode.tsx       # Recharts custom node for graph
        ConfidenceBadge.tsx      # High / Medium / Low chip
        DataGapsTooltip.tsx      # Tooltip listing missing data signals
      _hooks/
        useThemes.ts             # GET /supply-chain/themes
        useSupplyChainGraph.ts   # GET /supply-chain/{theme}/graph
        useSupplyChainScores.ts  # GET /supply-chain/{theme}/scorecard
        usePipelineLog.ts        # GET /supply-chain/{theme}/pipeline-log
```

### 7.3 TanStack Query configuration

```typescript
// useSupplyChainScores.ts
export function useSupplyChainScores(themeSlug: string) {
  return useQuery({
    queryKey: ['supply-chain', 'scorecard', themeSlug],
    queryFn: () => api.get(`/supply-chain/${themeSlug}/scorecard`),
    staleTime: 60 * 60 * 1000,          // 1 hour — data changes at most weekly
    gcTime: 24 * 60 * 60 * 1000,        // 24 hours — keep in memory between tab switches
    refetchOnWindowFocus: false,          // scores don't change while user is looking at them
    retry: 2,
  })
}
```

### 7.4 ScorecardTab columns

| Column | Source field | Render |
|---|---|---|
| Ticker | `ticker` | Bold, links to StockerPro stock detail page |
| Company | `company_name` | Plain text |
| Bottleneck score | `bottleneck_score` | Progress bar 0–100, colour: red < 40, amber 40–70, green > 70 |
| Gross margin trend | `margin_trend_3yr` | Sparkline (reuses existing Sparkline component) + "+X.Xpp" label |
| ROIC vs WACC | `roic_vs_wacc` | Coloured badge: green if positive, red if negative |
| Backlog / Rev | `backlog_ratio` | "1.8×" or "N/A" if backlog_not_found |
| Confidence | `confidence_flag` | ConfidenceBadge chip + DataGapsTooltip on hover |
| Action | — | "Add to watchlist" → POST /watchlist with context `{source: 'supply-chain', theme: slug}` |

### 7.5 ChainMapTab rendering

The supply chain graph is rendered as a custom Recharts `<ComposedChart>` or a plain SVG layout (no external graph library required — the node count per theme is small, max ~6–8 nodes). Nodes are positioned by `layer_index` on the x-axis. Node area is proportional to `hhi_score`. Bottleneck nodes render with a red border and warning icon. Edges are drawn as SVG `<path>` bezier curves between layer positions. Clicking a node filters the Scorecard tab to that node's companies.

---

## 8. Sequence Diagrams

### 8.1 Background pipeline — scheduled run

```
APScheduler          SmartOrchestrator      ThemePipelineRunner    Supabase
     |                      |                       |                  |
     |-- weekly_trigger ---> |                       |                  |
     |                      |-- _should_run(theme) ->|                  |
     |                      |       <-- (True, reason) --               |
     |                      |                       |                  |
     |                      |-- execute() ---------->|                  |
     |                      |                       |-- INSERT run_id -->|
     |                      |                       |                  |
     |                      |              UniverseBuilder              |
     |                      |                       |-- SELECT theme -->|
     |                      |                       |    OpenBB search  |
     |                      |                       |    Comtrade API   |
     |                      |                       |-- LOG 'universe_build ok' -->|
     |                      |                       |                  |
     |                      |              GraphBuilder                 |
     |                      |                       |   edgartools 10-K fetch      |
     |                      |                       |   spaCy NLP pass  |
     |                      |                       |   NetworkX HHI + centrality  |
     |                      |                       |-- LOG 'graph_build ok' -->|
     |                      |                       |                  |
     |                      |              Scorer                       |
     |                      |                       |   yfinance ratios |
     |                      |                       |   edgartools backlog|
     |                      |                       |-- LOG 'score_calc ok' -->|
     |                      |                       |                  |
     |                      |                       |-- INSERT graph nodes -->|
     |                      |                       |-- INSERT company scores ->|
     |                      |                       |-- UPDATE run status='completed' ->|
```

### 8.2 UI read path — user selects a theme

```
User (browser)      Next.js           FastAPI           Supabase
     |                 |                  |                 |
     |-- click theme ->|                  |                 |
     |                 |-- GET /scorecard ->                |
     |                 |                  |-- SELECT latest run -->|
     |                 |                  |-- SELECT scores, ORDER BY bottleneck_score -->|
     |                 |                  |<-- rows (<200ms) ------|
     |                 |<-- JSON ---------|                 |
     |<-- render table |                  |                 |
     |                 |                  |                 |
     |-- click graph tab->               |                 |
     |                 |-- GET /graph ----->                |
     |                 |                  |-- SELECT graph nodes -->|
     |                 |                  |<-- rows --------|
     |                 |<-- node-link JSON|                 |
     |<-- render SVG   |                  |                 |
     |                 |                  |                 |
     |-- add to watchlist->              |                 |
     |                 |-- POST /watchlist (existing endpoint) -->
     |<-- watchlist updated              |                 |
```

### 8.3 New filing trigger

```
APScheduler (daily 06:00)    SmartOrchestrator    edgartools    Supabase
     |                              |                  |             |
     |-- daily_check_trigger ------>|                  |             |
     |                              |-- _should_run(theme_1) -->     |
     |                              |   [checks last_completed_at]   |
     |                              |-- get_filings(each ticker) -->|
     |                              |                  |-- EDGAR API call
     |                              |<-- filing_date > last_run for TICKER_X
     |                              |                  |             |
     |                              |-- execute(triggered_by='new_filing:TICKER_X') -->
     |                              |                  |-- ThemePipelineRunner -->
     |                              |                  |-- full pipeline -->|
     |                              |                  |<-- completed ------|
```

---

## 9. Class Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    supply_chain package                   │
└──────────────────────────────────────────────────────────┘

┌───────────────────────┐
│   SmartOrchestrator   │
├───────────────────────┤
│ - db: SupabaseClient  │
│ - scheduler: AsyncIOScheduler │
├───────────────────────┤
│ + start()             │
│ + run_all_themes()    │
│ - _should_run(theme_id) -> (bool, str) │
│ - _check_new_filings(theme_id, since) -> str|None │
└───────────┬───────────┘
            │ creates
            ▼
┌───────────────────────┐
│  ThemePipelineRunner  │
├───────────────────────┤
│ - theme_id: int       │
│ - triggered_by: str   │
│ - logger: PipelineLogger │
│ - db: SupabaseClient  │
├───────────────────────┤
│ + execute()           │
│ - _persist_graph(run_id, GraphResult) │
│ - _persist_scores(run_id, list[ScoreResult]) │
└───┬───────┬───────┬───┘
    │       │       │
    ▼       ▼       ▼
┌────────┐ ┌──────────────┐ ┌────────┐
│Universe│ │ GraphBuilder │ │ Scorer │
│Builder │ │              │ │        │
├────────┤ ├──────────────┤ ├────────┤
│-theme_id│ │-universe:   │ │-theme_id│
│-db     │ │  Universe   │ │-universe│
│        │ │-db          │ │-graph:  │
├────────┤ │             │ │  Graph  │
│+run()  │ ├─────────────┤ │  Result │
│->      │ │+run()       │ ├────────┤
│Universe│ │->GraphResult│ │+run()  │
└────────┘ └──────┬──────┘ │->list[ │
                  │        │  Score │
                  │        │  Result]│
                  │        └────────┘
                  │
        ┌─────────▼──────────┐
        │ providers/          │
        ├─────────────────────┤
        │ OpenBBClient        │
        │  +search_by_sic()   │
        ├─────────────────────┤
        │ ComtradeClient      │
        │  +get_trade_flows() │
        ├─────────────────────┤
        │ EdgarNLP            │
        │  +extract_edges()   │
        │  +extract_backlog() │
        ├─────────────────────┤
        │ YFinanceClient      │
        │  +get_margins()     │
        │  +get_roic()        │
        ├─────────────────────┤
        │ ConcentrationCalc   │
        │  +hhi()             │
        │  +cr3()             │
        └─────────────────────┘

┌───────────────────────┐
│   PipelineLogger      │
├───────────────────────┤
│ - db: SupabaseClient  │
├───────────────────────┤
│ + start_run(theme_id, triggered_by) -> UUID │
│ + log(run_id, step, status, message, payload) │
│ + complete_run(run_id, duration, stats) │
│ + fail_run(run_id, error_message) │
└───────────────────────┘

┌──────────────── Pydantic models (models.py) ──────────────────┐
│                                                                │
│  LayerConfig(node_id, label, layer_index, sic_codes)          │
│  TickerInfo(symbol, company_name, sic_code, layer_id,         │
│             revenue_ttm, has_10k)                             │
│  Universe(theme_id, tickers, filings_read,                    │
│           geo_concentration, layers)                          │
│  GraphNode(node_id, label, layer_index, hhi_score, cr3_score, │
│            betweenness, is_bottleneck, edges)                 │
│  GraphResult(graph, node_count, edge_count,                   │
│              bottleneck_count, nodes)                         │
│  ScoreResult(ticker, node_id, company_name,                   │
│              bottleneck_score, hhi_component,                 │
│              margin_component, roic_component,                │
│              backlog_component, margin_trend_3yr,             │
│              roic_vs_wacc, backlog_ratio,                     │
│              confidence_flag, data_gaps)                      │
└───────────────────────────────────────────────────────────────┘
```

---

## 10. API Contract

### GET /supply-chain/themes

```json
[
  {
    "slug": "ai-infrastructure",
    "display_name": "AI Infrastructure",
    "description": "...",
    "last_run_at": "2026-06-08T02:14:33Z",
    "data_freshness_days": 5,
    "companies_analysed": 34,
    "bottleneck_nodes_found": 2,
    "status": "completed"
  }
]
```

### GET /supply-chain/{theme}/scorecard

```json
{
  "theme_slug": "ai-infrastructure",
  "run_id": "a3f2...",
  "computed_at": "2026-06-08T04:22:11Z",
  "data_freshness_days": 5,
  "companies": [
    {
      "ticker": "AMAT",
      "company_name": "Applied Materials Inc",
      "node_id": "semiconductor_equipment",
      "bottleneck_score": 87.4,
      "margin_trend_3yr": 4.2,
      "roic_vs_wacc": 8.1,
      "backlog_ratio": 1.8,
      "confidence_flag": "high",
      "data_gaps": []
    },
    {
      "ticker": "ENTG",
      "company_name": "Entegris Inc",
      "node_id": "semiconductor_equipment",
      "bottleneck_score": 61.2,
      "margin_trend_3yr": 2.8,
      "roic_vs_wacc": 3.4,
      "backlog_ratio": null,
      "confidence_flag": "medium",
      "data_gaps": ["backlog_not_found"]
    }
  ]
}
```

### GET /supply-chain/{theme}/graph

```json
{
  "theme_slug": "ai-infrastructure",
  "run_id": "a3f2...",
  "nodes": [
    {
      "node_id": "raw_materials",
      "label": "Raw Materials",
      "layer_index": 0,
      "hhi_score": 0.18,
      "cr3_score": 0.52,
      "betweenness": 0.12,
      "is_bottleneck": false,
      "company_count": 6,
      "edges": [
        {"target": "semiconductor_fab", "weight": 3.2, "evidence_tickers": ["AVGO","QCOM"]}
      ]
    },
    {
      "node_id": "semiconductor_equipment",
      "label": "Semiconductor Equipment",
      "layer_index": 2,
      "hhi_score": 0.44,
      "cr3_score": 0.81,
      "betweenness": 0.68,
      "is_bottleneck": true,
      "company_count": 5,
      "edges": [
        {"target": "advanced_packaging", "weight": 5.1, "evidence_tickers": ["AMAT","LRCX","KLAC"]}
      ]
    }
  ]
}
```

### GET /supply-chain/{theme}/pipeline-log

```json
{
  "theme_slug": "ai-infrastructure",
  "runs": [
    {
      "run_id": "a3f2...",
      "triggered_by": "weekly_cadence",
      "status": "completed",
      "started_at": "2026-06-08T02:00:04Z",
      "completed_at": "2026-06-08T04:22:11Z",
      "duration_secs": 8527,
      "stats": {"tickers_processed": 34, "edges_extracted": 41, "filings_read": 29},
      "steps": [
        {"step": "universe_build", "status": "ok", "message": "Universe built: 34 tickers", "logged_at": "..."},
        {"step": "graph_build",    "status": "ok", "message": "Graph: 7 nodes, 41 edges",   "logged_at": "..."},
        {"step": "score_calc",     "status": "ok", "message": "Scored 18 companies",         "logged_at": "..."}
      ]
    }
  ]
}
```

---

## 11. Implementation Plan

Development follows a strict dependency order. No step begins until the prior step's deliverable is verified.

### Phase 1 — Foundation (Steps 1–3)

| Step | Deliverable | Estimated effort | Acceptance criterion |
|---|---|---|---|
| 1 | Supabase migration: 5 tables + indexes | 2h | Tables exist; `sc_themes` seeded with 5 themes |
| 2 | `models.py`: all Pydantic models | 2h | All models import without error; unit tests pass |
| 3 | `logger.py`: PipelineLogger | 2h | `start_run` → `log` → `complete_run` writes correct rows to all three log tables |

**Verification gate:** Run a synthetic pipeline that logs "started / ok / completed" for a dummy theme. Confirm all three tables show correct data.

### Phase 2 — Pipeline steps (Steps 4–6)

| Step | Deliverable | Estimated effort | Acceptance criterion |
|---|---|---|---|
| 4 | `steps/universe.py`: UniverseBuilder | 4h | For "ai-infrastructure" theme, returns ≥10 tickers with layer assignments |
| 5 | `steps/graph_builder.py`: GraphBuilder | 8h | For "ai-infrastructure", produces a graph with ≥5 nodes; at least 1 node flagged is_bottleneck |
| 6 | `steps/scorer.py`: Scorer | 6h | For each bottleneck company, produces a score between 0–100; confidence_flag set correctly |

**Verification gate:** Run `ThemePipelineRunner` for "ai-infrastructure" manually. Inspect `sc_supply_chain_graph` and `sc_company_scores` rows. Confirm pipeline log shows no errors and confidence flags are plausible.

### Phase 3 — Orchestration (Step 7)

| Step | Deliverable | Estimated effort | Acceptance criterion |
|---|---|---|---|
| 7 | `scheduler.py`: SmartOrchestrator | 3h | `_should_run` returns correct (bool, reason) for all three trigger conditions; scheduler starts without error on FastAPI lifespan |

**Verification gate:** Set `force_run = TRUE` on one theme in `sc_themes`. Confirm the daily check job picks it up within its next tick and triggers a full pipeline run.

### Phase 4 — API read layer (Step 8)

| Step | Deliverable | Estimated effort | Acceptance criterion |
|---|---|---|---|
| 8 | `router.py`: 4 FastAPI endpoints | 3h | All endpoints return 200 with correct schema; response time < 200ms measured locally |

**Verification gate:** Call each endpoint via curl after a completed pipeline run. Validate response JSON against the API contract in Section 10.

### Phase 5 — Frontend (Steps 9–11)

| Step | Deliverable | Estimated effort | Acceptance criterion |
|---|---|---|---|
| 9 | Theme grid page (`/supply-chain`) | 3h | Renders 5 theme cards with last run date and bottleneck count |
| 10 | ChainMapTab: supply chain graph SVG | 5h | Nodes render at correct layer positions; bottleneck nodes highlighted; clicking a node filters scorecard |
| 11 | ScorecardTab + PipelineLogTab | 4h | Table sorts by bottleneck score; "Add to watchlist" calls existing endpoint; log accordion opens step details |

**Verification gate:** Full end-to-end test: pipeline ran, data in DB, all three tabs render correct data, "Add to watchlist" appears in the user's existing watchlist.

### Total estimated effort

| Phase | Hours |
|---|---|
| Phase 1 — Foundation | 6h |
| Phase 2 — Pipeline steps | 18h |
| Phase 3 — Orchestration | 3h |
| Phase 4 — API read layer | 3h |
| Phase 5 — Frontend | 12h |
| **Total** | **42h** |

---

## 12. Open Risks and Limitations

### Data quality risks

**SEC 10-K supplier disclosure is sparse.** Companies rarely name individual suppliers. The NLP edge extraction will produce a partial graph — some layers will have zero edges. This is surfaced via `confidence_flag = 'low'` and `data_gaps`. The graph is directionally correct but not complete.

**Private companies are invisible.** If the actual choke point company is private (e.g. a specialty chemical supplier or a private gas manufacturer), it will not appear in EDGAR and will be absent from both the graph and the scorecard.

**Backlog disclosure is inconsistent.** Not all companies disclose backlog in their 10-K MD&A. The regex extraction will fail for companies that use different terminology (e.g. "order intake", "contracted revenue"). These cases receive `backlog_not_found` and score 0 on the backlog component.

### Pipeline performance risks

**Graph build step is slow.** Fetching and parsing 20–50 10-K filings per theme via edgartools + running spaCy on each takes 1–3 hours per theme. Five themes running sequentially could take 8–15 hours. If this exceeds the weekly window, implement per-theme parallel execution using FastAPI BackgroundTasks or a task queue (Celery + Redis) rather than sequential APScheduler jobs.

**Comtrade API rate limits.** The UN Comtrade API enforces request limits. Cache the trade flow response per (hs_code, year) in Supabase to avoid re-fetching on every run.

**yfinance data gaps for small-cap tickers.** yfinance returns `NaN` for some financial fields on smaller companies. All yfinance calls must handle `NaN` explicitly — treat as missing data and record in `data_gaps`.

### Model risks

**The score weights (0.35 / 0.25 / 0.25 / 0.15) are a reasonable starting point, not a validated model.** They should be back-tested against the 2021–22 semiconductor supply chain episode (where equipment and advanced packaging companies significantly outperformed) before treating the scores as investment signals. This calibration step is outside the scope of the initial implementation.

**Betweenness centrality is sensitive to graph completeness.** A node that appears central may only do so because surrounding nodes have no edges (due to sparse 10-K disclosure), not because it is genuinely central in the real supply chain. Treat centrality scores as a starting filter, not a definitive ranking.

---

*End of design document. Next step: begin Phase 1, Step 1 — Supabase migration.*

---

## 13. Capability Drill-Down Feature

### 13.1 Problem statement

The supply chain graph and scorecard (Sections 6–7) identify *which layer* is a bottleneck and *which companies* sit in it. They do not answer the deeper question: **why is this company's capability hard to replicate, and what controls the physics underneath it?**

The conversation about Hamamatsu Photonics illustrates this gap precisely. A conventional supply chain analysis places Hamamatsu in a "photodetector" node with a high HHI score. That is correct but shallow. The real investment insight requires understanding that Hamamatsu's moat does not come from "making photodetectors" — it comes from operating at the intersection of four fundamental physics constraints that each have their own upstream oligopoly stack:

1. Quantum efficiency limit (photon → electron conversion probability)
2. Noise floor limit (false signal suppression at single-photon scale)
3. Gain stability limit (amplification reproducibility over time and temperature)
4. Spatial/temporal resolution limit (event localisation at atomic scale)

Each constraint maps to a cluster of upstream companies (materials, process tools, vacuum systems, metrology) whose capabilities collectively determine whether the downstream company's product is replicable. This recursive structure — company → physics constraints → upstream oligopoly stacks → deeper physics constraints — is what the Capability Drill-Down feature is designed to surface.

### 13.2 Architectural difference from Path A/B

The drill-down feature is architecturally distinct from the background pipeline:

| Dimension | Path A/B pipeline | Capability drill-down |
|---|---|---|
| Computation | Pre-computed, batch, weekly | Live, on-demand, per-request |
| Data source | SEC filings, yfinance, Comtrade | LLM reasoning + web search |
| Graph structure | Wide (many companies, few layers) | Deep (few companies, many constraint layers) |
| Pre-computable? | Yes | No — reasoning is open-ended |
| Output | Stored in Supabase, served from DB | Streamed to client in real time |
| User trigger | Theme selection | Click on any company in the scorecard |
| Depth | Fixed (supply chain layers) | Recursive, user-controlled |

Because the decomposition requires synthesising physics knowledge, materials science, financial context, and competitive dynamics simultaneously, this feature uses the Anthropic API (Claude) as the reasoning engine. It is not a retrieval or database feature.

### 13.3 Decomposition model

The drill-down operates on a **Capability Node** structure. Every node in the decomposition tree has the following attributes:

```
CapabilityNode {
  id:               string           // stable slug, e.g. 'electron_multiplication'
  label:            string           // display name
  parent_id:        string | null    // null for root (the company)
  depth:            int              // 0 = company, 1 = primary capability, 2 = sub-capability...
  description:      string           // what this capability does physically
  why_hard:         string           // the physical/manufacturing constraint that makes it hard
  replicability_score: float         // 0–10; 10 = nearly impossible to replicate
  replicability_rationale: string    // concise explanation of the score
  controlling_companies: [           // oligopoly stack that controls this constraint
    {
      ticker:       string | null    // null if private or non-public
      name:         string
      role:         string           // what they specifically control
      public:       boolean
    }
  ]
  can_go_deeper:    boolean          // whether further decomposition is meaningful
  children:         CapabilityNode[] // populated when user drills down
}
```

The root node is always the company being analysed. Depth 1 nodes are the primary capability domains (e.g. for Hamamatsu: photocathode physics, electron multiplication, analog amplification, signal extraction, calibration). Depth 2+ nodes are the physical constraints within each domain.

### 13.4 Use cases specific to drill-down

**UC-08 — Drill down into a bottleneck company**
Actor: Investor. Trigger: User clicks "Drill Down" on a scorecard row.
Flow: The system calls the Anthropic API with the company name, its industry context, and a structured prompt requesting a depth-1 capability decomposition. The response streams back as a tree of CapabilityNodes. The UI renders each node as an expandable card with its replicability score and controlling companies.
Outcome: User sees the primary capability domains that constitute the company's moat, each scored by how hard they are to replicate.

**UC-09 — Go one level deeper on a capability node**
Actor: Investor. Trigger: User clicks "Go Deeper" on any CapabilityNode card.
Flow: The system calls the Anthropic API with the selected node's label, description, and its parent context, requesting the next level of decomposition. New child nodes stream in and attach to the tree.
Outcome: User understands the physics/manufacturing constraint beneath a given capability.

**UC-10 — Find the investable companies controlling a constraint**
Actor: Investor. Trigger: User clicks "Show companies" on any CapabilityNode.
Flow: If the node already has controlling_companies populated, they are shown immediately. If not, the system calls the API to generate the oligopoly stack for that constraint. For each public ticker found, the system calls the existing StockerPro fundamentals endpoint to enrich the display with gross margin, ROIC, and market cap.
Outcome: User sees which public companies to investigate as upstream investments — e.g. clicking "electron multiplication structures" surfaces Schott AG (private), Hamamatsu itself, and specific vacuum microstructure suppliers.

**UC-11 — Save decomposition as a research note**
Actor: Investor. Trigger: User clicks "Save to research" on any node or the full tree.
Flow: The current decomposition tree (as JSON) is saved to a new `sc_research_notes` table linked to the ticker. A summary of the tree is stored as markdown text. The note appears in the existing StockerPro stock detail page under a new "Supply Chain Research" tab.
Outcome: User retains the decomposition for future reference and can compare against later runs.

**UC-12 — Identify the root constraint graph node**
Actor: Investor. Trigger: User keeps drilling down until `can_go_deeper = false` on all nodes.
Flow: The system detects when all leaf nodes have `can_go_deeper = false` and displays a "Root constraint identified" summary. This is the fundamental physical or manufacturing limit — e.g. "industrial control over atomic-scale defect formation in semiconductor interfaces" — that underlies the entire decomposition.
Outcome: User understands the deepest non-replicable capability in the stack, and which companies collectively control it.

### 13.5 LLM prompt architecture

The drill-down calls the Anthropic API with structured prompts. Prompt design is critical because the output must be machine-parseable JSON, physically accurate, and investment-relevant simultaneously.

**System prompt (constant across all calls):**

```
You are a technical investment analyst specialising in deep supply chain and
capability analysis at the physics and materials science level.

Your task is to decompose a company's capabilities into their fundamental
physical constraints — not business categories or product lines.

Rules:
1. Decompose by physics constraints, not by product/module/subsystem labels.
2. For each constraint, identify what physical law or manufacturing reality
   makes it hard to replicate — not just that it requires expertise.
3. Replicability score (0–10): 10 = bounded by physics; 9 = requires decades
   of process knowledge; 7 = hard but capital-solvable; 5 = replicable in 5
   years with investment; below 5 = commodity.
4. Controlling companies: list the real oligopoly stack, including private
   companies. Mark them public: true/false. Include ticker if public.
5. can_go_deeper: true if there are further physical constraints worth
   decomposing; false if the node is already at a fundamental physics limit.
6. Respond ONLY with valid JSON matching the CapabilityNode schema. No
   preamble, no markdown, no explanation outside the JSON structure.
```

**Depth-1 decomposition prompt (user trigger: company selected):**

```
Company: {company_name} ({ticker})
Industry context: {node_label} layer in the {theme_display_name} supply chain.
Known role: {one_sentence_from_scorecard_thesis}

Decompose this company's capability into its primary physical/manufacturing
constraint domains (3–6 domains). For each domain, provide:
- what it does physically
- why it is hard to replicate at physics or manufacturing level
- replicability_score
- the upstream oligopoly stack that controls this constraint
- whether further decomposition would reveal deeper non-obvious choke points

Return a JSON array of CapabilityNode objects at depth=1.
```

**Depth-N decomposition prompt (user trigger: "Go Deeper" on a node):**

```
Parent capability: {parent_node.label}
Parent description: {parent_node.description}
Parent why_hard: {parent_node.why_hard}
Company context: {root_company_name} in {theme_display_name}

Decompose this capability into its constituent physical sub-constraints.
Go one level deeper than "{parent_node.label}" — do not repeat the parent
framing. Find the specific material physics, fabrication physics, or
measurement physics that makes this capability hard to replicate.

Return a JSON array of CapabilityNode objects at depth={parent_depth + 1}.
```

### 13.6 Backend implementation

**New FastAPI endpoint:**

```python
# POST /supply-chain/drill-down
# Body: { ticker, company_name, node_id, theme_slug, depth, parent_node (optional) }
# Returns: Server-Sent Events stream of CapabilityNode JSON objects

@router.post("/drill-down")
async def drill_down(request: DrillDownRequest):
    """
    Calls Anthropic API and streams CapabilityNode JSON objects back to client.
    Does not write to database during streaming.
    On stream completion, persists the nodes to sc_capability_nodes if
    the user is authenticated and has 'save_research' flag set.
    """
    prompt = build_prompt(request)
    return StreamingResponse(
        stream_anthropic_response(prompt),
        media_type="text/event-stream"
    )

async def stream_anthropic_response(prompt: str):
    async with anthropic_client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=DRILL_DOWN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        async for text in stream.text_stream:
            yield f"data: {text}\n\n"
```

**New database table: sc_capability_nodes**

```sql
CREATE TABLE sc_capability_nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    theme_id        INTEGER REFERENCES sc_themes(id),
    node_id         TEXT NOT NULL,
    label           TEXT NOT NULL,
    parent_node_id  TEXT,
    depth           INTEGER NOT NULL,
    description     TEXT,
    why_hard        TEXT,
    replicability_score  NUMERIC(3,1),
    replicability_rationale TEXT,
    controlling_companies   JSONB,   -- [{ticker, name, role, public}]
    can_go_deeper   BOOLEAN,
    created_by_run  BOOLEAN DEFAULT FALSE,  -- FALSE = user-triggered, TRUE = pipeline
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON sc_capability_nodes (ticker, depth);
CREATE INDEX ON sc_capability_nodes (ticker, parent_node_id);
```

**New database table: sc_research_notes**

```sql
CREATE TABLE sc_research_notes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker      TEXT NOT NULL,
    theme_id    INTEGER REFERENCES sc_themes(id),
    tree_json   JSONB NOT NULL,   -- full CapabilityNode tree as of save time
    summary_md  TEXT,             -- LLM-generated markdown summary of the tree
    depth_reached INTEGER,        -- deepest level the user drilled to
    root_constraint TEXT,         -- final root constraint label if reached
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON sc_research_notes (ticker);
```

### 13.7 Frontend implementation

**New components:**

```
app/supply-chain/[theme]/
  _components/
    DrillDownPanel.tsx          # Slide-over panel triggered from ScorecardTab
    CapabilityTree.tsx          # Recursive tree renderer
    CapabilityNodeCard.tsx      # Single node: label, score, why_hard, companies
    ReplicabilityScoreBadge.tsx # Colour-coded 0–10 score chip
    ControllingCompanies.tsx    # Oligopoly stack list with optional watchlist CTA
    RootConstraintSummary.tsx   # Shown when all nodes have can_go_deeper=false
  _hooks/
    useDrillDown.ts             # SSE streaming hook, builds tree incrementally
    useSaveResearch.ts          # POST /supply-chain/research-notes
```

**`useDrillDown.ts` — SSE streaming hook:**

```typescript
export function useDrillDown(request: DrillDownRequest | null) {
  const [nodes, setNodes] = useState<CapabilityNode[]>([]);
  const [streaming, setStreaming] = useState(false);

  const trigger = useCallback(async (req: DrillDownRequest) => {
    setStreaming(true);
    const es = new EventSource('/api/supply-chain/drill-down?' +
      new URLSearchParams(req as any));

    let buffer = '';
    es.onmessage = (e) => {
      buffer += e.data;
      try {
        // Attempt to parse complete JSON array as it streams in
        const parsed: CapabilityNode[] = JSON.parse(buffer);
        setNodes(prev => mergeNodes(prev, parsed, req.parent_node_id));
        buffer = '';
      } catch {
        // Incomplete JSON — keep buffering
      }
    };
    es.onerror = () => { setStreaming(false); es.close(); };
    es.addEventListener('done', () => { setStreaming(false); es.close(); });
  }, []);

  return { nodes, streaming, trigger };
}
```

**`CapabilityNodeCard.tsx` — key UI decisions:**

Each card shows: capability label, replicability score (colour-coded badge: red ≥ 8, amber 5–7.9, green < 5), a two-sentence "why hard" explanation, and the controlling companies list. If `can_go_deeper = true`, a "Go Deeper →" button is shown. If the node already has children in the tree (the user already drilled this path), the button shows "Collapse" instead. The controlling companies list shows ticker badges — clicking any public ticker opens the existing StockerPro stock detail page.

**`CapabilityTree.tsx` — rendering:**

The tree renders as a vertically expanding accordion, not a 2D graph. Each depth level is indented 24px. This avoids the graph layout problem (no need for a force-directed layout library) and keeps the UI scannable on a single scroll. The Hamamatsu example would render as:

```
Hamamatsu Photonics [root]
  ├── Photocathode physics [9.0] — can go deeper
  │     ├── Crystal lattice purity [8.5]
  │     ├── Epitaxial growth precision [9.0]
  │     └── Surface trap state control [8.5]
  ├── Electron multiplication [9.0] — can go deeper
  ├── Low-noise analog amplification [8.0]
  ├── High-speed signal extraction [7.0]
  └── Calibration + stability control [8.0]
```

### 13.8 Integration with existing scorecard

The drill-down panel is triggered from the ScorecardTab. The only change to `ScorecardTab.tsx` is adding a "Drill Down" icon button to each row, and rendering `<DrillDownPanel>` as a slide-over when a row is selected. No other existing components change.

The "Add to watchlist" button on a CapabilityNodeCard's controlling companies list calls the same `POST /watchlist` endpoint already in production, with an additional context field: `{source: 'capability-drill-down', parent_ticker: 'HPHTF', constraint: 'electron_multiplication'}`. This gives the user a traceable reason for every watchlist addition.

### 13.9 What this feature does NOT do

**It does not replace financial analysis.** The replicability scores are qualitative reasoning from the LLM, not computed from financial data. They should be treated as a research starting point, not a buy signal.

**It does not validate its own physics.** The LLM can produce physically plausible but incorrect decompositions. For highly specialised domains (vacuum microstructure physics, compound semiconductor epitaxy), the output should be reviewed against primary sources before investment decisions are made.

**It does not pre-compute paths.** The decomposition is generated fresh on each user session. There is no guarantee that two drill-down sessions on the same company at the same depth produce identical node structures. This is inherent to LLM generation. Saving research notes (UC-11) is the mechanism for preserving a specific decomposition.

### 13.10 Updated implementation plan

The drill-down feature adds a Phase 6 to the existing 5-phase plan. It is independent of Phases 1–5 and can be developed in parallel after Phase 4 (the read endpoints) is complete, since it shares no database tables with the pipeline.

| Step | Deliverable | Est. hours | Acceptance criterion |
|---|---|---|---|
| 12 | `sc_capability_nodes` + `sc_research_notes` migration | 1h | Tables exist with correct indexes |
| 13 | `POST /supply-chain/drill-down` SSE endpoint | 4h | Streams valid CapabilityNode JSON for Hamamatsu test case |
| 14 | `useDrillDown.ts` streaming hook | 3h | Tree builds incrementally as SSE events arrive; no full-page re-render |
| 15 | `CapabilityNodeCard` + `CapabilityTree` components | 5h | Accordion renders correct depth indentation; "Go Deeper" triggers next API call |
| 16 | `DrillDownPanel` + ScorecardTab integration | 2h | Slide-over opens from scorecard row; closes without losing scorecard state |
| 17 | Save to research notes | 2h | `POST /supply-chain/research-notes` persists tree JSON; note appears on stock detail page |

**Phase 6 total: 17 hours**  
**Revised project total: 59 hours**

---

*End of design document v1.1 — Section 13 added: Capability Drill-Down Feature.*