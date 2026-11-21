"""
Cloud Supabase Full Backup Script
Captures schema + all data from cloud Supabase via REST API.
Saves as JSON files for later import into local Supabase.

Usage:
    cd backend
    python scripts/backup_cloud.py              # full backup
    python scripts/backup_cloud.py --dry-run     # test mode (5 rows per table)
"""
import argparse
import json
import os
import sys
import time

from supabase import create_client

CLOUD_URL = os.environ.get("SUPABASE_CLOUD_URL", "")
CLOUD_KEY = os.environ.get("SUPABASE_CLOUD_SERVICE_ROLE_KEY", "")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "migration_baseline")


def require_cloud_credentials() -> tuple[str, str]:
    missing = [
        name
        for name, value in (("SUPABASE_CLOUD_URL", CLOUD_URL), ("SUPABASE_CLOUD_SERVICE_ROLE_KEY", CLOUD_KEY))
        if not value
    ]
    if missing:
        raise SystemExit(
            "ERROR: missing required environment variable(s): "
            + ", ".join(missing)
            + "\nSet them before running this script. Credentials are intentionally"
            "\nnot stored in this repository."
        )
    return CLOUD_URL, CLOUD_KEY

# All known tables from codebase analysis + cloud discovery
ALL_TABLES = [
    # Core business
    "companies", "users", "currencies",
    # Market data
    "current_market_data", "price_history", "price_sources", "price_source_preferences",
    # Financial statements
    "income_statements", "balance_sheets", "cash_flow_statements", "financial_ratios",
    "derived_financial_metrics",
    # Earnings & splits
    "earnings", "splits", "analyst_eps_estimates",
    # Dividends
    "dividend_history", "dividend_metrics", "upcoming_dividend_events",
    # Portfolio
    "portfolio_accounts", "portfolio_holdings", "portfolio_transactions",
    "portfolio_dividends", "portfolio_events", "portfolio_snapshots",
    "portfolio_performance", "portfolio_brokerages", "portfolio_import_history",
    "portfolio_user_import_history", "portfolio_cash_activity", "accounts",
    # Watchlist
    "watchlists", "watchlist_items",
    # Valuation
    "valuation_runs", "valuation_method_defaults", "company_valuation_overrides",
    "intrinsic_value_analysis", "dcf_valuations", "ddm_valuations",
    "industry_multiples", "company_summary", "benchmark_config",
    # Moat analysis
    "moat_analysis", "moat_keyword_evidence", "moat_ai_narratives",
    # Super investors
    "institutional_investors", "institutional_holdings",
    # Scheduler / infrastructure
    "jobs", "job_attempts", "scheduler_state", "scheduler_run_history",
    "worker_heartbeats", "resource_locks", "company_refresh_requests", "scheduler_locks",
    # Event sourcing
    "event_sequence", "projection_checkpoint",
    # FX / data quality
    "exchange_rates", "fx_rate_history", "security_master",
    "data_quality_events", "data_conflicts",
    # Aggregation
    "group_metric_stats", "aggregation_state",
    # Forecast
    "revenue_forecast", "earnings_forecast",
    # Risk
    "risk_ai_narratives",
]


def get_client():
    url, key = require_cloud_credentials()
    return create_client(url, key)


def discover_tables(client):
    """Find which tables actually exist and their row counts."""
    print("Discovering tables...")
    found = []
    for table in ALL_TABLES:
        try:
            r = client.table(table).select("*", count="exact").limit(1).execute()
            count = r.count if hasattr(r, "count") and r.count is not None else len(r.data)
            cols = list(r.data[0].keys()) if r.data else []
            found.append({"name": table, "row_count": count, "columns": cols, "is_view": False})
            status = f"{count:>8} rows" if isinstance(count, int) else "     ? rows"
            print(f"  [OK] {table:<40} {status}")
        except Exception as e:
            err = str(e)
            if "does not exist" in err or "relation" in err or "PGRST205" in err:
                pass  # skip silently
            else:
                print(f"  [??] {table:<40} {err[:60]}")
    print(f"Found {len(found)} tables\n")
    return found


def get_schema(client, table_name):
    """Get column definitions by querying one row."""
    try:
        r = client.table(table_name).select("*").limit(1).execute()
        if not r.data:
            return []
        row = r.data[0]
        schema = []
        for col_name, val in row.items():
            col_type = infer_type(val)
            schema.append({"name": col_name, "type": col_type})
        return schema
    except Exception:
        return []


def infer_type(val):
    """Infer PostgreSQL type from Python value."""
    if val is None:
        return "text"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "numeric"
    if isinstance(val, str):
        if len(val) == 10 and val[4] == "-" and val[7] == "-":
            return "date"
        if "T" in val and ":" in val and ("Z" in val or "+" in val):
            return "timestamptz"
        return "text"
    if isinstance(val, dict):
        return "jsonb"
    if isinstance(val, list):
        return "jsonb"
    return "text"


def export_table(client, table_name, limit=None):
    """Export all data from a table with pagination."""
    page_size = 1000
    all_rows = []
    offset = 0

    while True:
        query = client.table(table_name).select("*").order("id", desc=False).range(offset, offset + page_size - 1)
        if limit and len(all_rows) >= limit:
            break
        try:
            r = query.execute()
        except Exception:
            # Table might not have 'id' column, try without ordering
            try:
                query = client.table(table_name).select("*").range(offset, offset + page_size - 1)
                r = query.execute()
            except Exception as e:
                print(f"    ERROR exporting {table_name}: {e}")
                return []

        if not r.data:
            break

        all_rows.extend(r.data)
        if len(r.data) < page_size:
            break
        offset += page_size

    if limit:
        all_rows = all_rows[:limit]

    return all_rows


def run_backup(dry_run=False):
    """Execute full cloud backup."""
    os.makedirs(OUT_DIR, exist_ok=True)
    client = get_client()

    # Phase 1: Discover tables
    tables = discover_tables(client)

    # Phase 2: Get schema for each table
    print("Capturing schema...")
    schema = {}
    for t in tables:
        cols = get_schema(client, t["name"])
        schema[t["name"]] = cols
        print(f"  {t['name']:<40} {len(cols)} columns")

    # Phase 3: Export data
    max_rows = 5 if dry_run else None
    mode = "DRY RUN (5 rows/table)" if dry_run else "FULL BACKUP"
    print(f"\nExporting data [{mode}]...")
    exported = {}
    total_rows = 0
    for t in tables:
        name = t["name"]
        rows = export_table(client, name, limit=max_rows)
        exported[name] = rows
        total_rows += len(rows)
        print(f"  {name:<40} {len(rows):>8} rows exported")

    # Phase 4: Save everything
    # 4a: Schema
    with open(os.path.join(OUT_DIR, "01_schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, default=str)

    # 4b: Data (one file per table)
    data_dir = os.path.join(OUT_DIR, "table_data")
    os.makedirs(data_dir, exist_ok=True)
    for name, rows in exported.items():
        with open(os.path.join(data_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)

    # 4c: Summary
    summary = {
        "cloud_url": CLOUD_URL,
        "backup_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "dry_run" if dry_run else "full",
        "tables_found": len(tables),
        "total_rows": total_rows,
        "tables": {
            t["name"]: {"row_count": t["row_count"], "columns": len(schema.get(t["name"], []))}
            for t in tables
        },
    }
    with open(os.path.join(OUT_DIR, "00_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # 4d: Row count baseline
    counts = {t["name"]: t["row_count"] for t in tables}
    with open(os.path.join(OUT_DIR, "02_row_counts.json"), "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)

    print("\nBackup complete.")
    print(f"  Tables: {len(tables)}")
    print(f"  Total rows exported: {total_rows:,}")
    print(f"  Output: {OUT_DIR}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Backup cloud Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Test mode: 5 rows per table")
    args = parser.parse_args()
    return run_backup(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
