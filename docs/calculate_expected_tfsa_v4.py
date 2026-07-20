"""
Calculate expected TFSA portfolio values from CSV + historical stock prices.
Optimized version - fetches all prices at once instead of per-date/symbol.
"""
import csv
import sys
import os
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import get_supabase


def load_tfsa_transactions(csv_path: str) -> list:
    rows = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('account_id') == 'HQ035ZHK5CAD':
                rows.append(row)
    return sorted(rows, key=lambda r: r['transaction_date'])


def main():
    csv_path = os.path.join(os.path.dirname(__file__), 'activities-export-2026-05-10.csv')
    supabase = get_supabase()

    # Load transactions
    transactions = load_tfsa_transactions(csv_path)
    print(f"Loaded {len(transactions)} TFSA transactions")

    # Get symbol -> company_id mapping
    r = supabase.table('companies').select('company_id, ticker_symbol').execute()
    sym_to_cid = {x['ticker_symbol']: x['company_id'] for x in r.data}
    print(f"Loaded {len(sym_to_cid)} company mappings")

    # Get all unique symbols from transactions
    tx_symbols = set(tx.get('symbol', '') for tx in transactions if tx.get('symbol'))
    print(f"TFSA symbols: {tx_symbols}")

    # Get company_ids for TFSA symbols
    tf_cid = {s: sym_to_cid[s] for s in tx_symbols if s in sym_to_cid}
    print(f"TFSA company_ids: {tf_cid}")

    # Fetch ALL price_history for these company_ids at once
    all_prices = {}  # (company_id, date) -> close_price
    for symbol, cid in tf_cid.items():
        r = supabase.table('price_history').select('price_date, close_price').eq('company_id', cid).execute()
        for row in r.data:
            all_prices[(cid, row['price_date'])] = float(row['close_price'])
        print(f"  {symbol}: {len(r.data)} price rows")

    print(f"Total price records: {len(all_prices)}")

    # Get closest price on or before target date
    def get_price(company_id, target_date):
        best = None
        for (cid, pdate), price in all_prices.items():
            if cid == company_id and pdate <= target_date:
                if best is None or pdate > best[0]:
                    best = (pdate, price)
        return best[1] if best else None

    snapshot_dates = [
        '2021-02-08', '2021-03-10', '2021-04-09', '2021-05-10', '2021-06-09',
        '2021-07-09', '2021-08-09', '2021-09-08', '2021-10-08', '2021-11-08',
        '2021-12-08', '2022-01-07', '2022-02-07', '2022-03-09', '2022-04-08',
        '2022-05-09', '2022-06-08', '2022-07-08', '2022-08-08', '2022-09-07',
        '2022-10-07', '2022-11-07', '2022-12-07', '2023-01-06', '2023-02-06',
        '2023-03-08', '2023-04-07', '2023-05-08', '2023-06-07', '2023-07-07',
        '2023-08-07', '2023-09-06', '2023-10-06', '2023-11-06', '2023-12-06',
        '2024-01-05', '2024-02-05', '2024-03-06', '2024-04-05', '2024-05-06',
        '2024-06-05', '2024-07-05', '2024-08-05', '2024-09-04', '2024-10-04',
        '2024-11-04', '2024-12-04', '2025-01-03', '2025-02-04', '2025-03-07',
        '2025-04-07', '2025-05-07', '2025-06-06', '2025-07-07', '2025-08-06',
        '2025-09-05', '2025-10-07', '2025-11-06', '2025-12-08', '2026-01-08',
        '2026-02-09', '2026-03-11', '2026-04-10', '2026-05-31', '2026-07-01',
        '2026-07-14'
    ]

    def reconstruct_holdings_at_date(target_date):
        holdings = {}
        cash = 0.0
        for tx in transactions:
            tx_date = tx['transaction_date']
            if tx_date > target_date:
                break
            activity_type = tx.get('activity_type', '')
            sub_type = tx.get('activity_sub_type', '')
            symbol = tx.get('symbol', '')
            quantity = float(tx.get('quantity', '0') or '0')
            unit_price = float(tx.get('unit_price', '0') or '0')
            net_cash = float(tx.get('net_cash_amount', '0') or '0')

            if activity_type in ('MoneyMovement', 'BonusPayment'):
                cash += net_cash
            elif activity_type == 'Trade':
                if sub_type == 'BUY':
                    if symbol not in holdings:
                        holdings[symbol] = {'quantity': 0, 'avg_cost': 0}
                    old_qty = holdings[symbol]['quantity']
                    old_cost = holdings[symbol]['avg_cost']
                    new_qty = old_qty + quantity
                    if new_qty > 0:
                        holdings[symbol]['avg_cost'] = (old_qty * old_cost + quantity * unit_price) / new_qty
                    holdings[symbol]['quantity'] = new_qty
                    cash += net_cash
                elif sub_type == 'SELL':
                    if symbol in holdings:
                        holdings[symbol]['quantity'] -= quantity
                        if holdings[symbol]['quantity'] <= 0:
                            del holdings[symbol]
                    cash += net_cash
        return holdings, cash

    results = []
    for snap_date in snapshot_dates:
        holdings, cash = reconstruct_holdings_at_date(snap_date)
        holdings_value = 0.0
        missing = []
        for symbol, h in holdings.items():
            cid = tf_cid.get(symbol)
            if cid:
                price = get_price(cid, snap_date)
                if price:
                    holdings_value += h['quantity'] * price
                else:
                    missing.append(symbol)
            else:
                missing.append(f"{symbol}(no cid)")
        total = holdings_value + cash
        results.append({
            'date': snap_date,
            'holdings': dict(holdings),
            'holdings_value': holdings_value,
            'cash': cash,
            'total': total,
            'missing': missing
        })

    print("\n=== EXPECTED TFSA PORTFOLIO VALUES ===")
    print(f"{'Date':<12} {'Exp PV':>12} {'Exp CB':>12} {'Exp ND':>12} {'Missing Prices'}")
    print("-" * 80)
    for r in results:
        missing_str = ', '.join(r['missing']) if r['missing'] else '-'
        print(f"{r['date']:<12} ${r['total']:>10,.2f} ${r['cash']:>10,.2f} ${r['cash']:>10,.2f} {missing_str}")

    # Print detailed holdings for key dates
    for snap_date in ['2021-02-08', '2024-07-05', '2024-11-04', '2026-07-14']:
        for r in results:
            if r['date'] == snap_date:
                print(f"\n{snap_date} detailed holdings:")
                for sym, h in r['holdings'].items():
                    cid = tf_cid.get(sym)
                    price = get_price(cid, snap_date) if cid else None
                    print(f"  {sym}: {h['quantity']:.0f} shares @ ${price:.2f} = ${h['quantity']*price:,.2f}")
                print(f"  Cash: ${r['cash']:,.2f}")
                print(f"  Total: ${r['total']:,.2f}")


if __name__ == '__main__':
    main()
