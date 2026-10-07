"""Daily price_history rows must survive every provider date representation.

The shared sanitizer replaced four drifting `_compress_daily_to_monthly_eom`
copies that had left 61 of 193 companies storing one price per month. Two
real defects were found only by executing it against the types the providers
actually emit: providers call ``.date()`` and hand back a plain
``datetime.date``, and a naive ``hasattr(raw_date, "date")`` branch drops
every such row; string dates left as strings then crash the sort. These tests
pin both, plus the daily-grain contract itself.
"""
from datetime import date, datetime

import pandas as pd
import pytest

from shared.price_rows import sanitize_daily_price_rows, safe_num


def test_plain_date_is_preserved_not_dropped():
    rows = [{"company_id": 1, "price_date": date(2024, 1, 2), "close_price": 45.67}]
    out = sanitize_daily_price_rows(rows)
    assert len(out) == 1
    assert out[0]["price_date"] == date(2024, 1, 2)


def test_datetime_and_timestamp_narrow_to_date():
    rows = [
        {"company_id": 1, "price_date": datetime(2024, 1, 2, 15, 30), "close_price": 1.0},
        {"company_id": 1, "price_date": pd.Timestamp("2024-01-03"), "close_price": 2.0},
    ]
    out = sanitize_daily_price_rows(rows)
    assert [r["price_date"] for r in out] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert all(type(r["price_date"]) is date for r in out)


def test_string_date_parses_so_mixed_types_can_sort():
    rows = [
        {"company_id": 1, "price_date": "2024-01-05", "close_price": 3.0},
        {"company_id": 1, "price_date": date(2024, 1, 4), "close_price": 2.0},
    ]
    out = sanitize_daily_price_rows(rows)
    assert [r["price_date"] for r in out] == [date(2024, 1, 4), date(2024, 1, 5)]


def test_every_trading_day_is_kept_not_compressed():
    rows = [
        {"company_id": 1, "price_date": date(2024, 1, d), "close_price": float(d)}
        for d in range(2, 24)
    ]
    out = sanitize_daily_price_rows(rows)
    assert len(out) == len(rows)


def test_row_without_close_price_is_dropped():
    rows = [
        {"company_id": 1, "price_date": date(2024, 1, 2), "close_price": None},
        {"company_id": 1, "price_date": date(2024, 1, 3), "close_price": 10.0},
    ]
    out = sanitize_daily_price_rows(rows)
    assert [r["price_date"] for r in out] == [date(2024, 1, 3)]


def test_row_without_company_id_is_dropped():
    rows = [
        {"company_id": None, "price_date": date(2024, 1, 2), "close_price": 10.0},
        {"company_id": 2, "price_date": date(2024, 1, 2), "close_price": 10.0},
    ]
    out = sanitize_daily_price_rows(rows)
    assert [r["company_id"] for r in out] == [2]


def test_row_without_date_is_dropped():
    rows = [{"company_id": 1, "price_date": None, "close_price": 10.0}]
    assert sanitize_daily_price_rows(rows) == []


def test_data_source_default_and_override_preserved():
    rows = [
        {"company_id": 1, "price_date": date(2024, 1, 2), "close_price": 1.0},
        {"company_id": 2, "price_date": date(2024, 1, 2), "close_price": 2.0, "data_source": "yfinance"},
    ]
    out = sanitize_daily_price_rows(rows, default_source="defeatbeta")
    assert {r["company_id"]: r["data_source"] for r in out} == {1: "defeatbeta", 2: "yfinance"}


def test_output_sorted_by_price_date():
    rows = [
        {"company_id": 1, "price_date": date(2024, 3, 1), "close_price": 3.0},
        {"company_id": 1, "price_date": date(2024, 1, 1), "close_price": 1.0},
        {"company_id": 1, "price_date": date(2024, 2, 1), "close_price": 2.0},
    ]
    out = sanitize_daily_price_rows(rows)
    assert [r["price_date"] for r in out] == [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]


def test_empty_and_none_input():
    assert sanitize_daily_price_rows([]) == []
    assert sanitize_daily_price_rows(None) == []


@pytest.mark.parametrize("raw,expected", [(None, None), (float("nan"), None), ("x", None), (5, 5.0), ("3.5", 3.5)])
def test_safe_num(raw, expected):
    assert safe_num(raw) == expected
