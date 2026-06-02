"""Seed portfolio data for the e2e test user."""
import os, sys, uuid
from datetime import date, timedelta, datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENV", "development")

from supabase import create_client, Client
from config import settings

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

FIREBASE_UID = "OVUH9KDf7TORSB4KuvrGEIRAvTI2"
EMAIL = "e2e-test-2026@stockerpro-test.com"
TODAY = date.today()

def log(msg):
    print(f"[seed] {msg}")

def get_or_create_user():
    """Create user row and return user_id."""
    existing = supabase.table("users").select("user_id").eq("auth_id", FIREBASE_UID).execute()
    if existing.data:
        uid = existing.data[0]["user_id"]
        log(f"User already exists: user_id={uid}")
        return uid

    result = supabase.table("users").insert({"auth_id": FIREBASE_UID}).execute()
    uid = result.data[0]["user_id"]
    log(f"Created user: user_id={uid}")
    return uid

def ensure_brokerages():
    """Ensure brokerages exist and return {code: id} map."""
    codes = {
        "QUESTRADE": "Questrade",
        "TD_DIRECT": "TD Direct Investing",
        "WS_TRADE": "Wealthsimple Trade",
    }
    result = {}
    for code, name in codes.items():
        existing = supabase.table("portfolio_brokerages").select("brokerage_id").eq("brokerage_code", code).execute()
        if existing.data:
            result[code] = existing.data[0]["brokerage_id"]
        else:
            ins = supabase.table("portfolio_brokerages").insert({
                "brokerage_code": code,
                "brokerage_name": name,
                "country_code": "CA",
                "is_active": True,
            }).execute()
            result[code] = ins.data[0]["brokerage_id"]
        log(f"Brokerage {code} → id={result[code]}")
    return result

def create_accounts(user_id, brokerages):
    """Create portfolio accounts, return {name: id} map."""
    accounts_data = [
        {"account_external_id": "EXT-TFSA-001", "account_name": "Main TFSA", "account_type": "TFSA", "brokerage_code": "QUESTRADE"},
        {"account_external_id": "EXT-RRSP-001", "account_name": "Retirement RRSP", "account_type": "RRSP", "brokerage_code": "TD_DIRECT"},
        {"account_external_id": "EXT-MRG-001", "account_name": "Margin Account", "account_type": "Margin", "brokerage_code": "QUESTRADE"},
    ]
    result = {}
    for a in accounts_data:
        existing = supabase.table("portfolio_accounts").select("account_id, account_name").eq("user_id", user_id).eq("account_external_id", a["account_external_id"]).execute()
        if existing.data:
            result[a["account_name"]] = existing.data[0]["account_id"]
            log(f"Account '{a['account_name']}' already exists: id={existing.data[0]['account_id']}")
            continue
        ins = supabase.table("portfolio_accounts").insert({
            "user_id": user_id,
            "brokerage_id": brokerages[a["brokerage_code"]],
            "account_external_id": a["account_external_id"],
            "account_name": a["account_name"],
            "account_type": a["account_type"],
            "currency": "CAD",
            "is_active": True,
        }).execute()
        result[a["account_name"]] = ins.data[0]["account_id"]
        log(f"Created account '{a['account_name']}': id={ins.data[0]['account_id']}")
    return result

def get_or_create_companies():
    """Get or create company entries for our test symbols."""
    symbols = [
        ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics"),
        ("RY", "Royal Bank of Canada", "Financial Services", "Banks"),
        ("TD", "Toronto-Dominion Bank", "Financial Services", "Banks"),
        ("ENB", "Enbridge Inc.", "Energy", "Oil & Gas Midstream"),
        ("SHOP", "Shopify Inc.", "Technology", "Software"),
    ]
    result = {}
    for sym, name, sector, industry in symbols:
        existing = supabase.table("companies").select("company_id").eq("ticker_symbol", sym).execute()
        if existing.data:
            result[sym] = existing.data[0]["company_id"]
            log(f"Company {sym} already exists: id={result[sym]}")
        else:
            ins = supabase.table("companies").insert({
                "ticker_symbol": sym,
                "company_name": name,
                "sector": sector,
                "industry": industry,
                "exchange": "NMS" if sym in ("AAPL", "SHOP") else "TSX",
                "currency": "USD" if sym in ("AAPL",) else "CAD",
                "security_type": "stock",
            }).execute()
            result[sym] = ins.data[0]["company_id"]
            log(f"Created company {sym}: id={result[sym]}")
    return result

def create_holdings(accounts, companies):
    """Create holdings for each account with realistic data."""
    holdings_plan = {
        "Main TFSA": [
            ("AAPL", 50, 145.00),
            ("RY", 100, 95.00),
            ("SHOP", 30, 68.00),
        ],
        "Retirement RRSP": [
            ("TD", 200, 72.00),
            ("ENB", 150, 45.00),
            ("AAPL", 30, 148.00),
        ],
        "Margin Account": [
            ("SHOP", 20, 70.00),
            ("ENB", 75, 44.50),
        ],
    }
    holding_ids = []
    for acct_name, holdings in holdings_plan.items():
        acct_id = accounts[acct_name]
        for sym, qty, avg_cost in holdings:
            company_id = companies[sym]
            total_cost = round(qty * avg_cost, 2)
            existing = supabase.table("portfolio_holdings").select("holding_id").eq("account_id", acct_id).eq("company_id", company_id).execute()
            if existing.data:
                holding_ids.append(existing.data[0]["holding_id"])
                log(f"Holding {sym} in {acct_name} already exists: id={existing.data[0]['holding_id']}")
                continue
            ins = supabase.table("portfolio_holdings").insert({
                "account_id": acct_id,
                "company_id": company_id,
                "symbol": sym,
                "quantity": qty,
                "average_cost": avg_cost,
                "total_cost": total_cost,
                "realized_gain_loss": 0,
            }).execute()
            holding_ids.append(ins.data[0]["holding_id"])
            log(f"Created holding {sym} x {qty} @ ${avg_cost} in {acct_name}")
    return holding_ids

def create_transactions(accounts, companies):
    """Create historical transactions for each account."""
    from datetime import date, timedelta
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
    count = 0
    for acct_name, txs in tx_plan.items():
        acct_id = accounts[acct_name]
        for sym, tx_date, qty, price, direction in txs:
            company_id = companies[sym]
            net_cash = -round(qty * price, 2) if direction == "Buy" else round(qty * price, 2)
            existing = supabase.table("portfolio_transactions").select("transaction_id").eq("account_id", acct_id).eq("symbol", sym).eq("transaction_date", tx_date.isoformat()).eq("quantity", qty).execute()
            if existing.data:
                continue
            supabase.table("portfolio_transactions").insert({
                "account_id": acct_id,
                "company_id": company_id,
                "transaction_date": tx_date.isoformat(),
                "activity_type": "Trade",
                "activity_sub_type": direction,
                "direction": direction,
                "symbol": sym,
                "quantity": qty,
                "unit_price": price,
                "net_cash_amount": net_cash,
                "currency": "CAD",
            }).execute()
            count += 1
    log(f"Created {count} transactions")

def create_dividends(accounts, companies):
    """Create dividend payment records."""
    divs = [
        ("Main TFSA", "RY", date.today() - timedelta(days=60), 42.00),
        ("Main TFSA", "RY", date.today() - timedelta(days=150), 40.00),
        ("Retirement RRSP", "TD", date.today() - timedelta(days=60), 76.00),
        ("Retirement RRSP", "TD", date.today() - timedelta(days=150), 72.00),
        ("Retirement RRSP", "ENB", date.today() - timedelta(days=60), 52.50),
        ("Margin Account", "ENB", date.today() - timedelta(days=60), 26.25),
    ]
    count = 0
    for acct_name, sym, pay_date, amount in divs:
        acct_id = accounts[acct_name]
        company_id = companies[sym]
        existing = supabase.table("portfolio_dividends").select("dividend_id").eq("account_id", acct_id).eq("symbol", sym).eq("payment_date", pay_date.isoformat()).execute()
        if existing.data:
            continue
        supabase.table("portfolio_dividends").insert({
            "account_id": acct_id,
            "company_id": company_id,
            "symbol": sym,
            "payment_date": pay_date.isoformat(),
            "amount": amount,
            "currency": "CAD",
            "fiscal_year": pay_date.year,
            "fiscal_month": pay_date.month,
        }).execute()
        count += 1
    log(f"Created {count} dividends")

def create_performance_snapshots(accounts):
    """Create portfolio_performance entries for the last 12 months."""
    now = datetime.now()
    count = 0
    for acct_name, acct_id in accounts.items():
        for i in range(12):
            d = date.today().replace(day=1) - timedelta(days=i * 30)
            d = d.replace(day=1)
            existing = supabase.table("portfolio_performance").select("snapshot_id").eq("account_id", acct_id).eq("snapshot_date", d.isoformat()).execute()
            if existing.data:
                continue
            total_value = round(50000 - i * 500 + (i * 200), 2)
            cost_basis = round(48000 - i * 400, 2)
            supabase.table("portfolio_performance").insert({
                "account_id": acct_id,
                "snapshot_date": d.isoformat(),
                "total_value": total_value,
                "cost_basis": cost_basis,
                "net_deposits": 0,
            }).execute()
            count += 1
    log(f"Created {count} performance snapshots")

def update_current_prices(companies):
    """Update current_market_data for companies to enable price lookups."""
    prices = {
        "AAPL": 178.50,
        "RY": 102.30,
        "TD": 78.40,
        "ENB": 47.20,
        "SHOP": 82.00,
    }
    for sym, price in prices.items():
        company_id = companies[sym]
        supabase.table("current_market_data").upsert({
            "company_id": company_id,
            "current_price": price,
            "open_price": price - 0.50,
            "high_price": price + 1.00,
            "low_price": price - 1.00,
            "close_price": price,
            "volume": 1000000,
            "market_state": "CLOSED",
        }, on_conflict="company_id").execute()
    log("Updated market prices")

def create_price_history(companies):
    """Create 90 days of price history for each company."""
    from random import uniform, seed as random_seed
    random_seed(42)
    prices = {
        "AAPL": 175.00,
        "RY": 100.00,
        "TD": 76.00,
        "ENB": 45.00,
        "SHOP": 65.00,
    }
    count = 0
    for sym, base in prices.items():
        company_id = companies[sym]
        for i in range(90, -1, -1):
            d = TODAY - timedelta(days=i)
            daily = base + uniform(-3, 3)
            existing = supabase.table("price_history").select("company_id").eq("company_id", company_id).eq("price_date", d.isoformat()).execute()
            if existing.data:
                continue
            supabase.table("price_history").insert({
                "company_id": company_id,
                "price_date": d.isoformat(),
                "open_price": round(daily - 0.2, 2),
                "close_price": round(daily, 2),
                "high_price": round(daily + 0.5, 2),
                "low_price": round(daily - 0.5, 2),
                "volume": 2000000,
            }).execute()
            count += 1
    log(f"Created {count} price history rows")

def main():
    log("Starting e2e data seed...")
    user_id = get_or_create_user()
    brokerages = ensure_brokerages()
    accounts = create_accounts(user_id, brokerages)
    companies = get_or_create_companies()
    create_holdings(accounts, companies)
    create_transactions(accounts, companies)
    create_dividends(accounts, companies)
    create_performance_snapshots(accounts)
    update_current_prices(companies)
    create_price_history(companies)
    log("E2E seed complete!")

if __name__ == "__main__":
    main()
