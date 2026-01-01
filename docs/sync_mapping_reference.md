# Data Mapping Reference: yfinance to Supabase

This document maintains the mapping between verbose labels provided by the `yfinance` library and the normalized columns in our Supabase database.

## 1. Income Statement Mapping
| yfinance Label | Supabase Column | Type |
| :--- | :--- | :--- |
| Total Revenue | `revenue` | numeric |
| Cost Of Revenue | `cost_of_goods_sold` | numeric |
| Gross Profit | `gross_profit` | numeric |
| Operating Expense | `operating_expenses` | numeric |
| Research And Development | `rd_expenses` | numeric |
| Selling General And Administrative | `sga_expenses` | numeric |
| Operating Income | `operating_income` | numeric |
| Interest Expense | `interest_expense` | numeric |
| Tax Provision | `tax_expense` | numeric |
| Net Income | `net_income` | numeric |
| EBITDA | `ebitda` | numeric |
| EBIT | `ebit` | numeric |

## 2. Balance Sheet Mapping
| yfinance Label | Supabase Column | Type |
| :--- | :--- | :--- |
| Total Assets | `total_assets` | numeric |
| Current Assets | `current_assets` | numeric |
| Cash And Cash Equivalents | `cash_and_cash_equivalents` | numeric |
| Inventory | `inventory` | numeric |
| Net PPE | `property_plant_equipment_net` | numeric |
| Total Liabilities Net Minority Interest | `total_liabilities` | numeric |
| Current Liabilities | `current_liabilities` | numeric |
| Total Debt | `total_debt` | numeric |
| Stockholders Equity | `shareholders_equity` | numeric |

## 3. Cash Flow Mapping
| yfinance Label | Supabase Column | Type |
| :--- | :--- | :--- |
| Operating Cash Flow | `cash_from_operating_activities` | numeric |
| Investing Cash Flow | `cash_from_investing_activities` | numeric |
| Financing Cash Flow | `cash_from_financing_activities` | numeric |
| Capital Expenditure | `capital_expenditures` | numeric |

## 4. Statistics (TTM) Mapping
Captured from `Ticker.info` snapshot. Values are converted from decimals to percentages (e.g., 0.25 -> 25.0).

| yfinance Key | Supabase Column | Conversion |
| :--- | :--- | :--- |
| trailingPE | `pe_ratio` | None |
| priceToSalesTrailing12Months | `ps_ratio` | None |
| priceToBook | `pb_ratio` | None |
| enterpriseValue | `enterprise_value` | None |
| enterpriseToEbitda | `ev_to_ebitda` | None |
| grossMargins | `gross_margin_pct` | * 100 |
| operatingMargins | `operating_margin_pct` | * 100 |
| ebitdaMargins | `ebitda_margin_pct` | * 100 |
| profitMargins | `net_margin_pct` | * 100 |
| returnOnAssets | `return_on_assets_pct` | * 100 |
| returnOnEquity | `return_on_equity_pct` | * 100 |
| currentRatio | `current_ratio` | None |
| quickRatio | `quick_ratio` | None |
| debtToEquity | `debt_to_equity` | None |

## 5. Metadata & Logic
*   **Period Type:** Annual financial statements use `fiscal_quarter = NULL`. Quarterly statements use `1-4`.
*   **TTM:** Statistics are stored with `period_type = 'ttm'` and the current date as `period_end_date`.
*   **Duplicates:** Upserts rely on the unique constraint: `(company_id, fiscal_year, fiscal_quarter)`.
