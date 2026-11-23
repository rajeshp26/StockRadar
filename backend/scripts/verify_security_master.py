"""Verify the security-master data invariants introduced by migration 020.

This is executable evidence for AC-2 and the mixed-lot half of AC-3. It reads the real
local database and fails loudly when an invariant is absent.
"""
from pathlib import Path

import psycopg2

LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ROOT = Path(__file__).resolve().parent.parent


def check(cur, name: str, sql: str, expected: object) -> tuple[bool, object]:
    cur.execute(sql)
    actual = cur.fetchone()[0]
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'} {name}: expected={expected} actual={actual}")
    return ok, actual


def main() -> int:
    conn = psycopg2.connect(LOCAL_DB)
    ok = True
    try:
        with conn.cursor() as cur:
            results = [
                check(cur, "securities listing key is unique", """
                    SELECT count(*) - count(DISTINCT (symbol, exchange, kind, currency, provider_symbol))
                    FROM public.securities
                """, 0),
                check(cur, "every watchlist item has security identity", """
                    SELECT count(*) FROM public.watchlist_items WHERE security_id IS NULL
                """, 0),
                check(cur, "watchlist security belongs to item company", """
                    SELECT count(*) FROM public.watchlist_items wi
                    JOIN public.securities s ON s.security_id = wi.security_id
                    WHERE s.company_id <> wi.company_id
                """, 0),
                check(cur, "every CDR security has underlying and ratio", """
                    SELECT count(*) FROM public.securities
                    WHERE kind = 'CDR'
                      AND (underlying_security_id IS NULL OR cdr_ratio IS NULL)
                """, 0),
                check(cur, "account 9 META CDR lot is 25 shares", """
                    SELECT l.quantity::int FROM public.portfolio_holding_lots l
                    JOIN public.securities s ON s.security_id = l.security_id
                    WHERE l.account_id = 9 AND s.company_id = 145 AND s.kind = 'CDR'
                """, 25),
                check(cur, "account 9 META direct lot is 2 shares", """
                    SELECT l.quantity::int FROM public.portfolio_holding_lots l
                    JOIN public.securities s ON s.security_id = l.security_id
                    WHERE l.account_id = 9 AND s.company_id = 145 AND s.kind <> 'CDR'
                """, 2),
                check(cur, "mixed lots reconcile to holdings quantity", """
                    SELECT (SELECT sum(l.quantity) FROM public.portfolio_holding_lots l
                              JOIN public.securities s ON s.security_id = l.security_id
                             WHERE l.account_id = 9 AND s.company_id = 145)
                         - (SELECT quantity FROM public.portfolio_holdings
                             WHERE account_id = 9 AND company_id = 145)
                """, 0),
                check(cur, "direct quotes seeded from current market data", """
                    SELECT count(*) FROM public.quotes q
                    JOIN public.securities s ON s.security_id = q.security_id
                    WHERE s.kind <> 'CDR' AND q.source = 'migration_020_current_market_data'
                """, 167),
            ]
            ok = all(result[0] for result in results)
    finally:
        conn.close()
    print("SECURITY_MASTER_VERIFIED" if ok else "SECURITY_MASTER_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
