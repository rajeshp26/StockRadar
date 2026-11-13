# Stock Evaluation Code Review — Findings

**Date:** 2026-08-15
**Scope:** Watchlist dashboard → stock analysis page → valuation evaluation flow (web + backend)
**Method:** Live Playwright execution against the running app (localhost:3000 + backend :8001), backend code + logs review, network/perf instrumentation of 11 symbols (RBLX, SIRI, AI, NOW, U, MSFT, SOFI, BMY, CPNG, F).
**Status:** ⚠️ Multiple performance and robustness issues found. No code changed — findings only.

---

## 1. Executive Summary

Clicking a stock in the watchlist dashboard fires **11–12 backend requests** for a single analysis page load. On a cold page load every request takes **~7.1–7.6s** (measured), producing a perceived load time of **>7s** — even though each endpoint's actual work (cache read) is ~50–350ms.

Root cause of the latency is not the evaluations themselves: it is that **the backend serializes all DB I/O onto a single event loop** (`async def` handlers calling the **synchronous** Supabase client, running under a **single uvicorn worker**). When 10+ requests arrive at once they queue behind each other's blocking `.execute()` calls instead of running concurrently. This is the classic "sync client inside async FastAPI" antipattern.

Two more root causes behind the surface symptoms:

- **Most stocks have never had a valuation computed at all** (§4.12). A `valuation_computation` job handler exists in `scheduler_worker.py`, but **no periodic planner registers it and nothing enqueues its jobs** — scheduled computation therefore never occurs; valuations are produced only when a user manually clicks "Run Computation" or adds a symbol to a watchlist. So for 9/10 stocks the 7.5s page load is mostly spent discovering there is nothing to show, and the AI recommendation (which needs ≥1 computed method) is unreachable by default.
- **~99% of historical valuation data was lost in the cloud → local migration** (§4.14). The cloud baseline had **4,174 valuation runs** for 194 companies; the local DB has **58** — all post-migration recomputes (IDs restarted at 1). DCF/DDM/intrinsic-value/dividend/price-history tables lost 56–100% of rows. The migration verify script checked **structure only** (tables/views/indexes/constraints), never asserted row equality — that's why the loss went unnoticed. The intact cloud dump (`docs/migration_baseline/table_data/*.json`) makes it recoverable; this restore is **step 0** before any valuation feature work.
- **All 7 local views are missing SELECT grants** (§4.15) — `portfolio_monthly_dividends` and `portfolio_user_import_history` are used by live endpoints that now return 500 (reproduced). The grant step of the migration silently didn't take effect; `fix_grants.sql` fixes it in seconds. Also part of **step 0**.
- **The database is re-read redundantly** (§4.13). Two separate problems: the **computation path** re-reads the same shared tables 5× (all 5 method fetchers query `income_statements`, `financial_ratios`, defaults, overrides independently — verified compute-only, with zero in-memory caching); the **read path** re-reads each method's snapshot twice per page load (5 GETs + overview re-reading all 5 snapshots) plus AI context build even when AI is disabled.

The rest of the findings:

- **3 of 5 valuation methods (DDM, Owner Earnings, Residual Income) are `not_computed` for 9 of 10 stocks tested** — yet the frontend still issues a full round-trip for each (each costing ~880ms under load, plus a 404 error in the console). Massive waste of requests and noise.
- **The overview endpoint re-reads the same 5 snapshots the frontend already fetched individually** — duplicate DB work server-side.
- **The AI recommendation (`/overview`) silently returns `null`** when `OPEN_ROUTER_KEY` is not configured (current dev/prod config), so the "AI recommendation" feature is effectively dead while still costing an extra request + full context build.
- **Design quality is good in places** (method-per-service, GET-cache/POST-compute split, React Query key discipline) — but there is **significant redundancy and duplicated extraction logic** across frontend and backend.
- **Content gaps:** Rule #1 valuation returns `stickerPrice: 0` for negative-EPS companies (RBLX) while still being marked `computed` — a zero intrinsic value presented as a real result. Freshness metadata contains a negative day count (`epsForecast: -140`), a date-handling bug.

**Proposed target architecture (§6, v2.1 after two design reviews — preferred, not mandated):** a **read model over valuation run history** — a SQL view/RPC selecting the latest publishable run per (company, scope, method), promoted to a physical `valuation_method_current` projection **only if measured** — exposed through a **page-oriented summary endpoint** (`GET /analysis/{symbol}/valuation-summary`, auth sync and live quote kept separate, per-method detail lazy-loaded on tab activation), backed by an **idempotent computation pipeline** in `scheduler_worker.py` (separate published-state vs job-state, stale-while-revalidate, transactional publication via outbox, applicability pre-check) and a **staged async-safe data layer**. A **typed method-summary contract** carries `status/reasonCode/computedAt/inputAsOf/modelVersion` plus lineage (`fundamentalsRevision`, `assumptionProfileVersion`, `marketDataAsOf`, `calculationRunId`); domain applicability, freshness semantics (`capturedAt` vs `targetPeriodEnd`), reference-price labeling, error architecture, and the AI lifecycle (with deterministic fallback) are separate concerns from the DTO. Six independently shippable phases (§6.3) map every finding in this doc to exactly one architectural change. If measurement shows scale doesn't warrant it, a simpler design (lazy method queries + one SQL view + thread-backed repo adapter) is preferable — the proposal is a target to verify against, not an unconditional mandate (review §10.3).

---

## 2. Measurement Data (live, Playwright)

### 2.1 Cold page load — one click (RBLX, fresh navigation)

All 10 requests fired within ~7ms of each other (t≈570ms) and all completed at t≈7.5s:

| Request | Duration |
|---|---|
| `/users/sync` (POST) | 7,179 ms |
| `/stocks/RBLX/quote` | 7,144 ms |
| `/valuations/RBLX/rule1` | 7,096 ms |
| `/valuations/RBLX/dcf` | 7,101 ms |
| `/valuations/RBLX/ddm?variant=gordon` | 7,139 ms |
| `/valuations/RBLX/owner_earnings` | 7,137 ms |
| `/valuations/RBLX/residual_income` | 7,553 ms |
| `/portfolio/holdings/RBLX/exists` | 7,574 ms |
| `/analysis/RBLX/risk-assessment` | 7,595 ms |
| `/analysis/RBLX/fundamentals?frequency=quarterly` | 7,647 ms |
| `/valuations/RBLX/overview` *(fires after the above settle)* | 609 ms |

### 2.2 Sequential vs parallel — strong serialization signal

- **1 request (warm):** ~320–550 ms (the endpoint's real work)
- **8 parallel identical requests (warm):** each 1.36–1.75 s, total wall 1.76 s → strongly suggests requests execute **serially** (one after another), rather than overlapping
- 8 × ~350 ms ≈ 2.8 s; observed 1.76 s → consistent with per-request blocking DB calls queueing on one event loop, but not conclusive on its own (see §4.1 — connection-pool limits, PostgREST concurrency, or cold connection establishment are alternative explanations; the definitive test is server-side instrumentation in Phase 1)

### 2.3 Multi-symbol sweep (9–12 requests per load)

| Symbol | Requests | Total req-time (sum) | Max single | Methods computed |
|---|---|---|---|---|
| RBLX | 11 | — | 7.6 s | rule1, dcf |
| SIRI | 12 | 8,357 ms | 1,257 ms | rule1 |
| MSFT | 11 | 6,867 ms | 991 ms | **none** |
| NOW | 10 | 6,415 ms | 926 ms | **none** |
| SOFI | 11 | 7,866 ms | 1,224 ms | **none** |
| BMY | 11 | 7,019 ms | 1,021 ms | **none** |
| CPNG | 11 | 6,975 ms | 975 ms | **none** |
| F | 11 | 6,917 ms | 991 ms | **none** |

Consistent 404s (console errors) for ddm / owner_earnings / residual_income on nearly every symbol.

---

## 3. What Is Working Well (keep this)

1. **Clean method-per-service backend design.** `ValuationService` is a thin orchestrator; each model (Rule1, DCF, DDM, OE, RI) has its own service + domain models + repository. Good separation. (`valuation_service.py`, `rule1_service.py`, etc.)
2. **GET-cache / POST-compute split.** GET endpoints are pure cache reads (no writes); POST runs the staleness gate. Correct REST discipline. Frontend mirrors this with `fetch*Cached` (queryFn) vs `fetch*Outcome` (recompute button).
3. **`not_computed` sentinel handling.** 404 → `{ notComputed: true }` → "Run Computation" CTA instead of an error state. Good UX.
4. **React Query key discipline.** All 5 method hooks share the *same* query keys as `prefetchAllValuations` and `useValuationOverview` → no duplicate network calls for the same method (react-query dedupes). This is the right pattern.
5. **Stale/gc tuning is sane.** Valuations: stale 10 min / gc 30 min. Navigation away and back serves from cache.
6. **History endpoints are fail-safe** (never break the UI, return empty list on error).
7. **Deprecated `useValuationStream`** — dead code properly marked, replaced by the single `GlobalSSEProvider` connection. Good hygiene.
8. **`_extract` helpers are null-safe** and upside/downside math is guarded against zero price.
9. **Rate limiting** exists per endpoint (30–60/min GET, 10/min POST) — reasonable, though see §5.

---

## 4. What Is Not Working

### 4.1 [PERF] Sync Supabase client inside async handlers → event-loop starvation  🔴 CRITICAL

- `backend/database.py` uses `create_client(...)` with `SyncClientOptions` — a **synchronous** HTTP client.
- FastAPI route handlers are declared `async def` and call `supabase.table(...).execute()` **directly** (98 sync `.execute()` calls in `valuation_repository.py` alone; also in `users.py`, `watchlists.py`, `portfolio.py`, `stocks.py`, `super_investors.py`).
- A blocking `.execute()` inside an `async def` **can** block the entire event loop: under 10 concurrent requests, request #2's DB query cannot start until #1's finishes → everything serializes. **Status: strong hypothesis, not yet conclusively proven.** The wall-clock evidence (8 parallel requests each taking 1.36–1.75 s, total wall time 1.76 s) is consistent with event-loop blocking during part of each request, but is *not* dispositive — it could also involve connection-pool limits, PostgREST concurrency limits, browser/proxy queuing, a shared upstream dependency, or cold connection establishment. The definitive test is server-side instrumentation (Phase 1): event-loop lag, per-request spans, timing around each `.execute()`, active request counts, and a controlled sync-vs-`to_thread`-vs-async-client comparison.
- **Verified single worker:** `backend/start.sh:144-148` launches `python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload --log-level debug` — **no `--workers N`** → exactly one event loop for the whole API.
- **Impact:** the "9+ concurrent requests" design intent is defeated — they are effectively sequential (if the hypothesis holds). Cold loads ~7.5 s; warm parallel bursts ~1.4–1.75 s per request instead of ~0.35 s.
- **Note:** sync endpoints declared `def` (e.g. `get_stock_quote`) run in the threadpool and are *not* the problem — the mix of sync `def` (threadpool) and async `def`-with-sync-calls (blocking loop) is.

**Fix options (in order of effort/impact):**
1. **Cheapest:** run uvicorn with `--workers 4` (or more). The blocking calls then starve only one loop; parallelism returns (still wasteful, CPU-heavy). **Mitigation only** — each worker still blocks its own loop; adds separate connection pools, caches, and rate-limit stores.
2. **Proper (staged):** migrate toward `create_async_client` + `AsyncClientOptions` with `await` on every `.execute()` — but staged via a repository boundary: bounded thread-pool adapter first (measure + stabilize), then async-client per repository group (measure), then remove the adapter. **Verified viable:** `requirements.txt` pins `supabase==2.28.3`, and `create_async_client` imports successfully in the backend venv. Caveat: `database.py` holds a module-level singleton and repos construct/use it synchronously in many places — the migration touches `database.py` + every repo call site (98 in `valuation_repository.py` alone) + unit tests that mock the client.
3. **Alternative:** wrap sync repo calls in `asyncio.to_thread(...)` at the repository boundary (keeps sync client, moves blocking off the loop). Lowest code churn per call site; legitimate as a *temporary* bounded-thread adapter so long as sync and async modes are not mixed unpredictably inside the same repository.

### 4.2 [PERF] 11–12 requests per page load — most of them unnecessary 🔴

Per click the frontend fires, via `prefetchAllValuations` + `usePredictiveTabPrefetch` + `useValuationOverview` + page components:

| Request | Needed? |
|---|---|
| rule1, dcf, ddm, owner_earnings, residual_income (5 GETs) | Only methods actually used — see 4.3 |
| overview (1 GET) | Needed only if ≥1 method computed; re-reads what the 5 GETs already fetched |
| risk-assessment, fundamentals (2 GETs) | Predictive prefetch of adjacent tabs — **not** needed on first paint |
| holdings/exists (1 GET) | Needed (decides "Performance" tab visibility) |
| quote (1 GET) | Needed (live price header) |
| users/sync (POST) | Fires from `auth-provider.tsx` `onAuthStateChange` (L221) — can fire **2+ times per session** (INITIAL_SESSION + TOKEN_REFRESHED events); settings page re-syncs on demand (L44). 7.1s cold |

**Fix options:**
- Consolidate the 5 valuation GETs into the overview response (see 4.3) → 5 requests become 1.
- Gate `usePredictiveTabPrefetch` to idle time only (it already uses `requestIdleCallback` — good — but the 5 valuation prefetches + risk + fundamentals run immediately on mount in `prefetchAllValuations`).
- Investigate `users/sync` repeated firing — single call site (`auth-provider.tsx:221` `onAuthStateChange`), but each auth event (INITIAL_SESSION, TOKEN_REFRESHED, SIGNED_IN…) triggers it; ensure the handler dedupes per-session instead of per-event.
- `fundamentals?frequency=quarterly` at ~1.2s is the single slowest endpoint under load — it should not be on the critical first-paint path.

### 4.3 [DESIGN] 5 parallel GETs + overview re-reading the same snapshots 🔴

- Frontend issues 5 method GETs **and** 1 overview GET.
- Backend `get_valuation_overview` (`valuation_service.py:175-272`) then re-fetches the same 5 snapshots server-side (`get_last_output_snapshots`) + current price + company context + builds an AI context string.
- Net: the same snapshot rows are read twice per load, and the AI overview path rebuilds the full company context even when AI is disabled.

**Fix (updated to match the final proposal, §6):** replace this page-load pattern with the page-oriented summary endpoint `GET /analysis/{symbol}/valuation-summary` (or an equivalent single query over the read model) — return all 5 method summaries **plus** recommendation status in one response, read from the read model (view/RPC over `valuation_runs` first, physical projection only if measured) in one query (§6.1-C). The frontend consumes the canonical contract without per-method extraction; per-method detail endpoints remain for lazy tab activation and recompute only.

### 4.4 [PERF] `not_computed` methods still cost a full round-trip + console 404s 🔴

- For 9/10 tested symbols, DDM/OE/RI have never been computed, yet the frontend fires a full GET for each (404) on every page load.
- Each 404 under load costs ~880 ms and produces a console error (`Failed to load resource: 404`), tripping error boundaries / analytics noise.
- **Fix:** the overview response already contains `status: not_computed` per method — the frontend should render those states from the overview cache **without** issuing per-method GETs until the user actually opens that method's tab (lazy per-tab fetch on first click). Same result, 3 fewer requests, zero 404 noise.

### 4.5 [BUG] Rule #1 returns `stickerPrice: 0` for negative-EPS companies, marked `computed` 🟠

Measured payload for RBLX (negative EPS):

```json
"valuation": { "eps0": -1.5671, "futureEPS": 0, "futurePrice": 0,
               "stickerPrice": 0, "mosPrice": 0 },
"applicability": { "score": 18, "category": "Poor" }
```

- `growth` was clamped from `-2.00%` to `2.00%` (flag `R1-GCLAMP-LOW`), then future EPS math on negative base EPS collapses to 0 → **$0 intrinsic value**, which the overview then displays as a `computed` method with IV 0.
- A zero intrinsic value is not "the company is worth $0" — it's "this model cannot value a negative-EPS company." It should be surfaced as `not_meaningful`/`not_computed` with a clear reason, and excluded from the overview consensus.
- **Fix:** applicability is a **domain rule**, not a status-flag tweak: the Rule #1 service (or an applicability policy) decides when output is `not_meaningful`/`not_applicable` — e.g. `stickerPrice <= 0` with `eps0 <= 0` → `R1-NEGEPS → valuation unavailable`. "Computation succeeded" and "output is publishable" are separate concepts: the run *was* computed, so `not_computed` is wrong; `not_applicable`/`not_meaningful` is right. Apply the same policy in the overview builder (skip `computed` when IV is 0/None) and exclude from the consensus. (Design review §7.1: the DTO carries the answer, it doesn't decide it.)

### 4.6 [BUG] Negative freshness days — `epsForecast: -140` 🟠

`dataQuality.freshnessDays` for RBLX: `{ epsForecast: -140, trailingEPS: 17, lastComputedAt: ... }`.

- **Root cause verified (not a parse bug):** `rule1_service.py:269-270` computes `epsForecast = (now_utc().date() - rep_date).days` where `rep_date` is the **earnings-forecast `report_date`** — which is a *future* fiscal-period end (verified live: RBLX's newest forecast row is `report_date = 2026-12-31` with `estimate_eps_growth = -0.02`). Today minus a future date → negative "days since". Measured −140 matches exactly (2026-08-13 − 2026-12-31 = −140).
- The semantics are wrong: `freshnessDays` claims "days since the data was captured", but for a forecast the `report_date` is the *target period end*, not the capture date. The capture date (`created_at`) is what should be measured.
- `toFreshnessInfoFromDataQuality` (`useAnalysis.ts`) validates the timestamp string but the negative day count is baked in server-side. UI consumers rendering "−140 days old" will mislead.
- **Fix:** expose `capturedAt` (forecast `created_at`) and `targetPeriodEnd` (`report_date`) as **distinct fields**; compute `freshnessDays` from `capturedAt`. Clamping negatives to 0 is only a last-resort defensive safeguard — it must not turn incorrect metadata into plausible-looking metadata. Unit-test the date math. (Design review §7.2.)

### 4.7 [FEATURE] AI recommendation is `null` in practice 🟠

- `generate_overview_summary` returns `None` when `OPEN_ROUTER_KEY` is unset (`ai_service.py:142-145`) — silently.
- Measured: `overview.recommendation = null` for every tested symbol, and `loadingRec` never resolves to content.
- **Fix:** three separate outcomes, not one: (a) **fix the silent failure** — recommendation carries its own status (`disabled | pending | available | failed | stale`) with `reasonCode`, so the UI can render "AI unavailable (provider not configured)" instead of an empty box; (b) **enable the feature** — that's a config decision (set `OPEN_ROUTER_KEY`), separate from surfacing its absence; (c) **move AI off the critical path** — precompute/cache the recommendation keyed by valuation snapshot version (Phase 6), never call an LLM during page load. (Design review §7.4.)

### 4.8 [ROBUST] Broad `except Exception` hides failures 🔶

- `valuations.py` wraps every handler in `try/except Exception → HTTP 500 "…failed"`; history endpoints swallow all exceptions and return `[]` ("fail-safe: never break UI").
- This makes real failures invisible: a broken DB query, a schema drift in `output_snapshot`, or a serialization error all degrade to generic messages — no structured error code, no detail for the user.
- **Fix (error architecture, not a payload field):** domain exceptions → repository exception translation → centralized FastAPI exception handlers → correlation IDs → structured logging (`exc_info=True`) → metrics. Stable `error_code`s (e.g. `VALUATION_READ_FAILED`) ride on top so the frontend can distinguish "not computed" (404) from "computed but failed to serialize" (500 with code) — but the broad route-level `except Exception` blocks are removed, not decorated. Keep fail-safe for history endpoints, but with structured logging + metric. (Design review §7.3.)

### 4.9 [DESIGN] Duplicated extraction/derivation logic across 3 layers 🟡

The same "IV + current price → upside/downside; score/category from applicability; lastComputedAt from dataQuality.freshnessDays" derivation is written **3 times**:

1. Backend `valuation_service.get_valuation_overview._extract` (python)
2. Frontend `useValuationOverview.extractFromSnapshot` / `extractRule1` (ts)
3. Inline in `useValuationOverview` per-method object spread

- Field names differ subtly (`stickerPrice` vs `intrinsicValue` vs `intrinsicValuePerShare`; `ivField` param), so a schema change on the backend requires coordinated edits in 3 places — the RBLX $0 bug (§4.5) exists partly because the overview `_extract` doesn't treat IV 0 as invalid while the frontend extractor does (`iv != null`).
- **Fix (updated to match the final proposal, §6):** backend method adapters normalize heterogeneous model outputs into **one summary contract** (`status/reasonCode/intrinsicValue/upsideDownside/score/category/computedAt/inputAsOf/modelVersion`) **when publishing the read model**. The frontend consumes that contract and renders it — it does **not** re-derive intrinsic value, status, or applicability from raw snapshots. Only a simple, canonical presentation calc (e.g. upside vs a live quote, §6.1-E) may run client-side, and must be labeled with its reference price and timestamp.

### 4.10 [MINOR] `useValuationOverview` rebuilds `methods[]` on every query state change 🟡

- `methods` is rebuilt imperatively on every render (5 `useQuery` hooks + object spread + post-hoc Rule1 upside fix at lines 272-276). Combined with the overview tab being the default view, this runs on every keystroke/price update via SSE.
- **Severity note (design review §10.1):** a five-element array rebuild is likely **negligible** vs network requests, component/chart rendering, and SSE-driven updates. **Profile before optimizing** — do not add `useMemo` purely on principle.
- **Fix:** the architectural fix (single summary query, one transform, §4.3/§6.1-B) removes this concern entirely for correctness and simplicity reasons — not because a five-item array is inherently expensive.

### 4.11 [OBS] Console errors on every load: 3× 404 🔶

Caused by §4.4 — 404s on `ddm`, `owner_earnings`, `residual_income` GETs. Not user-visible but pollutes dev/ProdError monitoring. Fixed by the same lazy-fetch change.

### 4.12 [ROOT-CAUSE] Why most stocks have NO computed evaluations 🔴

The evaluations aren't "failing to load" — for 9/10 tested symbols they were **never computed locally at all**. Verified in code **and in the database**:

- **There is no *scheduled/periodic* valuation job.** `backend/main.py:207-218` explicitly moved all schedulers to a separate `scheduler_worker.py` process — and that worker's planner registers Super Investors, Market Data, Earnings, Portfolio Snapshots, Aggregation, and Price Ingestion — but **no valuation planner**. A `valuation_computation` job handler *is* registered (`scheduler_worker.py:234` `engine.register_handler(...)`), but `ValuationComputationScheduler` has **no `plan()` method** (only `compute_all`/`compute_batch`), so it cannot be planner-registered and **nothing ever enqueues `valuation_computation` jobs** (grep confirms: no `enqueue_job("valuation_computation", ...)` anywhere). The only automatic trigger is a direct in-process call on **watchlist add** (`watchlist_service.py:996-1003` `_compute_valuations_background` → `compute_all(force=False)`, fire-and-forget). So in practice a valuation is produced only when a user manually clicks "Run Computation" (POST `/valuations/{symbol}/{method}`) or adds a symbol to a watchlist.
- The 55× `residual_income` runs on 2026-08-05 look like a one-off bulk watchlist-import trigger; rule1/dcf/ddm/oe did not run for those symbols — consistent with compute errors (data missing for negative-EPS/growth symbols, §4.5) rather than a working pipeline.
- So the default state of the product is: stock clicked → all 5 methods `not_computed` → UI shows "Run Computation" CTA. The 7.5s of page-load requests are mostly spent **discovering there is nothing to show**.
- The AI recommendation (which needs ≥1 computed method) therefore also stays `null` for almost every stock — the headline feature of the analysis page is effectively unreachable without manual per-method button clicks.
- **Fix:** background computation pipeline — a valuation job in `scheduler_worker.py` that pre-computes the 5 methods for watchlist/portfolio symbols on a TTL (e.g. nightly + on-watchlist-change). This is the only fix that actually makes evaluations *appear* for most stocks.

> **⚠️ Compound cause — migration data loss (§4.14):** the cloud database had **4,174 valuation runs** for **194 companies**; the local database has **58**, and all 58 are *post-migration recomputes* (IDs 1–58, sequence restarted). Even with a scheduler, most stocks show nothing because their **historical valuation data never made it into the local DB**. The backup dump is intact → recoverable.

### 4.13 [PERF] The computation path re-reads the same shared tables 5×; the read path re-reads snapshots 2× 🟠

**Correction (design review §7):** the 5 cached GET endpoints are **pure snapshot reads** — each `get_cached()` calls only `get_company_context` + `get_last_output_snapshot` (verified in all 5 services; e.g. `rule1_service.py:530-547` "Pure cache read — no gate logic, no recompute, no DB writes"). They do **not** load statements/ratios/defaults. The overlap splits into two distinct problems:

**A. Compute path — shared tables re-read 5× (design review §7 correction).**
The dependency fetchers are invoked **only from computation** (`compute_*_if_stale` / `compute_with_diagnostics` in the 5 services — verified: `get_rule1_dependency_values` called at `rule1_service.py:112/143/151/159`, etc.; 24 total call sites, all in compute):
- `valuation_repository.py` has 5 separate dependency fetchers (`get_rule1_dependency_values` L1021, `get_dcf_dependency_values` L1132, `get_oe_dependency_values` L1195, `get_ri_dependency_values` L1273, `get_ddm_dependency_values` L947).
- Cross-referencing the table calls: **income_statements, cash_flow_statements, balance_sheets, financial_ratios, company_summary, earnings, valuation_method_defaults, company_valuation_overrides** are queried by **multiple** fetchers — e.g. `financial_ratios` at L248/L329/L389/L458; `income_statements` at L239/L371/L431; `valuation_method_defaults` + `company_valuation_overrides` in **every** fetcher (5× each). So a `compute_all` over 5 methods re-reads the same rows ~5× with zero in-memory caching between them.

**B. Read path — snapshots re-read 2× per method (page load).**
The 5 cached GETs each read their method's last snapshot; the overview (`get_valuation_overview`, `valuation_service.py:175-199`) then re-reads **all 5 snapshots again** (`get_last_output_snapshots`) and additionally builds company context for the AI summary (`get_company_context` + financial context — even when AI is disabled, §4.7). So each page load reads each method's snapshot twice, plus AI-context work that the page doesn't need.

**Impact:** compute is slower than it needs to be (5× redundant input reads); page load carries snapshot re-reads + AI context build on top of the 5 GETs. Neither is the event-loop serialization of §4.1 — but both compound it.

**Fix:** shared "fundamentals context" loader in the **computation worker** (fetch company + statements + defaults **once**, feed all 5 methods); the page path reads the read model (view/RPC over `valuation_runs`, §6.1-C) in one query — read optimization and compute optimization are different problems and are solved separately.

### 4.14 [DATA-LOSS] Cloud → local migration dropped ~99% of valuation history 🔴🔴

**Confirmed: data was lost during the Supabase cloud → local migration.** This is the single biggest reason the analysis page shows "Run Computation" for nearly every stock — the historical valuation data simply is not in the local database.

**Evidence — cloud baseline (`backend/docs/migration_baseline/02_row_counts.json`, captured 2026-08-02 from `viqdqgxcumcdhqxooplw.supabase.co`) vs local (measured live today):**

| Table | Cloud | Local | Lost | Status |
|---|---|---|---|---|
| `valuation_runs` | 4,174 | 58 | 4,116 (**99%**) | 🔴 |
| `dcf_valuations` | 76 | 1 | 75 (99%) | 🔴 |
| `ddm_valuations` | 107 | 0 | 107 (100%) | 🔴 |
| `intrinsic_value_analysis` | 62 | 2 | 60 (97%) | 🔴 |
| `dividend_metrics` | 2,683 | 4 | 2,679 (100%) | 🔴 |
| `upcoming_dividend_events` | 73 | 12 | 61 (84%) | 🔴 |
| `dividend_history` | 13,424 | 3,231 | 10,193 (76%) | 🔴 |
| `institutional_holdings` | 48,664 | 4 | 48,660 (100%) | 🔴 |
| `price_history` | 40,327 | 17,757 | 22,570 (56%) | 🟠 |
| `splits` | 346 | 231 | 115 (33%) | 🟠 |

**34 of 58 tables migrated completely** (companies 3,122 = 3,122 ✓, income_statements 3,265 = 3,265 ✓, financial_ratios 3,193 = 3,193 ✓ — the financial core is intact). The loss is concentrated in **valuation + dividend + holdings + price-history** tables.

**Why the 58 `valuation_runs` rows are not "a sample":**
- Local `valuation_run_id` sequence restarted at **1** (min=1, max=58, all rows ID 1–58). A *successful* import would show IDs 1–4,174.
- All 58 rows are **post-migration recomputes**: 55× `residual_income` on 2026-08-05 (bulk run), 1× `rule1` + 1× `dcf` for RBLX on 08-13, 1× `rule1` for SIRI on 08-15. **Zero rows carried over from the cloud.**
- The cloud dump `docs/migration_baseline/table_data/valuation_runs.json` (39 MB) is **intact** — all 4,174 rows present (rule1 321, canslim 19, magic_formula 22, ddm_two_stage 25, ddm_gordon 103, dcf 76, residual_income 3,564, owner_earnings 44; 194 distinct companies).
- FK targets all exist locally (all 194 companies present, `user_id=1` present) — so this was **not** a foreign-key skip; the import for these tables failed wholesale or was never run.

**Likely mechanism (not fully pinned):** `full_schema_migration.py` phase3 batches inserts per table; a non-FK exception in a batch → whole table lands in the `failed` list → 0 rows. The identity-column override map in the script does **not** include `valuation_runs`/`dcf_valuations`/`ddm_valuations` (only `exchange_rates`, `company_summary`, `earnings_forecast`, `revenue_forecast`, `splits`), and the cloud schema declares `run_by_user_id` as **text** while the local DDL (`restore_all_constraints.sql` L1078) declares **integer** with a FK to `users` — a type mismatch is the most probable batch-failure cause for `valuation_runs`. `dcf_valuations`/`ddm_valuations` reference `valuation_run_id` from `valuation_runs` (FK), so their failure follows.

**Why nobody noticed:** `verify_migration.py` is **structure-only** — it compares tables/views/indexes/triggers/constraints (line 1202: "Row count comparison (informational - local will be empty)"). It never asserted row-count equality; row counts were printed as *informational*. The migration plan's "zero data loss" §7 was never enforced by an automated row-level comparison.

**Fix (precedes everything in §6):** re-run the data import for the lost tables from the intact `docs/migration_baseline/table_data/*.json` dumps with corrected column typing (align `run_by_user_id` to the local schema), or restore via psql COPY. Then a background valuation pipeline (§6.1-D) keeps them fresh. Note: `institutional_holdings` was likely wiped *intentionally* by `reset_and_refresh.py`/`cleanup_super_investors_db.py` (`delete().neq('holding_id', 0)`) for a fresh 13-F backfill — confirm before restoring that one; the other 9 tables are pure loss.

### 4.15 [BREAK] Local views have NO SELECT grants — 2 endpoints 500 at runtime 🟠🟠

**Verified live:** all **7 views** in the local database have **no `SELECT` grant** for `service_role`/`anon`/`authenticated` (checked via `pg_views` × `role_table_grants` — only `REFERENCES, TRIGGER, TRUNCATE` are granted). Any read through the service-role client fails with `42501 permission denied for view …`.

**Two are used by live API endpoints (500s):**
- `portfolio_monthly_dividends` — queried by `portfolio_repository.py:639,658` (`get_monthly_dividends`) → **`portfolio.py:1174` dividends endpoint returns 500** ("Failed to get dividends"). Reproduced directly against the service-role client.
- `portfolio_user_import_history` — queried by `portfolio_repository.py:1036` → CSV import-history reads fail. Reproduced.

**Not currently called by app code** (no production `.table()` references found — dormant until used): `super_investor_current_holdings`, `v_dcf_valuations`, `v_ddm_valuations`, `v_owner_earnings_valuations`, `v_residual_income_valuations`.

**Root cause:** `full_schema_migration.py` `main()` runs `phase4_recreate_views` (L507) then `phase5_grant_permissions` (L508) — the grant SQL (L420-422) *does* include views, so on a clean run the grants should exist. Their absence means phase5 either errored silently ("grants with warnings" path at L441) or the local instance was recreated after the migration via a different path (e.g. `supabase db reset` + DDL without grants). The `fix_grants.sql` helper script exists but was evidently never applied.

**Fix:** run the grant step (either `phase5_grant_permissions` or `backend/scripts/fix_grants.sql`) against the local DB. One-time, 5 seconds, restores the 2 live endpoints. This is separate from the data-loss restore in §4.14 — it's a **permission** gap, not missing rows (base tables like `portfolio_dividends` = 1,498 rows, intact).

---

## 5. Secondary Observations

- **Rate limits:** overview GET is `30/min` while the page + hover-prefetch can produce multiple overview hits per session (page prefetch + SSE `valuation_ready` invalidation). With a 46-stock watchlist, route-level prefetch via `stock-card.tsx` (`<Link prefetch={true}>`, L47 — fires on hover/visibility) + page prefetch + SSE invalidation could approach limits in heavy browsing. Verify `limiter` storage is shared across workers if `--workers` is added (in-memory default breaks per-worker limits).
- **`prefetchAllValuations` also prefetches magic-formula + canslim + risk** on mount — more requests than the "5 valuations" the function name implies. These are for tabs the user may never open. Scope prefetch to the default tab's data only.
- **SSE invalidation churn:** `GlobalSSEProvider` invalidates `QK.overview` + method key on every `valuation_ready`. If the backend computes several methods in a burst, the overview is refetched multiple times. Consider debouncing invalidation.
- **Frontend `rule1QueryFn` uses `as any` casts** (`useAnalysis.ts:68-70`, `useValuationOverview` extractors) — hides payload mismatches that §4.5/§4.6 types of bugs would otherwise surface. The backend response models exist; type the frontend against them instead of `as any`.

---

## 6. THE Definitive Solution (v2.1 — revised after second design review): read model (view-first) + page-oriented summary endpoint + idempotent pipeline + async-safe data layer

> **A read model over valuation run history (SQL view/RPC first, physical projection only if measured), exposed through a page-oriented summary endpoint, backed by an idempotent computation pipeline with separate published/job state and an async-safe data layer.**

Four principles from the design review are now baked into the design:

1. **The read path consumes a compact projection.** It never rebuilds valuation state from raw fundamentals on a page load. A SQL view/RPC over `valuation_runs` (latest publishable run per scope+method) is the default; a physical `valuation_method_current` table is promoted only if measured to be necessary. (Read-model optimization and computation-cost optimization are different problems; see §6.1-C/D.)
2. **The valuation endpoint does not absorb auth sync or live quotes.** `users/sync` stays an idempotent session concern; the live quote stays on its own channel. (Different freshness, cache lifetimes, providers, failure modes, HTTP semantics.)
3. **Scheduling is a real idempotent job pipeline with applicability checks** — not "run all five methods nightly." Unit of work, dedup, locking, retries, and a state machine are specified (see §6.1-D).
4. **Domain validation, error handling, freshness semantics, and the AI lifecycle are separate concerns** from the DTO itself (see §6.1-E).

### 6.1 The architecture (one paragraph each)

**A. Async-safe data layer (fixes §4.1).**
Migrate `database.py` toward `create_async_client` + `AsyncClientOptions` (verified available in `supabase==2.28.3`), but **staged**: (1) enforce a repository boundary; (2) move sync repository operations behind a bounded thread-pool adapter; (3) measure and stabilize; (4) migrate repository groups to an async client; (5) remove the thread-backed adapter. The invariant is that sync and async are never mixed *unpredictably inside the same repository*. Note: `--workers N` is an **emergency mitigation, not the end state** — each worker still blocks its own event loop and adds separate connection pools, in-memory caches, rate-limit stores, and duplicated startup behavior. It buys throughput while the staged migration (or bounded-thread adapter) lands.

**B. Page-oriented summary endpoint (fixes §4.2, §4.3, §4.4, §4.11, §4.10).**
`GET /analysis/{symbol}/valuation-summary` returns all 5 method summaries, applicability/reason codes, snapshot metadata, freshness + model versions, recommendation status/content, and **partial errors**. Per-section error isolation is mandatory: one method with malformed historical data must never 500 the whole response. It does **not**: synchronize users, compute valuations, load raw financial statements, call an LLM synchronously, or fail entirely because one method is broken. `users/sync` remains a separate idempotent session concern (dedupe it per session in `auth-provider`) — it is **not** a normal per-navigation request (design review §2.4). The live quote stays on its own channel (`GET /stocks/{symbol}/quote` or SSE) because quote and valuation data have different freshness, cache lifetimes, providers, failure modes, and update mechanisms. Method **detail** (DCF assumptions, projections, terminal-value breakdown) stays on per-method endpoints fetched only when a tab is activated — the summary endpoint stays compact, and the normal critical path per page load is **2 requests (summary + quote)**; auth sync may run concurrently only on session events, and is not counted as expected per-page traffic.

**C. Read model — view/RPC first, physical projection only if measured (fixes §4.3, §4.13 read side).**
The page path needs "latest publishable run per method, one query" — but a new physical table is **not automatically required** (design review §4). **Staged:**
- **Stage 1 (default):** a SQL **view or function** selecting the latest publishable run per `(company, scope, method)` from the immutable run history (`valuation_runs.output_snapshot`). Run history stays the source of truth; no dual-write synchronization, no backfill, no drift, fast to build and verify.
- **Stage 2 (only if measured):** promote to a physical `valuation_method_current` projection if latest-run selection is measurably too slow, query plans are unstable, output normalization is too expensive, or page traffic justifies denormalization.

Either way the page-read path does **not** load income statements, cash-flow statements, balance sheets, ratios, defaults, or overrides — those are computation inputs, not page-read inputs. Read-model optimization (cheap page reads) and compute optimization (shared fundamentals loader in the worker) are separate concerns.

**D. Idempotent computation pipeline (fixes §4.12, §4.13 compute side) — with published state and job state kept separate.**
The shared fundamentals loader belongs **here** — in the worker, not the page path. Per job: load fundamentals once → determine method applicability → compute eligible methods → persist immutable runs → **transactionally publish** current state + outbox event → consumer enqueues recommendation regeneration, SSE, and cache invalidation.

**The single most important correction (design review §3): separate the two state machines.** A professional application shows the last known good valuation while a replacement is queued or computing:

```
Published state (what the page reads)          Job state (what the worker tracks)
valuation_method_current                       valuation_computation_job
- available                                    - queued
- stale                                        - running
- not_applicable                                - succeeded
- not_computed                                  - failed
- failed_without_previous_result               - cancelled
                                               - superseded
                                               - dead_lettered
```

The summary response combines them — **stale-while-revalidate**:

```json
{
  "method": "dcf",
  "status": "stale",
  "intrinsicValue": 142.50,
  "computedAt": "2026-08-12T10:00:00Z",
  "refresh": { "status": "running", "jobId": "job_123", "startedAt": "2026-08-15T11:04:00Z" }
}
```

Rules: continue displaying the last known good result while a refresh is underway; atomically replace the published result **only** after successful computation; preserve the old result if the refresh fails.

**Transactional publication (design review §5).** With Supabase/PostgREST, separate API calls are not one transaction. Safe sequence:

```
Compute outside transaction
  → BEGIN transaction
  → insert immutable run
  → validate publishability (model version, provenance, supersession check)
  → update current pointer/projection conditionally
  → write outbox event
  → COMMIT
  → outbox consumer: recommendation regen, SSE publish, cache invalidate
```

Conditional publication rule: **publish only if `input_revision`/`model_version`/`job_generation` is at least as new as the current projection** — a superseded job can never overwrite a newer result. This prevents: run stored but current not updated; current updated but no event; SSE firing before the transaction is visible; old job overwriting new result.

**Scope model (design review §6).** `scope_id` alone is ambiguous. Use an explicit discriminator:

```
scope_type: global | user | assumption_profile
scope_id:   null only for global; user/profile identifier otherwise
```

- PostgreSQL unique constraints treat `NULL` specially — configure nulls-not-distinct or use a sentinel where needed.
- **The client can never choose another user's `scope_id`** — scope is derived from authenticated identity + authorization rules, enforced server-side.
- User-specific overrides are **snapshotted/versioned**, never silently mutated under an old valuation.
- Computation identity (reusable across users): `(company_id, method, model_version, fundamentals_revision, assumption_profile_hash, currency)` — two users with identical assumptions can share a calculation (content-addressed); the user references the result through their authorized profile.

**Applicability pre-check — candidate rules, pending math review (design review §9).** The checks below are **candidate policies for model-owner review**, not hard-coded universal truths — valuation math was explicitly out of scope for this review. Example candidates: DDM requires stable dividend history (more than just "pays a dividend"); Rule #1 requires positive EPS for *this implementation* (one negative trailing period does not invalidate every earnings-based model); residual income may remain meaningful under some negative-earnings conditions; owner earnings depends on normalization quality, not merely cash-flow history. Applicability is **versioned and recorded**:

```json
{
  "status": "not_applicable",
  "reasonCode": "INSUFFICIENT_DIVIDEND_HISTORY",
  "policyVersion": "ddm-applicability-v3",
  "evaluatedAt": "2026-08-15T10:00:00Z",
  "inputRevision": "fundamentals-abc123"
}
```

Versioning matters: a company can become applicable later, and rules can change.

**Job semantics:** idempotency keys, dedup across watchlists, single-flight locking, retries with backoff, dead-letter handling, per-provider rate limits, dependency freshness checks, model-version invalidation, cancellation/supersession, transactional publication (above), metrics per method and failure reason.

**E. Canonical contract + separated concerns (fixes §4.5, §4.6, §4.7, §4.8, §4.9) + lineage (review §11.2).**
One typed method-summary contract, generated frontend types (no `as any`): `status ∈ {available, stale, not_computed, not_applicable, failed_without_previous_result}`, `reasonCode`, `computedAt`, `inputAsOf`, `modelVersion`, `refresh` (job state, above), nullable numerics. The DTO is a **transport contract, not the policy engine**:

- **Applicability is a domain rule.** The Rule #1 service / applicability policy decides when output is `not_applicable`/`not_meaningful` — the DTO only carries it. "Computation succeeded" and "output is publishable" are separate concepts: a run can be technically successful yet `not_meaningful` (RBLX Rule #1). `not_computed` is wrong there — it *was* computed.
- **Upside/downside needs an explicit reference price (design review §8).** Because the live quote is separate, the contract must state which price produced the ratio:

```json
{
  "intrinsicValue": 142.50,
  "referencePrice": 130.00,
  "referencePriceAsOf": "2026-08-15T14:30:00Z",
  "upsideDownside": 0.0962
}
```

If the UI receives a newer quote after the summary loads: (a) keep showing upside based on the snapshot reference price, **or** (b) recompute display-only upside from the live quote — acceptable *only* as a simple canonical presentation calc (`intrinsicValue / livePrice − 1`), never re-deriving model applicability or intrinsic value. Label the distinction clearly: intrinsic value as-of valuation input date; upside vs current quote; price timestamp.

- **Financial-data lineage (design review §11.2).** `inputAsOf` alone is not enough. A robust result identifies exactly which inputs produced it:

```json
{
  "modelVersion": "dcf-4.2.1",
  "fundamentalsRevision": "fund-2026Q2-v7",
  "assumptionProfileVersion": "profile-18-v3",
  "marketDataAsOf": "2026-08-15T14:30:00Z",
  "currency": "USD",
  "calculationRunId": "run_123"
}
```

- **Restatement handling (design review §11.2).** Financial statements get restated. The pipeline needs rules for: detecting revised source data, invalidating dependent valuations, retaining prior calculations, and marking results superseded-due-to-restatement.
- **Authorization (design review §11.2).** Scope enforcement applies to summary reads, method details, historical runs, AI analysis, and SSE events — never trust client-supplied scope.
- **Freshness semantics are explicit.** Expose `capturedAt` and `targetPeriodEnd` as distinct fields; `freshnessDays` is computed from `capturedAt`. Clamping negatives is a last-resort defense, not the fix — it must not turn incorrect metadata into plausible-looking metadata.
- **Error handling is an architecture, not a field.** Domain exceptions → repository exception translation → centralized FastAPI exception handlers → correlation IDs → structured logging → metrics. Stable `error_code`s ride on top; broad route-level `except Exception` blocks are removed, not just decorated.
- **AI lifecycle is separate from the DTO (design review §12).** Recommendation is precomputed/cached by valuation snapshot version, exposed with its own status (`disabled | pending | available | failed | stale`) and metadata:

```json
{
  "status": "available",
  "text": "...",
  "generatedAt": "2026-08-15T12:00:00Z",
  "sourceSnapshotVersion": "summary-v92",
  "provider": "openrouter",
  "model": "configured-model-id",
  "promptVersion": "valuation-summary-v4",
  "disclaimerVersion": "investment-research-v2"
}
```

AI must summarize published deterministic results (never independently invent valuations), cite which methods were included/excluded, explain `not_applicable` states, avoid claiming certainty, retain the deterministic summary when AI fails, regenerate only when input versions change, and enforce cost/rate limits. **Deterministic fallback** (review §12): when AI is disabled, serve a rule-based summary from the published numbers — "DCF indicates 12% upside. Rule #1 is not applicable due to negative trailing EPS. DDM is not applicable — no qualifying dividend history." That makes the feature useful even without an LLM provider.

### 6.2 How each finding is resolved

| § | Finding | Resolved by |
|---|---|---|
| 4.1 | Sync client serializes all DB I/O | A — staged async migration (bounded-thread adapter → async client); workers as mitigation only |
| 4.2 | 11–12 requests per load | B — one summary endpoint (auth + quote stay separate) |
| 4.3 | Overview re-reads the 5 snapshots | C — one query against the read model (view/RPC first, physical projection only if measured) |
| 4.4 | `not_computed` methods still fetched (404s) | B — statuses arrive in the summary; no per-method GET on load |
| 4.5 | Rule #1 `stickerPrice: 0` shown as computed | E — applicability **policy** (not the DTO) → `not_applicable`/`not_meaningful` |
| 4.6 | Negative freshness days (−140) | E — `capturedAt` vs `targetPeriodEnd` as distinct fields; freshness from `capturedAt` |
| 4.7 | AI recommendation silently null | E — recommendation lifecycle: precomputed by snapshot version, own status (`disabled` when `OPEN_ROUTER_KEY` unset) |
| 4.8 | Broad `except Exception` hides failures | E — error architecture (exceptions → central handlers → correlation IDs → metrics); per-section isolation in B |
| 4.9 | Extraction logic duplicated ×3 | E — one typed contract, generated frontend types |
| 4.10 | Overview `methods[]` rebuilt every render ([MINOR], profile first) | B — one query, one transform (correctness/simplicity, not micro-opt) |
| 4.11 | 3× console 404s per load | B — no more not_computed GETs on load |
| 4.12 | Most stocks never computed at all | D — idempotent pipeline (published vs job state, applicability checks) |
| 4.13 | Shared tables re-read on compute; snapshots re-read on read | C (read: view/RPC first) + D (compute: shared fundamentals loader **in the worker**) |
| 4.14 | Migration dropped 99% of valuation data | **Phase 0 — staged recovery** (precedes all) |
| 4.15 | Local views have no SELECT grants (2 endpoints 500) | **Phase 0 — least-privilege grant review** |

### 6.3 Phased rollout (reordered for lowest risk — design review §10)

| Phase | Scope | Effort | Payoff |
|---|---|---|---|
| **0** | **Safe data recovery + grants.** Full local backup first; stop/isolate writes to affected tables; restore the cloud dump (`docs/migration_baseline/table_data/*.json`) into a **staging** database; apply explicit type transforms (`run_by_user_id` text↔integer); preserve historical IDs where possible; reconcile the 58 post-migration rows against the 4,174 historical rows with an explicit conflict policy (natural key / run identity); reset sequences after import; validate FKs and orphan counts; compare row counts + checksums; sample key symbols' snapshots; promote via a reviewed script; retain rollback artifacts. Historical runs restore **as history** — only promote to `current` if model version + data provenance are valid, else mark `stale` + queue recompute. **View grants:** least-privilege review — verify `security_invoker`, RLS-through-view, and whether the API needs `service_role` only (not blanket `anon`/`authenticated` SELECT) | M–L | Data back; 2 endpoints unblocked; **no risk of overwriting the 58 current rows** |
| 1 | **Instrument + mitigate.** Add tracing: event-loop lag metric, per-request spans, timing around each `.execute()`, active request counts, DB connection timing. Run the controlled sync-vs-`to_thread`-vs-async comparison to confirm the §4.1 hypothesis with server-side evidence (not just wall-clock correlation). Apply bounded-thread or worker mitigation | S–M | Root cause **proven**, not assumed; safe immediate latency relief |
| 2 | **Contract + read model + summary endpoint.** Define the canonical status contract; create the **view/RPC read model first** (latest publishable run per scope+method over `valuation_runs` — no new table, §6.1-C Stage 1); build `GET /analysis/{symbol}/valuation-summary` reading it in one query. Promote to a physical projection (Stage 2) only if measured | M | Fan-out + duplicate reads gone **without touching 98 repo calls first** |
| 3 | **Frontend switch.** Point the page at the summary endpoint; lazy-load method details on tab activation; decouple `users/sync` (dedupe per session — not per-navigation) and quote (own channel) | M | 11–12 → **2** requests/load; 404s gone; immediate UX win |
| 4 | **Async-native repositories** (staged: boundary → thread adapter → measure → async client per group → remove adapter) | M–L | Fix underlying concurrency with controlled risk |
| 5 | **Idempotent pipeline + shared compute context** in `scheduler_worker.py` (separate published/job state, transactional publication + outbox, applicability pre-check, job semantics from §6.1-D) | M | Evaluations exist + stay fresh for most stocks; stale-while-revalidate |
| 6 | **Precomputed/cached AI recommendation + deterministic fallback + shared cache** where measurements justify it (version-keyed, cross-worker safe) | S–M | AI off the critical path, reliable even when disabled |

Each phase is independently shippable and verifiable: re-measure with the same Playwright scripts used here, **plus** the server-side instrumentation from Phase 1 (latency targets are SLOs to verify, §6.7 — not guaranteed outcomes). Phase 0 restores correctness before any feature work; Phases 2–3 deliver the biggest user-visible win before the broad async migration (Phase 4) — the reverse of the v1 ordering, and lower-risk for exactly that reason. Phase 6's cache uses version-keyed invalidation and a shared store (or a clear version strategy) because process-local TTL caches are inconsistent across workers (review §5.3).

### 6.4 What NOT to do

- **Don't mix sync and async unpredictably inside the same repository** — a temporary interface-backed thread adapter is a fine migration step, but both modes in one repo with no boundary is the worst option.
- **Don't fold `users/sync` or the live quote into the valuation endpoint** — it couples auth side effects and fast-changing quote data into a slow, cacheable read; different lifetimes, providers, failure modes, and retry semantics.
- **Don't load raw fundamentals on the page-read path** — the summary endpoint reads the read model (view/RPC over `valuation_runs` first, physical projection only if measured); statements/ratios/defaults belong to the compute path only.
- **Don't let one method's failure 500 the whole summary** — per-section error isolation, always (§6.1-B).
- **Don't pre-compute on the API process** — keep it in `scheduler_worker.py` so page requests never compete with compute jobs (the exact reason schedulers were moved off the API in `main.py:207-218`).
- **Don't run "all 5 methods nightly for every symbol"** — applicability pre-check first; DDM/RI/OE don't apply to many symbols, and repeating known-meaningless compute is the 55× residual_income storm all over again.
- **Don't treat process-local TTL caches as a concurrency-safe cache** — with multiple workers each gets its own cache with inconsistent invalidation; user overrides can leak if keys omit `scope_id`. Version-keyed shared store or request-scoped dedup only.
- **Don't clamp freshness negatives and call it fixed** — expose `capturedAt`/`targetPeriodEnd`; clamping is a defensive last line, not the fix (§6.1-E).
- **Don't restore directly into the active DB or blanket-grant views** — staging + reconciliation + rollback artifacts (Phase 0); least-privilege grant review, `service_role`-only until deliberate.

### 6.5 Why this is the best approach — vs every alternative

**Alternative 1: "Just fix each finding as an isolated patch" (10 independent fixes).**
Fails on integration cost, not on any single patch. §4.5/4.6/4.7/4.8/4.9 all reshape the *same* response payload that §4.3's frontend extractors consume — five patches collide in two files (`valuation_service.py` + `useValuationOverview.ts`), each requiring coordinated edits and re-verification. The sync-client fix (§4.1) alone touches `database.py` + every repo call site (98 in `valuation_repository.py`) + tests that mock the client. Net: ~10 patches ≈ the same effort as Phases 1–6, with 2–3× the integration risk, and the end state is *still* 5 GETs + overview, still no read model, still no pipeline. The summary endpoint (B) and contract (E) exist precisely to make these five findings *one* edit each instead of three coordinated edits.

**Alternative 2: "Async client + workers only" (Phase 4 in isolation, v1's Phase 1).**
Biggest single win for wall-clock latency, but it makes the system *faster at doing unnecessary work*: still 11 requests/load, still 3×404 noise, still `not_computed` for 9/10 stocks, still dead AI, still $0-value and −140-day bugs, still duplicate reads, still no pipeline. It's a prerequisite, not a solution — and it's not even the *first* prerequisite (data + contract are). The v2 ordering puts the read-model win (Phases 2–3) before the async migration precisely because it delivers the same user-visible improvement with far less risk.

**Alternative 3: "Scheduler only" (Phase 5 in isolation).**
Makes evaluations exist for most stocks, but leaves the latency, the request fan-out, the 404s, and all correctness bugs. Worse: with missing data (§4.14) and broken view grants (§4.15) still unfixed, the pipeline would compute into a schema whose reads are broken for 2 endpoints — Phase 0 must precede it regardless. And without applicability checks it would be the residual_income storm repeated for every symbol.

**Alternative 4: "Shared cache loader only."**
Cuts DB round-trips on the *compute* path but doesn't touch the *read* path — the page still fires 5 GETs + overview. The read model (C) is the read-side answer; the shared context loader (D) is the compute-side answer. Using the loader as a read-path optimization was v1's error — it optimized the wrong side.

**Alternative 5: "Frontend lazy-fetch only."**
Removes the 404 noise but leaves all server-side waste; computed methods still pay 5 GETs + overview re-read.

**Alternative 6: "One big god endpoint that rebuilds fundamentals per request" (v1's bundle without the read model).**
The design review's central objection: a bundle that re-fetches statements/ratios per request is a larger failure domain that only *moves* the duplication server-side. v2 answers this with C — the endpoint reads a compact projection, so consolidation happens without creating a single fragile "god endpoint."

**Verdict (design review §10.3):** the alternatives each fix one symptom; the proposal fixes the architecture that produces all 14 findings — but it is the **preferred target architecture if measurement confirms the need** for a persistent projection and background precomputation, not an unconditional mandate. A simpler design (lazy method queries + one SQL view for summaries + no physical projection + a thread-backed repository adapter) can be preferable at the current scale, with lower operational complexity and fewer consistency risks. Some phases may be simplified based on observed scale and query performance; the phases are independently shippable, so choosing the target architecture never forfeits the quick win of a simpler interim state.

### 6.6 Why this is professional-grade (engineering rationale, no external claims)

The design stands on its own engineering merits; it does not rely on "what Bloomberg/Robinhood/TradingView do" (those claims are not substantiated here and are unnecessary). The professional-grade properties are intrinsic:

- **Separation of read model from compute** (C vs D). The page reads a compact projection (SQL view/RPC over run history by default, physical table only if measured); computation happens once, off the request path. This is the classic CQRS-shaped split — a well-established systems pattern that decouples "how fast the page reads" from "how expensive computation is."
- **A page-oriented endpoint with per-section error isolation** (B). The page needs a *coherent valuation state*, not five independently-fetched resources; and that state must survive one method being broken. Partial success with `reasonCode`s is how production APIs report heterogeneous status.
- **An explicit state machine for computation** (D) — **two** state machines: published valuation state (`available/stale/not_applicable/not_computed/failed_without_previous_result`) and job state (`queued/running/succeeded/failed/cancelled/superseded/dead_lettered`). This separation enables **stale-while-revalidate** — a professional application continues showing the last known good valuation while a replacement is queued or computing, and preserves it if the refresh fails. Explicit job semantics (idempotency, dedup, single-flight, retries, dead-letter, supersession) is what distinguishes a pipeline from a cron script.
- **Transactional publication with an outbox** (D) — run insert + conditional current-state update + outbox event commit atomically (a DB function/RPC, since separate PostgREST calls are not one transaction); an outbox consumer drives recommendation regen, SSE, and cache invalidation. A conditional rule prevents superseded jobs from ever overwriting newer results.
- **Financial-data lineage, restatement handling, and auditability** (E) — `modelVersion` + `fundamentalsRevision` + `assumptionProfileVersion` + `marketDataAsOf` + `currency` + `calculationRunId` identify exactly which inputs produced a result; restatements invalidate dependent valuations while retaining prior calculations; user-triggered recomputations carry a durable audit trail (who, which profile, model version, input revision, result, failure reason, publication decision). Deterministic methods reproduce identical results for identical (model, input revision, profile) — tested.
- **Entitlements and authorization** (E) — scope is derived from authenticated identity + authorization rules, never client-supplied; enforcement covers summary reads, method details, historical runs, AI analysis, and SSE events.
- **Domain rules enforced by policy, not by serialization** (E). "Is Rule #1 meaningful for a negative-EPS company?" is a domain question answered by the Rule #1 service / applicability policy; the DTO only carries the answer. This separation — policy vs transport — is the difference between a model that degrades gracefully and one that lies with a `0`.
- **Freshness as first-class metadata** (`capturedAt`/`targetPeriodEnd`/`freshnessDays` from `capturedAt`), **errors as an architecture** (exceptions → central handlers → correlation IDs → metrics), and **AI as a lifecycle with its own status + deterministic fallback** — each is a standard production concern that v1 (and the current code) conflated or omitted.
- **Generated frontend types from the OpenAPI contract** instead of `as any` — the codebase already has response models; this makes payload mismatches compile-time errors rather than runtime bugs.
- **Verification discipline** — every phase ships with before/after numbers from the same Playwright + tracing harness, and latency targets are expressed as SLOs to verify (§6.7), not guarantees.

The v2.1 design fixes all 14 findings through 6 architectural components that each address one concern — no orphan patches, no god endpoints, no conflation of "optimize the read" with "optimize the compute."

### 6.7 Expected performance — SLOs to verify, not guaranteed outcomes

The v1 table promised "7.5s → <1s." That was overconfident: final latency also depends on Supabase/PostgREST latency, quote-provider latency, auth behavior, process startup and connection reuse, AI behavior, cache-hit ratio, frontend rendering, and network conditions. The targets below are **hypotheses to verify** with the Phase-1 tracing harness + the same Playwright scripts used in §2 — each phase ships a before/after measurement against these SLOs.

| Dimension | Today (measured) | Target SLO (to verify) | Mechanism |
|---|---|---|---|
| Critical-path API calls per page load | 11–12 | **2** (summary + quote); auth sync only on session events | §6.1-B summary endpoint; method details lazy |
| Summary endpoint latency (cached) | ~1.5s (5 GETs + overview) | **p95 < 500 ms** | §6.1-C one-query read model (view first) |
| Page shell interactive | ~7.5 s cold | **< 1 s** | request count × concurrency both reduced |
| Full valuation content (incl. lazy details) | N/A (all on critical path) | **p95 < 1.5 s** | details load on tab activation only |
| `not_computed` round-trips + 404s | 3–5 wasted GETs, 3× console errors | **0** | statuses arrive in summary payload |
| DB round-trips per load | ~19 (overlapping fetchers, no cache) | **~2** (read model + quote) | §6.1-C read model; fundamentals only on compute path |
| Event-loop blocking (sync `.execute()` on loop) | hypothesis (to confirm, §4.1) | **p95 lag < 50 ms under load** | §6.1-A async migration, measured at Phase 1 |
| Correctness bugs shipped | 4 ($0 value, −140 days, silent AI off, invisible errors) | **0** (policy + contract tests) | §6.1-E domain policy + typed contract |

**Operational SLOs** (design review §11.2 — beyond endpoint latency):

| Operational dimension | Target (to verify) |
|---|---|
| Valuation freshness | 95% of watchlist valuations republished within **30 minutes** of a material fundamentals revision |
| Scheduler backlog | p95 queued-to-started < **5 min**; backlog alert above threshold |
| Computation success rate | ≥ **98%** of eligible methods succeed; failures classified by reason |
| Stale-result percentage | < **5%** of page loads show `stale` for a previously-`available` method |
| Summary partial-failure rate | p95 of sections with `failed`/`reasonCode` per response < **1 section** |
| Quote age | p95 < **60 s** from source |
| AI generation backlog | recommendation regenerated within **10 min** of summary publication (or `pending` otherwise) |
| Data-ingestion → valuation publication delay | p95 < **30 min** after ingestion revision lands |

Verification protocol: re-run the §2 measurement scripts after every phase against these SLOs; treat any miss as a phase-blocking regression, not a "close enough."

---

## 7. What Was NOT Reviewed (future work)

- Actual **valuation math correctness** per method (DCF/DDM/OE/RI internals) — reviewed only orchestration and output shapes. A math-level review of each service (assumption defaults, terminal value, discount rates) is a separate pass.
- **Mobile (Flutter)** evaluation flow — no eval code found under `mobile/lib` (grep for `evaluat|fairValue|intrinsic` returned zero matches); the mobile app appears to delegate to the same backend.
- **`stocks/{symbol}/quote` internals** (yfinance freshness, fallbacks) — only timing observed (7.1s cold).
- Frontend **components** rendering each panel (dcf-panel, ddm-panel, etc.) — reviewed hooks/services, not every panel's inner JSX.

---

## 8. Evidence Files

- `.playwright-mcp/analysis-rblx-overview.png` — screenshot of the Overview tab (RBLX)
- Live captures during session: `docs/PREFETCH_DEBUG` console logs, network timing above
- Existing related docs (read for context, not re-measured): `web/docs/PERFORMANCE_ANALYSIS_WATCHLIST_TO_ANALYSIS.md` (1803 lines, prior analysis — this doc adds the live measurement + root-cause attribution), `web/docs/WATCHLIST_PERFORMANCE_ANALYSIS.md`
- **Migration baseline (cloud snapshot, 2026-08-02):** `backend/docs/migration_baseline/02_row_counts.json` (cloud row counts used for the §4.14 table), `backend/docs/migration_baseline/01_schema.json` (cloud schema — note `valuation_runs.run_by_user_id` is `text` in cloud vs `integer` in local DDL), `docs/migration_baseline/table_data/valuation_runs.json` (39 MB, 4,174 rows — intact and recoverable)
- **Migration scripts (read-only):** `backend/scripts/full_schema_migration.py` (phase3 `failed`-list mechanism; identity-column override map missing the valuation tables; phase5 grant step), `backend/scripts/restore_all_constraints.sql` L1073-1090 (local `valuation_runs` DDL — `run_by_user_id integer NULL` + FK to `users`), `backend/scripts/verify_migration.py` L1202 (structure-only verification — row counts "informational"), `backend/scripts/reset_and_refresh.py` + `cleanup_super_investors_db.py` (intentional `institutional_holdings` wipe), `backend/scripts/fix_grants.sql` (grants — never applied)
- **View-grant check (this session):** `pg_views` × `role_table_grants` — all 7 views (`portfolio_monthly_dividends`, `portfolio_user_import_history`, `super_investor_current_holdings`, `v_dcf_valuations`, `v_ddm_valuations`, `v_owner_earnings_valuations`, `v_residual_income_valuations`) have **no SELECT grant**; service-role reads reproduced `42501 permission denied` for the 2 views used by live endpoints
- **Live local-DB measurements (this session):** local `valuation_runs` count = 58, ID min=1 / max=58 (sequence restarted), all rows post-migration (08-05 residual_income ×55, 08-13 RBLX rule1+dcf, 08-15 SIRI rule1); `companies` = 3,122 (matches cloud), `income_statements` = 3,265 (matches), `financial_ratios` = 3,193 (matches); all 194 dump companies + `user_id=1` present locally (no FK-skip explanation)

---

## 9. Fact-Check Appendix (every finding re-verified, 2026-08-15)

Each finding in §4 was re-checked against live code and/or the local database. Status: **VERIFIED** = original claim accurate; **ADJUSTED** = claim was substantially right but a detail was corrected (inline in §4); **CORRECTED** = mechanism/attribution was wrong and the §4 text now states the verified truth.

| § | Claim | Evidence re-checked | Status |
|---|---|---|---|
| 4.1 | Sync client in async handlers + single worker | `database.py` uses `create_client`+`SyncClientOptions` (sync); `start.sh:144-148` runs uvicorn with `--reload`, **no `--workers`**; 96 `async def` handlers in `api/`; `supabase==2.28.3` — `create_async_client` imports OK in venv; exactly **98** `.execute()` calls in `valuation_repository.py`. Note (design review §2.1): blocking-call serialization is a **strong hypothesis** — wall-clock timing is consistent but not dispositive; server-side instrumentation is the definitive test (now Phase 1) | ✅ VERIFIED (claim softened in §4.1 to "hypothesis, instrumentation required") |
| 4.2 | 11–12 requests/load; `users/sync` per auth event | `prefetchAllValuations` fires **8** prefetches (5 valuations + magic-formula + canslim + risk); `useValuationOverview` fires 5 method queries + overview; `usePredictiveTabPrefetch` confirmed (uses `requestIdleCallback`); `users/sync` **single call site** `auth-provider.tsx:221` (`onAuthStateChange`) — fires per auth event, not per page; settings page re-syncs on demand | ✅ VERIFIED (users/sync mechanism ADJUSTED in §4.2: single call site, auth-event-driven) |
| 4.3 | Overview re-reads the 5 snapshots | `valuation_service.py:201-203` `get_last_output_snapshots([...5 methods])` + company context + price inside `get_valuation_overview`; frontend `useValuationOverview.ts:146-204` issues 5 separate `useQuery` + 1 recQ | ✅ VERIFIED |
| 4.4 | `not_computed` methods still cost full GET + 404 | `useValuationOverview.ts` fires all 5 queries regardless of computed state; backend 404s on never-computed; `rule1QueryFn` maps 404 → `{notComputed:true}` (round-trip still paid) | ✅ VERIFIED |
| 4.5 | RBLX `stickerPrice: 0` shown as computed | DB: RBLX `trailing_eps = -1.5671` (snapshot 07-27) — matches measured `eps0`; `rule1_service.py:357-358` `future_eps = eps0_safe*(1+g)^n if eps0_safe>0 else 0.0` → 0; growth clamped 2% min (`R1-GCLAMP-LOW` L310-314, DB forecast `-0.02`); `R1-NEGEPS` flag exists (L242-246) but does **not** change `computed` status | ✅ VERIFIED |
| 4.6 | Negative freshness `epsForecast: -140` | `rule1_service.py:269-270` `(now_utc().date() - rep_date).days` where `rep_date` = `earnings_forecast.report_date` — a **future** fiscal-period end (RBLX newest = 2026-12-31). 2026-08-13 − 2026-12-31 = **−140** exactly. Not a parse bug — wrong reference date (target period end vs capture time) | 🔶 CORRECTED (was "likely parse bug"; now verified future-date mechanism) |
| 4.7 | AI recommendation null without key | `ai_service.py:144-145` — `OPEN_ROUTER_KEY` unset → `logger.info` + `return None` | ✅ VERIFIED |
| 4.8 | Broad `except Exception` hides failures | Every handler in `valuations.py` wraps in `except Exception → 500 "…failed"`; history endpoints return `{"items": []}` on any exception (`valuations.py:150-152`) | ✅ VERIFIED |
| 4.9 | Extraction duplicated ×3 | `valuation_service.py:212-236` (`_extract`); `useValuationOverview.ts:79-118` (`extractFromSnapshot`/`extractRule1`); inline per-method spreads L207-270 — field names differ (`stickerPrice` vs `intrinsicValue` vs `intrinsicValuePerShare`) | ✅ VERIFIED |
| 4.10 | `methods[]` rebuilt every render | `useValuationOverview.ts:207-270` — no `useMemo`; Rule1 upside recomputed post-hoc L272-276 | ✅ VERIFIED |
| 4.11 | 3× 404 console errors per load | Direct consequence of §4.4 (ddm/oe/ri 404s); reproduced in live sweep (§2.3) | ✅ VERIFIED |
| 4.12 | No periodic valuation scheduler | `scheduler_worker.py:234` **does** register a `valuation_computation` handler, but `ValuationComputationScheduler` has **no `plan()` method** (only `compute_all`/`compute_batch`) → cannot be planner-registered; **no `planner.register` for valuation**; **nothing enqueues `valuation_computation` jobs** (grep: no `enqueue_job("valuation_computation",…)` anywhere); only trigger = `watchlist_service.py:996-1003` direct `compute_all(force=False)` on watchlist-add | 🔶 ADJUSTED (was "no valuation/job step at all"; truth: handler exists but no planner wiring / no enqueue) |
| 4.13 | Shared tables re-read per method; snapshots re-read on read | **Compute path:** 5 fetchers at exact lines (`get_ddm_dependency_values` L947, `get_rule1_dependency_values` L1021, `get_dcf_dependency_values` L1132, `get_oe_dependency_values` L1195, `get_ri_dependency_values` L1273); `financial_ratios` at L248/L329/L389/L458; `income_statements` L239/L371/L431; `valuation_method_defaults`+`company_valuation_overrides` in every fetcher. **Read path (round-2 verification):** all 5 cached GETs use `get_cached()` (e.g. `rule1_service.py:530-547`) which reads **only** `get_company_context` + `get_last_output_snapshot` — pure snapshot reads; the 5 dependency fetchers are called **only from compute** (24 call sites in the `compute_*` methods). Round-1's "page-load reads shared tables multiple times" was overstated; §4.13 text now states the verified split (compute overlap vs read-path snapshot re-read) | ✅ VERIFIED (mechanism refined in round 2: read path is pure snapshot reads; fetchers are compute-only) |
| 4.14 | Migration dropped ~99% of valuation history | Full 58-table compare (`migration_compare_result.txt`): **34 OK + 13 NEW + 10 LOST + 1 ERR = 58**; 10 lost tables exactly as listed; local `valuation_run_id` 1–58 (restarted); all 58 rows post-migration; all 194 FK targets present; `run_by_user_id` = `text` (cloud) vs `integer` (local `restore_all_constraints.sql`) | ✅ VERIFIED |
| 4.15 | Views have no SELECT grants; 2 endpoints 500 | `pg_views` × `role_table_grants`: 7 views, no SELECT; `portfolio_repository.py:639/658` (`portfolio_monthly_dividends`) + `:1036` (`portfolio_user_import_history`); `portfolio.py:1174` calls `get_monthly_dividends` → 500 "Failed to get dividends"; service-role reads → `42501 permission denied` (reproduced) | ✅ VERIFIED |
| §5 | Rate limit risk, prefetch beyond 5 valuations, SSE churn, `as any` casts | `overview` GET = `30/min`; `prefetchAllValuations.ts:96-111` also prefetches magic/canslim/risk; `GlobalSSEProvider.tsx:177-191` invalidates method key + overview on every `valuation_ready`; `as any` casts at `useAnalysis.ts:68-70` + overview extractors | ✅ VERIFIED (stock-card hover attribution ADJUSTED — it's `<Link prefetch={true}>` L47, not a custom handler) |

**Net effect of the fact-check:** 15 of 17 findings verified exactly as written. Two claims corrected in place: §4.6 (mechanism: future-dated forecast `report_date`, not a date-parse bug) and §4.12 (a valuation handler exists but is not planner-wired — which *lowers* the Phase-5 effort since `ValuationComputationScheduler.compute_all` already exists). No finding was disproven; the data-loss (§4.14) and view-grant (§4.15) claims were re-confirmed against the live database. Design review (2026-08-15) added one refinement to §4.1: the serialization mechanism is a strong *hypothesis* to be confirmed by server-side instrumentation (Phase 1), not a proven root cause from wall-clock timing alone. **Round-2 verification (2026-08-15):** the §4.13 read-path mechanism was refined — all 5 cached GETs (`get_cached()`, e.g. `rule1_service.py:530-547`) are **pure snapshot reads** (`get_company_context` + `get_last_output_snapshot` only); the 5 dependency fetchers are called **only from compute** (24 call sites in the `compute_*` methods). Round-1's "page-load reads shared tables multiple times" was overstated; §4.13 text now states the verified split (compute-path overlap vs read-path snapshot re-read).

---

## 10. Review-Response Matrix (design review → v2/v2.1 changes, 2026-08-15)

How each design-review point was addressed. **Round 1 (rows 1.1–10)** mapped to v2; **Round 2 (rows 11.1–14.14 below)** mapped to v2.1. Two rounds of review were incorporated — §6 is titled v2.1 accordingly:

| Review § | Review point | v2 change |
|---|---|---|
| 1.1 | Keep GET/POST/worker separation | Retained — read via summary endpoint, recompute via POST, proactive via pipeline |
| 1.2 | Consolidated summary endpoint appropriate | Retained, refined to page-oriented `GET /analysis/{symbol}/valuation-summary` (§6.1-B) |
| 1.3 | Scheduler necessary | Retained, upgraded to a full job pipeline (§6.1-D) |
| 1.4 | Canonical contract valuable | Retained as transport contract; applicability/freshness/error/AI are now separate concerns (§6.1-E) |
| 2.1 | Serialization evidence not conclusive | §4.1 reframed as hypothesis; Phase 1 = instrumentation (event-loop lag, spans, `.execute()` timing, controlled sync-vs-to_thread-vs-async test) before any migration |
| 2.2 | Request count is symptom, not root defect | §4.2 + §6.7 reframed: focus on blocking execution, duplicate reads, eager loading, expensive critical-path endpoints, 404s, failure isolation |
| 2.3 | "7.5s → <1s" overconfident | §6.7 rewritten as SLOs to verify (`p95 < 500 ms` summary, `< 1 s` shell, **2** critical-path calls), with operational SLOs (freshness, backlog, success rate, stale %, partial-failure, quote age, AI backlog) + verification protocol per phase |
| 2.4 | Bloomberg/Robinhood/TradingView claims unsupported | Removed entirely; §6.6 now cites only intrinsic engineering rationale (CQRS-shaped split, state machines, policy-vs-transport, error architecture) |
| 3.1 | Bundle must not absorb `users/sync` | Removed from endpoint; `users/sync` stays an idempotent session concern, deduped per session (§6.1-B) |
| 3.2 | Live quote should stay separate | Split out to own channel; summary endpoint does not determine quote load (§6.1-B) |
| 3.3 | Single endpoint → larger failure domain | Per-section error isolation mandatory; partial success with `reasonCode`s; one broken method never 500s the bundle (§6.1-B, example payload §3.3 of review) |
| 3.4 | Summary vs detail endpoints | Method details moved to per-method endpoints, fetched on tab activation; summary stays compact (§6.1-B) |
| 4 | Shared fundamentals loader misplaced (read path) | Corrected: read path reads the read model (view/RPC over `valuation_runs` first, physical projection only if measured) (C); fundamentals loader lives in the compute worker (D) (§6.1-C/D) |
| 5.1 | Workers = mitigation, not root-cause fix | §6.1-A now labels `--workers N` an emergency mitigation; staged async migration is the end state |
| 5.2 | `to_thread` is a legitimate staged strategy | §6.1-A staged path: repository boundary → bounded thread-pool adapter → measure → async client per group → remove adapter; invariant: no unpredictable sync/async mixing inside one repo |
| 5.3 | Process-local TTL cache risky across workers | Phase 6 uses version-keyed invalidation + shared store (or explicit version strategy); cache keys include `scope_id`; request-scoped dedup default (§6.3) |
| 6.1 | Applicability pre-check before compute | Added to §6.1-D: DDM→dividend, Rule #1→positive EPS, RI→book value/ROE, OE→cash-flow history; ineligible → `not_applicable` + `reasonCode`, never executed; **candidate policies labeled for model-owner review, versioned (`policyVersion`), with `inputRevision`** (review §9, §6.1-D) |
| 6.2 | Unit of work must be explicit | Computation identity `(company_id, method, model_version, fundamentals_revision, assumption_profile_hash, currency)` (content-addressed, shareable across users); **scope discriminator `scope_type: global | user | assumption_profile` with `scope_id` null only for global**, auth-derived never client-chosen, assumption profiles versioned/snapshotted (§6.1-D) |
| 6.3 | Production job semantics | **Two state machines separated** (review §3): published state (`available/stale/not_applicable/not_computed/failed_without_previous_result`) vs job state (`queued/running/succeeded/failed/cancelled/superseded/dead_lettered`) → stale-while-revalidate; idempotency keys, dedup, single-flight, retries/backoff, dead-letter, rate limits, dependency freshness, model-version invalidation, supersession, **transactional publication (insert run + conditional current update + outbox event in one DB function/RPC, outbox consumer drives regen/SSE/cache)** (review §5), metrics (§6.1-D) |
| 6.4 | AI must be precomputed/cached, not per-page LLM | Recommendation lifecycle with own status (`disabled\|pending\|available\|failed\|stale`), cached by snapshot version, regenerated on summary change, page succeeds without AI; **deterministic non-AI fallback** serves a rule-based summary when AI is disabled (review §12); metadata includes provider/model/promptVersion/disclaimerVersion (§6.1-E, Phase 6) |
| 7.1 | `$0` is a domain-validation issue, not DTO | Applicability is a domain policy in the Rule #1 service; DTO only carries it; `computation succeeded ≠ applicable ≠ publishable` (§6.1-E) |
| 7.2 | Clamping freshness hides the error | `capturedAt`/`targetPeriodEnd` as distinct fields; freshness from `capturedAt`; clamp is last-resort defense only (§6.1-E) |
| 7.3 | Structured errors need an error architecture | Domain exceptions → repo translation → central FastAPI handlers → correlation IDs → structured logs → metrics; `error_code` rides on top; route-level `except Exception` removed (§6.1-E) |
| 7.4 | `aiEnabled` surfaces config, doesn't fix feature | Three outcomes separated: fix silent failure (status field) vs enable feature (config) vs move off critical path (precompute, Phase 6) |
| 8.1 | Phase 0 needs safer recovery | Staging DB, backup-first, type transforms, ID preservation, 58-vs-4,174 reconciliation + conflict policy, sequence reset, FK/orphan validation, counts+checksums, sample verification, reviewed promote script, rollback artifacts (§6.3 Phase 0) |
| 8.2 | Old outputs shouldn't auto-become current | Historical runs restore as history; promoted to `current` only if model version + provenance valid, else `stale` + queued recompute (§6.3 Phase 0) |
| 8.3 | Grants → least privilege | Verify `security_invoker`/RLS-through-view; `service_role`-only default; no blanket `anon`/`authenticated` grants until deliberate review (§6.3 Phase 0, §6.4) |
| 9 | Revised architecture (read model, read/compute split) | Adopted as §6.1-C/D; endpoint contract matches review §9.1; read-model projection matches review §9.2; computation path matches review §9.3 |
| 10 | Better rollout order | Adopted verbatim: 0 recovery → 1 instrument/mitigate → 2 contract+read model+summary → 3 frontend switch → 4 async migration → 5 pipeline → 6 AI+cache (§6.3) |

**Round 2 (v2 → v2.1):**

| Review § | Review point | v2.1 change |
|---|---|---|
| 3 | Separate published state from job state | §6.1-D split into two state machines (published: `available/stale/not_applicable/not_computed/failed_without_previous_result`; job: `queued/running/succeeded/failed/cancelled/superseded/dead_lettered`) → stale-while-revalidate with `refresh` block in the summary payload (§6.1-D, §6.6) |
| 4 | Read model conditional — view/RPC first, physical projection only after measurement | §6.1-C restaged: Stage 1 = SQL view/function over `valuation_runs` (no new table); Stage 2 = physical `valuation_method_current` **only if measured** (§6.1-C, §6.3 Phase 2) |
| 5 | Transactional publication + outbox | §6.1-D: run insert + conditional current-state update + outbox event commit atomically via a DB function/RPC; outbox consumer drives recommendation regen, SSE, cache invalidation; conditional rule prevents superseded jobs overwriting newer results (§6.1-D, §6.6) |
| 6 | Scope model precision | `scope_type: global | user | assumption_profile` + `scope_id` (null only for global); auth-derived never client-chosen; assumption profiles versioned/snapshotted; computation identity content-addressed `(company_id, method, model_version, fundamentals_revision, assumption_profile_hash, currency)` (§6.1-D) |
| 8 | Reference price/timestamp for upside | DTO carries `referencePrice` + `referencePriceAsOf`; UI labels intrinsic-value-as-of vs current-quote upside; display-only recompute allowed, never re-deriving applicability/intrinsic value (§6.1-E) |
| 9 | Applicability as candidate rules pending math review | Checks relabeled "candidate policies for model-owner review" (valuation math was out of scope); versioned `policyVersion` + `inputRevision` recorded per result (§6.1-D) |
| 10.3 | Remove "strict subset" overclaim | §6.5 verdict rewritten: target architecture is **preferred if measurement confirms** the need; simpler design (lazy queries + view + thread adapter) preferable at current scale (§6.5, exec summary) |
| 11 | Request target 2, not 3; auth sync not per-navigation | §6.1-B, §6.7: 2 requests/load (summary + quote); `users/sync` deduped per session, only on session events; not counted as per-page traffic |
| 11.2 | Lineage, restatement, auditability, freshness SLOs | §6.1-E: `modelVersion` + `fundamentalsRevision` + `assumptionProfileVersion` + `marketDataAsOf` + `currency` + `calculationRunId`; restatement rules (detect → invalidate → retain → mark superseded); audit trail for user-triggered recomputes; entitlement enforcement across all read paths. §6.7: operational SLO table (freshness 30-min republish, backlog, success ≥98%, stale <5%, partial-failure <1 section, quote age, AI backlog, ingestion→publication delay) (§6.1-E, §6.7) |
| 12 | Deterministic AI fallback | §6.1-E: rule-based summary served from published numbers when AI disabled — "DCF indicates 12% upside. Rule #1 is not applicable…"; AI metadata includes provider/model/promptVersion/disclaimerVersion; feature useful without an LLM provider (§6.1-E, §6.3 Phase 6) |
| 14.11 | Request target (see §11) | 2 requests/load everywhere (§6.1-B, §6.3 Phase 3, §6.7) |
| 14.12 | Remove "THE ONE definitive solution" language | §6 title → "THE Definitive Solution (v2.1…)"; exec summary → "Proposed target architecture (preferred, not mandated)"; §6.5 verdict conditional |
| 14.13 | Freshness/operational SLOs (see §11.2) | Added to §6.7 as a dedicated operational-SLO table |
| 14.14 | Deterministic AI fallback (see §12) | Applied in §6.1-E + Phase 6 |

*Prepared by Sisyphus (code review + live browser instrumentation). No code was modified.*
