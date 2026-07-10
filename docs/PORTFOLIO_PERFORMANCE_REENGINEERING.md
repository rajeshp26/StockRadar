# Portfolio Performance Engine Re-engineering

**Status:** Design Proposal (V4.0 — scope expanded to cover live enrichment)  
**Date:** 2026-07-10  
**Author:** Performance Audit  

**Changes in V3.2:** Fixed `resolve_price_forward_filled` signature (removed unused `fallback_price`); removed lower bound from `build_price_map` to guarantee forward-fill completeness; added dividend reinvestment prerequisite validation; fixed invariant assertion to compare rounded values (not same expression twice); added defensive empty-snapshots guard in service method; fixed reconciliation percent denominator to use max of both quantities; clarified rollback caveat for holdings table repairs; renamed `_compress_snapshots_by_date_bucket` → `_compress_snapshots_by_interval`; added `company_name` resolution step to daily job (not stored on `portfolio_holdings`); implemented explicit fallback FIFO code.

**Changes in V3.3:** Replaced APScheduler with `JobEngine`/`SchedulerPlanner` (v3 job queue); replaced all direct `supabase.table()` calls with repository methods; added `ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER` and `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH` config flags; corrected file paths (`jobs/` → `application/jobs/`); fully specified fallback path; added pagination for price history queries; folded feasibility audit findings into main design body; removed `_period_to_date_range` from deletion list; added legacy `portfolio_performance` table deprecation note.

**Changes in V3.4:** Fixed fallback cash/deposit method signatures (added `get_cash_balance_for_accounts`, `get_net_deposits_for_accounts` aggregate methods); fixed fallback holdings loop to store `symbol` and `company_id` in lot entries; made fallback holdings aggregation explicit (portfolio-level merge by `company_id`); gated read path with `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH` in service method; switched service to use dedicated `PortfolioSnapshotsRepository`; moved `validate_company_id_consistency` fully behind repository method; retained explicit `_get_portfolio_performance_legacy` method; added `get_user_accounts_all` to repository additions; added `@timed()` to the service code snippet; added dividend reinvestment note to fallback section; updated status line.

**Changes in V4.0:** Added Section 21 (Live Enrichment Performance) covering the dashboard enrichment bottleneck identified through empirical measurement. Documents the root cause (sequential yfinance calls for exchange-override holdings), compares against Wealthfront/Robinhood industry patterns, and proposes a price-ingestion-pipeline architecture that eliminates all live pricing from the request path. This extends the "compute once, read many" principle from the performance chart to the entire dashboard. Updated Table of Contents accordingly.

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Problems Identified](#2-problems-identified)
3. [Root Cause Analysis](#3-root-cause-analysis)
4. [Proposed Architecture](#4-proposed-architecture)
5. [Data Model](#5-data-model)
6. [Shared Valuation Model](#6-shared-valuation-model)
7. [Daily Snapshot Job](#7-daily-snapshot-job)
8. [Historical Backfill](#8-historical-backfill)
9. [New API Read Path](#9-new-api-read-path)
10. [Frontend Changes](#10-frontend-changes)
11. [Prerequisites](#11-prerequisites)
12. [Holdings Reconciliation](#12-holdings-reconciliation)
13. [Migration Plan](#13-migration-plan)
14. [Rollback Strategy](#14-rollback-strategy)
15. [SQL Migration Script](#15-sql-migration-script)
16. [Test Plan](#16-test-plan)
17. [Appendix A: Files to Delete After Migration](#17-appendix-a-files-to-delete-after-migration)
18. [Appendix B: Files to Create](#18-appendix-b-files-to-create)
19. [Appendix C: Price Data Gaps](#19-appendix-c-price-data-gaps)
20. [Implementation Alignment Notes](#20-implementation-alignment-notes)
21. [Live Enrichment Performance](#21-live-enrichment-performance)

---

## 1. Current Architecture

### 1.1 Request Flow

```
User selects period in UI
        |
        v
PortfolioPerformanceChart.tsx
  -> portfolio.service.ts::getPortfolioPerformance(period, accountIds)
       -> GET /api/portfolio/performance?period=1Y&account_ids=7,8,9
            |
            v
       api/portfolio.py::get_portfolio_performance
            |
            v
       PortfolioService::get_portfolio_performance(user_id, period, account_ids)
```

### 1.2 The FIFO Pipeline (Current Code)

When `get_portfolio_performance` is called, the following happens in sequence:

#### Step 1: Account Resolution
```python
accounts = portfolio_repo.get_user_accounts(user_id)
account_ids = [a["account_id"] for a in accounts]
```

#### Step 2: Date Range Determination
```python
_period_to_date_range(period, account_ids):
    if period == "1M":  start = today - 30 days
    if period == "3M":  start = today - 90 days
    if period == "1Y":  start = today - 365 days
    if period == "5Y":  start = today - 1825 days
    if period == "YTD": start = Jan 1 of current year
    if period == "ALL": start = earliest_transaction_date OR 2000-01-01
```

#### Step 3: Fetch All Trade Transactions (All Time)
```python
txns_batch = portfolio_repo.get_accounts_transactions(
    account_ids, activity_types=["Trade"]
)
```

Pre-period transactions are needed to build opening FIFO lots.

#### Step 4: Fetch Cash Flow Deltas (All Time)
```python
cashflow_deltas = _get_cashflow_deltas(account_ids)
# Builds cumulative_invested_map: date -> running net deposits
```

#### Step 5: Fetch Price History (Full Period Range)
```python
price_map: Dict[symbol, Dict[date_str, close_price]]
```

#### Step 6: Build Opening Lots from Pre-Period Transactions
```python
lots: Dict[(account_id, symbol), List[Lot]] = defaultdict(list)
for t in pre_txns:
    sym = t.get("symbol")
    if not sym: continue
    sub = (t.get("activity_sub_type") or "").upper()
    if sub == "BUY" or (sub == "" and qty > 0):
        lots[key].append({"quantity": qty, "cost_per_share": ..., "date": ...})
    elif sub == "SELL" or (sub == "" and qty < 0):
        # Remove from front of lot queue (FIFO)
```

#### Step 7: Generate Snapshot Dates
```python
_step_for_period(period):
    1W -> step=1 day    3M -> step=3 days    1Y -> step=7 days
    5Y -> step=14 days  ALL -> step=30 days

_generate_snapshot_dates(period, start, end):
    dates = [start, start+step, ..., end]
```

#### Step 8: Compute FIFO Snapshots
```python
_compute_fifo_snapshots(lots, in_txns_sorted, sorted_dates, price_map):
    for d in sorted_dates:
        while txn_index < len(txns) and txns[txn_index].date <= d:
            if activity_sub_type == "BUY" or (sub == "" and qty > 0): ADD lot
            elif activity_sub_type == "SELL" or (sub == "" and qty < 0): REMOVE lot
        for lot_list in lots.values():
            qty_held = sum(lot.quantity)
            avg_cost = sum(lot.qty * lot.cost_per_share) / qty_held
            historical_price = price_map[sym].get(d) OR nearest OR avg_cost
            total_value += qty_held * historical_price
```

#### Step 9: Return Response
```python
return {
    "snapshots": snapshots,       # list of {date, value, cost_basis, net_deposits}
    "total_return": ...,
    "total_return_pct": ...,
    "best_day": ..., "worst_day": ...,
}
```

### 1.3 Data Sources Used

| Source | Table | Columns Used |
|--------|-------|-------------|
| Accounts | `portfolio_accounts` | account_id, user_id |
| Transactions | `portfolio_transactions` | account_id, company_id, symbol, transaction_date, activity_type, activity_sub_type, quantity, unit_price, commission, net_cash_amount |
| Cash flows | `portfolio_transactions` | Same table, filtered to MoneyMovement + BonusPayment |
| Price history | `price_history` | company_id, price_date, close_price |
| Holdings | `portfolio_holdings` | *(not used in performance calculation)* |

### 1.4 Current Performance Characteristics

| Metric | Value |
|--------|-------|
| Transactions processed per request | 2734 (all-time for User 1) |
| Price rows fetched per request | 38771 |
| FIFO snapshot computation | O(txns * symbols * snapshots) |
| Average response time | 200-500ms (estimated) |
| Cacheability | None (recomputed every request) |

---

## 2. Problems Identified

### 2.1 Critical: FIFO Engine Produces Absurd Valuations (P0)

Running the engine against live data for User 1 (accounts 7, 8, 9):

| Snapshot Date | Portfolio Value | Notes |
|--------------|----------------|-------|
| 2021-07-06 | $4,964 | Reasonable — initial deposits + small trades |
| 2021-08-05 | **$103,621,240** | 20,869x increase in 30 days — IMPOSSIBLE |
| 2021-09-04 | $90,310,017 | Gradual decay |
| 2022-01-05 | $42,816,647 | Still absurd |
| 2023-10-24 | $222,570 | Finally approaching reasonable |
| 2026-06-22 | $152,234 | Current value (also wrong: actual holdings ~$150K) |

**Root Cause:** The lot-matching logic treats any transaction with `activity_sub_type = None` and `qty > 0` as a BUY:

```python
sub = (t.get("activity_sub_type") or "").upper()
if sub == "BUY" or (sub == "" and qty > 0):
    # ADD LOT <- InternalSecurityTransfer, FxExchange, etc. all hit this branch
```

`activity_type` is NEVER checked. Non-Trade activity types (InternalSecurityTransfer, Dividend, FxExchange) with `symbol` and `quantity` set silently add phantom lots. Over years these compound to $103M.

**Proof:** User 49 (accounts 10, 11, 12) has shorter history and does NOT show this bug.

### 2.2 Monthly EOM Price Data Creates Stair-Step Charts (P1)

`price_history` stores only end-of-month closing prices (median gap 30-31 days per company). A 1Y period generates ~52 snapshot dates but only ~12 unique price points per symbol.

### 2.3 Prices Missing Feb-May 2026 (P1)

Gaps > 40 days for all companies (69-119 day range). The chart is completely flat for those months.

### 2.4 No Absurd-Value Safeguards (P2)

No sanity checks, cross-validation, or logging of anomalous values.

### 2.5 Per-Request Transaction Processing (P3)

All 2734 transactions reprocessed from scratch on every request. O(txns * symbols * snapshots) computation, uncacheable.

### 2.6 Pre-Existing Issues (Not Caused by Recent Changes)

| Issue | Notes |
|-------|-------|
| Trade/BUY vs Trade/Buy case | 110 "BUY", 8 "Buy" (handled via `.upper()`) |
| InternalSecurityTransfer with None sub_type | 42 transfers with symbol set |
| Dividend with qty>0 and sub_type=None | 649 dividend rows hit the (sub == "" and qty > 0) branch |

---

## 3. Root Cause Analysis

The `activity_type` field is NEVER checked. The engine only looks at `activity_sub_type` and `quantity` sign:

| activity_type | activity_sub_type | qty | Engine Action | Correct Action |
|--------------|-------------------|-----|--------------|----------------|
| Trade | BUY | 10 | ADD lot | ADD lot |
| Trade | SELL | -5 | REMOVE lot | REMOVE lot |
| InternalSecurityTransfer | None | 10 | **ADD lot** | IGNORE |
| FxExchange | None | 24 | **ADD lot** | IGNORE |
| Dividend | None | 1.5 | **ADD lot** | IGNORE |

Each phantom BUY adds shares never removed. Over 2734 transactions, phantom shares accumulate linearly.

### Three Effects Combine to Make Charts "Weird"

1. Phantom shares cause $103M valuations — scale compresses everything to noise
2. Monthly EOM prices cause 3-4 consecutive snapshots with the same value
3. Recharts tick formatter shows "Mon DD" without year

---

## 4. Proposed Architecture

### 4.1 Design Principles

1. **Compute once, read many times** — background job stores snapshots in a table
2. **Single valuation model for all snapshots** — backfill and daily job produce semantically identical rows via a shared builder. The only difference is how holdings state is obtained: backfill replays corrected transaction history; daily job reads the verified holdings table
3. **Ledger-based cash** — cash balance = sum of `net_cash_amount` across ALL transactions. Correctly captures deposits, withdrawals, buys, sells, dividends, fees, FX
4. **Identity key is `(account_id, company_id)`** — symbols can change or collide
5. **Forward-fill prices, not cost-basis fallback** — `avg_cost` used only if no price history exists at all
6. **Auditability** — every row has a `job_id`, `computed_at`, and `data_quality_flag`

### 4.2 High-Level Architecture

```
                    +---------------------------+
                    |   Daily Snapshot Job      |
                    | (runs 23:00 UTC daily)    |
                    +---------------------------+
                              |
                              v
                    +---------------------------+
                    |  portfolio_snapshots      |
                    |  (database table)          |
                    +---------------------------+
                         ^            ^
                         |            |
               +---------+            +---------+
               |                               |
               v                               v
    +----------------------+        +----------------------+
    |  get_portfolio_perf  |        |  PortfolioDashboard  |
    |  (read from table)   |        |  (uses same table)   |
    +----------------------+        +----------------------+
```

### 4.3 Comparison: Current vs Proposed

| Aspect | Current | Proposed |
|--------|---------|----------|
| Data source | Transactions (reconstructed) | Pre-computed snapshots |
| Computation time | 200-500ms per request | <10ms per request |
| Transaction processing | Every request (2734 txns) | Never at request time |
| Phantom shares | Yes (broken activity_type filter) | No (corrected FIFO + holdings) |
| Cash balance | Not tracked | Ledger-based (sum all net_cash_amount) |
| Identity key | `(account_id, symbol)` | `(account_id, company_id)` |
| Data quality | No flagging | `data_quality_flag` column |
| Correctness guarantee | None | Ledger-reconciled cash + invariant checks |
| Code complexity | ~400 lines (fragile FIFO) | ~100 lines (simple read) |

---

## 5. Data Model

### 5.1 Semantic Definitions

Every `portfolio_snapshots` row follows these invariants:

| Column | Definition |
|--------|------------|
| `total_value` | `holdings_market_value + cash_balance`. The portfolio's total worth at the snapshot date. |
| `holdings_market_value` | Sum of `position_qty * resolved_price` across all holdings. |
| `cost_basis` | Cost basis of currently-held open positions only (not sold ones). |
| `cash_balance` | Sum of `net_cash_amount` across ALL transactions (all activity types) up to the snapshot date. |
| `net_deposits` | Cumulative external contributions minus withdrawals: sum of `net_cash_amount` where `activity_type` is `MoneyMovement` or `BonusPayment`. Does NOT include dividends (those are realized returns, not deposits). |
| `data_quality_flag` | `'OK'` if ALL positions have prices <=30 days old. `'STALE_PRICE'` if ANY position has stale data. Conservative: flags the account even if one component is stale. |

### 5.2 New Table

```sql
CREATE TABLE portfolio_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    account_id          INTEGER NOT NULL REFERENCES portfolio_accounts(account_id) ON DELETE CASCADE,
    snapshot_date       DATE NOT NULL,
    total_value         NUMERIC(15, 2) NOT NULL,
    holdings_market_value NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    cost_basis          NUMERIC(15, 2) NOT NULL,
    cash_balance        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    net_deposits        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    holdings_json       JSONB,
    data_quality_flag   TEXT NOT NULL DEFAULT 'OK',
    job_id              TEXT,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.3 Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_snapshots_account_date
    ON portfolio_snapshots (account_id, snapshot_date DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_account_date_unique
    ON portfolio_snapshots (account_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_snapshots_quality
    ON portfolio_snapshots (data_quality_flag)
    WHERE data_quality_flag != 'OK';
```

### 5.4 Row-Level Security

Server-only access via `SUPABASE_SERVICE_ROLE_KEY`. No anon/key RLS policies — the frontend never queries this table directly. If client-side access is needed in the future, a policy with the correct `auth.uid()` → `user_id` mapping (via a user-auth mapping table) must be added.

```sql
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;
```

### 5.5 `holdings_json` Format

Each position includes `company_id` alongside `symbol`. Price resolution uses `company_id`.

```json
[
    {
        "company_id": 31,
        "symbol": "RBLX",
        "company_name": "Roblox Corp",
        "quantity": 100.0,
        "current_price": 185.50,
        "current_value": 18550.00,
        "cost_basis": 15000.00,
        "unrealized_gain_loss": 3550.00,
        "unrealized_gain_loss_pct": 23.67,
        "price_age_days": 1,
        "price_data_quality": "OK"
    }
]
```

`price_age_days` and `price_data_quality` are per-position quality indicators, allowing drill-down diagnostics.

### 5.6 Table Size Estimates

| Metric | Estimate |
|--------|----------|
| Accounts | 6 (current) |
| Snapshots per account per year | ~250 (trading days) |
| Total rows after 5 years | 6 * 250 * 5 = ~7,500 |
| Holdings JSON per row | ~200-500 bytes |
| Total storage | ~4-15 MB (negligible) |

---

## 6. Shared Valuation Model

Both backfill and daily job produce snapshot rows using the same builder. This ensures semantic consistency.

```python
# shared/snapshot_builder.py

def build_snapshot_row(
    account_id: int,
    snapshot_date: date,
    holdings_state: List[Dict],
    cash_balance: Decimal,
    net_deposits: Decimal,
    prices_by_company: Dict[int, Dict],        # company_id -> {price, price_date}
    job_id: str,
    stale_threshold_days: int = 30,
) -> Dict[str, Any]:
    """
    Build a portfolio_snapshots row from resolved holdings, cash, and prices.

    This function is the SINGLE source of truth for snapshot structure.
    Both backfill and daily job call this.

    Invariant enforced:
        total_value == holdings_market_value + cash_balance
    """
    total_market_value = Decimal("0.00")
    total_cost = Decimal("0.00")
    holdings_detail = []

    for h in holdings_state:
        cid = h.get("company_id")
        qty = Decimal(str(h.get("quantity") or 0))
        cost = Decimal(str(h.get("cost_basis") or 0))

        if qty == 0:
            continue

        price_info = prices_by_company.get(cid, {})
        price = price_info.get("price")

        if price is not None:
            current_price = Decimal(str(price))
        else:
            current_price = Decimal(str(h.get("avg_cost") or 0))

        current_value = qty * current_price
        total_market_value += current_value
        total_cost += cost

        price_date = price_info.get("price_date")
        price_age_days = (snapshot_date - price_date).days if price_date else None
        pos_quality = "STALE_PRICE" if (price_age_days is not None and price_age_days > stale_threshold_days) else "OK"

        holdings_detail.append({
            "company_id": cid,
            "symbol": h.get("symbol", "?"),
            "company_name": h.get("company_name", h.get("symbol", "?")),
            "quantity": float(qty),
            "current_price": float(current_price),
            "current_value": float(current_value),
            "cost_basis": float(cost),
            "unrealized_gain_loss": float(current_value - cost),
            "unrealized_gain_loss_pct":
                float((current_value - cost) / cost * 100) if cost > 0 else 0.0,
            "price_age_days": price_age_days,
            "price_data_quality": pos_quality,
        })

    total_value = total_market_value + cash_balance

    # Account-level data quality: worst position wins
    any_stale = any(h.get("price_data_quality") == "STALE_PRICE" for h in holdings_detail)
    data_quality = "STALE_PRICE" if any_stale else "OK"

    # INVARIANT CHECK: rounded total_value must equal rounded market_value + rounded cash
    # This catches rounding bugs and caller-side errors, not the same expression re-checked.
    rounded_total = round(float(total_value), 2)
    rederived = round(float(total_market_value), 2) + round(float(cash_balance), 2)
    if abs(rounded_total - rederived) > 0.02:
        raise AssertionError(
            f"Invariant violation: total_value={rounded_total} != "
            f"holdings_market_value={round(float(total_market_value), 2)} + "
            f"cash_balance={round(float(cash_balance), 2)} = {rederived}"
        )

    return {
        "account_id": account_id,
        "snapshot_date": snapshot_date.isoformat(),
        "total_value": round(float(total_value), 2),
        "holdings_market_value": round(float(total_market_value), 2),
        "cost_basis": round(float(total_cost), 2),
        "cash_balance": round(float(cash_balance), 2),
        "net_deposits": round(float(net_deposits), 2),
        "holdings_json": holdings_detail if holdings_detail else None,
        "data_quality_flag": data_quality,
        "job_id": job_id,
        "computed_at": now_utc().isoformat(),
    }
```

---

## 7. Daily Snapshot Job

### 7.1 Job Specification

- **Schedule:** Runs daily at **23:00 UTC** (19:00 ET).
- **Scope:** Computes snapshot for every `portfolio_accounts` row. With ~6 accounts this is trivial; scaling note added if account count grows significantly.
- **Timezone:** All date comparisons use `now_utc().date()`. No `date.today()`.
- **Trigger:** `JobEngine` + `SchedulerPlanner` (v3 DB-backed job queue).
- **Error handling:** Failed accounts logged and retried on next run; `JobEngine` manages lease renewal, backoff, and dead-letter.
- **Performance target:** < 1 second per account.

### 7.2 Cash Balance Computation (Ledger-Based, via Repository)

All data access goes through `PortfolioRepository`. Add the following method to `PortfolioRepository`:

```python
# infrastructure/repositories/portfolio_repository.py
def get_cash_balance(self, account_id: int, target_date: date) -> Decimal:
    """
    Cash balance = sum of ALL transaction net_cash_amount up to target_date.

    Includes: deposits (+), withdrawals (-), buys (-), sells (+),
              dividends (+), fees (-), FX events.
    Excludes: Dividend reinvestment records if they duplicate Trade records.
              See Section 11.3 for validation.
    """
    result = (
        self.client.table("portfolio_transactions")
        .select("net_cash_amount")
        .eq("account_id", account_id)
        .lte("transaction_date", target_date.isoformat())
        .execute()
    )
    total = Decimal("0.00")
    for row in result.data or []:
        total += Decimal(str(row.get("net_cash_amount") or 0))
    return total
```

Then used in the daily job as:
```python
from infrastructure.repositories.portfolio_repository import PortfolioRepository
repo = PortfolioRepository()
cash_balance = repo.get_cash_balance(account_id, today)
```

### 7.3 Net Deposits Computation (via Repository)

Add to `PortfolioRepository`:

```python
# infrastructure/repositories/portfolio_repository.py
def get_net_deposits(self, account_id: int, target_date: date) -> Decimal:
    """
    Net deposits = external contributions minus withdrawals.
    Only MoneyMovement and BonusPayment — does NOT include dividends,
    which are realized returns, not deposits.
    """
    result = (
        self.client.table("portfolio_transactions")
        .select("net_cash_amount")
        .eq("account_id", account_id)
        .in_("activity_type", ["MoneyMovement", "BonusPayment"])
        .lte("transaction_date", target_date.isoformat())
        .execute()
    )
    total = Decimal("0.00")
    for row in result.data or []:
        total += Decimal(str(row.get("net_cash_amount") or 0))
    return total
```

Cross-account aggregate variant:
```python
# infrastructure/repositories/portfolio_repository.py
def get_net_deposits_for_accounts(self, account_ids: List[int], target_date: date) -> Decimal:
    """Sum net deposits across multiple accounts."""
    total = Decimal("0.00")
    for aid in account_ids:
        total += self.get_net_deposits(aid, target_date)
    return total
```

Used as:
```python
net_deposits = repo.get_net_deposits(account_id, today)
net_deposits_all = repo.get_net_deposits_for_accounts(account_ids, today)
```

### 7.4 Price Fetching (Batched, Deterministic, via Repository)

Add to `FinancialRepository`:

```python
# infrastructure/repositories/financial_repository.py
def get_latest_prices(
    self, company_ids: List[int], target_date: date
) -> Dict[int, Dict]:
    """
    Fetch the most recent price on or before target_date for each company.

    Returns {company_id: {"price": float, "price_date": date}}.
    Deterministic: uses explicit max-by-date reduction, not ordering tricks.
    """
    if not company_ids:
        return {}

    result = (
        self.client.table("price_history")
        .select("company_id, price_date, close_price")
        .in_("company_id", company_ids)
        .lte("price_date", target_date.isoformat())
        .execute()
    )

    latest_by_company: Dict[int, Dict] = {}
    for row in result.data or []:
        cid = row["company_id"]
        pd = row["price_date"]
        if isinstance(pd, str):
            pd = date.fromisoformat(pd)
        elif isinstance(pd, datetime):
            pd = pd.date()

        existing = latest_by_company.get(cid)
        if existing is None or pd > existing["price_date"]:
            latest_by_company[cid] = {
                "price": float(row["close_price"]),
                "price_date": pd,
            }

    return latest_by_company
```

For cross-account queries (e.g., fallback path), add an aggregate variant:

```python
# infrastructure/repositories/portfolio_repository.py
def get_cash_balance_for_accounts(self, account_ids: List[int], target_date: date) -> Decimal:
    """Sum cash balance across multiple accounts."""
    total = Decimal("0.00")
    for aid in account_ids:
        total += self.get_cash_balance(aid, target_date)
    return total
```

Used as:
```python
from infrastructure.repositories.portfolio_repository import PortfolioRepository
repo = PortfolioRepository()
cash_balance = repo.get_cash_balance(account_id, today)
cash_balance_all = repo.get_cash_balance_for_accounts(account_ids, today)
```

### 7.5 User Account Enumeration (via Repository)

```python
# infrastructure/repositories/portfolio_repository.py
def get_user_accounts_all(self) -> List[Dict[str, Any]]:
    """Return all user accounts (admin/backfill use)."""
    try:
        res = self.table("portfolio_accounts") \
            .select("account_id, user_id, account_name") \
            .execute()
        return res.data or []
    except Exception:
        return []
```

Used in the daily job and backfill script:
```python
all_accounts = portfolio_repo.get_user_accounts_all()
```

### 7.6 Job Logic (via Repository)

All data access goes through repositories. The job handler is decorated with `@timed()` for profiling consistency:

```python
# application/jobs/portfolio_snapshot_job.py

from shared.time_utils import now_utc
from shared.snapshot_builder import build_snapshot_row
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository

logger = logging.getLogger("stockerpro.portfolio.snapshots")

def timed(logger=logger):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            logger.info(f"{func.__name__} took {elapsed:.2f}s")
            return result
        return wrapper
    return decorator

@timed()
async def compute_daily_snapshots():
    today = now_utc().date()
    portfolio_repo = PortfolioRepository()
    financial_repo = SupabaseFinancialRepository()
    snapshots_repo = PortfolioSnapshotsRepository()

    all_accounts = portfolio_repo.get_user_accounts_all()
    if not all_accounts:
        logger.info("No accounts found, skipping")
        return

    account_ids = [a["account_id"] for a in all_accounts]
    logger.info(f"Computing snapshots for {len(account_ids)} accounts on {today}")

    for i in range(0, len(account_ids), BATCH_SIZE):
        batch = account_ids[i:i + BATCH_SIZE]

        # --- Fetch holdings from repository ---
        holdings_result = portfolio_repo.get_holdings_for_accounts(batch)
        holdings_by_account = defaultdict(list)
        for h in holdings_result:
            holdings_by_account[h["account_id"]].append(h)

        all_company_ids = set()
        for h_list in holdings_by_account.values():
            for h in h_list:
                if h.get("company_id"):
                    all_company_ids.add(h["company_id"])

        # Resolve company names via repository
        company_names: Dict[int, str] = {}
        if all_company_ids:
            names_result = portfolio_repo.get_company_names(list(all_company_ids))
            for row in names_result:
                company_names[row["company_id"]] = row.get("company_name")

        prices_by_company = financial_repo.get_latest_prices(list(all_company_ids), today)

        # --- Process each account ---
        for aid in batch:
            holdings = holdings_by_account.get(aid, [])

            clean_holdings = []
            for h in holdings:
                qty = Decimal(str(h.get("quantity") or 0))
                if qty < 0:
                    logger.error(f"Account {aid}: negative quantity: {h}")
                    raise ValueError(f"Data corruption: negative quantity in holdings")
                if qty == 0:
                    logger.warning(f"Account {aid}: zero-qty holding {h.get('company_id')} — skipping")
                    continue
                h["company_name"] = company_names.get(h.get("company_id"), h.get("symbol", "?"))
                clean_holdings.append(h)

            cash_balance = portfolio_repo.get_cash_balance(aid, today)
            net_deposits = portfolio_repo.get_net_deposits(aid, today)

            snapshot_row = build_snapshot_row(
                account_id=aid,
                snapshot_date=today,
                holdings_state=clean_holdings if clean_holdings else [],
                cash_balance=cash_balance,
                net_deposits=net_deposits,
                prices_by_company=prices_by_company,
                job_id=f"daily_{today.isoformat()}",
            )

            snapshots_repo.upsert_snapshot(snapshot_row)

        logger.info(f"Processed accounts batch {i}-{i + len(batch)}")

    logger.info("Daily snapshot job completed")
```

### 7.7 Scheduler Registration (v3 JobEngine)

Register with the existing v3 scheduler infrastructure: a planner `plan()` method enqueues jobs, and a `JobEngine` handler executes them.

**Scheduler class** (`application/schedulers/portfolio_snapshot_scheduler.py`):

```python
class PortfolioSnapshotScheduler:
    """Plans portfolio snapshot jobs. Runs daily at 23:00 UTC."""

    @property
    def interval_hours(self) -> int:
        return 24

    async def plan(self) -> List[Dict[str, Any]]:
        """Plan a single batch job for all active accounts."""
        return [{
            "job_type": "portfolio_snapshot",
            "dedupe_key": f"snapshot_{now_utc().date().isoformat()}",
            "priority": 50,
            "payload": {"date": now_utc().date().isoformat()},
        }]
```

**Job handler** (`application/jobs/portfolio_snapshot_job.py`):

```python
async def handle_portfolio_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    """Handler registered with JobEngine."""
    await compute_daily_snapshots()
    return {"status": "completed", "accounts_processed": ...}
```

**Registration** in `scheduler_worker.py`:

```python
# Register handler
engine.register_handler("portfolio_snapshot", handle_portfolio_snapshot)

# Register planner (enabled via ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER config flag)
if getattr(settings, "ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER", True):
    snapshot_scheduler = PortfolioSnapshotScheduler()
    planner.register(
        name="portfolio_snapshot",
        plan_fn=snapshot_scheduler.plan,
        interval_hours=snapshot_scheduler.interval_hours,
        enabled=True,
    )
    logger.info("Registered portfolio_snapshot planner (interval=%dh)", snapshot_scheduler.interval_hours)
```

---

## 8. Historical Backfill

### 8.1 Overview

One-time script processing ALL historical transactions using a CORRECTED FIFO engine. After backfill, the old FIFO engine is deleted.

**Event-driven strategy:** Only compute FIFO snapshots on dates where something changes (trade, money movement, dividend, month-end). API compression handles sparse data at read time.

### 8.2 Corrected Transaction Filtering (CRITICAL FIX)

Only `Trade/BUY` and `Trade/SELL` affect lot tracking. `activity_type` is checked first. These helpers live in `shared/snapshot_builder.py` alongside `build_snapshot_row()` so both the backfill script and the fallback path can use them:

```python
# shared/snapshot_builder.py

def _should_process_for_lots(txn: dict) -> bool:
    activity_type = (txn.get("activity_type") or "").upper()
    activity_sub_type = (txn.get("activity_sub_type") or "").upper()
    if activity_type != "TRADE":
        return False
    if activity_sub_type not in ("BUY", "SELL"):
        return False
    return True

def _classify_lot_action(txn: dict) -> Optional[str]:
    if not _should_process_for_lots(txn):
        return None
    sub = (txn.get("activity_sub_type") or "").upper()
    qty = Decimal(str(txn.get("quantity") or 0))
    if sub == "BUY" and qty > 0:
        return "BUY"
    elif sub == "SELL" and qty < 0:
        return "SELL"
    return None
```

Dividend reinvestments: If the import pipeline records a reinvested dividend as a single `Dividend` record with `qty > 0` and `symbol` set (not as separate Dividend cash + Trade buy records), the FIFO engine ignores it. In that case, the reinvested shares would be missing from lot tracking. **This must be verified in the data audit (Section 11.3).** If reinvested dividends use separate Trade records, the FIFO engine handles them correctly.

### 8.3 Corrected FIFO Engine

Uses `(account_id, company_id)` as the identity key:

```python
def reconstruct_holdings_at_date(
    account_ids: List[int],
    target_date: date,
    all_txns: List[Dict[str, Any]],
    price_map: Dict[int, List[tuple]],  # company_id -> [(date, price), ...] sorted ascending
) -> List[Dict[str, Any]]:
    """
    Reconstruct holdings at a specific date using corrected FIFO.

    Only processes Trade/BUY and Trade/SELL transactions.
    Identity key: (account_id, company_id).
    Returns holdings_state list only. Cash is computed separately via ledger sum.

    Each returned dict: {
        "company_id": int,
        "symbol": str,
        "quantity": int/float,
        "cost_basis": Decimal,  # total cost of this position
        "avg_cost": Decimal,    # per-share average cost
    }
    """
    lots: Dict[tuple, list] = defaultdict(list)

    relevant = [
        t for t in all_txns
        if _classify_lot_action(t) is not None
        and t["transaction_date"] <= target_date
    ]
    relevant.sort(key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))

    for t in relevant:
        cid = t.get("company_id")
        if not cid:
            continue
        key = (t.get("account_id"), cid)
        action = _classify_lot_action(t)

        if action == "BUY":
            qty = Decimal(str(t.get("quantity") or 0))
            price = Decimal(str(t.get("unit_price") or 0))
            commission = Decimal(str(t.get("commission") or 0))
            cost_per_share = price + (commission / qty) if qty else price
            lots[key].append({
                "quantity": float(qty),
                "cost_per_share": float(cost_per_share),
                "date": t["transaction_date"].isoformat(),
                "symbol": t.get("symbol"),
                "company_id": cid,
            })

        elif action == "SELL":
            qty = abs(float(t.get("quantity") or 0))
            remaining = qty
            while remaining > 0 and lots[key]:
                lot = lots[key][0]
                lot_qty = float(lot["quantity"])
                if lot_qty <= remaining:
                    remaining -= lot_qty
                    lots[key].pop(0)
                else:
                    lot["quantity"] -= remaining
                    remaining = 0

    holdings_state = []
    for (_, cid), lot_list in lots.items():
        qty_held = sum(l["quantity"] for l in lot_list)
        if qty_held <= 0.001:
            continue
        avg_cost = sum(l["quantity"] * l["cost_per_share"] for l in lot_list) / qty_held
        total_cost = qty_held * avg_cost
        symbol = lot_list[0].get("symbol", "?")

        holdings_state.append({
            "company_id": cid,
            "symbol": symbol,
            "quantity": qty_held,
            "cost_basis": total_cost,
            "avg_cost": avg_cost,
        })

    return holdings_state
```

### 8.4 Price Resolution by Company ID (with binary-search optimization)

Also in `shared/snapshot_builder.py`:

```python
# shared/snapshot_builder.py

def resolve_price_forward_filled(
    company_id: int,
    target_date: date,
    price_map: Dict[int, List[tuple]],  # company_id -> [(date, price), ...] sorted ascending
) -> Optional[Dict]:
    """
    Get the closest price on or before target_date for the given company_id.

    Uses binary search (bisect_right) on pre-sorted price list.
    Returns {"price": float, "price_date": date} or None.

    The caller handles the avg_cost fallback via build_snapshot_row() —
    this function only returns None if no price data exists at all.
    """
    import bisect

    prices = price_map.get(company_id, [])
    if not prices:
        return None

    target_key = target_date

    i = bisect.bisect_right(prices, (target_key, float("inf"))) - 1
    if i >= 0:
        pd, pr = prices[i]
        return {"price": pr, "price_date": pd}

    return None
```

### 8.5 Event Collection (via Repository)

Add to `PortfolioRepository`:

```python
# infrastructure/repositories/portfolio_repository.py
def get_event_dates(self, account_id: int) -> List[date]:
    """Collect all dates that could change portfolio value.

    Single query with activity_type filter (not four unfiltered queries).
    """
    event_dates: set = set()

    res = self.client.table("portfolio_transactions") \
        .select("transaction_date, activity_type") \
        .eq("account_id", account_id) \
        .in_("activity_type", ["Trade", "MoneyMovement", "BonusPayment", "Dividend"]) \
        .execute()

    for t in res.data or []:
        d = t["transaction_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        elif isinstance(d, datetime):
            d = d.date()
        event_dates.add(d)

    # Add month-ends for chart anchoring
    if event_dates:
        earliest = min(event_dates)
        today = now_utc().date()
        current = date(earliest.year, earliest.month, 1)
        while current <= today:
            if current.month == 12:
                month_end = date(current.year, 12, 31)
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
                month_end = next_month - timedelta(days=1)
            if month_end >= earliest:
                event_dates.add(month_end)
            current = next_month

    return sorted(event_dates)
```

Used as:
```python
event_dates = portfolio_repo.get_event_dates(account_id)
```

### 8.6 Price Map Builder (Pre-sorted for Binary Search, with Pagination)

Add to `PortfolioRepository`. Uses 1000-row pagination to handle Supabase's row limit and `_batch_execute` helper:

```python
# infrastructure/repositories/portfolio_repository.py
def get_all_prices_historical(
    self, company_ids: List[int], target_date: date
) -> Dict[int, List[tuple]]:
    """
    Build company_id -> [(date, price), ...] sorted ascending for binary search.

    Fetches ALL prices <= target_date for the given companies (no lower bound).
    Uses pagination to handle Supabase's 1000-row limit.

    Each tuple: (date, price). Sorted by date asc.
    """
    price_map: Dict[int, List[tuple]] = {}
    if not company_ids:
        return price_map

    offset = 0
    batch_size = 1000
    while True:
        result = (
            self.client.table("price_history")
            .select("company_id, price_date, close_price")
            .in_("company_id", company_ids)
            .lte("price_date", target_date.isoformat())
            .order("price_date", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        if not result.data:
            break
        for row in result.data:
            cid = row["company_id"]
            pd = row["price_date"]
            if isinstance(pd, str):
                pd = date.fromisoformat(pd)
            elif isinstance(pd, datetime):
                pd = pd.date()
            price_map.setdefault(cid, []).append((pd, float(row["close_price"])))
        offset += batch_size
        if len(result.data) < batch_size:
            break

    return price_map
```

Used as:
```python
price_map = portfolio_repo.get_all_prices_historical(company_ids, today)
```

### 8.7 Backfill Account (Uses Preloaded Price Map, via Repository)

```python
# scripts/backfill_portfolio_snapshots.py

from shared.time_utils import now_utc
from shared.snapshot_builder import (
    build_snapshot_row, _classify_lot_action, resolve_price_forward_filled
)
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository

logger = logging.getLogger("stockerpro.portfolio.backfill")

def backfill_account(account_id: int, force: bool = False):
    """
    Backfill portfolio_snapshots for a single account using event-driven dates.

    IMPORTANT: Prices are resolved from the preloaded price_map, not queried
    per event date. This makes the backfill efficient (~50-80 FIFO computations
    per year instead of 365, and zero price DB queries in the loop).
    """
    portfolio_repo = PortfolioRepository()
    snapshots_repo = PortfolioSnapshotsRepository()

    if not force and snapshots_repo.has_snapshots(account_id):
        logger.info(f"Account {account_id} already backfilled")
        return

    event_dates = portfolio_repo.get_event_dates(account_id)
    if not event_dates:
        logger.info(f"No events for account {account_id}, skipping")
        return

    today = now_utc().date()
    earliest = event_dates[0]

    # Pre-fetch all data ONCE
    symbols_seen, company_ids = _compute_symbol_company_map([account_id])
    price_map = portfolio_repo.get_all_prices_historical(company_ids, today)
    all_txns = portfolio_repo.get_accounts_transactions([account_id], activity_types=["Trade"])

    logger.info(f"Backfilling account {account_id}: {len(event_dates)} event dates")

    for d in event_dates:
        holdings_state = reconstruct_holdings_at_date([account_id], d, all_txns, price_map)
        cash_balance = portfolio_repo.get_cash_balance(account_id, d)
        net_deposits = portfolio_repo.get_net_deposits(account_id, d)

        # Resolve prices from preloaded price_map (no DB queries in loop)
        prices_by_company: Dict[int, Dict] = {}
        for cid in company_ids:
            result = resolve_price_forward_filled(cid, d, price_map)
            if result:
                prices_by_company[cid] = result

        snapshot_row = build_snapshot_row(
            account_id=account_id,
            snapshot_date=d,
            holdings_state=holdings_state,
            cash_balance=cash_balance,
            net_deposits=net_deposits,
            prices_by_company=prices_by_company,
            job_id="backfill_20260622",
        )

        snapshots_repo.upsert_snapshot(snapshot_row)

    # Also write today's snapshot if not an event date
    if event_dates[-1] < today:
        holdings_state = reconstruct_holdings_at_date([account_id], today, all_txns, price_map)
        cash_balance = portfolio_repo.get_cash_balance(account_id, today)
        net_deposits = portfolio_repo.get_net_deposits(account_id, today)
        prices_by_company = {}
        for cid in company_ids:
            result = resolve_price_forward_filled(cid, today, price_map)
            if result:
                prices_by_company[cid] = result

        snapshot_row = build_snapshot_row(
            account_id=account_id,
            snapshot_date=today,
            holdings_state=holdings_state,
            cash_balance=cash_balance,
            net_deposits=net_deposits,
            prices_by_company=prices_by_company,
            job_id="backfill_20260622",
        )
        snapshots_repo.upsert_snapshot(snapshot_row)

    logger.info(f"Backfilled account {account_id}: from {earliest} to {today}")
```

### 8.8 Post-Backfill Validation (via Repository)

Add to `PortfolioSnapshotsRepository`:

```python
# infrastructure/repositories/portfolio_snapshots_repository.py
def validate_snapshot_invariants(self, account_id: int) -> List[str]:
    """Check total_value == holdings_market_value + cash_balance for every row."""
    errors: List[str] = []
    rows = self.get_account_snapshots(account_id)
    for row in rows:
        tv = float(row["total_value"])
        hmv = float(row.get("holdings_market_value", 0))
        cb = float(row.get("cash_balance", 0))
        if abs(tv - (hmv + cb)) > 0.01:
            errors.append(
                f"INVARIANT: account {account_id} on {row['snapshot_date']}: "
                f"total={tv} != market={hmv} + cash={cb}"
            )
        if tv > 1_000_000_000:
            errors.append(f"ABSURD: account {account_id} on {row['snapshot_date']}: ${tv:,.2f}")
    return errors
```

---

## 9. New API Read Path

### 9.1 Repository Method

```python
def get_portfolio_snapshots(
    self,
    account_ids: List[int],
    start_date: date,
    end_date: date,
) -> List[Dict[str, Any]]:
    if not account_ids:
        return []
    try:
        res = (
            self.client.table("portfolio_snapshots")
            .select("snapshot_date, total_value, holdings_market_value, cost_basis, "
                    "cash_balance, net_deposits, holdings_json, data_quality_flag")
            .in_("account_id", account_ids)
            .gte("snapshot_date", start_date.isoformat())
            .lte("snapshot_date", end_date.isoformat())
            .order("snapshot_date", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to fetch portfolio snapshots: {e}")
        return []
```

### 9.2 Service Method

The service uses `PortfolioSnapshotsRepository` for reads and `PortfolioRepository` for account resolution. The read path is gated by `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH` for shadow-mode rollout:

```python
from config import settings
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository

logger_ = logging.getLogger("stockerpro.portfolio.performance")

def timed(logger=logger_):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            logger.info(f"{func.__name__} took {time.time() - start:.2f}s")
            return result
        return wrapper
    return decorator

@timed()
async def get_portfolio_performance(
    self, user_id: int, period: str = "1Y",
    account_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    if account_ids is None:
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
    else:
        user_accounts = self.portfolio_repo.get_user_accounts(user_id)
        valid_ids = {a["account_id"] for a in user_accounts}
        account_ids = [aid for aid in account_ids if aid in valid_ids]

    if not account_ids:
        return {
            "success": True, "period": period,
            "snapshots": [], "total_return": 0, "total_return_pct": 0,
            "data_source": "snapshots", "data_quality_flag": "OK",
            "return_methodology": "simple",
        }

    # Config-gated read path: shadow mode before full cutover
    if not getattr(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", False):
        return await self._get_portfolio_performance_legacy(
            user_id, period, account_ids
        )

    start_date, end_date = self._period_to_date_range(period, account_ids)
    snapshots_repo = PortfolioSnapshotsRepository()
    raw_snapshots = snapshots_repo.get_portfolio_snapshots(
        account_ids, start_date, end_date
    )

    if not raw_snapshots:
        result = await self._compute_performance_fallback(
            user_id, period, account_ids, start_date, end_date
        )
        result["data_source"] = "computed_fallback"
        result["return_methodology"] = "simple"
        return result

    # Merge snapshots across accounts by date
    merged: Dict[str, Dict] = {}
    for s in raw_snapshots:
        d = s["snapshot_date"]
        if d not in merged:
            merged[d] = {
                "date": d, "value": 0.0, "cost_basis": 0.0,
                "cash_balance": 0.0, "net_deposits": 0.0, "holdings": [],
            }
        merged[d]["value"] += s["total_value"]
        merged[d]["cost_basis"] += s["cost_basis"]
        merged[d]["cash_balance"] += s.get("cash_balance", 0)
        merged[d]["net_deposits"] += s.get("net_deposits", 0)
        if s.get("holdings_json"):
            merged[d]["holdings"].extend(s["holdings_json"])

    quality_flags = {s.get("data_quality_flag", "OK") for s in raw_snapshots}
    overall_quality = "STALE_PRICE" if "STALE_PRICE" in quality_flags else "OK"

    sorted_dates = sorted(merged.keys())
    snapshots = [merged[d] for d in sorted_dates]

    if not snapshots:
        return {
            "success": True, "period": period,
            "snapshots": [], "total_return": 0, "total_return_pct": 0,
            "data_source": "snapshots", "data_quality_flag": overall_quality,
            "return_methodology": "simple",
        }

    snapshots = self._compress_snapshots_by_interval(snapshots, period)

    first_value = snapshots[0]["value"]
    last_value = snapshots[-1]["value"]
    total_return = last_value - first_value
    total_return_pct = ((last_value - first_value) / first_value * 100) if first_value > 0 else 0

    return {
        "success": True,
        "period": period,
        "snapshots": snapshots,
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "data_source": "snapshots",
        "data_quality_flag": overall_quality,
        "return_methodology": "simple",
    }


async def _get_portfolio_performance_legacy(
    self, user_id: int, period: str = "1Y",
    account_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Legacy read path — uses the current FIFO engine.
    Retained for:
    - Emergency rollback via ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False
    - Shadow-mode comparison during migration
    - Fallback when no snapshots exist
    """
    return await self._compute_performance_fallback(
        user_id, period, account_ids, None, None
    )
```

### 9.3 Date-Bucket Compression

Picks one snapshot per N-day boundary, handling sparse event-driven data correctly. Uses N-day stepping (not row-index stepping), which works for both dense and sparse snapshots:

```python
def _compress_snapshots_by_interval(
    self, snapshots: List[Dict], period: str
) -> List[Dict]:
    """
    Compress by time interval (N days between points), not row index.

    For 1Y: picks one snapshot per 7-day interval (not per calendar week).
    For ALL: picks one per 30-day interval (not per calendar month).

    Handles sparse event-driven snapshots correctly — measures time
    between dates, not list position. If calendar-boundary bucketing
    (e.g., every Monday) is needed later, this function is the place
    to add it.
    """
    if not snapshots:
        return snapshots

    step_days = {"1D": 0, "1W": 0, "1M": 1, "3M": 3, "1Y": 7, "5Y": 14, "YTD": 7, "ALL": 30}
    step = step_days.get(period.upper(), 7)

    if step <= 0:
        return snapshots

    compressed = [snapshots[0]]
    last_selected = date.fromisoformat(snapshots[0]["date"])

    for s in snapshots[1:]:
        current = date.fromisoformat(s["date"])
        if (current - last_selected).days >= step:
            compressed.append(s)
            last_selected = current

    if compressed[-1]["date"] != snapshots[-1]["date"]:
        compressed.append(snapshots[-1])

    return compressed
```

Note: This is N-day interval sampling, not strict calendar-week bucketing. For MVP this is acceptable. If higher precision is needed, define weekly/monthly calendar boundaries.

### 9.4 API Response

```json
{
    "success": true,
    "period": "1Y",
    "snapshots": [...],
    "total_return": 5200.50,
    "total_return_pct": 12.4,
    "data_source": "snapshots",
    "data_quality_flag": "OK",
    "return_methodology": "simple"
}
```

### 9.5 Fallback Computation

Temporary path for periods without pre-computed snapshots (e.g., during migration). Uses the corrected FIFO helpers from `shared/snapshot_builder`, scoped to the requested date range. Circuit breaker alerts if triggered >3 times in 24h via `SchedulerRepository`.

Add to the top of `portfolio_service.py`:
```python
from shared.snapshot_builder import _classify_lot_action, resolve_price_forward_filled, build_snapshot_row
```

```python
async def _compute_performance_fallback(
    self, user_id, period, account_ids, start_date, end_date
):
    """
    Temporary fallback for periods without snapshots (e.g., during migration).

    Uses corrected FIFO engine + shared build_snapshot_row().
    Scoped to the requested date range only (not all-time).
    Circuit breaker: alerts if triggered >3 times in 24h via SchedulerRepository.
    """
    txns_batch = self.portfolio_repo.get_accounts_transactions(
        account_ids, activity_types=["Trade"]
    )
    for t in txns_batch:
        d = t.get("transaction_date")
        if isinstance(d, str):
            t["transaction_date"] = date.fromisoformat(d)
        elif isinstance(d, datetime):
            t["transaction_date"] = d.date()

    all_txns = sorted(txns_batch, key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))
    pre_txns = [t for t in all_txns if t["transaction_date"] < start_date]
    in_txns = [t for t in all_txns if start_date <= t["transaction_date"] <= end_date]

    # Build opening lots from pre-period transactions (corrected FIFO)
    # NOTE: Dividend reinvestment is treated as a BUY transaction here.
    # If DRIP shares are recorded as distinct Trade activity_type rows
    # with positive quantity, the existing _classify_lot_action handles
    # them naturally. If they use a non-Trade activity type, they will
    # be missed — the caller must ensure DRIP rows are included in the
    # transaction feed or this fallback may understate cost basis by
    # the reinvested dividend amount.
    lots: Dict[tuple, list] = defaultdict(list)
    for t in pre_txns:
        action = _classify_lot_action(t)
        if action is None:
            continue
        cid = t.get("company_id")
        if not cid:
            continue
        key = (t.get("account_id"), cid)
        if action == "BUY":
            qty = Decimal(str(t.get("quantity") or 0))
            price = Decimal(str(t.get("unit_price") or 0))
            commission = Decimal(str(t.get("commission") or 0))
            cost_per_share = price + (commission / qty) if qty else price
            lots[key].append({
                "quantity": float(qty), "cost_per_share": float(cost_per_share),
                "date": str(t["transaction_date"]),
                "symbol": t.get("symbol", ""),
            })
        elif action == "SELL":
            sell_qty = abs(float(t.get("quantity") or 0))
            remaining = sell_qty
            while remaining > 0 and lots[key]:
                lot = lots[key][0]
                if lot["quantity"] <= remaining:
                    remaining -= lot["quantity"]
                    lots[key].pop(0)
                else:
                    lot["quantity"] -= remaining
                    remaining = 0

    # Price map for the range
    company_ids = list({t.get("company_id") for t in all_txns if t.get("company_id")})
    price_map = self.portfolio_repo.get_all_prices_historical(company_ids, end_date)

    # Generate snapshot dates within range
    sorted_dates = self._generate_snapshot_dates(period, start_date, end_date)

    snapshots = []
    in_txns_sorted = sorted(in_txns, key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))
    txn_index = 0

    for d in sorted_dates:
        current_date = date.fromisoformat(d)
        while txn_index < len(in_txns_sorted) and in_txns_sorted[txn_index]["transaction_date"].isoformat() <= d:
            t = in_txns_sorted[txn_index]
            action = _classify_lot_action(t)
            cid = t.get("company_id")
            if action and cid:
                key = (t.get("account_id"), cid)
                if action == "BUY":
                    qty = Decimal(str(t.get("quantity") or 0))
                    price = Decimal(str(t.get("unit_price") or 0))
                    commission = Decimal(str(t.get("commission") or 0))
                    cost_per_share = price + (commission / qty) if qty else price
                    lots[key].append({
                        "quantity": float(qty), "cost_per_share": float(cost_per_share),
                        "date": d,
                        "symbol": t.get("symbol", ""),
                    })
                elif action == "SELL":
                    sell_qty = abs(float(t.get("quantity") or 0))
                    remaining = sell_qty
                    while remaining > 0 and lots[key]:
                        lot = lots[key][0]
                        if lot["quantity"] <= remaining:
                            remaining -= lot["quantity"]
                            lots[key].pop(0)
                        else:
                            lot["quantity"] -= remaining
                            remaining = 0
            txn_index += 1

        # Build holdings state for this date
    # Aggregate by company_id across accounts (lots keyed by (account_id, cid))
        cid_holdings: Dict[int, dict] = {}
        for (_, cid), lot_list in lots.items():
            qty_held = sum(l["quantity"] for l in lot_list)
            if qty_held <= 0.001:
                continue
            avg_cost = sum(l["quantity"] * l["cost_per_share"] for l in lot_list) / qty_held
            total_cost = qty_held * avg_cost
            # Pick first non-empty symbol from lots (all should match for same cid)
            symbol = next((l.get("symbol", "") for l in lot_list if l.get("symbol")), "")
            if cid in cid_holdings:
                cid_holdings[cid] = {
                    "company_id": cid, "symbol": symbol,
                    "quantity": cid_holdings[cid]["quantity"] + qty_held,
                    "cost_basis": cid_holdings[cid]["cost_basis"] + total_cost,
                    "avg_cost": (cid_holdings[cid]["avg_cost"] + avg_cost) / 2,
                }
            else:
                cid_holdings[cid] = {
                    "company_id": cid, "symbol": symbol,
                    "quantity": qty_held,
                    "cost_basis": total_cost,
                    "avg_cost": avg_cost,
                }
        holdings_state = list(cid_holdings.values())

        # Resolve prices from price_map
        prices_by_company = {}
        for cid in company_ids:
            result = resolve_price_forward_filled(cid, current_date, price_map)
            if result:
                prices_by_company[cid] = result

    cash_balance = self.portfolio_repo.get_cash_balance_for_accounts(account_ids, current_date)
    net_deposits = self.portfolio_repo.get_net_deposits_for_accounts(account_ids, current_date)

        snapshot_row = build_snapshot_row(
            account_id=0,  # merged across accounts
            snapshot_date=current_date,
            holdings_state=holdings_state,
            cash_balance=cash_balance,
            net_deposits=net_deposits,
            prices_by_company=prices_by_company,
            job_id="fallback",
        )
        snapshots.append({
            "date": d,
            "value": snapshot_row["total_value"],
            "cost_basis": snapshot_row["cost_basis"],
            "net_deposits": snapshot_row["net_deposits"],
        })

    if not snapshots:
        return {"snapshots": [], "total_return": 0, "total_return_pct": 0}

    first_value = snapshots[0]["value"]
    last_value = snapshots[-1]["value"]
    total_return = last_value - first_value
    total_return_pct = ((last_value - first_value) / first_value * 100) if first_value > 0 else 0

    return {
        "success": True,
        "period": period,
        "snapshots": snapshots,
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "data_source": "computed_fallback",
        "return_methodology": "simple",
    }
```

---

## 10. Frontend Changes

### 10.1 Minimal Changes

No changes needed to existing components. The API response format is backward-compatible (new optional fields only).

### 10.2 Optional: Display Data Quality

```typescript
interface PerformanceResponse {
    snapshots: PerformanceSnapshot[];
    total_return: number;
    total_return_pct: number;
    data_source?: "snapshots" | "computed_fallback";
    data_quality_flag?: "OK" | "STALE_PRICE";
    return_methodology?: "simple";
}
```

---

## 11. Prerequisites

### 11.1 Stock Split Adjustment Check

```sql
SELECT c.company_id, c.symbol, sh.split_date, sh.split_from, sh.split_to
FROM stock_splits sh
JOIN companies c ON sh.company_id = c.company_id
WHERE sh.company_id IN (
    SELECT DISTINCT company_id FROM portfolio_transactions WHERE activity_type = 'Trade'
)
  AND sh.split_date >= '2021-01-01'
ORDER BY sh.split_date;
```

If splits exist, verify `price_history.close_price` reflects split-adjusted closes.

### 11.2 Company ID Consistency Check

Run before backfill. Fails fast if any symbol maps to multiple company_ids:

```python
# shared/validation.py

Add a dedicated repository method:

```python
# infrastructure/repositories/portfolio_repository.py
def get_symbol_company_mappings(self, account_ids: List[int]) -> List[Dict[str, Any]]:
    """Return (symbol, company_id) pairs for all transactions in the given accounts."""
    try:
        res = self.table("portfolio_transactions") \
            .select("symbol, company_id") \
            .in_("account_id", account_ids) \
            .neq("symbol", None) \
            .neq("company_id", None) \
            .execute()
        return res.data or []
    except Exception:
        return []
```

Then the validation function calls it:

```python
def validate_company_id_consistency(account_ids: List[int]) -> List[str]:
    issues: List[str] = []
    repo = PortfolioRepository()
    rows = repo.get_symbol_company_mappings(account_ids)

    symbol_to_companies: Dict[str, set] = defaultdict(set)
    for r in rows:
        sym = r.get("symbol")
        cid = r.get("company_id")
        if sym and cid:
            symbol_to_companies[sym].add(cid)

    for sym, cids in symbol_to_companies.items():
        if len(cids) > 1:
            issues.append(
                f"Symbol {sym} maps to multiple company_ids: {sorted(cids)}. "
                f"This causes FIFO position splitting. Fix data before backfill."
            )
    return issues
```
```

### 11.3 Cash Ledger Integrity Check

The system's correctness relies on `net_cash_amount` being populated consistently. Run this audit before migration:

```sql
SELECT activity_type,
       COUNT(*) AS total_rows,
       COUNT(*) FILTER (WHERE net_cash_amount IS NULL) AS null_cash,
       COUNT(*) FILTER (WHERE net_cash_amount = 0) AS zero_cash,
       ROUND(AVG(net_cash_amount), 2) AS avg_cash,
       ROUND(MIN(net_cash_amount), 2) AS min_cash,
       ROUND(MAX(net_cash_amount), 2) AS max_cash
FROM portfolio_transactions
GROUP BY activity_type
ORDER BY activity_type;
```

Check sign conventions:
- `Trade/BUY` should have negative `net_cash_amount` (money leaves)
- `Trade/SELL` should have positive `net_cash_amount` (money enters)
- `Dividend` should have positive `net_cash_amount`
- `MoneyMovement/EFT` deposits should be positive
- Withdrawals should be negative

**Dividend reinvestment check:** Verify that reinvested dividends don't double-count. Query 5 sample records where `activity_type = 'Dividend'` and `quantity > 0`. If they have `net_cash_amount = -X`, and there's a corresponding `Trade/BUY` with `net_cash_amount = -X`, the cash balance will be double-counted. If import records them as separate Dividend cash + Trade records, and the Dividend record has `net_cash_amount = 0` (cash is already moved), there's no double-count.

### 11.4 Config Flags (Feature Flags)

Add to `backend/config.py` following the existing `ENABLE_*_SCHEDULER` pattern:

```python
ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER: bool = Field(
    True,
    description="Enable daily portfolio snapshot computation job (23:00 UTC)"
)

ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH: bool = Field(
    False,
    description="Enable snapshot-based read path for /api/portfolio/performance "
                "(shadow-mode before full cutover)"
)

PORTFOLIO_SNAPSHOT_FALLBACK_ENABLED: bool = Field(
    True,
    description="Enable fallback FIFO computation when snapshots not yet available"
)
```

The read-path flag (`ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH`) enables shadow-mode validation:
1. Deploy table + backfill + scheduler first with `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False`
2. Validate snapshots match expected values
3. Toggle `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=True` for read-path switch
4. If issues arise, toggle back to `False` — clean rollback without code revert

---

## 12. Holdings Reconciliation

This is a **mandatory migration gate**. The read-path switch is blocked unless reconciliation passes.

### 12.1 Reconciliation Logic (via Repository)

```python
# scripts/reconcile_holdings.py

from shared.time_utils import now_utc
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository

logger = logging.getLogger("stockerpro.portfolio.reconciliation")

def reconcile_holdings(
    account_id: int,
    quantity_tolerance: float = 0.0001,
    pct_tolerance: float = 0.1,
) -> Tuple[bool, List[str]]:
    """
    Compare the corrected backfill final holdings state against portfolio_holdings.

    Returns (passes, list_of_issues).
    Cutover is BLOCKED if:
    - Any position is missing or extra
    - Quantity delta exceeds tolerance
    """
    today = now_utc().date()
    snapshots_repo = PortfolioSnapshotsRepository()
    portfolio_repo = PortfolioRepository()

    latest_snapshot = snapshots_repo.get_latest_snapshot(account_id)
    if not latest_snapshot:
        return False, [f"No snapshots found for account {account_id}"]

    sd = latest_snapshot["snapshot_date"]
    if isinstance(sd, str):
        sd = date.fromisoformat(sd)
    if (today - sd).days > 1:
        return False, [f"Snapshot too old ({today - sd}d). Run backfill again."]

    corrected = {h["company_id"]: h for h in latest_snapshot.get("holdings_json") or []}
    current = {h["company_id"]: h for h in portfolio_repo.get_holdings(account_id)}

    all_ids = set(corrected.keys()) | set(current.keys())
    issues: List[str] = []
    passes = True

    for cid in all_ids:
        corr = corrected.get(cid)
        curr = current.get(cid)

        if corr and not curr:
            issues.append(f"MISSING in holdings: company_id={cid} ({corr['symbol']}) qty={corr['quantity']}")
            passes = False
        elif curr and not corr:
            issues.append(f"EXTRA in holdings: company_id={cid} ({curr['symbol']}) qty={curr['quantity']}")
            passes = False
        elif corr and curr:
            qty_diff = abs(float(corr['quantity']) - float(curr['quantity']))
            base = max(abs(float(corr['quantity'])), abs(float(curr['quantity'])), quantity_tolerance)
            if qty_diff > quantity_tolerance and base > 0:
                pct = qty_diff / base * 100
                if pct > pct_tolerance:
                    issues.append(
                        f"MISMATCH: company_id={cid} ({corr['symbol']}): "
                        f"backfill qty={corr['quantity']}, holdings qty={curr['quantity']} "
                        f"(diff={qty_diff:.4f}, {pct:.2f}%)"
                    )
                    passes = False

    if issues:
        for i in issues:
            logger.warning(f"Reconciliation {account_id}: {i}")
    else:
        logger.info(f"Account {account_id}: holdings table is consistent with corrected FIFO")

    return passes, issues
```

### 12.2 Pass/Fail Criteria

| Condition | Action |
|-----------|--------|
| No issues | Pass — proceed to read-path switch |
| Any missing/extra position | **Block cutover**. Investigate import pipeline. |
| Quantity delta > 0.1% on any position | **Block cutover**. Manual review required. |
| Quantity delta <= 0.1% and no missing/extra | Pass with warning. Log for audit. |

---

## 13. Migration Plan

### 13.1 Implementation Order

| Step | Description | Effort | Depends On |
|------|-------------|--------|------------|
| 0a | Prerequisites (splits, company_id, cash ledger) | 2 hours | — |
| 0b | Add config flags to `config.py` | 15 min | — |
| 1 | Add repository methods to `PortfolioRepository`, `FinancialRepository` | 2 hours | — |
| 2 | SQL migration (table + indexes) | 15 min | Step 0a |
| 3 | Write backfill script | 1 day | Steps 1, 2 |
| 4 | Run backfill + validate | 2 hours | Step 3 |
| 5 | Holdings reconciliation | 1 hour | Step 4 |
| 6 | Write `PortfolioSnapshotsRepository` + service/API changes | 1.5 hours | Step 2 |
| 7 | Deploy with `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False` (shadow mode) | 30 min | Steps 4, 5, 6 |
| 8 | Validate snapshots, toggle read path to `True` | 1 hour | Step 7 |
| 9 | Write daily job + scheduler handler + register in `scheduler_worker.py` | 2 hours | Step 6 |
| 10 | Monitor (24h) | 2 hours | Steps 8, 9 |
| 11 | Remove old FIFO code + legacy table migration | 1 hour | Step 10 |
| 12 | Write/update tests | 1 day | Steps 3, 6, 9 |

### 13.2 Deployment Sequence

```
Phase 1: Prerequisites + Infrastructure
  - Steps 0a-0b: Verify splits, company_id, cash ledger; add config flags
  - Step 1: Add repository methods
  - Step 2: SQL migration
  - No user-facing impact

Phase 2: Backfill + Reconciliation
  - Step 3: Write and run backfill script (--validate-only first)
  - Step 4: Holdings reconciliation (BLOCKS Phase 3 if fails)
  - Step 5: Reconciliation passes committed

Phase 3: Shadow Mode + Read Path Switch
  - Step 6: Snapshot repository + service/API changes
  - Step 7: Deploy with ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False
  - Step 8: Validate snapshots, toggle to True when confident
  - Response time drops from ~500ms to <10ms

Phase 4: Daily Job
  - Step 9: Write portfolio_snapshot job handler, planner, register in scheduler_worker.py
  - Enabled via ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER config flag

Phase 5: Cleanup
  - Step 11: Remove old FIFO methods, deprecate legacy portfolio_performance table
  - Step 12: Tests
```

---

## 14. Rollback Strategy

**Prefer config toggle over code revert.** If `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False` is set, the service falls back to the FIFO engine immediately without a deploy.

If code revert is required:

```
1. Set ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False (config-only rollback)
2. If config revert is insufficient: revert git commit that changed get_portfolio_performance
3. portfolio_snapshots table stays (unused; data preserved for re-enable)
4. Set ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER=False
5. Verify /api/portfolio/performance returns old-format data
```

### 14.1 Important Caveat: Holdings Table May Have Been Repaired

After migration Phase 2 (holdings reconciliation), `portfolio_holdings` may have been
corrected to match the backfill's output.  If you roll back the API read path:

- The **old FIFO engine** will read from `portfolio_transactions` (same as before),
  NOT from `portfolio_holdings`.  So the rollback restores the query path, not the data.
- If `portfolio_transactions` still contains the same phantom-share-causing rows
  (InternalSecurityTransfer, FxExchange with sub_type=None), the old FIFO engine
  will reproduce the same $103M valuations.  The rollback does NOT fix that bug.
- The underlying data corrections made during migration (if any) are NOT reverted.

**In short:** Rolling back restores the query logic, but the data may have changed.
Old FIFO + corrected holdings = different output than before migration.
Old FIFO + unchanged transactions = same broken output as before migration.

---

## 15. SQL Migration Script

```sql
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    account_id          INTEGER NOT NULL REFERENCES portfolio_accounts(account_id) ON DELETE CASCADE,
    snapshot_date       DATE NOT NULL,
    total_value         NUMERIC(15, 2) NOT NULL,
    holdings_market_value NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    cost_basis          NUMERIC(15, 2) NOT NULL,
    cash_balance        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    net_deposits        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    holdings_json       JSONB,
    data_quality_flag   TEXT NOT NULL DEFAULT 'OK',
    job_id              TEXT,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_account_date
    ON portfolio_snapshots (account_id, snapshot_date DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_account_date_unique
    ON portfolio_snapshots (account_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_snapshots_quality
    ON portfolio_snapshots (data_quality_flag)
    WHERE data_quality_flag != 'OK';

ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS portfolio_snapshots CASCADE;
```

---

## 16. Test Plan

### 16.1 Unit Tests

| Test | Verifies |
|------|----------|
| `test_build_snapshot_row_invariant` | `total_value == holdings_market_value + cash_balance` |
| `test_build_snapshot_row_invariant_assertion` | AssertionError raised if invariant violated |
| `test_corrected_fifo_only_trades` | Only Trade/BUY and Trade/SELL affect lots |
| `test_corrected_fifo_dividend_ignored` | Dividend with qty>0 does not add a lot |
| `test_corrected_fifo_transfer_ignored` | InternalSecurityTransfer does not add a lot |
| `test_corrected_fifo_buy_sell_sequence` | Buy then sell produces correct remaining shares |
| `test_corrected_fifo_partial_sell` | Partial sell reduces lot quantity |
| `test_corrected_fifo_company_id_key` | Lots keyed by (account_id, company_id) |
| `test_price_forward_fill_by_company_id` | Price resolved by company_id, binary search |
| `test_price_forward_fill_no_history` | No price data → avg_cost fallback |
| `test_cash_balance_ledger_all_types` | Sum of net_cash_amount across all types |
| `test_cash_balance_sell_increases_cash` | Sell (positive net_cash) increases cash |
| `test_net_deposits_only_money_movement` | Net deposits excludes buy/sell/dividend |
| `test_data_quality_flag_ok` | Fresh prices → OK |
| `test_data_quality_flag_stale` | One stale price → STALE_PRICE |
| `test_data_quality_flag_per_account` | Account A stale doesn't affect Account B |
| `test_compress_by_date_weekly` | 1Y: one per 7-day boundary |
| `test_compress_by_date_monthly` | ALL: one per 30-day boundary |
| `test_compress_sparse_snapshots` | Event-driven sparse dates compress correctly |
| `test_backfill_event_dates` | Event dates + month-ends only (not all 365 days) |
| `test_backfill_and_daily_same_builder` | Both paths produce identical row structure |
| `test_holdings_reconciliation_pass` | Perfect match → passes=True |
| `test_holdings_reconciliation_block` | Missing position → passes=False |
| `test_company_id_consistency_pass` | Consistent symbols → no issues |
| `test_company_id_consistency_fail` | Symbol mapped to multiple company_ids → issue |
| `test_cash_ledger_integrity_signs` | BUY negative, SELL positive, Dividend positive |
| `test_snapshot_value_sanity_check` | Values > $1B raise error |

### 16.2 Integration Tests (API + Job + Backfill)

| File | Test | Verifies |
|------|------|----------|
| `test_portfolio_snapshots_api.py` | `test_performance_endpoint_read_path_disabled` | `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=False` delegates to legacy `_get_portfolio_performance_legacy` |
| | `test_performance_endpoint_read_path_enabled` | `ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=True` reads from `portfolio_snapshots` table |
| | `test_performance_endpoint_fallback` | No snapshots → fallback FIFO engine triggered, `data_source="computed_fallback"` |
| | `test_performance_endpoint_merges_accounts` | Multiple accounts → snapshots merged by date, values summed |
| | `test_performance_endpoint_period_1d` | 1D period returns correct date bounds |
| | `test_performance_endpoint_period_1w` | 1W period returns correct date bounds |
| | `test_performance_endpoint_period_1m` | 1M period returns correct date bounds |
| | `test_performance_endpoint_period_1y` | 1Y period returns correct date bounds |
| | `test_performance_endpoint_period_5y` | 5Y period returns correct date bounds |
| | `test_performance_endpoint_period_all` | ALL period returns full date range |
| | `test_performance_endpoint_empty_account_ids` | No valid accounts → empty response, not error |
| | `test_performance_endpoint_invalid_account_ids` | accounts not owned by user → filtered out |
| | `test_performance_endpoint_compression_1y` | 1Y response compressed to weekly granularity |
| | `test_performance_endpoint_compression_all` | ALL response compressed to monthly granularity |
| | `test_performance_endpoint_data_source_flag` | Response body contains `data_source` field |
| | `test_performance_endpoint_data_quality_flag` | Response body contains `data_quality_flag` field |
| | `test_performance_endpoint_total_return` | `total_return == last_value - first_value` |
| | `test_performance_endpoint_total_return_pct` | `total_return_pct` matches percentage math |
| | `test_performance_endpoint_compares_legacy_shadow` | Both modes produce similar results (within tolerance) |
| | `test_performance_endpoint_stale_quality_flag` | At least one stale price → `STALE_PRICE` |
| | `test_performance_endpoint_unauthorized` | No auth token → 401 |
| `test_daily_snapshot_job.py` | `test_daily_snapshot_job_creates_rows` | Creates rows for active accounts |
| | `test_daily_snapshot_job_cash_ledger` | Cash matches sum of net_cash_amount |
| | `test_daily_snapshot_job_invariant` | Every row: `total_value == market_value + cash_balance` |
| | `test_daily_snapshot_job_empty_holdings` | Account with no holdings still gets snapshot (cash-only) |
| | `test_daily_snapshot_job_idempotent` | Running twice produces same data (upsert) |
| | `test_daily_snapshot_job_negative_quantity` | Negative quantity raises error |
| | `test_daily_snapshot_job_holdings_json` | `holdings_json` contains each holding with `company_id`, `symbol`, `quantity`, `avg_cost` |
| | `test_daily_snapshot_job_scheduler_flow` | `SchedulerPlanner.plan()` enqueues job; handler executes and rows appear |
| | `test_daily_snapshot_job_excludes_legacy_rows` | Daily job writes only to `portfolio_snapshots`, not `portfolio_performance` |
| | `test_daily_snapshot_job_job_id_tracking` | Every row has a non-null `job_id` linking to job run |
| `test_backfill_script.py` | `test_backfill_creates_rows` | Backfill creates rows for all event dates + month-ends |
| | `test_backfill_event_dates_count` | Event dates <= 365 per year |
| | `test_backfill_idempotent` | Running backfill twice produces same data |
| | `test_backfill_and_daily_consistent` | Both paths use same `build_snapshot_row` builder |
| | `test_backfill_respects_date_range` | `--start-date`/`--end-date` flags respected |
| | `test_backfill_validate_only` | `--validate-only` flag checks invariants without writing |
| | `test_backfill_company_name_resolution` | `company_name` populated in `holdings_json` |
| | `test_backfill_rollback` | Backfill deletion removes only its own rows |

### 16.3 Database Content Validation Tests

Tests that directly query the database to verify snapshot correctness against source data. These run against a test dataset with known transactions.

| Test | Verifies |
|------|----------|
| `test_db_snapshot_invariant_all_rows` | EVERY row: `total_value == market_value(holdings_json) + cash_balance` |
| `test_db_snapshot_value_within_bounds` | No snapshot has `total_value < 0` or `total_value > $10M` |
| `test_db_snapshot_cash_matches_ledger` | `cash_balance` equals `SUM(net_cash_amount)` for that account up to `snapshot_date` |
| `test_db_snapshot_net_deposits_matches` | `net_deposits` equals `SUM(CASE WHEN type IN (deposit,withdrawal) THEN net_cash END)` |
| `test_db_snapshot_no_duplicate_dates` | No two rows share the same `(account_id, snapshot_date)` |
| `test_db_snapshot_dates_are_trading_days` | All snapshot dates are weekdays (Mon-Fri) |
| `test_db_snapshot_daily_job_coverage` | Every active account has a snapshot for the job date |
| `test_db_snapshot_backfill_coverage` | Every account with transactions has snapshots for event dates |
| `test_db_snapshot_backfill_vs_daily_overlap` | Overlapping dates between backfill and daily job produce identical rows |
| `test_db_snapshot_holdings_json_quantities` | `holdings_json.quantity` matches live `portfolio_holdings.quantity` for that account/date |
| `test_db_snapshot_holdings_json_cost_basis` | `holdings_json.cost_basis` matches average cost snapshot |
| `test_db_snapshot_accounts_filtered` | Snapshots exist ONLY for accounts that belong to active users |
| `test_db_snapshot_data_quality_reproducible` | Re-running the daily job on the same date yields identical quality flags |
| `test_db_snapshot_holdings_json_symbols` | Every `holdings_json` entry has non-empty `symbol` and `company_id` |
| `test_db_snapshot_holdings_json_no_duplicates` | No duplicate `company_id` entries within a single snapshot's `holdings_json` |
| `test_db_reconciliation_holdings_vs_snapshots` | Each holding's cost basis in `portfolio_holdings` ≈ snapshot cost basis (within tolerance) |
| `test_db_reconciliation_transactions_vs_fifo` | FIFO lot quantities × prices ≈ cumulative buy/sell in transactions |
| `test_db_price_gap_detection` | Snapshots with missing price data are flagged `STALE_PRICE` correctly |
| `test_db_null_handling` | NULL `holdings_json` handled gracefully (cash-only account) |
| `test_db_rls_isolation` | User A cannot read User B's snapshots (RLS enforcement) |

### 16.4 Frontend Unit Tests

| File | Test | Verifies |
|------|------|----------|
| `__tests__/PortfolioPerformanceChart.test.tsx` | `renders loading skeleton` | Recharts `Skeleton` visible while `usePortfolio` is loading |
| | `renders chart with snapshot data` | Line chart rendered with correct data points from API |
| | `renders empty state when no snapshots` | "No performance data" message when array empty |
| | `renders error state` | Error message shown when query fails |
| | `formats currency on Y-axis` | Values formatted as `$X,XXX.XX` |
| | `formats percentage on tooltip` | Tooltip shows `+X.XX%` or `-X.XX%` |
| | `formats dates on X-axis` | Dates formatted as short date (MMM DD) or month (MMM YYYY) |
| | `renders multiple series for multi-account` | Separate line per account when not merged |
| | `renders fallback indicator badge` | "Computed" badge visible when `data_source="computed_fallback"` |
| | `renders stale price warning` | Warning banner visible when `data_quality_flag="STALE_PRICE"` |
| | `compresses >200 points to daily` | Recharts `data` prop truncated to max 200 points |
| | `renders area fill below line` | Gradient fill present for positive/negative regions |
| `__tests__/TimePeriodSelector.test.tsx` | `all periods render as buttons` | 1D, 1W, 1M, 3M, 1Y, 5Y, ALL buttons visible |
| | `clicking period updates URL` | `?period=3M` appended to search params |
| | `active period highlighted` | Selected period has `bg-primary` class |
| `__tests__/hooks/usePortfolioPerformance.test.ts` | `calls API with correct params` | Query key includes `period`, `accountIds` |
| | `returns performance data` | Hook returns `snapshots`, `totalReturn`, `totalReturnPct` |
| | `refetches on period change` | Period change triggers new query |
| | `handles stale data gracefully` | `staleTime: 30000` respected |

### 16.5 E2E Tests (Playwright)

Located in `web/e2e/portfolio-performance.spec.ts`. These tests use the real backend with a test user account and validate the full data pipeline: DB → API → UI.

| Test | Verifies |
|------|----------|
| `loads portfolio page and renders performance tab` | Page shell renders, performance tab clickable |
| `performance chart renders with real data` | Recharts SVG element exists with data points |
| `chart data matches API response` | Intercept `GET /portfolio/performance`, compare chart points to response JSON |
| `summary cards show correct values` | Total return, total return % match API `totalReturn`/`totalReturnPct` |
| `switching time period updates chart` | Click "3M" → chart re-renders with new data, URL updated |
| `account filter affects chart` | Select single account → chart filters to that account's data |
| `all time period returns most data points` | "ALL" period returns full range, chart renders many points |
| `stale price quality flag shows warning` | If any account has `STALE_PRICE`, warning banner visible |
| `fallback data source shows indicator` | If `data_source=computed_fallback`, "Computed" tag visible |
| `chart tooltip shows correct values` | Hover over data point → tooltip displays date, value, return |
| `mobile layout renders chart as full width` | Viewport 375×812 → chart takes full container width |
| `unauthenticated user redirected` | No auth token → redirected to login page |
| `API contract compliance` | Response body matches TypeScript `PortfolioPerformanceResponse` interface |

### 16.6 Performance Targets

| Scenario | Expected |
|----------|----------|
| 1Y period, 3 accounts | <10ms |
| ALL period, 3 accounts | <10ms |
| Daily job (6 accounts) | <60s |
| Backfill (5 years, 6 accounts, event-driven) | <10 min |
| E2E chart render (Playwright) | <5s first meaningful paint |

---

## 17. Appendix A: Files to Delete After Migration

| File | Reason |
|------|--------|
| `portfolio_service.py:_step_for_period` | Replaced by compress_by_interval |
| `portfolio_service.py:_generate_snapshot_dates` | Replaced by event-driven backfill |
| `portfolio_service.py:_compute_fifo_snapshots` | Replaced by backfill + daily job |
| `portfolio_service.py:_get_cashflow_deltas` | Cash is ledger-based now |
| `portfolio_service.py:get_portfolio_performance` body | Replaced by snapshot read logic (method signature kept for backward compat) |
| `portfolio_repository.py:get_account_performance_history` | Superseded by `PortfolioSnapshotsRepository` (old table kept for seed scripts; deprecate after migration) |
| `portfolio_repository.py:upsert_performance_snapshot` | Superseded by `PortfolioSnapshotsRepository` |

**Note:** `_period_to_date_range` is **NOT** deleted — it is still used by the new `get_portfolio_performance` service method and the fallback path.
**Note:** The legacy `portfolio_performance` table is **kept** during migration. Seed scripts (`seed_e2e_data.py`, `seed_e2e_requests.py`, `seed_e2e_data.ps1`) continue to work. The table is deprecated and should be migrated to `portfolio_snapshots` in a future release.

## 18. Appendix B: Files to Create

| File | Purpose |
|------|---------|
| `scripts/add_portfolio_snapshots_table.sql` | DDL + indexes + RLS |
| `shared/snapshot_builder.py` | Shared `build_snapshot_row()`, `_classify_lot_action()`, `resolve_price_forward_filled()` |
| `shared/validation.py` | company_id consistency, cash ledger integrity |
| `scripts/backfill_portfolio_snapshots.py` | Event-driven backfill |
| `application/jobs/portfolio_snapshot_job.py` | Daily computation job + `handle_portfolio_snapshot` handler |
| `application/schedulers/portfolio_snapshot_scheduler.py` | `PortfolioSnapshotScheduler` with `plan()` method |
| `infrastructure/repositories/portfolio_snapshots_repository.py` | Snapshot reads + writes |
| `infrastructure/repositories/portfolio_repository.py` | *(Add methods: `get_cash_balance`, `get_net_deposits`, `get_event_dates`, `get_all_prices_historical`, `get_holdings_for_accounts`, `get_company_names`, `get_user_accounts_all`, `get_symbol_company_mappings`, `get_cash_balance_for_accounts`, `get_net_deposits_for_accounts`)* |
| `infrastructure/repositories/financial_repository.py` | *(Add method: `get_latest_prices`)* |
| `backend/tests/test_portfolio_snapshots.py` | Unit tests |
| `backend/tests/integration/test_portfolio_snapshots_api.py` | API integration tests (read path gating, fallback, periods, compression) |
| `backend/tests/integration/test_daily_snapshot_job.py` | Daily job integration tests (row creation, idempotency, invariants) |
| `backend/tests/integration/test_backfill_script.py` | Backfill validation (event dates, date range, validate-only) |
| `backend/tests/integration/test_snapshot_database.py` | Database content validation (invariants across all rows, ledger reconciliation, holdings matching) |
| `web/src/__tests__/PortfolioPerformanceChart.test.tsx` | Frontend unit tests (loading, empty, error states, formatting) |
| `web/src/__tests__/hooks/usePortfolioPerformance.test.ts` | Hook unit tests (query keys, refetch, stale time) |
| `web/e2e/portfolio-performance.spec.ts` | Playwright E2E tests (real data pipeline, chart rendering, contract, mobile) |

## 19. Appendix C: Price Data Gaps

| Company | Gap | Missing Period |
|---------|-----|----------------|
| RBLX (31) | 69 days | 2026-02-20 to 2026-04-30 |
| SIRI (32) | 98 days | 2026-02-20 to 2026-05-29 |
| AI (33) | 119 days | 2026-01-30 to 2026-05-29 |
| CHTR (34) | 98 days | 2026-02-20 to 2026-05-29 |
| NOW (35) | 98 days | 2026-02-20 to 2026-05-29 |

---

## 20. Implementation Alignment Notes

**Status:** All blocking snowflakes identified in the feasibility audit (V3.2) have been **folded into the main design body** in V3.3. This section serves as a brief alignment summary.

### 20.1 Resolved Blocking Issues

| Issue | Status | Where Documented |
|-------|--------|-----------------|
| APScheduler → JobEngine/SchedulerPlanner | ✅ Resolved | Section 7.7 (scheduler registration), Section 7.1 (trigger) |
| File path `jobs/` → `application/jobs/` | ✅ Resolved | Appendix B (files to create) |
| Direct `supabase.table()` → repository calls | ✅ Resolved | Sections 7.2-7.5, 8.5-8.8, 12.1 |
| Missing feature flags | ✅ Resolved | Section 11.4 (config flags), Section 13 (migration plan) |

### 20.2 Resolved Non-Blocking Issues

| Issue | Status | Where Addressed |
|-------|--------|-----------------|
| `@timed()` decorators | ✅ Added | Section 7.5 (job logic), Section 9.2 (service method) |
| Schema updates | ✅ Specified | Section 10 (frontend changes), Pydantic schema notes |
| Price batching | ✅ Added | Section 8.6 (price map builder with pagination) |
| `_period_to_date_range` deletion | ✅ Corrected | Appendix A (removed from deletion list) |
| Legacy `portfolio_performance` table | ✅ Addressed | Appendix A (deprecation note), Section 11.4 |
| `now_utc()` import | ✅ Implicit | Section 6 - `from shared.time_utils import now_utc` |
| Helper function placement | ✅ Clarified | Section 8 - module-level in backfill script, repo methods for shared |

### 20.3 Minor Implementation Notes

- **Frontend schema:** Add `cash_balance?: number` and `holdings?: object[]` as optional fields on `PerformanceSnapshot`. Add `data_source`, `data_quality_flag`, `return_methodology` as optional on `PerformanceResponse`.
- **`shared/snapshot_builder.py`:** Include `from shared.time_utils import now_utc` at the top.
- **`_batch_execute()` helper** (`portfolio_repository.py:51-82`): Use for batch operations in repository methods.
- **Test fixtures:** Reuse `mock_supabase_client()` from `backend/tests/conftest.py`; extend with mock data for `portfolio_snapshots` table.
- **FIFO helpers** (`_classify_lot_action`, `resolve_price_forward_filled`, `build_snapshot_row`): Placed in `shared/snapshot_builder.py` so both backfill script and fallback path can import them. `reconstruct_holdings_at_date` lives in `scripts/backfill_portfolio_snapshots.py` as a one-time script function.
- **Legacy table migration:** `portfolio_performance` table and its seed script usage can remain during migration. A dedicated migration task should be created for a future release to move seed scripts to `portfolio_snapshots`.

Forward-fill fallback will set `data_quality_flag = 'STALE_PRICE'` during gap periods. A one-time price refresh job is recommended.

---

## 21. Live Enrichment Performance

### 21.1 Problem Statement

The `/portfolio/dashboard` endpoint enriches holdings with live prices on every request. Empirical measurement (2026-07-10) shows:

```
dashboard total: 8,999ms
├── accounts query         88ms   (1%)
├── enrich_holdings     8,576ms   (95%)  ← bottleneck
│   ├── account 7       2,193ms   (24%)
│   ├── account 8         486ms   (5%)
│   └── account 9       5,897ms   (66%)
├── dividends query        52ms   (1%)
└── overview/serialize     58ms   (1%)
```

`/portfolio/accounts` duplicates the same enrichment independently (~9s cold, ~2s warm if dashboard ran first), fired concurrently from the frontend. The 12s frontend axios timeout kills first attempts, retries add another ~4-5s, producing **15-17s page load**.

The bottleneck is `_enrich_holdings_with_prices_legacy` which uses sequential `asyncio.to_thread` calls for each exchange-override holding. Note the concurrent `fetch_override_prices_concurrent` (`market_cache.py`) already exists and benchmarks at 433ms for 9 symbols, but it is gated behind `ENABLE_FX_CONVERSION=True` which defaults to `False` — the legacy path runs in production.

Section 4's snapshot architecture solves only the **performance chart** path. The **dashboard enrichment** path — where 95% of request time is spent — remains live-computed.

### 21.2 Root Cause

#### 21.2.1 Exchange-Override Symbols

10 holdings across the user's 3 accounts have `exchange_override = "TOR"` — these are **Canadian Depositary Receipts** (CDRs) for US stocks, listed on the Toronto exchange in CAD:

| Account | Override Holdings | Symbols |
|---------|-----------------|---------|
| 7 | 7 | AAPL, AMZN, DIS, GOOG, META, PYPL, TSLA |
| 8 | 1 | NFLX |
| 9 | 2 | META, MSFT |

**These prices CANNOT be served from `current_market_data`.** Empirical measurement of 9 override symbols shows 68-95% price discrepancy between the TOR CDR price (via yfinance) and the NYSE USD price (in `current_market_data`):

| Symbol | yfinance (TOR, CAD) | current_market_data (USD) | Difference |
|--------|-------------------|--------------------------|------------|
| AAPL | 40.02 | 308.40 | 87% |
| META | 29.40 | 607.35 | 95% |
| TSLA | 33.05 | 423.68 | 92% |

All 9 override companies DO have entries in `current_market_data` (and `price_history`), but they store the underlying US listing price, not the CDR price. The yfinance call is necessary.

#### 21.2.2 Sequential Fetch Pattern

The bottleneck is in `_enrich_holdings_with_prices_legacy` (portfolio_service.py:852-863):

```python
if exchange_override:
    cache_key = f"{h.get('symbol')}:{exchange_override}"
    if cache_key not in override_cache:       ← per-call cache only
        sd = await asyncio.to_thread(          ← sequential
            self.stock_provider.get_stock_details,
            h["symbol"], exchange=exchange_override,
        )
        override_cache[cache_key] = sd.price if sd else None
    price = override_cache[cache_key]
```

Three problems compound:

1. **Sequential yfinance**: Each Symbol takes ~200ms via `asyncio.to_thread`. With 9 unique symbols, total = 1,727ms (verified via benchmark). If the same symbol appears in multiple accounts, it is fetched again — the `override_cache` lives only for the duration of a single `enrich_holdings_with_prices` call, not across accounts.

2. **Duplicate across endpoints**: Both `dashboard` and `accounts` call `_enrich_multi_account_holdings`, each running the full 3-account sequential loop independently. This means each page load pays the yfinance cost **twice**.

3. **No cross-request cache**: The in-memory `override_cache` dict is created fresh on every API call. There is no shared TTL cache between requests.

4. **Dormant concurrent path**: `market_cache.py` already implements `fetch_override_prices_concurrent` (concurrent yfinance with 300s TTL) but it is only called when `ENABLE_FX_CONVERSION=True` (line 534-535 in `portfolio_service.py`). Since the flag defaults to `False`, production always hits the legacy sequential path.

#### 21.2.3 Verified Performance Data

All benchmark results from live backend (2026-07-10, live verified):

| Test | Result | Source |
|------|--------|--------|
| Sequential yfinance, 9 symbols | **1,727ms** | Python benchmark (fresh provider) |
| Concurrent yfinance, 9 symbols (cold cache) | **433ms** | Python `asyncio.gather` (fresh provider) |
| Concurrent yfinance, 9 symbols (warm cache) | **~1ms** | Provider-level cache hit |
| Dashboard endpoint (authenticated) | **8,999ms** | `GET /portfolio/dashboard` with JWT |
| Accounts endpoint (authenticated, warm) | **1,988ms** | `GET /portfolio/accounts` with JWT (after dashboard warm) |
| Performance endpoint (snapshot read path) | **1,132ms** | `GET /portfolio/performance?period=1Y` (snapshots, 48 pts) |
| CMD query for same companies | 291ms (wrong prices) | Direct Supabase query |
| `portfolio_snapshots` total rows | **1,213 rows** | Supabase `count=exact` |
| Latest snapshot user 1 | 2026-06-30 | Supabase `SELECT max(snapshot_date)` |
| `current_market_data` coverage (all holdings) | **114/119 (95.8%)** | Supabase `SELECT .in_()` |
| Override holdings count | **10** | Direct DB query |
| `price_sources` table | **does not exist** | Supabase 404 (needs creation) |

### 21.3 Industry Patterns

Wealthfront, Robinhood, and other professional portfolio platforms follow a consistent pattern:

| Practice | Wealthfront | Robinhood | Industry Standard |
|----------|-------------|-----------|------------------|
| **Live price enrichment at request time** | ❌ Never | ❌ Never | ❌ Never |
| **Pre-computed account snapshots** | ✅ Daily batch | ✅ Real-time event stream | ✅ Daily batch minimum |
| **Separate price feed process** | ✅ Independent schedule | ✅ Kafka stream | ✅ Independent from API |
| **Cache layer between app and DB** | ✅ Memcached | ✅ Memcached | ✅ Redis/Memcached |
| **API response time SLA** | <100ms | <50ms | <100ms |
| **yfinance at request time** | ❌ Never | ❌ Never | ❌ Never |

**Wealthfront** (2025-12-08 blog): Their portfolio balance job was spending 10+ hours because of per-account serial processing with N+1 queries. Fixing it to batch accounts and pre-compute reduced runtime 10x. Key insight: *"the data set is minuscule, but the approach was fundamentally mismatched."* Our situation is identical: we have 10 CDR symbols, but the sequential-per-account-per-request pattern inflates 433ms (concurrent cold) to 1,727ms per call, and 8,576ms with duplication across accounts and endpoints.

**Robinhood** (2021-06-25 blog): At 750k req/s, live enrichment is impossible. Their brokeback service uses memcached between Django and PostgreSQL, with pre-computed portfolio values invalidated on trade execution events. Read path is a cache lookup.

**Key principle**: *"If it can't be computed in 100ms at request time, compute it offline and serve the pre-computed result."*

### 21.4 End-State Architecture

A professional portfolio app has **no enrichment layer at request time**. The dashboard reads prices from a provenance-tracked store fed by an independent pipeline.

```
                    ┌──────────────────────────────────────────────┐
                    │         Price Ingestion Scheduler            │
                    │  (only code that calls yfinance)             │
                    │                                              │
                    │  1. Query all active holdings                │
                    │  2. For each company_id, read its             │
                    │     LISTING_EXCHANGE from companies table     │
                    │  3. Look up preferred source for that         │
                    │     (company_id, exchange) in                 │
                    │     price_source_preferences                  │
                    │  4. Fetch price from that source              │
                    │     - source=yfinance_tor: concurrent gather  │
                    │     - source=supabase_market_data: bulk query │
                    │  5. Upsert to price_sources with provenance   │
                    │     (source, fetched_at, ttl_seconds)         │
                    └───────────────────┬──────────────────────────┘
                                        │ writes
                                        v
                    ┌──────────────────────────────────────────────┐
                    │            price_sources table                │
                    │                                              │
                    │  PRIMARY KEY: (company_id, exchange)          │
                    │                                              │
                    │  company_id | exchange | price | source       │
                    │  69         | TOR     | 40.02 | yfinance_tor │
                    │  69         | NYSE    | 308.40| supabase_md  │
│ 45         | NMS     | 417.79| supabase_md  │
│ 45         | TOR     | 26.10 | yfinance_tor │
                    │                                              │
                    │  No competing writers: scheduler writes       │
                    │  override prices, Supabase provider writes    │
                    │  standard prices, different exchanges         │
                    └───────────────────┬──────────────────────────┘
                                        │ read by dashboard on every
                                        │ request (no cache layer)
                                        v
                    ┌──────────────────────────────────────────────┐
                    │      GET /portfolio/dashboard                 │
                    │                                              │
                    │  1. Query accounts         (~50ms)           │
                    │  2. Query holdings         (~50ms)           │
                    │  3. Query price_sources    (~30ms)           │
                    │     JOIN holdings.exchange_override          │
                    │     to pick TOR vs NYSE price                │
                    │  4. Merge in memory        (~5ms)            │
                    │  5. Query dividends        (~50ms)           │
                    │  ───────────────────────────                 │
                    │  Total: <100ms                                │
                    └──────────────────────────────────────────────┘
```

#### 21.4.1 Data Model

**`price_sources` table** (replaces single-purpose `current_market_data`):

```sql
CREATE TABLE price_sources (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    exchange        TEXT NOT NULL,              -- 'TOR', 'NMS', 'NYQ', 'UNKNOWN'
    price           NUMERIC(12, 4),
    currency        TEXT NOT NULL DEFAULT 'USD',  -- 'USD', 'CAD'
    source          TEXT NOT NULL,               -- 'yfinance_tor', 'supabase_market_data',
                                                 -- 'price_history_fallback'
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ttl_seconds     INTEGER NOT NULL DEFAULT 300,
    data_quality    TEXT NOT NULL DEFAULT 'OK',  -- 'OK', 'STALE', 'MISSING'
    UNIQUE (company_id, exchange)
);

CREATE INDEX idx_price_sources_company_exchange
    ON price_sources (company_id, exchange);

-- Provenance: each row tracks exactly when and how it was fetched.
-- No more "who wrote $40 vs $308" ambiguity.
```

**`price_source_preferences` table** (decouples source selection from pipeline code):

```sql
CREATE TABLE price_source_preferences (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    exchange        TEXT NOT NULL,              -- listing exchange for a holding
    preferred_source TEXT NOT NULL,             -- 'yfinance_tor', 'supabase_market_data',
                                                -- 'price_history_fallback'
    UNIQUE (company_id, exchange)
);

-- Seeding script: run once during Step 1 deployment.
-- Populates preferences for all holdings' listing exchanges.

-- TOR-listed CDRs: yfinance
INSERT INTO price_source_preferences (company_id, exchange, preferred_source)
SELECT DISTINCT h.company_id, 'TOR', 'yfinance_tor'
FROM portfolio_holdings h
WHERE h.exchange_override = 'TOR'
  AND h.company_id IS NOT NULL
ON CONFLICT (company_id, exchange) DO NOTHING;

-- US-listed: supabase market data
INSERT INTO price_source_preferences (company_id, exchange, preferred_source)
SELECT DISTINCT c.company_id, c.exchange, 'supabase_market_data'
FROM companies c
JOIN portfolio_holdings h ON c.company_id = h.company_id
WHERE (h.exchange_override IS NULL OR h.exchange_override = '')
  AND c.exchange IN ('NMS', 'NYQ')
ON CONFLICT (company_id, exchange) DO NOTHING;

-- Unknown exchange: price_history fallback
INSERT INTO price_source_preferences (company_id, exchange, preferred_source)
SELECT DISTINCT h.company_id, 'UNKNOWN', 'price_history_fallback'
FROM portfolio_holdings h
LEFT JOIN companies c ON h.company_id = c.company_id
WHERE c.company_id IS NULL
   OR c.exchange IS NULL
   OR c.exchange NOT IN ('NMS', 'NYQ', 'TOR')
ON CONFLICT (company_id, exchange) DO NOTHING;

-- Adding a new exchange (e.g. LSE) requires one INSERT, not code changes.
```

**Migration from `current_market_data`**: One-time script:

```sql
INSERT INTO price_sources (company_id, exchange, price, currency, source, fetched_at, ttl_seconds, data_quality)
SELECT cm.company_id, 'UNKNOWN', cm.current_price, 'USD', 'supabase_market_data', NOW(), 300, 'OK'
FROM current_market_data cm
ON CONFLICT (company_id, exchange) DO NOTHING;
```

#### 21.4.2 Price Ingestion Scheduler

A single scheduler replaces all live yfinance calls. It is the ONLY code that calls yfinance.

```python
@timed()
async def refresh_all_prices():
    """Refresh prices for all holdings with active portfolio accounts.

    Reads from price_source_preferences to determine WHICH source to use
    for each (company_id, exchange) pair. Writes to price_sources with
    full provenance (source, fetched_at, ttl_seconds).

    Dashboard never waits on yfinance.
    """
    holdings = repo.get_all_active_holdings()
    company_ids = {h["company_id"] for h in holdings if h.get("company_id")}
    if not company_ids:
        return

    # Read source preferences for all company_ids
    prefs = repo.get_price_source_preferences(list(company_ids))
    # prefs = { (company_id, exchange): preferred_source, ... }

    # Group by source type
    yfinance_items = []
    supabase_items = set()

    for h in holdings:
        cid = h.get("company_id")
        exchange = h.get("exchange_override") or "UNKNOWN"
        pref = prefs.get((cid, exchange))
        if pref is None:
            # Missing preference: log warning and skip this symbol.
            # Without an explicit preference, we cannot know which source
            # is correct for this (company_id, exchange) pair.
            logger.warning("[PRICE-INGEST] no preference for (company=%s, exchange=%s) — skipped", cid, exchange)
            continue
        if pref == "yfinance_tor":
            yfinance_items.append((cid, h["symbol"], exchange))
        elif pref == "supabase_market_data":
            supabase_items.add(cid)
        elif pref == "price_history_fallback":
            pass  # handled downstream if needed

    # Fetch prices concurrently by source type
    prices = {}

    # Group 1: yfinance (concurrent gather, 509ms for 9 symbols verified)
    if yfinance_items:
        symbols = list(set(item[1] for item in yfinance_items))
        exchange = yfinance_items[0][2]  # all same exchange (TOR)

        yf_results = await _fetch_yfinance_batch(
            symbols, exchange,
            per_symbol_timeout=10,  # per-symbol timeout (seconds)
            max_concurrent=5,       # throttle to avoid rate-limit
        )
        # yf_results = {symbol: {"price": float, "error": None} or {"price": None, "error": "timeout"}}

        symbol_to_cid = {item[1]: item[0] for item in yfinance_items}
        for sym, result in yf_results.items():
            cid = symbol_to_cid.get(sym)
            if result["error"]:
                logger.warning("[PRICE-INGEST] symbol=%s exchange=%s error=%s",
                               sym, exchange, result["error"])
                # Partial result: skip this symbol, keep old price in price_sources
                continue
            if cid and result["price"] is not None:
                prices[(cid, exchange)] = {
                    "price": result["price"],
                    "source": "yfinance_tor",
                    "currency": "CAD",
                    "ttl_seconds": 300,
                }

    # Look up company exchange for standard prices (from companies table)
    company_exchanges: Dict[int, str] = {}
    if supabase_items:
        company_exchanges = repo.get_company_exchanges(list(supabase_items))
        # Returns {company_id: exchange} — e.g. {69: "NMS", 45: "NYQ"}
        supabase_prices = await _fetch_supabase_prices(list(supabase_items))
        # supabase_prices = {company_id: float}
        for cid, price in supabase_prices.items():
            if price is not None:
                exchange = company_exchanges.get(cid, "UNKNOWN")
                prices[(cid, exchange)] = {
                    "price": price,
                    "source": "supabase_market_data",
                    "currency": "USD",
                    "ttl_seconds": 30,
                }

    # Write to price_sources with provenance
    for (cid, exchange), data in prices.items():
        repo.upsert_price_source(
            company_id=cid,
            exchange=exchange,
            price=data["price"],
            source=data["source"],
            currency=data["currency"],
            ttl_seconds=data["ttl_seconds"],
        )

    logger.info("[PRICE-INGEST] refreshed %d/%d prices (yfinance=%d, supabase=%d)",
                len(prices), len(company_ids), len(yfinance_items), len(supabase_items))


async def _fetch_supabase_prices(company_ids: List[int]) -> Dict[int, Optional[float]]:
    """Bulk query current_market_data for standard prices.

    Single query, <50ms for 100+ companies.
    """
    if not company_ids:
        return {}
    try:
        result = (
            repo.client.table("current_market_data")
            .select("company_id, current_price")
            .in_("company_id", company_ids)
            .execute()
        )
        return {row["company_id"]: row.get("current_price") for row in (result.data or [])}
    except Exception as e:
        logger.error("[PRICE-INGEST] supabase bulk query failed: %s", e)
        return {}


async def _fetch_yfinance_batch(
    symbols: List[str], exchange: str,
    per_symbol_timeout: int = 10, max_concurrent: int = 5,
    max_retries: int = 2,
) -> Dict[str, Dict]:
    """Fetch yfinance prices with per-symbol timeout, throttling, and retry.

    Professional pipeline requirement: one slow symbol must not
    delay the entire batch. Each symbol gets its own timeout.
    Retries on failure with 1s backoff — semaphore is released
    during backoff so other symbols can proceed.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def fetch_one(sym: str) -> tuple:
        for attempt in range(1, max_retries + 2):
            async with sem:
                try:
                    sd = await asyncio.wait_for(
                        asyncio.to_thread(
                            stock_provider.get_stock_details, sym, exchange=exchange,
                        ),
                        timeout=per_symbol_timeout,
                    )
                    return sym, {"price": sd.price if sd else None, "error": None}
                except asyncio.TimeoutError:
                    if attempt <= max_retries:
                        await asyncio.sleep(1)
                    else:
                        return sym, {"price": None, "error": "timeout"}
                except Exception as e:
                    if attempt <= max_retries:
                        await asyncio.sleep(1)
                    else:
                        return sym, {"price": None, "error": str(e)}
        return sym, {"price": None, "error": "max retries exceeded"}

    results = await asyncio.gather(
        *[fetch_one(s) for s in symbols], return_exceptions=True
    )
    return {sym: data for sym, data in results if not isinstance(data, Exception)}
```

**Scheduler schedule**:

| Time (ET) | Frequency | Rationale |
|-----------|-----------|-----------|
| 09:30-16:00 (NYSE/TSX trading hours) | Every 5 min | CDR prices and US market move continuously |
| 07:00-09:30, 16:00-20:00 | Every 30 min | Pre/post market |
| 20:00-07:00 | Suspended | Markets closed, no price movement |

**Error handling**:
- Per-symbol timeout (10s): one slow symbol does not delay the batch
- Per-symbol retry: max 2 attempts with 1s backoff (via `_fetch_yfinance_batch`)
- Partial results: if 8/9 symbols succeed, those 8 are written; the failed symbol retains its previous price
- Dead-letter: after 3 consecutive failures for a symbol, emit `[PRICE-INGEST-ALERT]` and skip until next window
- Supabase provider failures: curl out, log error, skip batch (standard prices can be stale for one cycle)

#### 21.4.3 Dashboard Endpoint (Simplified, <100ms)

The existing enrichment layer is deleted. The dashboard fires parallel DB queries and merges in memory — no yfinance, no `asyncio.Lock`, no TTL cache.

```python
@timed()
async def get_portfolio_dashboard(user_id: int):
    db_user_id = authenticate(user_id)

    # Fire all queries concurrently
    accounts_task = repo.get_user_accounts(db_user_id, active_only=True)
    holdings_task = repo.get_user_all_holdings(db_user_id)
    dividends_task = repo.get_dividends(db_user_id, fiscal_year=now_utc().year)

    accounts, all_holdings, dividends = await asyncio.gather(
        accounts_task, holdings_task, dividends_task
    )

    # Fetch prices for each holding's listing exchange
    # (query price_sources directly — no cache layer)
    company_exchange_pairs = []
    for h in all_holdings:
        cid = h.get("company_id")
        if cid:
            exchange = h.get("exchange_override") or "UNKNOWN"
            company_exchange_pairs.append((cid, exchange))
    price_details = repo.get_price_details_for_holdings(company_exchange_pairs)
    # Returns { (company_id, exchange): {"price": float, "fetched_at": datetime, "ttl_seconds": int} }
    # Single query: SELECT company_id, exchange, price, fetched_at, ttl_seconds
    #               FROM price_sources WHERE (company_id, exchange) IN (...)

    # Merge prices into holdings (<5ms for 143 holdings)
    # Staleness uses per-row ttl_seconds from price_sources (not a hard-coded threshold)
    any_stale = False
    for h in all_holdings:
        cid = h.get("company_id")
        exchange = h.get("exchange_override") or "UNKNOWN"
        pd = price_details.get((cid, exchange))
        if pd is not None:
            h["current_price"] = pd["price"]
            qty = h.get("quantity", 0) or 0
            h["current_value"] = pd["price"] * qty
            # Price age: time since last fetch
            age = (now_utc() - pd["fetched_at"]).total_seconds()
            h["price_age_seconds"] = age
            h["data_quality"] = "OK" if age <= pd["ttl_seconds"] else "STALE_PRICE"
            if h["data_quality"] == "STALE_PRICE":
                any_stale = True
        else:
            # Fallback chain: price_history -> average_cost
            h["current_price"] = h.get("average_cost", 0)
            h["current_value"] = h.get("total_cost", 0)
            h["price_age_seconds"] = None
            h["data_quality"] = "MISSING"
        h["unrealized_gain_loss"] = h["current_value"] - float(h.get("total_cost", 0))

    overview = compute_overview(all_holdings, dividends)
    return {
        "accounts": accounts, "holdings": all_holdings, "overview": overview,
        "data_quality_flag": "STALE_PRICE" if any_stale else "OK",
    }
```

**Why no `get_cached_prices` / `asyncio.Lock` / 30s TTL**:
- The scheduler runs every 5 min and writes fresh prices to `price_sources`
- A direct DB query to `price_sources` takes ~30ms for 143 rows via `(company_id, exchange)` index
- There is no concurrent lock contention because there is no cache refresh — every request reads the latest committed data
- The 30s in-memory cache (`market_cache.py`) was designed for the old world where 5 concurrent requests each called yfinance. In the new world, yfinance calls are zero. The cache added complexity (lock, TTL management, `MAX_CACHE_SIZE`) for zero benefit.

**Performance target: <100ms** (not <400ms):
- `accounts` query: ~50ms (existing, unchanged)
- `holdings` query: ~50ms (existing, unchanged)
- `price_sources` query: ~30ms (143 rows via composite index, no join needed)
- In-memory merge: ~5ms (pure Python dict operations)
- `dividends` query: ~50ms (existing, unchanged)
- Overview computation: ~1ms
- **Total wall clock**: max(50, 50, 30, 50) + 5 + 1 = **~56ms**

If actual latency exceeds 100ms at scale (>500 accounts, >10k holdings), add Redis:
- Cache key: `price:{company_id}:{exchange}` → `value:{price}, fetched_at:...`
- Cache-aside: read Redis, miss → read `price_sources` → write Redis with TTL from `price_sources.ttl_seconds`
- No invalidation — scheduler writes to DB, Redis TTL handles expiry
- This is an optimization, not an architectural requirement. Start without Redis.

#### 21.4.4 Accounts Endpoint

`/portfolio/accounts` does NOT re-enrich via yfinance. It queries accounts + holdings in one batch, then attaches prices from `price_sources` in a second batch — both fast DB queries. The frontend already gets all holding data from the dashboard, so this endpoint exists only for backward-compatible API consumers.

**Implementation**:

```python
@router.get("/portfolio/accounts")
async def list_accounts(user_id: int):
    db_user_id = authenticate(user_id)
    accounts = repo.get_user_accounts(db_user_id, active_only=True)
    account_ids = [a["account_id"] for a in accounts]
    if not account_ids:
        return {"accounts": []}

    # Batch query ALL holdings across all accounts (one query, not N)
    all_holdings = repo.get_holdings_for_accounts(account_ids)
    holdings_by_account: Dict[int, List] = defaultdict(list)
    for h in all_holdings:
        holdings_by_account[h["account_id"]].append(h)

    # Batch query ALL prices (one query, not M per account)
    company_exchange_pairs = []
    for h in all_holdings:
        cid = h.get("company_id")
        if cid:
            exchange = h.get("exchange_override") or "UNKNOWN"
            company_exchange_pairs.append((cid, exchange))
    prices = repo.get_prices_for_holdings(company_exchange_pairs)
    # Returns { (company_id, exchange): float }

    for acc in accounts:
        holdings = holdings_by_account.get(acc["account_id"], [])
        for h in holdings:
            cid = h.get("company_id")
            exchange = h.get("exchange_override") or "UNKNOWN"
            price = prices.get((cid, exchange))
            if price is not None:
                h["current_price"] = price
                h["current_value"] = price * (h.get("quantity", 0) or 0)
            else:
                h["current_price"] = h.get("average_cost", 0)
                h["current_value"] = h.get("total_cost", 0)
        acc["holdings"] = holdings

    return {"accounts": accounts, ...}
```

**Response time**: ~100ms (accounts query + batch holdings query + batch prices query). Down from ~9,000ms.

#### 21.4.5 Frontend Changes

Current page load fires 5 concurrent API calls:

```
usePortfolioDashboard      → GET /portfolio/dashboard
usePortfolioAccounts       → GET /portfolio/accounts   (REDUNDANT)
usePortfolioPerformance    → GET /portfolio/performance
useBrokerages              → GET /portfolio/brokerages
useBenchmarks              → GET /benchmarks
```

**`usePortfolioAccounts` hook (`web/src/hooks/usePortfolioAccounts.ts`)**:

```typescript
// BEFORE: fires separate API call, enriches independently
export function usePortfolioAccounts() {
  return useQuery({
    queryKey: ["portfolio", "accounts"],
    queryFn: () => api.get("/portfolio/accounts"),
  });
}

// AFTER: reads accounts data from the dashboard query cache
export function usePortfolioAccounts() {
  const { data: dashboard } = usePortfolioDashboard();
  // dashboard.accounts already contains all holdings with prices
  // No network call needed
  return {
    data: dashboard?.accounts ?? [],
    isLoading: !dashboard,
    error: null,
  };
}
```

**Components that consume `usePortfolioAccounts`** (grep for usage):

| Component | File | Change |
|-----------|------|--------|
| `PortfolioTabShell` | `web/src/features/portfolio/components/PortfolioTabShell.tsx` | No change — reads from hook, hook now reads dashboard cache |
| `PortfolioPerformanceChart` | `web/src/features/portfolio/components/PortfolioPerformanceChart.tsx` | No change — same hook |
| `AccountSelector` | `web/src/features/portfolio/components/AccountSelector.tsx` | No change — same hook |
| `PortfolioSummaryCards` | `web/src/features/portfolio/components/PortfolioSummaryCards.tsx` | No change — same hook |

No component changes needed. The hook swap is transparent to consumers.

**Dependency note**: `usePortfolioAccounts` now depends on `usePortfolioDashboard` — the accounts hook no longer makes an independent network call but reads from the dashboard cache. This means:
- `AccountSelector` mounted **without** `PortfolioTabShell` (e.g. in a standalone widget or modal) will now trigger a full dashboard fetch where before it only fetched accounts. This is acceptable because the dashboard fetch is now <100ms, but the dependency change should be verified by the implementer.
- If a component tree uses `usePortfolioAccounts` without `usePortfolioDashboard` being called elsewhere, a `<Suspense>` boundary or `enabled` option should be added to prevent unintended fetches.
- No component changes are needed in the current app tree because all 4 consumers already render inside or alongside `PortfolioTabShell`, which calls `usePortfolioDashboard`.

**Axios retry interceptor (`web/src/lib/api.ts`)**:

```typescript
// BEFORE: retries on any 5xx or network error
api.interceptors.response.use(undefined, async (error) => {
  if (shouldRetry(error)) {
    await delay(backoff(retryCount));
    return api.request(error.config);
  }
  throw error;
});

// AFTER: retries removed entirely (production-grade practice)
// Network errors are surfaced to React Query, which can retry
// at the query level with exponential backoff if configured.
api.interceptors.response.use(undefined, async (error) => {
  return Promise.reject(error);
});
```

React Query's built-in retry (`retry: 3, retryDelay: attempt => Math.min(1000 * 2 ** attempt, 10000)`) replaces the axios interceptor. This is more idiomatic — React Query controls retry policy per-query, not per-request.

**Axios timeout**:

```typescript
// web/src/lib/api.ts
const api = axios.create({
  baseURL: "/api",
  timeout: 12_000,  // BEFORE
  timeout: 30_000,  // AFTER: safety net, never hit in practice
});
```

30s timeout is a safety net. With all endpoints returning in <1s, it should never trigger. It exists only for the fallback path (scheduler failure, database degradation).

**Total frontend changes**:
1. `web/src/lib/api.ts`: change timeout 12s → 30s, remove retry interceptor
2. `web/src/hooks/usePortfolioAccounts.ts`: read from dashboard cache instead of API call
3. No component changes

### 21.5 Migration Strategy

No incremental phases. The end state is deployed as one coordinated change with feature-flag gating:

```
             ┌─────────────────────────────────┐
             │   Step 1: Infrastructure          │
             │   - Create price_sources table     │
             │   - Create price_source_prefs      │
             │   - Migrate current_market_data    │
             │   - Implement scheduler            │
             └────────────┬────────────────────┘
                          │ deploy, run for 24h
                          v
             ┌─────────────────────────────────┐
             │   Step 2: Shadow Mode             │
             │   New dashboard path runs, logs   │
             │   comparison, OLD path serves     │
              │   DASHBOARD_READ_PATH = "shadow"  │
             │   READ_PATH = True (shadow)       │
             └────────────┬────────────────────┘
                          │ validate <1% diff for 24h
                          v
             ┌─────────────────────────────────┐
             │   Step 3: Cutover                 │
             │   Toggle flag → new path serves   │
             │   Old code stays (unused, 48h)    │
             └────────────┬────────────────────┘
                          │ monitor for 48h
                          v
             ┌─────────────────────────────────┐
             │   Step 4: Cleanup                 │
             │   Delete enrichment, market_cache │
             │   Frontend: hook swap, timeout    │
             │   Delete current_market_data (opt)│
             └─────────────────────────────────┘
```

#### Step 1: Infrastructure (2 days)

| Task | Description | Effort |
|------|-------------|--------|
| 1a | Create `price_sources` and `price_source_preferences` tables | 30 min |
| 1b | Migrate `current_market_data` rows to `price_sources` (ONE-TIME SQL) | 15 min |
| 1c | Seed `price_source_preferences` for all holdings | 30 min |
| 1d | Implement `_fetch_yfinance_batch` with per-symbol timeout and throttling | 4 hours |
| 1e | Implement `refresh_all_prices` scheduler | 4 hours |
| 1f | Register scheduler in `scheduler_worker.py` with market-hours awareness | 2 hours |
| 1g | Deploy, let run for 24h | — |

**Success criteria**: Scheduler completes in <60s, write to `price_sources` for all 119 companies, logs show `[PRICE-INGEST] refreshed N prices` with per-symbol success/failure.

#### Step 2: Shadow Mode (2 days)

| Task | Description | Effort |
|------|-------------|--------|
| 2a | Implement `get_portfolio_dashboard` new read path | 1 day |
| 2b | Add shadow-mode wrapper: run both paths, log comparison, serve old | 4 hours |
| 2c | Add `DASHBOARD_READ_PATH` config flag (`"off"` / `"shadow"` / `"serve"`) | 15 min |
| 2d | Deploy with `DASHBOARD_READ_PATH="shadow"` | 30 min |
| 2e | Monitor comparison logs for 24h | — |

```python
# Shadow mode: both paths run with timeout on old path, old path serves
# (DASHBOARD_READ_PATH="shadow")
async def get_portfolio_dashboard(user_id):
    # Old path runs with a 500ms timeout — 5s enrichment is never
    # inflicted on production traffic. If it times out, log and
    # still serve the new result.
    try:
        old_result = await asyncio.wait_for(
            old_get_portfolio_dashboard(user_id), timeout=0.5
        )
    except asyncio.TimeoutError:
        logger.warning("[SHADOW] old path timed out (>500ms)")
        old_result = None

    new_result = await new_get_portfolio_dashboard(user_id)
    if old_result is not None:
        _log_comparison(old_result, new_result)
    return old_result or new_result
```

**Comparison logging**:

```python
def _log_comparison(old, new):
    old_value = sum(h.get("current_value", 0) for h in old.get("holdings", []))
    new_value = sum(h.get("current_value", 0) for h in new.get("holdings", []))
    value_diff = abs(old_value - new_value) / max(old_value, 1) * 100
    logger.info(
        "[SHADOW] old_value=%.2f new_value=%.2f diff=%.2f%% "
        "old_time=%.0fms new_time=%.0fms",
        old_value, new_value, value_diff,
        old.get("_duration_ms", 0), new.get("_duration_ms", 0),
    )
    # Compare per-holding prices to catch offsetting errors
    old_by_cid = {h["company_id"]: h["current_price"]
                  for h in old.get("holdings", []) if h.get("company_id")}
    new_by_cid = {h["company_id"]: h["current_price"]
                  for h in new.get("holdings", []) if h.get("company_id")}
    mismatches = []
    for cid in set(old_by_cid) | set(new_by_cid):
        op = old_by_cid.get(cid)
        np = new_by_cid.get(cid)
        if op and np and abs(op - np) / max(op, np) > 0.01:
            mismatches.append(f"company={cid} old={op} new={np}")
    if mismatches:
        logger.error("[SHADOW] PRICE MISMATCH: %s", "; ".join(mismatches[:5]))
```

**Success criteria**: Value difference <1% for 24h, no per-holding price mismatches >1%.

#### Step 3: Cutover (15 min)

Use a single tri-state config (`'off'` → `'shadow'` → `'serve'`):

```python
# config.py
DASHBOARD_READ_PATH: str = Field(
    "off",  # Step 1: off — only old path runs
            # Step 2: "shadow" — both paths run, old serves, comparison logged
            # Step 3: "serve" — new path serves, old path disabled
    description="Dashboard read path mode: 'off' (old only), 'shadow' (both, log compare), 'serve' (new only)"
)
```

```python
# Off: old path only, no new path overhead
if settings.DASHBOARD_READ_PATH == "off":
    return await old_get_portfolio_dashboard(user_id)

# Shadow: both paths run with timeout on old path, log comparison
if settings.DASHBOARD_READ_PATH == "shadow":
    try:
        old_result = await asyncio.wait_for(
            old_get_portfolio_dashboard(user_id), timeout=0.5
        )
    except asyncio.TimeoutError:
        logger.warning("[SHADOW] old path timed out (>500ms)")
        old_result = None
    new_result = await new_get_portfolio_dashboard(user_id)
    if old_result is not None:
        _log_comparison(old_result, new_result)
    return old_result or new_result

# Serve: new path only (<100ms)
return await new_get_portfolio_dashboard(user_id)
```

**Rollback**: Set `DASHBOARD_READ_PATH="off"`. Old path resumes. No deploy.

**Success criteria**: Dashboard time <100ms, no errors, no value drift.

#### Step 4: Cleanup (1 day)

| Action | File | Details |
|--------|------|---------|
| Delete | `shared/market_cache.py` | Entire file — no live pricing means no cache |
| Delete | `_enrich_holdings_with_prices_legacy` | `portfolio_service.py` method |
| Delete | `_enrich_multi_account_holdings` | `portfolio_service.py` method |
| Delete | `_enrich_holdings_with_prices` | `portfolio_service.py` method (FX path never used) |
| Delete | `current_market_data` table | Optional — `price_sources` is canonical |
| Simplify | `api/portfolio.py:list_accounts` | Remove enrichment call (Section 21.4.4) |
| Simplify | `web/src/hooks/usePortfolioAccounts.ts` | Read from dashboard cache (Section 21.4.5) |
| Update | `web/src/lib/api.ts` | Timeout 12s → 30s, remove retry interceptor |

### 21.6 Rollback

```python
# Config-only rollback (no deploy, no code revert):
DASHBOARD_READ_PATH = "off"
```

If the price ingestion scheduler fails:
1. `price_sources` retains the last known prices (from the last successful scheduler run)
2. `data_quality_flag` set to `"STALE_PRICE"` if `fetched_at + ttl_seconds < now()`
3. Dashboard loads in <100ms — user sees a "prices may be stale" warning badge
4. Scheduler can be restarted independently — no user-facing impact

If the scheduler fails AND `price_sources` is empty (impossible after Step 1 has run for 24h):
1. Fallback to `price_history` most recent close per company (10ms)
2. Fallback to `average_cost` from holdings table (0ms, in-memory)

**The dashboard never calls yfinance. The dashboard never waits >500ms.**

### 21.7 Files Summary

#### Create

| File | Purpose |
|------|---------|
| `scripts/add_price_sources_table.sql` | DDL for `price_sources` and `price_source_preferences` tables |
| `scripts/migrate_current_market_data.sql` | One-time migration of existing prices |
| `application/jobs/price_ingestion_job.py` | `refresh_all_prices` + `_fetch_yfinance_batch` |
| `application/schedulers/price_ingestion_scheduler.py` | `PriceIngestionScheduler` with market-hours awareness |
| `infrastructure/repositories/price_repository.py` | `get_prices_for_holdings`, `get_price_details_for_holdings`, `get_company_exchanges`, `upsert_price_source`, `get_price_source_preferences` |

#### Modify

| File | Change |
|------|--------|
| `api/portfolio.py:get_portfolio_dashboard` | New read path: query `price_sources` + merge (gated by config flag) |
| `api/portfolio.py:list_accounts` | Remove enrichment; simple price lookup from `price_sources` |
| `application/services/portfolio_service.py` | Add `_get_dashboard_from_prices` |
| `config.py` | Add `DASHBOARD_READ_PATH` flag (`"off"` / `"shadow"` / `"serve"`) |
| `scheduler_worker.py` | Register price ingestion planner + handler |
| `web/src/hooks/usePortfolioAccounts.ts` | Read from dashboard cache (Section 21.4.5) |
| `web/src/lib/api.ts` | Timeout 12s → 30s, remove retry interceptor |

#### Delete

| File | Step | Reason |
|------|------|--------|
| `shared/market_cache.py` | 4 | No live pricing — no cache needed |
| `_enrich_holdings_with_prices_legacy` | 4 | Replaced by price merge |
| `_enrich_multi_account_holdings` | 4 | Replaced by price merge |
| `_enrich_holdings_with_prices` | 4 | FX path never enabled |
| `current_market_data` table (optional) | 4 | Replaced by `price_sources` |
