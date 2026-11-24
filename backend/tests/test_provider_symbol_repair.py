"""Migration 020 doubled-suffix defect reproduction.

Observed: seven securities carry ``provider_symbol`` values such as
``ENB.TO.TO`` because migration 020 appended ``.TO/.NE/.V`` to tickers that
already had a suffix. Yahoo answers every refresh with HTTP 404
``Quote not found for symbol: ENB.TO.TO``.

The invariant under test: ``provider_symbol_for`` is idempotent for an
already-suffixed symbol, and the forward repair migration must use that same
expression rather than unconditional concatenation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from domain.listing_identity import provider_symbol_for

# Oracle: security ids and rows captured by the rollback-only DB probe, not
# derived from the implementation under test.
KNOWN_BAD_ROWS = [
    (9, "YTSL.NE", "NEO", "YTSL.NE.NE"),
    (123, "ENB.TO", "TSX", "ENB.TO.TO"),
    (634, "PZA.TO", "TSX", "PZA.TO.TO"),
    (2605, "T.TO", "TSX", "T.TO.TO"),
    (3006, "BCE.TO", "TSX", "BCE.TO.TO"),
    (3010, "CU.TO", "TSX", "CU.TO.TO"),
    (3115, "GSY.TO", "TSX", "GSY.TO.TO"),
]

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
MIGRATION_021 = MIGRATIONS / "021_repair_provider_symbol_suffixes.sql"
MIGRATION_022 = MIGRATIONS / "022_provider_symbol_no_repeated_suffix.sql"

LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# Same canonical expression migration 021 applies. The oracle is the symbol
# column itself, not the migration file's text: a migration can be correct and
# still never applied (the exact reason this defect recurred).
_CANONICAL_EXPR = """
    CASE
        WHEN position('.' in symbol) > 0 THEN symbol
        ELSE symbol || CASE exchange
            WHEN 'TSX' THEN '.TO'
            WHEN 'NEO' THEN '.NE'
            WHEN 'TSXV' THEN '.V'
            ELSE ''
        END
    END
"""

_STALE_ROWS_SQL = f"""
    SELECT security_id, symbol, exchange, provider_symbol
    FROM public.securities
    WHERE provider_symbol IS DISTINCT FROM ({_CANONICAL_EXPR})
    ORDER BY security_id
"""

# Durable red oracle: feed the seven captured bad rows through the *same*
# canonical expression on a synthetic relation. This proves the detector would
# flag the defect if it reappeared, without mutating the live catalog.
def _connect():
    """Connect to the local catalog, skipping cleanly when it is not running."""
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        return psycopg2.connect(LOCAL_DB)
    except Exception as exc:
        pytest.skip(f"local Supabase unreachable: {exc}")


_PROBE_VALUES = ", ".join(["(%s, %s, %s, %s)"] * len(KNOWN_BAD_ROWS))
_STALE_PROBE_SQL = f"""
    WITH probe(security_id, symbol, exchange, provider_symbol) AS (
        VALUES {_PROBE_VALUES}
    )
    SELECT security_id, symbol, provider_symbol,
           ({_CANONICAL_EXPR}) AS canonical
    FROM probe
    WHERE provider_symbol IS DISTINCT FROM ({_CANONICAL_EXPR})
    ORDER BY security_id
"""


@pytest.mark.parametrize(
    "security_id,symbol,exchange,bad_provider_symbol",
    KNOWN_BAD_ROWS,
    ids=[f"security-{row[0]}" for row in KNOWN_BAD_ROWS],
)
def test_doubled_suffix_rows_are_detected_as_stale(
    security_id, symbol, exchange, bad_provider_symbol
):
    """Each captured bad row must be recognizable without querying Yahoo."""
    expected = provider_symbol_for(symbol, exchange)

    # Hand-derived oracle: an already-suffixed ticker is the correct provider symbol.
    assert expected == symbol
    assert bad_provider_symbol != expected
    assert bad_provider_symbol == f"{symbol}{'.TO' if exchange == 'TSX' else '.NE'}"


@pytest.mark.parametrize(
    "security_id,symbol,exchange,bad_provider_symbol",
    KNOWN_BAD_ROWS,
    ids=[f"security-{row[0]}" for row in KNOWN_BAD_ROWS],
)
def test_repair_target_is_idempotent(
    security_id, symbol, exchange, bad_provider_symbol
):
    """Applying the repair twice must not change the result (structural law)."""
    once = provider_symbol_for(symbol, exchange)
    twice = provider_symbol_for(once, exchange)

    assert once == twice
    assert once == symbol


def test_unsuffixed_symbol_still_gets_its_exchange_suffix():
    """The repair must not remove the legitimate suffix for plain tickers."""
    assert provider_symbol_for("AAPL", "NMS") == "AAPL"
    assert provider_symbol_for("ENB", "TSX") == "ENB.TO"
    assert provider_symbol_for("YTSL", "NEO") == "YTSL.NE"
    assert provider_symbol_for("SU", "TSXV") == "SU.V"


def test_live_catalog_has_no_stale_provider_symbols():
    """The repair must be *applied*, not merely present as reviewed SQL text."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_STALE_ROWS_SQL)
            stale = cur.fetchall()
    finally:
        conn.close()

    assert stale == [], f"live catalog still serves invalid tickers: {stale}"


def test_stale_detector_flags_all_captured_bad_rows():
    """Durable red oracle: the invariant query catches every logged bad row.

    The seven rows are injected as a synthetic relation, so this proves the
    detector's capability without writing to the live catalog.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            params = [value for row in KNOWN_BAD_ROWS for value in row]
            cur.execute(_STALE_PROBE_SQL, params)
            flagged = cur.fetchall()
    finally:
        conn.close()

    assert [row[0] for row in flagged] == [row[0] for row in KNOWN_BAD_ROWS]
    assert all(canonical == symbol for _, symbol, _, canonical in flagged)


def test_live_catalog_rejects_a_doubled_provider_suffix():
    """The schema must reject a reintroduced bad row, not merely detect it."""
    psycopg2 = pytest.importorskip("psycopg2")
    conn = _connect()
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    "UPDATE public.securities SET provider_symbol = %s "
                    "WHERE security_id = %s",
                    ("T.TO.TO", 2605),
                )
    finally:
        conn.rollback()
        conn.close()


def test_forward_repair_migration_exists_and_uses_idempotent_expression():
    """The applied migration must encode the same rule as the Python helper."""
    assert MIGRATION_021.is_file(), f"missing forward repair: {MIGRATION_021}"
    sql = MIGRATION_021.read_text(encoding="utf-8")

    assert "position('.' in symbol) > 0 THEN symbol" in sql
    assert "WHEN 'TSX' THEN '.TO'" in sql
    assert "WHEN 'NEO' THEN '.NE'" in sql
    assert "WHEN 'TSXV' THEN '.V'" in sql
    # Unconditional concatenation is the defect being repaired; it must not
    # appear as the repair expression.
    assert "SET provider_symbol = symbol || CASE exchange" not in sql


def test_repair_is_bounded_and_does_not_rewrite_security_ids():
    """The repair changes only provider_symbol; identity foreign keys stay stable."""
    sql = MIGRATION_021.read_text(encoding="utf-8")
    assert "UPDATE public.securities" in sql
    assert "SET provider_symbol" in sql
    assert "security_id" not in sql.split("WHERE", 1)[0].split("SET", 1)[1]


def test_repeated_suffix_guard_is_additive_and_reversible():
    """The guard lives in the schema and carries an explicit rollback."""
    assert MIGRATION_022.is_file(), f"missing persistent invariant: {MIGRATION_022}"
    sql = MIGRATION_022.read_text(encoding="utf-8")

    assert "ADD CONSTRAINT ck_securities_provider_symbol_single_suffix" in sql
    assert "CHECK" in sql
    assert "!~*" in sql
    assert "DROP CONSTRAINT IF EXISTS ck_securities_provider_symbol_single_suffix" in sql
    assert "UPDATE" not in sql.split("ALTER TABLE")[1]
