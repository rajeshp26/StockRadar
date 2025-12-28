from .yfinance_provider import YFinanceProvider

# This is where you could implement a more complex provider loading mechanism.
# For now, we'll just instantiate the YFinanceProvider directly.
# In the future, you could have a list of providers and try them in order.

stock_provider = YFinanceProvider()
