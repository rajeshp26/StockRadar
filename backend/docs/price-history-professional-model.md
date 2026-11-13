# Price History — Professional Data Model (raw OHLC + adjustment factor)

Status: LOCKED (implementation in progress)
Date: 2026-09-30
Owner: implementation (main agent)
Supersedes: "close_price is adjusted-as-if-raw" convention (unrecorded, inferred
from scheduler/providers). Fixes Gap 3 of
`backend/docs/PERFORMANCE_BUG_ANALYSIS_AND_REDESIGN.md` (corporate actions underspecified)
and the recorded intent `backend/docs/PORTFOLIO_PERFORMANCE_REENGINEERING.md:1651`
("verify price_history.close_price reflects split-adjusted closes").

## Problem (measured)

`price_history.close_price` is a scale hybrid. Each row froze the scale yfinance
served on the day it was written; yfinance restates its whole series on every new
split and on provider-side corrections, but old DB rows are never rewritten. Result:
a single column holding multiple incommensurate scales per company, e.g. TNXP rows
spanning 1,459,200,000.0000 (2016-08-31) to 9.745 (2026-09-30), GIS legacy rows at
the adjusted scale while recent rows sit at the raw scale, and a
`portfolio_repository` 5x-within-60-days "unit normalization" heuristic that exists
only to seam those discontinuities at read time.

Evidence: `backend/scripts/probe_price_scale.py` / `probe_price_scale2.py`
(canonical venv, live yfinance + local DB):

| symbol | stored/raw | stored/yf_adj | conclusion |
| --- | --- | --- | --- |
| TNXP (cid 3112, 729 rows) | 1.0000 all dates | 1.0000 | raw scale, matches provider raw |
| NFLX (cid 424, 6127 rows) | 1.0000 all dates | 1.0000 | raw scale, matches provider raw |
| GIS (cid 62, 11514 rows) | 0.4294–0.5647 | 1.0000 | legacy rows at adjusted scale |

Additional findings:
- `auto_adjust=True` is a no-op for TNXP/NFLX (provider Adj Close == Close) but
  differs for GIS → the provider flag is not a reliable adjustment source.
- yfinance raw `Close` is Yahoo's split-restated series (no discontinuity at
  NFLX 2025-11-17 10:1 / GIS 1999-11-09 2:1 in the raw column) — provider "raw"
  is not as-traded for deep history, only recent rows approximate it. This is the
  pivot of the whole design: "the provider serves" and "true raw" are different
  quantities, and the write path must convert between them.
- `splits` calendar is the only consistent adjustment authority. Probe 2 confirms
  it is also sufficient: recovery direction verified on real data, and the one
  suspect factor (GIS 1995-05-30 `'10000:8265'`) is provider-canonical (D8).

Probe 2 — `backend/scripts/probe_factor_direction.py` (canonical venv, live
yfinance + DefeatBeta + local DB), decisive on direction and scale:

| witness | served (provider raw) | true raw (as-traded) | Π(parse(to/from) over later splits) |
| --- | --- | --- | --- |
| NFLX 2015-07-14 | 10.0371 | **702.60** (1112.17 on 2025-11-14 ×10) | 70 (7:1 × 10:1) |
| GIS 2010-06-01 | 36.00 | **72.00** (stored legacy 20.33 = dividend scale, ratio 0.5647) | 2 (2:1) |
| TNXP 2025-01-27 | 41.00 | **0.41** (0.15 → 14.98 across 1:100) | 0.01 (1:100) |
| GIS 1995-05-22 | 12.37 | **59.88** | 4.83969 (2:1 × 2:1 × 10000:8265) |

- Recovery formula proven in both directions: `true_raw = served × Π(parse(s))`
  for splits `s.report_date > d`; `served = true_raw × Π(1/parse(s))`.
- DefeatBeta fallback serves the SAME restated scale as yfinance (ratio exactly
  1.0000 across 11 NFLX rows, `fetch_price_history`) → one uniform recovery
  formula on the write path regardless of `data_source`. No production Stooq
  path exists (`stooq` appears only in `scripts/compare_stored_vs_provider.py`).
- GIS 1995 `'10000:8265'` (≈1.2099213551119177) exists verbatim in Yahoo's own
  split history; `only-in-owned` and `only-in-provider` diffs are empty →
  provider-canonical restated distribution, NOT an import artifact. Keep it.

## Target model (matches Bloomberg/FactSet/S&P convention)

1. `price_history` stores **true raw (as-traded)** OHLC — NOT the value the
   provider serves. Both yfinance (`auto_adjust=False`) and DefeatBeta serve
   Yahoo's split-restated series; true raw is RECOVERED at write time from the
   owned `splits` calendar:
   `raw(d) = served(d) × Π(parse_split_factor(s)) for all s.report_date > d`
   (parse returns to/from: `3:1 → 3.0`, `1:100 → 0.01`).
   Recovered raw fits the existing `numeric(16,4)` columns (max ≈ 1e12). The old
   `upsert_price_history` clamp constant 99,999,999.9999 sits below even the
   served restated series for heavy reverse-split names (TNXP 2016 served
   1.4592e9) and is a latent bug; it is raised to the real column capacity.
2. New column `adjustment_factor numeric(20,15)` — the multiplier converting this
   row's true raw close to the current share-count scale. Direction is the
   RECIPROCAL of parse (a 3:1 split halves historical prices, so the price-side
   factor is 1/3, not 3):
   `factor(d) = Π(1/parse_split_factor(s)) for all s.report_date > d` (= Π(from/to)).
   `adj(d) = raw(d) × factor(d)`.
3. New column `adj_close numeric(16,4)` — materialized adjusted close. By
   construction `adj_close = raw × factor = served` (telescoping:
   served × Π(to/from) × Π(from/to) = served), so adj_close is the provider's
   continuous current-scale series. Readers stay simple; factor retained for
   auditability, matching professional price-with-adjustment-factor storage.
4. Splits calendar stays the single adjustment authority (it already powers the
   replay engine on the quantity side and `reconcile_split_events` — professional).
5. Invariant (no double counting): replay engine adjusts SHARES across splits;
   valuation multiplies `adj_close(d)` × shares at d. With
   `shares(d) = shares_orig × Π share-factors(≤d)` and
   `adj_close(d) = raw(d) × Π price-factors(>d)`, the product is constant across
   d — same value regardless of which date's scale the snapshot uses.
   **CORRECTED 2026-10-18 — this invariant is FALSE as implemented and the
   valuation read is `close_price`, not `adj_close`. It holds only if `shares(d)`
   is carried on the current (restated) share scale; the replay engine carries
   AS-TRADED quantities. See "Amendment 2026-10-18" at the end of this document.**
6. Plausibility gate evaluates on the **adjusted** scale: `adj_close` vs
   anchor × `MAX_PRICE_UP_RATIO` (default 100). Since adj_close == served == the
   continuous current-scale series, the comparison is scale-consistent with the
   anchor (tx unit price / current quote / latest adj close). Legitimate
   reverse-split rows pass on the adjusted scale: TNXP 2025-01-27 adj 41.00 vs
   anchor 9.745 = 4.2× < 100; NFLX 2015-07-14 adj 10.04 vs current quote ≈ 1100
   ≪ 100×. A row where Yahoo's own restated series is discontinuous (TNXP
   2016-08-31: true raw ≈ 2.28, but adj = 1.4592e9 vs anchor 9.745 = 1.5e8×) is
   REJECTED and flagged (`PRICE_PLAUSIBILITY_VIOLATION`) — it is portfolio-inert
   (residual-6) and outside every analysis window, so dropping it is correct.
7. Data reset: delete `price_history` rows per company and refetch raw through
   the fixed pipeline (scheduler/backfill), recomputing factor + adj_close at
   write. Delete-then-refetch is required: old rows sit on the old restated
   scale, new rows are recovered raw, and the conflict detector compares
   volumes values only; leaving old rows would also freeze the hybrid scale.
   Delisted names keep provider-served rows + calendar factor (DefeatBeta
   fallback where yfinance is empty — same restated scale, probed).
   `splits`, `dividend_history`, `current_market_data`, snapshots untouched.

## Decisions (locked)

- D1: Provider change = `auto_adjust=False` only. Hold the served value, then
  RECOVER true raw from the owned `splits` calendar at write (`served ×
  Π(to/from over later splits)`); materialize factor (Π(from/to)) + adj_close.
  Adjusted series is computed from the owned `splits` calendar, never from
  provider Adj Close (unreliable across names; mixed with dividends in Yahoo's
  column).
- D2: `adj_close` and `adjustment_factor` are write-time materialized, not
  read-time computed (one choke point, no per-read split lookup).
- D3: Write ordering: splits must exist in DB **before** price upsert computes
  factors. Scheduler currently fetches price (line 572) then splits (line 575) —
  must be reordered, or a new company gets factor=1 rows until next run.
- D4: `get_all_prices_historical` switches to `adj_close` and the 5x/60-day
  unit-normalization heuristic is **deleted** — its only purpose was to seam the
  hybrid scale, which D7 eliminates.
  **CORRECTED 2026-10-18: half-applied. The heuristic stays deleted; the read is
  `close_price` (as-traded), because D5's invariant is false — see
  "Amendment 2026-10-18".**
- D5: Gate/clamp: gate compares adjusted close; clamp raised to the real column
  capacity (~1e12) with a corrected comment.
- D6: API `PriceHistoryPoint` gains optional `adj_close` + `adjustment_factor`
  (additive; `close` stays raw). Frontend untouched (raw chart remains valid).
- D7: Transition reads use `COALESCE(adj_close, close_price)` while the refetch
  is in flight; readers flip to `adj_close` unconditionally after full-universe
  refetch completes. Snapshot jobs are held until refetch completes, then
  snapshots are revalidated — must be unchanged for consistent companies
  (D2 invariant).
  **CORRECTED 2026-10-18: the valuation read is `COALESCE(close_price, adj_close)`
  unconditionally. The "snapshots unchanged" check passed because both sides of
  the comparison were already on the served scale, so it could not detect the
  split double count — see "Amendment 2026-10-18".**
- D8: RESOLVED (probe 2) — the GIS 1995-05-30 `'10000:8265'` factor
  (1.2099213551119177) is provider-canonical: Yahoo's own split history contains
  the identical factor and no owned-vs-provider diff exists. It is a real
  (restated) distribution event, not an import artifact. No factor change; the
  record stands.

## Required code changes (in order)

1. Migration: add `adjustment_factor numeric(20,15) NULL`,
   `adj_close numeric(16,4) NULL` to `price_history`. (APPLIED. The inline
   SEMANTICS comment is directionally wrong — states Π(split_factor) but the
   factor is Π(1/parse) — corrected in place; no re-run needed.)
2. `yfinance_provider.get_price_history_df`: `auto_adjust=False`. (APPLIED.)
3. `financial_repository.upsert_price_history`: fetch per-company owned splits,
   recover true raw OHLC (`served × Π(to/from)`), compute factor
   (`Π(from/to)`, rounded to 15dp) + `adj_close` (round 4dp), gate on the
   adjusted scale, raise clamp to numeric(16,4) capacity (~1e12). Splits must
   already be in DB (D3) when this runs.
4. Scheduler + watchlist_service + backfill: upsert splits BEFORE price upsert.
5. `portfolio_repository.get_all_prices_historical`: read `close_price`
   (as-traded), delete heuristic. **CORRECTED 2026-10-18 (was: read adj_close);
   see "Amendment 2026-10-18".**
6. `analysis_repository` + `derived_financial_metrics_job`: adjusted scale where
   prices cross split boundaries (weekly/monthly readers).
7. API: additive adj_close/factor on PriceHistoryPoint.
8. Refetch orchestration script (delete rows → schedule raw fetch → verify
   density, gate pass, snapshot invariance).

## Verification

- Density integration test (`backend/tests/test_price_history_daily_density_integration.py`) green.
- Gate on the adjusted scale rejects only discontinuous-restatement rows
  (TNXP 2016 class); residual-6 rows pass/are flagged per anchor logic.
- Snapshots unchanged vs pre-change for consistent companies (invariant proof, real data).
- Full backend test suite green; G5 untouched (backend-only change).

### Recovery sources: do not substitute the 2026-08-31 cloud dump

Assessed 2026-10-01. `C:\Documents\db_cluster-31-08-2026@19-49-47.backup.gz` is a
valid `pg_dump`, but its `price_history` payload is **month-end sampled**, not daily:

| Company | id | Rows | Years | Rows/year | Typical gap |
| --- | --- | --- | --- | --- | --- |
| LEG | 899 | 569 | 47 | ~12 | 28-33 days |
| RMAX | 3162 | 123 | 14 | ~8-9 | 28-33 days |

Daily trading coverage is ~252 rows/year, so these series are ~4.7% (LEG) and ~3.7%
(RMAX) of expected density and **would fail
`test_price_history_daily_density_integration.py`** if restored as-is. It also uses the
legacy 9-column layout with no `adjustment_factor` / `adj_close`, so rows must be
re-derived through the canonical writer rather than copied in.

Consequences for anyone picking this up:

- The dump is evidence that a prior migration preserved a *subset* of history. It is
  not a rollback target and must not be described as a full backup.
- Restoring it would mask the open LEG/RMAX shortfall rather than resolve it, and would
  reintroduce the scale hybrid this document exists to eliminate.
- The only valid recovery inputs are a current Supabase project ref (the known ref
  `viqdqgxcumcdhqxooplw` is NXDOMAIN) or a genuine daily dump. See
  `backend/docs/SUPABASE_CLOUD_TO_LOCAL_MIGRATION.md` § "Price History Recovery Status".
- The refetch coverage guard in `backend/scripts/refetch_price_history.py` exists because
  a provider that returns sparse rows must never authorize destructive deletion; keep it
  enabled through any future recovery attempt.

## Amendment 2026-10-18 — valuation basis is the as-traded close

Status: APPLIED. Supersedes D4 (read choice), D5 (as an invariant), D7's second
sentence, target-model item 5, and required-change item 5. The stored data model
(items 1-3, D1-D3, D6, D8) is unchanged and stands.

### What was wrong

Item 5 claimed `adj_close(d) × shares(d)` is invariant across `d`. That is true
only when `shares(d)` is carried on the **current (restated) share scale**. The
replay engine carries **as-traded** quantities: it multiplies the share count by
the split factor at the split's effective date
(`backend/tests/test_replay_engine.py:1180-1186` — `(10+5)*3 = 45` for a 3:1).
It must: cost basis, sale proceeds and dividends are as-traded dollar amounts.

So the shipped pairing was as-traded shares × restated price, which double counts
every later split: a forward split deflates historical value by the cumulative
split ratio, a reverse split inflates it by the same ratio.

Measured on real rows (`price_history`, real DB):

| witness | date | `close_price` (as traded) | `adj_close` (restated) | factor |
| --- | --- | --- | --- | --- |
| AAPL | 2020-08-28 | 499.23 | 124.8075 | 0.25 (4:1 on 2020-08-31) |
| XELA | 2022-07-25 | 0.1455 | 582.0 | 4000 |
| XELA | 2022-07-26 | 1.85 | 370.0 | 200 |

XELA's factor is the owned calendar's product of two reverse splits: `1:20` on
2022-07-26 and `1:200` on 2023-05-15 (yfinance's calendar). The two witnesses
prove which column is as-traded: AAPL closed at **499.23** on 2020-08-28 as
traded, and `close_price` stores exactly that while `adj_close` stores the x0.25
restatement.

Consequence on real data — account 9, snapshot 2022-07-25:

- as-traded holding: 60 shares
- shipped value: `60 x 582 = 34,920 USD` (45,132.70 CAD) instead of
  `60 x 0.1455 = 8.73 USD` (11.28 CAD) — a 4000x overstatement
- account total 84,776.20 CAD vs 39,643.50 CAD for every other holding; the next
  day the 1:20 split divided the share count and XELA fell to 1,426.43 CAD

That artifact is the entire 2022-06-30 -> 2022-09-30 drop reported by
`backend/scripts/gate_chart_series_integrity.py`.

## Correction applied

- `PortfolioRepository.get_all_prices_historical` values on `close_price`
  (`COALESCE(close_price, adj_close)`). Legacy pre-refetch rows carry no
  `adj_close`, so their read is unchanged; refetched rows move from the restated
  to the as-traded scale.
- `adj_close` keeps its role everywhere it is a *single-security continuity*
  value, not a share-count pairing: the API chart (`api/stocks.py`), the
  plausibility gate's adjusted-scale comparison, `analysis_repository`
  (N/S ratios), `derived_financial_metrics_job`, and the live "latest close"
  fallback in `portfolio_service._get_current_price` (which restates a stale
  quote into today's share basis — the scale that matches today's holdings).
- Item 5 restated: `shares_current_basis(d) x adj_close(d)` is invariant. The
  shipped pairing is `as_traded_shares(d) x close_price(d)`.

Verification: `backend/tests/test_price_valuation_basis.py` — red before the
change (XELA yields 582.0 / AAPL yields 124.8075 / the split date shows a 4x
jump), green after.

## Residual, not addressed here

`portfolio_service._compute_performance_fallback` and `get_holding_performance`
build lots from transactions with no split events at all, so their quantity side
is stale after any split regardless of price basis. That is a quantity-side gap
(D4's `adj_close` read did not fix it and was not the cause of it).