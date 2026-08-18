# Valuation Overhaul — E2E Test Report

**Date:** 2026-08-16
**Scope:** Full Playwright regression across all spec files, both viewport projects (`chromium` 1280x720, `chromium-mobile` 375x812).
**Baseline (2026-08-15):** 328 passed / 2 failed / 2 skipped — 2 pre-existing E2E failures blocked the E2E gate.
**Result (2026-08-16):** **331 passed / 1 skipped / 0 failed** — E2E gate GREEN. The single skip is E2E-07's conditional `test.skip(true, 'Need at least 2 stocks for this test')` (by design).

---

## 1. Valuation Overhaul Gate Spec (VAL-01 … VAL-12)

`web/e2e/valuation-overhaul.spec.ts` maps 1:1 to ledger gates 3, 4, 5, 6. **All 12 tests pass on both projects.**

| Test | Gate | Asserts | Result |
|---|---|---|---|
| VAL-01 | 3 (§4.2) | Exactly 1 `valuation-summary` + 1 `quote` per fresh nav | 🟢 |
| VAL-02 | 3 (§4.4, §4.11) | 0 legacy per-method GETs (`/valuations/{rule1,dcf,ddm,owner_earnings,residual_income}`), 0 `/overview` | 🟢 |
| VAL-03 | 3 (§4.4, §4.11) | 0 console 404s, 0 page errors on load | 🟢 |
| VAL-04 | 3 | `users/sync` ≤ 1 per fresh nav (not per-navigation) | 🟢 |
| VAL-05 | 3 (§4.2) | Total `/api/` requests < 10 (baseline was 15) | 🟢 |
| VAL-06 | 5 (§4.3, §4.8) | All 5 methods served in ONE summary payload; direct endpoint 200 | 🟢 |
| VAL-07 | 5 (§4.5) | RBLX rule1 = `not_applicable` / `NEGATIVE_EPS`, `intrinsicValue: null` | 🟢 |
| VAL-08 | 5 (§4.6) | `freshnessDays >= 0` for every method (no −140 leak) | 🟢 |
| VAL-09 | 5 (§4.8) | Unknown symbol → 404 (not blanket 500) | 🟢 |
| VAL-10 | 6 (§4.7) | Deterministic card visible; "AI Summary" count = 0; consensus text present | 🟢 |
| VAL-11 | 6 (§4.7) | `recommendation` never silent-null; deterministic text + `PROVIDER_NOT_CONFIGURED` when disabled | 🟢 |
| VAL-12 | 4 (§4.1) | `v_valuation_latest_runs` traced with `on_loop_count === 0`; event-loop lag p95 < 50 ms | 🟢 |

---

## 2. Pre-Existing E2E Failures Fixed This Session

The full regression at session start was 328 passed / **2 failed** / 2 skipped. Both failures were timing flakes in `web/e2e/portfolio-overview.spec.ts`. Fixing them surfaced a shared root-cause class — **dropped clicks inside horizontally-scrollable strips** (hit-test vs React re-render race) — which also affected a third test that had been intermittently passing.

### 2.1 PD-E2E-15 — one-shot chart render check (chromium only)
- **Symptom:** One-shot `isChartRendered()` check ran before the lazy-loaded Recharts tree mounted (5s hydration window).
- **Fix:** Replaced with `expect.poll` waiting up to 15s for chart rendered OR `[class*="recharts"]` elements > 0. Removed the conditional chart-skip guard (this also accounts for the skip count dropping 2 → 1).

### 2.2 PD-E2E-20 — 500 ms fixed sleep before one-shot URL assert (mobile only)
- **Symptom:** `waitForTimeout(500)` then one-shot URL assert raced async `router.replace` in `usePortfolioNavigation`.
- **Fix:** `expect.poll(() => page.url(), { timeout: 5000 }).toMatch(/account=\d+/)`.

### 2.3 PD-E2E-04 — dropped Overview tab click (root cause)
- **Symptom:** `toHaveURL` already polls 5 s but URL stayed at `?tab=holdings` — the click itself never registered (test passed in isolation @ 23.9 s → intermittent). The TabBar strip is `overflow-x-auto`; a re-render can swallow the click's hit-test.
- **Fix:** `switchTab` helper (helpers.ts) now wraps `tab.click()` + `toHaveURL(new RegExp('tab=' + tabLabel.toLowerCase()), { timeout: 3000 })` inside `expect(async () => {...}).toPass({ timeout: 15000 })` — retry-click until the URL actually changes. Removed the `waitForTimeout(500)` / `waitForTimeout(300)` sleeps.

### 2.4 PD-E2E-06 / PD-E2E-07 / PD-E2E-08 — same dropped-click race on chips
- **Symptom:** Same class of race on watchlist chip clicks (chip strip is `.scrollbar-none`, horizontally scrollable).
- **Fix:** Applied the same `toPass` retry-click pattern: chip `click()` + `expect.poll` (3000 ms inner timeout) inside `.toPass({ timeout: 15000 })`.

### 2.5 Verification of the flake fixes
- `portfolio-overview.spec.ts` re-run: **44/44 green** (both projects) after all fixes.

---

## 3. Full Regression Evidence

Command: `npx playwright test --reporter=line --workers=1` (0 retries, both projects).

```
332 tests finished
331 passed, 1 skipped, 0 failed
Finished in 20.7m
```

- **1 skipped:** E2E-07 (conditional skip: watchlist has < 2 stocks — by design).
- All 44 portfolio-overview tests, all 12 VAL gate tests, all 14 portfolio-all-tabs tests, all 72 stock-analysis tests, all watchlist-dashboard/e2e-flow/loading-screen/race-conditions/sse-adaptivity tests: **green on both projects**.

---

## 4. Conclusion

The E2E gate ("all of the above re-verified in one full regression run") is **GREEN**. All phase gates 0a, 0b, 1, 2, 3, 4, 5, 6, and E2E now pass, completing the definition of done for the valuation overhaul.
