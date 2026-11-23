"""REG-006-DEPTS: a future forecast `report_date` is not a freshness signal.

Observed symptom: `dep_ts=2027-12-31` from `earnings_forecast.report_date`
caused the recompute guard to compare against a date two years in the future
and produced nonsensical `2026-09-05` valuation timestamps. `report_date` in a
forecast table is the *forecast period end*, not the time the row was written.
Freshness can never be in the future.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from infrastructure.repositories.valuation_repository import ValuationRepository


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def gt(self, *args, **kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _FakeSupabase:
    def __init__(self, per_table):
        self.per_table = per_table

    def table(self, name):
        return _FakeQuery(self.per_table.get(name, []))


def _fake_db(*, forecast_date: str):
    return _FakeSupabase(
        {
            "companies": [{"sector": "Tech", "industry": "Software"}],
            "company_summary": [],
            "earnings_forecast": [{"report_date": forecast_date}],
            "earnings": [],
            "income_statements": [],
            "financial_ratios": [],
            "splits": [],
            "industry_multiples": [],
            "valuation_method_defaults": [],
            "company_valuation_overrides": [],
        }
    )


@pytest.mark.asyncio
async def test_future_earnings_forecast_date_is_clamped_to_now():
    with patch(
        "infrastructure.repositories.valuation_repository.supabase",
        _fake_db(forecast_date="2027-12-31"),
    ):
        ts = await ValuationRepository().get_latest_dependency_ts(1, "rule1")

    assert ts is not None, "the forecast row is a real dependency; it must not vanish"
    # The repository normalises every dependency to naive UTC (see
    # _normalize_datetime), so "now" must be UTC here too.
    assert ts <= datetime.now(UTC).replace(tzinfo=None), (
        "a dependency timestamp must never be in the future"
    )


@pytest.mark.asyncio
async def test_past_forecast_date_is_preserved():
    with patch(
        "infrastructure.repositories.valuation_repository.supabase",
        _fake_db(forecast_date="2026-01-15"),
    ):
        ts = await ValuationRepository().get_latest_dependency_ts(1, "rule1")

    assert ts is not None
    assert ts.date().isoformat() == "2026-01-15"
