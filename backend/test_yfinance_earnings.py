# Test script to verify yfinance earnings_history format
import yfinance as yf
import pandas as pd

def test_earnings_history():
    print("=" * 60)
    print("Testing YFinance earnings_history for VEEV")
    print("=" * 60)

    ticker = yf.Ticker("VEEV")

    # Test earnings_history
    print("\n--- earnings_history (PROPERTY) ---")
    try:
        eh = ticker.earnings_history
        if eh is not None and not eh.empty:
            print(f"Columns: {list(eh.columns)}")
            print(f"Index: {list(eh.index)}")
            print("\nData:")
            print(eh)
        else:
            print("No data returned")
    except Exception as e:
        print(f"Error: {e}")

    # Test get_earnings_history (method)
    print("\n--- get_earnings_history (METHOD) ---")
    try:
        eh_method = ticker.get_earnings_history()
        if eh_method is not None and not eh_method.empty:
            print(f"Columns: {list(eh_method.columns)}")
            print(f"Index: {list(eh_method.index)}")
            print("\nData:")
            print(eh_method)
        else:
            print("No data returned")
    except Exception as e:
        print(f"Error: {e}")

    # Compare with calendar (current method)
    print("\n--- calendar (CURRENT METHOD) ---")
    try:
        cal = ticker.calendar
        if cal is not None and not cal.empty:
            print(f"Columns: {list(cal.columns)}")
            print("\nData:")
            print(cal)
        else:
            print("No data returned")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_earnings_history()