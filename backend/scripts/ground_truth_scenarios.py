"""Ground-truth audit: examine every table, every account, every edge case before writing the cutover plan."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from database import supabase

rows = lambda r: (r or {}).data or []

print("=" * 90)
print("TABLE EXISTENCE CHECK")
print("=" * 90)
for t in ["portfolio_events", "portfolio_transactions", "portfolio_holdings",
           "portfolio_snapshots", "portfolio_accounts", "portfolio_brokerages",
           "current_market_data", "price_sources", "price_history", "companies",
           "users", "import_batches", "portfolio_import_history"]:
    # Use count='exact' to verify table exists + get row count
    try:
        r = supabase.table(t).select("*", count="exact").limit(1).execute()
        cnt = r.count
        print(f"  {t:<35} EXISTS  rows={cnt}")
    except Exception as e:
        print(f"  {t:<35} ERROR  {str(e)[:80]}")

print()

print("=" * 90)
print("USERS AND THEIR ACCOUNTS")
print("=" * 90)
users = supabase.table("users").select("user_id, email, username").execute()
for u in users.data or []:
    accts = supabase.table("portfolio_accounts").select("account_id, account_name, account_type, currency, is_active").eq("user_id", u["user_id"]).execute()
    for a in accts.data or []:
        h_count_r = supabase.table("portfolio_holdings").select("*", count="exact").eq("account_id", a["account_id"]).execute()
        t_count = (supabase.table("portfolio_transactions").select("*", count="exact").eq("account_id", a["account_id"]).execute()).count or 0
        e_count = (supabase.table("portfolio_events").select("*", count="exact").eq("aggregate_id", f"account_{a['account_id']}").execute()).count or 0
        s_count = (supabase.table("portfolio_snapshots").select("*", count="exact").eq("account_id", a["account_id"]).execute()).count or 0
        h_count = len(h_count_r.data or [])
        print(f"  User {u['user_id']} ({u['email']:>30}): Acct {a['account_id']} {a['account_type']:<18} "
              f"holdings={h_count}  txn={t_count}  events={e_count}  snaps={s_count}")
        if e_count > 0:
            # Check event date range
            r2 = supabase.table("portfolio_events").select("event_type, created_at").eq("aggregate_id", f"account_{a['account_id']}").order("created_at").limit(1).execute()
            first_ev = (r2.data or [{}])[0]
            r3 = supabase.table("portfolio_events").select("event_type, created_at").eq("aggregate_id", f"account_{a['account_id']}").order("created_at", desc=True).limit(1).execute()
            last_ev = (r3.data or [{}])[0]
            print(f"           Events: first={first_ev.get('created_at','?')[:19]} type={first_ev.get('event_type','?')}  "
                  f"last={last_ev.get('created_at','?')[:19]} type={last_ev.get('event_type','?')}")

print()

print("=" * 90)
print("HOLDINGS ANALYSIS (what would replay produce vs portfolio_holdings)")
print("=" * 90)
from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import ReplayEngine

event_store = EventStore()
engine = ReplayEngine(event_store)
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
replay_prices = {}
for row in cmr.data or []:
    cid, px = row.get("company_id"), row.get("current_price")
    if cid and px:
        replay_prices[int(cid)] = {"price": float(px), "price_date": date(2026, 7, 8)}

for u in users.data or []:
    accts = supabase.table("portfolio_accounts").select("account_id, account_name, account_type").eq("user_id", u["user_id"]).execute()
    for a in accts.data or []:
        aid = a["account_id"]
        # Replay
        try:
            state = engine.replay_to_date(aid, date(2026, 7, 8))
            replay_count = len(state.holdings)
            replay_cash = float(state.cash_balance)
        except Exception as e:
            replay_count = 0
            replay_cash = 0
            print(f"  REPLAY FAILED: Acct {aid}: {e}")

        # portfolio_holdings
        ph = supabase.table("portfolio_holdings").select("company_id, quantity, total_cost").eq("account_id", aid).execute()
        ph_count = len(ph.data or [])
        ph_cash = sum(float(h.get("total_cost", 0)) for h in (ph.data or []))  # wrong, just for reference

        # Compare
        match = "MATCH" if replay_count == ph_count else "MISMATCH"
        print(f"  Acct {aid} ({a['account_type']}): replay_holdings={replay_count}  "
              f"ph_holdings={ph_count}  replay_cash=${replay_cash:.2f}  [{match}]")
        if replay_count != ph_count:
            replay_cids = set(state.holdings.keys())
            ph_cids = set(int(h["company_id"]) for h in (ph.data or []) if h.get("company_id"))
            only_replay = replay_cids - ph_cids
            only_ph = ph_cids - replay_cids
            if only_replay:
                print(f"    In replay but NOT in portfolio_holdings: {sorted(only_replay)[:10]}")
            if only_ph:
                print(f"    In portfolio_holdings but NOT in replay: {sorted(only_ph)[:10]}")

print()

print("=" * 90)
print("TRANSACTIONS vs EVENTS: check all 6 accounts for completeness")
print("=" * 90)
# For accounts 7 and 8 (full transaction history) - confirm events == transactions
for aid in [7, 8]:
    t = (supabase.table("portfolio_transactions").select("*", count="exact").eq("account_id", aid).execute()).count or 0
    e = (supabase.table("portfolio_events").select("*", count="exact").eq("aggregate_id", f"account_{aid}").execute()).count or 0
    print(f"  Acct {aid}: transactions={t}  events={e}")
    if t > 0:
        t_types = supabase.table("portfolio_transactions").select("activity_type, activity_sub_type").eq("account_id", aid).execute()
        t_set = set(f"{r['activity_type']}/{r.get('activity_sub_type','')}" for r in (t_types.data or []))
        print(f"    Transaction types: {sorted(t_set)}")

for aid in [9, 10, 11, 12]:
    e_r = supabase.table("portfolio_events").select("event_type, data").eq("aggregate_id", f"account_{aid}").execute()
    types = set(r["event_type"] for r in (e_r.data or []))
    print(f"  Acct {aid}: events={len(e_r.data or [])} types={types}")

print()

print("=" * 90)
print("CURRENT_MARKET_DATA: do we have prices for every company in holdings?")
print("=" * 90)
all_ph = supabase.table("portfolio_holdings").select("company_id, symbol").execute()
ph_companies = set(int(h["company_id"]) for h in (all_ph.data or []) if h.get("company_id"))
cmd = supabase.table("current_market_data").select("company_id").execute()
cmd_companies = set(int(r["company_id"]) for r in (cmd.data or []))
missing = ph_companies - cmd_companies
print(f"  Companies in portfolio_holdings: {len(ph_companies)}")
print(f"  Companies in current_market_data: {len(cmd_companies)}")
print(f"  Missing prices: {len(missing)} — {sorted(missing) if missing else 'NONE'}")

print()

print("=" * 90)
print("PRICE_SOURCES / PRICE_HISTORY: what does the UI current use?")
print("=" * 90)
try:
    ps = supabase.table("price_sources").select("*", count="exact").execute()
    print(f"  price_sources: {ps.count} rows")
except Exception:
    print("  price_sources: TABLE DOES NOT EXIST")
phist = supabase.table("price_history").select("company_id", count="exact").execute()
print(f"  price_history: {phist.count} rows")

print()

print("=" * 90)
print("PORTFOLIO_SNAPSHOTS: latest per account")
print("=" * 90)
for aid in [7, 8, 9, 10, 11, 12]:
    s = supabase.table("portfolio_snapshots").select("snapshot_date, total_value").eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
    if s.data:
        print(f"  Acct {aid}: latest {s.data[0]['snapshot_date']} — ${s.data[0]['total_value']:,.2f}")
    else:
        print(f"  Acct {aid}: NO SNAPSHOTS")

print()

print("=" * 90)
print("IMPORT HISTORY: what was the last import?")
print("=" * 90)
try:
    ih = supabase.table("portfolio_import_history").select("*", count="exact").order("created_at", desc=True).limit(5).execute()
    if ih.data:
        for r in ih.data:
            print(f"  batch_id={r.get('import_batch_id','?')[:20]} status={r.get('status','?')} created={r.get('created_at','?')}")
    else:
        print("  No import history found")
except Exception as e:
    print(f"  portfolio_import_history: {e}")

print()

print("=" * 90)
print("CONCURRENT IMPORT RISK: any active imports running?")
print("=" * 90)
# Check if there's a scheduler running
from config import settings

print(f"  Environment: {settings.ENVIRONMENT}")
print(f"  Replay enabled: {getattr(settings, 'ENABLE_EVENT_REPLAY_SNAPSHOTS', False)}")
print(f"  Comparison mode: {getattr(settings, 'EVENT_REPLAY_COMPARISON_MODE', False)}")
