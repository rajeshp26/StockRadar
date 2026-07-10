"""
Portfolio Dashboard E2E Performance Test

Connects to REAL Supabase (via service role key) and measures
actual query latencies for every DB call the portfolio endpoints make.
No JWT auth needed — uses service_role directly.

Usage:
    python -m pytest tests/test_portfolio_e2e_performance.py -v -s

WARNING: This test hits the real production database. Read-only queries only.
"""

import os
import time
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Read real Supabase credentials directly from .env (bypass conftest mocks)
_env_file = Path(__file__).resolve().parent.parent / ".env"
_SUPABASE_URL = "https://viqdqgxcumcdhqxooplw.supabase.co"
_SUPABASE_KEY = "sb_secret_NxN3ywf1RrMektnf-rq9hg_FxKFOVoG"
if _env_file.exists():
    import dotenv
    _env_vars = dotenv.dotenv_values(_env_file)
    _SUPABASE_URL = _env_vars.get("SUPABASE_URL") or _SUPABASE_URL
    _SUPABASE_KEY = _env_vars.get("SUPABASE_SERVICE_ROLE_KEY") or _SUPABASE_KEY

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Real auth_id for user rajeshp01@gmail.com ────────────────────────────────
AUTH_ID = "firebase_auth_id_placeholder"
# We use db_user_id=1 which we get from portfolio_accounts

USER_ID = 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grade(ms: float) -> str:
    if ms < 20: return "PASS"
    if ms < 100: return "OK"
    if ms < 500: return "SLOW"
    if ms < 2000: return "CRITICAL"
    return "FAIL"


def _print_waterfall(results: List[dict]):
    total_ms = sum(r["elapsed_ms"] for r in results)
    width = 50
    print()
    print("=" * 100)
    print("  PORTFOLIO DASHBOARD -- REAL DB QUERY WATERFALL")
    print("=" * 100)
    print(f"  User:   user_id={USER_ID}")
    print(f"  Total:  {total_ms:.0f}ms ({total_ms/1000:.1f}s)")
    print(f"  Queries: {len(results)}")
    print("=" * 100)
    print()

    for i, r in enumerate(results, 1):
        grade = _grade(r["elapsed_ms"])
        bar_len = max(1, int(r["elapsed_ms"] / max(total_ms, 1) * width))
        bar = "#" * bar_len
        print(f"  {i:2d}. {grade:<8s} {r['elapsed_ms']:>8.0f}ms  {r['label']:<50s} {bar}")
        if r.get("detail"):
            for line in r["detail"].split("\n"):
                print(f"       {line}")

    print()
    print(f"      TOTAL: {total_ms:.0f}ms ({total_ms/1000:.1f}s)")
    print()

    sorted_by_time = sorted(results, key=lambda r: r["elapsed_ms"], reverse=True)
    print("  -- Top 5 slowest queries --")
    for r in sorted_by_time[:5]:
        print(f"     {r['elapsed_ms']:>8.0f}ms  {r['label']}")
    print()

    slow = [r for r in results if r["elapsed_ms"] >= 500]
    if slow:
        print(f"  -- {len(slow)} queries over 500ms (action items) --")
        for r in slow:
            print(f"     {r['elapsed_ms']:>8.0f}ms  {r['label']}")
        print()


def _parse_timestamp(ts) -> date:
    if isinstance(ts, date) and not isinstance(ts, datetime):
        return ts
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, str):
        return date.fromisoformat(ts)
    return ts


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    """Real Supabase client via service role key (bypasses conftest mocks)."""
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions
    from supabase_auth import SyncMemoryStorage
    client = create_client(
        _SUPABASE_URL,
        _SUPABASE_KEY,
        options=SyncClientOptions(
            storage=SyncMemoryStorage(),
            postgrest_client_timeout=30,
        ),
    )
    yield client


def _get_account_ids(db):
    """Get account IDs for user_id=1."""
    res = db.table("portfolio_accounts").select("account_id").eq("user_id", USER_ID).execute()
    return [a["account_id"] for a in (res.data or [])]


def _get_company_ids(db, account_ids):
    """Get company IDs based on account_ids (no user_id column on holdings)."""
    if not account_ids:
        return []
    res = db.table("portfolio_holdings").select("company_id").in_("account_id", account_ids).neq("quantity", 0).execute()
    return list({h["company_id"] for h in (res.data or []) if h.get("company_id")})


# ── 1. Dashboard Query Latencies ─────────────────────────────────────────────

@pytest.mark.anyio
class TestDashboardQueryLatencies:
    """Measure each individual query the /portfolio/dashboard endpoint makes."""

    async def test_get_user_accounts(self, db):
        start = time.perf_counter()
        res = db.table("portfolio_accounts").select("*").eq("user_id", USER_ID).execute()
        elapsed = (time.perf_counter() - start) * 1000
        accounts = res.data or []
        print(f"\n  portfolio_accounts: {len(accounts)} records, ids={[a['account_id'] for a in accounts]}")
        print(f"  Time: {elapsed:.0f}ms")

    async def test_get_holdings_by_account_ids(self, db):
        aids = _get_account_ids(db)
        start = time.perf_counter()
        res = db.table("portfolio_holdings").select("*").in_("account_id", aids).neq("quantity", 0).execute()
        elapsed = (time.perf_counter() - start) * 1000
        holdings = res.data or []
        print(f"\n  portfolio_holdings (by account_ids): {len(holdings)} records in {elapsed:.0f}ms")
        print(f"  Companies involved: {len({h['company_id'] for h in holdings})}")

    async def test_current_market_data_all(self, db):
        """The app fetches ALL rows from current_market_data (no WHERE clause)."""
        start = time.perf_counter()
        res = db.table("current_market_data").select("company_id, current_price").execute()
        elapsed = (time.perf_counter() - start) * 1000
        data = res.data or []
        print(f"\n  current_market_data (ALL rows): {len(data)} records in {elapsed:.0f}ms")

    async def test_companies_enrichment(self, db):
        aids = _get_account_ids(db)
        cids = _get_company_ids(db, aids)
        start = time.perf_counter()
        res = db.table("companies").select("*").in_("company_id", cids).execute()
        elapsed = (time.perf_counter() - start) * 1000
        companies = res.data or []
        print(f"\n  companies enrichment: {len(companies)}/{len(cids)} found in {elapsed:.0f}ms")

    async def test_dividends_batch(self, db):
        aids = _get_account_ids(db)
        current_year = date.today().year
        start = time.perf_counter()
        res = db.table("portfolio_dividends").select("*").in_("account_id", aids).eq("fiscal_year", current_year).limit(10000).execute()
        elapsed = (time.perf_counter() - start) * 1000
        divs = res.data or []
        ytd = sum(float(d.get("amount") or 0) for d in divs)
        print(f"\n  Dividends ({current_year}): {len(divs)} records, ${ytd:.2f} YTD in {elapsed:.0f}ms")

    async def test_exchange_rates(self, db):
        start = time.perf_counter()
        res = db.table("exchange_rates").select("*").in_("base_currency", ["USD", "CAD"]).in_("target_currency", ["CAD", "USD"]).execute()
        elapsed = (time.perf_counter() - start) * 1000
        rates = res.data or []
        print(f"\n  exchange_rates: {len(rates)} pairs in {elapsed:.0f}ms")

    async def test_user_preferred_currency(self, db):
        """Uses users table with auth_id."""
        start = time.perf_counter()
        res = db.table("users").select("preferred_currency").eq("auth_id", AUTH_ID).maybe_single().execute()
        elapsed = (time.perf_counter() - start) * 1000
        profile = res.data if res.data else {}
        print(f"\n  users.preferred_currency: {profile} in {elapsed:.0f}ms")

    async def test_brokerages(self, db):
        start = time.perf_counter()
        res = db.table("portfolio_brokerages").select("*").execute()
        elapsed = (time.perf_counter() - start) * 1000
        print(f"\n  portfolio_brokerages: {len(res.data or [])} records in {elapsed:.0f}ms")


# ── 2. Performance Chart Query Latencies ─────────────────────────────────────

@pytest.mark.anyio
class TestPerformanceChartLatencies:
    """Measure queries the /portfolio/performance endpoint triggers."""

    async def test_transactions_trade_batch(self, db):
        aids = _get_account_ids(db)
        start = time.perf_counter()
        res = db.table("portfolio_transactions").select("*").in_("account_id", aids).in_("activity_type", ["Trade"]).order("transaction_date", desc=True).execute()
        elapsed = (time.perf_counter() - start) * 1000
        print(f"\n  portfolio_transactions (Trade): {len(res.data or [])} records in {elapsed:.0f}ms")

    async def test_transactions_all_batch(self, db):
        aids = _get_account_ids(db)
        start = time.perf_counter()
        res = db.table("portfolio_transactions").select("*").in_("account_id", aids).order("transaction_date", desc=True).limit(10000).execute()
        elapsed = (time.perf_counter() - start) * 1000
        print(f"\n  portfolio_transactions (ALL): {len(res.data or [])} records in {elapsed:.0f}ms")

    async def test_price_history_paginated(self, db):
        aids = _get_account_ids(db)
        cids = _get_company_ids(db, aids)
        target_date = date.today().isoformat()
        start = time.perf_counter()
        all_prices = []
        offset = 0
        batch_size = 1000
        while True:
            res = db.table("price_history").select("company_id, price_date, close_price").in_("company_id", cids).lte("price_date", target_date).order("price_date", desc=False).range(offset, offset + batch_size - 1).execute()
            if not res.data:
                break
            all_prices.extend(res.data)
            offset += batch_size
            if len(res.data) < batch_size:
                break
        elapsed = (time.perf_counter() - start) * 1000
        companies_with = len({r["company_id"] for r in all_prices})
        pages = (offset // batch_size) + (1 if offset % batch_size else 0)
        print(f"\n  price_history (paginated): {len(all_prices)} records, {companies_with}/{len(cids)} companies, {pages} pages in {elapsed:.0f}ms")

    async def test_splits_lookup(self, db):
        aids = _get_account_ids(db)
        cids = _get_company_ids(db, aids)
        start = time.perf_counter()
        res = db.table("splits").select("*").in_("company_id", cids).order("split_date", desc=False).execute()
        elapsed = (time.perf_counter() - start) * 1000
        print(f"\n  splits lookup: {len(res.data or [])} records in {elapsed:.0f}ms")

    async def test_portfolio_snapshots_1y(self, db):
        aids = _get_account_ids(db)
        start_date = (date.today() - timedelta(days=365)).isoformat()
        end_date = date.today().isoformat()
        start = time.perf_counter()
        res = db.table("portfolio_snapshots").select("*").in_("account_id", aids).gte("snapshot_date", start_date).lte("snapshot_date", end_date).order("snapshot_date", desc=False).execute()
        elapsed = (time.perf_counter() - start) * 1000
        snaps = res.data or []
        accounts_with = len({s["account_id"] for s in snaps})
        print(f"\n  portfolio_snapshots (1Y): {len(snaps)} records, {accounts_with}/{len(aids)} accounts in {elapsed:.0f}ms")


# ── 3. Full Dashboard Waterfall ──────────────────────────────────────────────

@pytest.mark.anyio
class TestFullDashboardWaterfall:
    """Simulate the EXACT query sequence /portfolio/dashboard makes."""

    async def test_full_dashboard_waterfall(self, db):
        results = []

        # Step 1: get_user_accounts
        start = time.perf_counter()
        accounts_res = db.table("portfolio_accounts").select("*").eq("user_id", USER_ID).execute()
        accounts = accounts_res.data or []
        account_ids_list = [a["account_id"] for a in accounts]
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_accounts", "elapsed_ms": t, "detail": f"{len(accounts)} accounts"})

        # Step 2: get_user_all_holdings (by account_ids)
        start = time.perf_counter()
        holdings_res = db.table("portfolio_holdings").select("*").in_("account_id", account_ids_list).neq("quantity", 0).execute()
        holdings = holdings_res.data or []
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_holdings (all)", "elapsed_ms": t, "detail": f"{len(holdings)} records"})

        company_ids = list({h["company_id"] for h in holdings if h.get("company_id")})

        # Step 3: current_market_data (ALL rows, then Python-filter)
        start = time.perf_counter()
        cm_res = db.table("current_market_data").select("company_id, current_price").execute()
        t = (time.perf_counter() - start) * 1000
        cm_data = cm_res.data or []
        relevant = sum(1 for r in cm_data if r["company_id"] in company_ids)
        results.append({"label": "current_market_data (ALL)", "elapsed_ms": t, "detail": f"{len(cm_data)} total, {relevant} relevant to user"})

        # Step 4: Companies enrichment
        start = time.perf_counter()
        co_res = db.table("companies").select("company_id, company_name, sector, exchange, currency").in_("company_id", company_ids).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "companies enrichment", "elapsed_ms": t, "detail": f"{len(co_res.data or [])} companies"})

        # Step 5: Exchange rates
        start = time.perf_counter()
        fx_res = db.table("exchange_rates").select("*").in_("base_currency", ["USD", "CAD"]).in_("target_currency", ["CAD", "USD"]).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "exchange_rates", "elapsed_ms": t, "detail": f"{len(fx_res.data or [])} pairs"})

        # Step 6: Dividends batch
        current_year = date.today().year
        start = time.perf_counter()
        div_res = db.table("portfolio_dividends").select("*").in_("account_id", account_ids_list).eq("fiscal_year", current_year).limit(10000).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_dividends (YTD)", "elapsed_ms": t, "detail": f"{len(div_res.data or [])} records"})

        # Step 7: Brokerages
        start = time.perf_counter()
        br_res = db.table("portfolio_brokerages").select("*").execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_brokerages", "elapsed_ms": t, "detail": f"{len(br_res.data or [])} records"})

        # Step 8: Users (preferred_currency) - using user_id since we have it
        start = time.perf_counter()
        user_res = db.table("users").select("preferred_currency").eq("id", USER_ID).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "users (preferred_currency)", "elapsed_ms": t, "detail": f"{user_res.data[0] if user_res.data else 'none'}"})

        # --- Performance chart queries (triggered when user visits Performance tab) ---

        # Step 9: Transactions (Trade)
        start = time.perf_counter()
        txn_res = db.table("portfolio_transactions").select("*").in_("account_id", account_ids_list).in_("activity_type", ["Trade"]).order("transaction_date", desc=True).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_transactions (Trades)", "elapsed_ms": t, "detail": f"{len(txn_res.data or [])} records"})

        # Step 10: All cash transactions
        start = time.perf_counter()
        cash_res = db.table("portfolio_transactions").select("*").in_("account_id", account_ids_list).order("transaction_date", desc=True).limit(10000).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_transactions (ALL cash)", "elapsed_ms": t, "detail": f"{len(cash_res.data or [])} records"})

        # Step 11: Price history (paginated)
        start = time.perf_counter()
        all_prices = []
        offset = 0
        batch_size = 1000
        while True:
            ph_res = db.table("price_history").select("company_id, price_date, close_price").in_("company_id", company_ids).lte("price_date", date.today().isoformat()).order("price_date", desc=False).range(offset, offset + batch_size - 1).execute()
            if not ph_res.data:
                break
            all_prices.extend(ph_res.data)
            offset += batch_size
            if len(ph_res.data) < batch_size:
                break
        t = (time.perf_counter() - start) * 1000
        pages = (offset // batch_size) + (1 if offset % batch_size else 0)
        results.append({"label": "price_history (paginated)", "elapsed_ms": t, "detail": f"{len(all_prices)} records, {pages} pages"})

        # Step 12: Split factors
        start = time.perf_counter()
        sp_res = db.table("splits").select("*").in_("company_id", company_ids).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "splits lookup", "elapsed_ms": t, "detail": f"{len(sp_res.data or [])} records"})

        # Step 13: Portfolio snapshots
        start = time.perf_counter()
        snap_res = db.table("portfolio_snapshots").select("*").in_("account_id", account_ids_list).gte("snapshot_date", (date.today() - timedelta(days=365)).isoformat()).lte("snapshot_date", date.today().isoformat()).order("snapshot_date", desc=False).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "portfolio_snapshots (1Y)", "elapsed_ms": t, "detail": f"{len(snap_res.data or [])} records"})

        _print_waterfall(results)

        total_db = sum(r["elapsed_ms"] for r in results)
        print(f"  DASHBOARD ONLY (steps 1-8):  {sum(r['elapsed_ms'] for r in results[:8]):.0f}ms")
        print(f"  + PERFORMANCE TAB (steps 9-13): {sum(r['elapsed_ms'] for r in results[8:]):.0f}ms")
        print()
        print("  Estimated total page load:")
        print(f"    DB queries:        {total_db:.0f}ms")
        print(f"    Network overhead:  ~200ms (HTTP + proxy + JSON)")
        print(f"    React render:      ~300ms (hydration + re-render)")
        total_est = total_db + 200 + 300
        print(f"    => TOTAL:          {total_est:.0f}ms ({total_est/1000:.1f}s)")


# ── 4. Tab Switch Simulation ─────────────────────────────────────────────────

@pytest.mark.anyio
class TestTabSwitchSimulation:
    """Simulate the exact DB query sequence when switching from Watchlist to Portfolio."""

    async def test_switch_watchlist_to_portfolio(self, db):
        results = []

        aids = _get_account_ids(db)
        cids = _get_company_ids(db, aids)
        print(f"\n  Accounts: {aids}")
        print(f"  Companies in holdings: {len(cids)}")

        # Phase 1: PortfolioTabShell mounts -> usePortfolioDashboard()
        print("\n  Phase 1: Dashboard load...")

        # Q1: portfolio_accounts
        start = time.perf_counter()
        accounts_res = db.table("portfolio_accounts").select("*").eq("user_id", USER_ID).execute()
        accounts = accounts_res.data or []
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D1] portfolio_accounts", "elapsed_ms": t, "detail": f"{len(accounts)} accounts"})

        # Q2: portfolio_holdings by account_ids
        start = time.perf_counter()
        holdings_res = db.table("portfolio_holdings").select("*").in_("account_id", aids).neq("quantity", 0).execute()
        holdings = holdings_res.data or []
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D2] portfolio_holdings", "elapsed_ms": t, "detail": f"{len(holdings)} holdings"})

        cids_from_holdings = list({h["company_id"] for h in holdings if h.get("company_id")})

        # Q3: current_market_data (all rows)
        start = time.perf_counter()
        cm_res = db.table("current_market_data").select("company_id, current_price, change_pct").execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D3] current_market_data (ALL)", "elapsed_ms": t, "detail": f"{len(cm_res.data or [])} rows"})

        # Q4: companies enrichment
        start = time.perf_counter()
        co_res = db.table("companies").select("*").in_("company_id", cids_from_holdings).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D4] companies enrichment", "elapsed_ms": t, "detail": f"{len(co_res.data or [])} companies"})

        # Q5: exchange_rates
        start = time.perf_counter()
        fx_res = db.table("exchange_rates").select("*").in_("base_currency", ["USD", "CAD"]).in_("target_currency", ["CAD", "USD"]).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D5] exchange_rates", "elapsed_ms": t, "detail": f"{len(fx_res.data or [])} pairs"})

        # Q6: portfolio_dividends (YTD)
        start = time.perf_counter()
        div_res = db.table("portfolio_dividends").select("*").in_("account_id", aids).eq("fiscal_year", date.today().year).limit(10000).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D6] portfolio_dividends (YTD)", "elapsed_ms": t, "detail": f"{len(div_res.data or [])} records"})

        # Q7: portfolio_brokerages
        start = time.perf_counter()
        br_res = db.table("portfolio_brokerages").select("*").execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D7] portfolio_brokerages", "elapsed_ms": t, "detail": f"{len(br_res.data or [])} records"})

        # Q8: users (preferred_currency)
        start = time.perf_counter()
        user_res = db.table("users").select("preferred_currency").eq("id", USER_ID).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[D8] users.preferred_currency", "elapsed_ms": t})

        # Phase 2: User clicks Performance tab -> /portfolio/performance?period=1Y
        print("  Phase 2: Performance tab load...")

        # Q9: portfolio_transactions (Trades)
        start = time.perf_counter()
        txn_res = db.table("portfolio_transactions").select("*").in_("account_id", aids).in_("activity_type", ["Trade"]).order("transaction_date", desc=True).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[P1] portfolio_transactions (Trades)", "elapsed_ms": t, "detail": f"{len(txn_res.data or [])} records"})

        # Q10: portfolio_transactions (ALL)
        start = time.perf_counter()
        cash_res = db.table("portfolio_transactions").select("*").in_("account_id", aids).order("transaction_date", desc=True).limit(10000).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[P2] portfolio_transactions (ALL)", "elapsed_ms": t, "detail": f"{len(cash_res.data or [])} records"})

        # Q11: price_history (paginated)
        start = time.perf_counter()
        all_prices = []
        offset = 0
        batch_size = 1000
        while True:
            ph_res = db.table("price_history").select("company_id, price_date, close_price").in_("company_id", cids_from_holdings).lte("price_date", date.today().isoformat()).order("price_date", desc=False).range(offset, offset + batch_size - 1).execute()
            if not ph_res.data:
                break
            all_prices.extend(ph_res.data)
            offset += batch_size
            if len(ph_res.data) < batch_size:
                break
        t = (time.perf_counter() - start) * 1000
        pages = (offset // batch_size) + (1 if offset % batch_size else 0)
        results.append({"label": "[P3] price_history (paginated)", "elapsed_ms": t, "detail": f"{len(all_prices)} records, {pages} pages"})

        # Q12: splits
        start = time.perf_counter()
        sp_res = db.table("splits").select("*").in_("company_id", cids_from_holdings).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[P4] splits lookup", "elapsed_ms": t, "detail": f"{len(sp_res.data or [])} records"})

        # Q13: portfolio_snapshots
        start = time.perf_counter()
        snap_res = db.table("portfolio_snapshots").select("*").in_("account_id", aids).gte("snapshot_date", (date.today() - timedelta(days=365)).isoformat()).lte("snapshot_date", date.today().isoformat()).order("snapshot_date", desc=False).execute()
        t = (time.perf_counter() - start) * 1000
        results.append({"label": "[P5] portfolio_snapshots (1Y)", "elapsed_ms": t, "detail": f"{len(snap_res.data or [])} records"})

        _print_waterfall(results)

        total_db = sum(r["elapsed_ms"] for r in results)
        dashboard_db = sum(r["elapsed_ms"] for r in results if r["label"].startswith("[D"))
        perf_db = sum(r["elapsed_ms"] for r in results if r["label"].startswith("[P"))

        print(f"  TAB SWITCH BREAKDOWN:")
        print(f"    Dashboard queries (8):  {dashboard_db:.0f}ms")
        print(f"    Performance queries (5): {perf_db:.0f}ms")
        print(f"    Total DB time:           {total_db:.0f}ms")
        print()
        est_network = 200
        est_render = 300
        est_total = total_db + est_network + est_render
        print(f"    Network overhead:        ~{est_network}ms")
        print(f"    React rendering:         ~{est_render}ms")
        print(f"    => TOTAL PAGE LOAD:      {est_total:.0f}ms ({est_total/1000:.1f}s)")

        # If Performance tab auto-fetches on mount
        est_with_perf = total_db + est_network + est_render
        if perf_db > 0:
            print(f"    (Performance tab costs {perf_db:.0f}ms in DB queries alone)")


# ── 5. Price History Data Coverage & Anomalies ───────────────────────────────

@pytest.mark.anyio
class TestPriceHistoryDataCoverage:
    """Check which companies have missing price data and detect unit mismatches."""

    async def test_price_coverage_and_anomalies(self, db):
        aids = _get_account_ids(db)
        holdings_res = db.table("portfolio_holdings").select("company_id, symbol").in_("account_id", aids).neq("quantity", 0).execute()
        holdings = holdings_res.data or []
        company_ids = list({h["company_id"] for h in holdings})
        cid_to_symbol = {h["company_id"]: h.get("symbol", "?") for h in holdings}

        # Check price_history coverage
        ph_res = db.table("price_history").select("company_id").in_("company_id", company_ids).execute()
        cids_with_data = {r["company_id"] for r in (ph_res.data or [])}

        missing = [cid for cid in company_ids if cid not in cids_with_data]
        has_data = [cid for cid in company_ids if cid in cids_with_data]

        print()
        print("=" * 100)
        print("  PRICE HISTORY DATA COVERAGE")
        print("=" * 100)
        print(f"  Total companies in portfolio:    {len(company_ids)}")
        print(f"  Companies WITH price data:       {len(has_data)}")
        print(f"  Companies WITHOUT price data:    {len(missing)}")
        if missing:
            missing_symbols = [cid_to_symbol[cid] for cid in missing]
            print(f"  Missing: {', '.join(missing_symbols)}")

        # Check date range of available prices
        if has_data:
            range_res = db.table("price_history").select("price_date").in_("company_id", has_data[:5]).order("price_date", desc=True).limit(1).execute()
            if range_res.data:
                print(f"  Latest price date: {range_res.data[0]['price_date']}")
            earliest_res = db.table("price_history").select("price_date").in_("company_id", has_data[:5]).order("price_date", desc=False).limit(1).execute()
            if earliest_res.data:
                print(f"  Earliest price date: {earliest_res.data[0]['price_date']}")

        # Check for price unit mismatches (>5x within 60 days)
        print()
        print("  -- Checking for price unit mismatches (>5x within 60 days) --")
        mismatch_count = 0
        for cid in has_data[:20]:
            prices_res = db.table("price_history").select("price_date, close_price").eq("company_id", cid).order("price_date", desc=False).execute()
            prices = prices_res.data or []
            for i in range(len(prices) - 1, 0, -1):
                nd = _parse_timestamp(prices[i]["price_date"])
                od = _parse_timestamp(prices[i - 1]["price_date"])
                days = (nd - od).days
                if 0 < days <= 60 and prices[i - 1]["close_price"] > 0:
                    ratio = prices[i]["close_price"] / prices[i - 1]["close_price"]
                    if ratio > 5:
                        mismatch_count += 1
                        print(f"    {cid_to_symbol.get(cid, f'cid={cid}')}: {od}={prices[i-1]['close_price']:.2f} -> {nd}={prices[i]['close_price']:.2f} (x{ratio:.1f}, {days}d)")
                        break
        if mismatch_count == 0:
            print("    No anomalies found in top 20 companies")


# ── 6. Cache Effectiveness ──────────────────────────────────────────────────

@pytest.mark.anyio
class TestCacheEffectiveness:
    """Measure benefit of current_market_data TTL cache."""

    async def test_cold_vs_warm_market_data(self, db):
        """Measure first call (cold) vs subsequent calls (warm) to current_market_data."""
        times = []
        for i in range(5):
            start = time.perf_counter()
            db.table("current_market_data").select("company_id, current_price").execute()
            t = (time.perf_counter() - start) * 1000
            times.append(t)

        print()
        print("=" * 100)
        print("  CURRENT_MARKET_DATA CACHE EFFECTIVENESS")
        print("=" * 100)
        print(f"  {'Call':<10s} {'Time (ms)':<15s}")
        print(f"  {'-'*10:<10s} {'-'*15:<15s}")
        for i, t in enumerate(times, 1):
            label = "Cold" if i == 1 else f"Warm #{i-1}"
            print(f"  {label:<10s} {t:<8.0f}ms")
        print(f"\n  Cold: {times[0]:.0f}ms | Warm avg: {sum(times[1:])/len(times[1:]):.0f}ms | Benefit: {times[0] - sum(times[1:])/len(times[1:]):.0f}ms")
        print(f"  Supabase query caching makes warm calls {times[0] / max(times[1], 0.1):.1f}x faster")

    async def test_price_history_page_size_impact(self, db):
        """Compare time to fetch price_history with different page sizes."""
        aids = _get_account_ids(db)
        cids = _get_company_ids(db, aids)
        if not cids:
            print("\n  No company IDs found, skipping")
            return

        page_sizes = [100, 500, 1000, 5000]
        target_date = date.today().isoformat()

        print()
        print("=" * 100)
        print("  PRICE_HISTORY PAGE SIZE IMPACT")
        print("=" * 100)
        print(f"  {'Page Size':<12s} {'Time (ms)':<12s} {'Pages':<8s} {'Records':<10s}")
        print(f"  {'-'*12:<12s} {'-'*12:<12s} {'-'*8:<8s} {'-'*10:<10s}")

        for size in page_sizes:
            start = time.perf_counter()
            all_prices = []
            offset = 0
            while True:
                res = db.table("price_history").select("company_id, price_date, close_price").in_("company_id", cids).lte("price_date", target_date).order("price_date", desc=False).range(offset, offset + size - 1).execute()
                if not res.data:
                    break
                all_prices.extend(res.data)
                offset += size
                if len(res.data) < size:
                    break
            t = (time.perf_counter() - start) * 1000
            pages = (offset // size) + (1 if offset % size else 0)
            print(f"  {size:<12d} {t:<8.0f}ms      {pages:<8d} {len(all_prices):<10d}")
