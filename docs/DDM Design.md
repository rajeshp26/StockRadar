
StockerPro Financial Analysis System
1. Purpose of This Document
This document is the single source of truth for understanding the StockerPro Financial Analysis System. It is written so that a new engineer (frontend or backend) can fully understand the system without reading any code first.
It covers:

Business goals and user intent
End‑to‑end request/response flow
Frontend architecture and state model
Backend architecture and responsibilities
Data model and persistence strategy
Caching vs recompute rules
Rule #1 and Dividend Discount Model (DDM)
Suitability, diagnostics, and explainability
History design
Extension patterns for future models (DCF, OE, etc.)


2. Core Product Goals
2.1 What the system solves
StockerPro provides explainable intrinsic valuation of publicly traded stocks. Unlike black‑box valuation tools, it emphasizes:

Transparency ("How we arrived here")
Applicability ("Should this model even be used?")
Auditability (history of past runs)
Consistency across valuation methods
2.2 Non‑Goals (Explicit)
The system intentionally does not:

Provide trading recommendations
Perform portfolio‑level optimization
Hide assumptions or auto‑tune inputs silently
Every assumption must be visible and traceable.


3. High‑Level Architecture

Browser (Next.js)
   │
   ▼
Next.js API Proxy  (/api/proxy/valuations/*)
   │   - injects auth
   │   - hides backend URL
   ▼
FastAPI Backend
   │   - ValuationService (orchestration)
   │   - RecomputeGuard (freshness logic)
   │   - Suitability Evaluators
   ▼
Supabase (Postgres)
   │   - valuation_runs (authoritative history)
   │   - intrinsic_value_analysis (Rule #1 cache only)
   │   - financial statement tables


Key principle: Frontend never talks directly to the backend.


4. Frontend Architecture
4.1 Page Structure

/analysis/[symbol]
 ├─ Sticky Header (symbol, live price)
 ├─ Tabs
 │   ├─ Intrinsic Value  ✅ implemented
 │   ├─ Financial Health (placeholder)
 │   ├─ Moat (placeholder)
 │   ├─ Dividend (placeholder)
 │   └─ Others (placeholder)


The Intrinsic Value tab is a method selector, not a single model.


4.2 Intrinsic Value – Mental Model

Intrinsic Value
 ├─ Valuation Overview
 ├─ Method Selector
 │   ├─ Rule #1 (Phil Town)
 │   └─ Dividend Discount Model (DDM)
 └─ Method Panel
     ├─ Summary
     ├─ How We Arrived Here
     ├─ Suitability
     └─ History


Each valuation method is isolated and lazy‑loaded.


4.3 State & Hooks (Frontend)

Hook	Responsibility
useAnalysis	Rule #1 valuation lifecycle
useDdmAnalysis	DDM valuation lifecycle (per variant cache)
useRule1History	Non‑blocking Rule #1 history
useDdmHistory	Non‑blocking DDM history
useLivePrice	Read‑only live market price

Key design rule:


History and price must never block valuation rendering.




4.4 Variant Switching (DDM)
DDM supports multiple variants:

Gordon Growth
Two‑Stage
Frontend behavior:

Each (symbol + variant) is cached independently
Switching variants is instant if cached
First access triggers compute
Recompute always forces backend refresh
This avoids stale UI and unnecessary recomputation.


5. Backend Architecture
5.1 API Layer (api/valuations.py)
Responsibilities:

Auth enforcement
Request validation
Method routing
Endpoints (current):

POST /valuations/{symbol}/rule1
GET /valuations/{symbol}/rule1/history
POST /valuations/{symbol}/ddm?variant=...
GET /valuations/{symbol}/ddm/history?variant=...
The API layer contains no valuation math.


5.2 ValuationService (Application Layer)
Responsibilities:

Resolve company context
Determine cached vs recompute path
Resolve inputs (defaults → overrides → fallbacks)
Call valuation engine
Persist valuation run
Return FE‑ready response
This layer is pure orchestration.


5.3 Recompute Guard (Freshness Logic)
Each valuation method defines:

Which data dependencies matter
How freshness is evaluated
Examples:

Rule #1 depends on EPS, forecasts, industry multiples
DDM depends on dividend history, ROE, payout ratios
Price is explicitly excluded from freshness checks (read‑time only).


6. Valuation Engines (Domain Layer)
6.1 Rule #1 Engine
Computes:

Future EPS
Future P/E
Sticker Price
MOS Price
Outputs:

valuation block
applicability block
dataQuality block


6.2 Dividend Discount Model (DDM)
Supported variants:

Gordon Growth
Two‑Stage
Core outputs:

Intrinsic value
Growth assumptions
Required return
All math is deterministic and side‑effect free.


7. Suitability & Diagnostics
7.1 Why Suitability Exists
Valuation math answers "what is the number". Suitability answers "should we trust this number".
They are intentionally separate.


7.2 Applicability Model

Applicability
 ├─ score (0–100)
 ├─ category (Good / Caution / Poor)
 └─ flags[]


Flags are explainability artifacts, not errors.
Examples:

UNSTABLE_DIVIDENDS
GROWTH_EXCEEDS_RETURN
INSUFFICIENT_HISTORY


8. History Design (Auditability)
8.1 Source of Truth
All history comes from valuation_runs.
Never from cached tables.


8.2 What History Shows (Phase 1)

Run timestamp
Key outputs only
Suitability score & category
No diagnostics or diffs (by design).


9. Persistence Strategy

Table	Purpose
valuation_runs	Authoritative audit log
intrinsic_value_analysis	Rule #1 cache only
ddm_valuations	Optional analytical store

History always reads from valuation_runs.


10. Security Model

Frontend → Proxy → Backend only
No backend URLs exposed
Auth enforced centrally
RLS enforced at DB level


11. Extending the System
To add a new valuation method:

Add engine (pure math)
Add suitability evaluator
Register dependencies
Add API endpoint
Add FE panel (reuse MethodPanel)
No existing code needs to change.


12. Key Design Principles (Summary)
✅ Transparency over cleverness
✅ Suitability ≠ valuation
✅ History is audit, not analytics
✅ Cached paths must explain themselves
✅ No silent assumptions


13. Who This Document Is For

New frontend engineers
New backend engineers
Product managers reviewing scope
Future maintainers of valuation logic
If someone reads only this document, they should understand what the system does, why it exists, and how data flows end‑to‑end.
