# AI Integration Design

> **Feature:** OpenRouter-based AI stock analysis summaries and cross-method valuation recommendations, enriched with full company financial context.
>
> **Status:** Implemented — 2026-05-24 | Caching v2 planned
>
> **Endpoints:**
> - `GET /valuations/{symbol}/overview` — cross-method AI recommendation
> - `POST /valuations/{symbol}/rule1` — suitability summary
> - `POST /valuations/{symbol}/ddm` — suitability summary
> - `POST /valuations/{symbol}/dcf` — suitability summary
> - `POST /valuations/{symbol}/owner_earnings` — suitability summary
> - `POST /valuations/{symbol}/residual_income` — suitability summary
> - `GET /analysis/{symbol}/magic-formula` — suitability summary
>
> **Design:** Provider-abstracted architecture with `AIProvider` ABC, `OpenRouterProvider`, extracted prompt builders, and `CompanySnapshotBuilder` for financial context enrichment. Zero behavioural change to callers.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Backend Components](#2-backend-components)
3. [Prompt Layer](#3-prompt-layer)
4. [Configuration](#4-configuration)
5. [Error Handling](#5-error-handling)
6. [Performance & Caching](#6-performance--caching)
7. [Class Diagrams](#7-class-diagrams)

---

## 1. Architecture Overview

```
Callers (unchanged)
  Rule1Service  DcfService  DdmService  OwnerEarningsService
  ResidualIncomeService  MagicFormulaService  ValuationService
        │
        │ generate_suitability_summary() / generate_overview_summary()
        ▼
┌─────────────────────────────────────────────────────────────────┐
│           CacheManager (TTLCache + request-scoped)             │
│  ├─ AI response cache: (symbol, method, hash) → text | dict   │
│  ├─ Query cache: (table, filters) → rows                      │
│  └─ Context cache: (symbol) → formatted context string        │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
ai_service.py (orchestration layer)
  configure_ai(provider, snapshot_builder, cache_manager)  ← DI wiring
  _get_or_create_provider() → lazy OpenRouterProvider singleton
  _build_company_context(symbol) → COMPANY CONTEXT block or ""

  generate_suitability_summary(...)
    ├─ check AI response cache → instant return if hit
    ├─ build_suitability_prompt() → method-specific TASK block
    ├─ (no company context for individual methods)
    ├─ OpenRouterProvider.generate_text(TASK, system_inst)
    ├─ store result in AI response cache
    └─ returns str | None

  generate_overview_summary(...)
    ├─ check AI response cache → instant return if hit
    ├─ build_overview_prompt() → cross-method TASK block
    ├─ _build_company_context(symbol) → COMPANY CONTEXT block
    ├─ OpenRouterProvider.generate_text(CONTEXT + TASK, system_inst)
    ├─ parses JSON, validates keys, normalises bestMethod
    ├─ store result in AI response cache
    └─ returns dict | None
        │
        ├──────────────────────────┬──────────────────────────┬──────────────────────┐
        ▼                          ▼                          ▼                      ▼
CompanySnapshotBuilder    Prompt Builders             AIProvider            CacheManager
(prompts/company_         (prompts/suitability.py,   (providers/ai_        (caching/
 snapshot.py)              overview.py)               provider.py)           cache_manager.py)
                        │                           OpenRouterProvider
repo injected via DI   │  Pure functions —           │
configure_ai()         │  no API concerns            POST /chat/completions
                        │                           httpx.AsyncClient
Queries in parallel    │                                     │
(via CacheManager):    │                                     ▼
├─ get_company_context(symbol)                      Open Router API
├─ get_income_statements_annual(limit=99)           model: openai/gpt-oss-120b:free
├─ get_income_statement_latest()
├─ get_balance_sheet_latest()
├─ get_cash_flow_latest()
├─ get_company_summary_latest()
├─ get_shares_history()
├─ get_current_market_price()
└─ get_last_output_snapshots() × 1 batch query
     (5 methods in a single .in_() call)
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `AIProvider` ABC | Future provider swaps (OpenAI, Anthropic, local LLM) without changing callers or prompts |
| Prompts extracted to `prompts/` module | Keeps `ai_service.py` at ~130 lines; prompts are pure data with no API concerns |
| `CompanySnapshotBuilder` | Centralises all company data queries, single source of truth for AI context |
| Two-part prompt: CONTEXT + TASK | Clear separation: model knows what is background vs what is the specific analysis task |
| All available years, no limit | Financial data quality improves with depth |
| Preserved function signatures | All 7 callers unchanged |
| Low temperature (0.1) | Deterministic, factual output for financial analysis |
| `configure_ai()` DI setter | Wired in `dependencies.py` via `get_valuation_repository()` |
| **No company context for individual methods** | Individual suitability promps are self-sufficient from `evidence`/`valuation_inputs`/`input_decisions`; company context (13 queries) is only built for overview |
| **AI response cache** | Same inputs always produce same outputs when financial data is static; TTL cache makes tab switches instant (3-6s → 0ms) |
| **Request-scoped query cache** | Eliminates ~50% duplication — route handler and snapshot builder fetch the same rows independently |
| **Single batch query for snapshots** | 5 `.eq()` round-trips → 1 `.in_()` call; reduces overview latency by ~4 network trips |

---

## 2. Backend Components

### 2.1 `providers/ai_provider.py`

#### AIProvider (ABC)

```python
class AIProvider(ABC):

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 800,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> Optional[str]:
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        ...
```

- `generate_text` — for free-text suitability summaries
- `generate_json` — calls `generate_text` then `json.loads()` with markdown fence stripping

#### OpenRouterProvider

| Property | Value |
|----------|-------|
| Base URL | `https://openrouter.ai/api/v1/chat/completions` |
| Auth | `Authorization: Bearer {OPEN_ROUTER_KEY}` |
| Model | `settings.OPEN_ROUTER_MODEL` (default: `openai/gpt-oss-120b:free`) |

**Request body:**
```json
{
  "model": "openai/gpt-oss-120b:free",
  "messages": [
    {"role": "system", "content": "You are a financial analysis assistant..."},
    {"role": "user", "content": "=== COMPANY CONTEXT ===\n\n...\n\n=== TASK ===\n\n..."}
  ],
  "max_tokens": 800,
  "temperature": 0.1
}
```

**Response extraction:**
```python
data = resp.json()
choice = data.get("choices", [{}])[0]
text = choice.get("message", {}).get("content", "").strip()
usage = data.get("usage", {})
```

### 2.2 `caching/cache_manager.py`

Central cache layer queried by both the route handler and `ai_service.py`. Deduplicates Supabase round-trips and stores AI responses for instant tab-switch performance.

```python
class CacheManager:
    """Three-layer cache: request-scoped dict + process TTL cache + AI response TTL cache."""

    _request_cache: ContextVar[Dict[str, Any]]  # per-request scope, cleared after each HTTP call
    _query_cache: TTLCache  # process-level, TTL=30s, caches Supabase query results
    _ai_cache: TTLCache    # process-level, TTL=300s, caches AI response text/dict
    _context_cache: TTLCache  # process-level, TTL=60s, caches formatted company context string

    def cache_key(self, *parts: str) -> str:
        """Joins parts with ':' — e.g. 'query:get_company_context:RBLX'"""

    def get_query_result(self, key: str) -> Optional[Any]:
        """Check request cache, then TTL cache."""

    def set_query_result(self, key: str, value: Any, ttl: int = 30) -> None:
        """Store in request + TTL caches."""

    def get_ai_response(self, symbol: str, method: str, context_hash: str) -> Optional[Any]:
        """Check AI response cache; hash captures financial data version."""

    def set_ai_response(self, symbol: str, method: str, context_hash: str,
                        value: Any, ttl: int = 300) -> None:
        """Store AI response."""

    async def clear_request_cache(self) -> None:
        """Reset request-scoped ContextVar — call at end of each HTTP request via middleware."""
```

**Key detail — context hash:** The AI response is cached under `SHA256(symbol + method + all_financial_data + all_output_snapshots)`. If any valuation run changes, the hash diverges and the cache automatically misses. No manual invalidation needed for the most critical case (user recomputes a valuation).

### 2.3 `application/services/prompts/company_snapshot.py`

`CompanySnapshotBuilder` — queries all financial data sources in parallel (via `CacheManager`):

```python
class CompanySnapshotBuilder:
    def __init__(self, repo: ValuationRepository) -> None: ...

    async def build(self, symbol: str) -> Dict[str, Any]:
        """Returns snapshot dict with all data sections."""

    @staticmethod
    def format_context(snapshot: Dict[str, Any]) -> str:
        """Converts snapshot dict to COMPANY CONTEXT text block."""
```

**Output format:**
```
=== COMPANY CONTEXT ===
Company: AAPL
Sector: Technology | Industry: Consumer Electronics
Currency: USD
Current Market Price: 175.50
Shares Outstanding: 15000000000
Trailing EPS: 6.5
Latest Income (FY2025) | Revenue=391000000000 | Net Income=97000000000 | EPS(diluted)=6.5
Latest Balance Sheet (FY2025) | Assets=352000000000 | Debt=105000000000 | Equity=62000000000 | Cash=55000000000
Latest Cash Flow (FY2025) | Ops Cash Flow=110000000000 | Capex=11000000000
FY2025 | Rev=391000000000 | NetInc=97000000000
FY2024 | Rev=383000000000 | NetInc=94000000000
Cached DCF intrinsic: 412.0
```

### 2.4 `application/services/ai_service.py`

Thin orchestration layer (~160 lines with caching). Wired via `configure_ai()` in `dependencies.py`:

```python
_provider: Optional[AIProvider] = None
_snapshot_builder: Optional[CompanySnapshotBuilder] = None
_cache_manager: Optional[CacheManager] = None

def configure_ai(provider=None, snapshot_builder=None, cache_manager=None):
    """DI setter — called from dependencies.py."""

async def generate_suitability_summary(symbol, method, score, category,
    flags, evidence=None, valuation_inputs=None,
    input_decisions=None, timeout=8.0) -> Optional[str]:
    # 1. check cache → instant return if hit (same financial data)
    # 2. builds TASK prompt only (no company context for individual methods)
    # 3. calls provider.generate_text() with TASK only
    # 4. store result in AI response cache
    # 5. return text

async def generate_overview_summary(symbol, sector, currency,
    current_price, methods, timeout=10.0) -> Optional[Dict[str, Any]]:
    # 1. check cache → instant return if hit (same financial data)
    # 2. builds TASK → builds CONTEXT (via CacheManager for dedup)
    # 3. calls provider.generate_text() → JSON parse
    # 4. store result in AI response cache
    # 5. return dict
```

### 2.5 System Instructions

Two separate instructions:

```python
_SUITABILITY_SYSTEM_INSTRUCTION = (
    "You are a financial analysis assistant writing plain-English summaries "
    "for retail investors. You always complete every sentence fully. "
    "You never use bullet points, headers, or labels. "
    "You only reference metric values that are explicitly provided — never invent numbers."
)

_OVERVIEW_SYSTEM_INSTRUCTION = (
    "You are a financial analysis assistant writing cross-method valuation recommendations "
    "for retail investors. You always respond with valid JSON only — no markdown, no preamble. "
    "You only reference metric values that are explicitly provided — never invent numbers. "
    "You complete every sentence in the reasoning field."
)
```

### 2.6 DI Wiring (`dependencies.py`)

```python
def get_ai_provider() -> AIProvider:
    """Creates OpenRouterProvider singleton."""

def get_valuation_repository() -> ValuationRepository:
    """Creates ValuationRepository singleton + wires configure_ai() once."""
```

### 2.7 Callers (UNCHANGED)

| Caller | Function | File |
|--------|----------|------|
| `Rule1Service` | `generate_suitability_summary` | `rule1_service.py` |
| `DcfService` | `generate_suitability_summary` | `dcf_service.py` |
| `DdmService` | `generate_suitability_summary` | `ddm_service.py` |
| `OwnerEarningsService` | `generate_suitability_summary` | `owner_earnings_service.py` |
| `ResidualIncomeService` | `generate_suitability_summary` | `residual_income_service.py` |
| `MagicFormulaService` | `generate_suitability_summary` | `magic_formula_service.py` |
| `ValuationService` | `generate_overview_summary` | `valuation_service.py` |

### 2.8 API Layer (UNCHANGED)

All 7 routes in `api/valuations.py` and `api/analysis.py` — no changes.

### 2.9 Repository Methods Used

| Method | Table | Cache Scope |
|--------|-------|-------------|
| `get_company_context(symbol)` | `companies` | request + 30s TTL |
| `get_income_statements_annual(company_id, limit=99)` | `income_statements` | request + 30s TTL |
| `get_income_statement_latest(company_id)` | `income_statements` | request + 30s TTL |
| `get_balance_sheet_latest(company_id)` | `balance_sheets` | request + 30s TTL |
| `get_cash_flow_latest(company_id)` | `cash_flow_statements` | request + 30s TTL |
| `get_company_summary_latest(company_id)` | `company_summary` | request + 30s TTL |
| `get_shares_history(company_id)` | `income_statements` | request + 30s TTL |
| `get_current_market_price(company_id)` | `current_market_data` | request + 30s TTL |
| `get_last_output_snapshots(company_id, methods_list)` | `valuation_runs` | request + 30s TTL |
| _(replaces 5 individual `get_last_output_snapshot` calls)_ | | |

New batch method signature:

```python
async def get_last_output_snapshots(
    self, company_id: int, methods: List[str]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Single query: SELECT FROM valuation_runs WHERE company_id=? AND method IN (...) ORDER BY run_at DESC.
       Returns dict keyed by method, with one row per method (the latest)."""
```

---

## 3. Prompt Layer

### 3.1 File Structure

```
application/services/prompts/
├── __init__.py
├── company_snapshot.py    # CompanySnapshotBuilder
├── suitability.py         # All method-specific prompt builders
└── overview.py            # Cross-method overview prompt builder
```

### 3.2 Prompt Structure

Overview AI calls produce a two-part prompt; individual method calls produce only the TASK (no company context):

```
=== COMPANY CONTEXT ===
[Financial snapshot — income statements, balance sheet, cash flow,
 market data, cached valuations from all methods]
*(overview only — skipped for individual suitability calls)*

=== TASK ===
[Method-specific analysis prompt with scorecard, metrics, flags,
 input decisions, and output instructions]
```

### 3.3 `suitability.py` — Contents

| Export | Description |
|--------|-------------|
| `build_suitability_prompt(...)` | Routes to method-specific builder |
| `_fmt(val, as_pct, decimals)` | Formats value or percentage |
| `_critical_flags(flags)` | Filters to critical/high severity |
| `_input_source_summary(...)` | Human-readable data-source trace |
| `_prompt_rule1(...)` | Rule #1 (Branches A/B/C) |
| `_prompt_ddm(...)` | DDM Gordon/Two-Stage (Branches A/B) |
| `_prompt_dcf(...)` | DCF (Branches A/B) |
| `_prompt_owner_earnings(...)` | Owner Earnings (Branches A/B) |
| `_prompt_residual_income(...)` | Residual Income (Branches A/B) |
| `_prompt_magic_formula(...)` | Magic Formula (Branches A/B/C) |
| `_prompt_canslim(...)` | CANSlim |
| `_prompt_generic(...)` | Unknown-method fallback |

Each method has multiple branches (broken formula / sparse data / valid formula) with context-appropriate prompts. Only available (non-None) metrics are shown to avoid hallucination.

### 3.4 `overview.py` — Contents

| Export | Description |
|--------|-------------|
| `build_overview_prompt(...)` | Builds cross-method overview with convergence analysis |
| `OVERVIEW_FALLBACK` | Default dict when JSON parsing fails |

Prompt includes per-method results, convergence analysis (spread %), method selection guidance, and strict JSON output requirements.

### 3.5 Prompt Quality

| Aspect | Detail |
|--------|--------|
| System instruction | Clear role + output format for each task type |
| Branching logic | Broken formula / sparse data / valid — appropriate for each method |
| Company context | Full financial picture with all available years |
| Metric filtering | Only non-None values shown — prevents N/A starvation |
| Few-shot examples | Per-branch examples with placeholder tickers |
| Sentence instructions | Precise output control ("Sentence 1: Verdict...") |
| Temperature | 0.1 — deterministic, factual |
| Max tokens | 800 (suitability) / 1000 (overview) |

---

## 4. Configuration

### 4.1 `config.py`

```python
OPEN_ROUTER_KEY: Optional[str] = Field(default=None)
OPEN_ROUTER_MODEL: str = Field(default="openai/gpt-oss-120b:free")
```

### 4.2 `.env`

```
OPEN_ROUTER_KEY='sk-or-v1-...'
OPEN_ROUTER_MODEL='openai/gpt-oss-120b:free'
```

### 4.3 Startup Scripts

`start.sh` and `start-prod.sh` check `OPEN_ROUTER_KEY` in the startup banner.

### 4.4 Dependencies

No AI-specific dependencies. Uses `httpx` (already in the dependency tree) for REST calls.

---

## 5. Error Handling

| Scenario | Behaviour |
|----------|-----------|
| API key not set | Both functions return `None` immediately. Log: `"OPEN_ROUTER_KEY not set — AI disabled"` |
| Company snapshot build fails | Log warning, fall back to TASK-only prompt (no company context) |
| HTTP error (4xx/5xx) | Log status + response body, return `None` |
| Network timeout | Log warning, return `None` |
| Empty response | Log finish reason + raw data, return `None` |
| JSON parse failure (overview) | Log parse error + raw text, return `None` |
| Missing JSON keys (overview) | Fill missing keys from `OVERVIEW_FALLBACK`, return partial dict |
| Unknown `bestMethod` (overview) | Fall back to highest-scored computed method |

All errors are caught at the AI layer — callers always receive `None` (never an exception).

---

## 6. Performance & Caching

### 6.1 Problem

Before caching, every AI call triggers:

| Request type | Supabase queries | AI API call | Typical P95 latency |
|---|---|---|---|
| Individual method (rule1/dcf/...) | 16 (3 route + 13 context) | 1 | 5-12s |
| Overview | 20 (7 route + 13 context) | 1 | 7-15s |
| _Tab switch (SAME data)_ | 16-20 _again_ | _1 again_ | _5-12s again_ |

The financial data and valuation output snapshots are **completely static** between recomputes. Every tab switch re-fetches identical data and re-calls OpenRouter for the same inputs — pure waste.

### 6.2 Three-Layer Cache Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CacheManager                                     │
│                                                                     │
│  ┌─────────────────────┐   ┌─────────────────┐   ┌───────────────┐  │
│  │ Layer A: AI Response│   │Layer B: Query   │   │Layer C:       │  │
│  │ Cache (TTLCache)    │   │Cache (request+  │   │Context String │  │
│  │                     │   │      TTL)       │   │Cache (TTLCache)│  │
│  │ Key: {symbol,       │   │                 │   │               │  │
│  │  method,            │   │ Key: {table,    │   │ Key: {symbol} │  │
│  │  context_hash}      │   │  filters}       │   │ Value: fmt str│  │
│  │ Value: AI text/dict │   │ Value: rows     │   │ TTL: 60s      │  │
│  │ TTL: 300s           │   │ TTL: 30s        │   │               │  │
│  └─────────────────────┘   └─────────────────┘   └───────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

#### Layer A: AI Response Cache (highest impact)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Avoid re-calling OpenRouter when financial data hasn't changed |
| **Key** | `SHA256(symbol + method + all_financial_data + all_output_snapshots)` |
| **Value** | Raw AI response string (suitability) or parsed dict (overview) |
| **TTL** | 300s — covers tab sessions; longer would also be safe since valuations are static |
| **Storage** | `cachetools.TTLCache` maxsize=256 |
| **Hit behaviour** | Returns cached response immediately — **0 DB queries, 0 AI calls** |
| **Miss behaviour** | Normal flow: DB → build prompt → AI call → store → return |

**Why hashing works for invalidation:** The `context_hash` incorporates all financial inputs (income statements, balance sheets, cash flow, current price, all output snapshots). If any valuation is recomputed (`POST /valuations/{symbol}/rule1`), the `output_snapshot` for that method changes, the hash diverges, and the next AI call automatically misses. No explicit cache invalidation logic needed.

#### Layer B: Request + TTL Query Cache

| Aspect | Detail |
|--------|--------|
| **Purpose** | Deduplicate repeated Supabase queries within a request and across close requests |
| **Key** | `query:{method_name}:{args_hash}` |
| **Value** | Supabase response rows |
| **TTL** | 30s (process-level) + request scope (cleared after response) |
| **Storage** | `ContextVar[dict]` + `cachetools.TTLCache` maxsize=512 |

**How duplication is eliminated:**

Before:
```
Route handler:   get_company_context("RBLX")    → Supabase round-trip #1
Snapshot builder: get_company_context("RBLX")    → Supabase round-trip #2 (same data!)
Route handler:   get_current_market_price(31)    → Supabase round-trip #3
Snapshot builder: get_current_market_price(31)   → Supabase round-trip #4 (same data!)
```

After (request cache):
```
Route handler:   get_company_context("RBLX")    → Supabase → cache: {query:...:RBLX:...}
Snapshot builder: get_company_context("RBLX")    → CACHE HIT → 0ms
Route handler:   get_current_market_price(31)    → Supabase → cache
Snapshot builder: get_current_market_price(31)   → CACHE HIT → 0ms
```

The `ContextVar` request cache is automatically cleared at the end of each HTTP request via FastAPI middleware:

```python
@app.middleware("http")
async def clear_request_cache(request: Request, call_next):
    response = await call_next(request)
    cache_manager.clear_request_cache()
    return response
```

#### Layer C: Context String Cache

| Aspect | Detail |
|--------|--------|
| **Purpose** | Avoid rebuilding the formatted COMPANY CONTEXT text block for every AI call within a short window |
| **Key** | `context:{symbol}` |
| **Value** | `=== COMPANY CONTEXT ===\n...` (formatted string) |
| **TTL** | 60s |
| **Storage** | `cachetools.TTLCache` maxsize=64 |

If a user visits multiple tabs within 60 seconds, the expensive context build (13 queries + string formatting) happens only once.

### 6.3 Individual Method Optimization

`generate_suitability_summary()` no longer builds company context. The individual method prompts are self-sufficient:

| Input | Source | Why no context needed |
|-------|--------|----------------------|
| `score`, `category` | Already passed as args | Sufficient for verdict |
| `flags` | Already passed as args | Sufficient for risk analysis |
| `evidence` dict | Contains all method-specific financial data | Per-method EPS, FCF, growth rates, etc. |
| `valuation_inputs` dict | Contains inputs used by the method | Beta, discount rate, growth assumptions |
| `input_decisions` dict | Contains user/auto decisions per input | Sufficient for transparency |

The company financial context adds zero value for individual method analysis — the model already has everything it needs in the method-specific data.

### 6.4 Batch Query for Output Snapshots

**Before:** 5 individual `get_last_output_snapshot(company_id, method)` calls:
```python
snapshots = await asyncio.gather(
    repo.get_last_output_snapshot(company_id, "rule1"),
    repo.get_last_output_snapshot(company_id, "dcf"),
    repo.get_last_output_snapshot(company_id, "ddm_gordon"),
    repo.get_last_output_snapshot(company_id, "owner_earnings"),
    repo.get_last_output_snapshot(company_id, "residual_income"),
)
```

**After:** 1 batch call with an `IN` filter:
```python
snapshots = await repo.get_last_output_snapshots(
    company_id, ["rule1", "dcf", "ddm_gordon", "owner_earnings", "residual_income"]
)
```

SQL generated:
```sql
SELECT DISTINCT ON (method) method, output_snapshot, run_at
FROM valuation_runs
WHERE company_id = 31 AND method IN ('rule1','dcf','ddm_gordon','owner_earnings','residual_income')
ORDER BY method, run_at DESC
```

### 6.5 Expected Performance Gains

| Scenario | Before | After (all 3 layers) |
|----------|--------|---------------------|
| First visit (cold) | 5-12s | 5-12s _(no change — cache miss is same as today)_ |
| Tab switch (30s later) | 5-12s | **~50ms** (Layer A hits → instant AI response) |
| Same tab, same data | 5-12s | **~50ms** (Layer A hits) |
| Recompute then revisit | 5-12s | 5-12s _(hash changes → cache miss → fresh AI call)_ |
| Overview (first) | 7-15s | 5-10s _(Layer B dedup + batch query saves ~4 round-trips)_ |
| Overview (tab switch) | 7-15s | **~50ms** (Layer A hits) |
| 5 tabs in sequence | 25-60s | 5-12s _(first call cold, next 4 are instant cache hits)_ |

### 6.6 Memory Budget

| Cache | Max size | Max memory |
|-------|----------|------------|
| AI response cache | 256 entries | ~1-2 MB (avg ~5KB per AI response) |
| Query cache | 512 entries | ~2-4 MB |
| Context string cache | 64 entries | ~256 KB |
| **Total** | | **~5-7 MB** |

Negligible memory footprint for the process.

### 6.7 Future Optimizations (Not Yet Implemented)

| Optimization | Effort | Impact | Status |
|---|---|---|---|
| Pre-compute AI on valuation recompute | Medium | Zero wait on first read after recompute | Not planned |
| Persistent AI cache (Redis) | Medium | Survives process restarts, shared across workers | Not planned |
| Stale-while-revalidate | Low | Show cached AI instantly, refresh in background | Not planned |
| Cache-Control headers on overview endpoint | Low | Browser-side cache eliminates re-requests entirely | Not planned |
| Warm cache on startup for popular tickers | Medium | First user always hits cold cache | Not planned |

### 6.8 End-to-End Sequence Diagram — Tab Flow with Caching

The diagram below traces a realistic user session across 5 steps, showing exactly where caching eliminates work.

```
User                    SPA                    FastAPI                    CacheManager            Supabase           OpenRouter
 │                       │                        │                          │                      │                  │
 │ 1. Load page          │                        │                          │                      │                  │
 │──────────>           │                        │                          │                      │                  │
 │                       │ GET /RBLX/rule1       │                          │                      │                  │
 │                       │──────────────────────>│                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │  get_company_context     │                      │                  │
 │                       │                        │─────────────────────────>│──── (cache miss) ────>│                  │
 │                       │                        │<──────── row ────────────│<──── response ───────│                  │
 │                       │                        │  store in request+TTL   │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  get_last_output_       │                      │                  │
 │                       │                        │  snapshot(rule1)        │                      │                  │
 │                       │                        │─────────────────────────>│──── (cache miss) ────>│                  │
 │                       │                        │<──── snapshot ──────────│<──── response ───────│                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  get_current_market_    │                      │                  │
 │                       │                        │  price                  │                      │                  │
 │                       │                        │─────────────────────────>│──── (cache miss) ────>│                  │
 │                       │                        │<──── price ────────────│<──── response ───────│                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  generate_suitability   │                      │                  │
 │                       │                        │  _summary(RBLX, rule1)  │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │                         │  check AI cache      │                  │
 │                       │                        │                         │  key=hash(rule1,    │                  │
 │                       │                        │                         │       all_data)      │                  │
 │                       │                        │                         │  → MISS              │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  build suitability      │                      │                  │
 │                       │                        │  prompt (TASK only)     │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  POST /chat/completions │                      │                  │
 │                       │                        │─────────────────────────────────────────────────────────────────>│
 │                       │                        │<─────────────────────────────────────────────────────────────────│
 │                       │                        │                         │                      │                  │
 │                       │                        │  store AI response      │                      │                  │
 │                       │                        │  key=hash(all_data)     │                      │                  │
 │                       │                        │  TTL=300s               │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │<── 200 OK + text ──────│                         │                      │                  │
 │<══════════════════════│                         │                         │                      │                  │
 │ Renders text         │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │ 2. Switch to DCF tab  │                        │                          │                      │                  │
 │──────────────────────>│                        │                          │                      │                  │
 │                       │ GET /RBLX/dcf          │                          │                      │                  │
 │                       │──────────────────────>│                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │  3 repo queries         │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │  check request cache    │                      │                  │
 │                       │                        │  get_company_context    │                      │                  │
 │                       │                        │  → HIT (request scope)  │                      │                  │
 │                       │                        │  get_last_output_snap   │                      │                  │
 │                       │                        │  → HIT (TTL cache)      │                      │                  │
 │                       │                        │  get_current_market_    │                      │                  │
 │                       │                        │  → HIT (TTL cache)      │                      │                  │
 │                       │                        │  **0 Supabase calls**   │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  generate_suitability   │                      │                  │
 │                       │                        │  _summary(RBLX, dcf)    │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │                         │  check AI cache      │                  │
 │                       │                        │                         │  key=hash(dcf,data)  │                  │
 │                       │                        │                         │  → MISS              │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  build DCF prompt       │                      │                  │
 │                       │                        │  (TASK only, no context)│                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  POST /chat/completions │                      │                  │
 │                       │                        │─────────────────────────────────────────────────────────────────>│
 │                       │                        │<─────────────────────────────────────────────────────────────────│
 │                       │                        │                         │                      │                  │
 │                       │                        │  store AI response      │                      │                  │
 │                       │                        │  key=hash(dcf,data)     │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │<── 200 OK + text ──────│                         │                      │                  │
 │<══════════════════════│                         │                         │                      │                  │
 │ Renders text         │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │ 3. Switch back to     │                        │                          │                      │                  │
 │    Rule1 tab          │                        │                          │                      │                  │
 │──────────────────────>│                        │                          │                      │                  │
 │                       │ GET /RBLX/rule1        │                          │                      │                  │
 │                       │──────────────────────>│                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │  3 repo queries         │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │  → ALL HIT (TTL cache)  │                      │                  │
 │                       │                        │  **0 Supabase calls**   │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  generate_suitability   │                      │                  │
 │                       │                        │  _summary(RBLX, rule1)  │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │                         │  check AI cache      │                  │
 │                       │                        │                         │  key=hash(rule1,    │                  │
 │                       │                        │                         │       all_data)      │                  │
 │                       │                        │                         │  → **HIT!**         │                  │
 │                       │                        │<── cached text ────────│                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │<── 200 OK (cached) ────│                         │                      │                  │
 │<══════════════════════│                         │                         │                      │                  │
 │ Instant render       │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │ 4. User recomputes    │                        │                          │                      │                  │
 │    Rule1              │                        │                          │                      │                  │
 │──────────────────────>│                        │                          │                      │                  │
 │                       │ POST /RBLX/rule1       │                          │                      │                  │
 │                       │──────────────────────>│                          │                      │                  │
 │                       │                        │  recompute valuation    │                      │                  │
 │                       │                        │  ~15-20 Supabase queries│                      │                  │
 │                       │                        │─────────────────────────>│──── (no cache) ─────>│                  │
 │                       │                        │                         │  writes new          │                  │
 │                       │                        │                         │  output_snapshot     │                  │
 │                       │                        │                         │  for rule1           │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  generate_suitability   │                      │                  │
 │                       │                        │  _summary(RBLX, rule1)  │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │                         │  check AI cache      │                  │
 │                       │                        │                         │  key=hash(rule1,    │                  │
 │                       │                        │                         │       NEW_data)      │                  │
 │                       │                        │                         │  → **MISS**          │                  │
 │                       │                        │                         │  (hash differs due   │                  │
 │                       │                        │                         │   to new snapshot)   │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  POST /chat/completions │                      │                  │
 │                       │                        │─────────────────────────────────────────────────────────────────>│
 │                       │                        │<─────────────────────────────────────────────────────────────────│
 │                       │                        │                         │                      │                  │
 │                       │                        │  store AI response      │                      │                  │
 │                       │                        │  key=hash(NEW_data)     │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │<── 200 OK + text ──────│                         │                      │                  │
 │<══════════════════════│                         │                         │                      │                  │
 │                       │                        │                          │                      │                  │
 │                       │                        │                          │                      │                  │
 │ 5. Switch to DCF tab  │                        │                          │                      │                  │
 │    (no recompute)     │                        │                          │                      │                  │
 │──────────────────────>│                        │                          │                      │                  │
 │                       │ GET /RBLX/dcf          │                          │                      │                  │
 │                       │──────────────────────>│                          │                      │                  │
 │                       │                        │  3 repo queries → HIT   │                      │                  │
 │                       │                        │  **0 Supabase calls**   │                      │                  │
 │                       │                        │                         │                      │                  │
 │                       │                        │  generate_suitability   │                      │                  │
 │                       │                        │  _summary(RBLX, dcf)    │                      │                  │
 │                       │                        │─────────────────────────>│                      │                  │
 │                       │                        │                         │  check AI cache      │                  │
 │                       │                        │                         │  key=hash(dcf,      │                  │
 │                       │                        │                         │       OLD_data)      │                  │
 │                       │                        │                         │  → **HIT!**          │                  │
 │                       │                        │                         │  (DCF data unchanged)│                  │
 │                       │                        │                         │                      │                  │
 │                       │<── 200 OK (cached) ────│                         │                      │                  │
 │<══════════════════════│                         │                         │                      │                  │
 │ Instant render       │                        │                          │                      │                  │
```


**Key observations from the sequence:**
- **Steps 2-3 & 5** make **zero** Supabase calls (query cache hits)
- **Steps 3 & 5** make **zero** OpenRouter calls (AI cache hits)
- **Step 4** (recompute) automatically invalidates only the affected method's AI cache — DCF still hits
- The only slow requests are the first visit (Step 1) and a recomputed method (Step 4)
- No explicit cache invalidation code needed — hash-based keys handle it automatically

---

## 7. Test Plan

### 7.1 Unit Tests

All unit tests are fast (no network calls) — pure logic, mocked repositories, mocked HTTP client.

#### 7.1.1 `CacheManager` — Cache Layer Tests

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 1 | `test_cache_manager_init` | All 3 caches exist, empty, with correct maxsize/TTL defaults | None |
| 2 | `test_query_cache_hit` | `set_query_result` → `get_query_result` returns same value within TTL | None |
| 3 | `test_query_cache_miss` | `get_query_result` for unseen key returns `None` | None |
| 4 | `test_query_cache_ttl_expiry` | Value set with TTL=0.001 → wait 10ms → returns `None` | None |
| 5 | `test_query_cache_request_scope` | Value set in request scope → `clear_request_cache()` → returns `None` | None |
| 6 | `test_query_cache_lifecycle` | Request scope hit, then TTL hit after clear, then miss after TTL expiry | `time` patched |
| 7 | `test_ai_cache_hit_miss` | `set_ai_response` → `get_ai_response` hit; different hash → miss | None |
| 8 | `test_ai_cache_key_hashing` | Same symbol+method+data produces same key; different data → different key | None |
| 9 | `test_ai_cache_hash_stability` | Hash is deterministic (same inputs → same output across calls) | None |
| 10 | `test_ai_cache_ttl` | AI response expires after configured TTL | `time` patched |
| 11 | `test_context_cache_hit_miss` | `set_context` → `get_context` hit; different symbol → miss | None |
| 12 | `test_cache_manager_clear_all` | `clear_all()` empties all 3 caches + resets request scope | None |

**Context hash computation tests:**

| # | Test | What it verifies |
|---|------|------------------|
| 13 | `test_hash_changes_on_output_snapshot` | Recomputing rule1 changes its `output_snapshot` → hash differs |
| 14 | `test_hash_unchanged_on_identical_data` | Same financial data + same snapshots → hash is identical |
| 15 | `test_hash_per_method_independent` | Rule1 recompute only changes rule1's hash; DCF's hash stays same |
| 16 | `test_hash_includes_all_columns` | Hash incorporates income, balance_sheet, cash_flow, shares, market_data |

#### 7.1.2 `ai_service.py` — Cache Integration Tests

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 17 | `test_suitability_cache_hit_returns_cached` | Cache hit → returns cached text, `provider.generate_text` **not called** | CacheManager.has_hit=True |
| 18 | `test_suitability_cache_miss_calls_provider` | Cache miss → calls `provider.generate_text`, stores result | CacheManager.has_hit=False |
| 19 | `test_overview_cache_hit_returns_cached_dict` | Cache hit → returns cached dict, `provider.generate_text` **not called** | CacheManager.has_hit=True |
| 20 | `test_overview_cache_miss_calls_provider` | Cache miss → full flow: context + prompt + provider + store | CacheManager.has_hit=False |
| 21 | `test_suitability_no_company_context_built` | `_build_company_context()` **never called** from `generate_suitability_summary` — verify via spy | Spy on builder |
| 22 | `test_overview_company_context_still_built` | `_build_company_context()` **is called** from `generate_overview_summary` | Spy on builder |
| 23 | `test_cache_context_hash_includes_evidence` | Hash incorporates `evidence`, `valuation_inputs`, `input_decisions` | Spy on hash builder |
| 24 | `test_cache_skipped_when_provider_disabled` | `OPEN_ROUTER_KEY` empty → returns `None`, no cache read/write | `settings.OPEN_ROUTER_KEY=None` |

#### 7.1.3 Repository — Batch Query Tests

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 25 | `test_get_last_output_snapshots_returns_all` | Returns dict with key for each requested method | Supabase `.in_()` mocked |
| 26 | `test_get_last_output_snapshots_missing_method` | Method with no runs → `None` in dict (not absent) | Supabase returns partial |
| 27 | `test_get_last_output_snapshots_ordering` | Returns most recent per method (DESC run_at) | Multiple rows per method |
| 28 | `test_get_last_output_snapshots_invalid_method` | Unknown method in list → `None` without error | Supabase filter excludes it |
| 29 | `test_get_last_output_snapshots_empty_list` | Empty `methods` list → returns `{}` | No call made |
| 30 | `test_get_last_output_snapshots_db_error` | Supabase exception → logged + returns `{}` | `.execute()` raises |

#### 7.1.4 `CompanySnapshotBuilder` — Context Isolation Tests

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 31 | `test_builder_only_used_by_overview` | `CompanySnapshotBuilder.build()` called 0 times for suitability, 1 for overview | Spy on both paths |
| 32 | `test_builder_results_cached` | Same symbol called twice within TTL → second call returns cached, 0 repo queries | Spy on repo |

#### 7.1.5 Request Cache Middleware Tests

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 33 | `test_middleware_clears_cache_after_response` | After request completes, `clear_request_cache()` called | FastAPI TestClient |
| 34 | `test_middleware_works_on_error` | Even on 500 error, cache is still cleared | Route that raises |

### 7.2 Integration Tests

Integration tests use a **real FastAPI TestClient** + **mocked Supabase** (httpx transport layer) + **real OpenRouter** (optional, skipped if key absent).

#### 7.2.1 Full Request Flow Tests

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 35 | `test_rule1_suitability_full_flow` | GET /RBLX/rule1 → 200 + text response. Total Supabase calls ≤ 3 (context, snapshot, price). **No company context queries.** | Mock Supabase transport |
| 36 | `test_dcf_suitability_full_flow` | Same assertion pattern for DCF method | Mock Supabase transport |
| 37 | `test_overview_full_flow` | GET /RBLX/overview → 200 + JSON. `_build_company_context` called once. Batch query replaces 5 individual calls. | Mock Supabase transport |
| 38 | `test_overview_missing_methods` | Only 2 of 5 methods computed → overview returns valid JSON with only those 2 | Partial snapshots |
| 39 | `test_cached_then_uncached_method` | First call hits → second call for same method hits **AI cache** (0 OpenRouter calls) | Double request |

#### 7.2.2 Tab Switch Scenario Tests

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 40 | `test_tab_switch_cache_hit` | Seq: GET rule1 → GET dcf → GET rule1. Third call returns **cached** (no AI call). | Sequential TestClient |
| 41 | `test_tab_switch_cache_ttl_respected` | Seq: GET rule1 → wait 310s → GET rule1. Third call is **cache miss** (fresh AI call). | Time patched + TestClient |
| 42 | `test_tab_switch_multi_user_isolation` | User A requests rule1/AAPL → User B requests rule1/RBLX → User A requests rule1/AAPL. User A's second call **hits cache** (separate keys). | Different symbols |
| 43 | `test_tab_switch_hash_invalidation` | Seq: GET rule1/RBLX → POST recompute rule1 → GET rule1/RBLX. Second GET is **cache miss** (hash changed). | Real recompute logic |

#### 7.2.3 Concurrency Tests

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 44 | `test_concurrent_identical_requests` | 10 concurrent GET rule1/RBLX → only 1 Supabase call, only 1 AI call. All 10 get same response. | `asyncio.gather` + semaphore |
| 45 | `test_concurrent_different_requests` | 10 concurrent: 5 GET rule1 + 5 GET dcf → 1 Supabase batch each, 1 AI call each method. Total: 2 AI calls, not 10. | Mix of symbols/methods |
| 46 | `test_concurrent_recompute_and_read` | POST recompute rule1 + concurrent GET rule1 → GET waits for recompute to finish, hash reflects new data | Race condition test |

#### 7.2.4 Cache Invalidation Tests

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 47 | `test_recompute_invalidates_only_own_cache` | Seq: GET rule1 + GET dcf → recompute rule1 → GET rule1 cache miss + GET dcf cache **hit** | Partial recompute |
| 48 | `test_market_price_change_invalidates_all` | Market data price changes → all AI caches for that company miss (hash includes price) | Mock price update |
| 49 | `test_income_statement_change_invalidates_overview` | New income statement year → overview AI cache misses (context hash changed) | Mock financial update |

#### 7.2.5 Error & Edge Case Tests

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 50 | `test_cache_manager_db_error_propagation` | Supabase query fails → CacheManager returns `None` (no throw), caller handles gracefully | Mock timeout |
| 51 | `test_cache_corruption_handling` | Cached value is `None` or malformed → treated as cache miss | Manually corrupt cache |
| 52 | `test_ai_cache_empty_response` | Cached AI response is empty string → treated as miss | `set_ai_response(key, "")` |
| 53 | `test_large_context_hash_mismatch` | Supabase returns nulls/None in financial data → hash computed correctly (no crash) | Null financial fields |
| 54 | `test_request_cache_cleared_on_chain_calls` | Service A → Service B (same request) → both use same request cache → cleared after response | Nested service calls |

### 7.3 Test Fixtures & Mocks

```python
# --- CacheManager Mock ---
@pytest.fixture
def cache_manager() -> CacheManager:
    """Real CacheManager with short TTLs for test isolation."""
    return CacheManager(
        ai_ttl=300,        # standard
        query_ttl=2,       # short — tests don't wait 30s
        context_ttl=2,     # short
        maxsize_ai=64,
        maxsize_query=128,
        maxsize_context=16,
    )

@pytest.fixture
def cache_manager_spy(cache_manager) -> Generator[CacheManager, None, None]:
    """CacheManager wrapped with call counters for assert."""
    with patch.object(cache_manager, "get_ai_response", wraps=cache_manager.get_ai_response) as spy:
        yield spy

# --- Supabase Transport Mock ---
@pytest.fixture
def mock_supabase_transport() -> httpx.MockTransport:
    """Intercepts all supabase.supabase.com requests and returns canned data."""

# --- FastAPI TestClient with real CacheManager ---
@pytest.fixture
def client(cache_manager) -> TestClient:
    """TestClient with all DI wired — real CacheManager, mocked repo + provider."""

# --- Hash Comparators ---
def hash_for(symbol: str, method: str, evidence: dict,
             valuation_inputs: dict, input_decisions: dict,
             output_snapshots: dict) -> str:
    """Public helper to compute what the CacheManager would compute for cache key."""
```

### 7.4 Test Success Criteria

| Metric | Threshold |
|--------|-----------|
| Unit test count | ≥ 34 |
| Integration test count | ≥ 20 |
| Total test count | ≥ 54 |
| Unit test execution time | < 2s (no network) |
| Integration test execution time | < 30s (with mocked Supabase transport) |
| Cache hit coverage | All 3 layers tested for hit/miss/expiry |
| Invalidation coverage | Hash-change scenarios for recompute, market data, financials |
| Concurrency coverage | Race conditions, concurrent identical + different requests |
| Error coverage | DB failure, cache corruption, null data, timeout |
| Code coverage target | > 90% for `CacheManager`, `ai_service.py` cache paths |

### 7.5 Running Tests

```bash
# Unit tests only (fast, no network)
pytest tests/test_ai_migration.py -k "unit" -v

# Integration tests (mocked Supabase transport, optional real AI)
pytest tests/test_ai_migration.py -k "integration" -v

# Caching-specific tests
pytest tests/test_ai_migration.py -k "cache" -v

# Concurrency tests (may need -xvs for debug)
pytest tests/test_ai_migration.py -k "concurrent" -v --timeout=60

# Full suite
pytest tests/test_ai_migration.py -v
```

---

## 8. Class Diagrams

```
┌─────────────────────────────────┐
│       AIProvider (ABC)          │
├─────────────────────────────────┤
│ + generate_text(prompt,         │
│     system_instruction,         │
│     max_tokens, temperature,    │
│     timeout) → Optional[str]    │
│ + generate_json(...)            │
│     → Optional[dict]            │
└───────────┬─────────────────────┘
            │ implements
            ▼
┌─────────────────────────────────┐
│     OpenRouterProvider          │
├─────────────────────────────────┤
│ POST /chat/completions          │
│ Bearer token auth               │
│ extract choices[0].message      │
│ .content                        │
│ → None on any failure           │
└─────────────────────────────────┘


┌────────────────────────────────────┐
│    CompanySnapshotBuilder          │
├────────────────────────────────────┤
│ + build(symbol) → Dict[str, Any]   │
│ + format_context(snapshot) → str   │
│   (static method)                  │
└────────────────────────────────────┘


┌──────────────────────────────────┐
│    ai_service.py (module)        │
├──────────────────────────────────┤
│ configure_ai(provider, builder,  │
│              cache_manager)      │
│ generate_suitability_summary()   │
│ generate_overview_summary()      │
└──────────────────────────────────┘
         │ uses
         ▼
┌──────────────────────┐  ┌───────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│  company_snapshot.py  │  │ suitability.py    │  │ overview.py         │  │  caching/cache_manager  │
│  CompanySnapshot     │  │ build_suitability_│  │ build_overview_     │  │  .py                    │
│  Builder             │  │   prompt(...)      │  │   prompt(...)       │  │  CacheManager          │
│                      │  │ _fmt()            │  │ OVERVIEW_FALLBACK   │  │  - AI response cache    │
│                      │  │ _critical_flags() │  │ _METHOD_LABELS      │  │  - Query cache          │
│                      │  │ _input_source_    │  └─────────────────────┘  │  - Context string cache │
│                      │  │   summary()       │                           │  - Request scope        │
│                      │  │ _prompt_*() × 6   │                           └─────────────────────────┘
│                      │  │ _prompt_generic() │
└──────────────────────┘  └───────────────────┘
```
