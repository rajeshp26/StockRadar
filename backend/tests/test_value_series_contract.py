"""
Contract tests for the live portfolio_value_series table.

These assert the properties that a repository cannot assert about itself, because
they only exist in the running stack:

  * every column the code selects or writes exists on the live table
  * the unique constraint the upsert conflicts on exists
  * RLS is enabled, and service_role holds the GRANTs (RLS and GRANT are two
    different layers; Postgres requires both, and 017 shipped only RLS)
  * a write/read/delete round trip survives PostgREST, the schema cache and RLS

They replace two standalone `scripts/verify_*.py` programs that printed
`PASS: shape correct` for a table missing two columns. A check that lives outside
the test runner has no exit code contract, is not collected, and is not run -
that is how 100% write loss went unnoticed.

Run with:
    RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_value_series_contract.py -v
    python tasks.py db-check          (from the repository root)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

# Ensure backend/ is on the path, then take real values over conftest's fakes -
# conftest sets SUPABASE_URL to http://test.db.local, which would block the stack.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

import psycopg2  # noqa: E402  (imports follow load_dotenv on purpose: config first)
import pytest  # noqa: E402

from infrastructure.repositories.portfolio_value_series_repository import (  # noqa: E402
    REQUIRED_COLUMNS,
    PortfolioValueSeriesRepository,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run against the live stack",
    ),
]

#: The direct connection, not the PostgREST URL: catalog queries are not exposed
#: through the API. Defaults to the documented local instance.
DB_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("LOCAL_DB")
    or "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)

TABLE = "portfolio_value_series"
PROBE_KEY = "__contract_probe__"


@pytest.fixture(scope="module")
def db():
    """Catalog connection. An unreachable stack fails loudly rather than passing."""
    try:
        conn = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment
        pytest.fail(
            f"cannot reach {DB_URL}: {exc}. A schema contract that cannot reach the "
            "database is unverifiable, not satisfied."
        )
    conn.autocommit = True
    yield conn
    conn.close()


# ── Shape ────────────────────────────────────────────────────────────────────


def test_live_table_has_every_column_the_repository_uses(db):
    with db.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{TABLE}",))
        assert cur.fetchone()[0] is not None, f"{TABLE} does not exist - apply migration 017"

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (TABLE,),
        )
        live = {row[0] for row in cur.fetchall()}

    # REQUIRED_COLUMNS comes from the repository, never a copy kept here. The
    # verifier this replaces kept its own list and drifted behind the code.
    missing = sorted(set(REQUIRED_COLUMNS) - live)
    assert not missing, (
        f"{TABLE} is missing {missing}. Every write is rejected with PGRST204/42703 "
        "and silently discarded. Re-run migration 017 (it is idempotent)."
    )


def test_unique_constraint_supports_the_upsert_conflict_target(db):
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT array_agg(a.attname ORDER BY a.attname)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN unnest(c.conkey) AS k(attnum) ON TRUE
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
            WHERE t.relname = %s AND c.contype = 'u'
            GROUP BY c.oid
            """,
            (TABLE,),
        )
        unique_sets = [set(row[0]) for row in cur.fetchall()]

    # Without this, the upsert has no conflict target and fails only at first write.
    assert {"account_key", "series_date"} in unique_sets, (
        f"no UNIQUE(account_key, series_date) on {TABLE}; found {unique_sets}"
    )


# ── Privileges: the layer that was missing ───────────────────────────────────


def test_rls_is_enabled(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)",
            (f"public.{TABLE}",),
        )
        row = cur.fetchone()
    assert row is not None and row[0] is True, f"RLS is not enabled on {TABLE}"


def test_service_role_holds_the_grants_rls_does_not_provide(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema = 'public' AND table_name = %s "
            "AND grantee = 'service_role'",
            (TABLE,),
        )
        granted = {row[0].upper() for row in cur.fetchall()}

    missing = {"SELECT", "INSERT", "UPDATE", "DELETE"} - granted
    assert not missing, (
        f"service_role lacks {sorted(missing)} on {TABLE} - PostgREST answers 42501 "
        "and the repository degrades to live computation with an empty read model. "
        "Apply migration 019_grant_portfolio_value_series_privileges.sql."
    )


# ── Round trip through the real client ───────────────────────────────────────


def _probe_points(days: int) -> list[dict]:
    base = date(2026, 1, 1)
    return [
        {
            "date": base + timedelta(days=i),
            "value": 1000.0 + i * 10,
            "holdings_market_value": 900.0 + i * 10,
            "cost_basis": 800.0,
            "cash_balance": 100.0,
            "net_deposits": 700.0,
            "fx_unconverted_count": 1 if i == 1 else 0,
            "points_used": 2,
            "locf_filled": 1 if i == 2 else 0,
            "spike_suppressed": 1 if i == 1 else 0,
        }
        for i in range(days)
    ]


def test_write_read_delete_round_trip():
    """The end-to-end proof: PostgREST + schema cache + RLS + the real repository."""
    # Build the client from this module's environment rather than using the global
    # `supabase` proxy: `config.settings` is a singleton read at import time, so when
    # the whole suite is collected conftest's fake SUPABASE_URL wins and the write
    # fails with getaddrinfo. Repairing that ordering in the test is not the fix -
    # the app sets its environment before it imports anything, a test cannot.
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if "test.db.local" in url or not key:
        pytest.fail(
            f"integration config not resolved (url={url!r}, key set={bool(key)}); "
            "load_dotenv was expected to override conftest's fakes"
        )

    repo = PortfolioValueSeriesRepository(client=create_client(url, key))
    repo.delete_account_key(PROBE_KEY)

    try:
        written = repo.upsert_points(
            PROBE_KEY, _probe_points(3), fingerprint="probe-fp", last_mark_date=date(2026, 1, 3)
        )
        assert written == 3, f"wrote {written} of 3 rows - the database rejected the write"

        stored = repo.get_series(PROBE_KEY)
        assert len(stored.points) == 3
        assert stored.fingerprint == "probe-fp"
        assert stored.last_mark_date == date(2026, 1, 3)

        # The two columns whose absence caused the outage, plus the FX counter.
        assert sum(p["locf_filled"] for p in stored.points) == 1
        assert sum(p["spike_suppressed"] for p in stored.points) == 1
        assert sum(p["fx_unconverted_count"] for p in stored.points) == 1
        assert stored.points[-1]["value"] == 1020.0
    finally:
        repo.delete_account_key(PROBE_KEY)

    assert repo.get_series(PROBE_KEY).is_empty, "probe rows survived cleanup"
