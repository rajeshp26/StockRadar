"""Compare stockdex monthly prices vs yfinance monthly EOM prices."""
import os
os.environ["ENVIRONMENT"] = "development"
import yfinance as yf
from stockdex import Ticker as StockdexTicker
import pandas as pd
pd.set_option('display.max_rows', 50)
pd.set_option('display.width', 300)

tickers = ["RY", "TD", "ENB", "SHOP", "AAPL"]

for sym in tickers:
    print(f"\n{'='*80}")
    print(f"  {sym}")
    print(f"{'='*80}")
    
    # Stockdex monthly (range="max")
    sd = StockdexTicker(ticker=sym)
    sd_df = sd.yahoo_api_price(range="max", dataGranularity="1d")
    
    # Find RY-specific data
    sd_monthly = sd_df[['timestamp', 'close', 'open', 'high', 'low', 'volume']].copy()
    sd_monthly['date'] = pd.to_datetime(sd_monthly['timestamp'])
    sd_monthly = sd_monthly.set_index('date')
    
    # Show last 12 months
    print(f"\n  Stockdex last 12 entries:")
    print(sd_monthly[['close']].tail(12))
    
    # yfinance daily, compress to monthly EOM
    t = yf.Ticker(sym)
    yf_daily = t.history(period="max", auto_adjust=True)
    yf_monthly = yf_daily.resample('ME').last()
    yf_monthly.index = yf_monthly.index.normalize()
    
    print(f"\n  YFinance monthly EOM last 12 entries:")
    print(yf_monthly[['Close']].tail(12))
    
    # Compare side by side
    print(f"\n  {'Date':<14s} {'SD Close':>10s} {'YF Close':>10s} {'Diff':>8s}")
    print(f"  {'-'*42}")
    
    # Find common dates
    sd_dates = {d.date() for d in sd_monthly.index}
    yf_dates = {d.date() for d in yf_monthly.index}
    common = sorted(sd_dates & yf_dates)[-12:]  # last 12 common
    
    for d in common:
        sd_close = float(sd_monthly.loc[sd_monthly.index.date == d, 'close'].iloc[-1])
        yf_close = float(yf_monthly.loc[yf_monthly.index.date == d, 'Close'].iloc[-1])
        diff = (sd_close - yf_close) / yf_close * 100
        flag = " <<<" if abs(diff) > 5 else ""
        print(f"  {d:<14s} ${sd_close:>8.2f} ${yf_close:>8.2f} {diff:>+6.1f}%{flag}")
    
    # Check what date format stockdex uses (1st of month or last?)
    print(f"\n  Stockdex date sample (last 5):")
    for idx, row in sd_monthly.tail(5).iterrows():
        print(f"    {idx.date()}: close=${float(row['close']):.2f}")
