"""
Full Schema Migration: Drop all tables, recreate with proper DDL, reimport data.
This fixes wrong types (UUID→text, SERIAL→bigint, etc.) and adds all constraints.

Usage:
    cd backend
    python scripts/full_schema_migration.py
"""
import json
import os
import sys

import psycopg2
import psycopg2.extensions
from psycopg2.extras import Json, execute_values

LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "migration_baseline")
SCHEMA_SQL = os.path.join(os.path.dirname(__file__), "restore_all_constraints.sql")

# Tables to skip (views, not real tables)
VIEWS = {
    "portfolio_monthly_dividends",
    "portfolio_user_import_history",
    "super_investor_current_holdings",
    "v_dcf_valuations",
    "v_ddm_valuations",
    "v_owner_earnings_valuations",
    "v_residual_income_valuations",
}

# FK dependency order: parent tables before children
IMPORT_ORDER = [
    # Tier 0: base tables (no FK dependencies)
    "currencies",
    "users",
    # Tier 1: depend on currencies or users
    "companies",
    # Tier 2: depend on companies
    "aggregation_state",
    "exchange_rates",
    "portfolio_brokerages",
    "institutional_investors",
    "valuation_method_defaults",
    "company_refresh_requests",
    "scheduler_state",
    "worker_heartbeats",
    "jobs",
    # Tier 2b: depend on jobs
    "job_attempts",
    # Tier 3: depend on companies + others
    "portfolio_accounts",
    "watchlists",
    "watchlist_items",  # depends on watchlists + companies
    "portfolio_events",  # event sourcing table
    "benchmark_config",
    "scheduler_run_history",
    "scheduler_locks",
    "resource_locks",
    "security_master",
    "moat_analysis",
    "moat_keyword_evidence",
    "moat_ai_narratives",
    "data_quality_events",
    "data_conflicts",
    "company_summary",
    "current_market_data",
    "company_valuation_overrides",
    "industry_multiples",
    "analyst_eps_estimates",
    "price_sources",
    "price_source_preferences",
    "derived_financial_metrics",
    "fx_rate_history",
    "portfolio_cash_activity",
    "projection_checkpoint",
    "risk_ai_narratives",
    "event_sequence",
    "portfolio_performance",
    # Tier 4: depend on companies + portfolio_accounts
    "portfolio_holdings",
    "portfolio_transactions",
    "portfolio_snapshots",
    "portfolio_import_history",
    "portfolio_dividends",
    # Tier 5: financial data
    "balance_sheets",
    "cash_flow_statements",
    "income_statements",
    "financial_ratios",
    "earnings",
    "earnings_forecast",
    "revenue_forecast",
    "dividend_history",
    "dividend_metrics",
    "price_history",
    "splits",
    "institutional_holdings",
    "intrinsic_value_analysis",
    "upcoming_dividend_events",
    "dcf_valuations",
    "ddm_valuations",
    "valuation_runs",
    "group_metric_stats",
]


def load_json(path):
    with open(os.path.join(BACKUP_DIR, path), encoding="utf-8") as f:
        return json.load(f)


def quote_ident(name):
    return f'"{name}"'


def pg_type(python_type):
    mapping = {
        "text": "TEXT",
        "integer": "BIGINT",
        "numeric": "NUMERIC",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMPTZ",
        "timestamptz": "TIMESTAMPTZ",
        "jsonb": "JSONB",
    }
    return mapping.get(python_type, "TEXT")


def phase1_drop_all(conn):
    """Drop all tables, views, and functions via Docker psql."""
    import subprocess
    import tempfile
    docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    print("\n--- Phase 1: Dropping all objects ---")

    drop_sql = """
-- Drop views
DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT viewname FROM pg_views WHERE schemaname = 'public' LOOP
        EXECUTE 'DROP VIEW IF EXISTS public.' || quote_ident(r.viewname) || ' CASCADE';
    END LOOP;
END $$;

-- Drop tables
DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

-- Drop functions
DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT p.proname, pg_get_function_identity_arguments(p.oid) as argtypes
              FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
              WHERE n.nspname = 'public' LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS public.' || quote_ident(r.proname) || '(' || r.argtypes || ') CASCADE';
    END LOOP;
END $$;
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
        f.write(drop_sql)
        tmp_path = f.name

    try:
        sql_in_container = "/tmp/drop_all.sql"
        subprocess.run([docker, "cp", tmp_path, f"supabase_db_StockerPro:{sql_in_container}"], check=True)
        result = subprocess.run(
            [docker, "exec", "supabase_db_StockerPro", "psql", "-U", "postgres", "-d", "postgres", "-f", sql_in_container],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print("  All objects dropped")
        else:
            print("  Drop completed with warnings")
    finally:
        os.unlink(tmp_path)


def phase2_create_schema(conn):
    """Run the full schema SQL via Docker psql (handles mixed statement types)."""
    print("\n--- Phase 2: Creating schema from restore_all_constraints.sql ---")
    import subprocess
    docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

    # Copy SQL file to container
    sql_in_container = "/tmp/restore_all_constraints.sql"
    subprocess.run([docker, "cp", SCHEMA_SQL, f"supabase_db_StockerPro:{sql_in_container}"], check=True)

    # Execute via psql
    result = subprocess.run(
        [docker, "exec", "supabase_db_StockerPro", "psql", "-U", "postgres", "-d", "postgres", "-f", sql_in_container],
        capture_output=True, text=True, timeout=120
    )

    errors = [line for line in result.stderr.split('\n') if line.strip() and 'ERROR' in line]
    notices = [line for line in result.stderr.split('\n') if line.strip() and 'NOTICE' in line]

    if errors:
        print(f"  Schema created with {len(errors)} errors:")
        for e in errors[:10]:
            print(f"    {e[:120]}")
    else:
        print(f"  Schema created successfully ({len(notices)} notices)")

    # Verify table count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
    table_count = cur.fetchone()[0]
    print(f"  Tables created: {table_count}")

    if table_count < 40:
        print(f"  WARNING: Expected ~60 tables, only {table_count} found!")


def phase3_import_data(conn):
    """Import data from JSON backup files in FK-dependency order."""
    print("\n--- Phase 3: Importing data ---")
    cur = conn.cursor()
    schema = load_json("01_schema.json")
    data_dir = os.path.join(BACKUP_DIR, "table_data")

    total_imported = 0
    failed = []

    # Determine tables to import
    tables_to_import = set()
    for table_name in sorted(schema.keys()):
        if table_name in VIEWS:
            continue
        if not schema[table_name]:
            continue
        path = os.path.join(data_dir, f"{table_name}.json")
        if os.path.exists(path):
            tables_to_import.add(table_name)

    # Use IMPORT_ORDER first, then append remaining tables
    ordered = [t for t in IMPORT_ORDER if t in tables_to_import]
    remaining = sorted(tables_to_import - set(ordered))
    ordered.extend(remaining)

    for table_name in ordered:
        path = os.path.join(data_dir, f"{table_name}.json")
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)

        if not rows:
            continue

        cols = list(rows[0].keys())
        col_names = ", ".join(quote_ident(c) for c in cols)

        try:
            def sanitize(val):
                if isinstance(val, (dict, list)):
                    return Json(val)
                return val

            values = []
            for row in rows:
                vals = tuple(sanitize(row.get(c)) for c in cols)
                values.append(vals)

            # Handle GENERATED ALWAYS identity columns
            identity_tables = {
                "exchange_rates": "id",
                "company_summary": "summary_id",
                "earnings_forecast": "earnings_forecast_id",
                "revenue_forecast": "forecast_id",
                "splits": "split_id",
            }
            if table_name in identity_tables and identity_tables[table_name] in cols:
                insert_sql = f"INSERT INTO {quote_ident(table_name)} ({col_names}) OVERRIDING SYSTEM VALUE VALUES %s ON CONFLICT DO NOTHING"
            else:
                insert_sql = f"INSERT INTO {quote_ident(table_name)} ({col_names}) VALUES %s ON CONFLICT DO NOTHING"

            try:
                execute_values(cur, insert_sql, values, page_size=1000)
            except psycopg2.errors.ForeignKeyViolation:
                conn.rollback()
                inserted = 0
                skipped = 0
                placeholders = ", ".join(["%s"] * len(cols))
                single_sql = f"INSERT INTO {quote_ident(table_name)} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                for val_tuple in values:
                    try:
                        cur.execute(single_sql, val_tuple)
                        inserted += 1
                    except Exception:
                        skipped += 1
                        conn.rollback()
                if inserted > 0:
                    conn.commit()
                total_imported += inserted
                print(f"  {table_name:<40} {inserted}/{len(rows)} rows OK ({skipped} FK-skipped)")
                continue
            total_imported += len(rows)
            print(f"  {table_name:<40} {len(rows):>8} rows OK")
        except Exception as e:
            print(f"  {table_name:<40} FAILED: {e}")
            failed.append(table_name)

        conn.commit()

    print(f"\n  Total imported: {total_imported:,} rows")
    if failed:
        print(f"  Failed tables: {failed}")
    return total_imported, failed


def phase4_recreate_views(conn):
    """Recreate all views via Docker psql."""
    print("\n--- Phase 4: Recreating views ---")
    import subprocess
    import tempfile
    docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

    views_sql = """
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
    """

    # Write SQL to temp file and execute via Docker
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
        f.write(views_sql)
        tmp_path = f.name

    try:
        sql_in_container = "/tmp/views.sql"
        subprocess.run([docker, "cp", tmp_path, f"supabase_db_StockerPro:{sql_in_container}"], check=True)
        result = subprocess.run(
            [docker, "exec", "supabase_db_StockerPro", "psql", "-U", "postgres", "-d", "postgres", "-f", sql_in_container],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("  All 7 views created")
        else:
            print("  Views created with warnings")
    finally:
        os.unlink(tmp_path)


def phase5_grant_permissions(conn):
    """Grant permissions to Supabase roles via Docker psql."""
    print("\n--- Phase 5: Granting permissions ---")
    import subprocess
    import tempfile
    docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

    grant_sql = """
DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.' || quote_ident(r.tablename) || ' TO service_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.' || quote_ident(r.tablename) || ' TO anon';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.' || quote_ident(r.tablename) || ' TO authenticated';
    END LOOP;
END $$;

DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public' LOOP
        EXECUTE 'GRANT USAGE, SELECT ON public.' || quote_ident(r.sequence_name) || ' TO service_role';
        EXECUTE 'GRANT USAGE, SELECT ON public.' || quote_ident(r.sequence_name) || ' TO anon';
        EXECUTE 'GRANT USAGE, SELECT ON public.' || quote_ident(r.sequence_name) || ' TO authenticated';
    END LOOP;
END $$;

DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT viewname FROM pg_views WHERE schemaname = 'public' LOOP
        EXECUTE 'GRANT SELECT ON public.' || quote_ident(r.viewname) || ' TO service_role';
        EXECUTE 'GRANT SELECT ON public.' || quote_ident(r.viewname) || ' TO anon';
        EXECUTE 'GRANT SELECT ON public.' || quote_ident(r.viewname) || ' TO authenticated';
    END LOOP;
END $$;
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
        f.write(grant_sql)
        tmp_path = f.name

    try:
        sql_in_container = "/tmp/grant.sql"
        subprocess.run([docker, "cp", tmp_path, f"supabase_db_StockerPro:{sql_in_container}"], check=True)
        result = subprocess.run(
            [docker, "exec", "supabase_db_StockerPro", "psql", "-U", "postgres", "-d", "postgres", "-f", sql_in_container],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("  Permissions granted to all roles")
        else:
            print("  Permissions granted with warnings")
    finally:
        os.unlink(tmp_path)


def phase6_verify(conn):
    """Verify the migration."""
    print("\n--- Phase 6: Verification ---")
    cur = conn.cursor()

    # Count tables
    cur.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
    table_count = cur.fetchone()[0]
    print(f"  Tables: {table_count}")

    # Count views
    cur.execute("SELECT COUNT(*) FROM pg_views WHERE schemaname = 'public'")
    view_count = cur.fetchone()[0]
    print(f"  Views: {view_count}")

    # Count constraints
    cur.execute("SELECT COUNT(*) FROM pg_constraint WHERE connamespace = 'public'::regnamespace")
    constraint_count = cur.fetchone()[0]
    print(f"  Constraints: {constraint_count}")

    # Count indexes
    cur.execute("SELECT COUNT(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'i'")
    index_count = cur.fetchone()[0]
    print(f"  Indexes: {index_count}")

    # Verify key constraints exist
    checks = [
        ("scheduler_state PK", "SELECT 1 FROM pg_constraint WHERE conname = 'scheduler_state_pkey'"),
        ("worker_heartbeats PK", "SELECT 1 FROM pg_constraint WHERE conname = 'worker_heartbeats_pkey'"),
        ("jobs PK", "SELECT 1 FROM pg_constraint WHERE conname = 'jobs_pkey'"),
        ("companies PK", "SELECT 1 FROM pg_constraint WHERE conname = 'companies_new_pkey'"),
        ("users PK", "SELECT 1 FROM pg_constraint WHERE conname = 'users_pkey'"),
        ("portfolio_events PK", "SELECT 1 FROM pg_constraint WHERE conname = 'portfolio_events_pkey'"),
    ]
    for name, sql in checks:
        cur.execute(sql)
        exists = cur.fetchone() is not None
        status = "OK" if exists else "MISSING"
        print(f"  {name}: {status}")

    # Count total rows
    cur.execute("""
        SELECT SUM(n_live_tup) FROM pg_stat_user_tables
        WHERE schemaname = 'public'
    """)
    total_rows = cur.fetchone()[0] or 0
    print(f"  Total rows: {total_rows:,}")


def main():
    print("=" * 60)
    print("Full Schema Migration: Drop + Recreate + Import")
    print("=" * 60)

    conn = psycopg2.connect(LOCAL_DB)
    conn.autocommit = True

    try:
        phase1_drop_all(conn)
        phase2_create_schema(conn)
        phase3_import_data(conn)
        phase4_recreate_views(conn)
        phase5_grant_permissions(conn)
        phase6_verify(conn)

        print("\n" + "=" * 60)
        print("Migration complete!")
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
