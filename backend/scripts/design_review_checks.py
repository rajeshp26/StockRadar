"""Check specific edge cases raised during design review."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter

from database import supabase

rows = lambda r: (r or {}).data or []

# 1. Check portfolio_events schema
print("=== EVENT STORE SCHEMA ===")
pe = supabase.table("portfolio_events").select("*").limit(1).execute()
if pe.data:
    cols = list(pe.data[0].keys())
    print(f"Columns: {cols}")
    print(f"idempotency_key: {pe.data[0].get('idempotency_key', 'N/A')}")
    print(f"event_version: {pe.data[0].get('event_version', 'N/A')}")
    print(f"aggregate_id: {pe.data[0].get('aggregate_id', 'N/A')}")
    print(f"aggregate_type: {pe.data[0].get('aggregate_type', 'N/A')}")

# 2. Check for duplicate idempotency_keys
print("\n=== DUPLICATE IDEMPOTENCY KEY CHECK ===")
all_events = supabase.table("portfolio_events").select("idempotency_key").execute()
all_keys = [e["idempotency_key"] for e in rows(all_events)]
print(f"Total events: {len(all_keys)}, Unique keys: {len(set(all_keys))}")
if len(all_keys) != len(set(all_keys)):
    dupes = [k for k, c in Counter(all_keys).items() if c > 1]
    print(f"DUPLICATE idempotency_keys FOUND: {dupes}")

# 3. Check for event_version gaps per account
print("\n=== VERSION GAPS ===")
for aid in [7, 8, 9, 10, 11, 12]:
    agg_id = f"account_{aid}"
    evts = (
        supabase.table("portfolio_events")
        .select("event_version")
        .eq("aggregate_id", agg_id)
        .order("event_version")
        .execute()
    )
    versions = [e["event_version"] for e in rows(evts)]
    if versions:
        expected = list(range(1, len(versions) + 1))
        if versions != expected:
            actual_set = set(versions)
            expected_set = set(range(1, max(versions) + 1))
            gaps = expected_set - actual_set
            print(f"  Account {aid}: {len(versions)} events, VERSION GAPS: {sorted(gaps)}")
        else:
            print(f"  Account {aid}: {len(versions)} events, versions 1..{len(versions)} — OK")
    else:
        print(f"  Account {aid}: NO EVENTS")

# 4. Check all event types used
print("\n=== EVENT TYPES USED ===")
evt_types = supabase.table("portfolio_events").select("event_type").execute()
type_counts = Counter(e["event_type"] for e in rows(evt_types))
for t, c in type_counts.most_common():
    print(f"  {t}: {c}")

# 5. Check duplicate event_types per account (should be unique per aggregate)
print("\n=== DUPLICATE EVENT TYPES PER ACCOUNT ===")
for aid in [7, 8, 9, 10, 11, 12]:
    agg_id = f"account_{aid}"
    evts = supabase.table("portfolio_events").select("event_type").eq("aggregate_id", agg_id).execute()
    types_list = [e["event_type"] for e in rows(evts)]
    dupes = {t for t, c in Counter(types_list).items() if c > 1}
    if dupes:
        print(f"  Account {aid}: DUPLICATE event types: {dupes}")
    else:
        print(f"  Account {aid}: all {len(types_list)} events have unique types — OK")

# 6. Check portfolio_holdings for all 6 accounts
print("\n=== HOLDING QUANTITIES PER ACCOUNT ===")
for aid in [7, 8, 9, 10, 11, 12]:
    ph = supabase.table("portfolio_holdings").select("company_id, quantity, total_cost").eq("account_id", aid).execute()
    total_qty = sum(float(h.get("quantity", 0)) for h in rows(ph))
    total_cost = sum(float(h.get("total_cost", 0)) for h in rows(ph))
    print(f"  Acct {aid}: {len(rows(ph))} holdings, total_qty={total_qty:.2f}, total_cost=${total_cost:.2f}")

# 7. portfolio_holdings column check
print("\n=== portfolio_holdings COLUMNS ===")
ph_sample = supabase.table("portfolio_holdings").select("*").limit(1).execute()
cols = list((ph_sample.data or [{}])[0].keys())
print(f"Columns: {cols}")
print(f"  Has current_value: {'current_value' in cols}")
print(f"  Has current_price: {'current_price' in cols}")

# 8. CASH row check
print("\n=== CASH BALANCE STORAGE ===")
ph_null = supabase.table("portfolio_holdings").select("account_id").is_("company_id", "null").execute()
if rows(ph_null):
    print(f"  Found CASH rows (company_id=null): {len(rows(ph_null))}")
    for r in rows(ph_null):
        print(f"    Account {r['account_id']}")
else:
    print("  No CASH rows found (company_id IS NULL) — blocked by NOT NULL constraint")

# 9. Check user 227 accounts that have 0 holdings
print("\n=== ACCOUNTS WITH 0 HOLDINGS ===")
accts = supabase.table("portfolio_accounts").select("account_id, account_type").eq("user_id", 227).execute()
for a in rows(accts):
    cnt = supabase.table("portfolio_holdings").select("*", count="exact").eq("account_id", a["account_id"]).execute()
    if cnt.count == 0:
        print(f"  User 227, Account {a['account_id']}: 0 holdings")
    else:
        has_null = supabase.table("portfolio_holdings").select("*", count="exact").eq("account_id", a["account_id"]).is_("company_id", "null").execute()
        print(f"  User 227, Account {a['account_id']} ({a['account_type']}): {cnt.count} holdings (CASH row: {'YES' if has_null.count > 0 else 'NO'})")

# 10. Check portfolio_snapshots schema — does it have holdings_json?
print("\n=== SNAPSHOT COLUMNS ===")
ps = supabase.table("portfolio_snapshots").select("*").limit(1).execute()
if ps.data:
    ps_cols = list(ps.data[0].keys())
    print(f"Columns: {ps_cols}")
    print(f"  Has holdings_json: {'holdings_json' in ps_cols}")
    print(f"  Has holdings_detail: {'holdings_detail' in ps_cols}")

# 11. Check for portfolio_holdings with company_id not in current_market_data
print("\n=== PRICE COVERAGE ===")
ph_all = supabase.table("portfolio_holdings").select("company_id, account_id, symbol").execute()
company_ids_in_ph = set()
for h in rows(ph_all):
    cid = h.get("company_id")
    if cid:
        company_ids_in_ph.add(cid)
cmd = supabase.table("current_market_data").select("company_id").execute()
company_ids_in_cmd = set(c["company_id"] for c in rows(cmd))
missing_from_cmd = company_ids_in_ph - company_ids_in_cmd
if missing_from_cmd:
    print(f"  Holdings companies NOT in current_market_data ({len(missing_from_cmd)}):")
    ph_lookup = {(h["company_id"], h.get("symbol", "?")) for h in rows(ph_all) if h.get("company_id") in missing_from_cmd}
    syms = sorted(set(s for _, s in ph_lookup))
    for s in syms:
        print(f"    {s}")
else:
    print("  All holdings companies have prices in current_market_data")

# 12. Check if current_market_data has the 5 companies from issue #7
print("\n=== ISSUE #7: MISSING 5 COMPANIES ===")
cmd_cols = supabase.table("current_market_data").select("*").limit(1).execute()
cmd_sample_cols = list((cmd_cols.data or [{}])[0].keys()) if cmd_cols.data else []
print(f"  current_market_data columns: {cmd_sample_cols}")
# Find the price column
price_col = "close_price" if "close_price" in cmd_sample_cols else ("price" if "price" in cmd_sample_cols else cmd_sample_cols)
for cid in [3139, 3140, 3144, 3155, 3159]:
    q = supabase.table("current_market_data").select("company_id, *").eq("company_id", cid).execute()
    if rows(q):
        print(f"  Company {cid}: {rows(q)[0]}")
    else:
        print(f"  Company {cid}: STILL MISSING from current_market_data")

# 13. Check account 9's initial_holding_set data for versions
print("\n=== ACCOUNT 9 EVENT DATA ===")
a9 = supabase.table("portfolio_events").select("event_version, event_type, data").eq("aggregate_id", "account_9").order("event_version").execute()
for e in rows(a9):
    print(f"  version={e['event_version']}, type={e['event_type']}, data_keys={list(e['data'].keys()) if isinstance(e.get('data'), dict) else 'N/A'}")

print("\n=== REVIEW COMPLETE ===")
