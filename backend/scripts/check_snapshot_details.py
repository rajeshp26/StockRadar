import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import date
from database import supabase

def query(label, filters, order=None, limit=None):
    q = supabase.table("portfolio_snapshots").select(
        "account_id, snapshot_date, total_value, job_id, data_quality_flag, holdings_market_value, cost_basis, cash_balance"
    )
    for col, op, val in filters:
        if op == "eq":
            q = q.eq(col, val)
        elif op == "gte":
            q = q.gte(col, val)
        elif op == "lte":
            q = q.lte(col, val)
        elif op == "in":
            q = q.in_(col, val)
    if order:
        if isinstance(order, str):
            q = q.order(order)
        else:
            q = q.order(order[0], desc=order[1])
    if limit:
        q = q.limit(limit)
    res = q.execute()
    rows = res.data or []
    print(f"\n{'='*80}")
    print(f"  {label}  ({len(rows)} rows)")
    print(f"{'='*80}")
    if not rows:
        print("  (no rows)")
        return rows
    for r in rows:
        tv = float(r.get('total_value') or 0)
        hmv = float(r.get('holdings_market_value') or 0)
        cb = float(r.get('cost_basis') or 0)
        cbal = float(r.get('cash_balance') or 0)
        print(f"  Acct {r['account_id']:>3}  {r['snapshot_date']}  total={tv:>14,.2f}  hmv={hmv:>14,.2f}  cost={cb:>14,.2f}  cash={cbal:>12,.2f}  job={r.get('job_id','')}  dq={r.get('data_quality_flag','')}")
    return rows

# ── Accounts 10, 11, 12: Jul 9-11 ──
for acct in [10, 11, 12]:
    query(
        f"Account {acct} — Jul 9-11",
        [("account_id", "eq", acct), ("snapshot_date", "gte", "2026-07-09"), ("snapshot_date", "lte", "2026-07-11")],
        order="snapshot_date"
    )

# ── Accounts 10, 11, 12: Jul 31 ──
for acct in [10, 11, 12]:
    query(
        f"Account {acct} — Jul 31",
        [("account_id", "eq", acct), ("snapshot_date", "eq", "2026-07-31")],
        order="snapshot_date"
    )

# ── Account 7: Jul 9-11 ──
query(
    "Account 7 — Jul 9-11",
    [("account_id", "eq", 7), ("snapshot_date", "gte", "2026-07-09"), ("snapshot_date", "lte", "2026-07-11")],
    order="snapshot_date"
)

# ── Account 9: ALL snapshots ──
query(
    "Account 9 — ALL snapshots",
    [("account_id", "eq", 9)],
    order="snapshot_date"
)

# ── Accounts 10, 11, 12: FIRST snapshot ──
for acct in [10, 11, 12]:
    query(
        f"Account {acct} — FIRST snapshot",
        [("account_id", "eq", acct)],
        order="snapshot_date",
        limit=1
    )

# ── Accounts 10, 11, 12: LAST snapshot ──
for acct in [10, 11, 12]:
    query(
        f"Account {acct} — LAST snapshot",
        [("account_id", "eq", acct)],
        order=("snapshot_date", True),
        limit=1
    )

print("\n\nDone.")
