"""
Create all tables in local Supabase from backup schema, then import data.
Uses direct PostgreSQL connection (psycopg2) for schema creation,
then Supabase REST API for data import.
"""
import json
import os
import sys

import psycopg2
import psycopg2.extensions
from psycopg2.extras import Json, execute_values

# Register JSON adapter for dict/list types
psycopg2.extensions.register_adapter(dict, lambda value: Json(value))
psycopg2.extensions.register_adapter(list, lambda value: Json(value))

# Local dev database only (the standard local Supabase default) -- no real
# credential. Overridable via env for a non-default local setup. I1c: the old
# LOCAL_KEY service-key literal was dead code (this script uses direct psycopg2,
# never the REST API) and has been removed; no secret lives in this file.
LOCAL_DB = os.environ.get("SUPABASE_LOCAL_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "migration_baseline")

# Views to skip during table creation
VIEWS = {
    "portfolio_monthly_dividends",
    "portfolio_user_import_history",
    "super_investor_current_holdings",
    "v_dcf_valuations",
    "v_ddm_valuations",
    "v_owner_earnings_valuations",
    "v_residual_income_valuations",
}


def load_json(path):
    with open(os.path.join(BACKUP_DIR, path), encoding="utf-8") as f:
        return json.load(f)


def pg_type(python_type):
    """Map Python/inferred type to PostgreSQL type."""
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


def create_tables(schema):
    """Create all tables from schema definition."""
    conn = psycopg2.connect(LOCAL_DB)
    conn.autocommit = True
    cur = conn.cursor()

    # Drop existing tables (clean start)
    cur.execute("""
        DO $$ DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)
    print("Dropped existing tables")

    created = 0
    for table_name, columns in schema.items():
        if table_name in VIEWS or not columns:
            continue

        col_defs = []
        for col in columns:
            col_name = col["name"]
            col_type = pg_type(col["type"])
            col_defs.append(f'    {quote_ident(col_name)} {col_type}')

        sql = f"CREATE TABLE {quote_ident(table_name)} (\n" + ",\n".join(col_defs) + "\n);"
        try:
            cur.execute(sql)
            created += 1
        except Exception as e:
            print(f"  ERROR creating {table_name}: {e}")

    print(f"Created {created} tables")
    conn.close()
    return created


def quote_ident(name):
    """Quote identifier for PostgreSQL."""
    return f'"{name}"'


def import_data(schema):
    """Import data using direct PostgreSQL COPY (much faster than REST API)."""
    conn = psycopg2.connect(LOCAL_DB)
    conn.autocommit = True
    cur = conn.cursor()

    data_dir = os.path.join(BACKUP_DIR, "table_data")
    total_imported = 0
    failed = []

    for table_name in sorted(schema.keys()):
        if table_name in VIEWS:
            continue
        if not schema[table_name]:
            continue

        path = os.path.join(data_dir, f"{table_name}.json")
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8") as f:
            rows = json.load(f)

        if not rows:
            continue

        # Get column names from first row
        cols = list(rows[0].keys())
        col_names = ", ".join(quote_ident(c) for c in cols)

        try:
            # Use execute_values for fast bulk insert
            def sanitize(val):
                """Convert dict/list to JSON string for JSONB columns."""
                if isinstance(val, (dict, list)):
                    return Json(val)
                return val

            values = []
            for row in rows:
                vals = tuple(sanitize(row.get(c)) for c in cols)
                values.append(vals)

            insert_sql = f"INSERT INTO {quote_ident(table_name)} ({col_names}) VALUES %s ON CONFLICT DO NOTHING"
            execute_values(cur, insert_sql, values, page_size=1000)
            total_imported += len(rows)
            print(f"  {table_name:<40} {len(rows):>8} rows OK")
        except Exception as e:
            print(f"  {table_name:<40} FAILED: {e}")
            failed.append(table_name)

        conn.commit()

    conn.close()
    return total_imported, failed


def main():
    print("=" * 60)
    print("Local Supabase: Schema Creation + Data Import")
    print("=" * 60)

    schema = load_json("01_schema.json")
    summary = load_json("00_summary.json")

    print(f"\nBackup: {summary['tables_found']} tables, {summary['total_rows']:,} rows")

    # Phase 1: Create tables
    print("\n--- Phase 1: Creating tables ---")
    create_tables(schema)

    # Phase 2: Import data
    print("\n--- Phase 2: Importing data ---")
    total, failed = import_data(schema)

    print(f"\n{'=' * 60}")
    print(f"Import complete: {total:,} rows imported")
    if failed:
        print(f"Failed tables: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
