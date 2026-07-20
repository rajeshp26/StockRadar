"""
Calculate expected TFSA portfolio values from CSV + historical stock prices.

For each snapshot date:
1. Reconstruct holdings from CSV (cumulative BUY/SELL transactions)
2. Get historical stock prices from price_history table
3. Calculate: expected_portfolio_value = Σ(shares × close_price) + cash_balance
"""
import csv
import sys
import os
from datetime import datetime, date
from collections import defaultdict

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import get_supabase


def load_tfsa_transactions(csv_path: str) -> list:
    """Load all TFSA transactions from CSV."""
    rows = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('account_id') == 'HQ035ZHK5CAD':
                rows.append(row)
    return sorted(rows, key=lambda r: r['transaction_date'])


def get_symbol_to_company_id(supabase) -> dict:
    """Map ticker symbols to company_ids."""
    r = supabase.table('companies').select('company_id, ticker_symbol').execute()
    return {x['ticker_symbol']: x['company_id'] for x in r.data}


def get_price_on_date(supabase, company_id: int, target_date: str) -> float | None:
    """Get closing price on or before target_date."""
    r = (supabase.table('price_history')
         .select('close_price, price_date')
         .eq('company_id', company_id)
         .lte('price_date', target_date)
         .order('price_date', desc=True)
         .limit(1)
         .execute())
    if r.data:
        return float(r.data[0]['close_price'])
    return None


def reconstruct_holdings_at_date(transactions: list, target_date: str) -> dict:
    """Reconstruct holdings at a given date from transactions."""
    holdings = {}  # symbol -> {'quantity': float, 'avg_cost': float}
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

        if activity_type == 'MoneyMovement' or activity_type == 'BonusPayment':
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
                cash += net_cash  # negative for buys
            elif sub_type == 'SELL':
                if symbol in holdings:
                    holdings[symbol]['quantity'] -= quantity
                    if holdings[symbol]['quantity'] <= 0:
                        del holdings[symbol]
                cash += net_cash  # positive for sells

    return holdings, cash


def main():
    csv_path = os.path.join(os.path.dirname(__file__), 'activities-export-2026-05-10.csv')
    supabase = get_supabase()

    # Load transactions
    transactions = load_tfsa_transactions(csv_path)
    print(f"Loaded {len(transactions)} TFSA transactions")

    # Get symbol -> company_id mapping
    sym_to_cid = get_symbol_to_company_id(supabase)
    print(f"Loaded {len(sym_to_cid)} company mappings")

    # Get all TFSA snapshot dates from price_history perspective
    # We need to check what dates have prices available
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

    results = []
    for snap_date in snapshot_dates:
        holdings, cash = reconstruct_holdings_at_date(transactions, snap_date)

        # Calculate holdings value using historical prices
        holdings_value = 0.0
        missing_prices = []
        for symbol, h in holdings.items():
            cid = sym_to_cid.get(symbol)
            if cid:
                price = get_price_on_date(supabase, cid, snap_date)
                if price:
                    holdings_value += h['quantity'] * price
                else:
                    missing_prices.append(symbol)
            else:
                missing_prices.append(f"{symbol}(no cid)")

        total_expected = holdings_value + cash
        results.append({
            'date': snap_date,
            'holdings': dict(holdings),
            'holdings_value': holdings_value,
            'cash': cash,
            'total': total_expected,
            'missing': missing_prices
        })

        # Print first few for debugging
        if snap_date in ['2021-02-08', '2021-07-09', '2022-07-08', '2024-07-05', '2024-11-04', '2026-07-14']:
            print(f"\n{snap_date}:")
            print(f"  Holdings: {holdings}")
            print(f"  Holdings value: ${holdings_value:,.2f}")
            print(f"  Cash: ${cash:,.2f}")
            print(f"  Total expected: ${total_expected:,.2f}")
            if missing_prices:
                print(f"  Missing prices: {missing_prices}")

    # Print summary
    print("\n\n=== SUMMARY ===")
    print(f"{'Date':<12} {'Exp Holdings':>15} {'Exp Cash':>12} {'Exp Total':>12} {'Missing'}")
    print("-" * 80)
    for r in results:
        missing_str = ', '.join(r['missing']) if r['missing'] else ''
        print(f"{r['date']:<12} ${r['holdings_value']:>13,.2f} ${r['cash']:>10,.2f} ${r['total']:>10,.2f} {missing_str}")


if __name__ == '__main__':
    main()
