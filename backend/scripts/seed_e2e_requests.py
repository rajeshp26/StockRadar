"""Seed e2e test data using direct HTTP requests to Supabase REST API.

The portfolio plan is NOT defined here: it comes from ``scripts/e2e_fixtures.py``,
the same module ``seed_e2e_data.py`` writes from. This script exists as a fallback
for a broken Python environment, and a fallback that seeds a *different* fixture is
worse than no fallback - the copy that used to live here signed a Sell with a
POSITIVE quantity, so the account's history totalled 110 shares against a
100-share position and every snapshot logged "Replay lot split declined".

``transaction_imported`` events are written here too. A transaction row with no
event is invisible to replay, so the account looks history-less to
``backfill_initial_holdings.py``, which then captures the projection into a
``position_state_checkpoint`` and freezes the contradiction into the event log.
"""
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from random import Random

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent
for _p in (str(_SCRIPTS), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import e2e_fixtures as fixtures  # noqa: E402

from shared.portfolio_event_payload import (  # noqa: E402
    build_transaction_event_data,
    transaction_event_key,
)

# Only market data is relative to the wall clock. The broker record uses the
# fixture's fixed AS_OF date so re-seeding on a different day does not create a
# different fixture (see e2e_fixtures.AS_OF).
TODAY = date.today()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
FIREBASE_UID = os.environ.get("SEED_FIREBASE_UID", "")

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Try to use requests, fallback to urllib
try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False

def request(method, table, body=None, query=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{query}"

    if HAVE_REQUESTS:
        try:
            r = requests.request(method, url, headers=HEADERS, json=body, timeout=30, verify=False)
            if r.status_code in (200, 201):
                return r.json()
            if r.status_code in (409, 406):
                return None
            print(f"  WARN: {method} {table} -> {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"  ERROR: {method} {table} -> {e}")
            return None
    else:
        # Fallback to urllib
        import ssl
        import urllib.error
        import urllib.request
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (409, 406):
                return None
            print(f"  WARN: {method} {table} -> {e.code}: {e.read().decode()[:200]}")
            return None
        except Exception as e:
            print(f"  ERROR: {method} {table} -> {e}")
            return None

def get(table, query):
    return request("GET", table, query=query)

def post(table, body, query=""):
    return request("POST", table, body, query)

def log(msg):
    print(f"[seed] {msg}")

# Suppress SSL warnings
if HAVE_REQUESTS:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 1. User ──────────────────────────────────────────────
log("=== 1. Creating/looking up user ===")
user_check = get("users", f"?auth_id=eq.{FIREBASE_UID}&select=user_id")
if user_check and len(user_check) > 0:
    user_id = user_check[0]["user_id"]
    log(f"User exists: id={user_id}")
else:
    result = post("users", {"auth_id": FIREBASE_UID})
    if result and len(result) > 0:
        user_id = result[0]["user_id"]
        log(f"Created user: id={user_id}")
    else:
        # Try fetching again
        user_check2 = get("users", f"?auth_id=eq.{FIREBASE_UID}&select=user_id")
        if user_check2 and len(user_check2) > 0:
            user_id = user_check2[0]["user_id"]
            log(f"User found after retry: id={user_id}")
        else:
            log("ERROR: Could not create or find user")
            sys.exit(1)

# ── 2. Brokerages ────────────────────────────────────────
log("=== 2. Ensuring brokerages ===")
brokerages = {}
brokerage_data = [
    {"brokerage_code": "QUESTRADE", "brokerage_name": "Questrade", "country_code": "CA", "is_active": True},
    {"brokerage_code": "TD_DIRECT", "brokerage_name": "TD Direct Investing", "country_code": "CA", "is_active": True},
    {"brokerage_code": "WS_TRADE", "brokerage_name": "Wealthsimple Trade", "country_code": "CA", "is_active": True},
]
for b in brokerage_data:
    existing = get("portfolio_brokerages", f"?brokerage_code=eq.{b['brokerage_code']}&select=brokerage_id,brokerage_code")
    if existing and len(existing) > 0:
        brokerages[b["brokerage_code"]] = existing[0]["brokerage_id"]
        log(f"  {b['brokerage_code']} exists: id={existing[0]['brokerage_id']}")
    else:
        result = post("portfolio_brokerages", b)
        if result and len(result) > 0:
            brokerages[b["brokerage_code"]] = result[0]["brokerage_id"]
            log(f"  Created {b['brokerage_code']}: id={result[0]['brokerage_id']}")
        else:
            log(f"  ERROR: Could not create brokerage {b['brokerage_code']}")

# ── 3. Accounts ──────────────────────────────────────────
log("=== 3. Creating accounts ===")
accounts = {}
for a in fixtures.ACCOUNTS:
    existing = get("portfolio_accounts", f"?user_id=eq.{user_id}&account_external_id=eq.{a.external_id}&select=account_id,account_name")
    if existing and len(existing) > 0:
        accounts[a.name] = existing[0]["account_id"]
        log(f"  Account '{a.name}' exists: id={existing[0]['account_id']}")
    else:
        result = post("portfolio_accounts", {
            "user_id": user_id,
            "brokerage_id": brokerages.get(a.brokerage_code),
            "account_external_id": a.external_id,
            "account_name": a.name,
            "account_type": a.account_type,
            "currency": "CAD",
            "is_active": True,
        })
        if result and len(result) > 0:
            accounts[a.name] = result[0]["account_id"]
            log(f"  Created account '{a.name}': id={result[0]['account_id']}")

# ── 4. Companies ─────────────────────────────────────────
log("=== 4. Ensuring companies ===")
companies = {}
company_data = [
    {"ticker_symbol": "AAPL", "company_name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics", "exchange": "NMS", "currency": "USD"},
    {"ticker_symbol": "RY", "company_name": "Royal Bank of Canada", "sector": "Financial Services", "industry": "Banks", "exchange": "TSX", "currency": "CAD"},
    {"ticker_symbol": "TD", "company_name": "Toronto-Dominion Bank", "sector": "Financial Services", "industry": "Banks", "exchange": "TSX", "currency": "CAD"},
    {"ticker_symbol": "ENB", "company_name": "Enbridge Inc.", "sector": "Energy", "industry": "Oil & Gas Midstream", "exchange": "TSX", "currency": "CAD"},
    # SHOP lists on NYSE (NMS) and trades in USD; it was CAD here while
    # seed_e2e_data.py had it right, so the two seeders disagreed about the
    # fixture's own currency and the FX path saw a different portfolio
    # depending on which one ran.
    {"ticker_symbol": "SHOP", "company_name": "Shopify Inc.", "sector": "Technology", "industry": "Software", "exchange": "NMS", "currency": "USD"},
]
for c in company_data:
    existing = get("companies", f"?ticker_symbol=eq.{c['ticker_symbol']}&select=company_id")
    if existing and len(existing) > 0:
        companies[c["ticker_symbol"]] = existing[0]["company_id"]
        log(f"  {c['ticker_symbol']} exists: id={existing[0]['company_id']}")
    else:
        result = post("companies", c)
        if result and len(result) > 0:
            companies[c["ticker_symbol"]] = result[0]["company_id"]
            log(f"  Created {c['ticker_symbol']}: id={result[0]['company_id']}")

# ── 5. Holdings ──────────────────────────────────────────
log("=== 5. Creating holdings ===")
holdings_created = 0
for p in fixtures.POSITIONS:
    acct_id = accounts.get(p.account)
    if not acct_id:
        log(f"  ERROR: No account id for {p.account}")
        continue
    company_id = companies.get(p.symbol)
    if not company_id:
        continue
    existing = get("portfolio_holdings", f"?account_id=eq.{acct_id}&company_id=eq.{company_id}&select=holding_id")
    if existing and len(existing) > 0:
        log(f"  Holding {p.symbol} in {p.account} exists: id={existing[0]['holding_id']}")
        continue
    result = post("portfolio_holdings", {
        "account_id": acct_id,
        "company_id": company_id,
        "symbol": p.symbol,
        "quantity": float(p.quantity),
        "average_cost": float(p.average_cost),
        "total_cost": float(p.total_cost),
        "realized_gain_loss": float(fixtures.realized_gain_loss(p.account, p.symbol)),
    })
    if result:
        holdings_created += 1
log(f"  Created {holdings_created} new holdings")

# ── 6. Transactions ──────────────────────────────────────
log("=== 6. Creating transactions ===")
tx_created = 0
events_created = 0
for t in fixtures.TRADES:
    acct_id = accounts.get(t.account)
    if not acct_id:
        continue
    company_id = companies.get(t.symbol)
    tx_date = t.trade_date(fixtures.AS_OF)
    date_str = tx_date.isoformat()
    existing = get("portfolio_transactions", f"?account_id=eq.{acct_id}&symbol=eq.{t.symbol}&transaction_date=eq.{date_str}&quantity=eq.{float(t.quantity)}&select=transaction_id")
    if existing and len(existing) > 0:
        transaction_id = existing[0]["transaction_id"]
    else:
        result = post("portfolio_transactions", {
            "account_id": acct_id,
            "company_id": company_id,
            "transaction_date": date_str,
            "activity_type": "Trade",
            "activity_sub_type": t.direction,
            "direction": t.direction,
            "symbol": t.symbol,
            "quantity": float(t.quantity),
            "unit_price": float(t.unit_price),
            "net_cash_amount": float(t.net_cash_amount),
            "currency": "CAD",
        })
        if not result:
            continue
        tx_created += 1
        transaction_id = result[0]["transaction_id"]

    # A transaction with no event is invisible to replay; the account then looks
    # history-less to backfill_initial_holdings.py and gets a checkpoint that
    # contradicts the rows written above.
    posted = post("portfolio_events", {
        "event_type": "transaction_imported",
        "event_version": 1,
        "aggregate_id": f"account_{acct_id}",
        "aggregate_type": "account",
        "data": build_transaction_event_data(
            account_id=acct_id,
            company_id=company_id,
            transaction_date=date_str,
            activity_type="Trade",
            activity_sub_type=t.direction,
            direction=t.direction,
            symbol=t.symbol,
            quantity=float(t.quantity),
            unit_price=float(t.unit_price),
            net_cash_amount=float(t.net_cash_amount),
            currency="CAD",
        ),
        "metadata": {
            "backfill": True,
            "entry_source": "seed_fixture",
            "original_transaction_id": transaction_id,
        },
        "idempotency_key": transaction_event_key(acct_id, transaction_id),
    })
    if posted:
        events_created += 1
log(f"  Created {tx_created} transactions, {events_created} events")

# ── 7. Dividends ────────────────────────────────────────
log("=== 7. Creating dividends ===")
div_created = 0
for d in fixtures.DIVIDENDS:
    acct_id = accounts.get(d.account)
    company_id = companies.get(d.symbol)
    if not acct_id or not company_id:
        continue
    pay_date = fixtures.AS_OF - timedelta(days=d.days_ago)
    date_str = pay_date.isoformat()
    existing = get("portfolio_dividends", f"?account_id=eq.{acct_id}&symbol=eq.{d.symbol}&payment_date=eq.{date_str}&select=dividend_id")
    if existing and len(existing) > 0:
        continue
    result = post("portfolio_dividends", {
        "account_id": acct_id,
        "company_id": company_id,
        "symbol": d.symbol,
        "payment_date": date_str,
        "amount": float(d.amount),
        "currency": "CAD",
        "fiscal_year": pay_date.year,
        "fiscal_month": pay_date.month,
    })
    if result:
        div_created += 1
log(f"  Created {div_created} dividends")

# ── 8. Performance ───────────────────────────────────────
# Intentionally absent. This section used to POST twelve months of
# ``portfolio_performance`` rows per account from a literal curve
# (``50000 - i*500 + i*200``), identical for every account.
#
# The table is deprecated (``docs/PORTFOLIO_PERFORMANCE_REENGINEERING.md:2146``),
# nothing reads it (``get_portfolio_performance`` reads ``portfolio_snapshots``;
# ``get_account_performance_history`` has no callers), and the insert can never
# succeed: ``total_cost`` is NOT NULL with no default and was never sent, so the
# request returns 23502. This client swallowed that error into ``result is None``
# and printed "Created 0 performance snapshots", which is why the failure was
# invisible here and fatal in ``seed_e2e_data.py``.
#
# Measured: ``select count(*) from portfolio_performance`` -> 0. The rows this
# section claimed to create have never existed. The real series is produced by the
# snapshot job, not by a fixture.

# ── 9. Market Data ───────────────────────────────────────
log("=== 9. Updating current market data ===")
prices = {"AAPL": 178.50, "RY": 102.30, "TD": 78.40, "ENB": 47.20, "SHOP": 82.00}
for sym, price in prices.items():
    company_id = companies.get(sym)
    if not company_id:
        continue
    post("current_market_data", {
        "company_id": company_id,
        "current_price": price,
        "open_price": price - 0.50,
        "high_price": price + 1.00,
        "low_price": price - 1.00,
        "close_price": price,
        "volume": 1000000,
        "market_state": "CLOSED",
    }, query="?on_conflict=company_id")
    log(f"  Updated {sym} = ${price}")

# ── 10. Price History ────────────────────────────────────
log("=== 10. Creating price history ===")
base_prices = {"AAPL": 175.00, "RY": 100.00, "TD": 76.00, "ENB": 45.00, "SHOP": 65.00}
rng = Random(42)
ph_created = 0
for sym, base in base_prices.items():
    company_id = companies.get(sym)
    if not company_id:
        continue
    for i in range(90, -1, -1):
        d = date.today() - timedelta(days=i)
        date_str = d.isoformat()
        daily = round(base + rng.uniform(-3, 3), 2)
        existing = get("price_history", f"?company_id=eq.{company_id}&price_date=eq.{date_str}&select=company_id")
        if existing and len(existing) > 0:
            continue
        result = post("price_history", {
            "company_id": company_id,
            "price_date": date_str,
            "open_price": round(daily - 0.2, 2),
            "close_price": daily,
            "high_price": round(daily + 0.5, 2),
            "low_price": round(daily - 0.5, 2),
            "volume": 2000000,
        })
        if result:
            ph_created += 1
log(f"  Created {ph_created} price history rows")

log("=== E2E seed complete! ===")
