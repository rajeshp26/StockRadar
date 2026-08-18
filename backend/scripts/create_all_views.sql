-- ============================================================
-- All Cloud Views — Run AFTER importing all table data
-- ============================================================
-- Source: Cloud database pg_get_viewdef() output
-- Date: 2026-08-02
--
-- Usage:
--   Option A: supabase db exec --file backend/scripts/create_all_views.sql
--   Option B: Paste into Supabase Studio SQL Editor (localhost:54323)
-- ============================================================

-- 1. Portfolio Monthly Dividends
CREATE OR REPLACE VIEW portfolio_monthly_dividends AS
SELECT
    account_id,
    fiscal_year,
    fiscal_month,
    count(*) AS payment_count,
    sum(amount) AS total_amount,
    count(DISTINCT company_id) AS paying_companies
FROM portfolio_dividends
GROUP BY account_id, fiscal_year, fiscal_month
ORDER BY account_id, fiscal_year DESC, fiscal_month DESC;

-- 2. Portfolio User Import History
CREATE OR REPLACE VIEW portfolio_user_import_history AS
SELECT
    pih.import_id,
    pih.user_id,
    pih.import_batch_id,
    pih.csv_filename,
    pih.csv_size_bytes,
    pih.total_rows,
    pih.imported_rows,
    pih.duplicate_rows,
    pih.status,
    pih.started_at,
    pih.completed_at,
    pb.brokerage_name,
    pb.brokerage_code,
    count(DISTINCT pa.account_id) AS accounts_affected
FROM portfolio_import_history pih
    JOIN portfolio_brokerages pb ON pih.brokerage_id = pb.brokerage_id
    LEFT JOIN portfolio_transactions pt ON pt.import_batch_id = pih.import_batch_id
    LEFT JOIN portfolio_accounts pa ON pt.account_id = pa.account_id
GROUP BY pih.import_id, pih.user_id, pih.import_batch_id, pih.csv_filename,
         pih.csv_size_bytes, pih.total_rows, pih.imported_rows, pih.duplicate_rows,
         pih.status, pih.started_at, pih.completed_at, pb.brokerage_name, pb.brokerage_code
ORDER BY pih.started_at DESC;

-- 3. Super Investor Current Holdings
CREATE OR REPLACE VIEW super_investor_current_holdings AS
SELECT
    h.company_id,
    c.ticker_symbol,
    c.company_name,
    i.investor_name,
    i.firm_name,
    i.investor_tag,
    i.investment_style,
    h.shares_held,
    h.position_value,
    h.portfolio_weight,
    h.change_type,
    h.shares_change_pct,
    h.quarter_end_date,
    h.filing_date
FROM institutional_holdings h
    JOIN institutional_investors i ON h.investor_id = i.investor_id
    JOIN companies c ON h.company_id = c.company_id
WHERE i.is_super_investor = true
  AND h.quarter_end_date = (
      SELECT max(ih2.quarter_end_date)
      FROM institutional_holdings ih2
      WHERE ih2.investor_id = h.investor_id
  );

-- 4. DCF Valuations View
CREATE OR REPLACE VIEW v_dcf_valuations AS
SELECT
    valuation_run_id,
    company_id,
    run_at AS analysis_date,
    run_by_user_id,
    (output_snapshot -> 'valuation' ->> 'terminalMethod') AS terminal_method,
    ((output_snapshot -> 'valuation' ->> 'forecastYears')::integer) AS forecast_years,
    ((output_snapshot -> 'valuation' ->> 'waccUsed')::numeric) AS wacc_used,
    ((output_snapshot -> 'valuation' ->> 'terminalGrowthRateUsed')::numeric) AS terminal_growth_rate,
    ((output_snapshot -> 'valuation' ->> 'baseFcf')::numeric) AS base_fcf,
    ((output_snapshot -> 'valuation' ->> 'baseFcfFiscalYear')::integer) AS base_fcf_fiscal_year,
    ((output_snapshot -> 'valuation' ->> 'totalPvFcf')::numeric) AS total_pv_fcf,
    ((output_snapshot -> 'valuation' ->> 'terminalValue')::numeric) AS terminal_value,
    ((output_snapshot -> 'valuation' ->> 'pvTerminalValue')::numeric) AS pv_terminal_value,
    ((output_snapshot -> 'valuation' ->> 'enterpriseValue')::numeric) AS enterprise_value,
    ((output_snapshot -> 'valuation' ->> 'netDebtUsed')::numeric) AS net_debt_used,
    ((output_snapshot -> 'valuation' ->> 'equityValue')::numeric) AS equity_value,
    ((output_snapshot -> 'valuation' ->> 'sharesOutstanding')::numeric) AS shares_outstanding,
    ((output_snapshot -> 'valuation' ->> 'intrinsicValuePerShare')::numeric) AS intrinsic_value_per_share,
    ((output_snapshot -> 'applicability' ->> 'score')::integer) AS suitability_score,
    (output_snapshot -> 'applicability' ->> 'category') AS suitability_category,
    notes
FROM valuation_runs vr
WHERE method::text = 'dcf'::text;

-- 5. DDM Valuations View
CREATE OR REPLACE VIEW v_ddm_valuations AS
SELECT
    valuation_run_id,
    company_id,
    run_at AS analysis_date,
    run_by_user_id,
    method,
    ((output_snapshot -> 'valuation' ->> 'currentDps')::numeric) AS current_dps,
    ((output_snapshot -> 'valuation' ->> 'nextYearDps')::numeric) AS next_year_dps,
    ((output_snapshot -> 'valuation' ->> 'dividendGrowthRate')::numeric) AS dividend_growth_rate,
    ((output_snapshot -> 'valuation' ->> 'requiredReturn')::numeric) AS required_return,
    ((output_snapshot -> 'valuation' ->> 'intrinsicValue')::numeric) AS intrinsic_value,
    ((output_snapshot -> 'valuation' ->> 'highGrowthYears')::integer) AS high_growth_years,
    ((output_snapshot -> 'valuation' ->> 'highGrowthRate')::numeric) AS high_growth_rate,
    ((output_snapshot -> 'valuation' ->> 'stableGrowthRate')::numeric) AS stable_growth_rate,
    ((output_snapshot -> 'valuation' ->> 'pvStage1')::numeric) AS pv_stage1,
    ((output_snapshot -> 'valuation' ->> 'pvTerminal')::numeric) AS pv_terminal,
    ((output_snapshot -> 'applicability' ->> 'score')::integer) AS suitability_score,
    (output_snapshot -> 'applicability' ->> 'category') AS suitability_category,
    notes
FROM valuation_runs vr
WHERE method::text = ANY (ARRAY['ddm_gordon'::character varying, 'ddm_two_stage'::character varying]::text[]);

-- 6. Owner Earnings Valuations View
CREATE OR REPLACE VIEW v_owner_earnings_valuations AS
SELECT
    valuation_run_id,
    company_id,
    run_at AS analysis_date,
    run_by_user_id,
    ((output_snapshot -> 'valuation' ->> 'baseOe')::numeric) AS base_oe,
    ((output_snapshot -> 'valuation' ->> 'baseOeFiscalYear')::integer) AS base_oe_fiscal_year,
    ((output_snapshot -> 'valuation' ->> 'netIncomeUsed')::numeric) AS net_income_used,
    ((output_snapshot -> 'valuation' ->> 'daUsed')::numeric) AS da_used,
    ((output_snapshot -> 'valuation' ->> 'capexUsed')::numeric) AS capex_used,
    ((output_snapshot -> 'valuation' ->> 'wcChangeUsed')::numeric) AS wc_change_used,
    ((output_snapshot -> 'valuation' ->> 'forecastYears')::integer) AS forecast_years,
    ((output_snapshot -> 'valuation' ->> 'discountRateUsed')::numeric) AS discount_rate_used,
    ((output_snapshot -> 'valuation' ->> 'oeGrowthRateUsed')::numeric) AS oe_growth_rate_used,
    ((output_snapshot -> 'valuation' ->> 'terminalGrowthRateUsed')::numeric) AS terminal_growth_rate_used,
    ((output_snapshot -> 'valuation' ->> 'maintenanceCapexRatioUsed')::numeric) AS maintenance_capex_ratio,
    ((output_snapshot -> 'valuation' ->> 'totalPvOe')::numeric) AS total_pv_oe,
    ((output_snapshot -> 'valuation' ->> 'terminalValue')::numeric) AS terminal_value,
    ((output_snapshot -> 'valuation' ->> 'pvTerminalValue')::numeric) AS pv_terminal_value,
    ((output_snapshot -> 'valuation' ->> 'enterpriseValue')::numeric) AS enterprise_value,
    ((output_snapshot -> 'valuation' ->> 'netDebtUsed')::numeric) AS net_debt_used,
    ((output_snapshot -> 'valuation' ->> 'equityValue')::numeric) AS equity_value,
    ((output_snapshot -> 'valuation' ->> 'sharesOutstanding')::numeric) AS shares_outstanding,
    ((output_snapshot -> 'valuation' ->> 'intrinsicValuePerShare')::numeric) AS intrinsic_value_per_share,
    ((output_snapshot -> 'applicability' ->> 'score')::integer) AS suitability_score,
    (output_snapshot -> 'applicability' ->> 'category') AS suitability_category,
    notes
FROM valuation_runs vr
WHERE method::text = 'owner_earnings'::text;

-- 7. Residual Income Valuations View
CREATE OR REPLACE VIEW v_residual_income_valuations AS
SELECT
    valuation_run_id,
    company_id,
    run_at AS analysis_date,
    run_by_user_id,
    ((output_snapshot -> 'valuation' ->> 'eps0')::numeric) AS eps0,
    ((output_snapshot -> 'valuation' ->> 'bvPerShare')::numeric) AS bv_per_share,
    ((output_snapshot -> 'valuation' ->> 'roe0')::numeric) AS roe0,
    ((output_snapshot -> 'valuation' ->> 'ri0PerShare')::numeric) AS ri0_per_share,
    ((output_snapshot -> 'valuation' ->> 'bvFiscalYear')::integer) AS bv_fiscal_year,
    ((output_snapshot -> 'valuation' ->> 'costOfEquityUsed')::numeric) AS cost_of_equity,
    ((output_snapshot -> 'valuation' ->> 'betaUsed')::numeric) AS beta_used,
    ((output_snapshot -> 'valuation' ->> 'rfUsed')::numeric) AS rf_used,
    ((output_snapshot -> 'valuation' ->> 'erpUsed')::numeric) AS erp_used,
    ((output_snapshot -> 'valuation' ->> 'forecastYears')::integer) AS forecast_years,
    ((output_snapshot -> 'valuation' ->> 'riGrowthRateUsed')::numeric) AS ri_growth_rate_used,
    ((output_snapshot -> 'valuation' ->> 'terminalGrowthRateUsed')::numeric) AS terminal_growth_rate_used,
    ((output_snapshot -> 'valuation' ->> 'totalPvRiPerShare')::numeric) AS total_pv_ri_per_share,
    ((output_snapshot -> 'valuation' ->> 'terminalValueRi')::numeric) AS terminal_value_ri,
    ((output_snapshot -> 'valuation' ->> 'pvTerminalRiPerShare')::numeric) AS pv_terminal_ri_per_share,
    ((output_snapshot -> 'valuation' ->> 'intrinsicValuePerShare')::numeric) AS intrinsic_value_per_share,
    ((output_snapshot -> 'applicability' ->> 'score')::integer) AS suitability_score,
    (output_snapshot -> 'applicability' ->> 'category') AS suitability_category,
    notes
FROM valuation_runs vr
WHERE method::text = 'residual_income'::text;
