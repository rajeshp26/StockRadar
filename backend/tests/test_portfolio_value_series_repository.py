"""Contract tests for the real PortfolioValueSeriesRepository.

The service-level suite patches this class out with an in-memory fake that
accepts any write, so the repository's own failure modes were never executed.
That is how a schema mismatch could reject every write with PGRST204 while the
job reported success: nothing in the test suite ever reached the PostgREST call.

These tests drive the repository through a fake client that can reject a write
the way PostgREST does, and assert the two properties that make the failure
survivable: the API keeps working (empty read / partial write), and the failure
is reported exactly once, at ERROR, naming the migration to run.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest

from infrastructure.repositories import portfolio_value_series_repository as repo_mod
from infrastructure.repositories.portfolio_value_series_repository import (
    REQUIRED_COLUMNS,
    PortfolioValueSeriesRepository,
    reset_reported_errors,
)


class DbError(Exception):
    """Stand-in for a supabase-py APIError (Postgres/PostgREST rejection)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__({"message": message, "code": code})


class FakeQuery:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.selected: str | None = None
        self.upserted: list[dict] | None = None
        self.conflict: str | None = None
        self.deleted = False

    def select(self, columns: str, *args, **kwargs):
        self.selected = columns
        return self

    def eq(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def upsert(self, rows, on_conflict=None, **kwargs):
        self.upserted = rows
        self.conflict = on_conflict
        return self

    def delete(self):
        self.deleted = True
        return self

    def execute(self):
        return self._handler(self)


class FakeResult:
    def __init__(self, data) -> None:
        self.data = data


class FakeClient:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.queries: list[FakeQuery] = []

    def table(self, name: str) -> FakeQuery:
        q = FakeQuery(self._handler)
        self.queries.append(q)
        return q


@pytest.fixture(autouse=True)
def _clear_reported():
    reset_reported_errors()
    yield
    reset_reported_errors()


def _repo(handler) -> PortfolioValueSeriesRepository:
    return PortfolioValueSeriesRepository(client=FakeClient(handler))


def _points(n: int = 1) -> list[dict]:
    return [
        {
            "date": date(2026, 1, 1) + timedelta(days=i),
            "value": 1000.0 + i,
            "holdings_market_value": 900.0,
            "cost_basis": 800.0,
            "cash_balance": 100.0,
            "net_deposits": 700.0,
            "fx_unconverted_count": 0,
            "points_used": 2,
            "locf_filled": 1,
            "spike_suppressed": 0,
        }
        for i in range(n)
    ]


# ── The contract: one column list, used by both paths ────────────────────────


def test_select_projection_covers_every_required_column():
    repo = _repo(lambda q: FakeResult([]))
    repo.get_series("7,8,9")
    selected = repo.client.queries[0].selected
    assert selected is not None
    for column in REQUIRED_COLUMNS:
        assert column in selected


def test_per_point_metadata_columns_are_required():
    # Regression: these two were added to the code after migration 017 had been
    # applied, and the verifier's private copy of the list was never updated.
    assert "locf_filled" in REQUIRED_COLUMNS
    assert "spike_suppressed" in REQUIRED_COLUMNS


def test_upsert_payload_carries_every_required_column_except_db_defaulted_ones():
    repo = _repo(lambda q: FakeResult(q.upserted))
    repo.upsert_points("7,8,9", _points(1), fingerprint="fp", last_mark_date=date(2026, 1, 1))
    row = repo.client.queries[0].upserted[0]
    # computed_at is set by the database (DEFAULT NOW()); writing it would claim
    # the row was computed at the API's clock. Everything else must be supplied.
    assert set(row) == set(REQUIRED_COLUMNS) - {"computed_at"}


# ── Happy paths ──────────────────────────────────────────────────────────────


def test_upsert_returns_rows_written_and_batches_large_builds():
    def handler(q):
        return FakeResult(q.upserted)

    repo = _repo(handler)
    written = repo.upsert_points(
        "7,8,9", _points(repo_mod._BATCH + 5), fingerprint="fp",
        last_mark_date=date(2026, 1, 1),
    )
    assert written == repo_mod._BATCH + 5
    assert len(repo.client.queries) == 2  # chunked, not one giant request
    assert repo.client.queries[0].conflict == "account_key,series_date"


def test_upsert_with_no_points_writes_nothing():
    repo = _repo(lambda q: FakeResult([]))
    assert repo.upsert_points("7,8,9", [], fingerprint="fp", last_mark_date=date(2026, 1, 1)) == 0
    assert repo.client.queries == []


def test_read_maps_stored_metadata_through():
    rows = [
        {
            "series_date": "2026-01-01",
            "total_value": 1000.0,
            "holdings_market_value": 900.0,
            "cost_basis": 800.0,
            "cash_balance": 100.0,
            "net_deposits": 700.0,
            "fx_unconverted_count": 0,
            "points_used": 2,
            "locf_filled": 1,
            "spike_suppressed": 0,
            "fingerprint": "fp",
            "computed_at": "2026-01-01T00:00:00Z",
            "last_mark_date": "2026-01-01",
        }
    ]
    repo = _repo(lambda q: FakeResult(rows))
    stored = repo.get_series("7,8,9")
    assert stored.fingerprint == "fp"
    assert stored.last_mark_date == date(2026, 1, 1)
    assert stored.points[0]["locf_filled"] == 1


# ── Failure modes: loud once, never fatal ────────────────────────────────────


def test_schema_rejection_is_reported_at_error_once_and_never_raised(caplog):
    err = DbError("PGRST204", "Could not find the 'locf_filled' column of "
                              "'portfolio_value_series' in the schema cache")
    repo = _repo(lambda q: (_ for _ in ()).throw(err))

    with caplog.at_level(logging.ERROR):
        assert repo.upsert_points("7,8,9", _points(2), fingerprint="fp",
                                  last_mark_date=date(2026, 1, 1)) == 0
        # A second build must not raise, and must not repeat the ERROR.
        assert repo.upsert_points("7,8,9", _points(2), fingerprint="fp",
                                  last_mark_date=date(2026, 1, 1)) == 0

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "PGRST204" in message
    assert "017_create_portfolio_value_series.sql" in message


def test_read_schema_rejection_degrades_to_empty_and_is_reported_once(caplog):
    err = DbError("42703", "column portfolio_value_series.locf_filled does not exist")
    repo = _repo(lambda q: (_ for _ in ()).throw(err))

    with caplog.at_level(logging.ERROR):
        assert repo.get_series("7,8,9").is_empty
        assert repo.get_series("7,8,9").is_empty

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "42703" in errors[0].getMessage()


def test_error_code_is_parsed_from_stringified_exception():
    # Older supabase-py paths stringify the payload rather than exposing .code.
    class StringyError(Exception):
        def __str__(self):
            return "{'message': 'column x does not exist', 'code': '42703'}"

    assert repo_mod._error_code(StringyError()) == "42703"
    assert repo_mod._is_schema_error(StringyError())


def test_transient_failure_stays_a_warning_and_is_retried_each_build(caplog):
    err = TimeoutError("connection reset by peer")
    repo = _repo(lambda q: (_ for _ in ()).throw(err))

    with caplog.at_level(logging.WARNING):
        repo.upsert_points("7,8,9", _points(1), fingerprint="fp",
                           last_mark_date=date(2026, 1, 1))
        repo.upsert_points("7,8,9", _points(1), fingerprint="fp",
                           last_mark_date=date(2026, 1, 1))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(warnings) == 2  # transient faults are not "reported once"
    assert errors == []
