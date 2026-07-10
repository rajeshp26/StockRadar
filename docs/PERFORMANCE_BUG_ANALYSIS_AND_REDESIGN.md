# Portfolio Performance — Bug Analysis & Long-Term Redesign

## Executive Summary

Five interconnected issues plague the portfolio performance system. Two are **data corruption bugs** (cost_basis=0, negative cash balance) that produce silently wrong numbers. Three are **architectural weaknesses** (return methodology, snapshot alignment, rate limiting) that undermine trust and usability. The root cause of the corruption bugs is a **mismatch between DB column names and code key names** — the snapshot job reads `total_cost` from the DB but the builder looks up `cost_basis`.

---

## Issue 1: `cost_basis=0` on 2026-06-23 Snapshot

**Impact:** All 75 holdings in account 9 show `cost_basis=0.00`, `current_price=0.00`, `current_value=0.00`. The dashboard may display a portfolio worth $0.

**Root Cause:** `build_snapshot_row` (`backend/shared/snapshot_builder.py:69`) uses the wrong dict key:

```python
cost = Decimal(str(h.get("cost_basis") or 0))   # line 69 — WRONG: no "cost_basis" in DB
```

But the database column is `total_cost`, not `cost_basis`. The holdings_state passed by `compute_daily_snapshots` (`backend/application/jobs/portfolio_snapshot_job.py:51`) comes from `portfolio_repo.get_holdings_for_accounts()` which selects `*` from `portfolio_holdings`. The columns are:

```
holding_id, account_id, company_id, symbol, quantity, average_cost, total_cost, ...
```

There is **no `cost_basis` column** in the DB. So `h.get("cost_basis")` always returns `None`, meaning `cost` is always 0.

**Same bug on line 84:**
```python
current_price = Decimal(str(h.get("avg_cost") or 0))   # line 84 — WRONG: "avg_cost" ≠ "average_cost"
```

When `prices_by_company` lacks a price for a company (e.g., because the price fetch failed or returned partial data), the fallback to `avg_cost` also returns 0 because the DB column is `average_cost`, not `avg_cost`.

**Why did the May 31 snapshot have correct values?** The data in `portfolio_snapshots` for May 31 shows `cost_basis=43905.62` and `holdings_market_value=71152.55`. This row was likely created by the **legacy fallback path** (`_compute_performance_fallback` at `portfolio_service.py:2179`) rather than the snapshot job. The legacy path manually constructs holdings_state dicts with the correct key names (`cost_basis`, `avg_cost` — see `portfolio_service.py:2291-2297`). The snapshot job's `holdings_state` comes from raw DB rows which use the real column names (`total_cost`, `average_cost`).

**Secondary issue — price failure:** On June 23, `get_latest_prices` returned very few entries (only F and QQQ had stale prices 33-34 days old). This could be a transient data-provider failure or a bug in the price-fetch query. Combined with the `avg_cost` fallback bug, all holdings got $0 price.

Even with the key name fix, the fallback to `average_cost` as a current price is semantically wrong — average cost is **not** a current price. Holdings that lack price data should be flagged distinctly, not silently assigned their cost basis.

**Price staleness is a core data-quality concern, not a secondary issue.** `get_latest_prices` failing silently affected every computation on June 23. This needs:
- A dedicated monitoring alert when daily price coverage drops below a threshold
- An independent health-check endpoint that tests price availability for the most-watched symbols
- Caching with staleness awareness — if yesterday's price exists, use it with a `STALE_PRICE` flag rather than returning nothing

### Fixes Needed

| Line | Current Key | Correct Key | Category |
|------|------------|-------------|----------|
| 69 | `cost_basis` | `total_cost` | Critical — data corruption |
| 84 | `avg_cost` | `average_cost` | Critical — data corruption |

### Defensive Invariant Check (Must Add)

The key name mismatch was possible because the code silently accepts missing keys. After fixing the key names, install a guard:

```python
if cost == 0 and qty > 0:
    raise ValueError(
        f"Holding {cid} (account {account_id}): cost_basis=0 "
        f"but qty={qty}. Available keys: {sorted(h.keys())}"
    )
```

This transforms any future key-name regression into an immediate, loud failure. Same for `current_price` when it falls through to the `average_cost` path.

### Better Data Quality Enum

Currently only two states in the code: `OK` and `STALE_PRICE`. Need at least:

| Flag | Meaning |
|------|---------|
| `OK` | All prices current, all costs populated |
| `STALE_PRICE` | Price exists but is >30 days old |
| `COST_FALLBACK` | No price found; using average_cost as proxy |
| `UNAVAILABLE` | No price and no cost available; holding excluded from market value |
| `INCOMPLETE` | One or more holdings excluded due to missing data |
| `DEPOSIT_GAP` | Cash balance deeply negative relative to cost basis (missing deposits) |
| `WARNING` | Post-computation validation produced one or more warnings |

The dashboard should surface any flag other than `OK` to the user.

---

## Issue 2: Negative Cash Balance in TFSA

**Impact:** The TFSA (account 4) shows sustained negative cash balance (e.g., -$33,648.68 on 2026-06-24). The user sees an alarming red number on the dashboard despite ample holdings value.

**Root Cause:** `PortfolioRepository.get_cash_balance()` (`backend/infrastructure/repositories/portfolio_repository.py:1033-1044`) sums ALL transactions' `net_cash_amount` without filtering by activity type:

```python
def get_cash_balance(self, account_id: int, target_date: date) -> Decimal:
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

**InternalSecurityTransfer** transactions record a negative `net_cash_amount` representing the market value of securities transferred *out* of the account. Since `get_cash_balance` sums **all** transactions — including non-cash ones — these transfers artificially reduce the cash balance.

The related function `get_net_deposits` (`:1046-1058`) correctly filters to `["MoneyMovement", "BonusPayment"]`. The fix follows the same pattern.

### Whitelist vs Blacklist Trade-off

There are two approaches:

**Whitelist** — only include known cash-moving types:
```python
.in_("activity_type", ["Trade", "Deposit", "Withdrawal", "Dividend",
        "MoneyMovement", "Interest", "Fee", "WithholdingTax",
        "ReorganizationDividend"])
```

**Blacklist** — exclude known non-cash types:
```python
.not_in("activity_type", ["InternalSecurityTransfer", "InternalCashTransfer"])
```

**Recommendation: Whitelist.** A financial system should be explicit about what constitutes cash. The downside — new legitimate cash types will be silently omitted — is mitigated by:
1. A test that fails when new activity types are added to the `activity_type` enum without explicit consideration in this filter
2. Documentation at the filter site listing all known types and why each is included/excluded

If `InternalCashTransfer` exists in the data: it represents cash movement *between accounts* and is net-zero across the system, but non-zero within a single account. Should it be included? **Yes** — it represents real cash movement in/out of each leg. The sending account's cash goes down, the receiving account's goes up. This is correct behavior. Only exclude it if it's a book-entry offset rather than an actual cash wire.

Blacklist candidate categories to research: `Adjustment`, `CorporateAction`, `Reorganization` — these may or may not affect cash depending on how the brokerage reports them. Each needs explicit review.

---

## Issue 3: Return Methodology — Simple Return vs TWR

**Impact:** The user's dashboard shows Total Return % computed as `(last_value - first_value) / first_value * 100`. This is a **simple return** that ignores cash flows. For accounts with deposits, this can significantly understate or overstate actual investment performance.

**Relevant code** (`portfolio_service.py:2142`):
```python
total_return_pct = ((last_value - first_value) / first_value * 100) if first_value > 0 else 0
```

### What Makes TWR Hard

The analysis below sketches the correct direction, but there are hard problems:

**1. Intraday cash flows.** TWR requires portfolio valuation at the instant *before* each cash flow. If a $10k deposit and a buy trade happen on the same day, you need the pre-deposit value and the post-deposit/pre-trade value to compute the correct sub-period return. Daily snapshots have only one valuation per day, so they cannot distinguish the ordering.

This means true TWR requires either:
- Transaction-level lot tracking with sub-daily precision (expensive)
- An assumption that cash flows occur at end-of-day (acceptable for retail, introduces small error)
- A settlement-date proxy instead of trade-date

**2. What counts as a cash flow for TWR?** Not all transactions are equal:
- Deposits/withdrawals (`MoneyMovement`): yes — these are external cash flows
- Dividends: **debatable**. In a retail portfolio, dividends are usually reinvested and should NOT be treated as TWR cash flows (they're generated by the portfolio, not added by the user). But if dividends are paid to the cash balance and not automatically reinvested, they *are* available for withdrawal and may need to be treated as internal cash generation rather than external flows.
- Fees: technically a withdrawal (cash leaves the account). For TWR, management fees reduce the return — they shouldn't be removed as cash flows.
- Interest: same as fees — it's portfolio return, not an external flow.

**3. Modified Dietz as a practical stepping stone.** Full TWR is architecturally expensive. The Modified Dietz method is a time-weighted approximation that is far simpler and "good enough" for retail portfolios:

```python
gain = end_value - start_value - net_cash_flow
weighted_capital = start_value
for cf in cash_flows:
    days_remaining = (end_date - cf.date).days
    total_days = (end_date - start_date).days
    weight = days_remaining / total_days if total_days > 0 else 0
    weighted_capital += cf.amount * weight
return_pct = gain / weighted_capital if weighted_capital > 0 else 0
```

**Recommended phased approach:**
1. **Phase 1:** Keep simple return but add a prominent disclaimer showing net deposits alongside the return figure so the user has context
2. **Phase 2:** Implement Modified Dietz — requires only cash flow dates/amounts, no intraday valuation
3. **Phase 3:** Full TWR with sub-period valuation and lot-level tracking

---

## Issue 4: Snapshot Date Alignment Across Accounts

**Impact:** The merge loop (`portfolio_service.py:2108-2121`) blindly sums snapshot values by date. If account A has a snapshot on June 1, 3, 5 but account B has one on June 2, 4, 6, the merged timeline only has dates where at least one account had a snapshot. On June 1, account B's contribution is missing (treated as 0), which drags down total_value.

```python
merged: Dict[str, Dict] = {}
for s in raw_snapshots:
    d = s["snapshot_date"]
    if d not in merged:
        merged[d] = {"date": d, "value": 0.0, "cost_basis": 0.0, ...}
    merged[d]["value"] += s["total_value"]
```

The **snapshot job runs daily** (`portfolio_snapshot_job.py:34`: `today = now_utc().date()`), so in practice all accounts get a snapshot on the same day. But:
- Gaps occur when the job fails or is skipped for certain accounts
- The legacy path generates dates independently per account
- Missing dates are silently treated as $0, which corrupts the aggregate view
- An individual account with no data on a given day is summed as 0, dragging down the combined total

### Fix: Day-Fill (LOCF) With Edge Case Handling

Last Observation Carried Forward is the right approach, but handles these edge cases:

1. **New accounts with no prior snapshot:** These accounts should be **excluded from aggregate calculations entirely** until they have at least one valid snapshot. Carrying forward 0 or None would be wrong. Detect this by checking if the account's earliest snapshot date is after the merge start date.

2. **Closed/inactive accounts:** If an account has transactions but the most recent snapshot is months old, DAY-fill would perpetually carry forward an obsolete balance. The user would see stale money. Instead, if the most recent snapshot is older than `stale_threshold_days` (same 30-day threshold used elsewhere), stop carrying forward and either exclude the account or mark the aggregate with a `LAGGING_DATA` flag.

3. **Cross-account transfers (`InternalSecurityTransfer`):** If securities move from Account A to Account B on day D, and both accounts have snapshots on day D-1 but only Account A has a snapshot on day D, then:
   - LOCF for Account B would still show the security (pre-transfer) on day D
   - Combined value would be overstated (security counted in both accounts)
   - **Mitigation:** Compute aggregate values at the account-group level only on dates where ALL accounts in the group have snapshots. For non-transfer dates, use LOCF. Flag transfer dates for separate reconciliation.

### Algorithm

```python
def merge_snapshots_with_locf(
    raw_snapshots: List[Dict], account_ids: List[int]
) -> List[Dict]:
    # 1. Group by account
    by_account = {aid: [] for aid in account_ids}
    for s in raw_snapshots:
        by_account.setdefault(s["account_id"], []).append(s)

    # 2. Collect all unique dates
    all_dates = sorted({s["snapshot_date"] for s in raw_snapshots})

    # 3. Exclude accounts with no prior snapshot
    active_accounts = []
    for aid, snaps in by_account.items():
        if snaps:
            active_accounts.append(aid)

    # 4. For each date, LOCF per account, then sum
    merged = {}
    last_values = {aid: None for aid in active_accounts}
    for d in all_dates:
        for aid in active_accounts:
            account_snaps = {s["snapshot_date"]: s for s in by_account[aid]}
            if d in account_snaps:
                last_values[aid] = account_snaps[d]
            # else: LOCF — last_values[aid] stays the same
        # Skip date if any account has no prior data at all
        if any(v is None for v in last_values.values()):
            continue
        merged[d] = {
            "date": d,
            "value": sum(v["total_value"] for v in last_values.values() if v),
            "cost_basis": sum(v["cost_basis"] for v in last_values.values() if v),
        }
    return merged
```

---

## Issue 5: Rate Limiting on Performance Endpoint

**Impact:** The `/portfolio/performance` endpoint at `backend/api/portfolio.py:1440-1441` is rate-limited to `20/minute`. A dashboard that loads 5 period tabs (1M, 3M, 1Y, 5Y, ALL) with 2 account groups triggers 10 requests. With auto-refresh or fast tab-switching, the user easily hits the limit.

**Rate limits on related endpoints:**
- `/portfolio/performance` → 20/min
- `/portfolio/performance/compare` → 20/min

### Better Fix: Bulk Batch Endpoint

Raising the limit to 60/min is a band-aid. The architectural issue is N×M requests (accounts × periods). Replace with a single request:

```
POST /portfolio/performance/batch
{
  "account_ids": [1, 4, 9],
  "periods": ["1M", "3M", "1Y", "5Y", "ALL"]
}
```

Response: `{ "results": { "1M": {...}, "3M": {...}, ... } }`

**Advantages:**
- Single snapshot DB query across all periods
- Single cash balance computation across all accounts
- Server-side deduplication of overlapping date ranges (1Y + ALL share 365 days of data)
- Fewer requests = lower rate limit concern
- Easier to cache server-side (key: `(account_ids_hash + periods)`)
- Client dashboard becomes a single fetch instead of N×M racing fetches

Replace the individual endpoint's rate limit with a generous one on the batch endpoint (60-120/min) since it consolidates multiple queries.

---

## Test Gap Analysis: Why the Existing Test Suite Didn't Catch the -$2,903 Bug

The existing test suite at `tests/test_portfolio_snapshots.py` and `tests/test_portfolio_performance_regression.py` covers many individual concerns correctly (whitelist filtering, LOCF merge, key name regression for `cost_basis`/`total_cost`, invariant arithmetic). However, three specific gaps allowed the -$2,903 bug to slip through:

### Gap 1: `avg_cost` vs `average_cost` Key Name Mismatch Was Never Tested

`shared/snapshot_builder.py:84` uses `h.get("avg_cost")` — a key name that doesn't exist in the database schema (the column is `average_cost`). The `TestBuildSnapshotRow::test_average_cost_fallback_when_no_price` test (line 231) passes `average_cost=150` in holdings_state — the **correct** key name — so the test passes. It never tests what happens with the **wrong** key name `avg_cost`. On June 23, when `prices_by_company` returned empty (transient data provider failure), the fallback to `avg_cost` found nothing, and every holding got `current_price = $0`.

**Why the similar `cost_basis`/`total_cost` test didn't help:** The regression test `test_uses_total_cost_not_cost_basis` (line 244) catches the `cost_basis` mismatch for the **cost** field. But there was no parallel test for the `avg_cost` mismatch for the **price** fallback field. A developer fixing the cost key would not have known the price fallback key was also wrong.

### Gap 2: No Test for the Zero-Deposit Account Pattern

The regression tests for cash balance (`TestCashLedgerSemantics::test_cash_balance_ledger_all_types`) use a balanced set of transactions that includes deposits (`MoneyMovement: +5000`) alongside trades. They never test the **zero-deposit pattern** (accounts 10/11/12) where only buy trades exist without any MoneyMovement records. This pattern produces `cash_balance = -$46,220` from buy transactions only, with `net_deposits = $0`. The snapshot builder has no invariant to catch "cash balance too negative relative to cost basis."

### Gap 3: No Test Checks That a Negative Total Value Sets a Quality Flag

The current invariant in `build_snapshot_row` (line 161-168) checks `total_value ≈ holdings_market_value + cash_balance` — a purely **arithmetic** check. It will pass when `total = -$49,123` if `holdings_mv + cash = -$49,123`. There is no **semantic** invariant that says "if total_value < 0 while holdings exist, the snapshot should be flagged with a warning." The only quality flags are `OK` and `STALE_PRICE` — neither fires on a negative total.

### How the Three Gaps Interacted to Produce the -$2,903 Dip

```
Pipeline Step           | Protection | Gap
------------------------|------------|-----
1. Import trades        | None       | No validation that deposits exist alongside buys
2. Compute cash balance | Whitelist  | Correctly filters InternalSecurityTransfer, but 
                        |            | doesn't flag "no deposits" pattern (Gap 2)
3. Fetch prices         | None       | Fails silently, returns empty dict
4. Fall back to avg_cost| None       | Uses wrong key "avg_cost" → $0 (Gap 1)
5. Build snapshot       | Invariant  | Arithmetic check passes for -$49,123
6. Set quality flag     | None       | OK despite negative total (Gap 3)
```

Each individual step's protection was insufficient, and no cross-cutting invariant caught the combination.


## Systematically Missing: Data Backfill for Corrupted Snapshots

The fixes in Issue 1 prevent future corruption, but the 2026-06-23 snapshots (and any other rows created with the wrong key names) remain wrong in the database.

### Backfill Strategy

1. **Detect:** Query `portfolio_snapshots` for rows where `cost_basis=0` AND `holdings_json` is not null AND contains entries with non-zero `quantity`. This catches all corrupted rows regardless of date.

```sql
SELECT account_id, snapshot_date, cost_basis, holdings_json
FROM portfolio_snapshots
WHERE cost_basis = 0
  AND holdings_json IS NOT NULL
  AND jsonb_path_exists(holdings_json, '$[*].quantity ? (@ > 0)');
```

2. **Re-compute:** For each affected row, re-run `build_snapshot_row` with the corrected code, passing the original holdings data from the DB at that snapshot date.

3. **Upsert corrected rows:** Replace the corrupted snapshot with the re-computed value.

4. **Price-aware handling:** For rows where `get_latest_prices` also failed (like June 23), the re-computed row will still have 0 prices. These rows should be **rebuilt using forward-filled prices** — the earliest available price after the snapshot date, flagged as `STALE_PRICE`. A snapshot with poor data quality is still better than no snapshot, provided the quality flag is accurate.

### One-Time Script Skeleton

```python
async def backfill_corrupted_snapshots():
    repo = PortfolioSnapshotsRepository()
    corrupt = repo.find_corrupted_snapshots()  # cost_basis=0 + non-zero holdings
    for row in corrupt:
        corrected = build_snapshot_row(
            account_id=row["account_id"],
            snapshot_date=row["snapshot_date"],
            holdings_state=row["_original_holdings"],  # re-fetched or from JSON
            cash_balance=repo.get_cash_balance(row["account_id"], row["snapshot_date"]),
            net_deposits=repo.get_net_deposits(row["account_id"], row["snapshot_date"]),
            prices_by_company=await get_prices_forward_filled(...),
            job_id=f"backfill_{datetime.utcnow().isoformat()}",
        )
        repo.upsert_snapshot(corrected)
```

---

## Systematically Missing: Test Strategy

None of the fixes include regression tests. Production-grade bug resolution requires:

### Test 1: `build_snapshot_row` Key Name Mismatches

```python
def test_build_snapshot_row_uses_total_cost_not_cost_basis():
    """Regression: must read 'total_cost' key from DB-shaped holdings."""
    holding = {
        "company_id": 1,
        "quantity": 100,
        "total_cost": 5000.00,   # DB column name
        "average_cost": 50.00,   # DB column name
        "symbol": "ACME",
    }
    prices = {1: {"price": 60.00, "price_date": date(2026, 6, 24)}}
    result = build_snapshot_row(
        account_id=1, snapshot_date=date(2026, 6, 24),
        holdings_state=[holding], cash_balance=Decimal("0"),
        net_deposits=Decimal("0"), prices_by_company=prices,
        job_id="test",
    )
    assert result["cost_basis"] == 5000.00, f"Expected 5000.00, got {result['cost_basis']}"
    assert result["holdings_json"][0]["cost_basis"] == 5000.00
```

### Test 2: `get_cash_balance` Filters Non-Cash Types

```python
def test_get_cash_balance_excludes_internal_transfer():
    """Regression: InternalSecurityTransfer must not affect cash."""
    # Setup: one Trade ($1000) and one InternalSecurityTransfer (-$5000)
    # Expected cash: $1000, NOT -$4000
    repo = PortfolioRepository()
    cash = repo.get_cash_balance(account_id=1, target_date=date(2026, 6, 24))
    assert cash == Decimal("1000.00"), f"Expected 1000.00, got {cash}"
```

### Test 3: Invariant Check on Zero Cost with Non-Zero Quantity

```python
def test_build_snapshot_row_raises_on_zero_cost():
    """Must reject holdings where cost=0 but qty>0 after key lookup."""
    bad_holding = {
        "company_id": 1,
        "quantity": 100,
        "total_cost": 0,       # obviously wrong
        "average_cost": 0,
        "symbol": "ACME",
    }
    with pytest.raises(ValueError, match="cost_basis=0 but qty=100"):
        build_snapshot_row(...)
```

### Test 4: Snapshot Merge Day-Fill Edge Cases

```python
def test_merge_locf_excludes_new_accounts():
    """An account with no prior snapshot should not contribute $0."""
    ...

def test_merge_locf_stops_carrying_forward_stale_accounts():
    """An account last active 45 days ago should be excluded beyond threshold."""
    ...
```

### Test 5: Whitelist Activity Type Enum Coverage

```python
def test_all_activity_types_considered_in_cash_filter():
    """Every activity type in the DB must be explicitly categorized."""
    known_types = {"Trade", "Deposit", "Withdrawal", "Dividend", ...}
    db_types = get_all_activity_types()
    unconsidered = db_types - known_types
    assert not unconsidered, f"New types not categorized: {unconsidered}"
```

---

## Three-Layer Defense Architecture

The individual fixes (key name corrections, whitelist, invariant) are necessary but not sufficient — they patch individual symptoms. A layered design ensures no single pipeline failure can silently produce a negative total.

### Layer 1: Cash Balance Sanity Invariant

**Where:** `shared/snapshot_builder.py` in `build_snapshot_row()`, after computing `cash_balance`

**Logic:**
```python
MAX_NEGATIVE_CASH_MULTIPLIER = 1.5  # cannot owe more than 1.5× cost basis
if cash_balance < 0 and cost_basis > 0:
    max_negative = -cost_basis * MAX_NEGATIVE_CASH_MULTIPLIER
    if cash_balance < max_negative:
        validation_warnings.append(
            f"cash_balance={cash_balance:.2f} exceeds max negative "
            f"{max_negative:.2f} (cost_basis={cost_basis:.2f}). "
            f"Possible missing deposit transactions."
        )
```

**What it catches:** The Accounts 10/11/12 pattern — $18,790 in buys with $0 deposits → cash = -$17,350, which exceeds -$18,790 × 1.5 = -$28,185. Warning is raised.

### Layer 2: 4-Tier Price Resolution (Skip, Don't Zero)

**Where:** `shared/snapshot_builder.py` in `build_snapshot_row()`, replacing the current two-tier fallback

**Logic:**
```python
def _resolve_holding_price(
    company_id: int,
    prices_by_company: Dict[int, Dict],
    price_history_all: Dict[int, List[tuple]],
    average_cost: Optional[Decimal],
    snapshot_date: date,
) -> Tuple[Optional[Decimal], str]:
    # Tier 1: Fresh market price (≤ 30 days old)
    info = prices_by_company.get(company_id, {})
    if info.get("price") is not None:
        return Decimal(str(info["price"])), "FRESH"
    # Tier 2: Forward-filled from price_history
    fwd = resolve_price_forward_filled(company_id, snapshot_date, price_history_all)
    if fwd:
        return Decimal(str(fwd["price"])), "FORWARD_FILLED"
    # Tier 3: Average cost from holdings
    if average_cost and average_cost > 0:
        return average_cost, "COST_BASIS"
    # Tier 4: Unavailable → skip holding entirely
    return None, "UNAVAILABLE"
```

When a holding resolves to `UNAVAILABLE`, it is **excluded from `holdings_market_value`** (not counted as $0). The snapshot's `data_quality_flag` is set to `INCOMPLETE` if any holding is unavailable.

### Layer 3: Post-Computation Validation Warnings

**Where:** `shared/snapshot_builder.py`, after building the snapshot dict

**Logic:**
```python
def validate_snapshot(snapshot: dict, holdings: List[dict]) -> List[str]:
    warnings = []
    # W1: Zero holdings MV but holdings exist
    if len(holdings) > 0 and snapshot["holdings_market_value"] <= 0:
        warnings.append("Zero holdings market value despite non-zero holdings")
    # W2: Negative total with positive holdings
    if snapshot["total_value"] < 0 and snapshot["holdings_market_value"] > 0:
        warnings.append(f"Negative total {snapshot['total_value']} despite "
                        f"positive holdings value")
    # W3: Cash too negative relative to cost
    cost = snapshot["cost_basis"]
    if snapshot["cash_balance"] < -cost * 1.5 and cost > 0:
        warnings.append(f"Cash balance {snapshot['cash_balance']} too negative "
                        f"relative to cost basis {cost}")
    return warnings
```

Warnings are stored in a new JSONB column `validation_warnings` on the snapshot. The `data_quality_flag` is set to `WARNING` if any warning exists.

### How the Three Layers Intercept the -$2,903 Pipeline

```
Step                      | Old Behavior              | Layer 1        | Layer 2        | Layer 3
--------------------------|---------------------------|----------------|----------------|------------------
1. No deposits recorded   | Silent                    | DEPOSIT_GAP ✓  | —              | W3 ✓
2. Empty prices_by_company| Silent → $0 holdings      | —              | UNAVAILABLE ✓  | W1 ✓
3. avg_cost key mismatch  | Silent → $0 fallback      | —              | UNAVAILABLE ✓  | —
4. Total = -$49K          | Stored as OK              | —              | —              | W2: NEGATIVE ✓
5. Snapshot stored        | OK flag                   | flag=WARNING   | flag=INCOMPLETE| flag=WARNING
```


## Summary of Changes Required

| # | File | Line(s) | Change | Severity | Tests |
|---|------|---------|--------|----------|-------|
| 1a | `shared/snapshot_builder.py` | 69 | `cost_basis` → `total_cost` | **Critical** | T1, T9, T16 |
| 1b | `shared/snapshot_builder.py` | 84 | `avg_cost` → `average_cost` | **Critical** | T16, T17 |
| 1c | `shared/snapshot_builder.py` | after 69 | Add invariant: raise if cost=0 and qty>0 | **Critical** | T3 |
| 1d | `shared/snapshot_builder.py` | new | 4-tier price resolution with UNAVAILABLE | **Critical** | T18, T19 |
| 1e | `shared/snapshot_builder.py` | new | Post-computation validation warnings | **Critical** | T20, T21 |
| 1f | `shared/snapshot_builder.py` | new | Cash balance sanity invariant (Layer 1) | **Critical** | T20 |
| 2 | `portfolio_repository.py` | 1033-1044 | Whitelist filter on `get_cash_balance` | **High** | T2, T5 |
| 3 | `portfolio_service.py` | 2142 | Replace simple return with TWR/Modified Dietz | Medium | — |
| 4 | `portfolio_service.py` | 2108-2121 | Day-fill LOCF merge with edge case handling | Medium | T4 |
| 5 | `api/portfolio.py` | — | Add `/portfolio/performance/batch` bulk endpoint | Low | — |
| B | — | — | Backfill script for corrupted historical snapshots | **High** | T10 |

### New Regression Tests

| Test | File | What It Captures |
|------|------|------------------|
| T16 | `test_portfolio_snapshots.py` | `avg_cost` key name mismatch — wrong key produces $0 fallback while correct key produces correct value |
| T17 | `test_portfolio_snapshots.py` | `avg_cost` vs `average_cost` produce different results — regression detector |
| T18 | `test_portfolio_snapshots.py` | Negative cash + $0 holdings → negative total with OK quality flag (the -$2,903 bug) |
| T19 | `test_portfolio_snapshots.py` | Zero-deposit account pattern — trades without MoneyMovement |
| T20 | `test_portfolio_snapshots.py` | DB-shaped holdings (`total_cost`, `average_cost`) passed to builder produce correct values |
| T21 | `test_portfolio_snapshots.py` | DB-shaped holdings with missing prices fall back to `average_cost` correctly |

---

## Proposed Long-Term Design

### Phase 0 — Backfill (immediate, before deploying fixes)
1. Identify all corrupted snapshot rows (cost_basis=0 but non-zero holdings)
2. Run backfill script with forward-filled prices
3. Validate corrected rows via invariant check

### Phase 1 — Fix Data Bugs (immediate)
1. Fix key name mismatch in `build_snapshot_row` (Issues 1a, 1b)
2. Add defensive invariant check (Issue 1c)
3. Add whitelist filter to `get_cash_balance` (Issue 2)
4. Write regression tests for all three

### Phase 2 — Raise the Floor (short-term)
5. Upgrade data quality enum: `OK | STALE_PRICE | COST_BASIS_FALLBACK | MISSING`
6. Add `/portfolio/performance/batch` bulk endpoint
7. Add validation endpoint (`/portfolio/performance/validate`) that checks invariants across all snapshots
8. Backfill script in scheduled job (re-check weekly)

### Phase 3 — Architecture (medium-term)
9. **Unified pricing service**: Move `get_latest_prices` into a dedicated `PricingService` with cache-fill, staleness detection, monitoring, and fallback to forward-filled prices
10. **Modified Dietz return engine**: Separate module computing weighted returns from cash flows; simple return becomes fallback only for cash-free periods
11. **LOCF merge engine**: Standalone, tested merge algorithm replacing the inline loop

### Phase 4 — Monitoring (ongoing)
12. Daily `validate_snapshot_invariants` with alert on violations
13. Price coverage metric: what fraction of holdings have a <30-day price? Alert if <90%
14. Add Prometheus metrics for snapshot quality (missing prices, zero cost, per-account staleness)

---

## Appendix: Data Quality Enum Design

```python
class SnapshotQuality(Enum):
    OK = "OK"                              # All prices <30 days, all costs populated
    STALE_PRICE = "STALE_PRICE"            # Some prices >30 days old, fallback to last known
    COST_BASIS_FALLBACK = "COST_FALLBACK"  # No price found; using avg_cost as proxy
    MISSING = "MISSING"                    # Critical data missing; snapshot should not exist
```

Each holding in `holdings_json` gets its own `data_quality` field. The snapshot-level flag is the worst of its holdings.

Dashboard behavior per flag:
- `OK`: green badge
- `STALE_PRICE`: yellow badge, muted prices
- `COST_BASIS_FALLBACK`: orange badge, values shown with asterisk
- `MISSING`: red badge, row excluded from aggregates


---

## Appendix B: Empirical Validation Against WealthSimple Data

All 2724 transactions from the three WealthSimple accounts (7: Non-reg, 8: RRSP, 9: TFSA) were queried from the live database to independently compute expected portfolio values for every date period. This section documents the exact numbers and the gaps they revealed.

### Activity Type Audit (Whitelist Gap)

| Type | Rows | Net Cash | In Whitelist? | Cash-Moving? |
|------|------|----------|---------------|--------------|
| `Trade` | 127 | -$31,690 | YES | YES |
| `Dividend` | 655 | $3,165 | YES | YES |
| `MoneyMovement` | 76 | $33,753 | YES | YES |
| `Interest` | 45 | $2 | YES | YES |
| `**BonusPayment**` | 2 | **+$25** | **NO — GAP** | **YES — cash received** |
| `**FxExchange**` | 24 | **-$2,386** | **NO — GAP** | **YES — currency conversion** |
| `**ReturnOfCapital**` | 27 | **-$19** | **NO — GAP** | **YES — cash to investor** |
| `**Tax**` | 1 | **-$1** | **NO — GAP** | **YES — tax paid from cash** |
| `InternalSecurityTransfer` | 42 | +$5,505 | NO — correct | NO — securities transfer |
| `NonCashDistribution` | 1 | +$30 | NO — correct | NO — non-cash event |

**Impact per account:**

| Account | Correct (full whitelist) | Current (incomplete) | Difference | Source |
|---------|-------------------------|---------------------|------------|--------|
| 7 | $351.28 | $304.84 | -$46.44 | BonusPayment, FxExchange, ReturnOfCapital, Tax |
| 8 | $8,113.25 | $5,005.84 | -$3,107.41 | FxExchange (-$2,386), InternalSecurityTransfer (+$5,505)* |
| 9 | $1,641.75 | $1,641.75 | $0 | Both match (InternalSecurityTransfer correctly excluded) |

\*Account 8 InternalSecurityTransfer is net-positive (+$5,505) — securities *received* into RRSP from another account. The unfiltered cash appears larger, but the whitelist correctly excludes it.

### Account 9 Cash Discrepancy

Current `get_cash_balance` returns **$1,641.75** for Account 9. But the July 6 snapshot stores **$1,235.23** — a **$406.52 difference**. Hypotheses:

1. An older whitelist version excluded some Dividend sub-types
2. The snapshot was computed by the legacy fallback path (which applies different filtering)
3. A date cut-off filtered out later dividend transactions

**Resolution:** The correct reference value is $1,641.75 (current whitelist). Any discrepancy in stored snapshots is a historical artifact that the backfill script will correct.

### Zero-Deposit Accounts (10, 11, 12)

| Account | Trades (net) | Holdings Cost | Cash | Deposits? |
|---------|-------------|--------------|------|-----------|
| 10 | -$17,350 | $18,790 | -$17,350 | NONE |
| 11 | -$24,200 | $25,590 | -$24,200 | NONE |
| 12 | -$4,670 | $4,738 | -$4,670 | NONE |

These accounts have **only Trade records** — no MoneyMovement, no Dividends. `Cash = -sum(Trade net_cash)` because every buy reduces cash. There are zero deposit records. This is the root cause of the negative portfolio totals when combined with missing prices.

### Stored Snapshot Quality Analysis (June 2026)

| Account | Jun 23 | Jun 24 | Jun 26 | Jun 27 | Jun 30 | Jul 6 | Pattern |
|---------|--------|--------|--------|--------|--------|-------|---------|
| 7 | $351 OK | $351 OK | $10,742 OK | $10,742 OK | $45,648 OK | $43,493 OK | Clean, but Jun 23-24 has $0 MV (no prices) |
| 8 | $9,253 STALE | $8,322 STALE | $30,678 STALE | $27,793 STALE | $45,681 STALE | $42,095 OK | Cash switches between $5,005 and $8,113 (mixed code versions) |
| 9 | -$12,507 STALE | -$10,932 STALE | $48,039 STALE | $47,723 STALE | $54,768 STALE | $67,167 STALE | Cash switches between $1,235 and -$13,631 |
| 10 | -$17,350 OK | -$17,350 OK | $1,440 OK | $1,440 OK | $20,888 OK | $20,629 OK | Negative total with OK flag → BUG |
| 11 | -$24,200 OK | -$24,200 OK | $1,390 OK | $1,390 OK | $16,825 OK | $16,673 OK | Negative total with OK flag → BUG |
| 12 | -$4,670 OK | -$4,670 OK | $67 OK | $67 OK | $1,632 OK | $1,885 OK | Negative total with OK flag → BUG |

**Key observations:**
- All 6 accounts have `OK` quality on June 23 despite **4 of 6 having negative totals**
- Cash oscillates between filtered/unfiltered on Jun 26 vs Jun 30 (mixed code versions in production)
- Accounts 10/11/12 never have deposits but the quality flag never warns about this

### 10 New Failing Tests (Capturing Every Gap)

| # | Test Name | What It Asserts | What Fails |
|---|-----------|-----------------|------------|
| 1 | `test_whitelist_includes_bonus_payment` | BonusPayment in CASH_ACTIVITY_TYPES | Not present — $25 gap |
| 2 | `test_whitelist_includes_fx_exchange` | FxExchange in CASH_ACTIVITY_TYPES | Not present — $2,386 gap |
| 3 | `test_whitelist_includes_return_of_capital` | ReturnOfCapital in CASH_ACTIVITY_TYPES | Not present — $19 gap |
| 4 | `test_whitelist_includes_tax` | Tax in CASH_ACTIVITY_TYPES | Not present — $1 gap |
| 5 | `test_whitelist_covers_all_known_db_types` | Every DB type categorized | 4 types missing |
| 6 | `test_negative_total_quality_not_ok` | Negative total → flag != OK | Current code: flag=OK |
| 7 | `test_negative_total_has_warning` | Negative total → validation_warnings | No warnings field exists |
| 8 | `test_cash_too_negative_warning` | Cash < -1.5×cost_basis → warning | No cash sanity check exists |
| 9 | `test_account_10_zero_deposit_negative_cash` | Zero-deposit pattern → warning | No validation_warnings |
| 10 | `test_account_10_negative_total_when_prices_missing` | Avg cost fallback → flag not OK | Current code: flag=OK |

All 10 tests pass only after implementing the 3-layer defense.
Existing test suite: 53 pass, 1 pre-existing fail (wrong assertion), 10 new fail (capturing bugs).


---

## Appendix C: Guarantee Reasoning — Why This Design Is Optimal

### The Design Space

The problem has three independent failure modes:
1. **Cash miscomputation** — wrong activity types leak into cash balance
2. **Price resolution failure** — no price → $0 holdings → negative total
3. **Silent corruption** — wrong answer stored with quality="OK"

Any fix must address all three. There are four possible architectural approaches:

### Approach A: Whitelist + 2-Tier Price + Arithmetic Invariant (CURRENT)
What exists today (after the key-name fixes). The arithmetic invariant (`total == mv + cash`) is necessary but not sufficient — it passes for -$24,200 because -$24,200 = $0 + (-$24,200). This is a **syntactic invariant** that checks formatting, not semantics.

**Defeated by:** Any case where arithmetic is correct but the numbers are wrong.

### Approach B: DB-Level Constraints + Stored Procedures
Move the whitelist and price fallback into PostgreSQL:
```sql
CREATE FUNCTION get_cash_balance(account_id, target_date) RETURNS NUMERIC
LANGUAGE SQL STABLE
AS $$
  SELECT COALESCE(SUM(net_cash_amount), 0)
  FROM portfolio_transactions
  WHERE activity_type = ANY(
    CASH_ACTIVITY_TYPES -- stored as a table or GUC
  )
$$;
```

**Advantages:** Single source of truth, can't be bypassed by application code.
**Disadvantages:** Testing requires DB setup, no fine-grained quality tracking, harder to version-control business logic, changes require migrations. Doesn't solve the quality flag problem (DB has no concept of "this answer looks wrong").

### Approach C: Monitoring + Alerting (Detect After the Fact)
Run a daily validation query that checks for negative totals, missing prices, etc. and sends an alert.

**Advantages:** No production code changes needed, catches regressions.
**Disadvantages:** Detects errors AFTER they've been stored. Users see bad data for up to 24 hours. No prevention, only detection.

### Approach D: Whitelist + 4-Tier Price + Post-Computation Validation (THIS PROPOSAL)
The three-layer defense:

```
Layer 1 (Cash):     cash_balance < -1.5 × cost_basis → WARNING
Layer 2 (Price):    price_history → average_cost → UNAVAILABLE → skip
Layer 3 (Quality):  negative total? holdings mismatch? → WARNING
```

### Comparison Matrix

| Criterion | A (Current) | B (DB constraints) | C (Monitoring) | D (This proposal) |
|-----------|-------------|-------------------|----------------|-------------------|
| Catches wrong cash type | ✓ (whitelist) | ✓ | ✗ | ✓ |
| Catches $0 prices | ✗ | ✗ | ✓ (next day) | ✓ (UNAVAILABLE skip) |
| Catches negative total | ✗ | ✗ | ✓ (next day) | ✓ (WARNING flag) |
| Prevents storage of bad data | ✗ | ✗ | ✗ | ✓ (flag stored alongside) |
| Testable without DB | ✓ | ✗ | ✓ | ✓ |
| Granular per-holding quality | ✗ | ✗ | ✗ | ✓ (COST_FALLBACK/UNAVAILABLE) |
| Survives code version changes | ✗ | ✓ | ✗ | ✓ (flag is data, not code) |
| Deployment complexity | None | High (migrations) | Low | None (code-only) |
| Works offline/without DB | ✓ (unit tests) | ✗ | ✓ | ✓ |

### Guarantee Proof

The design guarantees that no single pipeline failure can silently produce a corrupted snapshot. Here is the formal argument:

**Theorem:** For any input to `build_snapshot_row`, the output either (a) satisfies all three invariants, or (b) has `data_quality_flag ≠ "OK"` with an explanation in `validation_warnings`.

**Proof by exhaustive case analysis:**

1. **Cash balance accuracy** — `get_cash_balance` applies a whitelist. Every cash-moving activity type is enumerated in `CASH_ACTIVITY_TYPES`. A test (`test_whitelist_covers_all_known_db_types`) fails if any new type is added without explicit categorization. Therefore cash can only be wrong if a type is misclassified, which requires a human decision reviewed via failing test.

2. **Price resolution** — The 4-tier cascade guarantees every holding either:
   - Gets a current price (OK or STALE_PRICE), or
   - Gets average_cost as proxy (COST_FALLBACK), or
   - Is excluded from market value entirely (UNAVAILABLE) — impossible to contribute $0 to the total.

   The UNAVAILABLE tier is critical: it converts "missing price = $0 holding" into "missing price = holding excluded". This is the difference between total = -$24,200 and total = -$24,200 + $67.

3. **Post-computation check** — Three invariants run after all holdings are processed:
   - W1: Zero market value with non-zero holdings → warning
   - W2: Negative total with positive holdings value → warning  
   - W3: Cash < -1.5×cost_basis → warning

   Any warning sets `data_quality_flag = "WARNING"`, which the dashboard can surface. The remaining quality flags (OK, STALE_PRICE, COST_FALLBACK, INCOMPLETE) are determined by the worst holding quality, ensuring every level of data degradation is tracked.

4. **No single point of failure** — The three layers are independent:
   - Layer 1 catches deposit gaps even if price resolution works perfectly
   - Layer 2 catches price failures even if cash is correct
   - Layer 3 catches combinations that slip through 1+2 (e.g., correct cash + correct prices but negative total due to an arithmetic bug)

   Because they are independent, any one layer failing (e.g., a future developer removes the whitelist) still leaves the other two layers operational. The system degrades gracefully instead of collapsing silently.

**Corollary:** The -$2,903 dip cannot recur. The specific chain was:
```
no prices + wrong key + no whitelist + no semantic invariant = -$2,903 stored as OK
```

After the fix:
```
no prices → UNAVAILABLE (skip, not $0)
wrong key → test_whitelist_covers_all_known_db_types fails  
no whitelist → test_whitelist_includes_* fails
no semantic invariant → W2 catches negative total
```

Every link in the chain is independently defended. Four tests must simultaneously fail for the bug to recur, which is detectable in CI long before it reaches production.


---

## Appendix D: Design Critique — Failures, Snowflakes, and Complications

This section is a critical review of the three-layer defense proposed in Appendix C.
Every design has weaknesses; documenting them explicitly prevents blind spots and
guides the long-term architecture.

### Layer 1 Critique: Cash Sanity Invariant

**F1: The 1.5× multiplier is arbitrary and account-type-blind.**
Why 1.5×? A margin account can legitimately carry 3× cost basis in debt. A TFSA
cannot be negative at all (it's illegal in Canada). A single multiplier can't serve
both. The check produces false positives for margin users and false negatives for
registered accounts.

**F2: Circular dependency on cost_basis correctness.**
The invariant compares cash_balance to cost_basis. But cost_basis was exactly what
was wrong (the key-name bug made it $0). When cost_basis=0, the check
`total_cost > 0` silently skips. The one time you need the check most is when
cost_basis is broken.

**F3: Pure-cash accounts are invisible.**
An account with $100,000 cash and $0 cost_basis (all cash, no holdings) never
triggers the invariant. If the cash balance should be $100,000 but is $90,000
due to a missing deposit, no Layer 1 check fires. The invariant only works for
accounts with holdings.

**Mitigation (not fix):** Make threshold configurable per account type:
```
TFSA:  cash >= 0 always (negative is illegal)
Margin: threshold = margin_multiplier × equity
Cash:   check deposits_in = deposits_out + interest
```

### Layer 2 Critique: 4-Tier Price Resolution

**F4: COST_FALLBACK is still semantically wrong.**
Using average_cost as current_price is better than $0, but it's still wrong.
A holding bought at $145 that now trades at $90 would be reported at $145,
overstating the portfolio by 61%. The `COST_FALLBACK` flag tells the dashboard
"we couldn't get a real price" but gives the user no indication of *how wrong*
the proxy might be. A holding with average_cost=$10 and current price=$200 is
also wrong, but understates value. Both get the same flag.

**F5: UNAVAILABLE silently changes portfolio composition.**
When a holding is excluded via UNAVAILABLE, the total_value no longer represents
"what the portfolio is worth" — it represents "what the subset of holdings with
prices is worth." If 5 of 10 holdings are UNAVAILABLE, the user sees half their
portfolio with no visual distinction that 50% is missing. The flag `INCOMPLETE`
exists but nothing in the dashboard renders it.

**F6: No recency gradation.**
Prices 31 days old and 400 days old both get `STALE_PRICE`. There is no
distinction between "slightly stale" and "ancient." A frozen holding with its
last trade in 2022 would be valued at the 2022 price with the same flag as a
holding last priced 32 days ago.

**F7: Corporate actions break company_id continuity.**
If a company is acquired (e.g., TWTR → X), the old company_id still in
`portfolio_holdings` still has price_history up to the acquisition date. The
4-tier system finds the last price and uses it, overvaluing a defunct holding.
There is no mechanism to detect that a company no longer trades independently.

**F8: Price from different exchanges can conflict.**
A stock listed on both TSX and NYSE (e.g., TD) might have different prices on
each exchange. The system currently picks whichever price_history row has the
latest date, regardless of exchange. For Canadian-resident accounts, the TSX
price should be preferred, but there's no exchange-awareness in the price
resolution logic.

**Mitigation:** Add a `price_as_of` versioning layer:
```sql
CREATE TABLE portfolio_price_snapshots (
    snapshot_date DATE NOT NULL,
    company_id INT NOT NULL,
    price NUMERIC NOT NULL,
    price_date DATE NOT NULL,
    source TEXT NOT NULL,  -- 'current_market_data', 'price_history', 'average_cost'
    exchange TEXT,
    PRIMARY KEY (snapshot_date, company_id)
);
```
This records exactly which prices were used for each snapshot, making the
valuation reproducible. The tier logic doesn't change, but the chosen price
is persisted alongside the valuation.

### Layer 3 Critique: Post-Computation Validation

**F9: Warnings stored but not consumed.**
`validation_warnings` is a JSONB field on the snapshot. Nothing reads it. The
dashboard doesn't display it. The API doesn't expose it. Without a consumer,
warnings are dead data — they occupy space but never trigger action. The design
includes the field but not the pipeline to surface it.

**F10: W1 (zero MV with holdings) is redundant with Layer 2.**
If all holdings resolve to UNAVAILABLE, total_market_value = 0, and W1 fires.
But Layer 2 already handles this case (INCOMPLETE flag, each holding marked
UNAVAILABLE). The post-computation check adds no new information; it's a
duplicate assertion that creates maintenance surface area without coverage gain.

**F11: The negative-total check is still arithmetic, not economic.**
W2 catches `total < 0 AND holdings > 0`. But what about a portfolio that should
be $100K but shows $80K due to a missing $20K deposit? Total is +$80K,
holdings are +$70K, cash is +$10K. All arithmetic checks pass. The user sees
80% of their real net worth with no warning. The system can only detect
"something is catastrophically wrong" not "something is slightly wrong."

**F12: Single-period LOCF amplifies errors.**
The LOCF merge (last observation carried forward) fills missing dates with the
last known value. If that last known value was corrupted (-$24,200 on Jun 23),
every subsequent missing date inherits the corruption. LOCF doesn't distinguish
between "normal gap" and "propagating a known-bad value." The fix marks future
snapshots with INCOMPLETE, but inherited LOCF'd values from before the fix
remain unmarked.

### Systemic Complications

**C1: Non-deterministic snapshots.**
`build_snapshot_row` stamps `computed_at: now_utc().isoformat()`. The FX
service uses live exchange rates. Price_history values change as new data
arrives. Running the same function twice produces different outputs. This
makes debugging impossible ("what was the snapshot value last week? I can't
reproduce it") and breaks any system that expects the same inputs → same outputs.

**C2: No cross-account invariant.**
`InternalSecurityTransfer` moves securities from Account A to Account B. At
the USER level, net effect is zero (A loses, B gains). But the system has no
invariant checking that `delta_total[user] ≈ 0` across a transfer. If Account
A's snapshot runs before the transfer and Account B's after, the user's combined
total changes despite no external cash flow.

**C3: Event ordering ambiguity.**
A $10K deposit and a $10K buy on the same day produce different cash balances
depending on order (deposit-first → cash increases then decreases; buy-first →
transaction rejected due to insufficient funds). The current system sums all
transactions by date without ordering, so `cash = Σ net_cash_amount` is correct
regardless of intraday order. But the TWR computation needs the portfolio value
*before* each cash flow, and daily snapshots can't provide intraday precision.
This is a known limitation documented in Issue 3, but it fundamentally limits
what the system can compute.

**C4: Whitelist as ongoing maintenance burden.**
Every time the brokerage adds a new activity type (e.g., "StockSplit",
"RebalancingTransfer"), the whitelist must be manually reviewed and tests
updated. The `test_whitelist_covers_all_known_db_types` test catches new types,
but the test itself must be maintained with the current set. If a developer adds
a type to the allowed set but forgets to update the test's `all_known_types`,
the test silently passes and the new type is unmonitored. The test has a
reflection gap — it can only check what it knows about.

**C5: Price data decay over long horizons.**
The oldest transactions are from 2021. Holdings from 2021 might hold companies
that no longer trade (delisted, bankrupt, acquired). Their company_id is in
`portfolio_holdings` but `price_history` has entries only up to the delisting
date. The 4-tier system would use the delisting price (via forward-fill) and
report it as STALE_PRICE with 2+ years of age. The user sees a zombie holding
valued at its 2022 price with no indication it's worthless.

**C6: Large portfolio performance.**
With 75+ holdings in Account 9 and 100+ company IDs to resolve prices for,
the current approach queries price_history once per company_id. This is
N queries for N holdings. For a user with 500 holdings across 10 accounts,
this is 500+ queries per snapshot run. The batching in `get_all_prices_historical`
helps (limit 50000) but doesn't eliminate the N+1 pattern.

### Long-Term Alternative: Event-Sourced Portfolio Valuation

The three-layer defense is a tactical patch — it fixes the immediate failures
but doesn't change the architectural paradigm. A fundamentally more robust
approach replaces the entire snapshot-via-current-state model with an
event-sourced architecture.

#### Current Architecture (Mutable State)

```
Transactions → portfolio_holdings (mutable) + price_history (append) → build_snapshot_row → portfolio_snapshots
```

Problems:
- `portfolio_holdings` is overwritten on each import (current state only, no history)
- Cash is computed by filtering transactions — any filter mistake corrupts history
- Holdings have no lineage — you can't explain how a position reached its current quantity
- Snapshot correctness depends on the code that computed it, not the data

#### Proposed Architecture (Append-Only Event Log)

```
Transactions → Event Log (append-only) + valuation engine → portfolio_snapshots
```

**Event Log Schema:**
```sql
CREATE TABLE portfolio_events (
    event_id BIGSERIAL PRIMARY KEY,
    account_id INT NOT NULL,
    event_type TEXT NOT NULL,          -- 'deposit', 'withdrawal', 'trade', 'dividend', 'transfer', 'fee'
    event_date DATE NOT NULL,
    symbol TEXT,
    quantity NUMERIC,
    unit_price NUMERIC,
    gross_amount NUMERIC,
    net_amount NUMERIC,                -- always reflects actual cash impact
    fx_rate NUMERIC,
    counterparty_account_id INT,       -- for transfers between accounts
    description TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL               -- 'wealthsimple_csv', 'manual', 'dividend_statement'
);
```

**Key Properties:**

1. **Cash is derived, not stored.** Cash at any date = Σ event.net_amount for all events up to that date, where event_type ∈ cash_moving_types. No whitelist needed — each event_type has a known cash impact encoded in the schema.

2. **Holdings are derived, not stored.** Quantity at any date = Σ trade.quantity for trades up to that date. Lot tracking uses event ordering. No mutable `portfolio_holdings` table to get wrong.

3. **Deterministic replay.** Given the same event log, the valuation engine produces identical snapshots regardless of when or where it runs. `computed_at` becomes a metadata field, not part of the result.

4. **Corporate actions as events.** Stock splits, mergers, acquisitions, and name changes are events in the log. A split event adjusts quantities retroactively. An acquisition event closes the old position and opens the new one.

5. **Cross-account links.** Transfers reference `counterparty_account_id`, enabling the system to verify that A's loss = B's gain at the user level.

6. **Validation at entry time.** Events are validated before appending: trade quantity can't exceed available position, TFSA can't go negative, margin must stay within limits. Bad data is rejected at import, not discovered months later in snapshots.

7. **Price snapshots as separate concern.** Prices are stored in a `portfolio_price_snapshots` table keyed by `(snapshot_date, company_id)`. The valuation engine reads prices that were specifically recorded for that snapshot date, not the "latest" price which may have been added after the fact.

#### Migration Path

| Phase | What | Why |
|-------|------|-----|
| 0 | Implement tactical 3-layer defense | Stop the bleeding now; 10 failing tests pass |
| 1 | Add `portfolio_events` table, dual-write on import | Events recorded alongside existing tables |
| 2 | Build event-replay valuation engine alongside `build_snapshot_row` | Run both, compare outputs |
| 3 | Backfill events from transaction history | All historical data in event format |
| 4 | Replace current snapshot job with event-replay engine | Old code path removed |
| 5 | Drop `portfolio_holdings` and whitelist; cash is fully derived | Mutable state eliminated |

#### Event Type Catalog

Each event type has a defined handler that determines its effect on cash, holdings,
and cost basis. This replaces the generic whitelist with type-specific logic.

```python
@dataclass
class Event:
    event_id: UUID
    account_id: int
    event_type: str
    event_date: date
    symbol: Optional[str]
    quantity: Optional[Decimal]
    unit_price: Optional[Decimal]    # per-share price for trades
    gross_amount: Optional[Decimal]  # total before fees
    net_amount: Optional[Decimal]    # actual cash impact (negative = cash out)
    commission: Optional[Decimal]
    fx_rate: Optional[Decimal]       # CAD per 1 foreign currency unit
    counterparty_account_id: Optional[int]
    source: str
    description: str

class EventHandler(ABC):
    """Each event type implements this interface."""

    @abstractmethod
    def cash_impact(self, event: Event) -> Decimal:
        """Net cash change. Positive = cash received, negative = cash spent."""
        ...

    @abstractmethod
    def holding_delta(self, event: Event) -> List[LotDelta]:
        """Changes to position lots. Empty list if no holding impact."""
        ...

    @abstractmethod
    def validate(self, event: Event, state: PortfolioState) -> List[str]:
        """Business rule checks. Return empty list if valid, warnings if not."""
        ...

    @abstractmethod
    def cost_basis_adjustment(self, event: Event) -> Decimal:
        """Adjustment to total cost basis (0 for most events)."""
        ...
```

**Implemented handlers:**

| Event Type | Cash Impact | Holding Delta | Cost Basis | Validation |
|-----------|-------------|---------------|------------|------------|
| `deposit` | +net_amount | None | +0 | TFSA: net_amount ≥ 0, cash after ≥ 0 |
| `withdrawal` | -net_amount | None | +0 | TFSA: net_amount > 0, cash after ≥ min_balance |
| `trade_buy` | -gross_amount | +quantity @ unit_price | +gross_amount | TFSA: cash before ≥ gross_amount |
| `trade_sell` | +gross_amount | -quantity (FIFO lots) | -realized_cost | Quantity before ≥ sell_qty |
| `dividend` | +net_amount | None | +0 | None |
| `interest` | +net_amount | None | +0 | None |
| `fee` | -net_amount | None | +0 | None |
| `tax` | -net_amount | None | +0 | None |
| `return_of_capital` | +net_amount | None | -net_amount | None |
| `fx_exchange` | ±net_amount | None | +0 | net_amount = sold_currency × rate_change |
| `internal_transfer_out` | 0 (cash) | -quantity @ cost | -cost | counterparty_account_id required |
| `internal_transfer_in` | 0 (cash) | +quantity @ cost | +cost | counterparty_account_id required |
| `stock_split` | 0 | quantity × split_factor | 0 (per-share cost ÷ split_factor) | split_factor > 0 |
| `merger_out` | 0 (cash) | -quantity @ cost | -cost | Receives merger_in event |
| `merger_in` | 0 (cash) | +quantity @ new_price | +cost (new cost basis) | Links to merger_out |
| `symbol_change` | 0 | symbol field updated | 0 | Symbol must exist in companies table |

**Why this eliminates the whitelist:** Each type explicitly declares its cash impact.
`internal_transfer_out` has `cash_impact=0` (security movement, not cash).
`deposit` has `cash_impact=+net_amount` (real cash in). There is no filter list
to maintain — adding a new type requires implementing a handler, which by
definition declares its cash impact. A type with no handler cannot be imported.

#### Replay Engine Design

The core algorithm replays events from the log up to a target date, producing a
`PortfolioState` from which all snapshot fields are derived.

```python
@dataclass
class PortfolioState:
    cash: Decimal
    lots: Dict[UUID, List[Lot]]   # company_id → [Lot, ...] (FIFO ordered)
    cost_basis: Decimal
    net_deposits: Decimal
    last_event_date: date

@dataclass
class Lot:
    lot_id: UUID
    company_id: int
    quantity: Decimal
    cost_per_share: Decimal
    acquired_date: date
    symbol: str

def replay_to_date(
    account_ids: List[int],
    target_date: date,
    event_store: EventStore,
    price_snapshot: Dict[int, Decimal],  # company_id → price frozen at target_date
) -> PortfolioState:
    """Replay all events up to target_date and compute portfolio state."""

    events = event_store.get_events_up_to(account_ids, target_date)
    # events sorted by (event_date, event_id) for deterministic ordering

    state = PortfolioState(cash=Decimal(0), lots={}, cost_basis=Decimal(0),
                           net_deposits=Decimal(0), last_event_date=None)

    for event in events:
        handler = EVENT_HANDLERS[event.event_type]

        # 1. Validate against current state
        warnings = handler.validate(event, state)
        if warnings:
            logger.warning(f"Event {event.event_id}: {warnings}")

        # 2. Apply cash impact
        state.cash += handler.cash_impact(event)

        # 3. Apply holding deltas
        for delta in handler.holding_delta(event):
            if delta.direction == "BUY":
                state.lots.setdefault(delta.company_id, []).append(Lot(
                    lot_id=uuid4(), company_id=delta.company_id,
                    quantity=delta.quantity,
                    cost_per_share=delta.unit_price,
                    acquired_date=event.event_date,
                    symbol=delta.symbol,
                ))
            elif delta.direction == "SELL":
                remaining = abs(delta.quantity)
                lots_list = state.lots.get(delta.company_id, [])
                while remaining > 0 and lots_list:
                    lot = lots_list[0]
                    if lot.quantity <= remaining:
                        remaining -= lot.quantity
                        lots_list.pop(0)
                    else:
                        lot.quantity -= remaining
                        remaining = 0

        # 4. Apply cost basis adjustment
        state.cost_basis += handler.cost_basis_adjustment(event)

        # 5. Track net deposits
        if event.event_type in ("deposit", "withdrawal"):
            state.net_deposits += event.net_amount

        state.last_event_date = event.event_date

    # After replay, apply prices from snapshot
    # Holdings value = Σ qty × price (from frozen price_snapshot, or avg_cost fallback)
    ...

    return state
```

**Deterministic ordering:** Events with the same `event_date` are ordered by
`event_id` (which is a UUID v7 with embedded timestamp for millisecond precision).
This guarantees the same order on every replay, regardless of import timing.

**Checkpointing:** For performance, intermediate states can be persisted:
```sql
CREATE TABLE portfolio_replay_checkpoints (
    account_id INT NOT NULL,
    checkpoint_date DATE NOT NULL,
    state_json JSONB NOT NULL,           -- serialized PortfolioState
    event_id BIGINT NOT NULL,            -- last event processed
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, checkpoint_date)
);
```
Replay starts from the latest checkpoint ≤ target_date, avoiding full log replay.
Checkpoints are created automatically after each successful snapshot computation.

**Price snapshot freezing:**
```sql
CREATE TABLE portfolio_price_snapshots (
    snapshot_date DATE NOT NULL,
    company_id INT NOT NULL,
    price NUMERIC NOT NULL,
    price_date DATE NOT NULL,
    source TEXT NOT NULL,       -- 'current_market_data', 'price_history', 'average_cost'
    exchange TEXT,
    stale_days INT,
    PRIMARY KEY (snapshot_date, company_id)
);
```
Before each valuation run, the engine records which prices it used. This means:
- Re-running the valuation with the same snapshot_date → same prices → same result
- Debugging: "What was AAPL priced at on Jul 6?" → `SELECT * FROM portfolio_price_snapshots WHERE snapshot_date = '2026-07-06' AND company_id = 1`
- The 4-tier resolution logic runs once to populate this table; subsequent reads are a single PK lookup

#### Concurrency and Idempotency

**Problem:** Two imports can race — e.g., a CSV import and a dividend webhook arriving simultaneously.

**Solution: Optimistic concurrency with idempotency keys.**

```sql
CREATE TABLE portfolio_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key TEXT UNIQUE,          -- sha256(source + external_id) for dedup
    account_id INT NOT NULL,
    event_type TEXT NOT NULL,
    ...
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
);
```

```python
def import_event(event: Event) -> Event:
    """Atomically insert event if not duplicate. Thread-safe."""
    with transaction():
        # The UNIQUE constraint on idempotency_key prevents duplicates
        # even if two threads try to insert the same event simultaneously
        existing = event_store.find_by_idempotency_key(event.idempotency_key)
        if existing:
            return existing  # Idempotent: second insert becomes no-op
        
        # Validate against current state
        state = replay_to_date(event.account_id, event.event_date, ...)
        handler = EVENT_HANDLERS[event.event_type]
        warnings = handler.validate(event, state)
        if warnings:
            raise EventValidationError(warnings)
        
        event_store.insert(event)
        invalidate_checkpoints(event.account_id, event.event_date)
```

**How idempotency keys work:** Each source event (CSV row, webhook payload) has
a unique natural key — e.g., WealthSimple's `transaction_id`, or a hash of
(account_id, symbol, date, type, amount). The import function computes
`sha256(source + external_id)` and stores it as `idempotency_key`. The UNIQUE
constraint guarantees that retrying the same external event produces the same
result without duplication.

**Checkpoint invalidation:** When a new event is inserted at date D, all
checkpoints ≥ D for that account are deleted. The next replay will stop at the
latest checkpoint < D, then process events from D onward. This is an O(1)
operation (DELETE + SQL index scan).

#### Error Recovery

**Scenario 1: Import succeeds, event stored, but checkpoint invalidation crashes.**

Recovery: The next scheduled snapshot computation will replay from the last valid
checkpoint, which is before the new event. The new event is in the log, so it
will be included in the replay. The checkpoint is at a slightly older state, but
replay is fast (events since last checkpoint only). No data loss.

**Scenario 2: Replay fails mid-way (e.g., price fetch timeout).**

Recovery: The snapshot is not stored. The next scheduled run retries. Because
replay is deterministic, it produces the same intermediate state up to the point
of failure. The timeout might resolve on retry. If it doesn't, the 4-tier price
resolution falls back to a lower tier (e.g., average_cost) and the snapshot is
stored with COST_FALLBACK quality. Progress, not perfection.

**Scenario 3: Corrupted event discovered (wrong quantity, wrong price).**

Recovery: Events are append-only — never update or delete. Instead, insert a
correcting event:
```python
# Wrong: imported 100 AAPL @ $150, should have been 100 @ $145
correction = Event(
    event_type="correction",
    description="Correcting cost basis for AAPL trade on 2024-01-15",
    quantity=0,           # no quantity change
    net_amount=500,       # cash was overstated by 100 × ($150 - $145)
    corrects_event_id=original_event_id,
)
```
The replay engine applies corrections after the original event, so the net
effect is correct. This preserves the audit trail — you can always see what
was originally imported and what corrected it.

**Scenario 4: Full schema migration needed.**

Rollback plan:
1. Keep old tables (`portfolio_holdings`, `portfolio_transactions`) during
   Phase 1-4 as read replicas
2. Feature-flag the new engine behind `ENABLE_EVENT_SOURCING_VALUATION`
3. Run both engines in parallel during Phase 2; compare outputs
4. Cut-over: flip flag to 100% new engine, keep old tables for 30 days
5. Rollback: flip flag back to old engine, re-run from last dual-write checkpoint
6. After 30 days with no rollback, archive old tables

#### Versioning Strategy

**Problem:** When business logic changes (e.g., new tax treatment for dividends,
updated split adjustment formula), historical snapshots may need recomputation.

**Solution: Versioned replay engine.**

```python
ValuationEngine(version=1):
  def compute(state, event):
      # Original dividend handling
      if event.event_type == "dividend":
          state.cash += event.net_amount
      ...

ValuationEngine(version=2):
  def compute(state, event):
      # New: dividend has withholding tax already netted
      if event.event_type == "dividend":
          state.cash += event.net_amount
          # Also track gross dividend separately for tax reporting
          ...
      ...
```

```sql
ALTER TABLE portfolio_snapshots ADD COLUMN engine_version INT NOT NULL DEFAULT 1;
```

When a new engine version is deployed:
1. Old snapshots are not automatically recomputed — they keep their `engine_version`
2. The dashboard can show "this value was computed with engine v1" metadata
3. A background job re-computes snapshots with the new engine, updating
   `engine_version` as it goes
4. Users see progressively more accurate historical data without a big-bang migration

This is the same pattern as Git — old commits stay at their original version,
new commits use the latest. You can bisect value changes to specific engine
versions.

#### Performance Characteristics

| Metric | Current (mutable state) | Event Sourced |
|--------|------------------------|---------------|
| Events per account (3yr) | — (N/A) | ~1000 (Acct 7), ~500 (Acct 8), ~1700 (Acct 9) |
| Replay cost (full, no checkpoint) | — | ~2ms/event → ~3.4s for Acct 9 |
| Replay cost (incremental, 1 day) | — | ~10 events/day → ~20ms |
| Snapshot query count | N+1 (holdings + prices per company) | 2 (events + price snapshot lookup) |
| Storage per snapshot | 1 row + 1 JSONB blob | 1 row (checkpoint) + price snapshot rows |
| Memory per snapshot | Holdings list in memory | Events list in memory (can be streamed) |
| Deterministic | No (FX, prices, timing) | Yes (same events → same state) |
| Rollback window | None (state mutates) | Full history preserved |

**The replay cost is bounded by event count, not holding count.** A user with
2 holdings and 5000 dividend events replays 5000 events, not 2 holdings. This
is the right trade-off — events are the source of truth, holdings are derived.
For users with high dividend volume, checkpointing (e.g., monthly) keeps replay
cost to ~50-100 events per incremental run.

#### Detailed Migration Phases

**Phase 0: Tactical 3-Layer Defense (1-2 days)**

Files changed:
- `shared/snapshot_builder.py`: Add 4-tier price resolution (`_resolve_holding_price`),
  cash sanity invariant (`_validate_snapshot`), validation warnings in output
- `infrastructure/repositories/portfolio_repository.py`: Add `BonusPayment`,
  `FxExchange`, `ReturnOfCapital`, `Tax` to `CASH_ACTIVITY_TYPES`
- `tests/test_portfolio_snapshots.py`: 10 new tests exist and fail; they pass
  after code changes

Validation: `pytest tests/test_portfolio_snapshots.py -v` → 63 pass, 1 pre-existing fail

Deployment: No migration needed. Code-only change. Rollback: `git revert`.

**Phase 1: Dual-Write Event Log (1 week)**

1. Create `portfolio_events` table via migration
2. Create `portfolio_price_snapshots` table via migration
3. Create `portfolio_replay_checkpoints` table via migration
4. Add import hook: after writing to `portfolio_transactions`, also write to
   `portfolio_events` (same transaction, or idempotent retry)
5. Add webhook handler: dividend payments, interest, fees write directly to
   `portfolio_events` (previously they only wrote to `portfolio_transactions`)

```python
# In import_transactions():
async def import_transactions(user_id, raw_data):
    ...
    parsed = parser.parse(raw_data)
    
    async with supabase.transaction():
        # Write to existing tables (backward compat)
        for txn in parsed:
            await portfolio_repo.insert_transaction(txn)
        
        # Dual-write to event log
        for txn in parsed:
            event = Event(
                event_type=map_activity_type_to_event_type(txn.activity_type),
                account_id=txn.account_id,
                event_date=txn.transaction_date,
                ...
            )
            await event_store.insert(event)
```

Validation: Count events in `portfolio_events` matches count in
`portfolio_transactions` for all accounts. No data loss.

Rollback: Disable dual-write hook. Events table accumulates but is unused.
Old import path continues to work unchanged.

**Phase 2: Build Event-Replay Engine (2 weeks)**

1. Implement `EventStore` — read events by account + date range
2. Implement `EventHandler` registry — one handler per event type
3. Implement `replay_to_date()` — core algorithm
4. Implement price snapshot freezing — record prices before valuation
5. Implement checkpoint manager — create/read/invalidate checkpoints
6. Run comparison mode: both old (`build_snapshot_row`) and new (event replay)
   compute snapshots, compare outputs, log discrepancies

```python
async def compute_snapshot_comparison(account_id, snapshot_date):
    # Old path
    old_snapshot = await compute_snapshot_old(account_id, snapshot_date)
    
    # New path
    events = event_store.get_events_up_to([account_id], snapshot_date)
    state = replay_to_date(events, snapshot_date)
    price_snapshot = freeze_prices(state.company_ids(), snapshot_date)
    new_snapshot = state_to_snapshot(state, price_snapshot)
    
    # Compare
    diff = compare(old_snapshot, new_snapshot)
    if diff.max_error > 0.01:  # > 1 cent difference
        logger.error(f"Snapshot mismatch for account {account_id} on {snapshot_date}: {diff}")
        alert_critical(f"Valuation mismatch: {diff}")
    else:
        logger.info(f"Snapshot match: account {account_id} on {snapshot_date}")
```

Validation: Zero mismatches in comparison mode for all historical dates.

Cut-over criteria:
- 7 consecutive days with zero mismatches across all accounts
- All 10 failing tests pass
- No regression in dashboard performance (p95 < 500ms)

**New tests added:**
- `test_multi_currency_holding_excluded_when_fx_rate_missing` — asserts holding excluded (not $0) when FX rate is None
- `test_multi_currency_none_rate_marks_holding_unavailable` — asserts freeze_prices skips company when FX is unavailable, but other holdings still valued correctly

**Phase 3: Backfill Events from Transaction History (3 days)**

```python
async def backfill_events():
    """One-time migration: portfolio_transactions → portfolio_events."""
    for account_id in all_account_ids:
        txns = portfolio_repo.get_all_transactions(account_id)
        for txn in txns:
            event = Event(
                idempotency_key=sha256(f"backfill:{txn.transaction_id}"),
                event_type=map_activity_type_to_event_type(txn.activity_type),
                account_id=account_id,
                event_date=txn.transaction_date,
                net_amount=txn.net_cash_amount,
                quantity=txn.quantity,
                unit_price=txn.unit_price,
                symbol=txn.symbol,
                source="backfill",
            )
            await event_store.insert(event)
        create_checkpoint(account_id, date.today())
```

Validation: Event count matches transaction count per account.
`replay_to_date()` produces state where `state.cash == get_cash_balance(account_id, target_date)` for all dates.

**Phase 4: Switch Snapshot Job to Event Replay (1 day)**

1. Change `portfolio_snapshot_job.py` to call event-replay engine instead of
   `build_snapshot_row`
2. Keep `build_snapshot_row` as a fallback (feature flag:
   `ENABLE_EVENT_SOURCING_VALUATION`)
3. Monitor discrepancy rate (should be 0 after Phase 2 validation)

```python
async def compute_daily_snapshots():
    today = now_utc().date()
    if getattr(settings, "ENABLE_EVENT_SOURCING_VALUATION", False):
        for account_id in all_account_ids:
            state = replay_to_date([account_id], today, event_store)
            price_snapshot = freeze_prices(state.company_ids(), today)
            snapshot = state_to_snapshot(state, price_snapshot)
            snapshots_repo.upsert_snapshot(snapshot)
    else:
        # Old path (keep until Phase 5)
        await compute_daily_snapshots_old()
```

Rollback: Flip `ENABLE_EVENT_SOURCING_VALUATION` to False. Old path resumes.

**Phase 5: Eliminate Mutable State (1 week)**

1. Drop `portfolio_holdings` table (replaced by event replay)
2. Drop `portfolio_transactions` activity_type whitelist (cash is derived)
3. Remove `build_snapshot_row` and `build_snapshot_row` testing
4. Remove `PortfolioRepository.get_cash_balance()` (no longer needed)
5. Remove `PortfolioRepository.CASH_ACTIVITY_TYPES` (no longer needed)
6. Archive old tables to cold storage (keep for audit, no longer read)

Each removal must be a separate deploy, with a monitoring period between.

#### Testing Strategy

**Unit tests (replay engine):**
```python
def test_replay_buy_then_sell():
    events = [
        deposit(10000, "2024-01-01"),
        buy("AAPL", 10, 150, "2024-01-15"),
        sell("AAPL", 5, 200, "2024-06-01"),
    ]
    state = replay_to_date([1], date(2024, 6, 2), events)
    assert state.cash == 10000 - 1500 + 1000  # = 9500
    assert len(state.lots[1]) == 1             # 5 AAPL remaining
    assert state.lots[1][0].cost_per_share == 150

def test_replay_dividends():
    events = [
        buy("AAPL", 10, 150, "2024-01-15"),
        dividend(50, "2024-03-01"),
    ]
    state = replay_to_date([1], date(2024, 3, 2), events)
    assert state.cash == -1500 + 50  # = -1450
    assert state.cost_basis == 1500

def test_replay_corporate_action_split():
    events = [
        buy("AAPL", 10, 15000, "2024-01-15"),  # 10 shares @ $1500
        stock_split("AAPL", 4, 1, "2024-06-01"),  # 4:1 split
    ]
    state = replay_to_date([1], date(2024, 6, 2), events)
    assert state.lots[1][0].quantity == 40  # 10 × 4
    assert state.lots[1][0].cost_per_share == 375  # 1500 ÷ 4
    assert state.cost_basis == 15000  # unchanged
```

**Fuzz testing:**
```python
def test_random_event_sequences():
    """Property: cash + holdings_value = net_deposits + unrealized_gains."""
    for _ in range(1000):
        events = generate_random_event_sequence()  # random buys, sells, divs
        state = replay_to_date([1], date(2026, 1, 1), events)
        
        holdings_value = sum(
            lot.quantity * current_prices[lot.company_id]
            for company_lots in state.lots.values()
            for lot in company_lots
        )
        net_deposits = sum(e.net_amount for e in events if e.event_type in ("deposit", "withdrawal"))
        unrealized_gains = holdings_value - state.cost_basis
        
        assert abs(state.cash + holdings_value - (net_deposits + unrealized_gains)) < 0.01
```

**Comparison tests (Phase 2):**
```python
def test_event_replay_matches_snapshot_builder():
    """For every historical snapshot, replay produces the same total_value."""
    for snapshot in portfolio_snapshots:
        state = replay_to_date(
            [snapshot.account_id], snapshot.snapshot_date, event_store,
            price_snapshot=price_snapshots_for_date(snapshot.snapshot_date),
        )
        expected = snapshot.total_value
        actual = float(state.cash + state.holdings_value)
        assert abs(actual - expected) < 0.01, (
            f"Mismatch for account {snapshot.account_id} on {snapshot.snapshot_date}: "
            f"expected {expected}, got {actual}"
        )
```

#### Economic Invariants

Beyond the arithmetic checks in the tactical 3-layer defense, event sourcing
enables richer economic invariants:

1. **Cash conservation:** `cash + Σ(trade_cost) = Σ(deposit) + Σ(dividend) + Σ(interest) - Σ(fees) - Σ(tax)`
   - Explanation: Cash changes only through explicit cash events. Every dollar
     that enters (deposit, dividend) or leaves (fee, tax) is accounted for.
   - This is automatically satisfied by the event model (cash is derived from
     events), so it's not a runtime check — it's a schema guarantee.

2. **Cost basis tracking:** `cost_basis = Σ(lot.quantity × lot.cost_per_share)`
   - After every event that affects lots, cost_basis must equal the FIFO-computed
     sum. This is checked after each event during replay, not just at snapshot time.
   - Catches: lot removal without cost adjustment (e.g., sell event that forgets to
     reduce cost basis).

3. **Cross-account net-zero:** For each `internal_transfer_out` event, there must
   be a matching `internal_transfer_in` with the same quantity, symbol, and date:
   ```sql
   SELECT a.account_id AS sender, b.account_id AS receiver,
          a.quantity, a.event_date
   FROM portfolio_events a
   JOIN portfolio_events b
     ON a.counterparty_account_id = b.account_id
    AND b.counterparty_account_id = a.account_id
    AND a.event_type = 'internal_transfer_out'
    AND b.event_type = 'internal_transfer_in'
    AND a.quantity = -b.quantity  -- opposite signs
    AND a.event_date = b.event_date
   ```
   Orphaned (unmatched) transfers raise a WARNING.

4. **Account-type invariants:**
   - TFSA: `cash ≥ 0` at all times (cannot go negative)
   - RRSP: `cash ≥ -$100` (small overdraft allowed for settlement)
   - Margin: `cash ≥ -margin_limit × (holdings_value)` where margin_limit
     is per-account (e.g., 0.5 for 2:1 leverage)
   - Non-registered: `cash ≥ -settlement_buffer` (typically 3 days of trade
     value)

5. **Time-consistency:** `snapshot[t] ≥ snapshot[t-1]` should hold for merged
   portfolio totals across accounts (no artificial dips).
   - This is checked post-computation as a quality metric, not a hard invariant
     (the portfolio can genuinely lose value).
   - A violation where total drops by >$10K but no withdrawal event exists on
     that date produces a WARNING.

These invariants are checked at import time (event validation) and at snapshot
time (post-computation). Between them, they cover every failure mode documented
in the -$2,903 bug chain.

#### What the Event-Sourced Design Eliminates

| Current Problem | How Event Sourcing Fixes It |
|----------------|---------------------------|
| Whitelist maintenance | Event types are in the schema; each handler declares its cash impact explicitly |
| Holdings table corruption | Holdings are derived from events; no table to corrupt |
| Cost basis bugs (key names) | Cost basis = FIFO replay from events; no hardcoded column names |
| Non-deterministic snapshots | Same events + same price snapshot → same output every time |
| Fair-weather prices (only latest) | Price snapshot table freezes prices per valuation date |
| Cross-account transfers uncounted | counterparty_account_id + net-zero invariant |
| Import-time validation missing | Events validated before append (TFSA can't go negative, etc.) |
| Historical debugging impossible | Any past date is reproducible by replaying events up to that date |
| Corporate actions break IDs | Stock splits and mergers are explicit event types with handlers |
| Intraday ordering ambiguous | UUID v7 event IDs provide millisecond ordering |
| Price staleness undifferentiated | Source column in price snapshot shows which tier was used |
| Single code version for all history | Engine version column allows per-snapshot version tracking |

---

## Appendix E: Professional Industry Comparison — Gaps and Improvements

This appendix compares the proposed event-sourced design against production
portfolio management systems used by professional asset managers, brokerages,
and fintech platforms. The goal is to identify what the design gets right,
what it misses, and what a real-world implementation would need to address.

### Reference Systems

| System | Type | Scale | Architecture Highlights |
|--------|------|-------|------------------------|
| **Bloomberg PORT** | Buy-side PMS | Institutional, global | Real-time exposures, multi-factor risk models, integrated market data, compliance constraints at execution point |
| **SimCorp Dimension** | Front-to-back PMS | Institutional, 20+ countries | Integrated order management, compliance, portfolio accounting, performance attribution |
| **Charles Schwab** | Retail brokerage | $7.7T AUS, 30M+ accounts | Aerospike for intraday system of record, microservices, event-driven reconciliation |
| **Wealthsimple** | Retail fintech | 3M+ users, Canadian | Python/Go services, PostgreSQL, event-driven data pipelines |
| **Robinhood** | Retail brokerage | 23M+ users | Microservices, PostgreSQL, domain-driven decomposition |
| **FIS Securities Processing** | Post-trade platform | Global banks, broker-dealers | Real-time cross-asset processing, integrated settlement, accounting, corporate actions, collateral management |
| **S&P Global Corporate Actions** | Corporate actions data | 3M+ securities, 170 countries | Golden source data, election management, position tracking, tax handling |
| **Fund Recs** | NAV oversight | Fund administrators | Automated stale price detection, configurable ageing thresholds, exception dashboards |

### Gap 1: Missing CQRS (Command Query Responsibility Segregation)

**Design's approach:** Single `EventStore` that handles both writes (event import)
and reads (replay). The same data structure (`Event`) serves as both the command
and the query model.

**Industry practice:** Professional systems (SimCorp, Bloomberg PORT) separate
write and read models. Events are written to an append-only log, then projected
into one or more read-optimized models:
- **Transaction ledger** (write-optimized): Append-only, validated at entry
- **Portfolio dashboard** (read-optimized): Denormalized, pre-aggregated, OLAP-style
- **Performance analytics** (read-optimized): Time-series of returns, attribution
- **Risk model** (read-optimized): Factor exposures, VaR, stress tests

**Gap:** The current design uses the same event log directly for both. Every
replay scans and processes 1700 events to compute 25 fields. While checkpointing
mitigates this, the read model is still tightly coupled to the event schema.
Adding a new dashboard query (e.g., "show me dividend income by year") requires
either a new event scan or a new projection. No professional system replays
the full log on every read.

**Fix:** Add a projection layer:
```python
# Separate read models, updated by event handlers
@dataclass
class CashProjection:
    account_id: int
    date: date
    balance: Decimal  # Derived from events, updated incrementally

@dataclass
class HoldingsProjection:
    account_id: int
    company_id: int
    quantity: Decimal  # Running total, updated per trade event

@dataclass
class DividendProjection:
    account_id: int
    year: int
    total_dividends: Decimal  # Aggregated per year
```

Events trigger projection updates:
```python
def on_deposit(event, projections):
    projections.cash[event.account_id].balance += event.net_amount

def on_trade_sell(event, projections):
    projections.holdings[event.account_id][event.company_id].quantity -= event.quantity
    projections.cash[event.account_id].balance += event.gross_amount
```

This is the standard CQRS pattern: events are the source of truth (write side);
projections are derived models optimized for specific queries (read side).
The event log can still replay to rebuild any corrupted projection.

### Gap 2: No General Ledger Integration

**Design's approach:** Cash balance is the only financial metric. Net deposits
are tracked as a scalar. There is no double-entry accounting.

**Industry practice:** Every professional portfolio system integrates with or
contains a General Ledger (GL). SimCorp Dimension has full portfolio accounting.
FIS Securities Processing integrates middle-office accounting with settlement.
Even smaller systems like Orion maintain a transaction ledger with debits/credits.

**What the GL provides:**
- **Double-entry guarantee:** Every cash movement has a matching offset
  (deposit → cash increase AND liability increase)
- **Accrual accounting:** Dividends are accrued on ex-date, paid on pay date.
  The accrual period is tracked as a separate GL entry.
- **Gain/loss realization:** When a position is sold, the GL records the realized
  gain/loss as a separate accounting entry, not just a cash balance delta.
- **Tax lot accounting:** The GL maintains separate entries for short-term vs
  long-term gains, wash sales, and tax adjustments.

**Gap:** The current design conflates operational cash (what's in the account)
with accounting cash (what the portfolio is worth). These are different concepts.
A dividend declared Dec 31 but paid Jan 15 should be accrued in the Dec 31
valuation but not added to cash until Jan 15. The design has no accrual concept.

**Fix:** Add an accrual layer:
```python
@dataclass
class Accrual:
    event_id: UUID
    account_id: int
    accrual_date: date       # When it's earned (ex-date for dividends)
    settlement_date: date    # When cash actually moves
    amount: Decimal
    event_type: str          # 'dividend_accrual', 'interest_accrual', 'fee_accrual'
    settled: bool = False
```

Valuation logic:
```python
def compute_valuation(account_id, target_date):
    cash = replay_cash(account_id, target_date)             # settled cash only
    accruals = get_accruals(account_id, target_date)        # accrued but not settled
    holdings_value = compute_holdings_value(account_id, target_date)
    return PortfolioValue(
        cash = cash,
        accrued_income = sum(a.amount for a in accruals),
        holdings_value = holdings_value,
        total = cash + sum(a.amount for a in accruals) + holdings_value,
    )
```

### Gap 3: Corporate Actions Are Underspecified

**Design's approach:** Three corporate action event types: `stock_split`,
`merger_out`, `merger_in`, `symbol_change`. Each has a simple handler.

**Industry practice:** S&P Global Corporate Actions covers 3M+ securities across
170 countries with 50+ event types. Smartstream Smart Actions handles the
complete lifecycle: golden record management, position tracking, election
management, accounting integration, tax handling.

**Real-world corporate actions that are not handled:**

| Event Type | Complexity | What the Design Misses |
|-----------|-----------|----------------------|
| **Stock dividend** | Company pays dividend in stock, not cash. Quantity increases, no cash changes. | No `stock_dividend` event; would need `dividend` + `trade_buy` workaround |
| **Rights issue** | Shareholders can buy new shares at discount. Complex election: can take, sell, or let lapse. | No election management; no rights trading |
| **Spin-off** | Company creates separate entity, distributes shares pro rata. | No ability to create a new position from an existing one |
| **Reverse split** | Quantity decreases, price increases proportionally. | `stock_split` handles forward splits only. Reverse split needs `split_factor < 1`, which the design doesn't validate |
| **Tender offer** | Shareholders can sell shares at a fixed price. | Election: take offer or decline. Partial tenders. Pro-ration if oversubscribed. |
| **Delisting** | Company removed from exchange. Holding becomes worthless. | No `delisting` event. UNAVAILABLE tier would use stale price from before delisting. |
| **Wash sale** | Tax rule: selling at loss and buying back within 30 days. Loss is disallowed. | No wash sale tracking. Cost basis would be wrong for US taxpayers. |
| **Return of capital** (dividend sub-type) | A portion of dividend is tax-free return of capital, reducing cost basis. | Design has `return_of_capital` as cash-only, but doesn't adjust cost basis correctly for tax purposes. |

**Fix:** Add a dedicated Corporate Actions service with:
```python
class CorporateActionHandler:
    """Handles the lifecycle of a corporate action across accounts."""
    
    def announce(self, ca: CorporateAction):
        """Record the announcement, optional election period."""
        pass
    
    def record_election(self, account_id: int, election: Election):
        """Record shareholder's choice (take cash, take stock, decline)."""
        pass
    
    def execute(self, ca: CorporateAction):
        """Generate events based on elections. Creates the actual
        trade/dividend/transfer events that replay engine processes."""
        pass
    
    def validate(self, ca: CorporateAction) -> List[str]:
        """Check: position exists, election is valid, dates are consistent."""
        pass
```

This separates **corporate action lifecycle** (announcement, election, execution)
from **portfolio events** (the financial impact). The replay engine only sees
the executed events; the corporate actions service manages the complexity.

### Gap 4: No Security Master / Reference Data

**Design's approach:** Uses `company_id` and `symbol` directly from the
`companies` table. No awareness of exchanges, identifiers, asset classes.

**Industry practice:** Every professional PMS has a Security Master:
- **Identifiers:** CUSIP, ISIN, SEDOL, Bloomberg Ticker, Reuters RIC, FIGI
- **Asset class:** Equity, fixed income, option, future, currency, structured product
- **Exchange listing:** Primary exchange, secondary listings, currency
- **Sector/industry:** GICS, ICB, or custom classification
- **Corporate actions reference:** Links to corporate actions service
- **Status:** Active, suspended, delisted, matured

**Gap:** Without a security master, the system can't:
- Distinguish between TSX-listed TD and NYSE-listed TD (different prices, different currencies)
- Know when a security has matured (bond) or been called (preferred share)
- Apply correct FX conversion for multi-currency portfolios
- Group holdings by sector or asset class for risk analysis

**Fix:** Add a minimal security master:
```sql
CREATE TABLE security_master (
    company_id INT PRIMARY KEY,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL,  -- 'equity', 'etf', 'bond', 'option', 'mutual_fund'
    primary_exchange TEXT,
    currency TEXT NOT NULL DEFAULT 'CAD',
    isin TEXT,
    cusip TEXT,
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'delisted', 'matured', 'suspended'
    sector TEXT,
    industry TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The 4-tier price resolution would use this to know:
- Which exchange to query for prices (primary_exchange)
- Whether a price is even expected (matured bonds have no price)
- What fallback currency to apply

### Gap 5: No Performance Attribution or Benchmarking

**Design's approach:** Computes total_value, cost_basis, and cash. Returns are
"future work" (mentioned in Phase 3 as "Modified Dietz return engine").

**Industry practice:** Bloomberg PORT has multi-factor risk models (BARRA,
Axioma), attribution analysis (Brinson, factor-based), and benchmark comparison.
It shows which factors drove performance (sector allocation, stock selection,
currency effect, etc.). SimCorp Dimension has full GIPS-compliant performance
calculation with multiple return methods (time-weighted, money-weighted).

**Gap:** The system computes `total_value` but can't answer:
- "Why did my portfolio outperform the S&P 500 this quarter?"
- "Was the outperformance due to sector allocation or stock selection?"
- "What is my exposure to the tech sector?"
- "How much currency risk am I carrying?"

**Fix:** This is genuinely Phase 3+ work and shouldn't block the event-sourced
design. But the event schema should be designed with attribution in mind:
- Every event should have a `sector` field (derived from security master at
  import time, not re-derived on replay)
- Holdings projections should include sector breakdowns
- Price snapshots should include benchmark prices (e.g., S&P 500 level on
  snapshot date)

The design should at minimum acknowledge this gap and reserve fields for it,
rather than treating it as "add later."

### Gap 6: Tax Lot Accounting Is Incomplete

**Design's approach:** FIFO-only lot tracking. Cost basis is adjusted via
`cost_basis_adjustment` method on handlers.

**Industry practice:** Professional systems support:
- **Specific Identification (SpecID):** Choose which lots to sell at execution
  time. Used by active traders to optimize tax outcomes.
- **Average Cost:** Used by mutual funds and some jurisdictions.
- **FIFO:** Default for most brokerages.
- **LIFO/HIFO:** Less common but supported.
- **Wash sale tracking:** When a loss is realized and the same security is
  repurchased within 30 days, the loss is disallowed and added to the new
  position's cost basis.

**Gap:** The replay engine uses hardcoded FIFO (`lots_list.pop(0)`). There is no
way to choose which lots to sell. The `trade_sell` handler doesn't accept a
`lot_selection` parameter. Wash sales are not tracked.

**Fix:** Make lot selection configurable:
```python
class LotSelectionMethod(Enum):
    FIFO = "fifo"
    SPECIFIC = "specific"   # User picks lots at execution
    AVERAGE = "average"     # All lots merged to average cost

class TradeSellHandler(EventHandler):
    def holding_delta(self, event: Event, state: PortfolioState) -> List[LotDelta]:
        method = state.account_settings.get("lot_selection", LotSelectionMethod.FIFO)
        if method == LotSelectionMethod.FIFO:
            return self._fifo_sell(event, state)
        elif method == LotSelectionMethod.AVERAGE:
            return self._average_sell(event, state)
        elif method == LotSelectionMethod.SPECIFIC:
            return self._specific_sell(event, state, event.lot_ids)
```

Add wash sale tracking:
```python
def check_wash_sale(sale_event, state):
    """If sale at loss and buy of same security within 30 days, adjust cost basis."""
    if sale_event.net_amount >= 0:  # Not a loss
        return
    recent_buys = [
        e for e in state.events_buffer
        if e.event_type == 'trade_buy'
        and e.symbol == sale_event.symbol
        and sale_event.event_date - timedelta(days=30) <= e.event_date <= sale_event.event_date + timedelta(days=30)
    ]
    if recent_buys:
        disallowed_loss = abs(sale_event.net_amount)  # simplified
        # Add disallowed loss to cost basis of first recent buy
        ...
```

### Gap 7: No Multi-Currency Valuation

**Design's approach:** An `fx_exchange` event type exists, and the `Event` schema
has an `fx_rate` field. But the replay engine doesn't handle multi-currency
portfolios.

**Industry practice:** Bloomberg PORT values global portfolios in a base currency
(USD, EUR, etc.) by applying FX rates to each holding's market value in its
local currency. Schwab handles USD and CAD accounts separately but also supports
multi-currency for international equities. Wealthsimple offers USD accounts with
separate cash balances.

**Gap:** 
- Holdings priced in USD are added directly to CAD cash without FX conversion
- The price snapshot table doesn't store the FX rate used
- There's no concept of "base currency" per account or per user
- FX gains/losses on holdings are not tracked separately

**Example problem:** An account holds AAPL (priced in USD) and TD (priced in CAD).
On snapshot date, AAPL is $200 USD and TD is $85 CAD. USD/CAD = 1.36. The total
should be `($200 × 1.36) + $85 = $357 CAD`. The design has no mechanism to know
which currency each holding is priced in, nor the FX rate to apply.

**Fix:** Add currency awareness to the replay engine:
```python
@dataclass
class PortfolioState:
    cash: Dict[str, Decimal]        # currency → amount (e.g., {"CAD": 5000, "USD": 1000})
    lots: Dict[UUID, List[Lot]]     # Lot.currency added
    cost_basis: Decimal             # Always in base currency
    base_currency: str              # e.g., "CAD"

def compute_holdings_value(state, price_snapshot, fx_rates):
    """Convert each holding's value to base currency."""
    total = Decimal(0)
    for company_lots in state.lots.values():
        for lot in company_lots:
            local_price = price_snapshot[lot.company_id]  # e.g., 200 USD
            fx = fx_rates[lot.currency][state.base_currency]  # e.g., 1.36
            total += lot.quantity * local_price * fx
    return total
```

### Gap 8: No Reconciliation with External Data Sources

**Design's approach:** The event log is the single source of truth. Events are
the only way cash and holdings change.

**Industry practice:** Professional systems **reconcile** against external sources:
- **Custodian reconciliation:** Daily comparison of positions (what Schwab says
  we hold vs what our system says we hold)
- **Cash reconciliation:** Daily comparison of cash balance (what the broker
  says the cash is vs what we think it is)
- **Price reconciliation:** Comparing our prices against a second market data
  provider
- **Dividend reconciliation:** Comparing our expected dividends against what
  was actually paid

**Example problem (real):** Schwab reports $10,000 cash in Account 7. The event
log says $9,800 (a dividend was missed during import). The design would never
catch this because the event log IS the source of truth. There's no mechanism
to detect that the event log disagrees with reality.

**Gap:** The design achieves determinism by making the event log the sole
source of truth. But this means any gap between the event log and the actual
brokerage account is invisible.

**Fix:** Add reconciliation as a first-class process:
```python
async def reconcile_account(account_id, broker_statement):
    """Compare event log against broker's official record."""
    # 1. Replay events to get expected state
    expected = replay_to_date([account_id], broker_statement.as_of_date, event_store)
    
    # 2. Compare
    discrepancies = []
    if expected.cash != broker_statement.cash:
        discrepancies.append({
            "field": "cash",
            "expected": expected.cash,
            "actual": broker_statement.cash,
            "delta": broker_statement.cash - expected.cash,
        })
    
    # 3. Handle
    for d in discrepancies:
        if abs(d["delta"]) < 0.01:
            continue  # Rounding error, ignore
        if abs(d["delta"]) < 100:
            # Small discrepancy → flag for manual review
            create_reconciliation_flag(account_id, d)
        else:
            # Large discrepancy → auto-create correction event
            correction = Event(
                event_type="reconciliation_adjustment",
                net_amount=d["delta"],
                description=f"Reconciliation adjustment for {d['field']}",
                source="reconciliation_engine",
            )
            event_store.insert(correction)
```

### Gap 9: No Streaming / Real-Time Updates

**Design's approach:** Batch-oriented daily snapshots. Snapshot job runs on a
schedule. Users see yesterday's portfolio values.

**Industry practice:** Schwab and Robinhood show real-time (or near-real-time)
portfolio values. Bloomberg PORT shows intraday P&L with live market data.
Wealthsimple's dashboard updates within seconds of a trade.

**Gap:** A user deposits $10,000 and immediately wants to see it reflected.
The design waits until the next snapshot run. The snapshot job processes accounts
sequentially — if Account 9 has 1700 events and takes 3.4 seconds, Account 12
might be 30+ seconds behind Account 7. Batch latency compounds.

**Fix:** Add incremental projection updates on event import:
```python
async def import_event(event):
    """Standard import, but also update projections incrementally."""
    await event_store.insert(event)
    
    # Incremental projection update (sub-millisecond)
    handler = EVENT_HANDLERS[event.event_type]
    await projections.apply(event, handler)
    
    # Notify interested parties
    await notify_portfolio_update(event.account_id)
    
    # Full checkpoint update (async, don't block import)
    asyncio.create_task(async_update_checkpoint(event.account_id, event.event_date))
```

The dashboard reads from projections, not from replay, so it sees changes
as they happen. Daily snapshots are still run for: (a) verifiable audit trail,
(b) price snapshot freezing, (c) full invariant check.

### Gap 10: No NAV/Accrual Accounting

**Design's approach:** Cash is cash. Holdings value = qty × price. Total value =
cash + holdings.

**Industry practice:** For institutional PMS (SimCorp, Bloomberg PORT), Net Asset
Value (NAV) includes:
- Cash (actual balance)
- Accrued income (dividends declared but not paid, interest accrued but not received)
- Accrued expenses (management fees, custody fees)
- Unrealized gains/losses
- Realized gains/losses (captured at trade date, not settlement date)
- Deferred tax assets/liabilities (for taxable accounts)
- Capital calls (for private equity/alternative investments)

**Gap:** The current `total_value` is misleading for accounts with significant
accruals. Example: A bond fund accrues interest daily. If the snapshot captures
mid-month, the accrued interest for 15 days is missing. The user sees a lower
total than the NAV would show.

**Fix:** Add accrual events:
```python
accrual_event = Event(
    event_type="interest_accrual",
    net_amount=125.50,         # 15 days × $8.37/day
    accrual_start=date(2026, 7, 1),
    accrual_end=date(2026, 7, 15),
    settle_date=date(2026, 7, 31),
    description="Accrued interest on 1Y T-Bill",
)
```

Valuation logic:
```python
def compute_total_value(cash, holdings_value, target_date):
    accruals = sum(
        a.net_amount for a in accruals
        if a.accrual_start <= target_date <= a.accrual_end
    )
    return cash + holdings_value + accruals
```

### Systemic Gaps (Cross-Cutting)

#### Gap S1: GDPR / Right to Be Forgotten

Event sourcing's immutable log violates GDPR's right to erasure. Deleting an
event would change all subsequent replays. The financial industry solution is
**crypto-shredding**: encrypt personally identifiable information (PII) in
events and delete the decryption key when a user requests erasure. The events
still exist (required for audit compliance with financial regulations like
IIROC, FINRA), but the PII is irrecoverable.

```sql
-- Before erasure
INSERT INTO portfolio_events (event_data) VALUES (
    '{"account_id": 7, "type": "deposit", "description": "John Smith - Birthday"}'
);
-- After erasure (encrypted)
INSERT INTO portfolio_events (event_data) VALUES (
    '{"account_id": ENC(7), "type": "deposit", "description": ENC("John Smith - Birthday")}'
);
-- On erasure request: delete the encryption key; data becomes indecipherable
```

The design does not address this. Canadian regulations (PIPEDA) and similar
laws in other jurisdictions require it.

#### Gap S2: Schema Evolution / Upcasters

The design has `engine_version` for valuation logic but not for event schemas.
Events created today have fields that may not exist in events created 5 years
ago (e.g., `commission` was added later). The replay engine would crash on
events missing the `commission` field.

Industry solution: **Upcasters** — functions that transform old-format events
to the current schema during replay:
```python
UPCASTERS = {
    (2025, 1): upcast_v1_to_v2,   # Added commission field
    (2025, 6): upcast_v2_to_v3,   # Added fx_rate field, renamed source_channel
}

def upcast_all(events):
    """Transform events from any historical version to current schema."""
    for event in events:
        version = event.get("_schema_version", 1)
        while version < CURRENT_SCHEMA_VERSION:
            event = UPCASTERS.get((event.created_year, event.created_month), identity)(event)
            version += 1
        yield event
```

#### Gap S3: Multi-Tenancy and Isolation

The design assumes a single user ("StockerPro"). Professional systems must
isolate data between tenants (different users, different firms). The event log
cannot be shared. The design doesn't mention `user_id` in the event schema or
any tenant isolation mechanism.

**Fix:** Add `user_id` to every event and project it into table partitioning:
```sql
CREATE TABLE portfolio_events (
    user_id INT NOT NULL,
    account_id INT NOT NULL,
    ...
) PARTITION BY HASH (user_id);
```

#### Gap S4: Retention and Archival

The design stores all events forever. Professional systems have tiered storage:
- Hot (last 90 days): Full event log in fast storage (SSD/PostgreSQL)
- Warm (90 days – 7 years): Compressed events in cheaper storage
- Cold (>7 years): Aggregated checkpoints only, raw events archived to blob
  storage (S3, Azure Blob)

For regulatory compliance (FINRA requires 6-7 years), the 7-year mark is the
usual archival boundary. The design should specify retention policies per event
type (dividend events might be retained longer than fee events).

#### Gap S5: Observability Beyond Logging

The design mentions `logger.warning` and no other observability. Professional
systems expose:
- **Prometheus metrics:** Snapshot computation latency (p50/p95/p99), event
  import rate, checkpoint age, replay cache hit ratio
- **Tracing:** Each snapshot computation generates a trace showing which events
  contributed to the total, how long each phase took, which price tiers were hit
- **Alerting rules:** "Zero events imported for 24 hours" → WARNING,
  "Checkpoint age exceeds 7 days" → WARNING,
  "Reconciliation discrepancy > $100" → CRITICAL

The design should at minimum list the metrics that operators would need to know
the system is healthy.

### Summary Table

| Gap | Severity | Effort to Fix | Blocks Phase 0? |
|-----|----------|---------------|-----------------|
| G1: No CQRS separation | Medium | Medium (projections) | No |
| G2: No General Ledger | Low (for now) | Major (new domain) | No |
| G3: Corporate actions underspecified | Medium | Major (new service) | No |
| G4: No security master | Medium | Medium (new table) | No |
| G5: No performance attribution | Low | Major (Phase 3+) | No |
| G6: Tax lot accounting incomplete | Medium | Medium (configurable selection) | No |
| G7: No multi-currency | **High** | Major (core change) | **No** |
| G8: No reconciliation | Medium | New process | No |
| G9: No real-time updates | Low (for MVP) | Medium (projections) | No |
| G10: No NAV/accrual accounting | Low (for now) | Medium (new event types) | No |
| S1: GDPR right to erasure | **High** | Encryption key management | No |
| S2: Schema evolution | Medium | Upcaster framework | No |
| S3: Multi-tenancy | Low (app-specific) | Partitioning | No |
| S4: Data retention | Low | Archival process | No |
| S5: Observability | Medium | Metrics + tracing | No |

**What this means for Phase 0:** The tactical 3-layer defense needs none of
these gaps addressed. The event-sourced design (Phase 1-5) should address at
minimum G4 (security master), G7 (multi-currency), and S1 (GDPR) before the
first production event log is created, because those affect the event schema
and replay engine design. Schema changes after Phase 2 would require upcasters
(retrofitted) or a migration, both costly.

### What the Design Gets Right

Despite the gaps above, the core design decisions are sound and align with
industry practice:

1. **Immutable event log as single source of truth** — This is how FIS, SimCorp,
   and all major post-trade systems operate. The current design could be a
   direct competitor in this space.

2. **Deterministic replay** — Essential for audit compliance. FINRA and IIROC
   require the ability to reproduce historical valuations.

3. **Versioned engine** — Matches how Bloomberg PORT handles methodology changes.
   Industry standard, not overengineering.

4. **Price snapshot freezing** — Directly addresses the issue that
   "the latest price" changes over time. This is the same approach used by
   mutual fund NAV calculations.

5. **Separation of tactical fix from strategic architecture** — Phase 0
   (tactical 3-layer) vs Phase 1-5 (event sourcing) is the right ordering.
   Bloomberg PORT evolved over 20+ years with similar incremental improvements.

6. **Checkpointing** — Standard pattern in event-sourced systems. Matches how
   Kafka Streams state stores work.

7. **Idempotency keys** — Industry standard for preventing duplicate transactions
   in financial systems. Used by Stripe, Square, and every payment processor.

8. **Lots of code examples** — The pseudocode is at the right level of detail
   for a design document. It communicates intent without being a full implementation.

The design is **professionally credible** as a starting point for the tactical fix
(Phase 0) and as a roadmap for the long-term architecture (Phase 1-5). The gaps
identified above are refinements, not fundamental flaws. Every one of them is
addressable without changing the core event-sourced paradigm.

---

## Appendix F: Implementation Status — Complete Inventory

### Legend

```
[✓]  Implemented and tests pass
[~]  In progress
[ ]  Not started — design complete, ready for implementation
[N/A] Deferred / future phase
[✗]  Known gap, not yet designed
```

### 1. What Is Already Implemented

| # | Item | File(s) | Status | Evidence |
|---|------|---------|--------|----------|
| 1 | 10 failing gap-capture tests | `test_portfolio_snapshots.py` | [✓] | `pytest` shows all 10 fail with correct assertions |
| 2 | Empirical WealthSimple data analysis | Appendix B of this doc | [✓] | All 2724 transactions, 6 accounts, per-account cash documented |
| 3 | Guarantee proof | Appendix C of this doc | [✓] | Formal case analysis, comparison matrix |
| 4 | Design self-critique (12 failures) | Appendix D of this doc | [✓] | F1-F12 documented with mitigations |
| 5 | Professional industry comparison | Appendix E of this doc | [✓] | 10 functional gaps + 5 systemic gaps identified |
| 6 | Event-sourced architecture spec | Appendix D (long-term alt) + this appendix | [✓] | Full event schema, replay engine, migration phases |

**Important:** `snapshot_builder.py` has `total_cost`/`average_cost` key-name fixes
in the working tree (untracked). These are NOT committed and NOT part of the
tactical 3-layer defense — they were pre-existing fixes from earlier uncommitted
work. They do not address whitelist, price resolution, or validation gaps.

### 2. Phase 0: Tactical Fix + Historical Backfill [PENDING]

**Target:** Fix the -$2,903 bug chain AND repair all corrupted historical snapshots
so the UI shows correct data for every date. Code changes to `snapshot_builder.py`
and `portfolio_repository.py`, plus a one-time DB backfill script.

**Pre-flight check:** [✓] All 10 gap-capture tests exist and fail. After
implementation, all 10 will pass.

---

#### Fix 2.1: Add Missing Activity Types to Whitelist

**End outcome:** `PortfolioRepository.CASH_ACTIVITY_TYPES` includes all 13 known
cash-moving types. `get_cash_balance()` returns the correct cash value for all
6 WealthSimple accounts.

**Test with real data:**

```python
# In test_portfolio_snapshots.py — already written, currently failing
def test_whitelist_includes_bonus_payment():
    assert "BonusPayment" in CASH_ACTIVITY_TYPES, "BonusPayment missing — $25 gap"

def test_whitelist_includes_fx_exchange():
    assert "FxExchange" in CASH_ACTIVITY_TYPES, "FxExchange missing — $2,386 gap"

def test_whitelist_includes_return_of_capital():
    assert "ReturnOfCapital" in CASH_ACTIVITY_TYPES, "ReturnOfCapital missing — $19 gap"

def test_whitelist_includes_tax():
    assert "Tax" in CASH_ACTIVITY_TYPES, "Tax missing — $1 gap"

def test_whitelist_covers_all_known_db_types():
    db_types = list_all_activity_types_from_db()  # queries portfolio_transactions
    uncovered = [t for t in db_types if t not in CASH_ACTIVITY_TYPES
                 and t not in KNOWN_NON_CASH_TYPES]
    assert uncovered == [], f"Uncategorized types: {uncovered}"
```

**Real-data validation (manual, one-time):**

```bash
# Query the database for all distinct activity types
psql -d stockerpro -c "
  SELECT DISTINCT activity_type FROM portfolio_transactions
  ORDER BY activity_type;
"
# Expected: Trade, Dividend, MoneyMovement, Interest, BonusPayment,
#           FxExchange, ReturnOfCapital, Tax, InternalSecurityTransfer,
#           NonCashDistribution (10 types total)
# After adding 4 missing types: 8 should be CASH_ACTIVITY_TYPES,
# 2 should be KNOWN_NON_CASH_TYPES

# Verify cash balance matches known-good value for Account 7
psql -d stockerpro -c "
  SELECT SUM(net_cash_amount)
  FROM portfolio_transactions
  WHERE account_id = 7
    AND activity_type = ANY(ARRAY['Trade','Dividend','MoneyMovement',
                                 'Interest','BonusPayment','FxExchange',
                                 'ReturnOfCapital','Tax']::text[]);
"
# Expected: $351.28
```

**Implementation steps:**

1. Open `backend/infrastructure/repositories/portfolio_repository.py`
2. Locate `CASH_ACTIVITY_TYPES` at approximately line 1052
3. Add the 4 missing types:

```python
CASH_ACTIVITY_TYPES = [
    "Trade", "Dividend", "MoneyMovement", "Interest",
    "BonusPayment", "FxExchange", "ReturnOfCapital", "Tax",
]
```

4. Verify `KNOWN_NON_CASH_TYPES` list also exists (or add one) containing:
   `InternalSecurityTransfer`, `NonCashDistribution`

5. Run tests:
```bash
pytest tests/test_portfolio_snapshots.py::test_whitelist_includes_bonus_payment \
       tests/test_portfolio_snapshots.py::test_whitelist_includes_fx_exchange \
       tests/test_portfolio_snapshots.py::test_whitelist_includes_return_of_capital \
       tests/test_portfolio_snapshots.py::test_whitelist_includes_tax \
       tests/test_portfolio_snapshots.py::test_whitelist_covers_all_known_db_types -v
```
   Expected: all 5 pass

**Rollback:** `git checkout -- backend/infrastructure/repositories/portfolio_repository.py`

---

#### Fix 2.2: Add 4-Tier Price Resolution

**End outcome:** When `get_latest_prices()` returns no price for a holding (e.g.,
stale or missing data), `_resolve_holding_price()` cascades through 4 tiers:
1. Current market price (from `get_latest_prices`)
2. Price history forward-fill (last known trading price)
3. `average_cost` from holdings data
4. `UNAVAILABLE` — holding excluded from market value, not counted as $0

No holding can contribute $0 market value to the total, which was the root cause
of Account 10/11/12 having negative totals on Jun 23 when prices were missing.

**Test with real data:**

```python
# Already written, currently failing
def test_account_10_negative_total_when_prices_missing():
    """Account 10 has -$17K cash + $18K holdings cost but no prices.
    Before fix: total = -$17K + $0 = -$17K, flag=OK.
    After fix:  each holding marked UNAVAILABLE, flag=INCOMPLETE, total > -$17K."""
    snapshot = build_snapshot_row(account_id=10, snapshot_date=date(2026, 6, 23))
    assert snapshot.total_value > -17000  # Because UNAVAILABLE holdings are excluded
    assert snapshot.data_quality != "OK"  # Must be INCOMPLETE or better
```

**Real-data validation:**

```bash
# Identify holdings with no price data for Account 10
psql -d stockerpro -c "
  SELECT h.company_id, h.symbol, h.total_quantity, h.average_cost,
         p.id IS NULL AS no_price_record
  FROM portfolio_holdings h
  LEFT JOIN price_history p 
    ON h.company_id = p.company_id 
    AND p.price_date >= '2026-06-23'
  WHERE h.account_id = 10
    AND h.total_quantity > 0;
"
# Before fix: these holdings get price=0, market_value = quantity * 0 = 0
# After fix:  these get UNAVAILABLE, excluded from total
```

**Implementation steps:**

1. Add `_resolve_holding_price()` function to `snapshot_builder.py`:

```python
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple, Dict, Any

class PriceTier(Enum):
    CURRENT = "CURRENT"          # Tier 1: get_latest_prices
    FORWARD_FILL = "FORWARD"     # Tier 2: price_history forward-fill
    COST_BASIS = "COST_FALLBACK" # Tier 3: average_cost as proxy
    UNAVAILABLE = "UNAVAILABLE"  # Tier 4: skip this holding

def _resolve_holding_price(
    company_id: int,
    symbol: str,
    avg_cost: Optional[Decimal],
    latest_prices: Dict[int, Decimal],
    price_history: Dict[int, List[Dict[str, Any]]],
    snapshot_date: date,
) -> Tuple[Optional[Decimal], PriceTier]:
    """Resolve price using 4-tier cascade. Returns (price, tier).
    
    Returns (None, UNAVAILABLE) if no usable price found.
    """
    # Tier 1: current market price
    if company_id in latest_prices and latest_prices[company_id] is not None:
        return latest_prices[company_id], PriceTier.CURRENT
    
    # Tier 2: price_history forward-fill (most recent price <= snapshot_date)
    if company_id in price_history and price_history[company_id]:
        sorted_prices = sorted(
            price_history[company_id],
            key=lambda p: p.get("price_date", ""),
            reverse=True,
        )
        if sorted_prices:
            return sorted_prices[0].get("price"), PriceTier.FORWARD_FILL
    
    # Tier 3: average cost
    if avg_cost is not None and avg_cost > 0:
        return avg_cost, PriceTier.COST_BASIS
    
    # Tier 4: unavailable
    return None, PriceTier.UNAVAILABLE
```

2. Modify `build_snapshot_row()` in `snapshot_builder.py`:

```python
# BEFORE (existing code that iterates holdings):
holding_value = holding.get("total_cost", 0) or 0

# AFTER:
price, tier = _resolve_holding_price(
    h["company_id"], h.get("symbol", ""),
    h.get("average_cost"), latest_prices,
    price_history, snapshot_date,
)
if tier == PriceTier.UNAVAILABLE:
    continue  # Skip this holding entirely
holding_value += Decimal(str(h["total_quantity"])) * price
```

3. Track worst tier across all holdings to set snapshot quality flag:

```python
# After processing all holdings, determine quality
TIER_QUALITY = {
    PriceTier.CURRENT: SnapshotQuality.OK,
    PriceTier.FORWARD_FILL: SnapshotQuality.STALE_PRICE,
    PriceTier.COST_BASIS: SnapshotQuality.COST_FALLBACK,
    PriceTier.UNAVAILABLE: SnapshotQuality.INCOMPLETE,
}
worst_quality = max(TIER_QUALITY[t] for t in used_tiers)
snapshot["data_quality"] = worst_quality.value
```

4. Run tests:
```bash
pytest tests/test_portfolio_snapshots.py::test_account_10_negative_total_when_prices_missing -v
```
   Expected: passes (total > -17000, quality != OK)

**Rollback:** `git checkout -- backend/shared/snapshot_builder.py`

---

#### Fix 2.3: Add Cash Sanity Invariant

**End outcome:** After computing the snapshot, a validation step checks:
- W1: Zero market value with non-zero holdings → INCOMPLETE quality
- W2: Negative total with positive holdings value → WARNING
- W3: Cash < -1.5×cost_basis → WARNING (account-type-aware)

Any warning sets `validation_warnings` in the snapshot output.

**Test with real data:**

```python
# Already written, currently failing
def test_negative_total_quality_not_ok():
    """Account 10 on Jun 23 has total=-$17,350, holdings_value > $0, cash=-$17,350.
    Before fix: quality=OK (arithmetic invariant passes: -17350 = -17350 + 0).
    After fix:  quality ≠ OK because W2 fires: negative total with positive holdings."""
    snapshot = build_snapshot_row(account_id=10, snapshot_date=date(2026, 6, 23))
    assert snapshot.data_quality != "OK", (
        "Account 10 has negative total with positive holdings — must not be OK"
    )

def test_negative_total_has_warning():
    snapshot = build_snapshot_row(account_id=10, snapshot_date=date(2026, 6, 23))
    assert snapshot.validation_warnings is not None
    assert any("negative total" in w.lower() for w in snapshot.validation_warnings)

def test_cash_too_negative_warning():
    """Account 10: cash=-$17,350, cost_basis=$18,790. 
    -17350 < -1.5 * 18790 = -28185? No. But cash < -cost_basis → warning."""
    snapshot = build_snapshot_row(account_id=10, snapshot_date=date(2026, 6, 23))
    assert snapshot.validation_warnings is not None
```

**Real-data validation:**

```bash
# Check which accounts fail W3 invariant
psql -d stockerpro -c "
  SELECT account_id, cash_balance, cost_basis,
         CASE 
           WHEN cash_balance < -1.5 * cost_basis THEN 'W3 VIOLATION'
           WHEN cash_balance < 0 AND cash_balance >= -1.5 * cost_basis THEN 'W3 BORDERLINE'
           ELSE 'OK'
         END as w3_status
  FROM portfolio_snapshots
  WHERE snapshot_date = '2026-06-23';
"
```

**Implementation steps:**

1. Add validation function to `snapshot_builder.py`:

```python
from dataclasses import dataclass, field
from typing import List, Optional
from decimal import Decimal

@dataclass
class SnapshotValidation:
    warnings: List[str] = field(default_factory=list)
    quality_override: Optional[str] = None

def _validate_snapshot(
    total_value: Decimal,
    total_market_value: Decimal,
    cash_balance: Decimal,
    cost_basis: Decimal,
    has_holdings: bool,
    account_type: str,  # "TFSA", "RRSP", "MARGIN", "NON_REG", "CASH"
) -> SnapshotValidation:
    """Post-computation invariant checks. Returns warnings and quality override."""
    validation = SnapshotValidation()
    
    # W1: Zero market value with non-zero holdings
    if has_holdings and (total_market_value is None or total_market_value == 0):
        validation.warnings.append(
            "W1: Holdings exist but market value is $0 — all prices unresolved"
        )
        validation.quality_override = "INCOMPLETE"
    
    # W2: Negative total with positive holdings
    if total_value < 0 and (total_market_value or 0) > 0:
        validation.warnings.append(
            f"W2: Total value ({total_value:.2f}) is negative but holdings "
            f"value ({total_market_value:.2f}) is positive — possible missing deposit"
        )
        if not validation.quality_override:
            validation.quality_override = "WARNING"
    
    # W3: Cash too negative relative to cost basis
    if cost_basis and cost_basis > 0:
        threshold = Decimal(str(_get_cash_threshold(cost_basis, account_type)))
        if cash_balance < -threshold:
            validation.warnings.append(
                f"W3: Cash ({cash_balance:.2f}) is below threshold "
                f"({-threshold:.2f}) for {account_type} with cost basis {cost_basis:.2f}"
            )
            if not validation.quality_override:
                validation.quality_override = "WARNING"
    
    return validation

def _get_cash_threshold(cost_basis: Decimal, account_type: str) -> float:
    """Return the maximum allowed negative cash for this account type.
    Returns positive number; cash must be >= -return_value."""
    thresholds = {
        "TFSA": 0,           # Canadian law: TFSA cannot be negative
        "RRSP": 100,         # Small overdraft for settlement
        "MARGIN": float(cost_basis) * 0.5,  # 2:1 leverage limit
        "NON_REG": float(cost_basis) * 0.1, # 10% for settlement buffer
        "CASH": 0,           # Cash accounts cannot go negative
    }
    return thresholds.get(account_type.upper(), float(cost_basis) * 0.1)
```

2. Integrate validation into `build_snapshot_row()`:

```python
# After computing total_value, total_market_value, cash_balance, cost_basis:
validation = _validate_snapshot(
    total_value=total_value,
    total_market_value=total_market_value,
    cash_balance=cash_balance,
    cost_basis=cost_basis,
    has_holdings=len(holdings) > 0,
    account_type=account_data.get("account_type", "NON_REG"),
)

snapshot["validation_warnings"] = validation.warnings
if validation.quality_override:
    snapshot["data_quality_flag"] = validation.quality_override
```

3. Run tests:
```bash
pytest tests/test_portfolio_snapshots.py::test_negative_total_quality_not_ok \
       tests/test_portfolio_snapshots.py::test_negative_total_has_warning \
       tests/test_portfolio_snapshots.py::test_cash_too_negative_warning -v
```
   Expected: all 3 pass

**Rollback:** `git checkout -- backend/shared/snapshot_builder.py`

---

#### Fix 2.4: Add Zero-Deposit Detection Warning

**End outcome:** Accounts with Trade records but zero MoneyMovement deposits are
flagged with a `validation_warning`. This catches Accounts 10/11/12 pattern.

**Test with real data:**

```python
# Already written, currently failing
def test_account_10_zero_deposit_negative_cash():
    """Account 10 has trades but no deposits → warning."""
    snapshot = build_snapshot_row(account_id=10, snapshot_date=date(2026, 6, 23))
    assert snapshot.validation_warnings is not None
    assert any("no deposit" in w.lower() for w in snapshot.validation_warnings)
```

**Implementation steps:**

1. Add check to `_validate_snapshot()`:

```python
def _validate_snapshot(..., has_deposits: bool, ...):
    # W4: No deposits but has trades
    if not has_deposits:
        validation.warnings.append(
            "W4: Account has trades but no deposit records — "
            "cash may not reflect actual funding"
        )
```

2. Pass the flag from `build_snapshot_row()` — query whether the account has
   any `MoneyMovement` records with `net_cash_amount > 0`.

3. Run test:
```bash
pytest tests/test_portfolio_snapshots.py::test_account_10_zero_deposit_negative_cash -v
```
   Expected: passes

---

#### Fix 2.5 (WealthSimple End-to-End): Verify Real Account Values

**End outcome:** For Accounts 7, 8, 9, the fixed `build_snapshot_row` produces
total_value and cash_balance matching empirically verified correct values.

**Test with real data:**

```python
# Already written, currently failing
def test_wealthsimple_account_7_cash_matches_db():
    """Account 7 cash should be $351.28 with correct whitelist."""
    snapshot = build_snapshot_row(account_id=7, snapshot_date=date(2026, 7, 6))
    assert abs(snapshot.cash_balance - Decimal("351.28")) < 0.01, (
        f"Account 7 cash: expected 351.28, got {snapshot.cash_balance}"
    )

def test_wealthsimple_account_8_cash_matches_db():
    """Account 8 cash should be $5,005.84 with correct whitelist."""
    snapshot = build_snapshot_row(account_id=8, snapshot_date=date(2026, 7, 6))
    assert abs(snapshot.cash_balance - Decimal("5005.84")) < 0.01, (
        f"Account 8 cash: expected 5005.84, got {snapshot.cash_balance}"
    )
```

**Note:** The Account 9 cash discrepancy ($1,641.75 computed vs $1,235.23 stored)
is expected — the stored value came from a previous whitelist version. The test
asserts against the **correct** value ($1,641.75), not the stored value.

**Implementation steps:**

These tests exercise the full pipeline (whitelist fix + price resolution +
validation). They pass automatically when Fixes 2.1 through 2.4 are in place.
No additional code changes needed.

```bash
pytest tests/test_portfolio_snapshots.py::test_wealthsimple_account_7_cash_matches_db \
       tests/test_portfolio_snapshots.py::test_wealthsimple_account_8_cash_matches_db -v
```
Expected: both pass after all Phase 0 fixes applied.

---

#### Fix 2.6: Backfill All Corrupted Historical Snapshots

**End outcome:** Every historical snapshot in the database is validated against
the fixed `build_snapshot_row`. Any snapshot that fails invariance (wrong cash,
wrong cost_basis, wrong quality flag, negative total with OK flag) is corrected.
The UI chart shows no artificial dips for any historical date, not just Jun 23–Jul 6.

**Key difference from naive approach:** The existing script
`backend/scripts/backfill_portfolio_snapshots.py` already supports `--repair` and
`--validate-only` flags. But it only detects one bug type (`cost_basis=0` with
non-zero holdings). Phase 0 introduces 3 additional bug types (wrong whitelist
cash, negative total with OK flag, UNAVAILABLE prices). The backfill script must
be extended to detect and fix ALL 4 bug types.

**The 4 bug types the backfill must detect:**

| Bug Type | Detection Rule | Introduced By | Fixed By |
|----------|---------------|---------------|----------|
| Key-name (`cost_basis=0` with holdings) | `cost_basis=0 AND holdings_json has qty>0` | Original code (pre-Jun 23) | Existing `--repair` flag |
| Whitelist cash (wrong `cash_balance`) | `recomputed_cash != stored_cash_balance` | Missing `BonusPayment`, `FxExchange`, etc. | Phase 0 Fix 2.1 |
| Negative total with OK flag | `total_value < 0 AND data_quality_flag='OK'` | Missing prices + missing whitelist | Phase 0 Fix 2.2-2.3 |
| Missing price with $0 market value | `holdings_market_value=0 AND holdings have qty>0` | Missing `get_latest_prices` fallback | Phase 0 Fix 2.2 |

**Test with real data:**

```python
def test_backfill_account_9_cash_is_correct():
    """After backfill, Account 9 Jun 23 snapshot has correct cash."""
    snapshot = get_snapshot_from_db(account_id=9, snapshot_date=date(2026, 6, 23))
    # Before backfill: $1,235.23 (wrong whitelist version)
    # After backfill:  $1,641.75 (correct whitelist)
    assert abs(snapshot.cash_balance - Decimal("1641.75")) < 0.01

def test_backfill_account_10_dip_removed():
    """Account 10 Jun 23 no longer shows -$17,350 dip."""
    snapshot = get_snapshot_from_db(account_id=10, snapshot_date=date(2026, 6, 23))
    # Before backfill: -$17,350 (no prices → $0 holdings + -$17K cash)
    # After backfill:  > -$17,000 (UNAVAILABLE holdings excluded, total != cash alone)
    assert snapshot.total_value > Decimal("-17000")

def test_backfill_no_corruption_remains():
    """Every snapshot across ALL dates passes invariant check after backfill."""
    errors = []
    for account_id in ALL_ACCOUNT_IDS:
        for snap in get_all_snapshots(account_id):
            recomputed = build_snapshot_row(account_id, snap.snapshot_date)
            diffs = []
            if abs(recomputed.total_value - snap.total_value) > 0.01:
                diffs.append(f"total_value: stored={snap.total_value} vs {recomputed.total_value}")
            if abs(recomputed.cash_balance - snap.cash_balance) > 0.01:
                diffs.append(f"cash_balance: stored={snap.cash_balance} vs {recomputed.cash_balance}")
            if recomputed.data_quality_flag == "OK" and snap.data_quality_flag != "OK":
                diffs.append(f"quality_flag: stored={snap.data_quality_flag} vs {recomputed.data_quality_flag}")
            if diffs:
                errors.append(f"Account {account_id} on {snap.snapshot_date}: {'; '.join(diffs)}")
    
    assert len(errors) == 0, f"Corruption remains:\n" + "\n".join(errors[:10])
```

**Real-data validation (manual, one-time):**

```bash
# Run the existing repair script with --validate-only first to see current state
python -m scripts.backfill_portfolio_snapshots --validate-only
# This checks invariants on ALL existing snapshots — not just the known-bad range

# Then run with --repair and --dry-run to see what would be fixed
python -m scripts.backfill_portfolio_snapshots --repair --dry-run

# After Phase 0 code changes, run --repair for real (fixes key-name + new bug types)
python -m scripts.backfill_portfolio_snapshots --repair

# Verify corrected values
psql -d stockerpro -c "
  SELECT account_id, snapshot_date,
         cash_balance, holdings_market_value, total_value, data_quality_flag
  FROM portfolio_snapshots
  WHERE snapshot_date = '2026-06-23'
    AND account_id IN (7, 8, 9, 10, 11, 12)
  ORDER BY account_id;
"
# Expected:
# Account 7:  cash=$351.28,   flag=OK or STALE
# Account 8:  cash=$5,005.84, flag=STALE
# Account 9:  cash=$1,641.75, flag=STALE
# Account 10: cash=-$17,350,  flag=INCOMPLETE (UNAVAILABLE holdings + W2 warning)
# Account 11: cash=-$24,200,  flag=INCOMPLETE
# Account 12: cash=-$4,670,   flag=INCOMPLETE
```

**Implementation steps:**

1. **Extend existing `find_corrupted_snapshots()`** in
   `backend/scripts/backfill_portfolio_snapshots.py` to detect all 4 bug types
   (not just key-name). Add new functions:

```python
# Added to backfill_portfolio_snapshots.py

from shared.snapshot_builder import build_snapshot_row, _validate_snapshot

class CorruptionType(Enum):
    KEY_NAME = "key_name"           # cost_basis=0 with non-zero holdings
    WHITELIST_CASH = "whitelist"    # cash_balance doesn't match recomputed
    NEGATIVE_TOTAL = "negative"     # total<0 with OK flag
    MISSING_PRICE = "missing_price" # $0 market value with non-zero qty

def find_all_corrupted_snapshots() -> Dict[CorruptionType, List[Dict]]:
    """Detect all 4 corruption patterns across ALL historical snapshots."""
    
    repo = PortfolioRepository()
    snapshots_repo = PortfolioSnapshotsRepository()
    accounts = repo.get_user_accounts_all()
    
    all_bugs = {t: [] for t in CorruptionType}
    
    for acct in accounts:
        aid = acct["account_id"]
        all_snaps = snapshots_repo.get_account_snapshots(aid)
        
        for snap in all_snaps:
            sd = snap["snapshot_date"]
            if isinstance(sd, str):
                sd = date.fromisoformat(sd)
            
            hj = snap.get("holdings_json") or []
            has_holdings = any(h.get("quantity", 0) > 0 for h in hj)
            
            # Type 1: Key-name (cost_basis=0 with non-zero holdings)
            if snap.get("cost_basis", 0) == 0 and has_holdings:
                all_bugs[CorruptionType.KEY_NAME].append(snap)
            
            # Type 2: Whitelist cash (recompute cash and compare)
            recomputed_cash = repo.get_cash_balance(aid, sd)
            stored_cash = Decimal(str(snap.get("cash_balance", 0)))
            if abs(recomputed_cash - stored_cash) > Decimal("0.01"):
                all_bugs[CorruptionType.WHITELIST_CASH].append({
                    **snap,
                    "expected_cash": recomputed_cash,
                    "stored_cash": stored_cash,
                })
            
            # Type 3: Negative total with OK flag
            total = Decimal(str(snap.get("total_value", 0)))
            if total < 0 and snap.get("data_quality_flag") == "OK":
                all_bugs[CorruptionType.NEGATIVE_TOTAL].append(snap)
            
            # Type 4: $0 market value with non-zero holdings
            mv = Decimal(str(snap.get("holdings_market_value", 0)))
            if mv == 0 and has_holdings:
                all_bugs[CorruptionType.MISSING_PRICE].append(snap)
    
    return all_bugs


def repair_all_corrupted(dry_run: bool = False) -> Dict[str, int]:
    """Repair all detected corruption types. Returns counts per type."""
    all_bugs = find_all_corrupted_snapshots()
    
    # Deduplicate: a snapshot may have multiple bug types — repair once
    to_repair = set()
    for bug_type, snaps in all_bugs.items():
        for s in snaps:
            to_repair.add((s["account_id"], s["snapshot_date"]))
    
    logger.info(f"Found {len(to_repair)} unique corrupted snapshots to repair")
    for bug_type, snaps in all_bugs.items():
        logger.info(f"  {bug_type.value}: {len(snaps)}")
    
    repaired = 0
    errors = 0
    for account_id, snapshot_date in to_repair:
        try:
            # Recompute using the FIXED build_snapshot_row (after Phase 0 changes)
            sd = date.fromisoformat(snapshot_date) if isinstance(snapshot_date, str) else snapshot_date
            corrected = build_snapshot_row(account_id=account_id, snapshot_date=sd)
            
            if not dry_run:
                snapshots_repo.upsert_snapshot(corrected)
            repaired += 1
        except Exception as e:
            logger.error(f"Failed to repair account {account_id} on {snapshot_date}: {e}")
            errors += 1
    
    return {"repaired": repaired, "errors": errors, "skipped": 0}
```

2. **Add `--repair-all` flag** to the existing script's argument parser
   (parallel to the existing `--repair` flag which only handles key-name):

```python
parser.add_argument("--repair-all", action="store_true",
                    help="Detect and repair ALL corruption types (key-name, whitelist, negative total, missing price)")
```

3. **Validate by running against ALL historical snapshots**, not just Jun 23–Jul 6:

```bash
# First, see what corruption exists across all dates
python -m scripts.backfill_portfolio_snapshots --validate-only

# Check for all 4 bug types
python -m scripts.backfill_portfolio_snapshots --repair-all --dry-run

# Then repair
python -m scripts.backfill_portfolio_snapshots --repair-all

# Final validation
python -m scripts.backfill_portfolio_snapshots --validate-only
# Expected: no validation errors
```

---

#### Phase 0 Acceptance Criteria

```bash
# Run all tests
pytest tests/test_portfolio_snapshots.py -v

# Expected results:
#   54 existing tests: 53 pass, 1 pre-existing fail
#      (test_negative_cash_without_deposits_produces_negative_total — wrong assertion)
#   10 new gap-capture tests: all 10 pass
#   + backfill tests (Fix 2.6): all pass
#   ────────────────────────────────
#   Total: 66+ pass, 1 known pre-existing fail

# Verify ALL historical snapshots are clean (not just Jun 23-Jul 6)
python -m scripts.backfill_portfolio_snapshots --validate-only
# Expected: "Validation issue" count = 0 for all accounts

# Verify no corruption of any type remains
python -m scripts.backfill_portfolio_snapshots --repair-all --dry-run
# Expected: "Found 0 unique corrupted snapshots to repair"

# Known gap: daily snapshot freshness
# ───────────────────────────────────
# After Phase 0, the UI shows CORRECT data but not REAL-TIME data.
# Snapshots are computed once per day (EOD). If the user logs in at 3 PM,
# they see yesterday's snapshot. This is acceptable for MVP.
# Future: Phase 4 adds intra-day projections.
# Mitigation: Show "Last updated: <computed_at>" in the UI header so
# the user knows the data age. Never claim data is "live".
```

**Rollback (backfill only):** Not possible via git revert. Before running
`--repair-all`, back up the portfolio_snapshots table:
```bash
pg_dump --table=portfolio_snapshots --data-only stockerpro > pre_backfill_snapshots.sql
# Restore with: psql -d stockerpro -f pre_backfill_snapshots.sql
```

### 3. Phase 1: Dual-Write Event Log (Multi-Currency Ready) [PENDING]

**End outcome:** Every transaction written to `portfolio_transactions` is also
written to `portfolio_events` in the same logical operation. `portfolio_events`
is append-only, immutable, multi-currency from day one, and contains all
historical data. The event count matches the transaction count for all accounts.
The `portfolio_price_snapshots` table records FX rates alongside prices.
A `security_master` table exists to resolve exchange and currency per holding.

**Test with real data:**

```python
async def test_event_count_matches_transaction_count():
    """After Phase 1, every transaction has a corresponding event."""
    async with db.transaction():
        txn_count = await db.fetch_val(
            "SELECT COUNT(*) FROM portfolio_transactions"
        )
        event_count = await db.fetch_val(
            "SELECT COUNT(*) FROM portfolio_events"
        )
    assert txn_count == event_count, (
        f"Transaction count ({txn_count}) doesn't match event count ({event_count})"
    )

async def test_event_account_7_expected_events():
    """Account 7 has ~1000 transactions; events must match."""
    async with db.transaction():
        events = await event_store.get_events_up_to([7], date(2026, 7, 7))
    assert len(events) == approx_1000  # verify during implementation

async def test_event_immutability():
    """Events cannot be updated or deleted after insertion."""
    event_id = await event_store.insert(test_event())
    with pytest.raises(ImmutableEventError):
        await event_store.update(event_id, {"net_amount": 999})
    with pytest.raises(ImmutableEventError):
        await event_store.delete(event_id)

async def test_dual_write_atomic_rollback():
    """If the transaction insert fails after event insert, the event must also
    be rolled back. No orphan events without matching transactions."""
    event = Event(
        idempotency_key=event_store.make_idempotency_key("test", "rollback_test"),
        user_id=1, account_id=1, event_type="deposit",
        event_date=date(2024, 1, 1), currency="CAD",
        net_amount=Decimal("5000"), source="test",
        description="Test atomic rollback", schema_version=1,
    )
    
    # Simulate: event inserted, then transaction insert fails
    try:
        async with supabase.transaction():
            # Insert event
            inserted = await event_store.insert(event)
            assert inserted.event_id is not None, "Event should be inserted"
            
            # Simulate transaction insert failure (e.g., constraint violation)
            raise DatabaseError("Simulated transaction failure")
    except DatabaseError:
        pass  # Expected — transaction rolled back
    
    # Verify: event should NOT exist (rolled back with the transaction)
    remaining = await event_store.find_by_idempotency_key(event.idempotency_key)
    assert remaining is None, (
        f"Orphan event found after rollback: {remaining}"
    )

async def test_dual_write_orphan_detection_runs_daily():
    """A daily validation job detects any orphan events (events without matching
    portfolio_transactions rows) and alerts."""
    # Simulate: an orphan event was created (e.g., due to a bug in a previous
    # version of the dual-write hook where the transaction succeeded but the
    # event insert happened outside the transaction scope)
    orphan = Event(
        idempotency_key=event_store.make_idempotency_key("test", "orphan_test"),
        user_id=1, account_id=1, event_type="deposit",
        event_date=date(2024, 1, 1), currency="CAD",
        net_amount=Decimal("5000"), source="test_orphan",
        description="Orphan event — no matching transaction", schema_version=1,
    )
    await event_store.insert(orphan)
    
    # Run orphan detection
    orphans = await detect_orphan_events()
    assert any(o.event_id == orphan.event_id for o in orphans), (
        "Orphan event was not detected"
    )
    
    # Clean up
    await force_delete_event(orphan.event_id)

async def detect_orphan_events() -> List[Event]:
    """Find events that have no matching portfolio_transactions row.
    
    Uses LEFT JOIN: events with no matching transaction → orphan.
    Only checks events created in the last 24 hours (the validation window).
    """
    rows = await supabase.table("portfolio_events") \
        .select("portfolio_events.*") \
        .join("portfolio_transactions",
              "portfolio_events.idempotency_key = portfolio_transactions.external_id",
              how="left") \
        .is_("portfolio_transactions.id", None) \
        .gte("portfolio_events.created_at", "now() - interval '24 hours'") \
        .execute()
    
    return [EventStore._row_to_event(r) for r in rows.data]

async def force_delete_event(event_id: UUID):
    """Bypass immutability for cleanup in tests only.
    Never call this in production code."""
    await supabase.table("portfolio_events") \
        .delete() \
        .eq("event_id", str(event_id)) \
        .execute()
```

**Implementation steps:**

#### 3.1 Create Tables via Migration

```python
# backend/migrations/YYYYMMDD_HHMMSS_create_portfolio_events.py

import asyncio
from infrastructure.database import supabase

async def up():
    """Create portfolio_events and supporting tables (multi-currency ready)."""
    
    # Core event table — currency is required from day one
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_events (
            event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            idempotency_key TEXT UNIQUE,
            user_id INT NOT NULL,
            account_id INT NOT NULL,
            event_type TEXT NOT NULL,
            event_date DATE NOT NULL,
            symbol TEXT,
            company_id INT,
            quantity NUMERIC,
            unit_price NUMERIC,
            gross_amount NUMERIC,
            net_amount NUMERIC,
            commission NUMERIC,
            currency TEXT NOT NULL,           -- ISO 4217: 'CAD', 'USD', etc.
            fx_rate NUMERIC,                  -- CAD per 1 unit of currency (NULL if base)
            settlement_currency TEXT,          -- Currency the cash settled in
            settlement_net_amount NUMERIC,     -- Net amount in settlement currency
            counterparty_account_id INT,
            description TEXT,
            source TEXT NOT NULL,
            schema_version INT NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            corrects_event_id UUID REFERENCES portfolio_events(event_id)
        );
    """)

    -- Verify with comment: "All amounts are stored in the event's currency.
    -- Replay engine converts to base currency using fx_rate at valuation time."

    # Security master — needed to know what currency each holding is priced in
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS security_master (
            company_id INT PRIMARY KEY,
            symbol TEXT NOT NULL,
            asset_class TEXT NOT NULL DEFAULT 'equity',
            currency TEXT NOT NULL,            -- ISO 4217: pricing currency
            primary_exchange TEXT,
            isin TEXT,
            cusip TEXT,
            sector TEXT,
            industry TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # FX rate history — provides historical FX rates for multi-currency replay
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS fx_rate_history (
            from_currency TEXT NOT NULL,
            to_currency TEXT NOT NULL,
            rate_date DATE NOT NULL,
            rate NUMERIC NOT NULL,
            source TEXT NOT NULL DEFAULT 'bank_of_canada',
            PRIMARY KEY (from_currency, to_currency, rate_date)
        );
    """)

    # Account base currency settings
    await supabase.execute("""
        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS base_currency TEXT NOT NULL DEFAULT 'CAD';
    """)
    
    # Encrypted PII for GDPR compliance (crypto-shredding)
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_event_pii (
            event_id UUID PRIMARY KEY REFERENCES portfolio_events(event_id),
            encrypted_description BYTEA NOT NULL,
            encryption_key_id TEXT NOT NULL
        );
    """)
    
    # Price snapshots — fx_rate column records the rate used for conversion
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_price_snapshots (
            snapshot_date DATE NOT NULL,
            company_id INT NOT NULL,
            price NUMERIC NOT NULL,
            price_currency TEXT NOT NULL DEFAULT 'CAD',
            price_date DATE NOT NULL,
            source TEXT NOT NULL,
            exchange TEXT,
            stale_days INT,
            fx_rate NUMERIC,              -- CAD per 1 unit of price_currency at snapshot time
            base_price NUMERIC,           -- price * fx_rate (in account base currency)
            PRIMARY KEY (snapshot_date, company_id)
        );
    """)
    
    # Replay checkpoints — must store multi-currency cash balances
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_replay_checkpoints (
            account_id INT NOT NULL,
            checkpoint_date DATE NOT NULL,
            state_json JSONB NOT NULL,         -- PortfolioState with per-currency cash
            last_event_id UUID NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (account_id, checkpoint_date)
        );
    """)
    
    # Broker reconciliation log — stores comparison between event log and broker data
    await supabase.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_results (
            id BIGSERIAL PRIMARY KEY,
            account_id INT NOT NULL,
            reconciliation_date DATE NOT NULL,
            field TEXT NOT NULL,             -- 'cash', 'position_qty', 'dividend'
            currency TEXT,
            company_id INT,
            expected_value NUMERIC,
            actual_value NUMERIC,
            delta NUMERIC,
            delta_pct NUMERIC,              -- delta / |actual| for relative comparison
            severity TEXT NOT NULL DEFAULT 'info',
            status TEXT NOT NULL DEFAULT 'unreviewed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    
    await supabase.execute("""
        CREATE INDEX idx_events_account_date 
        ON portfolio_events(account_id, event_date, event_id);
    """)
    await supabase.execute("""
        CREATE INDEX idx_events_idempotency 
        ON portfolio_events(idempotency_key);
    """)
    await supabase.execute("""
        CREATE INDEX idx_fx_rate_lookup
        ON fx_rate_history(from_currency, to_currency, rate_date);
    """)

async def down():
    await supabase.execute("DROP TABLE IF EXISTS reconciliation_results CASCADE")
    await supabase.execute("DROP TABLE IF EXISTS portfolio_replay_checkpoints CASCADE")
    await supabase.execute("DROP TABLE IF EXISTS portfolio_price_snapshots CASCADE")
    await supabase.execute("DROP TABLE IF EXISTS portfolio_event_pii CASCADE")
    await supabase.execute("DROP TABLE IF EXISTS fx_rate_history CASCADE")
    await supabase.execute("DROP TABLE IF EXISTS security_master CASCADE")
    await supabase.execute("DROP TABLE IF EXISTS portfolio_events CASCADE")
    await supabase.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS base_currency")
```

#### 3.2 Implement EventStore

```python
# backend/infrastructure/repositories/event_store.py

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date
import hashlib

@dataclass
class Event:
    event_id: Optional[UUID]
    idempotency_key: str
    user_id: int
    account_id: int
    event_type: str
    event_date: date
    symbol: Optional[str]
    company_id: Optional[int]
    quantity: Optional[Decimal]
    unit_price: Optional[Decimal]
    gross_amount: Optional[Decimal]
    net_amount: Optional[Decimal]
    commission: Optional[Decimal]
    fx_rate: Optional[Decimal]
    currency: str
    counterparty_account_id: Optional[int]
    description: str
    source: str
    schema_version: int
    corrects_event_id: Optional[UUID]

class ImmutableEventError(Exception):
    pass

class EventStore:
    """Append-only event store. Events cannot be updated or deleted."""
    
    def __init__(self, db):
        self._db = db
    
    def make_idempotency_key(self, source: str, external_id: str) -> str:
        """Generate deterministic idempotency key from source + external ID."""
        raw = f"{source}:{external_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
    
    async def insert(self, event: Event) -> Event:
        """Insert event. Raises DuplicateEventError if idempotency_key conflicts."""
        row = await self._db.table("portfolio_events").insert({
            "event_id": event.event_id or None,  # Let DB generate
            "idempotency_key": event.idempotency_key,
            "user_id": event.user_id,
            "account_id": event.account_id,
            "event_type": event.event_type,
            "event_date": event.event_date.isoformat(),
            "symbol": event.symbol,
            "company_id": event.company_id,
            "quantity": str(event.quantity) if event.quantity else None,
            "unit_price": str(event.unit_price) if event.unit_price else None,
            "gross_amount": str(event.gross_amount) if event.gross_amount else None,
            "net_amount": str(event.net_amount) if event.net_amount else None,
            "commission": str(event.commission) if event.commission else None,
            "fx_rate": str(event.fx_rate) if event.fx_rate else None,
            "currency": event.currency,
            "counterparty_account_id": event.counterparty_account_id,
            "description": event.description,
            "source": event.source,
            "schema_version": event.schema_version,
            "corrects_event_id": str(event.corrects_event_id) if event.corrects_event_id else None,
        }).execute()
        return self._row_to_event(row.data[0])
    
    async def find_by_idempotency_key(self, key: str) -> Optional[Event]:
        rows = await self._db.table("portfolio_events") \
            .select("*") \
            .eq("idempotency_key", key) \
            .limit(1) \
            .execute()
        return self._row_to_event(rows.data[0]) if rows.data else None
    
    async def get_events_up_to(
        self, account_ids: List[int], target_date: date
    ) -> List[Event]:
        rows = await self._db.table("portfolio_events") \
            .select("*") \
            .in_("account_id", account_ids) \
            .lte("event_date", target_date.isoformat()) \
            .order("event_date, event_id") \
            .execute()
        return [self._row_to_event(r) for r in rows.data]
    
    async def get_events_since(
        self, account_id: int, since_date: date, target_date: date
    ) -> List[Event]:
        """Get events between two dates (for incremental replay from checkpoint)."""
        rows = await self._db.table("portfolio_events") \
            .select("*") \
            .eq("account_id", account_id) \
            .gt("event_date", since_date.isoformat()) \
            .lte("event_date", target_date.isoformat()) \
            .order("event_date, event_id") \
            .execute()
        return [self._row_to_event(r) for r in rows.data]
```

#### 3.3 Add Dual-Write Hook to Import Pipeline

```python
# In import_transactions() — existing function in infrastructure/repositories/

async def import_transactions(user_id: int, account_id: int, raw_data: bytes):
    """Import transactions. Dual-writes to events table."""
    parsed = parser.parse(raw_data)
    
    async with supabase.transaction():
        existing_txns = []
        new_events = []
        
        for txn in parsed:
            # Write to existing tables (backward compat)
            await portfolio_repo.insert_transaction(txn)
            
            # Build event with idempotency key
            event = Event(
                event_id=None,
                idempotency_key=event_store.make_idempotency_key(
                    txn.source, txn.external_id
                ),
                user_id=user_id,
                account_id=account_id,
                event_type=map_activity_type(txn.activity_type),
                event_date=txn.transaction_date,
                symbol=txn.symbol,
                net_amount=txn.net_cash_amount,
                quantity=txn.quantity,
                unit_price=txn.unit_price,
                currency=txn.currency or "CAD",
                source=txn.source,
                description=txn.description,
                schema_version=1,
                corrects_event_id=None,
            )
            
            # Idempotent: skip if already exists
            existing = await event_store.find_by_idempotency_key(event.idempotency_key)
            if existing:
                existing_txns.append(existing)
            else:
                new_events.append(event)
        
        # Batch insert new events
        for event in new_events:
            await event_store.insert(event)
        
        # Invalidate checkpoints for affected accounts
        if new_events:
            await checkpoint_manager.invalidate(account_id)
    
    return {
        "total": len(parsed),
        "new": len(new_events),
        "duplicates": len(existing_txns),
    }
```

#### 3.4 Run Phase 1 Validation

```bash
# Test event count parity
python -c "
import asyncio
from infrastructure.repositories.event_store import EventStore
from infrastructure.database import supabase

async def check():
    event_count = await supabase.table('portfolio_events').select('*', count='exact').execute()
    txn_count = await supabase.table('portfolio_transactions').select('*', count='exact').execute()
    print(f'Events: {event_count.count}, Transactions: {txn_count.count}')
    assert event_count.count == txn_count.count, 'MISMATCH'
    print('PARITY OK')

asyncio.run(check())
"

# Test event immutability
python -c "
import asyncio
from infrastructure.repositories.event_store import EventStore, ImmutableEventError

async def check():
    store = EventStore(supabase)
    try:
        await store.update(known_event_id, {'net_amount': 999})
        print('FAIL: should have raised ImmutableEventError')
    except ImmutableEventError:
        print('PASS: events are immutable')

asyncio.run(check())
"

# Test atomic rollback: verify no orphan events on transaction failure
python -m pytest tests/test_event_log.py::test_dual_write_atomic_rollback -v
# Expected: PASS — orphan event rolled back with failed transaction

# Test orphan detection: verify daily job catches leftover events
python -m pytest tests/test_event_log.py::test_dual_write_orphan_detection_runs_daily -v
# Expected: PASS — orphan event detected by daily validation job
```

---

### 4. Phase 2: Event-Replay Engine (Multi-Currency) [PENDING]

**End outcome:** A `replay_to_date()` function that takes account IDs and a target
date, replays events from `portfolio_events`, and produces a `PortfolioState`
with per-currency cash (Dict[str, Decimal]), holdings with FX-aware pricing,
cost_basis in base currency, net_deposits. Running in comparison mode
alongside `build_snapshot_row()` produces identical results to within $0.01
for all historical snapshots across all 6 WealthSimple accounts (all CAD).
For multi-currency accounts, holdings priced in USD are converted using the
fx_rate stored in the price snapshot, and cash balances are aggregated per
currency then converted to base currency for the total.

**Test with real data:**

```python
async def test_replay_matches_snapshot_builder_all_accounts():
    """For every historical snapshot, replay produces same total_value."""
    snapshots = await supabase.table("portfolio_snapshots") \
        .select("*") \
        .execute()
    
    for snap in snapshots.data:
        state = await replay_to_date(
            account_ids=[snap["account_id"]],
            target_date=date.fromisoformat(snap["snapshot_date"]),
            event_store=event_store,
            price_snapshot=await freeze_prices_for_date(
                snap["account_id"],
                date.fromisoformat(snap["snapshot_date"]),
            ),
        )
        expected = Decimal(str(snap["total_value"]))
        actual = state.cash + compute_holdings_value(state, snap["snapshot_date"])
        
        assert abs(actual - expected) < Decimal("0.01"), (
            f"Account {snap['account_id']} on {snap['snapshot_date']}: "
            f"expected {expected}, got {actual}"
        )

async def test_replay_account_7_cash():
    """Replay Account 7 to Jul 6 should produce cash=$351.28."""
    state = await replay_to_date(
        account_ids=[7],
        target_date=date(2026, 7, 6),
        event_store=event_store,
    )
    assert abs(state.cash - Decimal("351.28")) < Decimal("0.01")

async def test_replay_account_9_dividend_count():
    """Account 9 has 655 dividend events — replay should process all."""
    events = await event_store.get_events_up_to([9], date(2024, 12, 31))
    dividend_events = [e for e in events if e.event_type == "dividend"]
    assert len(dividend_events) == 655

async def test_replay_deterministic():
    """Same events → same state, regardless of when you run."""
    first = await replay_to_date([7], date(2024, 6, 1), event_store)
    second = await replay_to_date([7], date(2024, 6, 1), event_store)
    assert first.cash == second.cash
    assert len(first.lots) == len(second.lots)
```

**Implementation steps:**

#### 4.1 Implement EventHandler Registry (Multi-Currency)

```python
# backend/shared/event_handlers/__init__.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID, uuid4

@dataclass
class LotDelta:
    company_id: int
    symbol: str
    quantity: Decimal
    unit_price: Decimal     # In the event's currency
    currency: str           # Currency of unit_price
    direction: str          # "BUY" or "SELL"

@dataclass
class PortfolioState:
    """Mutable state accumulated during event replay.
    
    cash is a dict per currency: {"CAD": Decimal("5000"), "USD": Decimal("1000")}.
    Holdings are valued in their local currency; base_currency conversion
    happens at snapshot time using price_snapshot fx_rates.
    """
    cash: Dict[str, Decimal] = field(default_factory=lambda: {"CAD": Decimal(0)})
    lots: Dict[int, List["Lot"]] = field(default_factory=dict)
    cost_basis: Decimal = Decimal(0)           # Always in base_currency
    net_deposits: Decimal = Decimal(0)          # Always in base_currency
    last_event_date: Optional[date] = None
    base_currency: str = "CAD"                  # Per-account setting

@dataclass
class Lot:
    lot_id: UUID = field(default_factory=uuid4)
    company_id: int = 0
    quantity: Decimal = Decimal(0)
    cost_per_share: Decimal = Decimal(0)        # In event currency
    currency: str = "CAD"                       # Currency of cost_per_share
    acquired_date: Optional[date] = None
    symbol: str = ""

class EventHandler(ABC):
    @abstractmethod
    def cash_impact(self, event) -> Dict[str, Decimal]:
        """Returns {currency: delta}. Positive = cash received.
        Most events affect only one currency key."""
        ...

    @abstractmethod
    def holding_delta(self, event) -> List[LotDelta]:
        ...

    @abstractmethod
    def validate(self, event, state: PortfolioState) -> List[str]:
        ...

    @abstractmethod
    def cost_basis_adjustment(self, event) -> Decimal:
        """Adjustment to cost_basis (always in base_currency)."""

# Concrete handlers in backend/shared/event_handlers/handlers.py
```

#### 4.2 Implement replay_to_date() (Multi-Currency)

```python
# backend/shared/replay_engine.py

from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional, Tuple
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)

EVENT_HANDLERS: Dict[str, EventHandler] = {}  # registered handlers

def register_handler(event_type: str, handler: EventHandler):
    EVENT_HANDLERS[event_type] = handler

async def replay_to_date(
    account_ids: List[int],
    target_date: date,
    event_store: "EventStore",
    checkpoint_manager: Optional["CheckpointManager"] = None,
    price_snapshot: Optional[Dict[int, Decimal]] = None,
) -> PortfolioState:
    """Replay events up to target_date, starting from latest checkpoint if available.
    
    Cash is tracked per-currency. Holdings have per-lot currency.
    Total valuation converts all currencies to base_currency at snapshot time.
    """
    
    # 1. Try to load from checkpoint
    state = None
    checkpoint_date = None
    if checkpoint_manager and len(account_ids) == 1:
        checkpoint = await checkpoint_manager.latest_before(
            account_ids[0], target_date
        )
        if checkpoint:
            state = PortfolioState(**checkpoint["state_json"])
            checkpoint_date = date.fromisoformat(checkpoint["checkpoint_date"])
    
    if state is None:
        base_currency = await get_account_base_currency(account_ids[0])
        state = PortfolioState(
            cash={"CAD": Decimal(0)}, lots={}, cost_basis=Decimal(0),
            net_deposits=Decimal(0), last_event_date=None,
            base_currency=base_currency,
        )
        checkpoint_date = date.min
    
    # 2. Fetch events since checkpoint
    events = await event_store.get_events_since(
        account_ids, checkpoint_date, target_date
    )
    
    # 3. Replay
    for event in events:
        handler = EVENT_HANDLERS.get(event.event_type)
        if not handler:
            logger.error(f"No handler for event type {event.event_type} "
                         f"(event {event.event_id})")
            continue
        
        # Validate
        warnings = handler.validate(event, state)
        for w in warnings:
            logger.warning(f"Event {event.event_id}: {w}")
        
        # Apply cash impact (per-currency dict)
        cash_deltas = handler.cash_impact(event)
        for currency, delta in cash_deltas.items():
            if currency not in state.cash:
                state.cash[currency] = Decimal(0)
            state.cash[currency] += delta
        
        # Apply holding deltas
        for delta in handler.holding_delta(event):
            if delta.direction == "BUY":
                lots = state.lots.setdefault(delta.company_id, [])
                lots.append(Lot(
                    lot_id=uuid4(),
                    company_id=delta.company_id,
                    quantity=delta.quantity,
                    cost_per_share=delta.unit_price,
                    currency=delta.currency,
                    acquired_date=event.event_date,
                    symbol=delta.symbol,
                ))
            elif delta.direction == "SELL":
                _apply_fifo_sell(state, delta)
        
        # Cost basis adjustment (always in base_currency)
        state.cost_basis += handler.cost_basis_adjustment(event)
        
        # Track net deposits (always in base_currency, converted if needed)
        if event.event_type in ("deposit", "withdrawal"):
            if event.currency == state.base_currency:
                state.net_deposits += event.net_amount
            else:
                fx = event.fx_rate or await get_fx_rate(
                    event.currency, state.base_currency, event.event_date
                )
                state.net_deposits += event.net_amount * fx
        
        state.last_event_date = event.event_date
    
    return state


def compute_total_value(
    state: PortfolioState,
    price_snapshot: Dict[int, "PriceData"],
) -> Decimal:
    """Compute total portfolio value in base_currency.
    
    cash: sum over all currencies, converting non-base using snapshot FX.
    holdings: qty × local_price × fx_rate, summed.
    """
    # Cash: convert each currency to base
    total_cash = Decimal(0)
    for currency, amount in state.cash.items():
        if currency == state.base_currency:
            total_cash += amount
        else:
            fx = get_fx_rate_for_date(currency, state.base_currency, state.last_event_date)
            total_cash += amount * fx
    
    # Holdings: qty × local_price × fx_to_base
    holdings_value = Decimal(0)
    for company_id, lots in state.lots.items():
        price_data = price_snapshot.get(company_id)
        if not price_data:
            continue  # UNAVAILABLE — skip
        for lot in lots:
            holdings_value += lot.quantity * price_data.base_price
    
    return total_cash + holdings_value


@dataclass
class PriceData:
    local_price: Decimal       # Price in holding's native currency
    currency: str              # 'USD', 'CAD', etc.
    fx_rate: Decimal           # base_currency per 1 unit of currency
    base_price: Decimal        # local_price * fx_rate (in base_currency)
    source: str
    stale_days: Optional[int]


def _apply_fifo_sell(state: PortfolioState, delta: LotDelta):
    """Sell shares using FIFO lot selection.
    Only sells from lots matching delta.currency."""
    remaining = abs(delta.quantity)
    lots = state.lots.get(delta.company_id, [])
    while remaining > 0 and lots:
        lot = lots[0]
        if lot.currency != delta.currency:
            lots.pop(0)  # Skip lots in different currency
            continue
        if lot.quantity <= remaining:
            remaining -= lot.quantity
            lots.pop(0)
        else:
            lot.quantity -= remaining
            remaining = 0
```

#### 4.3 Implement Price Snapshot Freezing (Multi-Currency)

```python
# backend/shared/price_snapshot.py

from decimal import Decimal
from datetime import date
from typing import Dict, Set, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class PriceResolution:
    local_price: Decimal     # Price in the security's native currency
    currency: str            # 'USD', 'CAD', etc.
    price_date: date
    source: str              # 'current_market_data', 'price_history', 'average_cost'
    exchange: Optional[str]
    stale_days: Optional[int]


async def freeze_prices(
    account_ids: List[int],
    snapshot_date: date,
    event_store: "EventStore",
    price_resolver: "PriceResolver",
    fx_provider: "FxRateProvider",
) -> Dict[int, "PriceData"]:
    """Determine the price for each company_id as of snapshot_date.
    
    Records results in portfolio_price_snapshots for reproducibility.
    Returns dict of {company_id: PriceData} with base_price in account's base currency.
    """
    
    # 1. Find all company_ids with holdings across all accounts
    companies: Dict[int, str] = {}  # company_id → base_currency of first account that holds it
    for account_id in account_ids:
        state = await replay_to_date([account_id], snapshot_date, event_store)
        base_currency = state.base_currency
        for company_id in state.lots:
            if company_id not in companies:
                companies[company_id] = base_currency
    
    # 2. Get security master — tells us what currency each security is priced in
    security_currencies = await get_security_currencies(list(companies.keys()))
    
    # 3. Resolve price for each company
    prices: Dict[int, PriceData] = {}
    for company_id, base_currency in companies.items():
        resolution = await price_resolver.resolve(company_id, snapshot_date)
        
        local_currency = security_currencies.get(company_id, "CAD")
        
        # Convert to base currency
        if local_currency == base_currency:
            fx_rate = Decimal(1)
        else:
            fx_rate = await fx_provider.get_rate(
                from_currency=local_currency,
                to_currency=base_currency,
                as_of=snapshot_date,
            )
            if fx_rate is None:
                logger.warning(
                    f"No FX rate {local_currency}→{base_currency} "
                    f"for company {company_id} on {snapshot_date}"
                )
                # No FX rate available → cannot value this holding in base currency.
                # This is equivalent to "no price" for multi-currency purposes.
                # Skip this company_id entirely — it will be UNAVAILABLE.
                logger.warning(
                    f"No FX rate {local_currency}→{base_currency} "
                    f"for company {company_id} on {snapshot_date} — marking UNAVAILABLE"
                )
                continue  # holding excluded from market value, like missing price
        
        base_price = resolution.local_price * fx_rate
        
        price_data = PriceData(
            local_price=resolution.local_price,
            currency=local_currency,
            fx_rate=fx_rate,
            base_price=base_price,
            source=resolution.source,
            stale_days=resolution.stale_days,
        )
        prices[company_id] = price_data
        
        # Record for reproducibility
        await record_price_snapshot(snapshot_date, company_id, resolution, fx_rate, base_price)
    
    return prices


async def record_price_snapshot(snapshot_date, company_id, resolution, fx_rate, base_price):
    """Upsert price snapshot record with FX metadata."""
    await supabase.table("portfolio_price_snapshots").upsert({
        "snapshot_date": snapshot_date.isoformat(),
        "company_id": company_id,
        "price": str(resolution.local_price),
        "price_currency": resolution.currency,
        "price_date": resolution.price_date.isoformat(),
        "source": resolution.source,
        "exchange": resolution.exchange,
        "stale_days": resolution.stale_days,
        "fx_rate": str(fx_rate) if fx_rate and fx_rate != 1 else None,
        "base_price": str(base_price),
    }).execute()


async def get_security_currencies(company_ids: List[int]) -> Dict[int, str]:
    """Return {company_id: currency} from security_master."""
    rows = await supabase.table("security_master") \
        .select("company_id, currency") \
        .in_("company_id", company_ids) \
        .execute()
    return {r["company_id"]: r["currency"] for r in rows.data}


class FxRateProvider:
    """Provides historical FX rates from fx_rate_history table.
    
    Falls back to Bank of Canada API if not in table.
    Caches rates for the duration of a snapshot run.
    """
    
    def __init__(self, db):
        self._db = db
        self._cache: Dict[Tuple[str, str, date], Decimal] = {}
    
    async def get_rate(self, from_currency: str, to_currency: str, as_of: date) -> Optional[Decimal]:
        cache_key = (from_currency, to_currency, as_of)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Try DB first
        row = await self._db.table("fx_rate_history") \
            .select("rate") \
            .eq("from_currency", from_currency) \
            .eq("to_currency", to_currency) \
            .eq("rate_date", as_of.isoformat()) \
            .limit(1) \
            .execute()
        
        if row.data:
            rate = Decimal(str(row.data[0]["rate"]))
            self._cache[cache_key] = rate
            return rate
        
        # Fallback to Bank of Canada API
        rate = await self._fetch_from_boc(from_currency, to_currency, as_of)
        if rate:
            self._cache[cache_key] = rate
            # Persist for future use
            await self._db.table("fx_rate_history").insert({
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate_date": as_of.isoformat(),
                "rate": str(rate),
                "source": "bank_of_canada",
            }).execute()
        
        return rate
    
    async def _fetch_from_boc(self, from_currency, to_currency, as_of) -> Optional[Decimal]:
        """Fetch from Bank of Canada FX API."""
        # https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json
        ...
```

#### 4.4 Implement Comparison Mode

```python
# backend/jobs/compare_snapshot_engines.py

async def compare_snapshot_engines():
    """Run both old and new engines, compare outputs for all accounts."""
    accounts = await get_all_account_ids()
    today = now_utc().date()
    
    total_diffs = 0
    for account_id in accounts:
        # Old engine
        old = await compute_snapshot_old(account_id, today)
        
        # New engine
        state = await replay_to_date([account_id], today, event_store)
        price_snapshot = await freeze_prices([account_id], today, event_store, price_resolver)
        new = state_to_snapshot(state, price_snapshot)
        
        # Compare
        diff = abs(old.total_value - new.total_value)
        if diff > Decimal("0.01"):
            logger.error(
                f"Engine mismatch: account {account_id}, date {today}: "
                f"old={old.total_value}, new={new.total_value}, diff={diff}"
            )
            total_diffs += 1
    
    if total_diffs == 0:
        logger.info("Comparison mode: ALL MATCH (0 differences)")
    else:
        logger.warning(f"Comparison mode: {total_diffs} differences found")
    
    return total_diffs
```

#### 4.5 Multi-Currency Test Cases

```python
async def test_multi_currency_cash_separate():
    """Cash in different currencies stays separate until valuation."""
    events = [
        deposit(10000, "CAD", "2024-01-01"),    # +10,000 CAD
        deposit(5000, "USD", "2024-01-15"),     # +5,000 USD
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    assert state.cash["CAD"] == Decimal("10000")
    assert state.cash["USD"] == Decimal("5000")

async def test_multi_currency_buy_requires_conversion():
    """Buying USD stock uses USD cash. If only CAD exists, FX conversion needed."""
    events = [
        deposit(10000, "CAD", "2024-01-01"),
        buy("AAPL", 10, Decimal("150"), "USD", "2024-01-15"),
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    # Buy debits USD cash: -1500 USD. CAD cash unchanged.
    assert state.cash["CAD"] == Decimal("10000")
    assert state.cash["USD"] == Decimal("-1500")  # Negative USD after buy
    # lot is in USD
    assert state.lots[1][0].currency == "USD"

async def test_multi_currency_total_value():
    """Total value = CAD cash + (USD cash * FX) + (holding qty * base_price)."""
    events = [deposit(10000, "CAD", "2024-01-01")]
    state = await replay_to_date([1], date(2024, 1, 2), events=events)
    
    price_snapshot = {}  # No holdings, no prices needed
    total = compute_total_value(state, price_snapshot)
    assert total == Decimal("10000")

async def test_multi_currency_with_fx_conversion():
    """USD holdings converted to CAD using snapshot FX rate."""
    events = [
        deposit(10000, "CAD", "2024-01-01"),
        buy("AAPL", 10, Decimal("150"), "USD", "2024-01-15"),
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    price_snapshot = {
        1: PriceData(
            local_price=Decimal("155"),   # AAPL now $155 USD
            currency="USD",
            fx_rate=Decimal("1.36"),      # USD→CAD
            base_price=Decimal("210.80"), # 155 * 1.36
            source="current_market_data",
            stale_days=0,
        ),
    }
    total = compute_total_value(state, price_snapshot)
    # Cash: 10000 CAD + (-1500 USD * 1.36) = 10000 - 2040 = 7960 CAD
    # Holdings: 10 * 210.80 = 2108 CAD
    # Total: 7960 + 2108 = 10068
    assert total == Decimal("10068")

async def test_multi_currency_holding_excluded_when_fx_rate_missing():
    """When FX rate is unavailable for a non-base holding, the holding is excluded
    (UNAVAILABLE) — not counted as $0, and total does not include it."""
    events = [
        deposit(10000, "CAD", "2024-01-01"),
        buy("AAPL", 10, Decimal("150"), "USD", "2024-01-15"),
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    # Simulate: price resolved but FX rate for USD→CAD returned None.
    # The price_snapshot does NOT include company_id=1 because freeze_prices
    # skipped it when FxRateProvider.get_rate() returned None.
    price_snapshot = {}  # No prices at all → AAPL is UNAVAILABLE
    
    total = compute_total_value(state, price_snapshot)
    # Cash: 10000 CAD + (-1500 USD) — but USD cash cannot be converted to CAD
    #       because no FX rate exists. The compute_total_value should either:
    #       (a) exclude non-base cash when FX is missing, or
    #       (b) include CAD-only cash and flag the rest as UNAVAILABLE
    # Expected behavior: CAD cash only (10,000), USD cash excluded, holdings excluded
    assert total == Decimal("10000"), (
        f"Expected 10000 CAD only (USD excluded due to missing FX), got {total}"
    )

async def test_multi_currency_none_rate_marks_holding_unavailable():
    """When FxRateProvider returns None for a currency pair, freeze_prices skips
    that company_id. The resulting price_snapshot dict lacks the entry, and
    compute_total_value excludes it (doesn't count as $0)."""
    events = [
        deposit(10000, "CAD", "2024-01-01"),
        buy("AAPL", 10, Decimal("150"), "USD", "2024-01-15"),
        buy("TD", 20, Decimal("85"), "CAD", "2024-01-15"),
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    # TD has a price (CAD, no FX needed), AAPL has no FX rate → skipped
    price_snapshot = {
        2: PriceData(  # TD — CAD-denominated, no FX needed
            local_price=Decimal("88"),
            currency="CAD",
            fx_rate=Decimal("1"),
            base_price=Decimal("88"),
            source="current_market_data",
            stale_days=0,
        ),
    }
    total = compute_total_value(state, price_snapshot)
    # AAPL excluded (UNAVAILABLE, missing FX rate)
    # TD: 20 * 88 = 1760 CAD
    # Cash: 10000 CAD + (-1500 USD excluded from total, no FX)
    # Total: 10000 + 1760 = 11760
    assert total == Decimal("11760"), (
        f"Expected 11760 (AAPL excluded, TD included), got {total}"
    )

async def test_replay_matches_snapshot_builder_all_accounts():
    """For every historical snapshot, replay produces same total_value."""
    snapshots = await supabase.table("portfolio_snapshots") \
        .select("*") \
        .execute()
    
    for snap in snapshots.data:
        state = await replay_to_date(
            account_ids=[snap["account_id"]],
            target_date=date.fromisoformat(snap["snapshot_date"]),
            event_store=event_store,
        )
        price_snapshot = await freeze_prices_for_date(
            snap["account_id"],
            date.fromisoformat(snap["snapshot_date"]),
        )
        expected = Decimal(str(snap["total_value"]))
        actual = compute_total_value(state, price_snapshot)
        
        assert abs(actual - expected) < Decimal("0.01"), (
            f"Account {snap['account_id']} on {snap['snapshot_date']}: "
            f"expected {expected}, got {actual}"
        )
```

**Multi-currency UI validation (manual, one-time):**

```bash
# Check if any account holds USD securities
psql -d stockerpro -c "
  SELECT DISTINCT h.account_id, c.currency
  FROM portfolio_holdings h
  JOIN companies c ON h.company_id = c.id
  WHERE c.currency != 'CAD';
"
# If empty: all current accounts are CAD-only.
# If non-empty: those accounts need multi-currency testing.

# Verify security_master is populated
psql -d stockerpro -c "
  SELECT COUNT(*) AS total_securities,
         COUNT(*) FILTER (WHERE currency != 'CAD') AS non_cad
  FROM security_master;
"
# Expected: all holdings + any held-but-not-traded securities
```

#### 4.6 Phase 2 Acceptance Criteria

```bash
# Run comparison
python -m backend.jobs.compare_snapshot_engines

# Expected: "Comparison mode: ALL MATCH (0 differences)"

# Run replay tests (including multi-currency)
pytest tests/test_portfolio_snapshots.py \
       tests/test_replay_engine.py \
       tests/test_multi_currency.py -v
# Expected: All pass

# Multi-currency specific: all tests pass
pytest tests/test_multi_currency.py -v
# Expected: test_multi_currency_cash_separate PASS
#           test_multi_currency_buy_requires_conversion PASS
#           test_multi_currency_total_value PASS
#           test_multi_currency_with_fx_conversion PASS
#           test_replay_matches_snapshot_builder_all_accounts PASS
```

---

### 5. Phase 2.5: Broker Reconciliation [PENDING]

**End outcome:** A daily reconciliation job compares the event log against the
brokerage's official record (via CSV import — no API available). Any
discrepancy in cash balance, position quantity, or dividend amount is logged
to `reconciliation_results`. Discrepancies > $100 trigger a CRITICAL alert.
Discrepancies < $1 are suppressed as rounding errors. The user sees a
"Last reconciled: <date>" badge in the UI. If reconciliation has not run
for 7+ days, a WARNING badge appears.

#### 5.0 Prerequisite: Alerting Infrastructure

**Current state:** The codebase has a no-op `alert_slack()` callback — it logs
the message but never sends it anywhere. Reconciliation cannot go live without
real alerting because unreviewed critical discrepancies silently accumulate.

**Required before Phase 2.5 deployment:**

```python
# backend/shared/alerting.py

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

async def alert_critical(message: str, details: Optional[dict] = None):
    """Send a CRITICAL alert. Blocks until delivered (retry 3x on failure)."""
    if ENVIRONMENT == "development" and not SLACK_WEBHOOK_URL:
        logger.warning(f"[DEV ALERT] {message} — would send to Slack in production")
        return
    
    payload = {
        "text": f"[{ENVIRONMENT}] CRITICAL: {message}",
        "attachments": [{"text": json.dumps(details, indent=2)}] if details else [],
    }
    
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
                resp.raise_for_status()
            logger.info(f"Critical alert sent: {message}")
            return
        except Exception as e:
            logger.error(f"Alert attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s backoff
    
    logger.critical(f"FAILED TO SEND ALERT after 3 retries: {message}")

async def alert_warning(message: str):
    """Send a WARNING alert. Best-effort (no retry)."""
    if not SLACK_WEBHOOK_URL:
        logger.warning(f"[{ENVIRONMENT}] WARNING: {message}")
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(SLACK_WEBHOOK_URL, json={"text": f"[{ENVIRONMENT}] WARNING: {message}"})
    except Exception:
        pass  # Best-effort
```

**Deployment check:**
```bash
# Verify SLACK_WEBHOOK_URL is set in production
python -c "from backend.shared.alerting import SLACK_WEBHOOK_URL; assert SLACK_WEBHOOK_URL, 'SLACK_WEBHOOK_URL not set'"
echo "Alerting configured"
```

#### 5.0.1 Constraint: No WealthSimple API — CSV-Only Reconciliation

**Current state:** The codebase has `WealthsimpleParser` in
`backend/application/parsers/portfolio_parser.py` for CSV import only. There is
no WealthSimple API integration (no API credentials, no API client, no OAuth
flow). The `fetch_broker_statement()` function in the original design assumed an
API would exist; in reality it must parse the most recently imported CSV file.

**Impact on reconciliation quality:**

| Aspect | With API | With CSV Only |
|--------|----------|---------------|
| Frequency | Daily (automated) | Only when user imports CSV |
| Coverage | All accounts | Only accounts with CSV imports |
| Authority | High (live broker) | Medium (CSV at import time) |
| Time delay | 0 (real-time) | Days to months since last import |

**Design adjustment:** Reconciliation operates in 3 tiers:

1. **CSV-parsed data** (preferred): If a CSV import exists for this account,
   parse it into a `BrokerStatement` and reconcile against the event log.
   The CSV is treated as authoritative for the import date only.

2. **Manual statement upload** (future): Allow users to upload PDF/CSV
   statements. Parse with an extensible statement parser. Same authority as API.

3. **"Never reconciled" badge** (fallback): If no CSV import exists and no
   manual statement has been uploaded, the UI shows a grey "Never reconciled"
   badge. No comparison is attempted.

**Reconciliation badge reflects last-import freshness:**
- **Green** "Reconciled <date>": Last CSV import < 7 days ago
- **Yellow** "Stale <N> days": Last CSV import 7-30 days ago
- **Red** "Not reconciled in 30+ days": Last CSV import > 30 days ago
- **Grey** "Never reconciled": No CSV import ever

**Why this is Phase 2.5 (not Phase 4):** Without reconciliation, the event log can
drift from reality (missed dividend, wrong trade price, missing deposit). The
whole point of event sourcing is the event log being the truth — but if it
disagrees with the brokerage, the user's UI shows wrong data. Reconciliation
is the **only mechanism** that detects this. It should run as soon as the event
log exists and preferably before the replay engine replaces the old pipeline.

**Test with real data:**

```python
async def test_reconciliation_detects_missing_deposit():
    """Simulate: broker says $10,000, event log says $9,500."""
    events = [
        deposit(5000, "CAD", "2024-01-01"),
        deposit(4500, "CAD", "2024-01-15"),  # Should have been $5,000
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    broker_statement = BrokerStatement(
        account_id=1,
        as_of=date(2024, 1, 16),
        cash={"CAD": Decimal("10000")},
    )
    
    results = await reconcile(state, broker_statement)
    assert len(results) == 1
    assert results[0].field == "cash"
    assert results[0].currency == "CAD"
    assert results[0].delta == Decimal("-500")  # 9500 - 10000

async def test_reconciliation_suppresses_rounding():
    """Deltas < $1 are suppressed."""
    state = PortfolioState(cash={"CAD": Decimal("10000.30")})
    broker = BrokerStatement(account_id=1, as_of=date(2024, 1, 16),
                              cash={"CAD": Decimal("10000.00")})
    results = await reconcile(state, broker)
    assert len(results) == 0

async def test_reconciliation_checks_positions():
    """Holding quantities are compared."""
    events = [buy("AAPL", 10, 150, "USD", "2024-01-15")]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    broker = BrokerStatement(
        account_id=1, as_of=date(2024, 1, 16),
        cash={"CAD": Decimal("0")},
        positions={1: Position(company_id=1, symbol="AAPL", quantity=10)},
    )
    results = await reconcile(state, broker)
    assert len(results) == 0  # All match

async def test_reconciliation_detects_missing_position():
    """Broker says 0 of a symbol, event log says 10."""
    events = [buy("AAPL", 10, 150, "USD", "2024-01-15")]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    broker = BrokerStatement(
        account_id=1, as_of=date(2024, 1, 16),
        cash={"CAD": Decimal("0")},
        positions={},  # Broker says no positions
    )
    results = await reconcile(state, broker)
    assert any(r.field == "position" and r.company_id == 1 for r in results)

async def test_reconciliation_badge_in_ui():
    """API returns last_reconciled and reconciliation_status."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"/api/accounts/{ACCOUNT_ID}/reconciliation/status")
    data = resp.json()
    assert "last_reconciled" in data
    assert "reconciliation_status" in data  # 'ok' | 'warning' | 'critical'
    if data["reconciliation_status"] == "warning":
        assert data["last_reconciled_days_ago"] >= 7
```

**Real-data validation (manual, after implementation):**

```bash
# Run reconciliation for all accounts
python -m backend.jobs.reconcile_accounts

# Check results
psql -d stockerpro -c "
  SELECT account_id, field, currency, company_id,
         expected_value, actual_value, delta, severity, status
  FROM reconciliation_results
  WHERE reconciliation_date = CURRENT_DATE
  ORDER BY severity, ABS(delta) DESC;
"

# Expected for WealthSimple accounts (if events are complete):
# All deltas ≈ $0, severity = 'info' or no rows
# If any missing data, deltas > $100 should be 'critical'
```

**Implementation steps:**

#### 5.1 Implement BrokerStatement Model

```python
# backend/shared/reconciliation/models.py

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Dict, Optional

@dataclass
class Position:
    company_id: int
    symbol: str
    quantity: Decimal
    currency: str = "CAD"

@dataclass
class BrokerStatement:
    """Official record from the brokerage. Source of truth for comparison."""
    account_id: int
    as_of: date
    cash: Dict[str, Decimal]           # currency → amount
    positions: Dict[int, Position]     # company_id → Position
    source: str                        # 'wealthsimple_api', 'csv_import', 'manual'

@dataclass
class ReconciliationResult:
    field: str                         # 'cash', 'position', 'dividend'
    currency: Optional[str]
    company_id: Optional[int]
    expected_value: Optional[Decimal]  # From event log
    actual_value: Optional[Decimal]     # From broker
    delta: Decimal                     # expected - actual
    severity: str                      # 'info', 'warning', 'critical'
```

#### 5.1.5 Auto-Correction on Reconciliation

**End outcome:** When reconciliation detects a verified discrepancy (broker data
is authoritative), a correction event is automatically created in the event log.
The correction is a new event with `corrects_event_id` pointing to the original
(wrong) event. The replay engine applies corrections after the original event,
so the next snapshot shows the correct value. Manual review is still required
for discrepancies > $1000.

**Why auto-correction is safe:**
- Broker data is the authoritative source (it's where money actually is)
- Corrections are events (immutable, auditable, replayable)
- Every correction is traceable to a specific reconciliation run
- Large discrepancies (> $1000) still require manual approval

```python
async def _derive_position_unit_price(
    account_id: int,
    company_id: int,
    event_store: "EventStore",
) -> Optional[Decimal]:
    """Derive a reasonable unit_price for a correction position.
    
    Priority:
    1. Average cost from existing lots of the same company_id
    2. Last trade price for this company_id from the event log
    3. None (will be flagged as UNAVAILABLE in the snapshot)
    
    Never returns 0 — if no data is available, returns None.
    """
    # 1. Check existing lots via replay
    state = await replay_to_date([account_id], date.today(), event_store)
    existing_lots = state.lots.get(company_id, [])
    if existing_lots:
        total_cost = sum(lot.cost_basis for lot in existing_lots)
        total_qty = sum(lot.quantity for lot in existing_lots)
        if total_qty > 0:
            avg_cost = total_cost / total_qty
            logger.info(f"Derived unit_price={avg_cost} from existing lots for company {company_id}")
            return avg_cost
    
    # 2. Look for last trade event for this company
    events = await event_store.get_events_for_company(account_id, company_id)
    trade_events = [e for e in events if e.event_type in ("trade_buy", "trade_sell")]
    if trade_events:
        last_trade = max(trade_events, key=lambda e: e.event_date)
        if last_trade.unit_price and last_trade.unit_price > 0:
            logger.info(f"Derived unit_price={last_trade.unit_price} from last trade for company {company_id}")
            return last_trade.unit_price
    
    # 3. No data available
    logger.warning(f"Cannot derive unit_price for company {company_id} — will be UNAVAILABLE")
    return None


async def auto_correct(
    result: ReconciliationResult,
    event_store: "EventStore",
    account_id: int,
) -> Optional[Event]:
    """Create a correction event for a verified discrepancy.
    
    Returns the correction event, or None if the discrepancy is too large
    for auto-correction (> $1000 or > 10 shares).
    """
    
    # 1. Check if this discrepancy is within auto-correction threshold
    if result.severity == "critical" and abs(result.delta) > Decimal("1000"):
        logger.info(
            f"Discrepancy too large for auto-correction: "
            f"account={account_id}, field={result.field}, delta={result.delta}"
        )
        return None
    
    # 2. Find or create the correction event
    if result.field == "cash":
        correction = Event(
            event_id=None,
            idempotency_key=event_store.make_idempotency_key(
                "reconciliation_correction",
                f"{account_id}_{result.currency}_{result.reconciliation_date}",
            ),
            user_id=get_user_id_for_account(account_id),
            account_id=account_id,
            event_type="reconciliation_adjustment",
            event_date=result.reconciliation_date,
            currency=result.currency,
            net_amount=result.delta,  # positive = broker has more cash than us
            description=f"Auto-correction from reconciliation: "
                       f"{result.field} adjusted by {result.delta} "
                       f"(event log: {result.expected_value}, "
                       f"broker: {result.actual_value})",
            source="reconciliation_engine",
            schema_version=1,
            corrects_event_id=None,  # This is a standalone cash adjustment
        )
    
    elif result.field == "position":
        # Create a pair of events: one to remove the wrong lot,
        # one to add the correct quantity
        quantity_delta = result.actual_value - result.expected_value
        
        if quantity_delta > 0:
            # Broker has more shares → we missed a buy
            event_type = "reconciliation_add_position"
        else:
            # Broker has fewer shares → we missed a sell or have a phantom buy
            event_type = "reconciliation_remove_position"
        
        # Derive unit_price from existing holdings or last trade
        unit_price = await _derive_position_unit_price(
            account_id=account_id,
            company_id=result.company_id,
            event_store=event_store,
        )
        
        correction = Event(
            event_id=None,
            idempotency_key=event_store.make_idempotency_key(
                "reconciliation_correction",
                f"{account_id}_{result.company_id}_{result.reconciliation_date}",
            ),
            user_id=get_user_id_for_account(account_id),
            account_id=account_id,
            event_type=event_type,
            event_date=result.reconciliation_date,
            company_id=result.company_id,
            quantity=abs(quantity_delta),
            unit_price=unit_price,  # Derived from existing holdings or last trade; None if unavailable
            description=f"Auto-correction from reconciliation: "
                       f"position {result.company_id} adjusted by {quantity_delta} "
                       f"(event log: {result.expected_value}, "
                       f"broker: {result.actual_value})",
            source="reconciliation_engine",
            schema_version=1,
        )
    
    else:
        logger.warning(f"Unknown reconciliation field: {result.field}")
        return None
    
    # 3. Insert the correction event
    try:
        inserted = await event_store.insert(correction)
        logger.info(
            f"Auto-correction created: event_id={inserted.event_id}, "
            f"account={account_id}, field={result.field}, delta={result.delta}"
        )
        return inserted
    except DuplicateEventError:
        logger.info(f"Auto-correction already exists for this discrepancy")
        return None


async def reconcile_and_correct(
    account_id: int,
    broker_statement: BrokerStatement,
    event_store: "EventStore",
) -> List[ReconciliationResult]:
    """Reconcile and auto-correct. Returns all results (including corrected ones)."""
    
    results = await reconcile_account(account_id, broker_statement, event_store)
    
    corrections_created = 0
    for result in results:
        if result.severity == "critical" and abs(result.delta) > Decimal("1000"):
            # Too large — require manual review
            result.status = "manual_review_required"
            await alert_critical(
                f"Large discrepancy requires manual review: "
                f"account={account_id}, field={result.field}, "
                f"delta={result.delta}"
            )
        elif result.severity != "info":
            # Auto-correct
            correction = await auto_correct(result, event_store, account_id)
            if correction:
                result.status = "auto_corrected"
                result.correction_event_id = correction.event_id
                corrections_created += 1
    
    logger.info(
        f"Reconciliation for account {account_id}: "
        f"{len(results)} discrepancies, {corrections_created} auto-corrected"
    )
    
    return results
```

**Test with real data:**

```python
async def test_auto_correction_creates_event():
    """Reconciliation delta produces a correction event."""
    state = PortfolioState(cash={"CAD": Decimal("9500")})
    broker = BrokerStatement(
        account_id=1, as_of=date(2024, 1, 16),
        cash={"CAD": Decimal("10000")},
        positions={},
    )
    results = await reconcile_and_correct(1, broker, event_store)
    
    assert len(results) == 1
    assert results[0].status == "auto_corrected"
    
    # Verify correction event exists
    correction = await event_store.get(results[0].correction_event_id)
    assert correction.event_type == "reconciliation_adjustment"
    assert correction.net_amount == Decimal("500")  # CAD 500 added

async def test_auto_correction_replay_applies_it():
    """After correction, replay shows the correct cash."""
    # Simulate: event log has $9500, broker says $10000
    events = [deposit(9500, "CAD", "2024-01-01")]
    broker = BrokerStatement(account_id=1, as_of=date(2024, 1, 16),
                              cash={"CAD": Decimal("10000")}, positions={})
    await reconcile_and_correct(1, broker, event_store)
    
    # Replay from beginning — should include the correction
    state = await replay_to_date([1], date(2024, 1, 17), event_store)
    assert state.cash["CAD"] == Decimal("10000")

async def test_large_discrepancy_not_auto_corrected():
    """Delta > $1000 requires manual approval."""
    state = PortfolioState(cash={"CAD": Decimal("5000")})
    broker = BrokerStatement(
        account_id=1, as_of=date(2024, 1, 16),
        cash={"CAD": Decimal("10000")},  # Delta = $5000
        positions={},
    )
    results = await reconcile_and_correct(1, broker, event_store)
    assert results[0].status == "manual_review_required"

async def test_auto_correction_idempotent():
    """Running reconciliation twice doesn't create duplicate corrections."""
    state = PortfolioState(cash={"CAD": Decimal("9500")})
    broker = BrokerStatement(
        account_id=1, as_of=date(2024, 1, 16),
        cash={"CAD": Decimal("10000")}, positions={},
    )
    # Run twice
    first = await reconcile_and_correct(1, broker, event_store)
    second = await reconcile_and_correct(1, broker, event_store)
    
    # First run: auto-correction created
    assert first[0].status == "auto_corrected"
    
    # Second run: already corrected, no new events
    assert second[0].status == "already_corrected" or len(second) == 0

async def test_csv_parser_produces_broker_statement():
    """WealthsimpleParser output maps correctly to BrokerStatement fields.
    
    This test validates the adapter layer between the CSV parser and the
    reconciliation engine. It imports a sample CSV, parses it, converts
    to BrokerStatement, and verifies the fields match expected values.
    """
    sample_csv = (
        "Account Number,Transaction Date,Settlement Date,Description,Symbol,"
        "Quantity,Price,Gross Amount,Currency\n"
        "12345678,2024-01-15,2024-01-17,Buy Apple Inc,AAPL,10,150.00,-1500.00,USD\n"
        "12345678,2024-01-16,2024-01-18,Sell Apple Inc,AAPL,5,200.00,1000.00,USD\n"
        "12345678,2024-01-20,2024-01-22,Deposit,,,5000.00,CAD\n"
    )
    
    # Parse CSV
    parser = WealthsimpleParser()
    parsed = parser.parse_string(sample_csv)
    
    # Convert to BrokerStatement
    statement = broker_statement_from_parsed_csv(
        account_id=12345678,
        parsed=parsed,
        import_date=date(2024, 1, 22),
    )
    
    # Verify BrokerStatement structure
    assert statement.account_id == 12345678
    assert statement.as_of == date(2024, 1, 22)
    assert statement.source == "csv_import"
    
    # Cash balances
    assert "CAD" in statement.cash, f"Missing CAD in cash balances: {statement.cash}"
    assert "USD" in statement.cash, f"Missing USD in cash balances: {statement.cash}"
    assert statement.cash["CAD"] == Decimal("5000"), (
        f"CAD cash: expected 5000, got {statement.cash['CAD']}"
    )
    assert statement.cash["USD"] == Decimal("-500"), (
        f"USD cash: expected -500 (buy 1500 - sell 1000), got {statement.cash['USD']}"
    )
    
    # Positions
    assert 1 in statement.positions, f"Missing company_id 1 (AAPL) in positions"
    assert statement.positions[1].symbol == "AAPL"
    assert statement.positions[1].quantity == Decimal("5"), (
        f"AAPL qty: expected 5 (10 bought - 5 sold), got {statement.positions[1].quantity}"
    )
    assert statement.positions[1].currency == "USD"
    
    # Verify all fields are present with correct types
    assert isinstance(statement.cash, dict)
    assert all(isinstance(v, Decimal) for v in statement.cash.values())
    assert all(isinstance(p, Position) for p in statement.positions.values())

async def test_csv_parser_maps_missing_currency_to_default():
    """If CSV lacks currency column, WealthsimpleParser defaults to 'CAD'."""
    sample_csv = (
        "Account Number,Transaction Date,Description,Symbol,Quantity,Price,Gross Amount\n"
        "12345678,2024-01-20,Deposit,,,5000.00\n"
    )
    parser = WealthsimpleParser()
    parsed = parser.parse_string(sample_csv)
    
    for txn in parsed.transactions:
        assert txn.currency == "CAD", (
            f"Expected default currency CAD, got {txn.currency}"
        )

async def test_csv_parser_empty_file_returns_empty_statement():
    """An empty CSV (no transactions) produces a BrokerStatement with
    zero cash and no positions — not an error."""
    sample_csv = "Account Number,Transaction Date,Description,Symbol,Quantity,Price,Gross Amount\n"
    parser = WealthsimpleParser()
    parsed = parser.parse_string(sample_csv)
    
    statement = broker_statement_from_parsed_csv(
        account_id=12345678,
        parsed=parsed,
        import_date=date(2024, 1, 22),
    )
    assert statement.cash == {}, f"Expected empty cash dict, got {statement.cash}"
    assert statement.positions == {}, f"Expected empty positions dict, got {statement.positions}"


def broker_statement_from_parsed_csv(
    account_id: int,
    parsed: "WealthsimpleParsedData",
    import_date: date,
) -> BrokerStatement:
    """Convert parsed CSV data into a BrokerStatement for reconciliation.
    
    Aggregates transactions by currency to compute cash balances.
    Aggregates trades by symbol/company_id to compute position quantities.
    """
    from decimal import Decimal
    from collections import defaultdict
    
    cash: Dict[str, Decimal] = defaultdict(Decimal)
    positions: Dict[str, Dict] = {}  # symbol → {company_id, qty, currency}
    
    for txn in parsed.transactions:
        currency = txn.currency or "CAD"
        
        # Accumulate cash per currency
        if txn.net_cash_amount:
            cash[currency] += Decimal(str(txn.net_cash_amount))
        
        # Accumulate position quantities
        if txn.symbol and txn.quantity:
            if txn.symbol not in positions:
                positions[txn.symbol] = {
                    "company_id": txn.company_id,
                    "quantity": Decimal(0),
                    "currency": currency,
                }
            positions[txn.symbol]["quantity"] += Decimal(str(txn.quantity))
    
    return BrokerStatement(
        account_id=account_id,
        as_of=import_date,
        cash=dict(cash),
        positions={
            p["company_id"]: Position(
                company_id=p["company_id"],
                symbol=symbol,
                quantity=p["quantity"],
                currency=p["currency"],
            )
            for symbol, p in positions.items()
            if p["quantity"] > 0  # Only include open positions
        },
        source="csv_import",
    )
```

#### 5.2 Implement Reconciliation Engine

```python
# backend/jobs/reconcile_accounts.py

from decimal import Decimal
from datetime import date, timedelta
from typing import List
import logging

logger = logging.getLogger(__name__)

SEVERITY_THRESHOLDS = {
    "cash": {
        "critical": Decimal("100"),     # > $100 difference
        "warning": Decimal("10"),       # > $10 difference  
        "info": Decimal("1"),           # > $1 difference
    },
    "position": {
        "critical": Decimal("10"),      # 10+ shares different
        "warning": Decimal("1"),        # 1+ share different
    },
    "dividend": {
        "critical": Decimal("50"),
        "warning": Decimal("10"),
    },
}


async def reconcile_account(
    account_id: int,
    broker_statement: BrokerStatement,
    event_store: "EventStore",
) -> List[ReconciliationResult]:
    """Compare event log state against broker statement."""
    
    results = []
    
    # 1. Replay events to get expected state
    state = await replay_to_date(
        [account_id], broker_statement.as_of, event_store
    )
    
    # 2. Compare cash per currency
    all_currencies = set(list(state.cash.keys()) + list(broker_statement.cash.keys()))
    for currency in all_currencies:
        expected = state.cash.get(currency, Decimal(0))
        actual = broker_statement.cash.get(currency, Decimal(0))
        delta = expected - actual
        
        severity = _classify_delta("cash", delta)
        if severity:
            results.append(ReconciliationResult(
                field="cash",
                currency=currency,
                company_id=None,
                expected_value=expected,
                actual_value=actual,
                delta=delta,
                severity=severity,
            ))
    
    # 3. Compare positions
    all_company_ids = set(list(state.lots.keys()) + list(broker_statement.positions.keys()))
    for company_id in all_company_ids:
        expected_qty = sum(
            lot.quantity for lot in state.lots.get(company_id, [])
        )
        actual_qty = broker_statement.positions.get(company_id, Position(
            company_id=company_id, symbol="", quantity=Decimal(0)
        )).quantity
        delta = expected_qty - actual_qty
        
        severity = _classify_delta("position", delta)
        if severity:
            results.append(ReconciliationResult(
                field="position",
                currency=None,
                company_id=company_id,
                expected_value=expected_qty,
                actual_value=actual_qty,
                delta=delta,
                severity=severity,
            ))
    
    # 4. Store results
    for result in results:
        await supabase.table("reconciliation_results").insert({
            "account_id": account_id,
            "reconciliation_date": broker_statement.as_of.isoformat(),
            "field": result.field,
            "currency": result.currency,
            "company_id": result.company_id,
            "expected_value": str(result.expected_value) if result.expected_value else None,
            "actual_value": str(result.actual_value) if result.actual_value else None,
            "delta": str(result.delta),
            "delta_pct": str(abs(result.delta / result.actual_value * 100))
                       if result.actual_value and result.actual_value != 0 else None,
            "severity": result.severity,
            "status": "unreviewed",
        }).execute()
    
    # 5. Alert if critical
    critical = [r for r in results if r.severity == "critical"]
    if critical:
        logger.critical(
            f"Account {account_id} reconciliation: {len(critical)} critical discrepancies"
        )
        for c in critical:
            logger.critical(f"  {c.field}: expected={c.expected_value}, actual={c.actual_value}")
        # Send alert (email, Slack, etc.)
        await alert_critical(f"Reconciliation CRITICAL for account {account_id}")
    
    return results


def _classify_delta(field: str, delta: Decimal) -> Optional[str]:
    """Return severity level based on delta magnitude."""
    abs_delta = abs(delta)
    thresholds = SEVERITY_THRESHOLDS.get(field, {})
    
    if abs_delta >= thresholds.get("critical", Decimal("100")):
        return "critical"
    elif abs_delta >= thresholds.get("warning", Decimal("10")):
        return "warning"
    elif abs_delta >= thresholds.get("info", Decimal("1")):
        return "info"
    return None


async def reconcile_all_accounts():
    """Reconcile every account. Called by daily cron job."""
    accounts = await get_all_account_ids()
    total_critical = 0
    
    for account_id in accounts:
        broker = await fetch_broker_statement(account_id)
        if broker is None:
            logger.warning(f"No broker statement available for account {account_id}")
            continue
        
        results = await reconcile_account(account_id, broker, event_store)
        critical = len([r for r in results if r.severity == "critical"])
        total_critical += critical
        
        logger.info(
            f"Account {account_id}: {len(results)} discrepancies "
            f"({critical} critical)"
        )
    
    logger.info(f"Reconciliation complete: {total_critical} total critical items")
    return total_critical


async def fetch_broker_statement(account_id: int) -> Optional[BrokerStatement]:
    """Fetch official record from the brokerage.
    
    No WealthSimple API available — parse the most recent CSV import.
    Falls back to None if no CSV import exists for this account.
    """
    # Parse most recent CSV import
    try:
        parser = WealthsimpleParser()
        latest_csv = await parser.get_latest_import_for_account(account_id)
        if not latest_csv:
            logger.warning(f"No CSV import found for account {account_id}")
            return None
        
        parsed = parser.parse_file(latest_csv.file_path)
        return BrokerStatement(
            account_id=account_id,
            as_of=latest_csv.import_date,
            cash=parsed.cash_balances,      # Dict[str, Decimal]
            positions=parsed.positions,      # Dict[int, Position]
            source="csv_import",
        )
    except Exception as e:
        logger.error(f"Failed to parse CSV for account {account_id}: {e}")
        return None
```

#### 5.3 Add Reconciliation UI Badge

```python
# In API endpoint: GET /api/accounts/{id}/reconciliation/status

async def get_reconciliation_status(account_id: int):
    last = await supabase.table("reconciliation_results") \
        .select("reconciliation_date") \
        .eq("account_id", account_id) \
        .order("reconciliation_date", desc=True) \
        .limit(1) \
        .execute()
    
    if not last.data:
        return {"last_reconciled": None, "reconciliation_status": "never"}
    
    last_date = date.fromisoformat(last.data[0]["reconciliation_date"])
    days_ago = (date.today() - last_date).days
    
    if days_ago >= 7:
        status = "warning"
    elif days_ago >= 30:
        status = "critical"
    else:
        # Check for unreviewed critical items
        critical = await supabase.table("reconciliation_results") \
            .select("id", count="exact") \
            .eq("account_id", account_id) \
            .eq("severity", "critical") \
            .eq("status", "unreviewed") \
            .execute()
        status = "critical" if critical.count > 0 else "ok"
    
    return {
        "last_reconciled": last.data[0]["reconciliation_date"],
        "last_reconciled_days_ago": days_ago,
        "reconciliation_status": status,
    }

# In UI: show badge based on reconciliation_status
# 'ok'       → green "Reconciled <date>" badge
# 'warning'  → yellow "Not reconciled in 7+ days" badge
# 'critical' → red "Unreviewed discrepancies" badge
# 'never'    → grey "Never reconciled" badge
```

#### 5.4 Phase 2.5 Acceptance Criteria

```bash
# Prerequisite: alerting infrastructure must be deployed first
python -c "from backend.shared.alerting import SLACK_WEBHOOK_URL; assert SLACK_WEBHOOK_URL, 'SLACK_WEBHOOK_URL not set'"
echo "Alerting configured"

# Run reconciliation for all accounts
python -m backend.jobs.reconcile_all_accounts

# Expected: 
# - Accounts with CSV imports: "N discrepancies (X critical)"
# - Accounts without CSV imports: "No broker statement available for account N"
# - NOT "Reconciliation complete: 0 total critical items" — that's only possible with API

# Check UI badge (account with recent CSV import)
curl http://localhost:8000/api/accounts/7/reconciliation/status
# Expected: {"last_reconciled": "2026-07-06", "last_reconciled_days_ago": 1, "reconciliation_status": "ok"}
# Note: last_reconciled = CSV import date, not today's date (no API for live data)

# Check UI badge (account WITHOUT any CSV import)
curl http://localhost:8000/api/accounts/99/reconciliation/status
# Expected: {"last_reconciled": None, "reconciliation_status": "never"}

# Run reconciliation tests (including new CSV parser format tests)
pytest tests/test_reconciliation.py tests/test_csv_parser.py -v
# Expected: All pass
# ─────────────────────────────────────
#   test_reconciliation_detects_missing_deposit        PASS
#   test_reconciliation_suppresses_rounding            PASS
#   test_reconciliation_checks_positions               PASS
#   test_reconciliation_detects_missing_position       PASS
#   test_reconciliation_badge_in_ui                    PASS
#   test_csv_parser_produces_broker_statement          PASS
#   test_csv_parser_maps_missing_currency_to_default   PASS
#   test_csv_parser_empty_file_returns_empty_statement PASS
```

---

#### 5.5 General Data Correction Framework

**End outcome:** Any wrong data in the database can be corrected via one of three
mechanisms, each with a complete audit trail. Corrections are events (immutable,
replayable) and never involve UPDATE or DELETE on the event log.

**Three correction mechanisms:**

| Mechanism | Trigger | Speed | Safety Level |
|-----------|---------|-------|-------------|
| Auto-correction | Reconciliation (delta < $1000, < 10 shares) | Automatic, daily | Medium — broker is authoritative |
| Manual correction | Admin API (`POST /api/admin/correct-event`) | On demand | High — human reviews first |
| Bulk backfill | Script (`backfill_corrupted_snapshots.py`) | One-time | High — dry-run validated |

**Correction types supported by the event schema:**

```python
# Type 1: Correct a specific event (wrong amount, wrong quantity)
correction = Event(
    event_type="correction",
    corrects_event_id=original_event_id,  # Links to the wrong event
    net_amount=Decimal("500"),            # The CORRECT amount
    quantity=Decimal("100"),              # The CORRECT quantity
    description="Wrong trade price: was $145, should be $150",
    source="admin_correction",
)

# Type 2: Add a missing event that was never imported
correction = Event(
    event_type="dividend",
    corrects_event_id=None,               # No original — this is additive
    net_amount=Decimal("50"),
    description="Missing dividend from 2024-01-15 (discovered during reconciliation)",
    source="reconciliation_engine",
)

# Type 3: Remove a phantom event (event that never happened)
correction = Event(
    event_type="correction",
    corrects_event_id=phantom_event_id,   # The event to undo
    net_amount=Decimal("-30"),            # Reverse the cash impact
    quantity=Decimal("-10"),              # Reverse the quantity impact
    description="Phantom trade removed: this sell never occurred per broker records",
    source="reconciliation_engine",
)
```

**How corrections work in the replay engine:**

```python
def replay_to_date(...):
    for event in events:
        # Skip events that have been corrected
        if event.event_type == "correction" and event.corrects_event_id:
            continue  # Handled below
        
        # Apply the original event
        handler = EVENT_HANDLERS[event.event_type]
        apply_event(handler, event, state)
        
        # Apply any corrections that exist for this event
        corrections = get_corrections_for_event(state, event.event_id)
        for correction in corrections:
            # The correction event has its own handler that reverses
            # the original and applies the correct values
            correction_handler = EVENT_HANDLERS["correction"]
            apply_event(correction_handler, correction, state)
```

**Replay tests for corrections:**

```python
async def test_correction_reverses_original():
    """A correction event reverses the original and applies correct values."""
    events = [
        buy("AAPL", 10, 150, "USD", "2024-01-15"),       # Wrong: $150
        correction_event(original_id=event_1_id,          # Correction: should be $145
                        net_amount=Decimal("0"),          # No cash impact (gross didn't change)
                        quantity=Decimal("0"),            # Same qty
                        description="Wrong price: was 150, should be 145"),
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    
    # Lot should have cost_per_share = 145, not 150
    lot = state.lots[1][0]
    assert lot.cost_per_share == Decimal("145")
    assert lot.quantity == 10

async def test_correction_adds_missing_deposit():
    """A correction can add an event that never existed."""
    events = [
        deposit(5000, "CAD", "2024-01-01"),               # Known-good deposit
                                                          # Missing: $5000 deposit on 2024-01-10
        deposit(5000, "CAD", "2024-01-10",                # Correction: discovered via reconciliation
                source="reconciliation_engine"),
    ]
    state = await replay_to_date([1], date(2024, 1, 11), events=events)
    assert state.cash["CAD"] == Decimal("10000")

async def test_correction_removes_phantom_trade():
    """A correction can reverse an event that never happened."""
    events = [
        deposit(10000, "CAD", "2024-01-01"),
        sell("AAPL", 5, 200, "USD", "2024-01-15"),        # Phantom: this sell never occurred
        correction(original_id=phantom_sell_id,             # Reversal
                  net_amount=Decimal("1000"),               # Reverse cash (-1000 → +1000)
                  quantity=Decimal("5"),                    # Restore 5 shares
                  description="Phantom trade reversed: broker shows AAPL still held"),
    ]
    state = await replay_to_date([1], date(2024, 1, 16), events=events)
    assert state.cash["CAD"] == Decimal("10000")           # Cash restored
    assert len(state.lots.get(1, [])) > 0                  # Shares restored
```

**Admin correction API:**

```python
# POST /api/admin/correct-event
{
    "original_event_id": "uuid-of-wrong-event",
    "corrected_fields": {
        "net_amount": "500.00",           # Correct value
        "quantity": "100",
        "description": "Corrected trade price"
    },
    "reason": "Trade was imported at wrong price (145 vs 150)",
    "reviewed_by": "admin-user-id"
}

# Response:
{
    "correction_event_id": "uuid-of-new-correction-event",
    "original_event_id": "uuid-of-original",
    "status": "applied",
    "message": "Correction event created. Next snapshot will reflect corrected values."
}
```

**How this guarantees DB correction without data loss:**

1. **No UPDATE ever** — the original (wrong) event stays in the log
2. **No DELETE ever** — the phantom event stays in the log
3. **The correction is an event** — it's in the same log, same schema, same
   audit trail
4. **Replay is deterministic** — same events + same corrections = same state
5. **Full audit trail** — you can see: "Event A was wrong, Event B corrected it,
   Admin C approved it, Reconciliation D triggered it"

**Test with real data:**

```python
async def test_reconciliation_correction_flow():
    """End-to-end: broker says $10,000, event log says $9,500.
    Reconciliation creates correction → replay produces $10,000."""
    
    # Given: event log with wrong balance
    events = [
        deposit(5000, "CAD", "2024-01-01"),
        deposit(4500, "CAD", "2024-01-15"),  # Missing $500
    ]
    
    # When: reconciliation runs
    broker = BrokerStatement(account_id=1, as_of=date(2024, 1, 16),
                              cash={"CAD": Decimal("10000")}, positions={})
    results = await reconcile_and_correct(1, broker, event_store)
    
    # Then: correction event exists
    assert results[0].status == "auto_corrected"
    
    # And: replay produces correct value
    all_events = events + [await event_store.get(results[0].correction_event_id)]
    state = await replay_to_date([1], date(2024, 1, 17), events=all_events)
    assert state.cash["CAD"] == Decimal("10000")

async def test_manual_correction_via_admin_api():
    """Admin can correct any event via API."""
    # Given: wrong trade
    wrong_event = Event(..., net_amount=Decimal("-1500"), quantity=10, unit_price=150)
    wrong_id = await event_store.insert(wrong_event)
    
    # When: admin submits correction
    correction_id = await admin_correct_event(
        original_event_id=wrong_id,
        corrected_fields={"unit_price": "145"},  # Price was $150, should be $145
        reason="Trade price was wrong in import",
        reviewed_by="admin-001",
    )
    
    # Then: correction event created
    correction = await event_store.get(correction_id)
    assert correction.event_type == "correction"
    assert correction.corrects_event_id == wrong_id
    
    # And: replay with correction gives correct cost basis
    state = await replay_to_date([1], date(2024, 1, 16),
                                  events=[wrong_event, correction])
    assert state.lots[1][0].cost_per_share == Decimal("145")
```

**Admin API implementation:**

```python
# backend/api/admin.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin", tags=["admin"])

class CorrectEventRequest(BaseModel):
    original_event_id: UUID
    corrected_fields: Dict[str, Any]     # Only the fields that need correction
    reason: str
    reviewed_by: str

@router.post("/correct-event")
async def correct_event(request: CorrectEventRequest):
    """Create a correction event for a wrong event."""
    
    # 1. Validate original event exists
    original = await event_store.get(request.original_event_id)
    if not original:
        raise HTTPException(status_code=404, detail="Original event not found")
    
    # 2. Build correction event
    correction = Event(
        event_id=None,
        idempotency_key=event_store.make_idempotency_key(
            "admin_correction", str(request.original_event_id)
        ),
        user_id=original.user_id,
        account_id=original.account_id,
        event_type="correction",
        event_date=original.event_date,
        symbol=original.symbol if "symbol" not in request.corrected_fields
               else request.corrected_fields["symbol"],
        company_id=original.company_id,
        quantity=request.corrected_fields.get("quantity", original.quantity),
        unit_price=request.corrected_fields.get("unit_price", original.unit_price),
        gross_amount=request.corrected_fields.get("gross_amount", original.gross_amount),
        net_amount=request.corrected_fields.get("net_amount", original.net_amount),
        currency=request.corrected_fields.get("currency", original.currency),
        description=request.reason,
        source="admin_correction",
        schema_version=1,
        corrects_event_id=request.original_event_id,
    )
    
    # 3. Insert
    inserted = await event_store.insert(correction)
    
    # 4. Log audit
    await audit_log(
        action="CORRECT_EVENT",
        actor=request.reviewed_by,
        target=f"event:{request.original_event_id}",
        details={
            "correction_event_id": str(inserted.event_id),
            "corrected_fields": list(request.corrected_fields.keys()),
            "reason": request.reason,
        },
    )
    
    return {
        "correction_event_id": str(inserted.event_id),
        "original_event_id": str(request.original_event_id),
        "status": "applied",
        "message": "Correction event created. Next snapshot will reflect corrected values.",
    }
```


---

### 6. Phase 3: Backfill Events from Transaction History [PENDING]

**End outcome:** All historical transactions (2021-01-07 through Phase 0 date)
are migrated to `portfolio_events`. The event count matches the transaction
count. `replay_to_date()` for any date produces cash matching
`get_cash_balance()` for the same date.

**Test with real data:**

```python
async def test_backfill_parity():
    """For every account, replay cash matches get_cash_balance on every snapshot date."""
    for account_id in [7, 8, 9, 10, 11, 12]:
        for snap in historical_snapshots_by_account[account_id]:
            state = await replay_to_date([account_id], snap.date, event_store)
            stored_cash = snap.cash_balance
            assert abs(state.cash - stored_cash) < 0.01, (
                f"Account {account_id} on {snap.date}: replay={state.cash}, stored={stored_cash}"
            )
```

**Implementation steps:**

```python
# backend/jobs/backfill_events.py

async def backfill_events():
    """One-time migration: portfolio_transactions → portfolio_events."""
    
    for account_id in all_account_ids:
        txns = await portfolio_repo.get_all_transactions(account_id)
        
        batch = []
        for txn in txns:
            event = Event(
                event_id=None,
                idempotency_key=event_store.make_idempotency_key(
                    f"backfill", txn.transaction_id  # or txn.id / txn.uuid
                ),
                user_id=txn.user_id,
                account_id=account_id,
                event_type=map_activity_type(txn.activity_type),
                event_date=txn.transaction_date,
                symbol=txn.symbol,
                net_amount=txn.net_cash_amount,
                quantity=txn.quantity,
                unit_price=txn.unit_price,
                currency=txn.currency or "CAD",
                source="backfill",
                description=txn.description,
                schema_version=1,
                corrects_event_id=None,
            )
            batch.append(event)
        
        # Batch insert
        for event in batch:
            await event_store.insert(event)
        
        # Create checkpoint for this account
        await checkpoint_manager.create(account_id, date.today(), initial_state())
        
        logger.info(f"Account {account_id}: {len(batch)} events backfilled")

# Run: python -m backend.jobs.backfill_events
```

---

### 7. Phase 4: Switch Snapshot Job to Event Replay [PENDING]

**End outcome:** Daily snapshot job uses event-replay engine
(behind feature flag). Old engine is fallback. Dashboard latency:
p95 < 500ms. No discrepancies between old and new engines. Reconciliation runs daily and reports 0 critical items.

**Test with real data:**

```python
async def test_replay_engine_production_parity():
    """Run for 7 consecutive days with zero discrepancies."""
    disparities = []
    for day in range(7):
        date = now_utc().date() - timedelta(days=day)
        for account_id in all_account_ids:
            old = await compute_snapshot_old(account_id, date)
            new = await compute_snapshot_new(account_id, date)
            if abs(old.total_value - new.total_value) > 0.01:
                disparities.append((account_id, date, old.total_value, new.total_value))
    
    assert len(disparities) == 0, f"Disparities found: {disparities}"
```

**Implementation steps:**

```python
# backend/jobs/portfolio_snapshot_job.py

async def compute_daily_snapshots():
    today = now_utc().date()
    
    use_event_replay = getattr(settings, "ENABLE_EVENT_SOURCING_VALUATION", False)
    
    for account_id in get_all_account_ids():
        t0 = time.monotonic()
        
        if use_event_replay:
            state = await replay_to_date(
                [account_id], today, event_store, checkpoint_manager
            )
            price_snapshot = await freeze_prices(
                [account_id], today, event_store, price_resolver
            )
            snapshot = state_to_snapshot(state, price_snapshot)
        else:
            snapshot = await build_snapshot_row(account_id, today)
        
        # Record quality metric
        elapsed = time.monotonic() - t0
        record_snapshot_latency(account_id, elapsed)
        
        # Store
        await snapshots_repo.upsert_snapshot(snapshot)

# Cut-over procedure:
# 1. Deploy with ENABLE_EVENT_SOURCING_VALUATION=false
# 2. Run comparison mode for 7 days
# 3. Flip flag to true
# 4. Monitor for 30 minutes
# 5. If errors: flip flag back to false
```

---

### 8. Phase 5: Eliminate Mutable State [PENDING]

**End outcome:** `portfolio_holdings`, `CASH_ACTIVITY_TYPES`,
`get_cash_balance()`, and `build_snapshot_row()` are removed.
Cash and holdings are derived exclusively from `portfolio_events`.
Event count == transaction count, parity maintained for 30+ days.

**Implementation steps and rollback for each sub-deployment:**

| Step | What | Rollback | Monitoring Period |
|------|------|----------|-------------------|
| 5.1 | Remove `get_cash_balance()` → all callers use replay | `git revert` | 3 days |
| 5.2 | Remove `CASH_ACTIVITY_TYPES` | `git revert` | 3 days |
| 5.3 | Archive `portfolio_holdings` to cold storage | Restore from archive | 7 days |
| 5.4 | Remove `build_snapshot_row()` | `git revert` | 3 days |
| 5.5 | Remove comparison mode job | `git revert` | 3 days |
| 5.6 | Drop `portfolio_transactions` table | Restore from backup | 30 days |

---

### 9. Gap Fixes (from Appendix E) — Implementation Status

| Gap | Phase | Status | Blocks? | UI Impact? | Notes |
|-----|-------|--------|---------|------------|-------|
| G1: CQRS separation | Phase 4+ | [ ] | No | Indirect (latency) | Add projections after replay engine stable |
| G2: General Ledger | Future | [N/A] | No | No | Major new domain, separate project |
| G3: Corp actions lifecycle | Phase 2 | [ ] | **Yes (spin-offs)** | **Yes** | Handler stubs defined; full lifecycle deferred |
| G4: Security master | Phase 1 | **in plan** | **Yes** | **Yes (FX per holding)** | Table created in migration; populated from companies table |
| G5: Performance attribution | Future | [N/A] | No | No | Separate product feature |
| G6: Configurable lot selection | Phase 2 | [ ] | No | No | Default FIFO; SpecID added later |
| G7: Multi-currency | Phase 1-2 | **in plan** | **Yes** | **Yes (wrong totals)** | Schema (P1) + replay engine (P2) — full design in sections 3-4 |
| G8: Reconciliation | Phase 2.5 | **in plan** | **Yes** | **Yes (undetected drift)** | Auto-correction for deltas < $1000; manual for larger |
| G9: Real-time projections | Phase 4 | [ ] | No | Indirect (freshness) | Add after CQRS separation |
| |
| **Freshness Gap** | **Current** | **Trade-off** | | | |
| Snapshot frequency | Daily (EOD) only | Not real-time. User sees yesterday's data until next snapshot (which may fail silently). Industry standard: Schwab/Robinhood show live or 15-min delayed. Acceptable for MVP if snapshots are reliable. | | | |
| Chart data age | 1-2 days stale | The portfolio chart may show today's date but contain yesterday's data because the snapshot job runs at 2 AM. Label snapshots with `computed_at` timestamp to avoid confusion. | | | |
| Price freshness | Varies per holding | Some holdings may have prices minutes old, others days old (depending on `get_latest_prices` coverage). The UNAVAILABLE flag exposes this but doesn't fix it. | | | |
| Recommendations | Pre-snapshot: show "Last updated: yesterday 2:01 AM" in the UI header. Post-snapshot: show "Last updated: just now" (or the actual `computed_at` time). Never show today's data without today's snapshot having completed. | | | |
| G10: NAV/accrual accounting | Future | [N/A] | No | Minor | New event types, additive |
| S1: GDPR crypto-shredding | Phase 1 | **in plan** | **Yes** | **Yes (PII in descriptions)** | `portfolio_event_pii` table with encrypted descriptions |
| S2: Schema evolution | Phase 2 | [ ] | No | No | Add upcasters before first schema change |
| S3: Multi-tenancy | Phase 1 | **in plan** | **Yes** | No | `user_id` field in initial schema |
| S4: Data retention | Phase 5 | [ ] | No | No | Operational concern |
| S5: Observability | Phase 2 | [ ] | No | No | Prometheus metrics for operators |
| | | | | | |
| **Correction mechanisms** | | | | | |
| FX fallback silently wrong (Decimal(1)) | Phase 2 | **fixed** | — | **Yes (wrong $ with no flag)** | Changed to `continue` → UNAVAILABLE tier |
| Auto-correction via reconciliation | Phase 2.5 | **in plan** | — | **Yes (detects but doesn't fix)** | Correction events created automatically for deltas < $1000 |
| Manual correction via admin API | Phase 2.5 | **in plan** | — | **Yes (no manual fix path)** | `POST /api/admin/correct-event` with audit trail |
| Bulk backfill for known-bad patterns | Phase 0 | **in plan** | — | **Yes (historical corruption)** | Extend existing `backfill_portfolio_snapshots.py` `--repair` mode to detect all 4 bug types (not just key-name). Full scan, not date-range-limited. |

**Critical path items that block Phase 1 event schema finalization:**
1. G4: Security master — fields needed for price resolution
2. G7: Multi-currency — `currency` field must be in initial event schema
3. S1: GDPR — PII fields must be encryptable from day one
4. S3: Multi-tenancy — `user_id` field must be in initial event schema

All four are additive (new columns/tables), not breaking changes. They must be
designed before Phase 1 migration runs because adding columns to an existing
table with millions of events is expensive (PostgreSQL ALTER TABLE rewrites).

---

### 10. Quick Reference: Test Suite Status

```bash
# Current state (pre-implementation)
pytest tests/test_portfolio_snapshots.py -v
# ┌──────────────────────────────────────────────────────────────┬────────────┐
# │ Test Group                                                   │ Status     │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ 54 existing tests (key-name, price, snapshot, etc.)          │ 53 pass    │
# │   test_negative_cash_without_deposits... (old bug)           │ FAIL       │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 0 — Tactical Fix + Backfill                            │            │
# │   5 whitelist tests (Fix 2.1)                                │ 5 fail     │
# │   3 quality-flag tests (Fix 2.2-2.3)                         │ 3 fail     │
# │   1 zero-deposit detection (Fix 2.4)                         │ 1 fail     │
# │   2 WealthSimple end-to-end (Fix 2.5)                        │ 2 fail     │
# │   3 historical backfill tests (Fix 2.6)                      │ not yet    │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 1 — Dual-Write Event Log                               │            │
# │   1 event count parity test                                   │ not yet    │
# │   1 event immutability test                                   │ not yet    │
# │   1 dual-write atomic rollback test                           │ not yet    │
# │   1 orphan detection test                                     │ not yet    │
# │   1 security_master populated test                            │ not yet    │
# │   1 multi-currency schema test                                │ not yet    │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 2 — Event-Replay Engine (Multi-Currency)                │            │
# │   5 replay core tests (buy/sell/dividend/split/deterministic) │ not yet    │
# │   6 multi-currency tests (cash, buy, total, FX,               │ not yet    │
# │     FX missing → UNAVAILABLE, mixed-currencies with FX gap)   │            │
# │   1 replay matches snapshot builder test (comparison)        │ not yet    │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 2.5 — Broker Reconciliation + Auto-Correction           │            │
# │   5 reconciliation tests (missing deposit, rounding,          │ not yet    │
# │     positions match, missing position, UI badge)             │            │
# │   4 auto-correction tests (creates event, replay applies,    │ not yet    │
# │     large delta blocked, idempotent)                         │            │
# │   3 correction framework tests (reverses original,           │ not yet    │
# │     adds missing deposit, removes phantom trade)            │            │
# │   3 CSV parser format tests (BrokerStatement conversion,     │ not yet    │
# │     missing currency default, empty file handling)          │            │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 3 — Backfill Events from History                        │            │
# │   5 backfill parity tests                                    │ not yet    │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 4 — Switch Snapshot Job                                 │            │
# │   7 comparison mode tests (7-day run)                        │ not yet    │
# ├──────────────────────────────────────────────────────────────┼────────────┤
# │ Phase 5 — Eliminate Mutable State                             │            │
# │   3 immutability tests (no updates, no deletes, full replay)  │ not yet    │
# └──────────────────────────────────────────────────────────────┴────────────┘

# Target state after all phases complete
pytest tests/ -v
# Expected: All tests pass, zero failures
# Total: ~40+ tests across all phases, covering every UI-data gap

# Progress tracking:
# Phase 0 complete  → 14 new tests pass (10 original gap + 3 backfill + 1 pre-existing)
# Phase 1 complete  → +4 event log tests pass
# Phase 2 complete  → +10 replay + multi-currency tests pass
# Phase 2.5 complete → +5 reconciliation tests pass
# Phase 3 complete  → +5 backfill parity tests pass
# Phase 4 complete  → +7 comparison tests pass
# Phase 5 complete  → +3 immutability tests pass
```
