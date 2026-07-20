"""Verify CDR backfill results."""
import sys
sys.path.insert(0, '.')
from database import supabase

result = supabase.table('companies').select('company_id, ticker_symbol, cdr_ratio, cdr_ratio_date').not_.is_('cdr_ratio', 'null').execute()
cdr_cids = [r['company_id'] for r in (result.data or [])]

cmr = supabase.table('current_market_data').select('company_id, current_price').in_('company_id', cdr_cids).execute()
prices_by_cid = {r['company_id']: float(r['current_price']) for r in (cmr.data or [])}

print("CDR Ratio Verification:")
print(f"{'Symbol':<10} {'TSX Price':>12} {'Ratio':>10} {'CDR Price':>12} {'Expected~10':>12}")
print("-" * 60)
for row in sorted(result.data or [], key=lambda x: x.get('cdr_ratio', 0)):
    cid = row['company_id']
    sym = row['ticker_symbol']
    ratio = float(row['cdr_ratio'])
    tsx = prices_by_cid.get(cid, 0)
    cdr = tsx / ratio if ratio else 0
    flag = "OK" if 5 < ratio < 25 else "CHECK"
    print(f"{sym:<10} ${tsx:>10.2f} {ratio:>10.2f} ${cdr:>10.2f}   {flag}")
