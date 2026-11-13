# Portfolio Valuation Architecture — Target Design

> **Status:** Proposed target architecture. Design-only; no implementation in this document.
> **Scope:** Portfolio valuation (positions, CDR pricing, FX, point-in-time snapshots) for the
> web Overview card and the performance chart.
> **Relationship to existing docs — read, do not replace:**
> - `backend/docs/CDR_PRICING_BUG_ANALYSIS_AND_REDESIGN.md` — the 13 CDR bugs and Phase 1–3 sketch.
>   This document is the **architecture** the Phase 3 there ("Multi-Instrument Security Master")
>   implies, extended to cover the live/overview path.
> - `backend/docs/EVENT_SOURCING_CQRS_DESIGN.md` — the event store + read-model direction this builds on.
> - `backend/docs/FX_CURRENCY_CONVERSION_DESIGN.md` — "convert at the edge" and the FX contract.
> - `backend/docs/PORTFOLIO_DESIGN.md` — current layered design and schema.
> - `framework/architecture_rules.yaml` — declared boundaries (G3).

---

## 1. Problem statement

The Overview "Total Value" card and the performance chart disagree for the same account on the
same day. On 2026-10-08 the chart reaches **145,052.53** while the card reads lower; the gap is
dominated by **holdings valuation**, not cash, and the largest single contributor is CDR
(depositary-receipt) holdings priced on two different rules.

**The two rules (verified in code):**

- Snapshot path — `backend/shared/snapshot_builder.py:195-216` (`_apply_cdr`): a CDR price from a
  US source is `price / cdr_ratio`, then `× fx_rate` when `price_source == "price_history"`.
- Overview path — `backend/application/services/portfolio_service.py:546-555` (`_enrich_holdings`):
  `effective_price = current_price / cdr_ratio`, then `price_currency = "CAD"` with **no USD→CAD
  conversion**.

**The repo's own tests declare the snapshot rule correct:**
`backend/tests/test_cdr_pricing.py:84-107` (Bug 2) and `:352-365` (Bug 12) assert
`CDR_price = (US_price / ratio) × FX`. So the **Overview card understates every CDR holding by the
FX factor** (~1.40×) because it never applies the USD→CAD conversion — the `/ratio` half of the
CDR fix reached both paths (commit `22942cc4`, Jul 10) but the `×FX` half reached only the snapshot
(commit `91db98e6`, Jul 20). The Overview was left behind.

Independently, both paths read a **conflated upstream**: `current_market_data` is one row per
`company_id`, overwritten by whichever instrument ran last (probe: MSFT `530.97 → 36.44` between
runs; META `38.19`, NFLX `26.79`, PYPL `3.91` — none a valid US or CDR price). This is the
documented "Bug 2" CDR/US conflation (`backend/docs/CDR_PRICING_BUG_ANALYSIS_AND_REDESIGN.md`).

**Conclusion:** the bug is not a formula bug. It is an **architecture** defect: the same economic
quantity is computed by multiple independent code paths over conflated reference data.

---

## 2. Root cause: duplicated valuation over conflated identity

CDR adjustment / valuation logic is scattered across at least nine decision points:

| # | Location | Role |
|---|---|---|
| 1 | `shared/snapshot_builder.py` `_resolve_holding_price` / `_apply_cdr` | snapshot valuation |
| 2 | `application/services/portfolio_service.py` `_enrich_holdings` | live overview valuation |
| 3 | `api/portfolio.py` `apply_cdr_adjustment` (`:138`, called `:282/:526/:833/:908`) | 4 API read endpoints |
| 4 | `application/services/watchlist_service.py` | watchlist |
| 5 | `shared/price_utils.py` | price normalization |
| 6 | `shared/replay_engine.py` | event replay |
| 7 | `services/event_projection_handler.py` | projection |
| 8 | SSE broadcast | live streaming |
| 9 | stock quote endpoint | per-symbol quote |

The repo already recognised the pattern in `shared/cdr_utils.py:1-18`: *"single source of truth for
CDR classification … so the signal can never drift between layers the way it did in the original
bug."* Classification was unified. **Valuation was not.** That is the remaining gap.

Two structural faults cause the drift:

- **F1 — No single valuation implementation.** Nine copies of "divide (and maybe convert) a CDR
  price"; any rule change must be applied nine times, and `91db98e6` proves it won't be.
- **F2 — Conflated instrument identity.** `companies` holds the US issuer (`currency='USD'`,
  `exchange='NMS'`), while the CDR instrument exists only as a per-holding string cache
  (`portfolio_holdings.exchange_override = 'TOR'`). One `current_market_data` row serves both, so
  the US quote and the CDR quote overwrite each other.

---

## 3. Design principles (aligned to this repo)

1. **Transactions/events are canonical; everything else is a projection.** Stated in
   `shared/cdr_utils.py:10-17` and `backend/docs/EVENT_SOURCING_CQRS_DESIGN.md`. A cache must never
   overrule the truth it caches (`snapshot_builder.py:430-434`).
2. **One valuation kernel.** A single pure function computes account-currency value from
   (instrument, as-of date, quote source, FX rate). Every consumer calls it. No second copy.
3. **Point-in-time.** Valuation for date *D* uses only information available at *D*. Enforced today
   by the future-date guard (`snapshot_builder.py:383-392`); made systematic by the kernel.
4. **Convert at the edge, once.** `backend/docs/FX_CURRENCY_CONVERSION_DESIGN.md:155`. FX enters only in
   the kernel.
5. **Distinguish issuer from security.** An issuer (Microsoft) can have many securities (MSFT.NMS,
   MSFT.TOR CDR). Identity, ratio, currency, and exchange live on the security.
6. **Derive, don't cache-and-trust.** Instrument facts are materialised from transactions by an
   idempotent projection (reuse `cdr_utils`), not hand-maintained.
7. **Prove equivalence, not intent.** A read model is correct only if recomputation equals the
   persisted snapshot (Section 9). This is the property whose absence caused the defect.

---

## 4. Options considered

### Option A — Minimal patch (make the Overview match the snapshot)
Add the `× FX` step to `_enrich_holdings`. **Cost:** ~1 file. **Fixes:** the visible card
disagreement. **Leaves:** all nine duplicate implementations, the conflated `current_market_data`,
and no equivalence guarantee — the next rule change re-introduces drift. **Verdict:** necessary as
Phase 0, insufficient as a design.

### Option B — Shared valuation kernel, current schema
Extract one kernel and repoint all nine consumers; keep `companies` + `exchange_override` for now.
**Cost:** moderate. **Fixes:** F1 (single rule). **Leaves:** F2 (quotes still keyed by `company_id`,
pollution persists). **Verdict:** the correct **near-term** step.

### Option C — Security master + CQRS consolidation (recommended end-state)
Option B **plus** an instrument model (`securities`) and a re-keyed quote store, so a CDR and its
underlying are distinct entities with distinct quotes. This is `CDR_PRICING_BUG_ANALYSIS_AND_REDESIGN.md`
Phase 3 ("professional grade") and the read-model consolidation in
`EVENT_SOURCING_CQRS_DESIGN.md`. **Cost:** highest, staged. **Fixes:** F1 + F2 + point-in-time
equivalence. **Verdict:** the target. Adopt via the phased plan in Section 8.

**Recommendation:** A → B → C, one phase at a time, each independently shippable and reversible.
Do not attempt C as a big-bang cutover.

---

## 5. Target architecture (end-state)

```
                           WRITE SIDE (canonical)
  CSV / manual ──► parser ──► portfolio_events (append-only)  + portfolio_transactions
                                        │
                                        │  idempotent projections
                                        ▼
                       ┌───────────────────────────────────────────┐
                       │  portfolio_holdings (position projection)  │
                       │  securities / instruments (NEW, derived)   │
                       └───────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
        ┌───────────────────────┐               ┌───────────────────────────┐
        │  VALUATION KERNEL     │               │  QUOTE STORE (NEW)         │
        │  domain/valuation.py  │◄─────────────►│  quotes(security_id,       │
        │  value_security(...)  │               │         as_of, price, ccy, │
        │  · CDR ratio          │               │         source)            │
        │  · FX once            │               └───────────────────────────┘
        │  · tier + audit       │               ┌───────────────────────────┐
        └───────────┬───────────┘◄─────────────►│  FX rate series            │
                    │                            └───────────────────────────┘
                    │  SAME function, different as-of
        ┌───────────┴───────────────────────────────────────────┐
        ▼                                                         ▼
  Overview (as_of = now)                          Snapshot job (as_of = D)
        │                                                         │
        └──────────────► portfolio_snapshots (read model) ◄───────┘
                                  │
                     Overview card + performance chart
```

### 5.1 Write model
Unchanged: `portfolio_events` + `portfolio_transactions` are canonical
(`EVENT_SOURCING_CQRS_DESIGN.md`). Holdings remain a projection. No new write path.

### 5.2 Instrument model — the core fix

```sql
CREATE TABLE public.securities (
  security_id            BIGSERIAL PRIMARY KEY,
  company_id             INTEGER NOT NULL REFERENCES companies(company_id),
  kind                   TEXT NOT NULL CHECK (kind IN ('COMMON','CDR','PREF','OTHER')),
  symbol                 TEXT NOT NULL,          -- as traded (MSFT.NMS, MSFT.TOR)
  exchange               TEXT NOT NULL,          -- NMS, TOR
  currency               TEXT NOT NULL,          -- native quote currency
  underlying_security_id BIGINT  REFERENCES securities(security_id),  -- CDR -> US listing
  cdr_ratio              NUMERIC,
  cdr_ratio_source       TEXT,
  cdr_ratio_date         DATE,
  UNIQUE (company_id, kind, exchange)
);
```

- A US listing and its CDR become **two `securities` rows** sharing one issuer.
- `cdr_ratio` moves from `companies` (shared by issuer) to the CDR security.
- `portfolio_holdings` gains `security_id`; `exchange_override` becomes a **derived
  compatibility view** over `securities.kind`, never an input (mirrors `cdr_utils.py:16-17`).
- **Materialisation** is an idempotent projection that reuses `cdr_utils.matches_cdr_name` /
  `is_cdr_transaction` over `portfolio_transactions.security_name` + `raw_data`. Deterministic,
  rebuildable, auditable — consistent with rule 1.

### 5.3 Quote store

```sql
CREATE TABLE public.quotes (
  security_id BIGINT NOT NULL REFERENCES securities(security_id),
  as_of       TIMESTAMPTZ NOT NULL,
  price       NUMERIC NOT NULL,
  currency    TEXT NOT NULL,
  source      TEXT NOT NULL,
  PRIMARY KEY (security_id, as_of)
);
```

Re-keying from `company_id` to `security_id` means a CDR quote and its underlying's quote can never
overwrite each other. `price_ingestion_job.py` writes to `(security_id, as_of)`; `current_market_data`
is retired or becomes a compatibility view. `price_history` (US series) migrates under the US
security; the CDR series uses the CDR security.

### 5.4 Valuation kernel (the single implementation)

New `backend/domain/valuation.py` (domain layer, per `framework/architecture_rules.yaml` layer
order — no I/O, pure):

```python
@dataclass(frozen=True)
class Valuation:
    unit_price_account_ccy: Decimal
    raw_price: Decimal
    raw_price_ccy: str
    price_source: str            # 'current' | 'price_history' | 'yfinance_tor' | 'cost_basis' | 'unavailable'
    price_date: date | None
    tier: PriceTier
    cdr_ratio_applied: Decimal | None
    fx_rate_applied: Decimal | None
    audit: dict

def value_security(security, as_of, account_currency, quotes, history, fx) -> Valuation:
    """Single source of truth for one security's value in account currency."""
```

Rules (exactly the repo's declared contract, now in one place):

1. **Tier resolution** (unchanged order): as-of quote → history forward-fill → cost basis →
   unavailable (`snapshot_builder._resolve_holding_price` semantics).
2. **Non-CDR:** `value = raw × fx(raw.currency → account_currency, as_of)`.
3. **CDR:** `value = raw / cdr_ratio`, then apply FX **only when the quote's native currency is not
   the account currency** — i.e. a US-series source
   (`(US / ratio) × FX`, `test_cdr_pricing.py:84-107`) vs. an already-CAD CDR feed
   (`raw / ratio`, `test_cdr_pricing.py:134-171`). FX unavailable → `/ratio` only
   (`test_cdr_pricing.py:109-127`).
4. **Per-leg, not per-company:** mixed CDR/direct positions split first via
   `cdr_utils.classify_lot_legs` (`cdr_utils.py:295-354`, BLK-027); the kernel values each leg.

Every former call site (Section 2 table) is repointed to `value_security` and its local copy
deleted. The write-time audit fields already emitted by `snapshot_builder.py:589-614`
(`raw_price`, `cdr_ratio`, `price_source`, `fx_rate`) become the kernel's return value.

### 5.5 Query/read models

- `portfolio_snapshots` stays the time-series read model (already exists; already the chart's
  source — `portfolio_service.py:1709-1738`).
- **Overview** computes `as_of = now` through the **same kernel**; the nightly snapshot computes
  `as_of = D` through the same kernel. Because both share one implementation, same-day values are
  equal by construction, and the equivalence test (Section 9) proves it.
- Alternative (if stronger consistency is preferred): Overview reads the latest persisted snapshot
  as a pure read-model query. Trade-off: contradicts CQRS if freshness matters more. Either is
  acceptable **provided the kernel is shared**; the failure mode we must never repeat is two
  implementations.

### 5.6 FX

One `FXService` rate series; applied **once**, inside the kernel, keyed to `as_of`. Staleness is a
kernel-level quality flag (`price_data_quality`), not a caller concern. UI never converts
(`FX_CURRENCY_CONVERSION_DESIGN.md:155`).

---

## 6. Component contracts

| Component | Input | Output | Boundary rule |
|---|---|---|---|
| `securities` projection | transactions + companies | security rows | idempotent; rebuildable |
| `value_security` (kernel) | security, as_of, ccy, quote/history/fx sources | `Valuation` | pure; no I/O; domain layer |
| Overview read | user, `as_of=now` | `PortfolioOverview` | calls kernel only |
| Snapshot writer | account, date | `portfolio_snapshots` row | calls kernel only |
| Quote writer | security, as_of, price | `quotes` row | keyed by `security_id` |

**Invariant (machine-checkable):** for every account and date,
`Overview(as_of=D).total_value == snapshot(D).total_value` within a fixed tolerance; and no `quotes`
row exists where a `COMMON` and a `CDR` security share an identity key.

---

## 7. Data model / migrations

| Step | Change | Reversible by |
|---|---|---|
| M1 | Add `securities` table + `holdings.security_id` (nullable) | drop column/table |
| M2 | Backfill `securities` from companies + transactions (`cdr_utils`) | re-run idempotent |
| M3 | Add `quotes`; dual-write alongside `current_market_data` | drop table; reads still hit old |
| M4 | Flip reads to `quotes`; keep `current_market_data` as view | revert read flag |
| M5 | Retire per-endpoint CDR copies | git revert |

Each migration is additive first, then a read-flip, then a cleanup — never a destructive step
before the equivalence test is green.

---

## 8. Phased migration (reversible, gated)

- **Phase 0 — correctness.** Make `_enrich_holdings` apply the declared CDR+FX rule (or call the
  kernel once extracted). Kills the user-visible defect. One file. Reversible. Gate: the 2026-10-08
  reproduction (card == chart).
- **Phase 1 — kernel extraction (Option B).** Create `domain/valuation.py`; repoint all nine call
  sites; delete duplicates; keep schema. Gate: `test_cdr_pricing.py` still green against the kernel;
  new equivalence test green.
- **Phase 2 — instrument + quote model (Option C data half).** M1–M4. Gate: no identity collision in
  `quotes`; ingestion writes by `security_id`; CDR/US prices no longer overwrite.
- **Phase 3 — consolidation.** Overview reads kernel/read-model; retire ad-hoc endpoint code; make
  the equivalence invariant a standing gate.

Each phase runs G1 (contract) if API shape changes, G3 (`architecture_rules.yaml` boundaries — the
kernel must not import infrastructure), and G4 (executable tests). No phase bypasses a gate.

---

## 9. Verification and evidence

| Requirement shape | Evidence |
|---|---|
| CDR valuation rule (`/ratio`, `×FX`, fallbacks) | unit tests against the kernel (`test_cdr_pricing.py` becomes a kernel contract test) |
| Overview and chart agree | equivalence test: recompute(D) == persisted snapshot(D) for 6 accounts × N dates, exit code |
| No CDR/US quote collision | data-integrity check: zero shared-key collisions in `quotes` |
| Point-in-time | future-date guard (exists) + as-of replay test |
| Mixed lots (BLK-027) | per-leg kernel test (`test_cdr_mixed_lot_valuation.py`) |
| Visible card value | browser evidence via G6 for the Overview card |

The **equivalence invariant is the load-bearing test**: it is exactly what was missing when the two
paths diverged. If it cannot run, the requirement is *unverifiable*, never a pass.

---

## 10. Risks, non-goals, and what not to do

**Risks**
- `securities` derivation drifts if transaction `security_name` is inconsistent → add a
  reconciliation report and treat divergence as a blocker, not a warning.
- Mixed-lot edge cases (BLK-027) → kernel must value per leg; reuse `classify_lot_legs`, do not
  re-implement.
- Backfill correctness → dual-write + read-flip, never a destructive cutover.
- FX staleness → kernel quality flag, surfaced not hidden.

**Non-goals**
- Not a security master for the whole market — only instruments the user holds.
- No FX in the UI; no new event store (it exists).
- No speculative "improve sourcing" beyond the identity split.

**What not to do**
- Do **not** add a tenth CDR division. Every fix routes through `value_security`.
- Do **not** re-key quotes by anything but `security_id`.
- Do **not** delete or weaken `test_cdr_pricing.py` to reach green; it is the contract.
- Do **not** let a cache (`exchange_override`) overrule the transaction-derived truth.

---

## Appendix — Key evidence (opened this run)

- `backend/shared/snapshot_builder.py:195-216` `_apply_cdr`; `:364-678` `build_snapshot_row`
  invariants (future-date guard `:383-392`; CDR-ratio write invariant `:485-497`; rederived-total
  assertion `:656-663`; audit fields `:589-614`).
- `backend/application/services/portfolio_service.py:508` `_enrich_holdings`; `:903`
  `get_user_portfolio_overview`; `:1709-1738` `get_portfolio_performance` (snapshot read).
- `backend/api/portfolio.py:121-160` `_get_company_cdr_ratios` / `apply_cdr_adjustment`; call sites
  `:282/:526/:833/:908`.
- `backend/shared/cdr_utils.py:1-118` canonical classification; `:295-354` `classify_lot_legs`.
- `backend/tests/test_cdr_pricing.py:84-127,134-171,352-365` the declared CDR valuation contract.
- `backend/docs/EVENT_SOURCING_CQRS_DESIGN.md` (CQRS/event store/read model ground truth);
  `backend/docs/CDR_PRICING_BUG_ANALYSIS_AND_REDESIGN.md:99-129` Phase 1–3;
  `backend/docs/FX_CURRENCY_CONVERSION_DESIGN.md:155`; `framework/architecture_rules.yaml`.
