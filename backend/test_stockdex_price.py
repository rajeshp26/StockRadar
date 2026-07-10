"""Test stockdex yahoo_api_price and check currency theory for defeatbeta."""
import os
os.environ["ENVIRONMENT"] = "development"

# Test 1: Stockdex price API
print("=" * 60)
print("TEST 1: Stockdex yahoo_api_price")
print("=" * 60)
try:
    from stockdex import Ticker as StockdexTicker
    t = StockdexTicker(ticker="RY")
    df = t.yahoo_api_price(range="1mo", dataGranularity="1d")
    print(f"RY 1mo price data shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(df.tail(10))
    print()
    
    # Test with max range
    df_max = t.yahoo_api_price(range="max", dataGranularity="1d")
    print(f"RY max range price data shape: {df_max.shape}")
    print(f"Date range: {df_max.index[0]} to {df_max.index[-1]}")
    print(df_max.tail(5))
except ImportError as e:
    print(f"stockdex not installed: {e}")
except Exception as e:
    print(f"stockdex error: {e}")

print()

# Test 2: Check defeatbeta currency issue
# Look at the defeatbeta data source and see if exchange suffix matters
print("=" * 60)
print("TEST 2: DefeatBeta currency check")
print("=" * 60)

# Check if the defeatbeta data matches known USD prices or CAD prices
from database import supabase as client

# For RY: check if defeatbeta CAD price would match when converted
# RY.TO CAD price from yfinance: ~$287 CAD
# RY NYSE USD price from yfinance: ~$189 USD
# USD/CAD rate: ~1.36
# DefeatBeta shows: ~$100

# If $100 CAD / 1.36 = $73.53 USD — doesn't match $189
# If $100 USD * 1.36 = $136 CAD — doesn't match $287
# So it's not a simple currency flip

# But let's check the defeatbeta raw data source more carefully
# The Ticker().price() call — does it have a currency parameter?
print("Checking defeatbeta Ticker.price() signature...")
from defeatbeta_api.data.ticker import Ticker as DBTicker
import inspect
try:
    sig = inspect.signature(DBTicker.price)
    print(f"DBTicker.price signature: {sig}")
except:
    pass
try:
    # Check if price accepts parameters
    print(f"DBTicker.price annotations: {getattr(DBTicker.price, '__annotations__', 'N/A')}")
except:
    pass

# Check the defeatbeta Ticker constructor
try:
    sig2 = inspect.signature(DBTicker.__init__)
    print(f"DBTicker.__init__ signature: {sig2}")
except:
    pass

# Check all methods of DBTicker that might relate to price
print(f"\nAll DBTicker methods containing 'price':")
for name in dir(DBTicker):
    if 'price' in name.lower():
        print(f"  {name}")
