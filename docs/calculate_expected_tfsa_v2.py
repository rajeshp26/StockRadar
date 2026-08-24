import csv
from datetime import date, datetime
from decimal import Decimal
from collections import defaultdict

csv_path = r"C:\Project\StockerPro\StockerPro\docs\activities-export-2026-05-10.csv"
TFSA_EXTERNAL_ID = "HQ035ZHK5CAD"

# Parse CSV
transactions = []
with open(csv_path, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['account_id'] == TFSA_EXTERNAL_ID:
            txn_date = datetime.strptime(row['transaction_date'], '%Y-%m-%d').date()
            transactions.append({
                'date': txn_date,
                'activity_type': row['activity_type'],
                'activity_sub_type': row['activity_sub_type'],
                'net_cash': Decimal(row['net_cash_amount']) if row['net_cash_amount'] else Decimal('0'),
                'symbol': row['symbol'].strip() if row['symbol'] else '',
                'quantity': Decimal(row['quantity']) if row['quantity'] else Decimal('0'),
                'unit_price': Decimal(row['unit_price']) if row['unit_price'] else Decimal('0'),
            })

transactions.sort(key=lambda x: x['date'])

# Track holdings: symbol -> {quantity, total_cost}
holdings = defaultdict(lambda: {'quantity': Decimal('0'), 'total_cost': Decimal('0')})

def get_net_deposits(target_date):
    total = Decimal('0')
    for txn in transactions:
        if txn['date'] <= target_date and txn['activity_type'] in ('MoneyMovement', 'BonusPayment'):
            total += txn['net_cash']
    return total

def get_cash_balance(target_date):
    total = Decimal('0')
    for txn in transactions:
        if txn['date'] <= target_date:
            if txn['activity_type'] in ('MoneyMovement', 'BonusPayment'):
                total += txn['net_cash']
            elif txn['activity_type'] == 'Trade':
                total += txn['net_cash']
            elif txn['activity_type'] == 'Dividend':
                total += txn['net_cash']
            elif txn['activity_type'] == 'ReturnOfCapital':
                total += txn['net_cash']
            elif txn['activity_type'] == 'Interest':
                total += txn['net_cash']
            elif txn['activity_type'] == 'Tax':
                total += txn['net_cash']
    return total

def get_holdings_cost_basis(target_date):
    """Reconstruct holdings at target_date and return total cost basis"""
    local_holdings = defaultdict(lambda: {'quantity': Decimal('0'), 'total_cost': Decimal('0')})
    for txn in transactions:
        if txn['date'] <= target_date and txn['activity_type'] == 'Trade' and txn['symbol']:
            sym = txn['symbol']
            qty = txn['quantity']
            price = txn['unit_price']
            if txn['activity_sub_type'] == 'BUY':
                cost = abs(qty * price)
                local_holdings[sym]['quantity'] += qty
                local_holdings[sym]['total_cost'] += cost
            elif txn['activity_sub_type'] == 'SELL':
                # Reduce holdings proportionally
                if local_holdings[sym]['quantity'] > 0:
                    sold_fraction = qty / local_holdings[sym]['quantity']
                    local_holdings[sym]['quantity'] += qty  # qty is negative for sells
                    local_holdings[sym]['total_cost'] *= (1 + sold_fraction)
            elif txn['activity_sub_type'] in ('SPLIT', 'SUBDIVISION', 'CONSOLIDATION'):
                # Handle stock splits - adjust quantity, keep cost basis same
                if local_holdings[sym]['quantity'] > 0:
                    local_holdings[sym]['quantity'] += qty
            elif txn['activity_sub_type'] in ('NAME_CHANGE', 'MERGER_TAXABLE'):
                pass  # Skip corporate actions for now
    
    total_cost = sum(h['total_cost'] for h in local_holdings.values() if h['quantity'] > 0)
    return total_cost

# Snapshot dates
snapshot_dates = [
    date(2021, 2, 8), date(2021, 3, 10), date(2021, 4, 9), date(2021, 5, 10),
    date(2021, 6, 9), date(2021, 7, 9), date(2021, 8, 9), date(2021, 9, 8),
    date(2021, 10, 8), date(2021, 11, 8), date(2021, 12, 8), date(2022, 1, 7),
    date(2022, 2, 7), date(2022, 3, 9), date(2022, 4, 8), date(2022, 5, 9),
    date(2022, 6, 8), date(2022, 7, 8), date(2022, 8, 8), date(2022, 9, 7),
    date(2022, 10, 7), date(2022, 11, 7), date(2022, 12, 7), date(2023, 1, 6),
    date(2023, 2, 6), date(2023, 3, 8), date(2023, 4, 7), date(2023, 5, 8),
    date(2023, 6, 7), date(2023, 7, 7), date(2023, 8, 7), date(2023, 9, 6),
    date(2023, 10, 6), date(2023, 11, 6), date(2023, 12, 6), date(2024, 1, 5),
    date(2024, 2, 5), date(2024, 3, 6), date(2024, 4, 5), date(2024, 5, 6),
    date(2024, 6, 5), date(2024, 7, 5), date(2024, 8, 5), date(2024, 9, 4),
    date(2024, 10, 4), date(2024, 11, 4), date(2024, 12, 4), date(2025, 1, 3),
    date(2025, 2, 4), date(2025, 3, 7), date(2025, 4, 7), date(2025, 5, 7),
    date(2025, 6, 6), date(2025, 7, 7), date(2025, 8, 6), date(2025, 9, 5),
    date(2025, 10, 7), date(2025, 11, 6), date(2025, 12, 8), date(2026, 1, 8),
    date(2026, 2, 9), date(2026, 3, 11), date(2026, 4, 10), date(2026, 5, 31),
    date(2026, 7, 1), date(2026, 7, 14),
]

# Print results
print(f"{'#':<4} {'Date':<12} {'Exp ND':<15} {'Exp CB':<15} {'Exp CostBasis':<15}")
print("-" * 65)
for i, snap_date in enumerate(snapshot_dates, 1):
    nd = get_net_deposits(snap_date)
    cb = get_cash_balance(snap_date)
    cost = get_holdings_cost_basis(snap_date)
    print(f"{i:<4} {snap_date.isoformat():<12} ${nd:>12,.2f} ${cb:>12,.2f} ${cost:>12,.2f}")
