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

MIGRATION_021 = (
    Path(__file__).resolve().parents[1]
    / "supabase" / "migrations"
    / "021_repair_provider_symbol_suffixes.sql"
)


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
