"""Deep dive into the real price data quality issue."""
import yfinance as yf
import pandas as pd
pd.set_option('display.max_rows', 200)
pd.set_option('display.width', 200)

# Full history for RY
t = yf.Ticker("RY")
hist = t.history(period="max", auto_adjust=True)
print("=== RY FULL HISTORY ===")
print(f"Shape: {hist.shape}")
print(f"Date range: {hist.index[0]} to {hist.index[-1]}")
print()

# Show April-June 2026
mask = (hist.index >= '2026-04-01') & (hist.index <= '2026-06-23')
print(hist[mask])
print()

# Check for weekend data
print("=== Weekend data check ===")
weekends = hist[hist.index.dayofweek >= 5]
print(f"Weekend rows: {len(weekends)}")
if len(weekends) > 0:
    print(weekends)

# Check May specifically for RY
print("\n=== RY May 2026 ===")
mask2 = (hist.index >= '2026-05-01') & (hist.index <= '2026-05-31')
print(hist[mask2])

# Same for AAPL
print("\n=== AAPL April-June 2026 ===")
t2 = yf.Ticker("AAPL")
hist2 = t2.history(period="max", auto_adjust=True)
mask3 = (hist2.index >= '2026-04-01') & (hist2.index <= '2026-06-23')
print(hist2[mask3])
weekends2 = hist2[hist2.index.dayofweek >= 5]
print(f"\nAAPL Weekend rows: {len(weekends2)}")
if len(weekends2) > 0:
    print(weekends2)
