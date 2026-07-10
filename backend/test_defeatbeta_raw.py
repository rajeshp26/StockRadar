"""Check defeatbeta raw price data output to understand the values."""
import os
os.environ["ENVIRONMENT"] = "development"

from defeatbeta_api.data.ticker import Ticker as DBTicker
import pandas as pd
pd.set_option('display.max_rows', 30)
pd.set_option('display.width', 200)

# Test RY - with exchange="NYQ" (no suffix)
print("=" * 60)
print("DefeatBeta RY (no suffix, NYSE)")
print("=" * 60)
t = DBTicker(ticker="RY")
df = t.price()
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Dtypes:\n{df.dtypes}")
print()
print(df.tail(20))
print()

# Check the close prices for May dates
print("May 2026 prices from DefeatBeta:")
may = df[df['report_date'].between('2026-05-01', '2026-05-31')] if 'report_date' in df.columns else df
if 'report_date' not in df.columns:
    # Try other column names
    date_col = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()][0]
    may = df[df[date_col].between('2026-05-01', '2026-05-31')]
print(may[['report_date', 'close']].tail(30) if 'report_date' in df.columns else may.tail(30))

# Test RY.TO - Canadian suffix
print("=" * 60)
print("DefeatBeta RY.TO (Canadian suffix)")
print("=" * 60)
try:
    t2 = DBTicker(ticker="RY.TO")
    df2 = t2.price()
    print(f"Shape: {df2.shape}")
    print(f"Columns: {list(df2.columns)}")
    print(df2.tail(20))
except Exception as e:
    print(f"Error: {e}")

# Check AAPL too
print("=" * 60)
print("DefeatBeta AAPL")
print("=" * 60)
t3 = DBTicker(ticker="AAPL")
df3 = t3.price()
print(f"Shape: {df3.shape}")
print(f"Columns: {list(df3.columns)}")
print(df3[['report_date', 'close']].tail(20) if 'report_date' in df3.columns else df3.tail(20))
