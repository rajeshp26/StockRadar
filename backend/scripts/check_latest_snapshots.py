"""Show latest snapshots per account."""
from database import supabase
r = supabase.table("portfolio_snapshots").select("account_id,snapshot_date,total_value,cash_balance,net_deposits,holdings_market_value,cost_basis").order("snapshot_date", desc=True).limit(20).execute()
seen = set()
for s in r.data:
    aid = s["account_id"]
    if aid not in seen:
        seen.add(aid)
        print(f"Account {aid}: {s['snapshot_date']} total=${s['total_value']:,.2f} cash=${s['cash_balance']:,.2f} market=${s['holdings_market_value']:,.2f} cost=${s['cost_basis']:,.2f}")
