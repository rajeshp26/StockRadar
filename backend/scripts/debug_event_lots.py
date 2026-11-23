"""Show the currency-based lot aggregation migration 020 computed for META."""
import psycopg2

LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> int:
    conn = psycopg2.connect(LOCAL_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT data->>'account_id' AS account_id,
                       data->>'company_id' AS company_id,
                       data->>'activity_type' AS activity_type,
                       data->>'currency' AS currency,
                       (data->>'quantity')::numeric AS quantity,
                       data->>'transaction_date' AS transaction_date
                FROM public.portfolio_events
                WHERE data->>'company_id' = '145'
                  AND data->>'activity_type' IN ('Trade','InternalSecurityTransfer')
                ORDER BY account_id, transaction_date
            """)
            for row in cur.fetchall():
                print(row)

            cur.execute("""
                SELECT
                    (data->>'account_id')::integer AS account_id,
                    sum((data->>'quantity')::numeric) FILTER (
                        WHERE upper(btrim(coalesce(data->>'currency','USD'))) = 'CAD'
                    ) AS cdr_qty,
                    sum((data->>'quantity')::numeric) FILTER (
                        WHERE upper(btrim(coalesce(data->>'currency','USD'))) = 'USD'
                    ) AS direct_qty
                FROM public.portfolio_events
                WHERE data->>'activity_type' IN ('Trade', 'InternalSecurityTransfer')
                  AND data->>'company_id' = '145'
                GROUP BY 1
            """)
            print("aggregates:")
            for row in cur.fetchall():
                print(row)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
