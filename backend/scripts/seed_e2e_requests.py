"""Seed e2e test data using direct HTTP requests to Supabase REST API."""
import os, sys, json, math
from datetime import date, timedelta, datetime
from random import Random

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
        import urllib.request, urllib.error, ssl
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
account_data = [
    {"account_external_id": "EXT-TFSA-001", "account_name": "Main TFSA", "account_type": "TFSA", "brokerage_code": "QUESTRADE"},
    {"account_external_id": "EXT-RRSP-001", "account_name": "Retirement RRSP", "account_type": "RRSP", "brokerage_code": "TD_DIRECT"},
    {"account_external_id": "EXT-MRG-001", "account_name": "Margin Account", "account_type": "Margin", "brokerage_code": "QUESTRADE"},
]
for a in account_data:
    existing = get("portfolio_accounts", f"?user_id=eq.{user_id}&account_external_id=eq.{a['account_external_id']}&select=account_id,account_name")
    if existing and len(existing) > 0:
        accounts[a["account_name"]] = existing[0]["account_id"]
        log(f"  Account '{a['account_name']}' exists: id={existing[0]['account_id']}")
    else:
        result = post("portfolio_accounts", {
            "user_id": user_id,
            "brokerage_id": brokerages.get(a["brokerage_code"]),
            "account_external_id": a["account_external_id"],
            "account_name": a["account_name"],
            "account_type": a["account_type"],
            "currency": "CAD",
            "is_active": True,
        })
        if result and len(result) > 0:
            accounts[a["account_name"]] = result[0]["account_id"]
            log(f"  Created account '{a['account_name']}': id={result[0]['account_id']}")

# ── 4. Companies ─────────────────────────────────────────
log("=== 4. Ensuring companies ===")
companies = {}
company_data = [
    {"ticker_symbol": "AAPL", "company_name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics", "exchange": "NMS", "currency": "USD"},
    {"ticker_symbol": "RY", "company_name": "Royal Bank of Canada", "sector": "Financial Services", "industry": "Banks", "exchange": "TSX", "currency": "CAD"},
    {"ticker_symbol": "TD", "company_name": "Toronto-Dominion Bank", "sector": "Financial Services", "industry": "Banks", "exchange": "TSX", "currency": "CAD"},
    {"ticker_symbol": "ENB", "company_name": "Enbridge Inc.", "sector": "Energy", "industry": "Oil & Gas Midstream", "exchange": "TSX", "currency": "CAD"},
    {"ticker_symbol": "SHOP", "company_name": "Shopify Inc.", "sector": "Technology", "industry": "Software", "exchange": "NMS", "currency": "CAD"},
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
holdings_plan = {
    "Main TFSA": [("AAPL", 50, 145.00), ("RY", 100, 95.00), ("SHOP", 30, 68.00)],
    "Retirement RRSP": [("TD", 200, 72.00), ("ENB", 150, 45.00), ("AAPL", 30, 148.00)],
    "Margin Account": [("SHOP", 20, 70.00), ("ENB", 75, 44.50)],
}
holdings_created = 0
for acct_name, holdings in holdings_plan.items():
    acct_id = accounts.get(acct_name)
    if not acct_id:
        log(f"  ERROR: No account id for {acct_name}")
        continue
    for sym, qty, avg_cost in holdings:
        company_id = companies.get(sym)
        if not company_id:
            continue
        existing = get("portfolio_holdings", f"?account_id=eq.{acct_id}&company_id=eq.{company_id}&select=holding_id")
        if existing and len(existing) > 0:
            log(f"  Holding {sym} in {acct_name} exists: id={existing[0]['holding_id']}")
            continue
        result = post("portfolio_holdings", {
            "account_id": acct_id,
            "company_id": company_id,
            "symbol": sym,
            "quantity": qty,
            "average_cost": avg_cost,
            "total_cost": round(qty * avg_cost, 2),
            "realized_gain_loss": 0,
        })
        if result:
            holdings_created += 1
log(f"  Created {holdings_created} new holdings")

# ── 6. Transactions ──────────────────────────────────────
log("=== 6. Creating transactions ===")
tx_plan = {
    "Main TFSA": [
        ("AAPL", date.today() - timedelta(days=180), 50, 142.00, "Buy"),
        ("RY", date.today() - timedelta(days=150), 100, 93.50, "Buy"),
        ("SHOP", date.today() - timedelta(days=90), 30, 65.00, "Buy"),
        ("RY", date.today() - timedelta(days=30), 10, 105.00, "Sell"),
    ],
    "Retirement RRSP": [
        ("TD", date.today() - timedelta(days=200), 200, 70.00, "Buy"),
        ("ENB", date.today() - timedelta(days=170), 150, 44.00, "Buy"),
        ("AAPL", date.today() - timedelta(days=120), 30, 146.00, "Buy"),
        ("TD", date.today() - timedelta(days=45), 10, 78.00, "Sell"),
    ],
    "Margin Account": [
        ("SHOP", date.today() - timedelta(days=100), 20, 68.50, "Buy"),
        ("ENB", date.today() - timedelta(days=80), 75, 44.00, "Buy"),
    ],
}
tx_created = 0
for acct_name, txs in tx_plan.items():
    acct_id = accounts.get(acct_name)
    if not acct_id:
        continue
    for sym, tx_date, qty, price, direction in txs:
        company_id = companies.get(sym)
        net_cash = -round(qty * price, 2) if direction == "Buy" else round(qty * price, 2)
        date_str = tx_date.isoformat()
        existing = get("portfolio_transactions", f"?account_id=eq.{acct_id}&symbol=eq.{sym}&transaction_date=eq.{date_str}&quantity=eq.{qty}&select=transaction_id")
        if existing and len(existing) > 0:
            continue
        result = post("portfolio_transactions", {
            "account_id": acct_id,
            "company_id": company_id,
            "transaction_date": date_str,
            "activity_type": "Trade",
            "activity_sub_type": direction,
            "direction": direction,
            "symbol": sym,
            "quantity": qty,
            "unit_price": price,
            "net_cash_amount": net_cash,
            "currency": "CAD",
        })
        if result:
            tx_created += 1
log(f"  Created {tx_created} transactions")

# ── 7. Dividends ────────────────────────────────────────
log("=== 7. Creating dividends ===")
dividends = [
    ("Main TFSA", "RY", date.today() - timedelta(days=60), 42.00),
    ("Main TFSA", "RY", date.today() - timedelta(days=150), 40.00),
    ("Retirement RRSP", "TD", date.today() - timedelta(days=60), 76.00),
    ("Retirement RRSP", "TD", date.today() - timedelta(days=150), 72.00),
    ("Retirement RRSP", "ENB", date.today() - timedelta(days=60), 52.50),
    ("Margin Account", "ENB", date.today() - timedelta(days=60), 26.25),
]
div_created = 0
for acct_name, sym, pay_date, amount in dividends:
    acct_id = accounts.get(acct_name)
    company_id = companies.get(sym)
    if not acct_id or not company_id:
        continue
    date_str = pay_date.isoformat()
    existing = get("portfolio_dividends", f"?account_id=eq.{acct_id}&symbol=eq.{sym}&payment_date=eq.{date_str}&select=dividend_id")
    if existing and len(existing) > 0:
        continue
    result = post("portfolio_dividends", {
        "account_id": acct_id,
        "company_id": company_id,
        "symbol": sym,
        "payment_date": date_str,
        "amount": amount,
        "currency": "CAD",
        "fiscal_year": pay_date.year,
        "fiscal_month": pay_date.month,
    })
    if result:
        div_created += 1
log(f"  Created {div_created} dividends")

# ── 8. Performance ───────────────────────────────────────
log("=== 8. Creating performance snapshots ===")
perf_created = 0
for acct_name, acct_id in accounts.items():
    for i in range(12):
        d = date.today().replace(day=1) - timedelta(days=i * 30)
        d = d.replace(day=1)
        date_str = d.isoformat()
        existing = get("portfolio_performance", f"?account_id=eq.{acct_id}&snapshot_date=eq.{date_str}&select=snapshot_id")
        if existing and len(existing) > 0:
            continue
        total_val = round(50000 - i * 500 + i * 200, 2)
        cost_basis = round(48000 - i * 400, 2)
        result = post("portfolio_performance", {
            "account_id": acct_id,
            "snapshot_date": date_str,
            "total_value": total_val,
            "cost_basis": cost_basis,
            "net_deposits": 0,
        })
        if result:
            perf_created += 1
log(f"  Created {perf_created} performance snapshots")

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
