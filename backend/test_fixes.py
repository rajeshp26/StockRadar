# Test script to verify the fixes work
import asyncio
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

async def test_fixes():
    print("=" * 60)
    print("Testing the fixes")
    print("=" * 60)

    # Test 1: YFinance provider
    print("\n--- Test 1: YFinance get_earnings_data() ---")
    from providers.yfinance_provider import YFinanceProvider
    yf = YFinanceProvider()
    earnings = yf.get_earnings_data("VEEV")
    if earnings:
        print("OK - YFinance returned {} quarterly records".format(len(earnings)))
        for e in earnings[:4]:
            print("  Q{} {}: eps_reported={}, eps_estimate={}, surprise={}".format(
                e['fiscal_quarter'], e['fiscal_year'], e['eps_reported'], e['eps_estimate'], e['eps_surprise_percent']))
    else:
        print("FAIL - No earnings data returned")

    # Test 2: Analysis repository
    print("\n--- Test 2: AnalysisRepository get_quarterly_eps_from_income_statements() ---")
    from infrastructure.repositories.analysis_repository import AnalysisRepository
    repo = AnalysisRepository()
    eps_data = await repo.get_quarterly_eps_from_income_statements(63, limit=12)  # VEEV = company_id 63
    if eps_data:
        print("OK - income_statements returned {} quarterly records".format(len(eps_data)))
        for e in eps_data[:4]:
            print("  Q{} {}: eps={}".format(e['fiscal_quarter'], e['fiscal_year'], e['eps_reported_diluted']))
    else:
        print("FAIL - No EPS data returned")

    # Test 3: Old function (deprecated) still works
    print("\n--- Test 3: Old get_quarterly_earnings_series() (deprecated) ---")
    old_data = await repo.get_quarterly_earnings_series(63, limit=12)
    if old_data:
        print("OK - Old function still works, returned {} records".format(len(old_data)))
    else:
        print("FAIL - Old function returned empty")

if __name__ == "__main__":
    asyncio.run(test_fixes())