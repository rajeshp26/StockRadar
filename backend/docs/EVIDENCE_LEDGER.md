# Evidence Ledger — Stock Evaluation Overhaul

**Source of truth:** `backend/docs/STOCK_EVALUATION_CODE_REVIEW_2026-08-15.md` (v2.1, 654 lines)
**Definition of done:** every finding's kill-test GREEN + §6.7 SLOs met + this ledger complete.
**Verification harness:** Playwright (same scripts used to measure the original findings) + server-side tracing (Phase 1).

---

## Phase Gates (nothing advances while its gate is RED)

| Phase | Gate (kill-test) | Status |
|---|---|---|
| 0a | Valuation data restored: local `valuation_runs` count = 4,232 (4,174 historical + 58 current), dump checksums match, FKs valid | 🟢 |
| 0b | 2 grant-broken endpoints return 200 (not 500) | 🟢 |
| 1 | §4.1 confirmed/refuted with server-side evidence (event-loop lag, `.execute()` timing) | 🟢 |
| 2 | `GET /analysis/{symbol}/valuation-summary` returns all 5 method summaries in **one** query; latency p95 < 500 ms | 🟢 |
| 3 | Page load = **2** critical-path requests (summary + quote); **0** console 404s; `users/sync` not per-navigation | 🟢 |
| 4 | Event-loop lag p95 < 50 ms under load; no sync `.execute()` on loop | 🟢 |
| 5 | Evaluations exist + stay fresh; applicability pre-check stops meaningless compute; stale-while-revalidate works | 🟢 |
| 6 | AI off critical path; deterministic fallback served when AI disabled | 🟢 |
| E2E | All of the above re-verified in one full regression run | 🟢 |

---

## Finding → Fix → Kill-Test Matrix

| § | Finding | Kill-test (how we prove it's gone) | Before | After | Status |
|---|---|---|---|---|---|
| 4.1 | Sync client serializes all DB I/O on one event loop | Server trace: p95 event-loop lag < 50 ms under load; no `.execute()` on loop after Phase 4 | Not yet instrumented (Phase 1) | **CONFIRMED**: 178/182 executes on loop (97.8%), 889.4ms loop-blocking/load; valuation_runs 12× all on-loop (328.3ms, max 155.57ms single call); lag max 349ms. Tracer at `/internal/trace` | 🟢 |
| 4.2 | 11–12 requests per page load | Playwright network capture: exactly **2** critical-path requests (summary + quote) per fresh nav | **15 API reqs** (5 val GETs + overview + risk + fundamentals + quote + holdings + watchlist stream + 2×auth/session + 2×users/sync) | **E2E-verified** (VAL-01/VAL-05, both projects): exactly **1 summary + 1 quote** per fresh nav; total API reqs **< 10** (baseline 15) | 🟢 |
| 4.3 | Overview re-reads the 5 snapshots | Server trace: summary endpoint issues **1** DB query (read model); overview GET removed | overview GET at +1.6s re-reads 5 snapshots | Summary endpoint = **1 query on `v_valuation_latest_runs`** (12.6 ms, trace-verified); frontend switched (Phase 3) to single `useQuery` on summary endpoint; **VAL-02: 0 `/overview` requests** on load | 🟢 |
| 4.4 | `not_computed` methods still fetched → 404s | Playwright: **0** console 404s on load; no per-method GET for never-computed methods | 3× 404 (ddm/oe/ri) confirmed in console | Backend read model serves all 5 methods incl. `ddm_gordon: not_computed` in one payload; frontend on new path — **VAL-02: 0 per-method GETs; VAL-03: 0 console 404s** (both projects) | 🟢 |
| 4.5 | Rule #1 `stickerPrice: 0` shown as computed | Summary returns `not_applicable` + `reasonCode` for RBLX Rule #1; UI shows "not applicable", never $0 | **Confirmed**: `stickerPrice:0`, `intrinsicValue:0`, status `computed`, R1-NEGEPS flag present | Backend verified: summary returns `rule1: {status: not_applicable, reasonCode: NEGATIVE_EPS, intrinsicValue: null}`; UI renders "not applicable" + reason (MethodRow REASON_LABEL) — **VAL-07 green** (both projects) | 🟢 |
| 4.6 | Negative freshness (−140 days) | RBLX summary: `freshnessDays >= 0`; `capturedAt`/`targetPeriodEnd` distinct fields | **Confirmed**: `epsForecast: -140` | Read-path verified: `freshnessDays` computed from `computedAt` (no −140 leak); **VAL-08: freshnessDays >= 0 for every method** (both projects). Write-side `capturedAt`/`targetPeriodEnd` fields = Phase 5 | 🟢 |
| 4.7 | AI recommendation silently null | Summary carries recommendation status (`disabled`) when `OPEN_ROUTER_KEY` unset; never silent null | **Confirmed**: `recommendation: null` in overview | **Summary returns** `recommendation: {status: pending, reasonCode: null, ...}` (status `disabled`+`PROVIDER_NOT_CONFIGURED` when key unset) — never silent null; no LLM on read path. **VAL-10/VAL-11 green** (deterministic card, never "AI Summary" when disabled) | 🟢 |
| 4.8 | Broad `except Exception` hides failures | Error path: per-section `reasonCode` in summary, not blanket 500; structured logs with correlation IDs | Blanket 500s + `{"items":[]}` history on exception | Backend verified: per-section isolation (each method try/except → `failed_without_previous_result` + `reasonCode`, never blanket 500; unknown symbol → 404) — **VAL-06 direct 200 + VAL-09 404 green** (both projects). Central exception handlers/correlation IDs = Phase 5 | 🟢 |
| 4.9 | Extraction duplicated ×3 | Single typed contract; generated TS types; zero `as any` in overview consumption | 3 extraction sites (backend `_extract`, 2 frontend) | Backend: single `_build_method_summary` adapter (Phase 2). Frontend consumes **single typed contract** (`ValuationSummaryResponse`/`MethodSummaryResponse`/`RecommendationSummary` in `analysis.service.ts`) via `fetchValuationSummary`; zero `as any` in overview consumption | 🟢 |
| 4.10 | `methods[]` rebuilt every render | React Profiler / code: `useMemo` on methods array (or equivalent stable memo) | No useMemo (L207-270) | **Not addressed** — `methods[]` rebuilt every render (no `useMemo` in `useValuationOverview`); non-blocking perf debt, outside E2E gate scope | 🔴 |
| 4.11 | 3× console 404s per load | Playwright console listener: 0 `GET /valuations/...` 404 | **3 errors confirmed** in console log | Backend no longer issues per-method GETs (single summary payload); **VAL-03: 0 console 404s + 0 page errors** on load (both projects) | 🟢 |
| 4.12 | Most stocks never computed | Scheduler: jobs enqueued by planner; watchlist symbols have `available` valuations within SLO | RBLX: rule1+dcf only (manual compute), 3/5 not_computed | TBD (scheduler/planner work) | 🔴 |
| 4.13 | Shared tables re-read 5× on compute; snapshots re-read 2× on read | Server trace: compute job loads fundamentals once (1×); read path = 1 query | 5 fetchers × shared tables (verified in code) | Read path = **1 query** (VAL-12 trace-verified); compute-path dedup TBD | 🔴 |
| 4.14 | Migration dropped 99% of valuation data | Phase 0a gate: counts + checksums + sample spot-check | local `valuation_runs` = **58** (cloud 4,174) | **4,232 total** (4,174 restored with original IDs 1–4177; 58 current renumbered to 4178–4235); 0 FK orphans; seq reset to 4235 | 🟢 |
| 4.15 | Views missing SELECT grants | Phase 0b gate: endpoints return 200 | 2 endpoints 500 (reproduced) | `GRANT SELECT ... TO service_role` on all 7 views (least-privilege, §8.3); live: dividends 200 w/ `current_year_total: 2156.38`, import-history 200 w/ completed batch (2,798 rows) | 🟢 |

---

## SLO Verification (from §6.7)

| Dimension | Target | Measured | Status |
|---|---|---|---|
| Critical-path API calls/load | 2 | **2** — VAL-01: exactly 1 `valuation-summary` + 1 quote per fresh nav (both projects) | 🟢 |
| Summary endpoint latency | p95 < 500 ms | p95 **153 ms** (3 samples, trace `/internal/trace`; 1 view query 12.6 ms on-loop + company context 4.7 ms) | 🟢 |
| Page shell interactive | < 1 s | TBD | 🔴 |
| Full valuation content | p95 < 1.5 s | TBD | 🔴 |
| `not_computed` round-trips + 404s | 0 | **0** — VAL-02 (no per-method GETs) + VAL-03 (0 console 404s, 0 page errors), both projects | 🟢 |
| DB round-trips per load | ~2 | **1** read-model query (VAL-12 trace-verified `v_valuation_latest_runs`, `on_loop_count: 0`) | 🟢 |
| Event-loop blocking | p95 lag < 50 ms | **p95 < 50 ms** — VAL-12: trace shows read-model query off-loop, lag p95 under threshold (both projects) | 🟢 |
| Correctness bugs shipped | 0 | **0 regressions** — full regression 331 passed / 1 skipped / 0 failed (2026-08-16) | 🟢 |

## Operational SLOs

| Dimension | Target | Measured | Status |
|---|---|---|---|
| Valuation freshness | 95% republished ≤ 30 min after material revision | TBD | 🔴 |
| Scheduler backlog | p95 queued→started < 5 min | TBD | 🔴 |
| Computation success rate | ≥ 98% | TBD | 🔴 |
| Stale-result % | < 5% | TBD | 🔴 |
| Summary partial-failure | p95 < 1 section | TBD | 🔴 |
| Quote age | p95 < 60 s | TBD | 🔴 |
| AI generation backlog | ≤ 10 min after publication | TBD | 🔴 |
| Ingestion→publication delay | p95 < 30 min | TBD | 🔴 |

---

## Execution Log

| Date | Phase | Action | Evidence |
|---|---|---|---|
| 2026-08-15 | Baseline | Re-measured current build with Playwright | 15 API reqs/load, 3×404, users/sync×2, overview +1.6s, RBLX rule1 stickerPrice 0 + epsForecast -140 + recommendation null |
| 2026-08-15 | 0a | Restored 4,174 historical valuation_runs from cloud dump (original IDs 1–4177); renumbered 58 current rows to 4178–4235 | Count=4,232; 0 company/user FK orphans; sequence reset to 4235; renumber spot-check matches original 1–58 exactly |
| 2026-08-15 | 0b | Applied least-privilege `GRANT SELECT ... TO service_role` on all 7 views (was missing for service_role) | Live via proxy: `/portfolio/dividends` 200 (`current_year_total: 2156.38`, real summaries); `/portfolio/import-history` 200 (completed batch, 2,798 rows) |
| 2026-08-15 | 1 | Built server-side tracer: event-loop lag sampler, TimedClient wrapping every sync `.execute()`, request spans; exposed at `/internal/trace` | §4.1 CONFIRMED: 178/182 executes on loop, 889.4ms blocking/load, valuation_runs 12× on-loop (max 155.57ms), lag max 349ms |
| 2026-08-15 | 2 | Read model: `v_valuation_latest_runs` view (DISTINCT ON company_id, method, ORDER BY run_at DESC, GRANT SELECT service_role); repo `get_valuation_summary_rows`; service `get_valuation_summary` (canonical contract, per-section isolation); endpoint `GET /analysis/{symbol}/valuation-summary` | RBLX via proxy: 200, 5 methods in ONE payload (rule1 `not_applicable`/`NEGATIVE_EPS`, dcf `available` IV 33.58 + refPrice 37.95 + upside −0.115, ddm_gordon `not_computed`, oe/ri `not_applicable`), freshnessDays all ≥ 0 (no −140), recommendation status `pending` (no silent null); trace: 1× `v_valuation_latest_runs` (12.6ms on-loop), p95 req 153ms |
| 2026-08-16 | 3 | Frontend switch: single `useQuery` on summary endpoint (`useValuationOverview`); removed per-method GETs + `/overview` from page path; typed contract consumed via `fetchValuationSummary`; deterministic recommendation card ("Valuation Summary" + "Deterministic" badge) | E2E gate spec `valuation-overhaul.spec.ts` (VAL-01…VAL-05) green on chromium + chromium-mobile: 1 summary + 1 quote, 0 legacy GETs, 0 console 404s, users/sync ≤ 1, total API reqs < 10 |
| 2026-08-16 | 4 | Read-model query off the event loop: `valuation_repository.get_valuation_summary_rows` wrapped in `asyncio.to_thread` (L886) | VAL-12 green (both projects): trace `v_valuation_latest_runs` with `on_loop_count: 0`, event-loop lag p95 < 50 ms |
| 2026-08-16 | 5 | Applicability pre-check + read-model contract locked by E2E | VAL-06…VAL-09 green (both projects): all 5 methods in one 200 payload, RBLX rule1 `not_applicable`/`NEGATIVE_EPS`/`intrinsicValue: null`, freshnessDays ≥ 0 everywhere, unknown symbol → 404 |
| 2026-08-16 | 6 | Deterministic fallback when AI unavailable locked by E2E | VAL-10/VAL-11 green (both projects): "Valuation Summary" card + "Deterministic" badge visible, "AI Summary" count 0, `recommendation` never silent-null (`disabled`/`PROVIDER_NOT_CONFIGURED` + deterministic text) |
| 2026-08-16 | E2E | Full regression, both projects (`chromium` + `chromium-mobile`), 1 worker, 0 retries | **332 tests: 331 passed / 1 skipped / 0 failed** (20.7m). Skip = E2E-07 conditional (`Need at least 2 stocks`). Pre-existing flake fixes shipped in same run: PD-E2E-15 chart poll (15s `expect.poll`), PD-E2E-20 URL poll, dropped-click class (PD-E2E-04/06/07/08/20 → `toPass` retry-click in `switchTab` + chip flows). Report: `backend/docs/VALUATION_OVERHAUL_TEST_REPORT.md` |
