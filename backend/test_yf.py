"""Test yfinance directly to see what prices it returns."""
import yfinance as yf
import pandas as pd
pd.set_option('display.max_rows', None)

# RY with auto_adjust=True
t = yf.Ticker("RY")
hist = t.history(period="1mo", auto_adjust=True)
print("=== RY auto_adjust=True (last 10) ===")
print(hist.tail(10))

hist2 = t.history(period="1mo", auto_adjust=False)
print("\n=== RY auto_adjust=False (last 10) ===")
print(hist2.tail(10))

print("\n=== RY info ===")
info = t.info
print(f"currentPrice: {info.get('currentPrice')}")
print(f"regularMarketPrice: {info.get('regularMarketPrice')}")
print(f"previousClose: {info.get('regularMarketPreviousClose')}")
print(f"currency: {info.get('currency')}")
print(f"exchange: {info.get('exchange')}")
print(f"shortName: {info.get('shortName')}")

# Also check RY.TO (Canadian listing)
print("\n=== RY.TO (Canadian) auto_adjust=True ===")
t2 = yf.Ticker("RY.TO")
hist3 = t2.history(period="1mo", auto_adjust=True)
print(hist3.tail(10))
info2 = t2.info
print(f"currentPrice: {info2.get('currentPrice')}")
print(f"currency: {info2.get('currency')}")
print(f"exchange: {info2.get('exchange')}")

# Check AAPL
print("\n=== AAPL auto_adjust=True ===")
t3 = yf.Ticker("AAPL")
hist4 = t3.history(period="1mo", auto_adjust=True)
print(hist4.tail(10))
info3 = t3.info
print(f"currentPrice: {info3.get('currentPrice')}")
print(f"previousClose: {info3.get('regularMarketPreviousClose')}")
