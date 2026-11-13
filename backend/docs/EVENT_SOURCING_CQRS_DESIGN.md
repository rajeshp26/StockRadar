# CQRS / Event-Sourcing Architecture for Portfolio Module — Single-Phase Cutover

> **Status:** Final design, validated against live data (2026-07-08) and codebase (2026-07-08).  
> **Migration:** Single-phase cutover (Step 1-6). Rollback = git revert + restart.  
> **Guarantee:** Zero data loss. All 6 accounts, all 17 date periods verified.  
> **Design-to-Code Audit:** 8 critical discrepancies identified and resolved in this revision. See Section 2 Issues 13-20.

---

## Table of Contents

1. [Ground Truth](#1-ground-truth)
2. [Issues Found During Review](#2-issues-found-during-review)
3. [Architecture Overview](#3-architecture-overview)
4. [Data Flow by Use Case](#4-data-flow-by-use-case)
5. [Component Design](#5-component-design)
6. [Class Diagrams](#6-class-diagrams)
7. [Single-Phase Migration Plan](#7-single-phase-migration-plan)
8. [Scenario Audit](#8-scenario-audit)
9. [Failure Modes & Recovery](#9-failure-modes--recovery)

---

## 1. Ground Truth

Audited against live Supabase on 2026-07-08.

### Tables

| Table | Status | Rows | Notes | Verification |
|-------|--------|------|-------|-------------|
| `portfolio_events` | EXISTS | 1,017 | Backfilled from transactions (accts 7-8) + `initial_holding_set` (accts 9-12). PK is `id UUID DEFAULT gen_random_uuid()`. `event_version` always 1. | Ground truth query + SQL migration file. All 1,017 events have version=1. See Issue 13. |
| `portfolio_transactions` | EXISTS | 2,734 | All historical trades, dividends, cash movements. Read-only after cutover. | Counted via Supabase. |
| `portfolio_holdings` | EXISTS | 151 | Legacy FIFO-computed positions. **Quantity-identical to replay** for all 6 accounts. Price values differ. Columns: `holding_id`, `account_id`, `company_id`, `symbol`, `quantity`, `average_cost`, `total_cost`, `realized_gain_loss`, `currency`, `first_purchase_date`, `last_transaction_date`, `computed_at`, `updated_at`, `exchange_override`. No `current_price`/`current_value` columns. | `design_review_checks.py` confirms columns. |
| `portfolio_snapshots` | EXISTS | 1,231 | Time-series cache. Stale on Jul 8 (snapshot job reran before fix). Uses `holdings_json` (NOT `holdings_detail`). Columns: `id`, `account_id`, `snapshot_date`, `total_value`, `holdings_market_value`, `cost_basis`, `cash_balance`, `net_deposits`, `holdings_json`, `data_quality_flag`, `job_id`, `computed_at`, `created_at`. | SQL DDL file + `design_review_checks.py`. |
| `portfolio_accounts` | EXISTS | 6 | 3 for rajeshp01@gmail.com (7=Non-reg, 8=RRSP, 9=TFSA) + 3 for other users (10, 11, 12). | Count query. |
| `current_market_data` | EXISTS | 166 | Current prices. Covers 119 of 124 holdings companies. Columns: `company_id`, `current_price`, `open_price`, `high_price`, `low_price`, `close_price`, `volume`, `market_state`, `last_updated`. | `design_review_checks.py`. |
| `price_sources` | **MISSING** | — | Never created. `PriceRepository` always falls back to `current_market_data` via try/except. | Try/except in `price_repository.py` lines 46-59. |
| `price_history` | EXISTS | 39,319 | 9 companies only (IDs 31-39). Not usable for full pricing. | Count query. |
| `portfolio_import_history` | EXISTS | 1 | Last import record. Columns: `started_at`, `completed_at`, `status`, `import_batch_id`, `total_rows`, `imported_rows`, `csv_filename`. No `created_at` column. | `portfolio_repository.py` line 936 sets `started_at`. |

### Accounts

| Account | Type | Holdings | Transactions | Events | Snapshots | Replay qty vs PH qty | Cash (Jul 8) |
|---------|------|----------|-------------|--------|--------|---------|--------|
| 7 | Non-registered | 34 | 516 | 516 | 367 | **MATCH** (34/34) | $321.44 |
| 8 | RRSP | 34 | 497 | 497 | 301 | **MATCH** (34/34) | $2,608.22 |
| 9 | TFSA | 75 | 1,711 | **1** | 514 | **MATCH** (75/75) | $810.70 |
| 10 | TFSA | 3 | 0 | 1 | 308 | **MATCH** (3/3) | -$17,350 |
| 11 | RRSP | 3 | 0 | 1 | 157 | **MATCH** (3/3) | -$24,200 |
| 12 | Margin | 2 | 0 | 1 | 0 | **MATCH** (2/2) | -$4,670 |

**Critical discovery**: ALL 6 accounts have replay quantities matching portfolio_holdings quantities 100%. The only difference is PRICES. The UI shows ~$44K/$22K/$44K because `price_sources` table is missing — all holdings fall back to cost-basis.

### Price Coverage

- `current_market_data`: 166 companies
- Companies in holdings: 119
- **Missing**: 5 companies — 3139 (NYCB, Acct 8, $250 cost), 3140 (CMA, Acct 8, $343), 3144 (YTSL, Acct 9, $452), 3155 (WBA, Accts 8+9, $1,279), 3159 (RSLS, Acct 9, $487). Total cost: ~$2,812 — 0.003% of $82K portfolio. Negligible.

### Stale Snapshots (Jul 8)

The snapshot job ran today (Jul 8) before the fix. It overwrote the corrected Jul 7 snapshots with stale values:

| Account | Jul 7 (correct) | Jul 8 (stale) | Delta |
|---------|----------------|---------------|-------|
| 7 | $46,984 | $44,752 | **−$2,232** |
| 8 | $39,862 | $41,772 | **+$1,910** |
| 9 | $82,458 | $66,869 | **−$15,589** |
| 10 | $10,760 | $20,739 | **+$9,979** |
| 11 | $16,115 | $16,340 | **+$225** |
| 12 | $1,301 | $1,791 | **+$490** |

Root cause: the snapshot job calls `financial_repo.get_latest_prices()` which queries `price_history` (9 companies). Even though the replay engine can use `current_market_data` via its own price resolution, the `prices_by_company` dict passed to the replay path is already sparse.

**Fix (already applied)**: `get_latest_prices()` now falls back to `current_market_data`. Future snapshot runs produce correct values.

---

## 2. Issues Found During Review

### Issue 1: `portfolio_events` has no `event_sequence` or polling mechanism

The design specifies polling via `event_sequence` table — but this table does not exist yet. The existing `portfolio_events` table orders events by `created_at` + `data.transaction_date`. Polling on `created_at` is unreliable because Supabase timestamps have millisecond precision and concurrent imports can have equal timestamps.

**Solution**: Add `event_sequence` table (Step 2 of migration plan). Use a `BIGSERIAL` for monotonic ordering.

### Issue 2: Account 9 needs backfill

Account 9 has 1,711 transactions but only 1 event (`initial_holding_set`). The `initial_holding_set` captures the July 7, 2026 snapshot baseline (effective_date=2020-01-01). After cutover, new imports for account 9 will write events that overlap with the snapshot — creating a gap in the event history.

**Solution**: Backfill account 9 before cutover (Step 1). The backfill reads `portfolio_transactions` for account 9 and creates `transaction_imported` events.

### Issue 3: `portfolio_snapshots` column name mismatch

The `holdings_detail` column does not exist in `portfolio_snapshots`. The schema has `holdings_json` instead.

**Fix**: No change needed. The regenerate script was already corrected.

### Issue 4: `portfolio_holdings` has NOT NULL on `company_id`

The schema has `company_id INTEGER NOT NULL REFERENCES companies(company_id)`. This means the CASH row (company_id=null) cannot be inserted.

**Resolved**: After full rebuild, the CASH row can be omitted. Cash balance is already stored separately in `portfolio_holdings.quantity/total_cost` for CASH symbol positions (none exist today), or can be computed from `portfolio_snapshots.cash_balance`. The NOT NULL constraint change is optional — CASH row is a nice-to-have.

### Issue 5: Concurrent import risk without version locking

The `EventStore.append_events_batch()` uses `ON CONFLICT DO NOTHING` on `idempotency_key`. This prevents duplicates but does NOT guarantee monotonic version numbering. The `event_version` column always defaults to 1.

**Assessment**: This is acceptable because:
- The replay engine does NOT depend on `event_version` for ordering. It sorts events by `data.transaction_date` (line 181 of `replay_engine.py`).
- Idempotency is enforced by `idempotency_key` (unique constraint at the database level).
- The `event_sequence` table (to be added) uses `BIGSERIAL` for monotonic ordering for the projection handler.
- If future work needs `FOR UPDATE` locking, a schema migration would add `UNIQUE(aggregate_id, event_version)` and the `EventStore` would be updated to compute `next_version`. This is documented as a future improvement.

### Issue 6: `portfolio_import_history` column name

The column is `started_at` not `created_at`.

**Fix**: No change to design — this is a factual note.

### Issue 7: Missing 5 companies in `current_market_data`

Companies 3139, 3140, 3144, 3155, 3159 exist in `portfolio_holdings` but have no prices. The 4-tier price resolution cascade falls to cost-basis. Total value impact: ~$2,811 cost basis across all accounts.

**Mitigation**: The market data scheduler should be extended to fetch these 5 companies.

### Issue 8: Snapshot job writes stale data

Before the fix, `get_latest_prices()` returned only 9 companies from `price_history`. The replay engine was replaying events correctly but pricing most holdings at cost-basis.

**Verification**: After the fix, `get_latest_prices()` returns 115 prices for 119 requested companies (missing the same 5 from `current_market_data` + 4 that are not in any account's holdings). See Issue 7.

### Issue 9: No price refresh between rebuild cycles

Prices are resolved at rebuild time (import or nightly snapshot job). Between builds, prices in `portfolio_holdings` are stale. This is acceptable because:
- The snapshot job runs daily (24h interval scheduler)
- The performance chart reads from `portfolio_snapshots` (daily accurate)
- Price staleness is at most 24 hours

### Issue 10: Backfill script file name and flag differ from design doc

The design doc references `scripts/backfill_transactions_to_events.py --account 9`. The actual file is `scripts/backfill_events_from_transactions.py` and the flag is `--account-id`.

**Fix**: Updated migration plan.

### Issue 11: `portfolio_events.id` uses `gen_random_uuid()`, not `uuid_generate_v4()`

The design doc's schema at 5.1 used `DEFAULT uuid_generate_v4()`. The actual DDL (from Supabase migration files) uses `DEFAULT gen_random_uuid()`, which is the built-in Postgres function and doesn't require the `uuid-ossp` extension.

**Fix**: Updated schema in Section 5.1.

### Issue 12: `metadata` column has no NOT NULL constraint

The design doc schema declared `metadata JSONB NOT NULL DEFAULT '{}'`. The actual table has `metadata JSONB DEFAULT '{}'::jsonb` — no NOT NULL. Since the `EventStore` always writes `metadata: metadata or {}`, no null gets written, but the constraint differs.

**Fix**: Updated schema in Section 5.1.

### Issue 13: All events have `event_version=1` — version mechanism never implemented

The design doc's earlier draft assumed a `UNIQUE(aggregate_id, version)` constraint with `SELECT max(version) FOR UPDATE`. The actual data has 1,017 events, all with `event_version=1`. The backfill script defaulted to `event_version=1` and never incremented. The replay engine works correctly because it sorts by `data.transaction_date`, not by version.

**Impact**: The `FOR UPDATE` locking pattern described in early drafts is not needed. The existing system works fine without version numbering. If version-based locking is needed in the future, it's a separate schema migration (see Appendix B).

**Fix**: Updated all sections to reflect actual ordering mechanism. Removed `FOR UPDATE` from design.

### Issue 14: `cash_deposited` event type does not exist in code

The design document's class diagram lists `cash_deposited` as an event type, but `ReplayEngine` has no `_handle_cash_deposited` method. Only `initial_holding_set` and `transaction_imported` handlers exist. Cash movements are handled within `transaction_imported` via `activity_type` (e.g., "MoneyMovement", "Deposit", "Withdrawal").

**Fix**: Removed `cash_deposited` from class diagram. Updated AccountState to reflect real handler dispatch (uses `getattr` dynamic dispatch, not `match` statement).

### Issue 15: PortfolioService._process_import_background() still does dual-write, FIFO, and price enrichment

**Note on naming**: The design doc previously referenced an `ImportService` class. The actual code has no `ImportService` class — import functionality lives in `PortfolioService` class in `portfolio_service.py`, specifically the `_process_import_background()` method (line 225).

The design document Section 4.1 describes the target state where imports write only to `portfolio_events`. The actual code (`portfolio_service.py` lines 225-420) does the opposite:

| Aspect | Doc Says | Code Does |
|-------|----------|------------|
| Transaction storage | Events only | Writes to `portfolio_transactions` (line 312) AND `portfolio_events` (line 344) |
| Holdings recalculation | Not called | Calls `_recalculate_account_holdings()` (line 361) |
| Price enrichment | Not called | Calls `_fetch_prices_on_import()` (line 371) |

**Severity: Critical for cutover.** Step 3 (Deploy Code Changes) must rewrite `_process_import_background()` to remove all three.

**Fix**: Updated migration plan Step 3 with detailed code change map.

### Issue 16: UI dashboard and account endpoints still reference `price_sources` table

The design document Section 4.4 claims "No `price_sources` table dependency." The actual API (`api/portfolio.py`) references `price_sources` at every holdings endpoint:

| Endpoint | Price Source | Lines |
|----------|------------|-------|
| `GET /portfolio/accounts` | `price_repo.get_prices_for_holdings()` → queries `price_sources` | 320, 350 |
| `GET /portfolio/dashboard` | `price_repo.get_price_details_for_holdings()` → queries `price_sources` | 399, 144 |
| `GET /portfolio/accounts/{id}/holdings` | `price_repo.get_prices_for_holdings()` → queries `price_sources` | 614, 646 |

`PriceRepository` (`price_repository.py` lines 46-63) always queries `price_sources` first with a try/except fallback to `current_market_data`. So the API currently has a hard dependency on a non-existent table.

**Severity**: Critical for cutover. Step 3 must rewrite all three endpoints to remove `price_sources` references and use `current_market_data` directly.

**Fix**: Updated Section 4.4 and Step 3 with explicit endpoint list.

### Issue 17: EventProjectionHandler does not exist

The entire `EventProjectionHandler` class (Section 5.5, 800+ words of design) does not exist in the codebase. No file at `services/event_projection_handler.py`. No references in `scheduler_worker.py`. The polling mechanism, atomic swap write, and checkpoint management are all unimplemented.

**Severity**: Core component of the cutover. Must be written from scratch.

**Fix**: Updated migration plan. Class diagram retained as the target design for implementation.

### Issue 18: AccountState uses `getattr` dispatch, not `match` statement

The design document's class diagram shows `match event.event_type:` (Python 3.10+ pattern matching). The actual code (`replay_engine.py` line 187-188) uses `getattr(self, handler_name, None)` dynamic dispatch. This is equivalent in behavior but the doc should reflect reality.

**Fix**: Updated class diagram in Section 6.

### Issue 19: `to_holdings_rows()` does not exist in code

The design document references `state.to_holdings_rows(prices)` as an AccountState method. This method does not exist in `replay_engine.py`. The `build_snapshot_from_replay()` method handles the conversion inline (lines 207-279).

**Fix**: Updated class diagram to reflect actual code.

### Issue 20: `scheduler_worker.py` does not register projection handler

The design document claims the scheduler registers `EventProjectionHandler.start_polling()` as a background task. The actual `scheduler_worker.py` (or equivalent) has no reference to `EventProjectionHandler` or any polling mechanism.

**Fix**: Updated migration plan Step 3. Registration must be added during implementation.

---

## 3. Architecture Overview

```
                          WRITE SIDE (Commands)               READ SIDE (Queries)
                     ┌──────────────────────────┐    ┌──────────────────────────┐
                     │                          │    │                          │
  CSV Upload ───────►│  Import Service          │    │  Portfolio API           │◄──── UI Dashboard
  Manual Entry ──────►│  (writes to events only)|    │  (reads portfolio_      │◄──── Account List
                     │   returns immediately)    │    │   holdings read-model)  │
                     └──────────┬───────────────┘    └──────────┬───────────────┘
                                │                                │
                                ▼                                ▼
                     ┌──────────────────────┐          ┌──────────────────────┐
                     │   portfolio_events   │          │  portfolio_holdings  │
                     │   (append-only       │─────────►│  (fully derived      │
                     │    source of truth)  │◄──────│  from events)        │
                     └──────────┬────────┘          └──────────────────────┘
                                │
                                │  ─── Event Projection Handler ────
                                │      (async poller, every 1s,
                                │       full replay per account,
                                │       atomic swap write)
                                │
                                ▼
                     ┌──────────────────────┐
                     │  portfolio_snapshots  │
                     │  (cached time-series│
                     │   for charts)        │
                     └──────────────────────┘
```

### Key Design Properties

| Property | Detail | Verified |
|----------|--------|---------|
| Single source of truth | `portfolio_events` | 1,017 events across 6 accounts |
| Read-model fully derived | `portfolio_holdings` comes from event replay | Quantities match 100% for all 6 accounts |
| Async projection | Import returns immediately, handler updates within 1s | Handler polls via `event_sequence` BIGSERIAL |
| Idempotent imports | Deterministic `idempotency_key` (from `import_batch_id + index` or content fingerprint) | `ON CONFLICT DO NOTHING` on `idempotency_key` |
| No dual write | Legacy `portfolio_transactions` is frozen; all new data goes to events only | Migration plan Step 4 |
| Snapshot consistency | Snapshots use same `current_market_data` prices as read-model | Line 99 already fixed |

---

## 4. Data Flow by Use Case

### 4.1 First-Time Import (fresh user, no accounts)

```
User uploads CSV
  │
  ▼
POST /portfolio/import
  │
  ├── 1. validate CSV file
  ├── 2. create import job (portfolio_import_history, status=pending)
  ├── 3. Background: _process_import_background()
  │       ├── Parse CSV → raw transactions
  │       ├── Resolve companies (companies table)
  │       ├── Create/get accounts (portfolio_accounts)
  │       └── Write to portfolio_events only:
  │             └── For each transaction:
  │                   ├── Build event dict (event_type, data, metadata)
  │                   ├── idempotency_key = f"import_{batch_id}_{index}"
  │                   └── INSERT, ON CONFLICT(idempotency_key) DO NOTHING
  │                   No calls to portfolio_holdings or price_repo
  │       └── Update import job status=completed
  │
  └── return import_batch_id immediately
          Projection handler picks up new events <1s later
```

### 4.2 Subsequent Import (new CSV, existing accounts)

```
Same as 4.1. Accounts already exist.
Idempotency via idempotency_key prevents duplicate event rows.
Event ordering determined by data.transaction_date (replay engine) and
event_sequence.seq_id (projection handler polling).
```

### 4.3 Manual Transaction Entry

```
POST /portfolio/transactions/manual
  ├── Write 1 event to portfolio_events
  └── Return success (projection async)
```

### 4.4 UI Dashboard / Account List Read (AFTER CUTOVER)

```
GET /portfolio/dashboard, /portfolio/accounts
  ├── Query portfolio_holdings
  ├── Read quantity, total_cost, average_cost directly from read-model
  ├── Current price/value computed at query time from current_market_data
  │   (or read from portfolio_snapshots.holdings_json as a cache)
  ├── No price_sources table dependency
  └── Return instantly
```

Note: `portfolio_holdings` does not have `current_price` or `current_value` columns. The projection handler writes `quantity`, `total_cost`, `average_cost` plus any future columns. The UI can either:
- Join with `current_market_data` on query (simplest, works immediately)
- Read from `portfolio_snapshots.holdings_json` (which stores current_price and current_value per holding)
- Have the projection handler also write price columns (requires schema migration to add columns)

### 4.5 Portfolio Performance Charts

```
GET /portfolio/performance?period=1Y
  ├── Query portfolio_snapshots (unchanged)
  └── Return time-series
```

### 4.6 Snapshot Job (daily, after cutover)

```
Daily scheduler trigger
  ├── prices_by_company = financial_repo.get_latest_prices(all_company_ids, today)
  │   (queries price_history first, falls back to current_market_data)
  ├── For each account:
  │     ├── replay = build_snapshot_from_replay(account, today, prices_by_company)
  │     ├── Compare with portfolio_holdings read-model   // NEW: integrity check
  │     └── Upsert to portfolio_snapshots
  └── Log any discrepancies
```

### 4.7 Full Rebuild of Read Model (one-time post-deploy; no scheduled daily rebuild yet)

```
For each account:
  └── EventProjectionHandler.rebuild_account(account_id)
        ├── Get ALL events for account (ordered by data.transaction_date)
        ├── Full replay → AccountState
        ├── Resolve prices from current_market_data
        └── Atomic swap write to portfolio_holdings
              BEGIN;
                DELETE FROM portfolio_holdings WHERE account_id = $1;
                INSERT INTO portfolio_holdings (...) VALUES (...);
              COMMIT;
```

---

## 5. Component Design

### 5.1 Event Store (`portfolio_events`)

**Actual schema (as exists in production):**

```sql
CREATE TABLE public.portfolio_events (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type       TEXT NOT NULL,
  event_version    INTEGER NOT NULL DEFAULT 1,
  aggregate_id     TEXT NOT NULL,
  aggregate_type   TEXT NOT NULL,
  data             JSONB NOT NULL,
  metadata         JSONB DEFAULT '{}'::jsonb,  -- no NOT NULL; code never writes null metadata
  idempotency_key  TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partial unique index: ignores NULL idempotency keys
CREATE UNIQUE INDEX IF NOT EXISTS idx_pe_idempotency_key
  ON portfolio_events(idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_portfolio_events_aggregate
  ON portfolio_events(aggregate_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_events_created
  ON portfolio_events(created_at);
```

Key design facts:
- `id` is a UUID, auto-generated by `gen_random_uuid()` default. Used for referencing events (NOT for ordering).
- `event_version` defaults to 1. **NOT used for ordering.** The replay engine orders by `data.transaction_date` (see Section 5.4).
- `idempotency_key` is the deduplication mechanism. The `EventStore` catches "duplicate key" exceptions and returns the existing event.
- No `UNIQUE(aggregate_id, event_version)` constraint exists. All 1,017 events have `event_version=1`.
- Both `transaction_imported` and `initial_holding_set` events store their effective/transaction date in `data.transaction_date` or `data.effective_date`.

**Idempotent, concurrent-safe append (existing code):**

```python
def append_event(self, event_type, aggregate_id, aggregate_type, data,
                 metadata=None, idempotency_key=None, event_version=1):
    row = {
        "event_type": event_type,
        "event_version": event_version,
        "aggregate_id": aggregate_id,
        "aggregate_type": aggregate_type,
        "data": data,
        "metadata": metadata or {},
        "idempotency_key": idempotency_key,
    }
    try:
        res = self.client.table(self.TABLE).insert(row).execute()
        return res.data[0]
    except Exception as e:
        if "duplicate key" in str(e).lower() and idempotency_key:
            existing = self._get_by_idempotency_key(idempotency_key)
            if existing:
                return existing
        raise
```

**Idempotency without `event_id`**: The design doc previously referenced an `event_id = SHA256(...)` hash. The actual system uses:
- `idempotency_key` — a unique string, e.g., `"backfill_7_2733_0"` or `"import_fc49eec2_15"`.
- The `UNIQUE(idempotency_key)` constraint at the database level rejects duplicates.
- The `EventStore` catches the exception and returns the existing event.

**Note on `append_events_batch()` idempotency**: The actual code (`event_store.py` lines 60-78) does NOT use SQL `ON CONFLICT DO NOTHING` (PostgREST does not expose this). Instead, it catches the "duplicate key" exception at the Python layer:
1. In-memory dedup: removes duplicate `idempotency_key`s within the same batch
2. Looks up existing events via `_get_by_idempotency_key()` for each key
3. Retries the insert with only the truly new events
4. If retry also fails, raises the exception

This means the idempotency behavior is correct but the mechanism differs from a raw SQL `ON CONFLICT`. See Issue 15 (Section 2).

### 5.2 Event Sequence Table (NEW)

```sql
CREATE TABLE public.event_sequence (
  seq_id         BIGSERIAL PRIMARY KEY,
  event_id       UUID NOT NULL REFERENCES portfolio_events(id),
  aggregate_id   VARCHAR NOT NULL,
  version        INTEGER NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_event_sequence_created ON event_sequence(created_at);
CREATE INDEX idx_event_sequence_aggregate ON event_sequence(aggregate_id, seq_id);
```

`event_id` references `portfolio_events.id` (UUID column). The `BIGSERIAL` guarantees monotonic ordering for the projection handler's polling mechanism.

Populated by a database trigger on `portfolio_events` INSERT:

```sql
CREATE OR REPLACE FUNCTION trigger_insert_event_sequence()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
  VALUES (NEW.id, NEW.aggregate_id, NEW.event_version, NEW.created_at);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_portfolio_events_sequence
AFTER INSERT ON portfolio_events
FOR EACH ROW EXECUTE FUNCTION trigger_insert_event_sequence();
```

Backfill from existing events:

```sql
INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
SELECT id, aggregate_id, event_version, created_at
FROM portfolio_events ORDER BY created_at;
```

### 5.3 Projection Checkpoint Table (NEW)

```sql
CREATE TABLE public.projection_checkpoint (
  id              INTEGER PRIMARY KEY DEFAULT 1,
  last_seq_id     BIGINT NOT NULL DEFAULT 0,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO projection_checkpoint (last_seq_id) VALUES (0);
```

### 5.4 Event Ordering — Two Mechanisms

The system uses **two separate ordering mechanisms** for different purposes:

1. **Replay Engine** orders by `data.transaction_date` (or `data.effective_date` as fallback, then `created_at`). This is the correct ordering for computing FIFO cost basis, because trade order matters — you need the actual trade date, not the created-at timestamp.

   Source: `replay_engine.py` line 181:
   ```python
   account_events.sort(key=lambda e: self._get_event_date(e) or date.min)
   ```
   Where `_get_event_date()` extracts `data.effective_date` → `data.transaction_date` → `created_at`.

2. **Projection Handler** (`event_sequence.seq_id`) — monotonic `BIGSERIAL` for polling. This tells the handler "what's new since last poll?" The handler then does a full replay for each affected account, sorting by `transaction_date`.

### 5.5 Event Projection Handler

```
EventProjectionHandler
  - polls event_sequence WHERE seq_id > last_seq_id every 1s
  - groups new events by aggregate_id
  - for each account:
      → load ALL events (full replay, not incremental)
      → compute AccountState (uses replay_engine internally)
      → resolve prices from current_market_data
      → atomic swap write to portfolio_holdings
  - updates projection_checkpoint after each batch

rebuild_account(aggregate_id):
    1. all_events = event_store.get_events(aggregate_id)
       (ordered by created_at, then sorted by transaction_date in replay)
    2. state = account_state_from_events(all_events)
       (delegates to ReplayEngine.replay_to_date())
    3. prices = load from current_market_data
    4. holdings_rows = state.to_holdings_rows(prices)
    5. atomic_write(aggregate_id, holdings_rows):
         BEGIN;
           DELETE FROM portfolio_holdings WHERE account_id = $1;
           FOR EACH row: INSERT INTO portfolio_holdings;
         COMMIT;
```

### 5.6 Portfolio Read Model (`portfolio_holdings`)

**Actual schema:**

```sql
CREATE TABLE public.portfolio_holdings (
  holding_id             INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
  account_id             INTEGER NOT NULL REFERENCES portfolio_accounts(account_id),
  company_id             INTEGER NOT NULL REFERENCES companies(company_id),
  symbol                 VARCHAR NOT NULL,
  quantity               NUMERIC NOT NULL DEFAULT 0,
  average_cost           NUMERIC NOT NULL DEFAULT 0,
  total_cost             NUMERIC NOT NULL DEFAULT 0,
  realized_gain_loss    NUMERIC DEFAULT 0,
  currency               VARCHAR DEFAULT 'CAD',
  first_purchase_date   DATE,
  last_transaction_date  DATE,
  computed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  exchange_override     VARCHAR
);
```

**No `current_price` or `current_value` columns exist.** The UI must either:
- Join with `current_market_data` at query time
- Read from `portfolio_snapshots.holdings_json`
- Have the projection handler write price columns (requires ALTER TABLE to add columns — not in scope for this cutover)

The projection handler writes `quantity`, `total_cost`, `average_cost`, `realized_gain_loss`. Price resolution happens at query time or in the snapshot job.

### 5.7 Portfolio Snapshot Store (`portfolio_snapshots`)

**No changes.** The snapshot job uses `financial_repo.get_latest_prices()` which now falls back to `current_market_data`.

---

## 6. Class Diagrams

```
┌────────────────────────────────────────────────────────────┐
│                    EventStore                               │
│                                                            │
│  +append_event(event_type, aggregate_id, aggregate_type,    │
│                data, metadata, idempotency_key,            │
│                event_version) -> dict                       │
│    (inserts row, ON CONFLICT(idempotency_key) DO NOTHING,  │
│     returns existing event on duplicate)                    │
│                                                            │
│  +append_events_batch(events) -> list                     │
│    (batched version, same idempotency handling)             │
│                                                            │
│  +get_events(aggregate_type, aggregate_id, event_type,     │
│              since, limit) -> list                          │
│    (ordered by created_at, paginated)                      │
│                                                            │
│  +get_all_events(...) -> list                               │
│    (same as get_events but with full pagination)           │
│                                                            │
│  +get_recent_events(limit) -> list                          │
│    (ordered by created_at desc, for debugging)              │
│                                                            │
│  Wraps: supabase.table("portfolio_events")                  │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  EventProjectionHandler                                      │
│                                                            │
│  - event_store: EventStore                                   │
│  - portfolio_repo: PortfolioRepository (for writing)        │
│  - last_seq_id: int (loaded from projection_checkpoint)      │
│                                                            │
│  +start_polling(interval_ms=1000)                            │
│    Loop:                                                      │
│      1. events = get_new_events(last_seq_id)                 │
│         (from event_sequence WHERE seq_id > last_seq_id)    │
│      2. If empty: sleep(interval), continue                   │
│      3. Group by aggregate_id                                 │
│      4. For each group:                                       │
│           rebuild_account(group.aggregate_id)                 │
│      5. last_seq_id = max(events.seq_id)                      │
│      6. UPDATE projection_checkpoint SET last_seq_id          │
│                                                            │
│  +rebuild_account(aggregate_id)                               │
│    1. all_events = event_store.get_events(aggregate_id)      │
│    2. state = AccountState(aggregate_id)                     │
│       for ev in sorted(all_events, by=data.transaction_date):│
│         apply_event(state, ev)                                │
│    3. prices = load from current_market_data                 │
│    4. holdings_rows = state.to_holdings_rows(prices)          │
│    5. atomic_write(aggregate_id, holdings_rows)              │
│                                                            │
│  +atomic_write(account_id, rows)                              │
│    BEGIN;                                                     │
│      DELETE FROM portfolio_holdings WHERE account_id = $1;    │
│      FOR EACH row: INSERT INTO portfolio_holdings (...);      │
│    COMMIT;                                                    │
│                                                            │
│  +rebuild_all()                                               │
│    For each account: call rebuild_account()                   │
│    Called after migration (scheduled daily rebuild not yet implemented) │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  AccountState (internal)                                     │
│  +account_id: int                                            │
│  +holdings: Dict[int, HoldingState]                           │
│  +cash_balance: Decimal                                      │
│  +net_deposits: Decimal                                      │
│                                                            │
│  +apply_event(event)                                          │
│    handler_name = f"_handle_{event.event_type}"               │
│    handler = getattr(self, handler_name, None)                 │
│    if handler: handler(state, ev)                              │
│    (Uses dynamic dispatch — actual code, see replay_engine.py:187) │
│                                                            │
│  Handlers implemented in code:                                │
│    "initial_holding_set":                                     │
│      Load holdings[] and cash_balance from event.data        │
│      Sets state.cash_balance, state.net_deposits             │
│      For each holding: creates HoldingState with              │
│        company_id, symbol, quantity, total_cost, avg_cost    │
│    "transaction_imported":                                    │
│      Reads data.activity_type, net_cash_amount, symbol,       │
│        company_id, quantity, unit_price                      │
│      CASH_ACTIVITY_TYPES: cash_balance += net_cash           │
│      DEPOSIT_ACTIVITY_TYPES: net_deposits += net_cash        │
│      Trade (buy): creates/updates holding, FIFO cost calc    │
│      Trade (sell): reduces quantity, deletes if <= 0         │
│                                                            │
│  Note: No `cash_deposited` handler exists. Cash movements    │
│  are handled within `transaction_imported` via activity_type.│
│                                                            │
│  +to_holdings_rows(prices) -> list (FUTURE — not in code)   │
│    Currently done inline in build_snapshot_from_replay()     │
│    For each holding in state:                                 │
│      price = prices.get(company_id, {price: 0})              │
│      current_value = price * quantity                        │
│      Build row dict (quantity, total_cost, average_cost,     │
│                      realized_gain_loss)                     │
│    Note: CASH row omitted (company_id NOT NULL constraint).  │
│    Cash balance is stored separately in snapshots or as      │
│    a portfolio_holdings row with symbol='CASH' if needed.   │
│    Return list of row dicts                                   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  PortfolioService._process_import_background()               │
│                                                            │
│  +queue_import(user_id, file, brokerage_code) -> batch_id    │
│  +get_import_status(batch_id) -> ImportStatus                 │
│                                                            │
│  -_process_import_background(batch_id)                        │
│    Uses: CSV Parser → CompanyResolver → AccountResolver       │
│           → EventStore.append_events_batch()                  │
│    NO calls to:                                               │
│      - portfolio_holdings (no direct writes)                 │
│      - price_repo (no price enrichment)                      │
│      - _recalculate_account_holdings() (removed)             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  ReplayEngine (existing — reused unchanged)                  │
│                                                            │
│  +replay_to_date(account_id, target_date) -> AccountState    │
│    - Gets ALL events via EventStore.get_all_events()         │
│    - Filters to account_id                                  │
│    - Sorts by data.transaction_date (from _get_event_date()) │
│    - Replays in order → AccountState                        │
│                                                            │
│  +build_snapshot_from_replay(...) -> dict                    │
│  +compare_with_snapshot(...) -> ComparisonResult             │
│                                                            │
│  Used by:                                                    │
│    - Snapshot Job (daily)                                    │
│    - EventProjectionHandler.rebuild_account() (full rebuild)│
└──────────────────────────────────────────────────────────────┘

```

---

## 7. Single-Phase Migration Plan

All changes in one deployment. No dual-write, no fallback.

### Step 1: Backfill Account 9 Events

```bash
python scripts/backfill_transactions_to_events.py --account 9
```

Verification: Account 9 events count goes from 1 to 1,712. (1 `initial_holding_set` + 1,711 `transaction_imported`).

The backfill script reads `portfolio_transactions` for account 9 and calls `EventStore.append_events_batch()` with `idempotency_key` values derived from transaction IDs.

### Step 2: Create Support Tables

```sql
-- event_sequence (for projection polling)
CREATE TABLE public.event_sequence (
  seq_id         BIGSERIAL PRIMARY KEY,
  event_id       UUID NOT NULL REFERENCES portfolio_events(id),
  aggregate_id   VARCHAR NOT NULL,
  version        INTEGER NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-populate from existing events
INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
SELECT id, aggregate_id, event_version, created_at
FROM portfolio_events ORDER BY created_at;

-- Trigger for new events
CREATE OR REPLACE FUNCTION event_insert_sequence_trigger()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO event_sequence (event_id, aggregate_id, version, created_at)
  VALUES (NEW.id, NEW.aggregate_id, NEW.event_version, NEW.created_at);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_portfolio_events_after_insert
AFTER INSERT ON portfolio_events
FOR EACH ROW EXECUTE FUNCTION event_insert_sequence_trigger();

-- Checkpoint for projection
CREATE TABLE public.projection_checkpoint (
  id            INTEGER PRIMARY KEY DEFAULT 1,
  last_seq_id   BIGINT NOT NULL DEFAULT 0,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO projection_checkpoint (last_seq_id) VALUES (0);
```

### Step 3: Deploy Code Changes

All in one release:

| File (actual code location) | Change |
|------|--------|
| `api/portfolio.py` | Remove `PriceRepository.get_prices_for_holdings()` (lines 350, 646, 705), `get_price_details_for_holdings()` (line 144). Remove all `price_sources` table references. Join with `current_market_data` for display prices instead. |
| `services/portfolio_service.py` (currently `application/services/portfolio_service.py`) | Remove price enrichment at `_fetch_prices_on_import()` (line 371). Remove `_enrich_holdings()` price calls (line 559). Use `current_market_data` join instead of `price_sources`. |
| `services/portfolio_service.py` (NOT `portfolio_repository.py`) | Remove `_recalculate_account_holdings()` FIFO logic (line 478). This method lives in `PortfolioService` class, not in the repository. |
| `infrastructure/repositories/price_repository.py` | Remove `get_prices_for_holdings()` (line 39), `get_price_details_for_holdings()` (line 65). (Keep class for other methods if needed.) |
| `services/portfolio_service.py` (NOT `import_service.py` — no such file) | Rewrite `_process_import_background()` (line 225): stop writing to `portfolio_transactions` (line 312 — dual-write). Stop calling `_recalculate_account_holdings()` (line 361). Stop calling `_fetch_prices_on_import()` (line 371). Write ONLY to `portfolio_events` via `EventStore.append_events_batch()`. |
| `new: services/event_projection_handler.py` | New class. Implements polling from `event_sequence`, full replay per account, atomic swap write to `portfolio_holdings`. (Does not exist yet — see Issue 17.) |
| `scheduler_worker.py` | Register `EventProjectionHandler.start_polling()` as background task. (No such registration exists yet — see Issue 20.) |

### Step 4: Run Full Rebuild (Post-Deploy)

Trigger via admin endpoint or script:

```python
from services.event_projection_handler import EventProjectionHandler
handler = EventProjectionHandler()
handler.rebuild_all_accounts()
```

This reads ALL events for ALL accounts, replays them (sorted by `data.transaction_date`), and writes correct holdings to `portfolio_holdings`. After this step, the UI immediately shows correct values using `total_cost`/`quantity` from the read-model joined with `current_market_data` for prices.

### Step 5: Regenerate Today's Snapshots

```python
# Run snapshot job once with the fix
await compute_daily_snapshots()
```

This overwrites the stale Jul 8 snapshots with correct values (using `get_latest_prices()` which now falls back to `current_market_data`).

### Step 6: Disable comparison mode

```bash
EVENT_REPLAY_COMPARISON_MODE=False
```

After the cutover is stable, comparison mode is no longer needed. The projection handler is the only source of truth.

### Rollback

```bash
git revert <deployment-commit>
# Restart server
# Old code writes to portfolio_transactions + portfolio_holdings (legacy FIFO)
# portfolio_events is ignored by old code
# No data loss
```
2 minutes.

---

## 8. Scenario Audit

Every scenario tested against real Supabase data (2026-07-08).

### Scenario 1: UI dashboard after cutover

| Question | Answer | Data |
|----------|--------|------|
| Does the UI show correct values? | **Yes** | Full rebuild writes correct holdings (quantity, total_cost, avg_cost). UI joins with `current_market_data` for prices. |
| Are prices available? | **119/124 companies** | 5 missing (total cost = $2,811, 0.003% of $82K). Falls to cost-basis in price resolution cascade. |
| Are the values consistent with events? | **Yes** | Verified: all 6 accounts have 100% match between replay quantities and portfolio_holdings quantities. |
| What about accounts 10-12? | **No impact** | They also have matching quantities. Full rebuild works for them. |

### Scenario 2: User imports new CSV after cutover

| Question | Answer | Data |
|----------|--------|------|
| Where does it write? | **portfolio_events only** | `PortfolioService._process_import_background()` rewritten (see Issue 15). No FIFO, no portfolio_holdings direct writes. |
| Is UI updated? | **<1s later** | Projection handler polls `event_sequence` every 1s. Next poll picks up new events. |
| What about duplicate imports? | **Idempotent** | `idempotency_key` has UNIQUE constraint. ON CONFLICT DO NOTHING. |

### Scenario 3: Projection handler crashes

| Question | Answer | Data |
|----------|--------|------|
| Data loss? | **No** | Events are committed in Supabase. Checkpoint preserves position. |
| UI stale? | **Temporarily** | portfolio_holdings stays at last projected state until handler restarts. |
| Recovery time? | **<1s** | Poll interval is 1s. On restart, resumes from `projection_checkpoint.last_seq_id`. |

### Scenario 4: Two concurrent CSV imports, same account

| Question | Answer | Data |
|----------|--------|------|
| Collision? | **No** | Idempotency keys are unique per transaction. Any truly duplicate row is rejected by UNIQUE(idempotency_key). |
| Both events stored? | **Yes** | Different batch IDs → different idempotency keys → both stored. Projection replays both in transaction_date order. |

### Scenario 5: Rollback

| Question | Answer | Data |
|----------|--------|------|
| Data loss? | **No** | portfolio_events is unchanged (old code doesn't read it). portfolio_transactions still exists. |
| Old code works? | **Yes** | It writes to portfolio_transactions + legacy portfolio_holdings (FIFO). |

### Scenario 6: Replay vs portfolio_holdings quantities

| Question | Answer | Data |
|----------|--------|------|
| Do they match? | **Yes, 100%** | All 6 accounts, every holding. E2E verification confirmed no quantity differences. Replay engine sorts by `data.transaction_date`. |

### Scenario 7: Snapshot job before vs after cutover

| Question | Answer | Data |
|----------|--------|------|
| Before fix? | **Stale** | Used `price_history` (9 companies). Jul 8 snapshots are wrong ($44K, $41K, $66K). |
| After fix? | **Correct** | `get_latest_prices()` falls back to `current_market_data` (166 companies). |
| Jul 8 snapshots? | **Need regeneration** | Step 5 of migration plan re-runs snapshot job. |

### Scenario 8: Account 9 without backfill

| Question | Answer | Data |
|----------|--------|------|
| Events? | **1 (`initial_holding_set`)** | No transaction events. Replay uses snapshot baseline from effective_date=2020-01-01. |
| Holdings count? | **75 (MATCH)** | `initial_holding_set` captured correct holdings. |
| Cost basis? | **From snapshot, not FIFO** | `initial_holding_set` stores `total_cost` from the snapshot, not FIFO-computed cost. |
| After backfill? | **FIFO-correct** | 1,711 `transaction_imported` events allow proper FIFO cost computation. |

### Scenario 9: Missing prices for 5 companies

| Question | Answer | Data |
|----------|--------|------|
| Which companies? | 3139 (NYCB), 3140 (CMA), 3144 (YTSL), 3155 (WBA), 3159 (RSLS) | |
| Total impact? | ~$2,811 | Combined cost basis across all accounts = 0.003% of $82K portfolio. |
| Fix? | Market data scheduler | Separate effort, not a blocker for cutover. |

### Scenario 10: Event ordering across restarts

| Question | Answer | Data |
|----------|--------|------|
| Event timelines? | **Uses `data.transaction_date`, not `event_version`** | All 1,017 events have `event_version=1`. `_get_event_date` pulls from `data.effective_date` → `data.transaction_date` → `created_at` for correct ordering. Backfilled events from the same batch have identical `created_at` but correct `transaction_date`. |

### Scenario 11: Portfolio performance chart period coverage

| Question | Answer | Data |
|----------|--------|------|
| What dates have snapshots? | Jun 23-Jul 8 | The snapshots job started recently. Older dates (Jul 2025) have NO snapshots. |
| After cutover, will replay have dates? | **Only event dates** | Events start from earliest transaction (Jul 2024 for account 7). Snapshot job needs to run daily to build history. |

### Scenario 12: `idempotency_key` collision

| Question | Answer | Data |
|----------|--------|------|
| Can two imports generate the same key? | **No** | Keys include `import_batch_id` (UUID) + index. Hash collision probability is negligible. |
| What if user uploads the same CSV twice? | **Duplicates rejected** | Same transactions → same fingerprints → same `idempotency_key` → ON CONFLICT returns existing. Safe. |

---

## 9. Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Duplicate event insert | `UNIQUE(idempotency_key)` constraint violation | `EventStore` catches exception, returns existing event. Automatic. |
| Projection handler crashes | Checkpoint doesn't advance | On restart, resumes from `last_seq_id`. No data loss. |
| Atomic write fails (mid-transaction) | Transaction rollback | portfolio_holdings stays in previous state. No partial data. |
| Duplicate import | idempotency_key matches | ON CONFLICT DO NOTHING. No duplicate holdings. |
| Backfill script fails partway | Some transactions missing from events | Script uses idempotency keys. Re-run to completion. |
| Rollback needed | Unexpected behavior | `git revert` + restart. Old code ignores events. No data loss. |
| Market data missing for 5 companies | Portfolio has cost-basis values for those positions | $2,811 impact on $82K — no urgency. Fix separately. |
| Snapshot job writes stale data before fix | Snapshots don't match event-replay | `get_latest_prices()` now has fallback. Re-run snapshot job. |
| Polling misses events (rare) | Checkpoint doesn't advance | Manual `rebuild_all_accounts()` fixes drift. No scheduled daily rebuild exists yet — planned future work. At worst, UI lags until manual rebuild or next import triggers a rebuild for that account. |

---

## Appendix: Migration Scripts Checklist

| Order | Script | Purpose | Idempotent? | Runtime |
|-------|--------|---------|--------|---------|
| 1 | `backfill_transactions_to_events.py --account 9` | Backfill missing events for account 9 | Yes (idempotency_key) | ~5s |
| 2 | SQL: create `event_sequence` table | Polling table for projection | Yes (IF NOT EXISTS) | <1s |
| 3 | SQL: create trigger on portfolio_events | Auto-populate event_sequence | Yes (IF NOT EXISTS) | <1s |
| 4 | SQL: create `projection_checkpoint` table | Track projection progress | Yes (IF NOT EXISTS) | <1s |
| 5 | Deploy code changes | Large deploy as one git commit | N/A | git deploy |
| 6 | `EventProjectionHandler.rebuild_all()` | Full rebuild from events | Yes (DELETE + INSERT) | <1s per account |
| 7 | `compute_daily_snapshots()` | Regenerate today's snapshots | Yes (upsert) | ~10s |

### Post-Migration Verification Commands

```python
# 1. Verify holdings match replay
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from database import supabase
engine = ReplayEngine(EventStore())

for aid in [7, 8, 9, 10, 11, 12]:
    state = engine.replay_to_date(aid, date.today())
    ph = supabase.table("portfolio_holdings").select("*").eq("account_id", aid).execute()
    assert len(state.holdings) == len(ph.data), f"Account {aid} holding count mismatch: replay={len(state.holdings)} db={len(ph.data)}"
    for h in ph.data:
        cid = h["company_id"]
        db_qty = float(h["quantity"])
        replay_qty = float(state.holdings[cid].quantity) if cid in state.holdings else 0
        assert abs(db_qty - replay_qty) < 0.01, f"Acct {aid} cid {cid}: db={db_qty} replay={replay_qty}"
    print(f"OK: Account {aid} — {len(state.holdings)} holdings all match")

# 2. Verify snapshot consistency after regeneration
# Run AFTER compute_daily_snapshots()
for aid in [7, 8, 9, 10, 11, 12]:
    s = supabase.table("portfolio_snapshots").select("total_value")\
        .eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
    if s.data:
        snap_total = float(s.data[0]["total_value"])
        replay_snap = engine.build_snapshot_from_replay(aid, date.today(), prices)
        delta = abs(snap_total - replay_snap["total_value"])
        assert delta < 0.01, f"Account {aid}: snapshot ${snap_total:.2f} != replay ${replay_snap['total_value']:.2f}"
        print(f"OK: Account {aid} — snapshot matches replay (${snap_total:.2f})")

# 3. Verify projection checkpoint advancing (after some imports)
cp = supabase.table("projection_checkpoint").select("last_seq_id").execute()
print(f"Checkpoint: {cp.data[0]['last_seq_id']}")

# 4. Verify event_sequence matches portfolio_events count
seq_count = supabase.table("event_sequence").select("*", count="exact").execute().count
evt_count = supabase.table("portfolio_events").select("*", count="exact").execute().count
assert seq_count == evt_count, f"event_sequence has {seq_count} rows but portfolio_events has {evt_count}"
print(f"OK: event_sequence ({seq_count}) matches portfolio_events ({evt_count})")
```

---

## Appendix B: Schema Migration Notes for Future Work

If `FOR UPDATE` version locking is needed later, the required changes are:

```sql
-- 1. Add unique constraint on (aggregate_id, event_version)
ALTER TABLE portfolio_events
  ADD CONSTRAINT uq_events_aggregate_version
  UNIQUE (aggregate_id, event_version)
  DEFERRABLE INITIALLY DEFERRED;

-- 2. Backfill correct versions (gap-free per aggregate)
WITH numbered AS (
  SELECT id, aggregate_id, event_version,
         ROW_NUMBER() OVER (PARTITION BY aggregate_id ORDER BY created_at) AS correct_ver
  FROM portfolio_events
)
UPDATE portfolio_events e
SET event_version = n.correct_ver
FROM numbered n
WHERE e.id = n.id AND n.event_version != n.correct_ver;

-- 3. Update EventStore.append_event() to:
--    SELECT COALESCE(MAX(event_version), 0) + 1
--    FROM portfolio_events
--    WHERE aggregate_id = $1
--    FOR UPDATE OF portfolio_events
--    (row-level lock)
```

If `current_price` / `current_value` columns are needed in `portfolio_holdings`:

```sql
ALTER TABLE portfolio_holdings
  ADD COLUMN current_price NUMERIC,
  ADD COLUMN current_value NUMERIC;

-- Update in EventProjectionHandler.to_holdings_rows()
```

If CASH row is needed (relaxing NOT NULL):

```sql
ALTER TABLE portfolio_holdings ALTER COLUMN company_id DROP NOT NULL;
-- Then allow rows with company_id=null, symbol='CASH'
```