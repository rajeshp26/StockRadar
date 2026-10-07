"""Regression tests for CDR ratio integrity.

The CDR ratio is a STRUCTURAL property of the instrument, fixed by the
depositary at issuance (1 CDR = 1/10 of an underlying US share). It is not a
market measurement and must never be derived from price or cost data.

These tests exist because that rule was violated twice in production:

  1. ``backfill_cdr_ratios.py`` computed TSX_price / CDR_average_cost and wrote
     the result to ``companies.cdr_ratio``;
  2. ``application/jobs/price_ingestion_job.py::_update_cdr_ratios`` wrote the
     correct structural constant and then OVERWROTE it in the same function
     with the same market-derived formula, guarded only by a ``[1, 100]`` range
     check that every observed bad value passed (1.03 ... 34.12).

Because the stored ratio divides the displayed price, a polluted value
underpriced the holding: NFLX stored at 34.12 was shown at roughly 1/34th of
its real CDR price.

The first test below is the load-bearing one. If a market-derived writer is ever
reintroduced, it fails.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
from decimal import Decimal
from pathlib import Path

import pytest

from shared.cdr_utils import CDR_RATIO

BACKEND = Path(__file__).resolve().parent.parent
SCRIPTS = BACKEND / "scripts"


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, recorder, table):
        self._recorder = recorder
        self._table = table

    def select(self, *cols):
        self._recorder.selected.setdefault(self._table, []).append(
            ",".join(str(c) for c in cols)
        )
        return self

    def update(self, payload):
        self._recorder.updates.append((self._table, payload))
        return self

    def eq(self, *_a):
        return self

    def in_(self, *_a):
        return self

    def execute(self):
        return _FakeResponse(self._recorder.data.get(self._table, []))


class _FakeRepo:
    """Records every table touched, column selected and row written."""

    def __init__(self, holdings):
        self.data = {"portfolio_holdings": holdings}
        self.updates: list[tuple[str, dict]] = []
        self.selected: dict[str, list[str]] = {}

        class _Client:
            def __init__(self, repo):
                self._repo = repo

            def table(self, name):
                return _FakeQuery(self._repo, name)

        self.client = _Client(self)


def _run_update_cdr_ratios(holdings):
    from application.jobs import price_ingestion_job

    repo = _FakeRepo(holdings)
    original = price_ingestion_job.repo
    price_ingestion_job.repo = repo
    try:
        asyncio.run(price_ingestion_job._update_cdr_ratios())
    finally:
        price_ingestion_job.repo = original
    return repo


class TestCdrRatioIsStructural:
    def test_job_writes_only_the_structural_constant(self):
        """The core regression: no writer may emit a market-derived ratio.

        Every recorded write is checked, not just the first, so a writer that
        emits the constant and then overwrites it with a derived value (the
        exact original bug) cannot pass.
        """
        holdings = [
            {"company_id": 1, "exchange_override": "TOR"},
            {"company_id": 2, "exchange_override": "TOR"},
            {"company_id": 3, "exchange_override": "TOR"},
        ]
        repo = _run_update_cdr_ratios(holdings)

        company_writes = [p for t, p in repo.updates if t == "companies"]
        assert company_writes, "expected the job to write CDR ratios"

        bad = [
            p["cdr_ratio"] for p in company_writes
            if p["cdr_ratio"] != float(CDR_RATIO)
        ]
        assert not bad, (
            "cdr_ratio written as something other than the structural constant "
            f"{CDR_RATIO}: {bad}"
        )

        assert len(company_writes) == len(holdings), (
            f"expected exactly {len(holdings)} ratio writes, got "
            f"{len(company_writes)} - a repeated write indicates a double-write"
        )

    def test_job_never_reads_price_or_cost_to_derive_a_ratio(self):
        """The ratio must not depend on market data at all.

        Asserts structurally: the job never reads current_market_data and never
        selects average_cost or quantity. A market-derived implementation
        cannot pass this without also failing the constant assertion above.
        """
        holdings = [{"company_id": 1, "exchange_override": "TOR"}]
        repo = _run_update_cdr_ratios(holdings)

        assert "current_market_data" not in repo.selected, (
            "CDR ratio maintenance must not read market prices"
        )
        for table, cols in repo.selected.items():
            for col in cols:
                assert "average_cost" not in col, (
                    "CDR ratio maintenance must not read cost basis"
                )

    def test_job_writes_provenance_required_by_the_db_constraint(self):
        """A ratio may not exist without declaring the constant produced it."""
        repo = _run_update_cdr_ratios([{"company_id": 1, "exchange_override": "TOR"}])
        for table, payload in repo.updates:
            if table == "companies":
                assert payload.get("cdr_ratio_source") == "structural_constant"


class TestCdrCompanyClassification:
    def test_only_unanimously_tor_companies_are_written(self):
        """A company with any non-TOR holding is not company-global CDR.

        AAPL is CDR in account 7 and direct in accounts 10/11. Dividing it by a
        company-global ratio would misprice the direct accounts, so the job
        leaves such companies out entirely: company 3 is mixed and gets no write.
        """
        repo = _run_update_cdr_ratios([
            {"company_id": 1, "exchange_override": "TOR"},
            {"company_id": 2, "exchange_override": "TOR"},
            {"company_id": 3, "exchange_override": None},
        ])
        assert len([t for t, _ in repo.updates if t == "companies"]) == 2

    def test_no_cdr_holdings_writes_nothing(self):
        repo = _run_update_cdr_ratios([{"company_id": 1, "exchange_override": None}])
        assert [t for t, _ in repo.updates if t == "companies"] == []


class TestRetiredPollutersCannotRun:
    """Both scripts that derived ratios from price data must stay inert."""

    @pytest.mark.parametrize("script_name", [
        "backfill_cdr_ratios.py",
        "fix_cdr_holdings.py",
    ])
    def test_script_refuses_to_execute(self, script_name):
        spec = importlib.util.spec_from_file_location(
            f"retired_{script_name[:-3]}", SCRIPTS / script_name
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        entrypoints = [
            getattr(module, name) for name in dir(module)
            if not name.startswith("_") and callable(getattr(module, name))
        ]
        assert entrypoints, f"{script_name} exposes no callable entry point"

        for fn in entrypoints:
            if fn.__module__ != module.__name__:
                continue
            with pytest.raises(RuntimeError, match="RETIRED"):
                fn()


class TestDivisionTrace:
    """The cross-layer trace that makes silent CDR drift observable."""

    def test_structural_ratio_traces_at_debug(self, caplog):
        from shared.cdr_utils import trace_division

        with caplog.at_level(logging.DEBUG, logger="stockerpro.cdr"):
            trace_division("test", 1, 100.0, CDR_RATIO, 100.0 / CDR_RATIO)
        assert any(r.levelno == logging.DEBUG for r in caplog.records)

    def test_non_structural_ratio_traces_at_warning(self, caplog):
        """A non-structural ratio reaching pricing is a defect, so it warns."""
        from shared.cdr_utils import trace_division

        with caplog.at_level(logging.DEBUG, logger="stockerpro.cdr"):
            trace_division("test", 424, 3412.0, 34.12, 100.0)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_trace_identifies_the_layer_and_company(self, caplog):
        from shared.cdr_utils import trace_division

        with caplog.at_level(logging.DEBUG, logger="stockerpro.cdr"):
            trace_division("snapshot_builder", 424, 3412.0, CDR_RATIO, 341.2)
        message = caplog.records[-1].getMessage()
        assert "snapshot_builder" in message
        assert "424" in message


class TestPricingUsesTheConstant:
    def test_snapshot_builder_falls_back_to_the_structural_constant(self):
        from datetime import date

        from shared.snapshot_builder import PriceTier, _resolve_holding_price

        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="NFLX", avg_cost=None,
            latest_prices={1: {"price": 1000.0, "price_date": date.today()}},
            price_history={}, snapshot_date=date.today(),
            exchange_override="TOR", cdr_ratio=None,
        )
        assert tier == PriceTier.CURRENT
        assert price == Decimal("1000") / Decimal("10")
