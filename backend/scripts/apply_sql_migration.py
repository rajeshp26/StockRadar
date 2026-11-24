"""Apply a single SQL migration file to the local Supabase database.

Used to verify a migration is idempotent: run it twice and confirm the second
run changes nothing (idempotency is a claim until executed twice). The
before/after comparison covers CDR state, installed triggers, the event log,
stale provider_symbol rows and check constraints on public.securities, so a
migration that only creates DDL is still measured rather than reported as a
no-op it never was. The provider_symbol count matters: migration 021 was once
"verified" with a snapshot that could not see the seven rows it changed, and
the defect stayed live.

Usage:
    python scripts/apply_sql_migration.py 013_checkpoint_backdating_invariant.sql
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
MIGRATIONS = BACKEND / "supabase" / "migrations"
LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def snapshot(conn) -> dict:
    """Capture the state a migration can actually be responsible for.

    The CDR tables alone are not enough to judge a migration that creates a
    trigger, a function, or touches the event log: those changes are invisible
    to a CDR-only reading, so a schema migration reports "no change" whether or
    not it did anything. The DDL and event-log fingerprints below are what make
    the before/after comparison mean something for those migrations.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.companies')")
        if cur.fetchone()[0] is None:
            return {"ratios": [], "tor_holdings": 0, "ddl": [], "events": None}

        cur.execute("SELECT company_id, cdr_ratio FROM companies ORDER BY company_id")
        ratios = [(r[0], str(r[1])) for r in cur.fetchall()]

        cur.execute("SELECT count(*) FROM portfolio_holdings WHERE exchange_override='TOR'")
        tor = cur.fetchone()[0]

        cur.execute(
            "SELECT c.relname || '.' || t.tgname || ':' || t.tgenabled::text "
            "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE NOT t.tgisinternal ORDER BY 1"
        )
        ddl = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT count(*), max(created_at)::text FROM portfolio_events")
        events = cur.fetchone()

        cur.execute(
            "SELECT to_regclass('public.securities') IS NOT NULL AND "
            "to_regclass('public.quotes') IS NOT NULL AND "
            "to_regclass('public.portfolio_holding_lots') IS NOT NULL"
        )
        security_state = None
        if cur.fetchone()[0]:
            cur.execute("""
                SELECT
                    (SELECT count(*) FROM public.securities),
                    (SELECT count(*) FROM public.quotes),
                    (SELECT count(*) FROM public.portfolio_holding_lots),
                    (SELECT count(*) FROM public.watchlist_items WHERE security_id IS NULL),
                    (SELECT count(*) FROM public.portfolio_holding_lots l
                       JOIN public.securities s ON s.security_id = l.security_id
                      WHERE s.company_id = 145),
                    (SELECT count(*) FROM public.securities s
                      WHERE s.provider_symbol IS DISTINCT FROM (
                          CASE
                              WHEN position('.' in s.symbol) > 0 THEN s.symbol
                              ELSE s.symbol || CASE s.exchange
                                  WHEN 'TSX' THEN '.TO'
                                  WHEN 'NEO' THEN '.NE'
                                  WHEN 'TSXV' THEN '.V'
                                  ELSE ''
                              END
                          END
                      )),
                    (SELECT count(*) FROM pg_constraint
                      WHERE conrelid = 'public.securities'::regclass
                        AND contype = 'c')
            """)
            security_state = cur.fetchone()

    return {
        "ratios": sorted(ratios),
        "tor_holdings": tor,
        "ddl": ddl,
        "events": (events[0], events[1]),
        "security_master": security_state,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    name = sys.argv[1]
    if not name.endswith(".sql"):
        name += ".sql"
    path = MIGRATIONS / name
    if not path.exists():
        print(f"ERROR: migration not found: {path}")
        return 2

    sys.path.insert(0, str(BACKEND))
    import psycopg2

    conn = psycopg2.connect(LOCAL_DB)
    print(f"=== BEFORE ({name}) ===")
    before = snapshot(conn)
    polluted = [r for r in before["ratios"] if r[1] not in ("None", "10.00")]
    print(f"  companies with a ratio : {sum(1 for r in before['ratios'] if r[1] != 'None')}")
    print(f"  non-structural ratios  : {len(polluted)}")
    for cid, ratio in polluted:
        print(f"    company {cid}: ratio={ratio}")
    print(f"  TOR holdings           : {before['tor_holdings']}")
    print(f"  triggers installed     : {len(before['ddl'])}")
    print(f"  portfolio_events       : {before['events'][0]} rows, latest {before['events'][1]}")
    print(f"  security master        : {before['security_master']}")

    sql = path.read_text(encoding="utf-8")
    print(f"\n=== APPLYING {name} ===")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("applied")

    after = snapshot(conn)
    print(f"\n=== AFTER ({name}) ===")
    print(f"  companies with a ratio : {sum(1 for r in after['ratios'] if r[1] != 'None')}")
    print(f"  non-structural ratios  : {len([r for r in after['ratios'] if r[1] not in ('None','10.00')])}")
    print(f"  TOR holdings           : {after['tor_holdings']}")
    print(f"  triggers installed     : {len(after['ddl'])}")
    print(f"  portfolio_events       : {after['events'][0]} rows, latest {after['events'][1]}")
    print(f"  security master        : {after['security_master']}")

    if before == after:
        print("\nRESULT: no change (idempotent no-op)")
    else:
        print("\nRESULT: state changed (this run was the applying run)")
        for key in ("ratios", "tor_holdings", "ddl", "events", "security_master"):
            if before[key] != after[key]:
                print(f"  - {key} changed")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
