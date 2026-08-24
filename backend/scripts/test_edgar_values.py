"""
Test script to verify what values the edgar tool returns for different time periods.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from edgar import Company, set_identity


def test_edgar_values():
    set_identity("StockerPro test script rajeshp01@gmail.com")

    # Test with Warren Buffett's Berkshire Hathaway (CIK: 0001067983)
    cik = "0001067983"

    print(f"Testing edgar values for CIK {cik} (Berkshire Hathaway)")
    print("=" * 60)

    company = Company(cik)

    # Get filings for different years (pre-2023 and post-2023)
    test_years = [2022, 2024]  # 2022 = pre-change, 2024 = post-change

    for year in test_years:
        print(f"\n--- Testing year {year} ---")
        try:
            filings = list(company.get_filings(form="13F-HR", year=year))
            if not filings:
                print(f"No filings found for {year}")
                continue

            # Get the first filing of the year
            filing = filings[0]
            thirteenf = filing.obj()

            if not thirteenf:
                print(f"Could not parse filing for {year}")
                continue

            period = str(thirteenf.report_period)
            filing_date = str(filing.filing_date)

            print(f"Report Period: {period}")
            print(f"Filing Date: {filing_date}")
            print(f"Total Value (from thirteenf.total_value): {thirteenf.total_value}")

            holdings_df = thirteenf.holdings
            if holdings_df is None or holdings_df.empty:
                print("No holdings data")
                continue

            print("\nFirst 3 holdings (sorted by Value):")
            top_holdings = holdings_df.sort_values("Value", ascending=False).head(3)

            for idx, row in top_holdings.iterrows():
                ticker = row.get("Ticker", "N/A")
                value = row.get("Value", 0)
                shares = row.get("SharesPrnAmount", 0)

                print(f"  {ticker}: Value={value}, Shares={shares}")

                # Calculate what the value would be in dollars
                # If Value is in thousands: value * 1000
                # If Value is in dollars: value
                print(f"    If 'Value' is thousands: ${float(value) * 1000:,.0f}")
                print(f"    If 'Value' is dollars: ${float(value):,.0f}")

            # Calculate total from holdings
            total_from_holdings = float(holdings_df["Value"].sum())
            print(f"\nTotal from summing holdings['Value']: {total_from_holdings:,.0f}")
            print(f"  If thousands: ${total_from_holdings * 1000:,.0f}")
            print(f"  If dollars: ${total_from_holdings:,.0f}")

            print(f"\nthirteenf.total_value: {thirteenf.total_value}")
            print(f"  Type: {type(thirteenf.total_value)}")

        except Exception as e:
            print(f"Error testing {year}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test complete!")

if __name__ == "__main__":
    test_edgar_values()
