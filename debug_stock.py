import yfinance as yf
import json

try:
    ticker = yf.Ticker("HRL")
    info = ticker.info
    # Use a serializable-safe way to print
    # We can't just dump `info` as it may contain non-JSON-serializable objects
    safe_info = {k: repr(v) for k, v in info.items()}
    print(json.dumps(safe_info, indent=2))
except Exception as e:
    print(f"An error occurred: {e}")
