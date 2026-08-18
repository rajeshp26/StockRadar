"""Fix all column types to match cloud exactly."""
import psycopg2

DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

FIXES = [
    # Category 1: smallint → integer
    ("balance_sheets", "fiscal_quarter", "integer"),
    ("cash_flow_statements", "fiscal_quarter", "integer"),
    ("earnings", "fiscal_quarter", "integer"),

    # Category 2: double precision → numeric (confidence_score)
    ("balance_sheets", "confidence_score", "numeric"),
    ("cash_flow_statements", "confidence_score", "numeric"),
    ("earnings", "confidence_score", "numeric"),
    ("financial_ratios", "confidence_score", "integer"),
    ("income_statements", "confidence_score", "integer"),
    ("dividend_history", "confidence_score", "integer"),

    # Category 2b: double precision → numeric (moat_analysis)
    ("moat_analysis", "roic", "numeric"),
    ("moat_analysis", "wacc", "numeric"),
    ("moat_analysis", "roic_minus_wacc", "numeric"),
    ("moat_analysis", "gross_margin_pct", "numeric"),
    ("moat_analysis", "operating_margin_pct", "numeric"),
    ("moat_analysis", "net_margin_pct", "integer"),
    ("moat_analysis", "roic_5y_avg", "numeric"),
    ("moat_analysis", "asset_turnover", "numeric"),
    ("moat_analysis", "capital_efficiency_score", "integer"),
    ("moat_analysis", "moat_score", "numeric"),
    ("moat_analysis", "sector_adjustment", "integer"),
    ("moat_keyword_evidence", "relevance_score", "numeric"),
    ("data_conflicts", "percent_diff", "numeric"),

    # Category 3: bigint → integer (cloud had integer)
    ("current_market_data", "volume", "integer"),
    ("price_history", "volume", "integer"),
    ("dcf_valuations", "shares_outstanding", "integer"),
    ("institutional_holdings", "shares_held", "integer"),
    ("institutional_holdings", "shares_change", "integer"),
    ("income_statements", "shares_outstanding_basic", "integer"),
    ("income_statements", "shares_outstanding_diluted", "integer"),
    ("earnings", "shares_outstanding_basic", "bigint"),
    ("earnings", "shares_outstanding_diluted", "bigint"),

    # Category 4: integer → bigint (cloud had integer, local wrongly bigint)
    ("data_conflicts", "conflict_id", "integer"),
    ("data_quality_events", "event_id", "integer"),
    ("moat_ai_narratives", "id", "integer"),
    ("moat_ai_narratives", "company_id", "integer"),
    ("moat_analysis", "id", "integer"),
    ("moat_analysis", "company_id", "integer"),
    ("moat_keyword_evidence", "id", "integer"),
    ("moat_keyword_evidence", "company_id", "integer"),
    ("portfolio_snapshots", "id", "integer"),
    ("revenue_forecast", "forecast_id", "integer"),
    ("earnings_forecast", "earnings_forecast_id", "integer"),
    ("exchange_rates", "id", "integer"),
    ("splits", "split_id", "integer"),
    ("valuation_runs", "valuation_run_id", "integer"),

    # Category 5: date → text (cloud stored as text)
    ("companies", "next_earnings_date", "text"),
    ("companies", "cdr_ratio_date", "text"),
    ("dividend_history", "payment_date", "text"),
    ("dividend_history", "record_date", "text"),
    ("portfolio_holdings", "first_purchase_date", "text"),
    ("portfolio_transactions", "settlement_date", "text"),

    # Category 6: uuid → text (cloud stored as text)
    ("jobs", "id", "text"),
    ("job_attempts", "id", "text"),
    ("job_attempts", "job_id", "text"),
    ("jobs", "lease_token", "text"),
    ("portfolio_events", "id", "text"),
    ("scheduler_run_history", "id", "text"),
    ("upcoming_dividend_events", "id", "text"),

    # Category 7: other
    ("institutional_investors", "last_filed_period", "date"),
    ("scheduler_state", "interval_hours", "integer"),
    ("data_conflicts", "new_value", "numeric"),
]

conn = psycopg2.connect(DB)
conn.autocommit = True
cur = conn.cursor()

success = 0
fail = 0
for table, col, target_type in FIXES:
    sql = f"ALTER TABLE public.{table} ALTER COLUMN {col} TYPE {target_type} USING {col}::{target_type}"
    try:
        cur.execute(sql)
        success += 1
        print(f"OK: {table}.{col} -> {target_type}")
    except Exception as e:
        fail += 1
        print(f"FAIL: {table}.{col} -> {target_type}: {e}")

print(f"\nDone: {success} succeeded, {fail} failed")
conn.close()
