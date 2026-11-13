# Delisting / Stale-Price Lifecycle — Design Brief

Status: **design locked, not yet implemented.** This document is the executable brief.

Adopted model: professional reference-data instrument lifecycle (Bloomberg/FactSet/MSCI
class). These are domain priors, not sources verified in-repo — treat as strong priors.

## Why

A holding whose last quote froze keeps being forward-filled into every snapshot
forever, so portfolio value silently drifts. Measured on 2026-09-28 (real data, no
mocking) across 118 held companies / 6 accounts:

| Age | Symbol | Last price | Exposure | Status |
|---|---|---|---|---|
| 1278d | PSYK | 2023-03-30 | 716.88 | unclassified |
| 1127d | HYLD | 2023-08-28 | 1274.50 | unclassified |
| 647d | NYCB | 2024-12-20 | 90.50 | known delisted |
| 396d | WBA | 2025-08-28 | 431.28 | known delisted |
| 241d | CMA | 2026-01-30 | 709.36 | known delisted |

- Known-delisted exposure: **1,231.14**
- Total on >90d-old prices: **3,222.52** (~5.9% of holdings value)
- 113 of 118 held companies priced within 30d — a small, bounded tail, not systemic.

## Root cause (verified in source)

`backend/shared/snapshot_builder.py`

1. **Unbounded forward-fill.** `_resolve_holding_price` (:255) calls
   `resolve_price_forward_filled` with **no age bound**. Any prior price qualifies.
2. **Tier identity used as staleness proxy.** `TIER_QUALITY_MAP` (:126) maps
   `FORWARD_FILL -> "STALE_PRICE"`. The flag reports *which tier won*, not price age.
3. **Threshold defeated by callers.** `scripts/step9_rebuild_all_snapshots.py:221`
   passes `stale_threshold_days=0`, which makes Tier 1 require an exact same-day price,
   so Tier 1 never fires and **every** holding is labelled `STALE_PRICE`. The
   diagnostic meant to catch this class of problem is itself miscalibrated.
4. **No lifecycle state.** No terminal concept exists; nothing distinguishes
   "no recent quote" from "this instrument no longer exists".
5. **Valuation never consults the delisting list.** `get_effective_skipped_symbols()`
   has exactly two callers: `refresh_all_prices`, `run_backfill`.

## Locked design

### Lifecycle states

```
ACTIVE | SUSPENDED
TERMINAL_ACQUIRED | TERMINAL_REDEEMED | TERMINAL_RENAMED
TERMINAL_DELISTED | TERMINAL_BANKRUPT | TERMINAL_LIQUIDATED
```

Each terminal state carries a **known** value or an explicit absence of one.
`TERMINAL_DELISTED` has no terminal value by definition (see SOLO below) and must
not be treated as a payout.

### Terminal events

A new event type, posted deliberately — never inferred by a heuristic:

```
instrument_terminated {
  company_id,
  outcome,              # one of the TERMINAL_* states
  effective_date,
  terminal_value,       # null for DELISTED/BANKRUPT-without-known-recovery
  currency,
  replacement_company_id # for RENAMED / stock-consideration mergers
}
```

The replay engine closes the position, or converts it (cash or replacement
security), and adjusts cost basis and net deposits accordingly.

### Staleness handling (retain-and-disclose, with a deadline)

| Age | Status | Treatment |
|---|---|---|
| <= soft threshold | `PRICED` | in `total_value` |
| soft -> hard horizon | `STALE` | **retained** in `total_value`; `stale_value` disclosed |
| > hard horizon | `UNPRICED_LAST_KNOWN` | leaves `holdings_market_value`; reported as count + last-known value |
| terminal event posted | closes/converts | at the known value |

The two thresholds are **config**, never literals. The gap between them is the
"retain while we try to establish a value" window — in a fund this is enforced by a
pricing committee; here it must be mechanical because no committee exists. Dropping
the hard horizon is not professional practice, it is a simplified version of it,
and the simplification is what is currently broken.

A transient provider outage is measured in days and never triggers a value change.

### Quality derived from age, not tier

Add `price_age_days` to the audit dict. Derive `valuation_status` from age
independently of which tier supplied the price. Stop using tier identity as a
staleness proxy. Fix `stale_threshold_days=0` in `step9`.

### Delisting fast-path (read-only)

`_resolve_holding_price` consults `get_effective_skipped_symbols()`. Known-dead ->
unpriced regardless of age. **Never** auto-extends the list: a data outage must not
permanently poison a human-curated set.

### Surface it

Snapshots gain `stale_value`, `unpriced_value_at_last_known`, `pricing_coverage_pct`,
`unpriced_count`. `total_value` keeps its current meaning (retain-and-disclose).

**Non-negotiable:** the disclosure must be *rendered* in the portfolio UI. A stored
field nobody reads is decoration, not disclosure. A visible unpriced-position
indicator on the portfolio value is in scope, not a follow-up. An aggregate total
masks a small phantom component regardless of adjacent fields.

### Retained permanently

Price history for dead instruments is never deleted — cost basis, lots, performance
and audit all depend on it.

## Confirmed terminal event

`SOLO` (company_id 3138) — **TERMINAL_DELISTED**, effective **2026-07-08**.
NYSE removal, Rule 17 CFR 240.12d2-2(b), exchange-initiated, failure to meet
continued-listing standards. Source: SEC Form 25-NSE, accession
`0000876661-26-000606`. **No terminal value** — no merger consideration exists.

**Open discrepancy:** that filing identifies the security as **SBDS** (Solo Brands,
CIK 1870600). Holdings carry `SOLO`. Verify which entity `company_id` 3138 is
before posting a terminal event against it.

## Open research (7 tickers, per-ticker, primary sources)

`ZSAN` `FIRE` `NYCB` `WBA` `CMA` `PSYK` `HYLD`

No sourced finding yet. A single combined query returns law-firm solicitation spam,
not evidence. Use SEC EDGAR (25-NSE, 8-K, Form 15) and, for PSYK/HYLD, fund-sponsor
liquidation or closure notices.

PSYK and HYLD carry the largest combined exposure (1,991.38) and are frozen since
2023 — plausibly wound down or liquidated, meaning a real distribution or recovery
may be postable.

Their outcomes determine whether the schema also needs `TERMINAL_LIQUIDATED` and a
`RECOVERY` valuation path. **Do the research before finalising the schema.**

## Scope

`L3` / impact `cross_component` / `public_api_change: true` / `data_change: true`.

Touches: `snapshot_builder.build_snapshot_row` (**59 callers**), `replay_engine`
(consumes `PriceTier` + `TIER_QUALITY_MAP`), the event schema and replay handlers,
reconciliation invariants, portfolio API and UI.

Must not break: `tests/test_price_lookahead_guard.py` (locks Tier 1 age-bound
semantics — keep them), `test_cdr_pricing.py`, `test_fx_conversion.py`, portfolio
performance tests, and the `reconcile_snapshots` CDR-ratio-audit and
net-deposit-monotonicity invariants.

## E2E test requirement

Real local Supabase (`localhost:54321`). **No mocking.** Assert value invariants,
not field presence:

1. A `TERMINAL_DELISTED` holding leaves `holdings_market_value` but retains
   `cost_basis`.
2. `pricing_coverage_pct` moves by exactly the expected amount when a holding
   crosses the hard horizon.
3. CDR ratio audit still holds on every priced CDR row.
4. Net deposits stay monotonic across the rebuild.
5. Terminal event with a `terminal_value` closes the position at that value and
   adjusts net deposits correctly.
6. Regression: the 113 healthy positions (<30d) are unchanged by this work.

The 8 frozen positions are the fixtures. `SOLO` is the worked `TERMINAL_DELISTED` case.

## Known blocker — resolved

`update_price_refresh_marker` previously failed with `permission denied for table
cdr_ratio_registry` (Postgres `42501`). Price rows still wrote; refresh markers did
not.

**Resolution:** migration `010_cdr_ratio_provenance_guard.sql` now includes
`GRANT SELECT ON public.cdr_ratio_registry TO service_role` (the grant every other
migration in the repo already declared), and the grant was applied to the live
local Supabase. Refresh markers now write correctly.

## Implementation order

1. ~~Resolve the `cdr_ratio_registry` grant.~~ Done (migration 010 + live DB).
2. Per-ticker research for the 7 unresolved symbols; confirm the `SOLO`/`SBDS` identity.
3. Architecture pass on the event schema and the two thresholds.
4. Implement: lifecycle states, bounded forward-fill, age-derived quality, fast-path,
   snapshot reporting fields, UI indicator, terminal event handling.
5. E2E against real local Supabase, no mocking.
6. Remediate the 8 existing positions by posting real terminal events.
