CREATE OR REPLACE VIEW portfolio_monthly_dividends AS
SELECT account_id, fiscal_year, fiscal_month, count(*) AS payment_count,
       sum(amount) AS total_amount, count(DISTINCT company_id) AS paying_companies
FROM portfolio_dividends
GROUP BY account_id, fiscal_year, fiscal_month
ORDER BY account_id, fiscal_year DESC, fiscal_month DESC;

CREATE OR REPLACE VIEW portfolio_user_import_history AS
SELECT import_id, user_id, brokerage_id, import_batch_id, csv_filename,
       total_rows, imported_rows, duplicate_rows, error_rows, status,
       error_message, started_at, completed_at
FROM portfolio_import_history;

CREATE OR REPLACE VIEW super_investor_current_holdings AS
SELECT ih.investor_id, ii.investor_name, ii.firm_name, ih.company_id,
       c.ticker_symbol, c.company_name, ih.shares_held, ih.position_value,
       ih.portfolio_weight, ih.quarter_end_date
FROM institutional_holdings ih
JOIN institutional_investors ii ON ih.investor_id = ii.investor_id
JOIN companies c ON ih.company_id = c.company_id
WHERE ii.is_super_investor = true;

CREATE OR REPLACE VIEW v_dcf_valuations AS
SELECT dcf_id AS id, company_id, analysis_date, forecast_years,
       revenue_growth_rate, terminal_growth_rate, wacc_used,
       fcf_margin_assumption, total_pv_fcf, terminal_value,
       pv_terminal_value, enterprise_value_dcf, less_net_debt,
       equity_value, shares_outstanding, intrinsic_value_per_share,
       current_stock_price, upside_downside_pct, analyst_name,
       sensitivity_scenarios, notes, created_at
FROM dcf_valuations;

CREATE OR REPLACE VIEW v_ddm_valuations AS
SELECT ddm_id AS id, company_id, analysis_date, current_dps,
       next_year_dps, dividend_growth_rate, required_return,
       intrinsic_value_gordon, high_growth_years, high_growth_rate,
       stable_growth_rate, intrinsic_value_multistage,
       current_stock_price, upside_downside_pct, analyst_name,
       notes, created_at
FROM ddm_valuations;

CREATE OR REPLACE VIEW v_owner_earnings_valuations AS
SELECT valuation_run_id AS id, company_id, method, run_at,
       input_snapshot, assumption_snapshot, output_snapshot
FROM valuation_runs
WHERE method = 'owner_earnings';

CREATE OR REPLACE VIEW v_residual_income_valuations AS
SELECT valuation_run_id AS id, company_id, method, run_at,
       input_snapshot, assumption_snapshot, output_snapshot
FROM valuation_runs
WHERE method = 'relative';
