# AI Integration Design

> **Feature:** OpenRouter-based AI stock analysis summaries and cross-method valuation recommendations, enriched with full company financial context.
>
> **Status:** Implemented — 2026-05-24 | Caching v2 planned | Digital Twin Chatbot planned
>
> **Endpoints:**
> - `GET /valuations/{symbol}/overview` — cross-method AI recommendation
> - `POST /valuations/{symbol}/rule1` — suitability summary
> - `POST /valuations/{symbol}/ddm` — suitability summary
> - `POST /valuations/{symbol}/dcf` — suitability summary
> - `POST /valuations/{symbol}/owner_earnings` — suitability summary
> - `POST /valuations/{symbol}/residual_income` — suitability summary
> - `GET /analysis/{symbol}/magic-formula` — suitability summary
> - `POST /valuations/{symbol}/chat` — digital twin conversational AI (SSE streaming)
>
> **Design:** Provider-abstracted architecture with `AIProvider` ABC, `OpenRouterProvider`, extracted prompt builders, and `CompanySnapshotBuilder` for financial context enrichment. The Digital Twin adds a streaming chat layer reusing the same provider and context infrastructure.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Backend Components](#2-backend-components)
3. [Prompt Layer](#3-prompt-layer)
4. [Configuration](#4-configuration)
5. [Error Handling](#5-error-handling)
6. [Performance & Caching](#6-performance--caching)
7. [Test Plan](#7-test-plan)
8. [Class Diagrams](#8-class-diagrams)
9. [Digital Twin Chatbot](#9-digital-twin-chatbot)

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
        ├──────────────────────────────────────────────────────────┐
        ▼                                                         ▼
ai_service.py (orchestration)                         api/chat.py (chat endpoint)
  configure_ai(...)                                      POST /{symbol}/chat
  generate_suitability_summary(...)                        ├─ authenticate user
  generate_overview_summary(...)                           ├─ build company context
                                                          ├─ build chat system prompt
                                                          ├─ OpenRouterProvider
                                                          │  .generate_text_stream()
                                                          │   → SSE: {"token":"..."}
                                                          │   → SSE: {"done":true}
                                                          └─ StreamingResponse
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
| Prompts extracted to `prompts/` module | Keeps `ai_service.py` at ~236 lines; prompts are pure data with no API concerns |
| `CompanySnapshotBuilder` | Centralises all company data queries, single source of truth for AI context |
| Two-part prompt: CONTEXT + TASK | Clear separation: model knows what is background vs what is the specific analysis task |
| All available years, no limit | Financial data quality improves with depth |
| Preserved function signatures | All 7 existing callers unchanged; chat endpoint is new and uses `generate_text_stream` |
| Low temperature (0.1) | Deterministic, factual output for financial analysis |
| `configure_ai()` DI setter | Wired in `dependencies.py` via `get_valuation_repository()` |
| **No company context for individual methods** | Individual suitability promps are self-sufficient from `evidence`/`valuation_inputs`/`input_decisions`; company context (13 queries) is only built for overview |
| **AI response cache** | Same inputs always produce same outputs when financial data is static; TTL cache makes tab switches instant (3-6s → 0ms) |
| **Request-scoped query cache** | Eliminates ~50% duplication — route handler and snapshot builder fetch the same rows independently |
| **Single batch query for snapshots** | 5 `.eq()` round-trips → 1 `.in_()` call; reduces overview latency by ~4 network trips |
| **Streaming chat pattern** | Digital Twin uses SSE streaming (`StreamingResponse`) so users see tokens appear progressively — no full-response wait. Reuses same `OpenRouterProvider` with `stream=True` |
| **Chat reuses context cache** | The same `CompanySnapshotBuilder` + `CacheManager` context that powers overview feeds the chatbot, so the AI has the full financial picture without extra DB queries |
| **No chat persistence (MVP)** | Messages are held in React component state only. Page refresh resets conversation. No DB writes needed. |

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

Thin orchestration layer (~236 lines with caching). Wired via `configure_ai()` in `dependencies.py`:

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

Three system instructions — one for each AI interaction mode:

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

_CHAT_SYSTEM_INSTRUCTION_TEMPLATE = (
    "You are a digital financial analyst specializing in {symbol}. "
    "You answer questions about valuation, financial health, and market data "
    "for {symbol} using the live financial data below.\n\n"
    "{company_context}\n\n"
    "Guidelines:\n"
    "- Be concise and factual. Reference specific numbers from the data.\n"
    "- If asked about something outside the provided data, say so clearly.\n"
    "- Do not invent metrics or make up data.\n"
    "- Use plain English — your audience is a retail investor.\n"
    "- Keep responses under 3-4 sentences unless the question requires detail."
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
| `ChatEndpoint` (new) | `generate_text_stream` | `api/chat.py` |

### 2.8 API Layer

All 7 existing routes in `api/valuations.py` and `api/analysis.py` remain unchanged:

| Method | Path | Location | AI Used |
|--------|------|----------|---------|
| GET | `/valuations/{symbol}/overview` | `valuations.py` | Overview summary |
| GET/POST | `/valuations/{symbol}/rule1` | `valuations.py` | Suitability summary |
| GET/POST | `/valuations/{symbol}/ddm` | `valuations.py` | Suitability summary |
| GET/POST | `/valuations/{symbol}/dcf` | `valuations.py` | Suitability summary |
| GET/POST | `/valuations/{symbol}/owner_earnings` | `valuations.py` | Suitability summary |
| GET/POST | `/valuations/{symbol}/residual_income` | `valuations.py` | Suitability summary |
| GET | `/analysis/{symbol}/magic-formula` | `analysis.py` | Suitability summary |
| POST | `/valuations/{symbol}/chat` | `chat.py` (new) | Digital Twin conversational AI |

The new chat endpoint is defined in a separate `api/chat.py` router, included from `main.py`, using the same `/valuations` prefix so the stock symbol context is immediately available.

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
| Max tokens | 800 (suitability) / 1000 (overview) / 1024 (chat) |
| Streaming | Chat uses SSE streaming; suitability & overview are single-response |

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
| API key not set (chat) | Endpoint returns `503 AI provider not configured` |
| Company snapshot fails (chat) | Returns `503` — without financial context the AI cannot answer usefully |
| HTTP error / timeout (chat) | Yields `{"error": "..."}` SSE event, then `{"done": true}` |
| Malformed SSE chunk (chat) | Logged and skipped — streaming continues |

All errors are caught at the AI layer — callers always receive `None` (never an exception) except the chat endpoint which yields error events in the SSE stream.

---

## 6. Performance & Caching

### 6.1 Problem

Before caching, every AI call triggers:

| Request type | Supabase queries (before) | Supabase queries (after) | AI API call | Typical P95 latency |
|---|---|---|---|---|
| Individual method (rule1/dcf/...) | 16 (3 route + 13 context) | 3 (context, snapshot, price) — no company context | 1 | 5-12s |
| Overview | 20 (7 route + 13 context) | 7 (CacheManager dedup + batch snapshot query) | 1 | 7-15s |
| _Tab switch (SAME data)_ | 16-20 _again_ | **0** (all cache hits) | _1 again_ | _5-12s again_ |
| Digital Twin chat | N/A | 0 (context already cached from overview flow) | 1+ (streaming) | stream-dependent |

The financial data and valuation output snapshots are **completely static** between recomputes. Every tab switch re-fetches identical data and re-calls OpenRouter for the same inputs — pure waste.

**Note on individual method optimization:** `generate_suitability_summary()` no longer builds company context for individual methods. The method-specific `evidence`, `valuation_inputs`, and `input_decisions` dicts are self-sufficient — providing the full 13-query financial snapshot added zero marginal value for per-method analysis. This reduced per-method Supabase queries from 16 to 3.

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

---

## 9. Digital Twin Chatbot

> **Feature:** Conversational AI assistant embedded in the Analysis page that answers stock-specific questions by streaming responses from OpenRouter, enriched with real-time company financial context.
>
> **Status:** Planned — 2026-05-24
>
> **Endpoints:**
> - `POST /valuations/{symbol}/chat` — SSE streaming chat endpoint
>
> **Pattern:** Follows the existing AI architecture — same `AIProvider` ABC, same `CompanySnapshotBuilder`, same `CacheManager` context dedup. Adds streaming support as a first-class capability.

### 9.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Analysis Page (Next.js)                                        │
│                                                                 │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │              │  │                │  │  <AIChatBot />      │  │
│  │ Valuation    │  │  Method Panel  │  │  ┌──────────────┐  │  │
│  │ Overview     │  │  with Analyst  │  │  │  Pulsing Orb  │  │  │
│  │ (AI rec)     │  │  Note          │  │  │  (fixed pos)  │  │  │
│  │              │  │                │  │  ├──────────────┤  │  │
│  │              │  │                │  │  │  Chat Panel   │  │  │
│  │              │  │                │  │  │  (w-96 popup)  │  │  │
│  │              │  │                │  │  │  Messages     │  │  │
│  │              │  │                │  │  │  Streaming    │  │  │
│  │              │  │                │  │  │  Input        │  │  │
│  └──────────────┘  └────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │
         │ POST /api/proxy/valuations/{symbol}/chat
         ▼
┌────────────────────────────────────────────────────────────────┐
│  Next.js API Proxy (web/src/app/api/proxy/[...path]/route.ts)  │
│  • Injects Firebase auth token                                 │
│  • Pipes SSE response through unchanged                        │
└────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│  api/chat.py — POST /valuations/{symbol}/chat                  │
│                                                                │
│  1. Authenticate user (same Depends as valuations)             │
│  2. Parse ChatRequest { messages: [{role, content}] }          │
│  3. Build system prompt with COMPANY CONTEXT:                  │
│     "You are a digital financial analyst specializing          │
│      in {symbol}. Live financial data:                         │
│      {CompanySnapshotBuilder.format_context(snapshot)}"        │
│  4. Construct messages: [system, ...body.messages]             │
│  5. Call OpenRouterProvider.generate_text_stream(messages)     │
│  6. Yield SSE events to StreamingResponse:                     │
│       data: {"token":"The"}                                    │
│       data: {"token":" intrinsic"}                             │
│       data: {"done":true}                                      │
│  7. No caching (conversations are unique by nature)            │
└────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│  OpenRouterProvider.generate_text_stream()                     │
│  (providers/ai_provider.py)                                    │
│                                                                │
│  POST https://openrouter.ai/api/v1/chat/completions            │
│  Body: { model, messages, stream: true, max_tokens: 1024 }    │
│                                                                │
│  Parses SSE chunks from OpenRouter:                            │
│    data: {"choices":[{"delta":{"content":"The"}}]}             │
│    → yields {"token": "The"}                                   │
│  On [DONE] or finish_reason=stop:                              │
│    → yields {"done": true}                                     │
│  On error: logs + yields {"error": "msg"}                      │
└────────────────────────────────────────────────────────────────┘
```

### 9.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Streaming (SSE) over non-streaming** | Users see progressive token rendering, feels responsive. Backend already uses SSE for price streaming — same `StreamingResponse` + `text/event-stream` pattern. No WebSocket dependency needed. |
| **No conversation persistence (MVP)** | Chat is per-session, per-stock. Page refresh resets. No DB writes, no conversation management. Can add Supabase persistence later if needed. |
| **Reuses `CompanySnapshotBuilder` + `CacheManager`** | The company context built for the overview is already cached at the context layer — the chat endpoint gets it for free (0 extra DB queries if overview was just loaded). |
| **Separate `api/chat.py` router** | Keeps the chat endpoint isolated from valuation endpoints. Follows the same pattern as `api/analysis.py`. |
| **`generate_text_stream` as new abstract method** | Adds streaming as a first-class capability to `AIProvider`. Any future provider (Anthropic, OpenAI native) can implement it independently. |
| **No AI response cache for chat** | Chat conversations are free-form and unique — caching would rarely hit and adds complexity. The company context itself is cached (60s TTL) so repeated chats within a session share the same financial snapshot. |
| **Low temperature (0.1)** | Same as suitability/overview — deterministic, factual answers. Stock analysis should not be creative. |

### 9.3 `providers/ai_provider.py` — Streaming Extension

New abstract method on `AIProvider`:

```python
class AIProvider(ABC):

    @abstractmethod
    async def generate_text(
        ...
    ) -> Optional[str]:
        ...

    @abstractmethod
    async def generate_json(
        ...
    ) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    async def generate_text_stream(
        self,
        messages: List[Dict[str, str]],       # [{"role": "user", "content": "..."}]
        system_instruction: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.1,
        timeout: float = 15.0,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream tokens from the AI provider.
        
        Yields dicts with one of these shapes:
          {"token": "word"}     — a content token to stream to the client
          {"done": True}        — signals the response is complete
          {"error": "..."}      — something went wrong, stop streaming
          
        Implementations must use `stream=True` on the underlying API call
        and parse `delta.content` from each SSE chunk.
        """
        ...
        if False:
            yield  # make the generator type-check
```

`OpenRouterProvider.generate_text_stream()` implementation:

```python
async def generate_text_stream(
    self,
    messages: List[Dict[str, str]],
    system_instruction: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.1,
    timeout: float = 15.0,
) -> AsyncGenerator[Dict[str, Any], None]:
    
    if not self._api_key:
        logger.info("[AI] OPEN_ROUTER_KEY not set — streaming disabled")
        return
    
    chat_messages = []
    if system_instruction:
        chat_messages.append({"role": "system", "content": system_instruction})
    chat_messages.extend(messages)
    
    body = {
        "model": self._model,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            async with client.stream(
                "POST", self._BASE_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                if not resp.is_success:
                    logger.warning("[AI] OpenRouter stream %s", resp.status_code)
                    yield {"error": f"HTTP {resp.status_code}"}
                    return
                
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        yield {"done": True}
                        return
                    try:
                        chunk = json.loads(payload)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield {"token": content}
                        finish = chunk.get("choices", [{}])[0].get("finish_reason")
                        if finish == "stop":
                            yield {"done": True}
                            return
                    except json.JSONDecodeError:
                        continue
    
    except httpx.TimeoutException:
        logger.warning("[AI] OpenRouter stream timed out")
        yield {"error": "timeout"}
    except Exception as exc:
        logger.warning("[AI] OpenRouter stream failed: %s", exc)
        yield {"error": str(exc)}
```

### 9.4 `api/chat.py` — Chat Endpoint

```python
router = APIRouter(prefix="/valuations", tags=["Digital Twin Chat"])


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)


@router.post("/{symbol}/chat")
@limiter.limit("20/minute")
async def chat_with_digital_twin(
    request: Request,
    symbol: str,
    body: ChatRequest,
    user=Depends(get_current_user_dep),
):
    sym = _normalize_symbol(symbol)
    
    # 1. Build company financial context (reuses CacheManager)
    provider = _get_or_create_provider()
    if provider is None:
        raise HTTPException(503, detail="AI provider not configured")
    
    snapshot_builder = CompanySnapshotBuilder(get_valuation_repository())
    snapshot = await snapshot_builder.build(sym)
    context = CompanySnapshotBuilder.format_context(snapshot)
    
    # 2. Build system prompt with financial context
    system_prompt = (
        f"You are a digital financial analyst specializing in {sym.upper()}. "
        f"You answer questions about valuation, financial health, and market data "
        f"for {sym.upper()} using the live financial data below.\n\n"
        f"{context}\n\n"
        f"Be concise, factual, and reference specific numbers from the data. "
        f"If asked about something outside the provided data, say so clearly."
    )
    
    # 3. Convert messages to dict list for the provider
    chat_messages = [m.model_dump() for m in body.messages]
    
    # 4. Stream response back as SSE
    async def event_stream():
        async for event in provider.generate_text_stream(
            messages=chat_messages,
            system_instruction=system_prompt,
            max_tokens=1024,
            temperature=0.1,
            timeout=15.0,
        ):
            if "error" in event:
                yield f"data: {json.dumps({'error': event['error']})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

### 9.5 Frontend Components

#### 9.5.1 `AIChatBot` — Floating Orb + Popup Container

```
web/src/components/chat/
├── ai-chat-bot.tsx     # Floating button + popup toggle
├── chat-panel.tsx      # Message list + input + streaming UI
├── message-bubble.tsx  # Individual message rendering
└── index.ts            # Re-exports
```

**`ai-chat-bot.tsx`** — Floating pulsing orb at `fixed bottom-6 right-6 z-50`:

```tsx
export function AIChatBot({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false);
  
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {open && <ChatPanel symbol={symbol} onClose={() => setOpen(false)} />}
      
      <button
        onClick={() => setOpen(v => !v)}
        className="w-14 h-14 rounded-full glass-panel flex items-center justify-center
                   animate-pulse-glow shadow-lg cursor-pointer hover:scale-105
                   transition-all duration-200"
        aria-label="Toggle AI assistant"
      >
        {open ? (
          <X className="w-6 h-6 text-white/80" />
        ) : (
          <Sparkles className="w-6 h-6 text-indigo-300" />
        )}
      </button>
    </div>
  );
}
```

**`chat-panel.tsx`** — Compact messenger popup (`w-96 max-h-[520px]`):

| Section | Description |
|---------|-------------|
| Header | `"Digital Twin · AAPL"` + close button, glass-nav style |
| Messages | Scrollable area, auto-scrolls to bottom on new content |
| User bubble | Right-aligned, indigo tint, `rounded-2xl` |
| AI bubble | Left-aligned, glass style, small sparkle avatar |
| Streaming indicator | Three bouncing dots (`animate-bounce` with staggered delay) |
| Input bar | `glass-input` text field + send button (ArrowUp icon) |
| Disabled state | Input + send disabled while `isStreaming` is true |

**`use-chat.ts`** — Stream-aware chat hook:

```typescript
function useChat(symbol: string) {
  const [messages, setMessages] = useState<Array<{role: string; content: string}>>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function send(content: string) {
    const userMsg = { role: "user" as const, content };
    setMessages(prev => [...prev, userMsg]);
    setIsStreaming(true);
    setStreamingContent("");

    const res = await fetch(`/api/proxy/valuations/${symbol}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [...messages, userMsg] }),
    });

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";  // keep incomplete line in buffer
      
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = JSON.parse(line.slice(6));
        if (data.done) {
          setMessages(prev => [...prev, { role: "assistant", content: streamingContent }]);
          setStreamingContent("");
          setIsStreaming(false);
        } else if (data.token) {
          setStreamingContent(prev => prev + data.token);
        }
      }
    }
  }

  return { messages, streamingContent, isStreaming, send, clear: () => setMessages([]) };
}
```

**Integration in analysis page:**

```tsx
// web/src/app/(authenticated)/analysis/[symbol]/page.tsx
<AIChatBot symbol={params.symbol} />
```

### 9.6 System Instruction

```python
_CHAT_SYSTEM_INSTRUCTION_TEMPLATE = (
    "You are a digital financial analyst specializing in {symbol}. "
    "You answer questions about valuation, financial health, and market data "
    "for {symbol} using the live financial data below.\n\n"
    "{company_context}\n\n"
    "Guidelines:\n"
    "- Be concise and factual. Reference specific numbers from the data.\n"
    "- If asked about something outside the provided data, say so clearly.\n"
    "- Do not invent metrics or make up data.\n"
    "- Use plain English — your audience is a retail investor.\n"
    "- Keep responses under 3-4 sentences unless the question requires detail."
)
```

### 9.7 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| API key not set | Endpoint returns `503 AI provider not configured`. Logged once. |
| Company snapshot build fails | Returns `503` — without financial context the AI cannot give useful answers |
| HTTP error from OpenRouter | Yields `{"error": "..."}` SSE event, then `{"done": true}`. Frontend shows error state in last message. |
| Network timeout | Yields `{"error": "timeout"}`. Frontend shows "Request timed out" in chat. |
| Empty response | Yields `{"done": true}` with no tokens — chat shows empty assistant message. |
| Malformed SSE chunk | Logged and skipped — streaming continues with next chunk. |

### 9.8 Frontend Error States

The chat bubble component handles:

```
Messages state machine:
  idle → user sends → streaming (tokens arriving) → done (full msg) → idle
  
Error display within the message stream:
  - Last AI bubble shows: "Sorry, I encountered an error: [message]"
  - Input re-enabled so user can retry
  - No toast/global notification needed — error is contextual to the chat
```

### 9.9 Dependencies

| Dependency | Change | Reason |
|------------|--------|--------|
| `httpx` | Already present | Used for the streaming POST to OpenRouter |
| `lucide-react` | Already present | `Sparkles`, `X`, `ArrowUp` icons |
| Tailwind CSS | Already present | `animate-pulse-glow`, `glass-panel`, `glass-input` already defined |

No new npm or pip packages required.

### 9.10 Future Enhancements (Not Yet Implemented)

| Enhancement | Effort | Impact | Status |
|---|---|---|---|
| Persist chat history to Supabase | Medium | Conversations survive page refresh | Not planned |
| Follow-up suggested questions | Low | Show "Ask about DCF value" buttons below AI response | Not planned |
| Chat context from specific valuation method | Medium | "Explain the DCF result for AAPL" — injects method-specific evidence | Not planned |
| Multi-symbol chat | Medium | "Compare AAPL and MSFT" — builds two contexts | Not planned |
| Abort in-flight generation | Low | Cancel button during streaming | Not planned |
| Markdown rendering in AI responses | Low | Code blocks, bold numbers for key metrics | Not planned |

### 9.11 Test Plan

#### 9.11.1 Unit Tests — `providers/ai_provider.py`

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 1 | `test_generate_text_stream_yields_tokens` | SSE chunks parsed into `{"token": "..."}` events in correct order | `httpx.Client.stream` with canned SSE lines |
| 2 | `test_generate_text_stream_done_signal` | `[DONE]` line yields `{"done": true}` and stops | Single-line SSE |
| 3 | `test_generate_text_stream_finish_reason_stop` | `finish_reason: "stop"` yields `{"done": true}` | Last chunk has stop |
| 4 | `test_generate_text_stream_http_error` | Non-2xx response yields `{"error": "..."}` + returns | Mock 401 response |
| 5 | `test_generate_text_stream_timeout` | `httpx.TimeoutException` yields `{"error": "timeout"}` | AsyncMock side_effect=TimeoutException |
| 6 | `test_generate_text_stream_no_api_key` | Empty key → no API call, generator yields nothing | `settings.OPEN_ROUTER_KEY = None` |
| 7 | `test_generate_text_stream_malformed_chunk` | Bad JSON lines are skipped, valid lines still processed | Mixed valid/invalid SSE |
| 8 | `test_generate_text_stream_system_instruction` | System message prepended to messages array | Spy on body content |
| 9 | `test_generate_text_stream_noop_yield` | Abstract method has `yield` for type-checking (coverage) | Direct ABC call |
| 10 | `test_generate_text_stream_produces_type` | Generator yields `dict` with correct keys only | Full stream capture |

#### 9.11.2 Unit Tests — `api/chat.py`

| # | Test | What it verifies | Mock |
|---|------|------------------|------|
| 11 | `test_chat_endpoint_200` | Valid request → 200 + `text/event-stream` | Mock provider + snapshot |
| 12 | `test_chat_endpoint_no_provider` | No API key → 503 | `settings.OPEN_ROUTER_KEY = None` |
| 13 | `test_chat_endpoint_snapshot_fails` | Snapshot build fails → 503 | `CompanySnapshotBuilder.build` raises |
| 14 | `test_chat_endpoint_streams_response` | Response body contains SSE `data:` lines | Real mock stream |
| 15 | `test_chat_endpoint_invalid_symbol` | Empty/non-existent symbol → `_normalize_symbol` error | Short symbol |
| 16 | `test_chat_endpoint_missing_messages` | Empty messages array → 422 validation | `messages: []` |
| 17 | `test_chat_endpoint_rate_limit` | Hits rate limit → 429 | Multiple rapid requests |
| 18 | `test_chat_endpoint_unauthorized` | No user token → 401/403 | Unauthenticated client |

#### 9.11.3 Integration Tests — End-to-End Chat Flow

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 19 | `test_chat_full_flow` | POST → SSE stream → full response reconstructs coherent text | Mock OpenRouter transport |
| 20 | `test_chat_context_injected` | System prompt contains financial metrics from snapshot | Inspect provider call args |
| 21 | `test_chat_conversation_history` | 2-turn conversation passes both user messages to provider | Two sequential requests |
| 22 | `test_chat_overview_cache_shared` | Company context from prior overview call is reused (0 extra DB queries) | Spy on repo methods |

#### 9.11.4 Frontend Tests

| # | Test | What it verifies | Setup |
|---|------|------------------|-------|
| 23 | `test_floating_orb_renders` | Button appears at bottom-right with sparkle icon | Render `<AIChatBot symbol="AAPL" />` |
| 24 | `test_orb_toggles_chat_panel` | Click opens panel, click again closes | React Testing Library |
| 25 | `test_chat_panel_sends_message` | Typing + submit calls fetch with correct body | Mock fetch |
| 26 | `test_chat_panel_displays_incoming_message` | SSE tokens reconstruct into message bubble | Mock SSE stream |
| 27 | `test_chat_panel_streaming_indicator` | Three bouncing dots visible during streaming | Mock slow stream |
| 28 | `test_chat_panel_disabled_during_streaming` | Input + send disabled while streaming | Mock stream in progress |
| 29 | `test_chat_panel_send_empty_message` | Empty input does nothing (no fetch call) | Mock fetch |
| 30 | `test_chat_panel_error_handling` | `{"error": "..."}` event shows error message in chat | Mock error SSE |

#### 9.11.5 Test Fixtures — Chat

```python
@pytest.fixture
def mock_sse_chunks() -> list:
    """Simulates 3 token events + done from OpenRouter."""
    return [
        b"data: {\"choices\":[{\"delta\":{\"content\":\"The\"}}]}\n\n",
        b"data: {\"choices\":[{\"delta\":{\"content\":\" intrinsic\"}}]}\n\n",
        b"data: {\"choices\":[{\"delta\":{\"content\":\" value\"}}]}\n\n",
        b"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n",
    ]

@pytest.fixture
def mock_openrouter_stream(mock_sse_chunks):
    """Patches httpx.AsyncClient.stream to yield mock_sse_chunks."""
    async def mock_stream(*args, **kwargs):
        class FakeStream:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *excinfo):
                pass
            @property
            def is_success(self):
                return True
            async def aiter_lines(self):
                for chunk in mock_sse_chunks:
                    # Convert raw bytes to parsed SSE lines
                    for line in chunk.decode().split("\n"):
                        yield line
        return FakeStream()
    
    with patch("httpx.AsyncClient.stream", new=mock_stream):
        yield

@pytest.fixture
def chat_client(mock_valuation_repo, mock_supabase_transport) -> TestClient:
    """FastAPI TestClient with mocked chat dependencies."""
    # Wires OpenRouterProvider with mock stream + CompanySnapshotBuilder
    ...
```

#### 9.11.6 Test Success Criteria

| Metric | Threshold |
|--------|-----------|
| Provider unit tests | ≥ 10 |
| API endpoint tests | ≥ 8 |
| Integration tests | ≥ 4 |
| Frontend component tests | ≥ 8 |
| Total test count | ≥ 30 |
| Streaming coverage | Token yield, done signal, error, timeout, malformed data |
| Error coverage | No API key, HTTP error, timeout, snapshot failure, rate limit |
| Mock quality | All external calls mocked (OpenRouter, Supabase) |
| Frontend coverage | Open/close, send, receive, stream indicator, disabled state, error |
