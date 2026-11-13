# FX Currency Conversion — Design Document

**Status:** Design Proposal (V3 — review feedback incorporated)  
**Date:** 2026-06-23  
**Author:** Code Audit  
**Context:** Portfolio `total_value` sums CAD and USD prices directly without conversion, producing incorrect portfolio values, gain/loss calculations, and snapshot history.

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Problem Analysis](#2-problem-analysis)
3. [Root Cause](#3-root-cause)
4. [Design Principles & Currency Semantics](#4-design-principles--currency-semantics)
5. [Conversion Rule: Snapshot-Date FX for Stock-Only P/L](#5-conversion-rule-snapshot-date-fx-for-stock-only-pl)
6. [Double-Conversion Prevention](#6-double-conversion-prevention)
7. [Data Model](#7-data-model)
8. [Component Design](#8-component-design)
9. [Impacted Code Paths](#9-impacted-code-paths)
10. [Migration Plan](#10-migration-plan)
11. [Rollback Strategy](#11-rollback-strategy)
12. [SQL Migration Script](#12-sql-migration-script)
13. [RLS Policy](#13-rls-policy)
14. [Observability](#14-observability)
15. [Test Plan](#15-test-plan)
16. [Appendix: Code References](#16-appendix-code-references)

---

## 1. Current Architecture

### 1.1 Price Storage

Prices are stored without any currency context in aggregation:

```
current_market_data:  company_id, current_price                        ← no currency
price_history:        company_id, close_price, price_date               ← no currency
```

The **`companies` table** does track currency correctly:

| Symbol | companies.currency | YFinance native currency |
|--------|-------------------|--------------------------|
| RY     | CAD               | CAD (RY.TO)              |
| TD     | CAD               | CAD (TD.TO)              |
| ENB    | CAD               | CAD (ENB.TO)             |
| AAPL   | USD               | USD                      |
| SHOP   | USD               | USD (SHOP on NMS)        |

**Note:** The seed data in `seed_e2e_data.py:106` incorrectly sets SHOP currency to `"CAD"` — this is a pre-existing bug that should be corrected independently. SHOP is listed on NYSE/NMS and trades in USD, regardless of the company being Canadian. This inconsistency will cause test failures under FX conversion and must be fixed.

Portfolio accounts have a `currency` field defaulting to `"CAD"`.

### 1.2 Portfolio Value Flow

```
Transactions (CAD-default currency)
    → FIFO holding calculation → portfolio_holdings (has currency field, correctly set)
        → enrich_holdings_with_prices() ← fetches raw prices, no FX conversion
            → aggregate_holdings() ← passes through currency field
                → get_user_portfolio_overview() ← sums values directly
                    → build_snapshot_row() in snapshot_builder ← sums values directly
```

### 1.3 Current Aggregation

At every level where values are summed, CAD and USD amounts are mixed:

```
total_value = Σ(RY_cad_price * qty) + Σ(AAPL_usd_price * qty) + cash_balance
```

This is equivalent to treating C$1 = US$1, which is wrong by ~36%.

---

## 2. Problem Analysis

### 2.1 Magnitude of Error

With CAD/USD at approximately 1.36 (Jun 2026):

| Holding | Price | Qty | Raw Sum | Converted to CAD | Error per holding |
|---------|-------|-----|---------|------------------|-------------------|
| RY (CAD) | C$202.93 | 100 | $20,293 | $20,293 CAD | — |
| AAPL (USD) | US$294.30 | 50 | $14,715 | $20,012 CAD | US holdings **undervalued by 36%** |
| **Total** | | | **$35,008** | **$40,305 CAD** | **Portfolio undervalued by 13%** |

The per-holding error for any USD-denominated position is 36% (the FX rate). The blended portfolio error depends on the USD/CAD mix — in this example it's 13%. Both are unacceptable, but they are different measures.

If the portfolio base is CAD, USD-denominated holdings are undervalued by 36%. If the base is USD, CAD holdings are overvalued by 36%.

### 2.2 Downstream Impact

- **Portfolio snapshots** (`portfolio_snapshots.total_value`) — wrong for all mixed-currency accounts
- **Portfolio performance** (returns, gain/loss %) — wrong because base and snapshot values are inconsistently denominated
- **Top holdings ranking** (sorted by `current_value`) — wrong ordering if a USD holding ranks above a CAD holding
- **Diversification analysis** (sector % allocation) — wrong percentages
- **Risk metrics** (volatility, drawdown) — wrong due to incorrect base values
- **Dividend yield calculations** — CAD dividends on USD-denominated cost basis (or vice versa)

### 2.3 Accounts Affected

| Account ID | Holdings | Currency Mix |
|-----------|----------|-------------|
| 7-9 (legacy) | Mixed | CAD + USD |
| 10-12 (rebuilt) | Mixed | CAD + USD |

All accounts with both Canadian (RY, TD, ENB) and US (AAPL, SHOP) holdings are affected.

---

## 3. Root Cause

Three independent gaps cause the currency problem:

### Gap 1: No FX Rate Infrastructure

There is no FX rate table, no FX rate fetching service, no exchange rate API configuration. The system has never fetched or stored a currency conversion rate.

- No `exchange_rates` table in Supabase
- No `FX_RATE_PROVIDER` or `FX_API_KEY` in `config.py`
- No currency conversion function anywhere in the codebase
- Zero hits for `fx_rate`, `exchange_rate`, `CAD_USD`, `currency_conversion` in all `.py` files

### Gap 2: Currency Not Propagated to Enrichment

`_enrich_holdings()` at `portfolio_repository.py:397` selects `company_id, company_name, sector, industry, exchange, security_type` — but **not `currency`** from the `companies` table. Even though `companies.currency` is correctly set to `"CAD"` for Canadian stocks, the currency is never attached to the holding objects used in aggregation.

### Gap 3: Summation Ignores Currency

At `portfolio_service.py:1159`:
```python
total_value = sum(h.get("current_value") or 0 for h in holdings)
```

And at `snapshot_builder.py:77-78`:
```python
current_value = qty * current_price
total_market_value += current_value
```

Both sum raw values with zero currency awareness.

---

## 4. Design Principles & Currency Semantics

### 4.1 Design Principles

1. **Base currency per account**: Each `portfolio_accounts` row already has a `currency` field (default `"CAD"`). Use this as the target currency for all conversions.
2. **Convert both sides with snapshot-date FX**: Both `current_value` AND `cost_basis` are converted using the FX rate on the snapshot/valuation date. This reports **stock-only gain/loss** (see §5 for rationale).
3. **Convert at the edge**: Normalize to account base currency during `enrich_holdings_with_prices`, so all downstream code sees only same-currency values. After enrichment, `current_value` is always in account currency.
4. **Never pollute history with live rates**: Live fallback fetches are always cached under today's date, never the requested `as_of` date. Historical rates must come from backfill only.
5. **Daily FX snapshots + historical backfill**: Fetch and cache FX rates daily alongside price data. Run a one-time backfill for all past dates before rebuilding historical snapshots.
6. **No retroactive conversion of stored values**: Existing snapshot rows represent the wrong values. They will be rebuilt after the fix.

### 4.2 Currency Semantics

There are three distinct currency concepts in the system. Confusing them is the source of the bugs this design fixes:

| Field | Source | Meaning | Used For |
|-------|--------|---------|----------|
| `price_currency` | `companies.currency` | Currency of market prices from yfinance/exchange | Converting `current_value` |
| `cost_currency` | Transaction lots (default `price_currency`) | Currency of the original cash outlay | Converting `cost_basis` |
| `account_currency` | `portfolio_accounts.currency` | Reporting/base currency for totals | Target of all conversions |

**Rules:**
- `price_currency` always comes from `companies.currency` — this is the native market currency for the stock's primary exchange.
- `cost_currency` defaults to `price_currency` when transaction-level currency is unavailable. If transaction CSV data specifies a different currency, that takes precedence.
- `account_currency` is the single target for all conversions per account. For accounts 7-12 this is `"CAD"`.

### 4.3 Output Field Naming Convention

After enrichment, holdings carry these currency-related fields:

```python
# Raw / native values (never converted)
h["current_price_native"]   = price          # e.g., 294.30 (USD)
h["current_value_native"]   = price * qty    # e.g., 14715.00 (USD)
h["cost_basis_native"]      = cost_basis     # e.g., 10000.00 (USD)
h["price_currency"]         = "USD"
h["cost_currency"]          = "USD"

# Converted / base values
h["current_value"]          = converted      # e.g., 20012.40 (CAD)
h["cost_basis"]             = converted_cost # e.g., 13600.00 (CAD)
h["value_currency"]         = "CAD"
h["fx_rate"]                = 1.36
h["fx_applied"]             = True
```

This naming makes double-conversion impossible to miss — downstream code always reads `current_value` (which is always in account currency) and never converts again.

---

## 5. Conversion Rule: Snapshot-Date FX for Stock-Only P/L

### 5.1 The Decision

Both `current_value` and `cost_basis` are converted using the FX rate on the **valuation date** (snapshot date or current date), not the transaction date.

```
converted_current_value = current_value_native × fx_rate(price_currency → account_currency, valuation_date)
converted_cost_basis    = cost_basis_native    × fx_rate(cost_currency    → account_currency, valuation_date)

gain_loss = converted_current_value - converted_cost_basis  ← both in account currency
```

### 5.2 What This Reports

This design reports **stock-only gain/loss** — the local-currency return of the security, translated into account currency at snapshot-date FX. It does **not** report true account-currency gain/loss including FX movement between trade date and valuation date.

**Example:**

```
Buy AAPL at US$100 when USD/CAD = 1.25
Valuation date: AAPL is still US$100, USD/CAD = 1.40
```

| Method | Cost Basis | Current Value | Gain/Loss |
|--------|-----------|---------------|-----------|
| True CAD (trade-date FX for cost) | US$100 × 1.25 = C$125 | US$100 × 1.40 = C$140 | **+C$15** (FX gain only) |
| Stock-only (snapshot-date FX for both) | US$100 × 1.40 = C$140 | US$100 × 1.40 = C$140 | **C$0** (no stock movement) |

Stock-only P/L = C$0 — AAPL didn't move in USD terms, so there's no stock gain/loss to report. The C$15 is pure FX gain, which is intentionally excluded.

### 5.3 Why Stock-Only P/L?

| Reason | Detail |
|--------|--------|
| **Matches brokerage statements** | Canadian brokerages (Questrade, IBKR, Wealthsimple) report current value at today's FX. Cost basis is a separate matter — for portfolio valuation they use daily rates. |
| **Simpler implementation** | No need to store FX rate per transaction or per lot. No retroactive data fixes. |
| **Cleaner signal** | Users see "did my stock go up or down?" rather than "did the loonie move?" |
| **Future enhancement path** | Transaction-date FX can be added later for tax/book-cost accurate reporting without changing the current-value conversion. |

### 5.4 What This Does NOT Report

> This design reports local-currency security performance translated into account currency at the valuation-date FX rate. It does not report true account-currency gain/loss including historical FX movement between trade dates and valuation dates. A future enhancement may store transaction-date FX rates for tax/book-cost accurate true-gain/loss reporting.

### 5.5 Implication for Snapshot Cost Basis

Because cost basis is converted at snapshot-date FX, the **same lot's cost basis changes day-to-day** as FX moves:

- Day 1: 10 AAPL @ US$100, FX 1.36 → cost_basis = C$1,360
- Day 2: same lot, FX 1.40 → cost_basis = C$1,400

This is intentional. Cost basis in snapshots is a **derived "valuation cost" reflecting FX on the valuation date**, NOT the historical cash outlay. If reconciliation or auditing compares `Σ(snapshot.cost_basis)` against `Σ(raw_transaction_amounts)`, they will never match. Reconciliation must convert transactions at the snapshot FX rate, not the trade date.

---

## 6. Double-Conversion Prevention

The most dangerous implementation bug is double-conversion:

```
Holding has current_value already converted to CAD,
but holding.currency still says USD,
snapshot_builder sees USD and converts again.
```

Result: `USD value × 1.36 × 1.36` — wrong.

### 6.1 Prevention Strategy

**Enrichment layer** (`enrich_holdings_with_prices`):
- Writes `current_value` in account currency
- Sets `value_currency` to `account_currency`
- Never changes `price_currency` or `currency` (those stay as native)

**Snapshot builder** (`build_snapshot_row`):
- Receives **raw holdings** from the persistence layer, NOT enriched API holdings
- Converts using `price_currency` and `cost_currency` from the raw data
- Never reads `current_value` from input (always recomputes from `qty × price`)

**Result**: The two code paths never share already-converted values. Each converts from raw data independently using the same `FXService`.

### 6.2 Guard Assertion

```python
# In snapshot_builder: assert we're reading raw data, not pre-converted
assert h.get("value_currency") is None, \
    f"Holding {h.get('company_id')} already has value_currency={h['value_currency']}; would double-convert"
```

---

## 7. Data Model

### 7.1 New Table: `exchange_rates`

```sql
CREATE TABLE IF NOT EXISTS exchange_rates (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    base_currency   CHAR(3) NOT NULL,          -- e.g., 'USD'
    target_currency CHAR(3) NOT NULL,          -- e.g., 'CAD'
    rate            NUMERIC(18, 8) NOT NULL,    -- e.g., 1.36450000
    rate_date       DATE NOT NULL,              -- the date this rate was valid
    source          TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_rate_per_day UNIQUE (base_currency, target_currency, rate_date),
    CONSTRAINT rate_positive CHECK (rate > 0),
    CONSTRAINT currencies_len CHECK (
        length(base_currency) = 3 AND length(target_currency) = 3
    ),
    CONSTRAINT no_same_currency CHECK (base_currency <> target_currency),
    CONSTRAINT currencies_uppercase CHECK (
        base_currency = upper(base_currency)
        AND target_currency = upper(target_currency)
    )
);

CREATE INDEX idx_exchange_rates_lookup
    ON exchange_rates (base_currency, target_currency, rate_date DESC);
```

### 7.2 Why Separate from price_history?

FX rates are not stock prices — they apply across all holdings and need independent lookup semantics. A separate table avoids conflating the two concerns.

### 7.3 Rate Direction Convention

Store all rates as `base_currency → target_currency` (how many units of target per 1 unit of base).

| base | target | rate | Meaning |
|------|--------|------|---------|
| USD  | CAD    | 1.36 | US$1 = C$1.36 |
| CAD  | USD    | 0.74 | C$1 = US$0.74 |

For portfolio conversion where account base is CAD and a holding is in USD:
```
converted_value = usd_value × fx_rate(USD → CAD, valuation_date)
```

### 7.4 Inverse Rate Approximation

When the exact `(base, target)` rate is not cached but the inverse `(target, base)` is, we compute `1 / inverse_rate` on the fly and do **not** cache the computed value. This avoids storing a potentially divergent derived rate alongside the direct rate from the scheduler. The approximation error from bid-ask spreads is < 0.05% for CAD/USD — well within portfolio valuation tolerance.

### 7.5 Stale-Rate Policy

The `_query_cached_rate` method finds the nearest-past rate (`.lte("rate_date", as_of)`). This intentionally handles weekends and holidays when FX markets are closed. A **max-staleness guard** is enforced:

- If the nearest cached rate is older than **7 calendar days** from `as_of`, the service logs a warning and returns `None` (triggering live fallback or failure handling).
- This prevents a rate from 10+ days ago being silently used after a scheduler outage.

### 7.6 Cash Balance Assumption

> This design assumes `cash_balance` is already denominated in `portfolio_accounts.currency`. Multi-currency cash balances are out of scope and require separate cash ledger support.

If accounts have USD cash inside a CAD account, the cash value is incorrect under this assumption. This is a known limitation.

---

## 8. Component Design

### 8.1 `shared/fx_service.py`

```python
"""
FX conversion service.

Provides currency conversion at the holding level using cached exchange
rates from the exchange_rates table, falling back to live yfinance fetch.

Caching strategy:
  - Instance-level dict with TTL (300s) — NOT a module global.
  - Each request/snapshot-rebuild creates its own FXService.
  - None results are cached briefly (60s) to avoid thundering herds.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Tuple
from shared.time_utils import now_utc
import logging

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(seconds=300)
NONE_CACHE_TTL = timedelta(seconds=60)


class FXService:
    """Single concern: convert amounts between currencies using exchange rates."""

    MAX_STALE_DAYS = 7

    def __init__(self, supabase_client):
        self._client = supabase_client
        self._cache: Dict[Tuple[str, str, str], Tuple[Optional[Decimal], datetime]] = {}

    def _cache_get(self, key: Tuple[str, str, str]) -> Optional[Decimal]:
        if key not in self._cache:
            return None
        val, ts = self._cache[key]
        ttl = NONE_CACHE_TTL if val is None else CACHE_TTL
        if now_utc() - ts > ttl:
            del self._cache[key]
            return None
        return val

    def _cache_set(self, key: Tuple[str, str, str], val: Optional[Decimal]) -> None:
        self._cache[key] = (val, now_utc())

    def get_rate(
        self, base: str, target: str, as_of: Optional[date] = None
    ) -> Optional[Decimal]:
        """Look up cached rate; fall back to live fetch (today only)."""
        as_of = as_of or now_utc().date()
        cache_key = (base.upper(), target.upper(), as_of.isoformat())

        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        if cache_key in self._cache:  # cached as None
            return None

        # 1. Try exchange_rates table
        rate = self._query_cached_rate(base.upper(), target.upper(), as_of)
        if rate is not None:
            self._cache_set(cache_key, rate)
            return rate

        # 2. Try inverse (CAD→USD when asking USD→CAD) — compute on the fly, don't cache
        inverse_rate = self._query_cached_rate(target.upper(), base.upper(), as_of)
        if inverse_rate is not None and inverse_rate > 0:
            computed = Decimal("1") / inverse_rate
            self._cache_set(cache_key, computed)
            return computed

        # 3. Live fetch — only for today, never for historical dates
        if as_of == now_utc().date():
            rate = self._fetch_and_cache_today(base.upper(), target.upper())
            if rate is not None:
                self._cache_set(cache_key, rate)
                return rate

        self._cache_set(cache_key, None)
        return None

    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of: Optional[date] = None,
    ) -> Optional[Decimal]:
        """Convert amount. Returns None if no rate is available."""
        if from_currency.upper() == to_currency.upper():
            return amount
        rate = self.get_rate(from_currency, to_currency, as_of)
        if rate is None:
            return None
        return amount * rate

    def convert_or_warn(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of: Optional[date] = None,
        holding_id: Optional[str] = None,
    ) -> Tuple[Decimal, bool]:
        """Convert or warn. Returns (converted_amount, fx_applied)."""
        result = self.convert(amount, from_currency, to_currency, as_of)
        if result is not None:
            return (result, True)
        logger.warning(
            "FX rate unavailable for %s->%s as_of %s (holding %s); using unconverted value",
            from_currency, to_currency, as_of, holding_id,
        )
        return (amount, False)

    def _query_cached_rate(
        self, base: str, target: str, as_of: date
    ) -> Optional[Decimal]:
        """Check exchange_rates table for nearest-past rate within staleness limit."""
        res = (
            self._client.table("exchange_rates")
            .select("rate, rate_date")
            .eq("base_currency", base)
            .eq("target_currency", target)
            .lte("rate_date", as_of.isoformat())
            .order("rate_date", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            rate_date = date.fromisoformat(row["rate_date"])
            days_stale = (as_of - rate_date).days
            if days_stale > self.MAX_STALE_DAYS:
                logger.warning(
                    "Cached FX rate %s->%s is %d days stale (max %d); ignoring",
                    base, target, days_stale, self.MAX_STALE_DAYS,
                )
                return None
            return Decimal(str(row["rate"]))
        return None

    def _fetch_and_cache_today(self, base: str, target: str) -> Optional[Decimal]:
        """Live fetch via yfinance, cache under today's date only."""
        from providers.fx_provider import fetch_fx_rate
        rate = fetch_fx_rate(base, target)
        if rate is not None:
            today = now_utc().date()
            self._cache_rate(base, target, rate, today)
            return rate
        return None

    def _cache_rate(self, base: str, target: str, rate: Decimal, rate_date: date) -> None:
        """Upsert rate into exchange_rates. Raises if rate_date is in the future."""
        if rate_date > now_utc().date():
            raise ValueError(
                f"Refusing to cache rate dated in the future: {rate_date}"
            )
        self._client.table("exchange_rates").upsert({
            "base_currency": base,
            "target_currency": target,
            "rate": str(rate),                    # Decimal -> str for NUMERIC column
            "rate_date": rate_date.isoformat(),
            "source": "yfinance",
            "fetched_at": now_utc().isoformat(),
        }, on_conflict="base_currency,target_currency,rate_date").execute()
```

### 8.2 `providers/fx_provider.py`

```python
"""
FX rate provider — fetches live exchange rates from yfinance.

Uses yfinance ticker symbols like CADUSD=X or USDCAD=X.
Uses yf.download() (historical endpoint) instead of ticker.info to avoid
heavy scraping that can return partial data.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
import logging
import math

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_fx_rate(base: str, target: str) -> Optional[Decimal]:
    """Fetch live FX rate via yfinance.

    Uses the last 5 trading days of history and returns the most recent close.
    Handles MultiIndex columns that newer yfinance versions may return.

    Returns Decimal for clean boundary from float arithmetic.
    """
    symbol = f"{base.upper()}{target.upper()}=X"
    try:
        df = yf.download(symbol, period="5d", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None

        # Handle possible MultiIndex columns (newer yfinance versions)
        close_series = df["Close"]
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]

        close = close_series.dropna().iloc[-1]
        if close is not None and not (isinstance(close, float) and math.isnan(close)):
            return Decimal(str(round(float(close), 8)))
    except Exception as e:
        logger.warning("Failed to fetch FX rate for %s: %s", symbol, e)
    return None
```

### 8.3 Integration with `enrich_holdings_with_prices` (portfolio_service.py)

**Current (line 508-623):**

```python
async def enrich_holdings_with_prices(self, holdings):
    ...
    for h in holdings:
        ...
        if price is not None and quantity > 0:
            h["current_price"] = price
            h["current_value"] = price * quantity       # NO FX CONVERSION
        ...
```

**Proposed:**

```python
async def enrich_holdings_with_prices(
    self, holdings, account_base_currency: str   # no default — caller must provide
):
    if not settings.ENABLE_FX_CONVERSION:
        return await self._enrich_holdings_with_prices_legacy(holdings)

    fx = FXService(supabase)
    valuation_date = now_utc().date()
    ...
    for h in holdings:
        ...
        if price is not None and quantity > 0:
            h["current_price_native"] = price
            price_currency = h.get("price_currency") or h.get("currency") or "USD"
            cost_currency = h.get("cost_currency") or price_currency

            # Raw native values (stay in Decimal)
            raw_value = Decimal(str(price)) * Decimal(str(quantity))
            raw_cost = Decimal(str(h.get("total_cost", 0) or 0))

            if price_currency.upper() != account_base_currency.upper():
                conv_val, fx_ok = fx.convert_or_warn(
                    raw_value, price_currency, account_base_currency,
                    as_of=valuation_date, holding_id=str(h.get("company_id")),
                )
                h["current_value"] = float(conv_val)
                h["fx_applied"] = fx_ok

                if raw_cost > 0:
                    conv_cost, _ = fx.convert_or_warn(
                        raw_cost, cost_currency, account_base_currency,
                        as_of=valuation_date, holding_id=str(h.get("company_id")),
                    )
                    h["cost_basis"] = float(conv_cost)
            else:
                h["current_value"] = float(raw_value)
                h["fx_applied"] = True

            h["current_price"] = price                          # always native
            h["value_currency"] = account_base_currency
            h["fx_rate"] = float(fx.get_rate(
                price_currency, account_base_currency, valuation_date
            )) if price_currency.upper() != account_base_currency.upper() else 1.0
```

### 8.4 Integration with `_enrich_holdings` (portfolio_repository.py)

**Current (line 397):**

```python
.select("company_id, company_name, sector, industry, exchange, security_type")
```

**Proposed:**

```python
.select("company_id, company_name, sector, industry, exchange, security_type, currency")
```

And map into the holding:

```python
h["price_currency"] = c.get("currency", "USD")
h["cost_currency"] = h.get("cost_currency") or h["price_currency"]
```

### 8.5 Integration with `build_snapshot_row` (snapshot_builder.py)

```python
def build_snapshot_row(
    account_id: int,
    snapshot_date: date,
    holdings_state: List[Dict],
    cash_balance: Decimal,
    net_deposits: Decimal,
    prices_by_company: Dict[int, Dict],
    job_id: str,
    stale_threshold_days: int = 30,
    account_currency: str = "CAD",
    fx_service: Optional[FXService] = None,
) -> Dict[str, Any]:
    fx = fx_service or FXService(supabase)
    total_market_value = Decimal("0.00")
    total_cost = Decimal("0.00")
    holdings_detail = []

    for h in holdings_state:
        cid = h.get("company_id")
        qty = Decimal(str(h.get("quantity") or 0))
        cost = Decimal(str(h.get("cost_basis") or 0))
        price_currency = h.get("price_currency") or h.get("currency") or "USD"

        # Guard: raw holdings must not carry value_currency (would mean pre-converted)
        assert h.get("value_currency") is None, \
            f"Holding {cid} already has value_currency={h['value_currency']}; would double-convert"

        if qty == 0:
            continue

        price_info = prices_by_company.get(cid, {})
        price = price_info.get("price")
        if price is not None:
            current_price = Decimal(str(price))
        else:
            current_price = Decimal(str(h.get("avg_cost") or 0))

        raw_value = qty * current_price

        if price_currency.upper() != account_currency.upper():
            conv_val, _ = fx.convert_or_warn(
                raw_value, price_currency, account_currency,
                as_of=snapshot_date, holding_id=str(cid),
            )
            if cost > 0:
                conv_cost, _ = fx.convert_or_warn(
                    cost, price_currency, account_currency,
                    as_of=snapshot_date, holding_id=str(cid),
                )
                cost = conv_cost
            current_value = conv_val
        else:
            current_value = raw_value

        total_market_value += current_value
        total_cost += cost
        ...
```

Key differences from V2:
- `snapshot_date` is explicitly passed as `as_of`
- `FXService` is passed in (or created once) to avoid per-call instantiation
- Assertion prevents double-conversion
- Uses `price_currency` not generic `currency`

### 8.6 Scheduler Integration (market_data_scheduler.py)

Add a step to the 24h MarketDataRefresh cycle:

```python
def _refresh_fx_rates(self):
    """Fetch and cache daily CAD/USD rate."""
    from providers.fx_provider import fetch_fx_rate

    usd_to_cad = fetch_fx_rate("USD", "CAD")
    if usd_to_cad is not None:
        self.fx_service._cache_rate("USD", "CAD", usd_to_cad, now_utc().date())
        logger.info("FX rate USD->CAD cached: %s", usd_to_cad)
    else:
        logger.error("Failed to fetch FX rate USD->CAD — rate cache not updated")
        # Metric: fx_rate_fetch_failure

    cad_to_usd = fetch_fx_rate("CAD", "USD")
    if cad_to_usd is not None:
        self.fx_service._cache_rate("CAD", "USD", cad_to_usd, now_utc().date())
```

### 8.7 Historical Backfill Script (`scripts/backfill_exchange_rates.py`)

```python
"""
One-time backfill of historical FX rates into the exchange_rates table.

Runs before Phase 5 (snapshot rebuild) to ensure historical snapshots
can be reconstructed with correct period-appropriate rates.

Extended-range note: for accounts created after this backfill runs,
the snapshot builder will fail to find rates for dates before the backfill
range. Re-run this script periodically with an updated --start, or extend
the daily scheduler to fetch on demand for missing dates.

Usage:
    python scripts/backfill_exchange_rates.py --start 2020-01-01 --pairs USD/CAD CAD/USD
"""

import argparse
from datetime import date
from decimal import Decimal
import math

import pandas as pd
import yfinance as yf

from database import supabase
from shared.time_utils import now_utc

BATCH_SIZE = 250


def backfill_pair(base: str, target: str, start: date, end: date) -> int:
    """Download history for an FX pair and upsert into exchange_rates."""
    symbol = f"{base}{target}=X"
    df = yf.download(symbol, start=start.isoformat(), end=end.isoformat(),
                     auto_adjust=False, progress=False)
    if df is None or df.empty:
        return 0

    # Handle MultiIndex columns
    close_series = df["Close"]
    if isinstance(close_series, pd.DataFrame):
        close_series = close_series.iloc[:, 0]

    rows = []
    for idx, row in close_series.items():
        rate_date = idx.date() if hasattr(idx, "date") else idx
        close = row
        if isinstance(close, pd.Series):
            close = close.iloc[0]
        if close is None or (isinstance(close, float) and math.isnan(close)):
            continue
        rows.append({
            "base_currency": base,
            "target_currency": target,
            "rate": str(Decimal(str(round(float(close), 8)))),
            "rate_date": rate_date.isoformat(),
            "source": "yfinance",
            "fetched_at": now_utc().isoformat(),
        })

    count = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        supabase.table("exchange_rates").upsert(
            batch,
            on_conflict="base_currency,target_currency,rate_date",
        ).execute()
        count += len(batch)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--pairs", nargs="+", default=["USD/CAD", "CAD/USD"])
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = now_utc().date()

    for pair in args.pairs:
        base, target = pair.split("/")
        n = backfill_pair(base.upper(), target.upper(), start, end)
        print(f"Backfilled {n} rows for {pair}")
```

Estimated row count: ~1,600 trading days per pair from 2020 to 2026, not 2,300. Total ~3,200 rows across both pairs.

---

## 9. Impacted Code Paths

### 9.1 Files to Modify

| File | Changes |
|------|---------|
| `backend/config.py` | Add `ENABLE_FX_CONVERSION: bool = False` feature flag |
| `backend/providers/fx_provider.py` | **New file** — live FX rate fetcher using `yf.download()` |
| `backend/shared/fx_service.py` | **New file** — cached FX conversion service with instance-scoped TTL cache |
| `backend/scripts/backfill_exchange_rates.py` | **New file** — one-time historical FX backfill |
| `backend/infrastructure/repositories/portfolio_repository.py:397` | Add `currency` to company select; map to `price_currency` |
| `backend/application/services/portfolio_service.py:508` | Add FX conversion for value + cost; require `account_base_currency` (no default) |
| `backend/shared/snapshot_builder.py` | Accept `account_currency` and `fx_service`; convert with `snapshot_date` as `as_of` |
| `backend/application/schedulers/market_data_scheduler.py` | Add FX rate refresh step with error logging |
| `backend/infrastructure/repositories/portfolio_snapshots_repository.py` | Pass account currency through |

### 9.2 Downstream Consumers (no code change needed, benefit automatically)

| Consumer | What changes |
|----------|-------------|
| `aggregate_holdings()` | `current_value` and `cost_basis` already converted by enrichment |
| `get_user_portfolio_overview()` | `total_value = sum(current_value)` — now correct |
| `_calculate_symbol_holding_fifo()` | Price lookup returns same-currency prices |
| Portfolio performance chart API | Snapshot values now correct |
| Frontend holdings table | Values pre-converted at the API layer |

### 9.3 Downstream Consumers (need `fx_applied` awareness)

| Consumer | Change needed |
|----------|--------------|
| API response schema | Add optional `fx_applied: bool` and `value_currency: str` to holding objects |
| Frontend holdings table | Show warning icon when `fx_applied == false` |
| Frontend portfolio overview | Note "values may be inaccurate" when any holding has `fx_applied == false` |

### 9.4 Callers of `enrich_holdings_with_prices` (must all pass `account_base_currency`)

| Caller | Location |
|--------|----------|
| `get_user_portfolio_overview` | `portfolio_service.py:1151` |
| Portfolio performance calculations | `portfolio_service.py` (various) |
| Snapshot backfill scripts | `scripts/backfill_portfolio_snapshots.py` |

Each must resolve `account_base_currency` from `portfolio_accounts.currency`.

### 9.5 Affected Config

```python
# config.py additions
ENABLE_FX_CONVERSION: bool = False  # feature flag; default False for safe rollout
```

### 9.6 Seed Data Bug to Fix

`backend/scripts/seed_e2e_data.py:106` sets SHOP currency to `"CAD"`. SHOP trades on NMS (NYSE/NASDAQ) in USD. This must be corrected to `"USD"` to avoid test failures under FX conversion.

---

## 10. Migration Plan

### Phase 0: Fix Seed Data (Before Day 1)
1. Correct SHOP currency from `"CAD"` to `"USD"` in `seed_e2e_data.py:106`

### Phase 1: Foundation (Day 1)
1. Run SQL migration to create `exchange_rates` table (with CHECK constraints, RLS)
2. Create `fx_provider.py` — live yfinance FX fetcher (uses `yf.download()`, returns `Decimal`)
3. Create `fx_service.py` — cached FX conversion service with instance-scoped TTL cache
4. Create `backfill_exchange_rates.py` — one-time historical FX backfill script
5. Add feature flag `ENABLE_FX_CONVERSION` to config (default `False`)

### Phase 2: Historical FX Backfill (Day 2)
1. Run `python scripts/backfill_exchange_rates.py --start 2020-01-01 --pairs USD/CAD CAD/USD`
2. Verify row count: ~1,600 rows per pair × 2 pairs = ~3,200 total
3. Spot-check rates against known values (e.g., Bank of Canada archive)

### Phase 3: Integration (Day 3)
1. Modify `_enrich_holdings()` to include `currency` from companies table; map to `price_currency`
2. Modify `enrich_holdings_with_prices()` to convert both `current_value` and `cost_basis` when `ENABLE_FX_CONVERSION=True`; make `account_base_currency` required
3. Modify `build_snapshot_row()` to accept and apply account currency with `snapshot_date` as FX `as_of`
4. Add double-conversion guard assertion in snapshot builder
5. Add FX rate step to MarketDataRefresh scheduler with error logging
6. Add `fx_applied`, `value_currency`, `fx_rate` to holding API responses
7. Update all callers of `enrich_holdings_with_prices` to pass `account_base_currency`

### Phase 4: Validation (Day 4)
1. Run with `ENABLE_FX_CONVERSION=False` — verify no regression (all values unchanged)
2. Flip to `ENABLE_FX_CONVERSION=True` on staging
3. Compare portfolio totals against manual calculation: `Σ(price × qty × daily FX rate)`
4. Verify gain/loss: both sides converted with snapshot-date FX, so gain/loss changes only when stock price changes
5. Verify `fx_applied` and `value_currency` flags are correct for mixed-currency accounts
6. Verify SHOP is correctly treated as USD after seed data fix

### Phase 5: Snapshot Rebuild (Day 5)
1. Rebuild portfolio snapshots for all accounts
2. Verify reconciliation passes with correct FX-adjusted values
3. Document that post-backfill accounts may need the backfill script re-run with an earlier `--start`

---

## 11. Rollback Strategy

### If conversion introduces errors:
1. Set `ENABLE_FX_CONVERSION=False` in config → all values revert to raw (pre-conversion) behavior
2. No data is destroyed — `exchange_rates` table is additive only
3. Existing snapshots are not modified (rebuild needed to correct them)

### If FX rate source is unreliable:
- Add fallback providers (Bank of Canada API, exchangerate-api.com)
- `MAX_STALE_DAYS = 7` prevents ancient rates from being used silently
- `fx_applied` flag lets the frontend surface "value may be inaccurate" warnings

### If live fetch fails during scheduler run:
- Error is logged, metric is incremented, no rate is stored
- Next 24h cycle retries automatically
- `_query_cached_rate` still returns the last good rate (if within staleness limit)

---

## 12. SQL Migration Script

```sql
-- 001_create_exchange_rates_table.sql
CREATE TABLE IF NOT EXISTS exchange_rates (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    base_currency   CHAR(3) NOT NULL,
    target_currency CHAR(3) NOT NULL,
    rate            NUMERIC(18, 8) NOT NULL,
    rate_date       DATE NOT NULL,
    source          TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_rate_per_day UNIQUE (base_currency, target_currency, rate_date),
    CONSTRAINT rate_positive CHECK (rate > 0),
    CONSTRAINT currencies_len CHECK (
        length(base_currency) = 3 AND length(target_currency) = 3
    ),
    CONSTRAINT no_same_currency CHECK (base_currency <> target_currency),
    CONSTRAINT currencies_uppercase CHECK (
        base_currency = upper(base_currency)
        AND target_currency = upper(target_currency)
    )
);

CREATE INDEX IF NOT EXISTS idx_exchange_rates_lookup
    ON exchange_rates (base_currency, target_currency, rate_date DESC);

COMMENT ON TABLE exchange_rates IS
    'Daily exchange rates for portfolio currency conversion.';
COMMENT ON COLUMN exchange_rates.base_currency IS
    'Source currency (ISO 4217), e.g. USD';
COMMENT ON COLUMN exchange_rates.target_currency IS
    'Target currency (ISO 4217), e.g. CAD';
COMMENT ON COLUMN exchange_rates.rate IS
    'Conversion rate: 1 base_currency = rate target_currency';
```

---

## 13. RLS Policy

The `exchange_rates` table is populated by the backend using the `service_role` key. The policies below are **defense-in-depth** — the service_role key bypasses RLS entirely, but the policies document intent and protect against misconfiguration.

```sql
ALTER TABLE exchange_rates ENABLE ROW LEVEL SECURITY;

-- Authenticated users (including via anon key) can read exchange rates.
-- This is needed for live API lookups.
CREATE POLICY "authenticated can read exchange_rates"
    ON exchange_rates
    FOR SELECT
    USING (auth.role() IN ('authenticated', 'service_role'));

-- Only service_role can insert new rates.
CREATE POLICY "service_role can insert exchange_rates"
    ON exchange_rates
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Only service_role can update existing rates.
CREATE POLICY "service_role can update exchange_rates"
    ON exchange_rates
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Only service_role can delete rates.
CREATE POLICY "service_role can delete exchange_rates"
    ON exchange_rates
    FOR DELETE
    USING (auth.role() = 'service_role');
```

**Note:** Because the service_role key bypasses RLS, these policies primarily serve as documentation and a safety net. The backend client uses the service_role key directly.

---

## 14. Observability

### 14.1 Metrics

All metrics are logged at INFO level for grep-based alerting. No separate metrics system (statsd/Prometheus) is currently deployed.

| Log Pattern | Level | Purpose |
|------------|-------|---------|
| `FX rate USD->CAD cached: 1.3645` | INFO | Scheduler success |
| `Failed to fetch FX rate USD->CAD` | ERROR | Scheduler failure |
| `FX rate unavailable for USD->CAD as_of 2025-06-01` | WARNING | API-time conversion miss |
| `Cached FX rate USD->CAD is 9 days stale` | WARNING | Stale-rate guard triggered |

### 14.2 Frontend Signals

When `fx_applied == False` for any holding:
- API response includes `warnings: ["Currency conversion unavailable for some holdings"]`
- Frontend displays a yellow banner: "Some values may be in mixed currencies"

---

## 15. Test Plan

This section covers three layers of testing: **unit tests** (isolated component logic), **integration tests** (real database, multi-component interactions), **database validation** (data integrity assertions), and **end-to-end tests** (full stack from API to DB to frontend).

---

### 15.1 Testing Philosophy

| Principle | Rationale |
|-----------|-----------|
| **Isolate FX provider** from live yfinance in unit tests | Avoid network dependency; mock `yf.download` |
| **Real Supabase instance** for integration tests | `exchange_rates` table is the source of truth; mocking misses RLS, constraints, type coercion |
| **Mutate nothing in production** | All integration tests use a dedicated test schema or isolated test records with cleanup |
| **Test both flag states** | Every integration test runs twice: `ENABLE_FX_CONVERSION=False` (assert no change) and `True` (assert conversion) |
| **Verify both directions** | CAD->USD and USD->CAD; not just the common path |
| **Test the guard, not just the happy path** | Stale rates, missing rates, future dates, double-conversion, concurrent access |

---

### 15.2 Test Fixtures

```python
# conftest.py additions

@pytest.fixture
def fx_service(supabase_client):
    """FXService with a real Supabase client; cleans up after itself."""
    svc = FXService(supabase_client)
    yield svc
    # Cleanup: remove test rates inserted during the test
    supabase_client.table("exchange_rates") \
        .delete() \
        .eq("source", "test") \
        .execute()


@pytest.fixture
def seed_exchange_rate(supabase_client):
    """Insert a known FX rate into exchange_rates for a specific date."""
    def _seed(base, target, rate, rate_date, source="test"):
        supabase_client.table("exchange_rates").upsert({
            "base_currency": base,
            "target_currency": target,
            "rate": str(rate),
            "rate_date": rate_date.isoformat(),
            "source": source,
        }, on_conflict="base_currency,target_currency,rate_date").execute()
    return _seed


@pytest.fixture
def mixed_currency_holdings():
    """Sample holdings with CAD and USD positions for enrichment tests."""
    return [
        {
            "company_id": 1,
            "symbol": "RY",
            "quantity": 100,
            "total_cost": 17000.00,
            "price_currency": "CAD",
            "cost_currency": "CAD",
        },
        {
            "company_id": 2,
            "symbol": "AAPL",
            "quantity": 50,
            "total_cost": 10000.00,
            "price_currency": "USD",
            "cost_currency": "USD",
        },
    ]


@pytest.fixture
def mock_price_map():
    """Mock price data keyed by company_id."""
    return {
        1: {"price": 170.00, "price_date": date(2026, 6, 20)},
        2: {"price": 220.00, "price_date": date(2026, 6, 20)},
    }
```

---

### 15.3 Unit Tests

These test individual components in isolation. External dependencies (yfinance, Supabase) are mocked.

| # | Test | What it verifies | Mock strategy |
|---|------|-----------------|---------------|
| 1 | `test_fx_provider_returns_decimal` | `fetch_fx_rate()` returns `Decimal`, not `float` | Mock `yf.download` to return a DataFrame with known Close |
| 2 | `test_fx_provider_handles_multiindex_columns` | Extracts scalar from DataFrame with MultiIndex columns | Mock `yf.download` to return MultiIndex DataFrame |
| 3 | `test_fx_provider_handles_singleindex_columns` | Extracts scalar from normal DataFrame | Mock `yf.download` to return single-index DataFrame |
| 4 | `test_fx_provider_empty_dataframe` | Returns `None` when yfinance returns empty | Mock `yf.download` to return empty DataFrame |
| 5 | `test_fx_provider_all_nan_close` | Returns `None` when Close column is all NaN | Mock `yf.download` to return DataFrame with NaN closes |
| 6 | `test_fx_provider_network_error` | Returns `None` when yfinance raises | Mock `yf.download` to raise Exception |
| 7 | `test_fx_service_convert_same_currency` | USD->USD returns input unchanged with `fx_applied=True` | No mock needed (short-circuit) |
| 8 | `test_fx_service_convert_with_cached_rate` | Multiplication by cached rate is correct | Insert test rate into `exchange_rates` (real DB) |
| 9 | `test_fx_service_convert_inverse_rate` | USD->CAD computed from cached CAD->USD as `1 / inverse` | Insert CAD->USD rate, verify USD->CAD = 1/rate |
| 10 | `test_fx_service_convert_no_rate` | Returns `None` when cache empty, live fails, as_of != today | Mock `fetch_fx_rate` to return None; as_of=2025-01-01 |
| 11 | `test_fx_service_today_live_fetch_success` | Live fetch called, result cached under today | Mock `fetch_fx_rate` to return Decimal('1.36'); as_of=today |
| 12 | `test_fx_service_historical_as_of_does_not_live_fetch` | Live fetch NOT called for historical as_of; returns None | Assert mock `fetch_fx_rate` not called; as_of=2025-01-01 |
| 13 | `test_fx_service_stale_rate_rejected` | Rate 10 days old with MAX_STALE_DAYS=7 returns None | Seed rate dated 10 days before as_of |
| 14 | `test_fx_service_fresh_rate_accepted` | Rate 3 days old with MAX_STALE_DAYS=7 returns the rate | Seed rate dated 3 days before as_of |
| 15 | `test_fx_service_instance_cache_hit` | Same (base, target, as_of) returns cached value, single DB query | Spy on `_query_cached_rate`; call get_rate twice |
| 16 | `test_fx_service_instance_cache_ttl_expiry` | After CACHE_TTL (300s), cache miss triggers new lookup | Freeze time, call get_rate twice crossing TTL boundary |
| 17 | `test_fx_service_none_cache_ttl_shorter` | None cached with NONE_CACHE_TTL (60s), expires sooner | Freeze time; None result cached, then expires |
| 18 | `test_fx_service_future_rate_date_raises` | `_cache_rate(rate_date=tomorrow)` raises ValueError | Call `_cache_rate` with tomorrow's date |
| 19 | `test_fx_service_convert_or_warn_success` | Returns (converted, True) | Happy path with cached rate |
| 20 | `test_fx_service_convert_or_warn_failure` | Returns (unconverted, False) and logs warning | No rate available, capture log output |
| 21 | `test_fx_service_decimal_arithmetic_precision` | No float rounding errors: `Decimal('1.23456789') * Decimal('1000') = Decimal('1234.56789')` | Direct assertion on convert() result |
| 22 | `test_fx_service_round_trip_via_inverse` | USD->CAD then CAD->USD returns original amount (within 0.01%) | Use known rate, convert both directions |

---

### 15.4 Integration Tests

These tests exercise multiple components together against a **real Supabase instance**. They use the test schema (or a dedicated test project) and clean up after themselves.

#### 15.4.1 Enrich Holdings Tests

Each test in this section:
1. Seeds `companies`, `portfolio_holdings`, and `exchange_rates` tables with known data
2. Calls `enrich_holdings_with_prices()` with `ENABLE_FX_CONVERSION=True`
3. Asserts the returned holdings have correct currency fields

| # | Test | Setup | Assertions |
|---|------|-------|------------|
| 23 | `test_enrich_holdings_cad_holding_in_cad_account` | RY holding (price_currency=CAD), account_currency=CAD, rate=1.36 | `current_value` = raw_value (unchanged), `fx_applied=True`, `value_currency="CAD"`, `fx_rate=1.0` |
| 24 | `test_enrich_holdings_usd_holding_in_cad_account` | AAPL holding (price_currency=USD), account_currency=CAD, rate=1.36 | `current_value` = raw_value × 1.36, `cost_basis` = raw_cost × 1.36, `fx_applied=True`, `value_currency="CAD"` |
| 25 | `test_enrich_holdings_cad_holding_in_usd_account` | RY holding (price_currency=CAD), account_currency=USD, rate=0.74 | `current_value` = raw_value × 0.74, `fx_applied=True` |
| 26 | `test_enrich_holdings_mixed_currencies` | RY (CAD) + AAPL (USD) in CAD account | RY unchanged, AAPL converted; `total_value` = sum of both in CAD |
| 27 | `test_enrich_holdings_cost_basis_zero` | Holding with total_cost=0 | `cost_basis` remains 0, no division by zero |
| 28 | `test_enrich_holdings_cost_basis_negative` | Holding with negative cost_basis (covered short) | Negative cost converted with same rate (not flipped) |
| 29 | `test_enrich_holdings_native_fields_preserved` | After enrichment | `current_price_native` = original price (USD), `current_value_native` = raw value (USD), `price_currency` = "USD" |
| 30 | `test_enrich_holdings_flag_off_no_conversion` | `ENABLE_FX_CONVERSION=False` | `current_value` = raw value, `cost_basis` = raw cost, no new fields added |
| 31 | `test_enrich_holdings_flag_off_legacy_match` | `ENABLE_FX_CONVERSION=False` output matches current production code output | Exact numeric match on all fields |
| 32 | `test_enrich_holdings_requires_account_currency` | `enrich_holdings_with_prices(holdings)` called without `account_base_currency` | TypeError raised |
| 33 | `test_enrich_holdings_fx_applied_false_when_rate_missing` | No exchange_rates row, live fetch disabled (as_of=historical) | `fx_applied=False`, `warnings` populated |
| 34 | `test_enrich_holdings_multiple_accounts_different_currencies` | Account A (CAD) + Account B (USD) with same holdings | Each account's holdings converted to its respective base |
| 35 | `test_enrich_holdings_shop_usd_after_seed_fix` | SHOP holding with price_currency=USD after seed data fix | Correctly treated as USD (not CAD) |

#### 15.4.2 Snapshot Builder Tests

| # | Test | Setup | Assertions |
|---|------|-------|------------|
| 36 | `test_snapshot_builder_same_currency` | All holdings in account currency | `total_market_value` = Σ(qty × price), cost_basis unchanged |
| 37 | `test_snapshot_builder_mixed_currency` | RY (CAD) + AAPL (USD) in CAD account, historical rate seeded | Total computed with rate from `snapshot_date`, not today |
| 38 | `test_snapshot_builder_cost_basis_converted` | AAPL with cost_basis=$10,000 USD, rate=1.36 on snapshot_date | `cost_basis` in output = $13,600 CAD |
| 39 | `test_snapshot_builder_snapshot_date_used_as_of` | Seed rate for snapshot_date=2025-06-15 = 1.30, today's rate = 1.36 | Conversion uses 1.30, not 1.36 |
| 40 | `test_snapshot_builder_double_conversion_guard` | Input holding with `value_currency` already set | AssertionError raised with message "would double-convert" |
| 41 | `test_snapshot_builder_zero_quantity_skipped` | Holding with qty=0 | Skipped, not included in holdings_detail |
| 42 | `test_snapshot_builder_no_price_fallback` | Holding with no price in prices_by_company | Falls back to avg_cost in native currency |
| 43 | `test_snapshot_builder_cash_balance_unchanged` | `cash_balance` is always in account currency | `total_value = total_market_value + cash_balance` (no conversion on cash) |
| 44 | `test_snapshot_builder_fx_service_passed_in` | `fx_service` parameter provided | Uses the passed instance (not creating a new one) |

#### 15.4.3 Scheduler Tests

| # | Test | Setup | Assertions |
|---|------|-------|------------|
| 45 | `test_scheduler_fx_refresh_success` | Run `_refresh_fx_rates()` with live yfinance | Rows inserted into `exchange_rates` for USD->CAD and CAD->USD with `rate_date=today` |
| 46 | `test_scheduler_fx_refresh_existing_date` | Run twice on same day | Upsert updates existing row (no duplicate) |
| 47 | `test_scheduler_fx_refresh_failure_logs_error` | Mock `fetch_fx_rate` to return None | ERROR log written, no row inserted |
| 48 | `test_scheduler_fx_refresh_rate_reasonable` | Live rate from yfinance is between 0.70 and 1.50 | Sanity check on actual rate range |

#### 15.4.4 Backfill Script Tests

| # | Test | Setup | Assertions |
|---|------|-------|------------|
| 49 | `test_backfill_pair_inserts_rows` | Run `backfill_pair("USD", "CAD", start_date, end_date)` with 30-day window | Rows inserted into `exchange_rates` for each trading day in range |
| 50 | `test_backfill_pair_idempotent` | Run backfill twice with same range | No duplicates (unique constraint), same row count |
| 51 | `test_backfill_pair_empty_range` | start > end (future dates) | Returns 0, no rows inserted |
| 52 | `test_backfill_pair_weekend_handling` | Range includes weekends | Only trading days inserted (no weekend gaps in data) |
| 53 | `test_backfill_smoke_2020_2021` | Backfill USD->CAD for first 6 months of 2020 | ~126 trading days inserted, rates between 1.25 and 1.45 |

---

### 15.5 Database Validation Tests

These tests validate data integrity in the database **before and after** the FX conversion logic runs. They can run as standalone assertions or as part of the CI pipeline.

#### 15.5.1 Schema & Constraint Validation

| # | Test | SQL / Method | Expected |
|---|------|-------------|----------|
| 54 | `test_exchange_rates_table_exists` | `SELECT to_regclass('exchange_rates')` | Not null |
| 55 | `test_exchange_rates_has_expected_columns` | `SELECT column_name FROM information_schema.columns WHERE table_name='exchange_rates'` | Contains: id, base_currency, target_currency, rate, rate_date, source, fetched_at |
| 56 | `test_exchange_rates_rate_positive_constraint` | `INSERT INTO exchange_rates (base,target,rate,rate_date) VALUES ('USD','CAD',-1.0,'2026-01-01')` | Raises `check constraint "rate_positive"` |
| 57 | `test_exchange_rates_unique_per_day` | Insert same (USD,CAD,2026-01-01) twice | Second insert updates (ON CONFLICT DO NOTHING) or raises unique violation |
| 58 | `test_exchange_rates_currency_len_check` | `INSERT ... VALUES ('US','CAD',1.0,'2026-01-01')` | Raises constraint violation (CHAR(3)) |
| 59 | `test_exchange_rates_no_same_currency` | `INSERT ... VALUES ('USD','USD',1.0,'2026-01-01')` | Raises `check constraint "no_same_currency"` |
| 60 | `test_exchange_rates_uppercase_check` | `INSERT ... VALUES ('usd','cad',1.0,'2026-01-01')` | Raises `check constraint "currencies_uppercase"` |
| 61 | `test_exchange_rates_rls_enabled` | `SELECT relrowsecurity FROM pg_class WHERE relname='exchange_rates'` | true |
| 62 | `test_exchange_rates_index_exists` | `SELECT indexname FROM pg_indexes WHERE tablename='exchange_rates' AND indexname='idx_exchange_rates_lookup'` | Not null |

#### 15.5.2 Data Quality Validation

| # | Test | SQL / Method | Expected |
|---|------|-------------|----------|
| 63 | `test_no_future_dated_rates` | `SELECT COUNT(*) FROM exchange_rates WHERE rate_date > CURRENT_DATE` | 0 |
| 64 | `test_no_rates_within_7_days_of_future` | `SELECT COUNT(*) FROM exchange_rates WHERE rate_date > CURRENT_DATE + INTERVAL '7 days'` | 0 |
| 65 | `test_every_rate_date_has_usd_cad_and_cad_usd` | For each rate_date, count rows with (USD,CAD) and (CAD,USD) | Both present for every date |
| 66 | `test_rates_are_reciprocal_within_tolerance` | `SELECT a.rate_date, a.rate AS usd_cad, b.rate AS cad_usd, abs(a.rate * b.rate - 1) AS error FROM exchange_rates a JOIN exchange_rates b ON a.rate_date=b.rate_date AND a.base_currency='USD' AND a.target_currency='CAD' AND b.base_currency='CAD' AND b.target_currency='USD' WHERE abs(a.rate * b.rate - 1) > 0.01` | 0 rows (reciprocal error < 1%) |
| 67 | `test_no_duplicate_rate_dates_per_pair` | `SELECT rate_date, COUNT(*) FROM exchange_rates WHERE base_currency='USD' AND target_currency='CAD' GROUP BY rate_date HAVING COUNT(*) > 1` | 0 rows |
| 68 | `test_rate_coverage_for_snapshot_dates` | `SELECT s.account_id, s.snapshot_date FROM portfolio_snapshots s LEFT JOIN exchange_rates e ON e.rate_date = s.snapshot_date::date AND e.base_currency='USD' AND e.target_currency='CAD' WHERE e.rate_date IS NULL` | 0 rows (every snapshot has a rate) |
| 69 | `test_rate_coverage_for_transaction_dates` | `SELECT DISTINCT t.transaction_date::date FROM transactions t LEFT JOIN exchange_rates e ON e.rate_date = t.transaction_date::date AND e.base_currency='USD' AND e.target_currency='CAD' WHERE e.rate_date IS NULL AND t.currency = 'USD'` | 0 rows (every USD transaction date has a rate) |
| 70 | `test_price_currency_not_null` | `SELECT company_id, symbol FROM companies WHERE currency IS NULL` | 0 rows |
| 71 | `test_price_currency_valid_values` | `SELECT DISTINCT currency FROM companies` | Only {'CAD', 'USD'} |
| 72 | `test_seed_data_shop_currency_fixed` | `SELECT currency FROM companies WHERE symbol='SHOP'` | 'USD' |

#### 15.5.3 Post-Conversion Data Integrity

These tests run **after** the FX conversion has been applied (after Phase 3/4) to verify the database state is correct.

| # | Test | Method | Expected |
|---|------|--------|----------|
| 73 | `test_portfolio_holdings_have_fx_fields` | `SELECT column_name FROM information_schema.columns WHERE table_name='portfolio_holdings'` | Contains: value_currency, fx_applied, fx_rate (or these are API-only fields) |
| 74 | `test_all_holdings_value_currency_matches_account` | `SELECT h.account_id, h.company_id, h.value_currency, a.currency FROM portfolio_holdings h JOIN portfolio_accounts a ON h.account_id=a.account_id WHERE h.value_currency <> a.currency` | 0 rows (all holdings denominated in account currency) |
| 75 | `test_no_raw_usd_values_in_current_value` | For USD-price_currency holdings in CAD accounts, `current_value` > `current_value_native` | Always true (converted up) |
| 76 | `test_cost_basis_consistency` | `cost_basis` / `cost_basis_native` ≈ fx_rate | Within 0.1% tolerance |
| 77 | `test_snapshot_total_value_greater_after_conversion` | Compare old snapshot total_value vs rebuild with FX for mixed-currency accounts | New total ≥ old total (USD holdings are now properly valued) |

---

### 15.6 End-to-End Tests

These test the full stack: **API endpoint → service layer → database → response → frontend display**. They run against a staging environment with real data.

#### 15.6.1 API-Level E2E

| # | Test | User Action | Expected API Response |
|---|------|-------------|----------------------|
| 78 | `e2e_portfolio_overview_usd_holdings_converted` | GET `/api/portfolio/overview?account_ids=10` | `total_value` = Σ(CAD holdings) + Σ(USD holdings × 1.36). Response includes `warnings` array if any `fx_applied=False`. |
| 79 | `e2e_portfolio_overview_feature_flag_off` | Set `ENABLE_FX_CONVERSION=False`, repeat request | `total_value` matches pre-FX values (raw sum) |
| 80 | `e2e_portfolio_overview_same_currency_account` | GET `/api/portfolio/overview` for an account with only CAD holdings | `total_value` = raw sum (same as before), `fx_applied=True`, `fx_rate=1.0` |
| 81 | `e2e_portfolio_holdings_fx_fields` | GET `/api/portfolio/holdings?account_id=10` | Each holding has: `fx_applied`, `value_currency`, `fx_rate`, `current_price_native`, `current_value_native` |
| 82 | `e2e_portfolio_performance_uses_fx_snapshots` | GET `/api/portfolio/performance?period=1Y` | Performance calculated from FX-corrected snapshots |
| 83 | `e2e_portfolio_performance_matches_manual_calc` | Manually compute: Σ(price × qty × fx_rate) for each snapshot date | API returns values within 0.5% of manual calc |
| 84 | `e2e_dividend_yield_uses_converted_values` | GET `/api/portfolio/holdings?account_id=10` | dividend_yield correctly uses converted current_value |
| 85 | `e2e_reconciliation_passes_with_fx` | POST `/api/portfolio/reconcile?account_id=10` | PASSED; `current_value` = Σ(qty × price × fx_rate) for USD holdings |
| 86 | `e2e_reconciliation_matches_legacy_for_cad_only` | Reconcile an account with only CAD holdings | Same PASS/FAIL status as before FX |
| 87 | `e2e_holdings_sort_order_correct` | GET `/api/portfolio/holdings?account_id=10&sort=value` | AAPL (now properly valued) sorts above/below RY correctly based on true CAD value |

#### 15.6.2 Database-Level E2E

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 88 | `e2e_exchange_rates_backfill_covers_all_snapshots` | 1. Run backfill from 2020-01-01. 2. `SELECT COUNT(*) FROM portfolio_snapshots s LEFT JOIN exchange_rates e ON e.rate_date=s.snapshot_date AND e.base_currency='USD' AND e.target_currency='CAD' WHERE e.id IS NULL AND EXISTS (SELECT 1 FROM portfolio_holdings h WHERE h.account_id=s.account_id AND h.price_currency='USD')` | 0 (every snapshot with USD holdings has a rate for that date) |
| 89 | `e2e_exchange_rates_scheduler_keeps_current` | 1. Run scheduler. 2. `SELECT rate_date FROM exchange_rates WHERE base_currency='USD' AND target_currency='CAD' ORDER BY rate_date DESC LIMIT 1` | rate_date = today |
| 90 | `e2e_snapshot_rebuild_idempotent` | 1. Rebuild snapshots for account 10. 2. Run reconciliation. 3. Rebuild again. 4. Run reconciliation again. | Both reconciliations PASS with identical total_value |
| 91 | `e2e_no_data_loss_after_rebuild` | Compare count of portfolio_snapshots rows before and after rebuild | Same count (no snapshots dropped) |
| 92 | `e2e_cost_basis_never_zero_after_conversion` | `SELECT COUNT(*) FROM portfolio_snapshots, jsonb_array_elements(holdings_json) AS h WHERE (h->>'cost_basis')::numeric = 0 AND (h->>'quantity')::numeric > 0` | 0 (no holding with qty>0 has zero cost basis after conversion) |

#### 15.6.3 Frontend-Level E2E

| # | Test | User Action | Expected UI Behavior |
|---|------|-------------|---------------------|
| 93 | `e2e_frontend_holdings_value_correct` | Open portfolio dashboard for account 10 | Total portfolio value matches API `total_value`. USD holding values show converted amounts with (USD) label |
| 94 | `e2e_frontend_fx_warning_banner` | Disable FX rate (delete today's rate from exchange_rates), refresh page | Yellow banner: "Some values may be in mixed currencies" appears |
| 95 | `e2e_frontend_fx_warning_dismissible` | Click dismiss on the warning banner | Banner dismissed, preference persisted for session |
| 96 | `e2e_frontend_holding_detail_shows_fx_info` | Click on AAPL holding row | Detail panel shows: "Price (USD): $220.00 | FX Rate: 1.3645 | Value (CAD): $300.19" |
| 97 | `e2e_frontend_performance_chart_updated` | Navigate to performance tab for account 10 | Chart values match FX-corrected snapshots, not old raw snapshots |
| 98 | `e2e_frontend_portfolio_csv_export` | Export portfolio CSV | Exported values use converted CAD amounts, with fx_rate column |

#### 15.6.4 Negative / Edge Case E2E

| # | Test | Scenario | Expected |
|---|-------|----------|----------|
| 99 | `e2e_fx_rate_missing_for_date` | Delete a single day's FX rate, request snapshot for that date | `fx_applied=False` for USD holdings; `total_value` uses unconverted USD values; `warnings` populated |
| 100 | `e2e_fx_rate_stale` | Backfill stops at 2026-06-01; today is 2026-06-20 (19 days stale) | `_query_cached_rate` rejects (MAX_STALE_DAYS=7); live fetch attempted; if live also fails, `fx_applied=False` |
| 101 | `e2e_new_account_after_backfill` | Create new account with transactions from 2022, rebuild snapshots | Snapshot builder triggers live fallback for missing 2022 rates; rates are cached under today (not 2022); `fx_applied=False` for historical dates; warning logged |
| 102 | `e2e_concurrent_scheduler_and_api_request` | Run scheduler refresh while API request reads exchange_rates | Both succeed; upsert with on_conflict handles the race; API may get old or new rate but never an error |
| 103 | `e2e_account_with_no_holdings` | Account with cash_balance > 0 but no holdings | `total_value` = `cash_balance` (no conversion needed), no warnings |

---

### 15.7 Test Pass / Fail Criteria

| Gate | Required Pass Rate | Critical Tests |
|------|-------------------|----------------|
| PR (unit + integration) | 100% | All unit tests (1-22), all integration tests (23-53) |
| Staging deploy (database validation + E2E) | 100% | Tests 54-77 (schema + data quality), 78-87 (API E2E) |
| Production deploy (database validation) | 100% full scan | Tests 63 (no future rates), 68 (rate coverage for snapshots), 73-77 (post-conversion integrity) |
| Weekly (data quality monitoring) | 99.5% | Tests 63, 64, 66, 67, 68, 69 run as scheduled checks |

---

### 15.8 Known Gaps / Out of Scope

| Area | Why excluded | Future work |
|------|-------------|-------------|
| Load testing (1000+ concurrent FX lookups) | Rate table is read-heavy; in-memory cache absorbs most traffic | Add if latency exceeds 50ms p99 |
| Multi-currency cash balance | Assumed in account currency per §7.6 | Separate cash ledger project |
| Transaction-date FX for cost basis | Chose snapshot-date FX per §5 | True gain/loss enhancement |
| CAD/USD vs other currency pairs | Only CAD/USD exist in current data | N-currency support when needed |


---

## 16. Appendix: Code References

### Current code locations

| Location | Description |
|----------|-------------|
| `portfolio_service.py:508-623` | `enrich_holdings_with_prices()` — applies prices without FX conversion |
| `portfolio_service.py:1159` | `total_value = sum(h["current_value"])` — mixes currencies |
| `portfolio_service.py:652-730` | `aggregate_holdings()` — passes through currency but does not convert |
| `portfolio_service.py:732-818` | `_calculate_symbol_holding_fifo()` — returns `currency` but it is unused by conversion |
| `portfolio_service.py:1564` | `_create_company_from_symbol` stores `sd.currency or "USD"` from yfinance |
| `portfolio_repository.py:389-424` | `_enrich_holdings()` — does NOT select `currency` from companies |
| `snapshot_builder.py:77-78` | `current_value = qty * current_price` — no FX conversion |
| `snapshot_builder.py:100` | `total_value = total_market_value + cash_balance` — mixes currencies |
| `config.py` | No FX-related settings |
| `market_data_scheduler.py` | No FX rate refresh step |
| `defeat_beta_provider.py:1343+` | All financial statement parsers hardcode `currency="USD"` (separate concern, not addressed here) |
| `seed_e2e_data.py:106` | SHOP incorrectly set to `"CAD"` — must be `"USD"` |

### Holdings currency fields origin

- `portfolio_service.py:817` — FIFO holding returns `currency` from first transaction (defaults to `"CAD"`)
- `portfolio_service.py:677` — `aggregate_holdings` passes through `h.get("currency")`
- CSV import at `portfolio_service.py:296` — stores `tx.currency` from parsed CSV

### Companies table currency origin

- `portfolio_service.py:1564` — `_create_company_from_symbol` stores `sd.currency or "USD"` from yfinance
- `seed_e2e_data.py:106` — seed data: RY->CAD, TD->CAD, ENB->CAD, AAPL->USD, SHOP->CAD **(bug: should be USD)**

### New files

| File | Purpose |
|------|---------|
| `backend/providers/fx_provider.py` | Live FX rate fetcher using `yf.download()` |
| `backend/shared/fx_service.py` | Cached FX conversion service with instance-scoped TTL cache |
| `backend/scripts/backfill_exchange_rates.py` | One-time historical FX rate backfill |
