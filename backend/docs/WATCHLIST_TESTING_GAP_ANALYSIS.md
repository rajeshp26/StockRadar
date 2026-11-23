# Why testing did not catch the watchlist listing defect

This is the durable answer to the user's question. It is not a claim that "tests were too few". The tests were green at the wrong level of abstraction.

## Short answer

The test suite proved CDR arithmetic and dialog presence. It never proved the end-to-end invariant that matters to the user: **the exchange selected in search becomes the identity of the watchlist row and of the quote used to price it**. Without that contract, every layer could satisfy its own local test while the selected exchange was discarded.

## The escape, in three parts

### 1. Architecture injected the defect

The search API already returned `exchange`, and the UI displayed it, but the add payload contained only `symbol` [VERIFIED: backend/api/watchlist_items.py:73-160]. The web client copied only `s.symbol` from the selected suggestion [VERIFIED: web/src/components/dashboard/add-stock-dialog.tsx:107-126], and both `StockSearchResult` and `AddStockInput` omitted security identity [VERIFIED: web/src/features/watchlists/services/watchlist.service.ts:12-25].

The contract gate was active, but there was no contract saying that quote identity is `security_id`. Context build and review therefore had nothing to compare against the persisted row. This is a containment miss (`context_build`, `review`, `gate_g1`), not a missing-gate routing failure. It is recorded as `SEC-MASTER-RETRO-01`.

### 2. Test design made the wrong thing observable

The CDR test class that looks most relevant is explicitly a formula check: "This is a logic test" [VERIFIED: backend/tests/test_cdr_pricing.py:283-297]. It divides `350.0 / 10.0` directly. It never calls `WatchlistService.add_stock_to_watchlist`, never inspects a watchlist row, and never checks which listing supplied a quote.

The API e2e test posts only `watchlist_id`, `symbol`, `target_buy`, and `target_sell` [VERIFIED: backend/tests/e2e/test_deep_sync.py:55-60]. It then recovers `company_id` by fallback lookup. So it encodes the exact symbol-only identity that caused the defect.

The browser add-dialog tests only assert that the dialog opens and that symbol/target fields are visible [VERIFIED: web/e2e/watchlist-dashboard.spec.ts:382-415]. They never select a search result with a specific exchange and never assert the resulting badge or price.

No data-invariant test existed for "one row per listing" because no listing table existed. No browser test existed for "selected exchange -> persisted identity -> rendered price". G6 was legitimately skipped in earlier runs under "no visible-behaviour requirement and no frontend source changed" [VERIFIED: .planning/phases/00-unphased/VERIFICATION.md:9563-9570]; when this work declares the visible_behaviour shape and changes frontend source, that route is no longer available.

This is recorded as `SEC-MASTER-RETRO-02`.

### 3. The three CDR rules were tested independently, never against each other

`shared/price_utils.py` used a unanimous-TOR rule, `watchlist_service` and the quote endpoint used an any-TOR rule, and ingestion wrote a company-global ratio. Each could be tested in isolation. What no test asserted was the cross-layer invariant: all consumers must derive CDR-ness from the same listing identity. That is why a uniform-CDR test could pass while a mixed direct/CDR account was mispriced [VERIFIED: .blk027_mechanism.json:5-6].

## What now prevents the same escape

Phase 1 plan AC-1 makes listing identity a contract field from search through add, quote, and SSE. AC-2 makes one-row-per-listing a data invariant. AC-3 values mixed lots with one kernel. AC-4 and AC-5 exercise both META listings through the real API and browser. AC-8 closes the chain through reload and SSE.

The retrospective entries `SEC-MASTER-RETRO-01` and `SEC-MASTER-RETRO-02` were amended with `fix_landed: true` and exact `fix_verified_by` commands after those commands ran green. The durable command outputs and exit codes are in `.planning/phases/01-security-master-watchlist-identity-and-isolated-reliability/VERIFICATION.md`; this document does not claim a fix by itself.

## Honest limits

- This analysis does not prove a fix has landed. The command outputs in the verification matrix do.
- The frozen 14-test black-box system suite provides real-stack proof on the seeded META pair (RED under a targeted kernel mutation, GREEN after restore). It does not cover every provider, exchange kind, or production load profile.
- The mobile symbol-only add path was fixed: `addStock` now posts `symbol` plus full `ListingIdentity` when supplied [VERIFIED: mobile/lib/core/services/watchlist_service.dart:20-34]. Dart static analysis remains **unverifiable** in this workspace because no Flutter SDK is installed; that is not recorded as a pass.
- Every applicable gate is green: `g8_blockers` now passes with no open blockers. BLK-028 was resolved by primary evidence, not by a code change. A real Wealthsimple export shows same-date META CDR dividends scaling with 20 vs 25 held CDR units (0.56/0.70, 0.55/0.69, …; ratio 1.25 = 25/20), proving `net_cash_amount` is the cash total for the lot rather than a per-share rate. The earlier blocker premise was wrong: 25 CDR units are not 25 underlying shares. No dividend code or test was changed. The human applied `plan-scope-web-repair.patch`; the plan was re-stamped (`ee42201c…`), the matrix re-emitted, all gates re-run against that matrix and re-bound: `g1`, `g2`, `g3`, `g4`, `g5`, `g6`, `g9`, `g17`, `g19` all exit 0 and the matrix closes 8/8. `g4_executable` is green after the fenced ratchet patch plus an agent-side fix for the WSL `.cmd`-shim execution in the non-fenced ratchet tool; BLK-028, BLK-031 and BLK-032 are resolved. The exact patches and copy-paste commands are in the phase `handoff/HANDOFF.md`. `g6_browser` and `g17_system_tests`, the two gates explicitly required for the visible behaviour, are green.
