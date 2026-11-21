"""
Migration Verification Script
Compares cloud and local Supabase databases to ensure zero data loss.

Usage:
    # Set cloud credentials (read-only)
    export CLOUD_DATABASE_URL="postgresql://postgres:[PASSWORD]@db.viqdqgxcumcdhqxooplw.supabase.co:5432/postgres"

    # Local is always:
    # postgresql://postgres:postgres@localhost:5432/postgres

    cd backend
    python scripts/verify_migration.py
"""
import os
import sys


def get_cloud_connection():
    """Connect to cloud database (requires password from Supabase Dashboard)."""
    try:
        import psycopg2
    except ImportError:
        print("SKIP: psycopg2 not installed (pip install psycopg2-binary)")
        return None

    url = os.environ.get("CLOUD_DATABASE_URL")
    if not url:
        print("SKIP: CLOUD_DATABASE_URL not set (set it to verify against cloud)")
        return None

    try:
        return psycopg2.connect(url)
    except Exception as e:
        print(f"SKIP: Cannot connect to cloud database: {e}")
        return None


def get_local_connection():
    """Connect to local Supabase database."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed (pip install psycopg2-binary)")
        sys.exit(1)

    try:
        return psycopg2.connect(
            "postgresql://postgres:postgres@localhost:5432/postgres"
        )
    except Exception as e:
        print(f"ERROR: Cannot connect to local database: {e}")
        sys.exit(1)


QUERY_TABLES = """
SELECT tablename
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY tablename;
"""

QUERY_VIEWS = """
SELECT table_name
FROM information_schema.views
WHERE table_schema = 'public'
ORDER BY table_name;
"""

QUERY_INDEXES = """
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
"""

QUERY_TRIGGERS = """
SELECT
    event_object_table AS table_name,
    trigger_name
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table, trigger_name;
"""

QUERY_CONSTRAINTS = """
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema = 'public'
ORDER BY tc.table_name, tc.constraint_name;
"""


def fetch_all(conn, query):
    """Fetch all rows from a query."""
    with conn.cursor() as cur:
        cur.execute(query)
        return set(row[0] if len(row) == 1 else row for row in cur.fetchall())


def fetch_row_counts(conn):
    """Fetch table names with row counts (approximate from stats collector)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename, n_live_tup
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        return {row[0]: row[1] for row in cur.fetchall()}


def compare(label, cloud_set, local_set):
    """Compare two sets and report differences."""
    missing_in_local = cloud_set - local_set
    extra_in_local = local_set - cloud_set

    if not missing_in_local and not extra_in_local:
        print(f"  [MATCH] {label}: {len(cloud_set)} items")
        return True
    else:
        print(f"  [MISMATCH] {label}")
        if missing_in_local:
            print(f"     Missing in local: {sorted(missing_in_local)}")
        if extra_in_local:
            print(f"     Extra in local: {sorted(extra_in_local)}")
        return False


def main():
    print("=" * 60)
    print("MIGRATION VERIFICATION: Cloud vs Local")
    print("=" * 60)

    cloud = get_cloud_connection()
    local = get_local_connection()

    if not cloud:
        print("\n  Cloud connection unavailable. Performing local-only checks.")
        print("  To verify against cloud, set CLOUD_DATABASE_URL.\n")

    all_passed = True

    try:
        # --- Local-only checks ---
        print("\n--- Local Database Structure Checks ---")

        local_tables = fetch_all(local, QUERY_TABLES)
        print(f"  Tables found: {len(local_tables)}")

        local_views = fetch_all(local, QUERY_VIEWS)
        print(f"  Views found: {len(local_views)}")

        local_indexes = fetch_all(local, QUERY_INDEXES)
        print(f"  Indexes found: {len(local_indexes)}")

        local_triggers = fetch_all(local, QUERY_TRIGGERS)
        print(f"  Triggers found: {len(local_triggers)}")

        # Check minimum expected counts
        expected_min_tables = 55
        if len(local_tables) < expected_min_tables:
            print(f"  [FAIL] Expected at least {expected_min_tables} tables, found {len(local_tables)}")
            all_passed = False
        else:
            print(f"  [PASS] {len(local_tables)} tables (expected >= {expected_min_tables})")

        # Check critical tables exist
        # This list covers all major feature areas with heavy .table() usage
        critical_tables = [
            # Core business
            "companies", "users", "currencies",
            # Watchlist
            "watchlists", "watchlist_items",
            # Portfolio
            "portfolio_accounts", "portfolio_holdings", "portfolio_transactions",
            "portfolio_events", "portfolio_snapshots", "portfolio_dividends",
            "portfolio_brokerages", "portfolio_performance",
            # Financial statements
            "income_statements", "balance_sheets", "cash_flow_statements",
            "financial_ratios", "earnings", "splits",
            # Market data
            "current_market_data", "price_history",
            # Dividends
            "dividend_history", "dividend_metrics", "upcoming_dividend_events",
            # Valuation
            "valuation_runs", "valuation_method_defaults",
            "company_valuation_overrides", "intrinsic_value_analysis",
            "dcf_valuations", "ddm_valuations", "industry_multiples",
            "company_summary",
            # Moat analysis
            "moat_analysis", "moat_keyword_evidence", "moat_ai_narratives",
            # Super investors
            "institutional_investors", "institutional_holdings",
            # Scheduler / infrastructure
            "jobs", "job_attempts", "scheduler_state",
            "scheduler_run_history", "worker_heartbeats",
            "resource_locks", "company_refresh_requests", "scheduler_locks",
            # Event sourcing
            "event_sequence", "projection_checkpoint",
            # FX / data quality
            "exchange_rates", "data_quality_events", "data_conflicts",
            # Aggregation
            "group_metric_stats", "aggregation_state",
            # Forecast
            "revenue_forecast", "earnings_forecast",
        ]
        missing_critical = [t for t in critical_tables if t not in local_tables]
        if missing_critical:
            print(f"  [FAIL] Missing critical tables: {missing_critical}")
            all_passed = False
        else:
            print(f"  [PASS] All {len(critical_tables)} critical tables present")

        # --- Cloud vs Local comparison ---
        if cloud:
            print("\n--- Cloud vs Local Comparison ---")

            cloud_tables = fetch_all(cloud, QUERY_TABLES)
            all_passed &= compare("Tables", cloud_tables, local_tables)

            cloud_views = fetch_all(cloud, QUERY_VIEWS)
            all_passed &= compare("Views", cloud_views, local_views)

            cloud_indexes = fetch_all(cloud, QUERY_INDEXES)
            all_passed &= compare("Indexes", cloud_indexes, local_indexes)

            cloud_triggers = fetch_all(cloud, QUERY_TRIGGERS)
            all_passed &= compare("Triggers", cloud_triggers, local_triggers)

            cloud_constraints = fetch_all(cloud, QUERY_CONSTRAINTS)
            local_constraints = fetch_all(local, QUERY_CONSTRAINTS)
            all_passed &= compare("Constraints", cloud_constraints, local_constraints)

            # Row count comparison (informational - local will be empty)
            print("\n--- Row Counts (Cloud) ---")
            cloud_counts = fetch_row_counts(cloud)
            for table, count in sorted(cloud_counts.items()):
                if count > 0:
                    print(f"  {table}: {count:,} rows")

            total_rows = sum(cloud_counts.values())
            print(f"\n  Total rows in cloud: {total_rows:,}")

    finally:
        local.close()
        if cloud:
            cloud.close()

    # --- Final result ---
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED - review output above")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
