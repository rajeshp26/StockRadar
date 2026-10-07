"""Regression tests for _fetch_existing_price_rows pagination.

The single-row `.single()` conflict pre-pass this replaced issued one HTTP
request per incoming row, and its unpaged replacement would have been worse
than slow: PostgREST caps a response at db-max-rows (1000 by default), so a
multi-decade daily backfill (>1500 rows for one company) silently received only
the oldest page and every later day compared as "no existing row".
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from infrastructure.repositories.financial_repository import (  # noqa: E402
    SupabaseFinancialRepository,
)


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    """Range-aware PostgREST stand-in.

    The mock in test_portfolio_performance_500_repro.py returns `self` from
    `.range()` and ignores the window in `.execute()`, so it cannot prove that a
    paginated read actually walks past the first page.
    """

    def __init__(self, rows):
        self._rows = rows
        self._start = 0
        self._end = None
        self._eq = {}
        self._gte = {}
        self._lte = {}

    def select(self, fields):
        return self

    def eq(self, field, value):
        self._eq[field] = value
        return self

    def gte(self, field, value):
        self._gte[field] = value
        return self

    def lte(self, field, value):
        self._lte[field] = value
        return self

    def order(self, field, desc=False):
        return self

    def range(self, start, end):
        self._start = start
        self._end = end
        return self

    def execute(self):
        rows = list(self._rows)
        for field, value in self._eq.items():
            rows = [r for r in rows if r.get(field) == value]
        for field, value in self._gte.items():
            rows = [r for r in rows if str(r.get(field))[:10] >= str(value)[:10]]
        for field, value in self._lte.items():
            rows = [r for r in rows if str(r.get(field))[:10] <= str(value)[:10]]
        rows.sort(key=lambda r: str(r.get("price_date"))[:10])
        if self._end is None:
            return _Response(rows)
        return _Response(rows[self._start:self._end + 1])


class _Client:
    def __init__(self, rows_by_company):
        self._rows = rows_by_company
        self.execute_calls = 0

    def table(self, name):
        assert name == "price_history"
        client = self

        class _T(_Query):
            def execute(self):
                client.execute_calls += 1
                return super().execute()

        return _T(self._rows)


def _history(cid, count, start=date(2020, 1, 1)):
    return [
        {
            "company_id": cid,
            "price_date": (start + timedelta(days=i)).isoformat(),
            "close_price": float(i),
        }
        for i in range(count)
    ]


def _incoming(cid, count, start=date(2020, 1, 1)):
    return [
        {
            "company_id": cid,
            "price_date": (start + timedelta(days=i)).isoformat(),
            "close_price": float(i),
        }
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_single_page_when_under_cap():
    client = _Client(_history(1, 10))
    repo = SupabaseFinancialRepository(client=client)

    found = await repo._fetch_existing_price_rows(_incoming(1, 10))

    assert len(found) == 10
    assert client.execute_calls == 1


@pytest.mark.asyncio
async def test_pages_past_the_1000_row_cap():
    """The regression: one company holding more rows than PostgREST returns."""
    client = _Client(_history(1, 2500))
    repo = SupabaseFinancialRepository(client=client)

    found = await repo._fetch_existing_price_rows(_incoming(1, 2500))

    assert len(found) == 2500
    assert client.execute_calls == 3  # 1000 + 1000 + 500
    last_day = (date(2020, 1, 1) + timedelta(days=2499)).isoformat()
    assert (1, last_day) in found  # the tail past page 3 is genuinely indexed


@pytest.mark.asyncio
async def test_terminates_on_exact_multiple_of_page_size():
    """A page that is exactly full must still be followed by a final short page."""
    client = _Client(_history(1, 2000))
    repo = SupabaseFinancialRepository(client=client)

    found = await repo._fetch_existing_price_rows(_incoming(1, 2000))

    assert len(found) == 2000
    assert client.execute_calls == 3  # 1000 + 1000 + 0-length terminator


@pytest.mark.asyncio
async def test_each_company_queried_separately_with_its_own_span():
    client = _Client(_history(1, 5) + _history(2, 7))
    repo = SupabaseFinancialRepository(client=client)

    found = await repo._fetch_existing_price_rows(_incoming(1, 5) + _incoming(2, 7))

    assert len(found) == 12
    assert client.execute_calls == 2
    assert sum(1 for k in found if k[0] == 1) == 5
    assert sum(1 for k in found if k[0] == 2) == 7


@pytest.mark.asyncio
async def test_span_bounds_the_query_to_incoming_dates():
    stored = _history(1, 400)
    client = _Client(stored)
    repo = SupabaseFinancialRepository(client=client)

    window = [r for r in stored if 10 <= int(r["close_price"]) < 20]
    found = await repo._fetch_existing_price_rows(window)
    assert len(found) == 10


@pytest.mark.asyncio
async def test_key_normalizes_datetime_to_iso_date():
    """price_date arrives as datetime for some sources; the key must be the date."""
    client = _Client([
        {
            "company_id": 1,
            "price_date": datetime(2021, 6, 15, 15, 30).isoformat(),
            "close_price": 1.0,
        }
    ])
    repo = SupabaseFinancialRepository(client=client)

    found = await repo._fetch_existing_price_rows([{"company_id": 1, "price_date": "2021-06-15"}])

    assert (1, "2021-06-15") in found


@pytest.mark.asyncio
async def test_rows_missing_company_id_or_date_are_ignored():
    client = _Client(_history(1, 3))
    repo = SupabaseFinancialRepository(client=client)

    found = await repo._fetch_existing_price_rows([
        {"price_date": "2020-01-01"},
        {"company_id": 1},
        {"company_id": 1, "price_date": "2020-01-01"},
    ])

    assert len(found) == 1
