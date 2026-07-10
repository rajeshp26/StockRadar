import os
os.environ["ENVIRONMENT"] = "development"
from database import supabase as client
from datetime import date, datetime
from collections import defaultdict

# ── Check RY (Royal Bank) price and splits ──
print("=" * 60)
print("TRACING ACCOUNTS 10, 11, 12 SPIKE")
print("=" * 60)

# Get RY info
ry = client.table("companies").select("*").eq("ticker_symbol", "RY").execute()
print(f"\nRY company: {ry.data}")

if ry.data:
    cid = ry.data[0]["company_id"]
    
    # Check RY split factors
    splits = client.table("splits").select("*").eq("company_id", cid).order("report_date").execute()
    print(f"\nRY splits: {[(s['report_date'], s['split_factor']) for s in (splits.data or [])]}")
    
    # Check RY price_history around the spike period
    ph = client.table("price_history").select("price_date, close_price").eq("company_id", cid).gte("price_date", "2026-05-01").order("price_date").execute()
    print(f"\nRY price_history (May-Jun 2026):")
    for p in (ph.data or []):
        print(f"  {p['price_date']}: ${p['close_price']}")
    
    # Check RY current_market_data
    cmd = client.table("current_market_data").select("*").eq("company_id", cid).execute()
    print(f"\nRY current_market_data: {cmd.data}")

# ── Check TD (Toronto Dominion) ──
td = client.table("companies").select("*").eq("ticker_symbol", "TD").execute()
print(f"\nTD company: {td.data}")
if td.data:
    cid = td.data[0]["company_id"]
    splits = client.table("splits").select("*").eq("company_id", cid).order("report_date").execute()
    print(f"TD splits: {[(s['report_date'], s['split_factor']) for s in (splits.data or [])]}")
    ph = client.table("price_history").select("price_date, close_price").eq("company_id", cid).gte("price_date", "2026-05-01").order("price_date").execute()
    print(f"TD price_history (May-Jun 2026):")
    for p in (ph.data or []):
        print(f"  {p['price_date']}: ${p['close_price']}")
    cmd = client.table("current_market_data").select("*").eq("company_id", cid).execute()
    print(f"TD current_market_data: {cmd.data}")

# ── Check ENB ──
enb = client.table("companies").select("*").eq("ticker_symbol", "ENB").execute()
print(f"\nENB company: {enb.data}")
if enb.data:
    cid = enb.data[0]["company_id"]
    splits = client.table("splits").select("*").eq("company_id", cid).order("report_date").execute()
    print(f"ENB splits: {[(s['report_date'], s['split_factor']) for s in (splits.data or [])]}")
    ph = client.table("price_history").select("price_date, close_price").eq("company_id", cid).gte("price_date", "2026-05-01").order("price_date").execute()
    print(f"ENB price_history (May-Jun 2026):")
    for p in (ph.data or []):
        print(f"  {p['price_date']}: ${p['close_price']}")
    cmd = client.table("current_market_data").select("*").eq("company_id", cid).execute()
    print(f"ENB current_market_data: {cmd.data}")

# ── Check SHOP ──
shop = client.table("companies").select("*").eq("ticker_symbol", "SHOP").execute()
print(f"\nSHOP company: {shop.data}")
if shop.data:
    cid = shop.data[0]["company_id"]
    splits = client.table("splits").select("*").eq("company_id", cid).order("report_date").execute()
    print(f"SHOP splits: {[(s['report_date'], s['split_factor']) for s in (splits.data or [])]}")
    ph = client.table("price_history").select("price_date, close_price").eq("company_id", cid).gte("price_date", "2026-05-01").order("price_date").execute()
    print(f"SHOP price_history (May-Jun 2026):")
    for p in (ph.data or []):
        print(f"  {p['price_date']}: ${p['close_price']}")
    cmd = client.table("current_market_data").select("*").eq("company_id", cid).execute()
    print(f"SHOP current_market_data: {cmd.data}")

# ── Check AAPL ──
aapl = client.table("companies").select("*").eq("ticker_symbol", "AAPL").execute()
print(f"\nAAPL company: {aapl.data}")
if aapl.data:
    cid = aapl.data[0]["company_id"]
    splits = client.table("splits").select("*").eq("company_id", cid).order("report_date").execute()
    print(f"AAPL splits: {[(s['report_date'], s['split_factor']) for s in (splits.data or [])]}")
    ph = client.table("price_history").select("price_date, close_price").eq("company_id", cid).gte("price_date", "2026-05-01").order("price_date").execute()
    print(f"AAPL price_history (May-Jun 2026):")
    for p in (ph.data or []):
        print(f"  {p['price_date']}: ${p['close_price']}")
    cmd = client.table("current_market_data").select("*").eq("company_id", cid).execute()
    print(f"AAPL current_market_data: {cmd.data}")

# ── Deep trace: Account 10 snapshot May 31 vs Jun 30 ──
print(f"\n{'='*60}")
print("ACCOUNT 10 (Main TFSA) — SNAPSHOT COMPARISON")
print(f"{'='*60}")
for date_str in ["2026-05-31", "2026-06-30"]:
    snap = client.table("portfolio_snapshots").select("*").eq("account_id", 10).eq("snapshot_date", date_str).execute()
    if snap.data:
        s = snap.data[0]
        print(f"\n  {date_str}:")
        print(f"    total_value:       ${s['total_value']:,.2f}")
        print(f"    holdings_market:   ${s.get('holdings_market_value',0):,.2f}")
        print(f"    cash_balance:      ${s.get('cash_balance',0):,.2f}")
        print(f"    net_deposits:      ${s.get('net_deposits',0):,.2f}")
        hj = s.get("holdings_json") or []
        for h in hj:
            print(f"    {h['symbol']:8s} qty={h['quantity']:>8.2f} px=${h['current_price']:>8.2f} val=${h['current_value']:>10,.2f}")

# ── Also show live enrich_holdings_with_prices values for these symbols ──
print(f"\n{'='*60}")
print("LIVE enrich_holdings_with_prices VALUES")
print(f"{'='*60}")
from application.services.portfolio_service import PortfolioService
from infrastructure.repositories.portfolio_repository import PortfolioRepository
import asyncio

async def check():
    repo = PortfolioRepository()
    svc = PortfolioService()
    for aid, name in [(10, "Main TFSA"), (11, "Retirement RRSP"), (12, "Margin")]:
        holdings = repo.get_account_holdings(aid)
        enriched = await svc.enrich_holdings_with_prices(holdings)
        enriched.sort(key=lambda h: float(h.get("current_value") or 0), reverse=True)
        total = sum(float(h.get("current_value") or 0) for h in enriched)
        print(f"\n  Account {aid} ({name}):")
        for h in enriched:
            print(f"    {h['symbol']:8s} qty={float(h.get('quantity',0)):>8.2f} px=${float(h.get('current_price',0)):>8.2f} val=${float(h.get('current_value',0)):>10,.2f} source={h.get('_price_source','?')}")
        print(f"    TOTAL: ${total:,.2f}")

asyncio.run(check())
