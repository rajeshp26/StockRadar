# CDR Pricing Bug — Analysis & Redesign

## Current State

Portfolio TFSA (account 9) shows V=$83,149 instead of ~$49k. Root cause: 12 CIBC CDR holdings across accounts 7/8/9 are priced using US stock prices, which are ~10x the actual CDR price.

CIBC CDRs (Canadian Depositary Receipts, CAD Hedged) trade on NEO exchange. Each CDR represents 1/10th of one underlying US share. Example: META @ $607 US → CDR @ $60.70 CAD.

## Three Bugs

### Bug 1: `exchange_override` dropped on event replay

**Fault:** `EventProjectionHandler._atomic_write_holdings()` does not write `exchange_override` to `portfolio_holdings`. The `ReplayEngine.HoldingState` dataclass has no `exchange_override` field.

**Impact:** The one-time `migrate_holding_exchange_override.py` backfill gets undone on every event replay. CDR holdings lose their `exchange_override=TOR` marker, so no code path can distinguish CDR from US holdings.

**Files:**
- `backend/shared/replay_engine.py:13-19` — `HoldingState` dataclass
- `backend/services/event_projection_handler.py:123-135` — `_atomic_write_holdings`
- `backend/application/parsers/portfolio_parser.py:334-342` — parser correctly sets `exchange_override=TOR`

**Fix:** Add `exchange_override: Optional[str] = None` to `HoldingState`. Include it in `_atomic_write_holdings` INSERT. The parser already sets it; it just needs to survive the replay cycle.

---

### Bug 2: `current_market_data` can't store CDR prices alongside US prices

**Fault:** `current_market_data` has `company_id` as its conflict key (`on_conflict="company_id"`). CDR and US holdings of the same equity (e.g., META) share one `company_id`. The price ingestion job writes both a `yfinance_tor` price (for CDR) and a `supabase_market_data` price (for US) to the same row — whichever runs last wins.

**Files:**
- `backend/infrastructure/repositories/price_repository.py:53-76` — `upsert_price_source()` uses `on_conflict="company_id"`
- `backend/application/jobs/price_ingestion_job.py:99-107` — writes all prices to same table
- `backend/shared/snapshot_builder.py:50-51` — `_resolve_holding_price()` reads by `company_id` only
- `backend/application/services/portfolio_service.py:473-478` — `_enrich_holdings()` reads by `company_id` only

**Fix (immediate):** Apply CDR ratio in pricing code using `exchange_override` + company exchange data. When `exchange_override=TOR` and the company's primary exchange is US (NMS/NYQ), divide US price by 10.

---

### Bug 3: Pricing code ignores `exchange_override`

**Fault:** `_resolve_holding_price()` (snapshot builder) and `_enrich_holdings()` (dashboard) accept `(company_id, symbol, avg_cost, ...)` — no `exchange_override` parameter. They resolve to a single price per `company_id` in `current_market_data`, which conflates CDR and US prices.

**Files:**
- `backend/shared/snapshot_builder.py:33-79` — `_resolve_holding_price()` signature
- `backend/shared/snapshot_builder.py:158-186` — `build_snapshot_row()` calls it without exchange_override
- `backend/shared/replay_engine.py:217-254` — `build_snapshot_from_replay()` calls it without exchange_override
- `backend/application/services/portfolio_service.py:464-499` — `_enrich_holdings()` has no exchange awareness

**Fix:** Add `exchange_override` parameter to both pricing functions. When `exchange_override="TOR"`:
1. If Tier 1/CURRENT price is from a US-listed company → divide by CDR ratio
2. If Tier 2/FORWARD-FILL price is from `price_history` → divide by CDR ratio (price_history has US prices)
3. Tier 3/COST_BASIS uses actual CDR cost basis from transactions → already correct

---

## Long-Term Solution Design

### How Professional Systems Handle This

Large investment platforms (Bloomberg, Charles River, Aladdin) use a **multi-instrument security master**:

```
securities                         issuers
┌─────────────────────────┐       ┌──────────────────┐
│ security_id (PK)        │       │ issuer_id (PK)   │
│ issuer_id (FK)          │──────▶│ legal_name       │
│ ticker                  │       │ domicile         │
│ exchange                │       │ industry         │
│ security_type           │       │ ...              │
│ currency                │       └──────────────────┘
│ cdr_ratio               │
│ underlying_security_id  │──▶ self-ref FK
│ cusip / isin            │
│ ...                     │
└─────────────────────────┘

pricing_engine
┌──────────────────────────────────┐
│ (security_id, exchange, currency)│  ← unique key
│     → price, source, timestamp   │
└──────────────────────────────────┘

portfolio_holdings
┌─────────────────────────┐
│ holding_id              │
│ security_id (FK)        │  ← references securities, not issuers
│ quantity                │
│ ...                     │
└─────────────────────────┘
```

Key differences from current design:
- **Securities != Issuers**: A company (issuer) can have multiple securities (US stock, CDR, preferred shares, warrants)
- **CDR is a derivative security**: Has `underlying_security_id` pointing to the US stock + `cdr_ratio=10`
- **Pricing by security**: Each security gets its own price, regardless of underlying issuer
- **Holdings reference securities**: So a META CDR holding and a META US holding point to different security_ids

### Recommended Phased Migration

#### Phase 1 — Immediate Fix (current sprint)
- Preserve `exchange_override` through event replay
- Apply static CDR ratio in pricing code based on `(exchange_override=TOR, company_exchange=US)`

Cost: ~3 files changed, 0 schema changes, 0 new tables.
Limitation: CDR ratio is hardcoded as 10 (works for all CIBC CDRs).

#### Phase 2 — Data-Driven CDR Ratio (needs DDL)
- Add `cdr_ratio DECIMAL(10,2)` column to `companies` table (DEFAULT NULL)
- CDR companies get `cdr_ratio=10` set during CSV import or via migration
- Pricing code reads `companies.cdr_ratio` instead of hardcoded 10
- When `cdr_ratio IS NULL` → no adjustment (standard equity)

Cost: 1 DDL operation + update company creation in `portfolio_service.py:1287-1301`.
Limitation: Companies still conflate US stock + CDR under one `company_id`.

#### Phase 3 — Multi-Instrument Security Master (professional grade)
- New table: `securities (security_id PK, issuer_id FK, ticker, exchange, security_type, currency, cdr_ratio, underlying_security_id FK → securities)`
- New table: `issuers (issuer_id PK, legal_name, domicile, ...)`
- Migrate `companies` → `issuers` (corporate entities without exchange info)
- CDRs become separate securities with `underlying_security_id` pointer
- `portfolio_holdings.security_id` becomes a FK to `securities`
- `current_market_data` stores prices per `security_id`
- `price_source_preferences` uses `(security_id, exchange)`
- All pricing becomes issuer-agnostic: a security has exactly one price

Cost: Multiple schema migrations, code refactoring across pricing, holdings, and import paths.

### Phase Recommendation

| Phase | Effort | Risk | Fixes Bug 2? | Data-driven? |
|-------|--------|------|------------|--------------|
| 1 (hardcoded ratio) | 1 day | Low | ✓ (logic) | No |
| 2 (cdr_ratio column) | 2 days | Low | ✓ (column) | ✓ ratio |
| 3 (multi-instrument) | 2-4 weeks | High | ✓ (arch) | ✓ everything |

For a single-user portfolio with 12 CDR symbols, Phase 1 + Phase 2 provides a maintainable solution without architectural overkill. Phase 3 is warranted when the system needs to support multiple CDR issuers (CIBC, BMO, RBC), complex instrument types (warrants, rights, options), or multi-user portfolios with diverse security types.

### Decision Tree

```
Need to support CDR pricing?
    │
    ├── Only CIBC CDRs? → Phase 1 + Phase 2 (enough)
    │
    ├── Multiple CDR issuers (CIBC, BMO, RBC)?
    │   └── Different CDR ratios per issuer? → Phase 2 column enough
    │
    ├── Need warrants, rights, options, or other derivatives?
    │   └── Phase 3 (proper security master)
    │
    └── Multi-user enterprise deployment?
        └── Phase 3 (industry standard)
```
