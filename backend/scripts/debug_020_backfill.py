"""Run migration 020 up to the watchlist NOT NULL gate and report any unbackfilled rows.

Rolls back unconditionally: this is a diagnostic, never a migration runner.
"""
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "supabase" / "migrations" / "020_security_master.sql").read_text(encoding="utf-8")
STOP = "ALTER TABLE public.watchlist_items ALTER COLUMN security_id SET NOT NULL;"
SQL = SQL.split(STOP)[0] + "SELECT 1;\n"
LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> int:
    conn = psycopg2.connect(LOCAL_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(SQL)
            cur.execute("""
                SELECT wi.watchlist_item_id, wi.company_id, c.ticker_symbol, c.exchange,
                       count(s.security_id) AS direct_securities
                FROM public.watchlist_items wi
                LEFT JOIN public.securities s
                  ON s.company_id = wi.company_id AND s.kind = 'COMMON'
                LEFT JOIN public.companies c ON c.company_id = wi.company_id
                WHERE wi.security_id IS NULL
                GROUP BY wi.watchlist_item_id, wi.company_id, c.ticker_symbol, c.exchange
                ORDER BY wi.watchlist_item_id
                LIMIT 30
            """)
            rows = cur.fetchall()
            print(f"unbackfilled watchlist rows: {len(rows)} (first 30)")
            for row in rows:
                print("  ", row)
            cur.execute("SELECT count(*) FROM public.securities")
            print("securities:", cur.fetchone()[0])
    finally:
        conn.rollback()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
