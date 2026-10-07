"""CDR classification must not depend on the denormalized holdings flag alone.

Root cause: portfolio_snapshot_job built its exchange_overrides map from
portfolio_holdings.exchange_override and passed NO override map at all to the
primary build_snapshot_row call. A NULL flag therefore disabled BOTH the CDR
ratio and the CAD-currency override, so a 1/10-scale position was priced as a
full US share -- a 10x overvaluation on every daily-written row.

These tests lock the fix: CDR-ness is the transaction-derived truth
(shared/cdr_utils.py is canonical) and portfolio_holdings.exchange_override is
only a cache of it. A cache must never overrule the truth it caches, so a
supplied classification -- including an EMPTY one, which is a real "not a CDR"
answer -- is authoritative, and the flag is read only when none was supplied.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _holding(cid=1, symbol="TSLA", qty=10, override="TOR"):
    return {
        "company_id": cid,
        "symbol": symbol,
        "quantity": qty,
        "total_cost": Decimal("294.10"),
        "average_cost": Decimal("29.41"),
        "price_currency": "USD",
        "exchange_override": override,
    }


def _build(holdings, prices, **overrides):
    from shared.snapshot_builder import build_snapshot_row

    kwargs = {
        "account_id": 1,
        "snapshot_date": date(2024, 6, 1),
        "holdings_state": holdings,
        "cash_balance": Decimal("0"),
        "net_deposits": Decimal("1000"),
        "prices_by_company": prices,
        "job_id": "test",
        "account_currency": "CAD",
        "price_history": {},
    }
    kwargs.update(overrides)
    with patch("config.settings") as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = False
        return build_snapshot_row(**kwargs)


_TOR_PRICE = {1: {"price": 350.0, "price_date": date(2024, 6, 1), "source": "yfinance_tor"}}


class TestDerivedCDRTruth:
    def test_ratio_applies_when_holdings_flag_is_missing(self):
        """The regression: NULL holdings flag, transaction says CDR."""
        row = _build(
            [_holding(override=None)],
            _TOR_PRICE,
            exchange_overrides=None,
            derived_cdr_companies={1},
        )
        h = row["holdings_json"][0]
        assert h["current_price"] == 35.0
        assert h["current_value"] == 350.0

    def test_ratio_applies_when_override_map_is_empty(self):
        """The daily job filtered falsy flags out, leaving an empty map."""
        row = _build(
            [_holding(override=None)],
            _TOR_PRICE,
            exchange_overrides={},
            derived_cdr_companies={1},
        )
        assert row["holdings_json"][0]["current_price"] == 35.0

    def test_flag_alone_still_works(self):
        """No regression: the pre-existing flag-driven path is unchanged."""
        row = _build([_holding()], _TOR_PRICE, exchange_overrides={1: "TOR"})
        assert row["holdings_json"][0]["current_price"] == 35.0

    def test_non_cdr_is_untouched(self):
        row = _build(
            [_holding(override=None)],
            _TOR_PRICE,
            exchange_overrides=None,
            derived_cdr_companies=set(),
        )
        assert row["holdings_json"][0]["current_price"] == 350.0


class TestValuationProvenance:
    def test_row_records_its_valuation_basis(self):
        """A stored row must be auditable without re-running the builder."""
        row = _build(
            [_holding(override=None)],
            _TOR_PRICE,
            exchange_overrides=None,
            derived_cdr_companies={1},
        )
        h = row["holdings_json"][0]
        assert h["exchange_override"] == "TOR"
        assert h["cdr_ratio"] == 10.0
        assert h["cdr_ratio_source"] == "transactions"
        assert h["price_unit_raw"] == 350.0
        assert h["price_date"] == "2024-06-01"
        assert h["price_tier"] == "CURRENT"
        assert h["price_source"] == "yfinance_tor"

    def test_ratio_source_distinguishes_the_two_signals(self):
        row = _build([_holding()], _TOR_PRICE, exchange_overrides={1: "TOR"})
        assert row["holdings_json"][0]["cdr_ratio_source"] == "holdings_flag"

    def test_null_flag_with_derived_cdr_is_reported(self):
        row = _build(
            [_holding(override=None)],
            _TOR_PRICE,
            exchange_overrides=None,
            derived_cdr_companies={1},
        )
        warnings = row["validation_warnings"]
        assert any("derived CDR" in w and "exchange_override=None" in w for w in warnings)


class TestWriteTimeInvariant:
    def test_priced_cdr_without_a_recorded_ratio_is_rejected(self):
        """A resolver that skips the ratio must not reach storage."""
        from shared import snapshot_builder

        def _skip_ratio(*a, **kw):
            audit = kw.get("audit")
            if audit is not None:
                audit["price_source"] = "yfinance_tor"
            return Decimal("350"), snapshot_builder.PriceTier.CURRENT, date(2024, 6, 1)

        with patch.object(snapshot_builder, "_resolve_holding_price", _skip_ratio):
            with pytest.raises(ValueError, match="no ratio applied"):
                _build(
                    [_holding(override=None)],
                    _TOR_PRICE,
                    exchange_overrides=None,
                    derived_cdr_companies={1},
                )

    def test_unpriced_cdr_is_exempt_and_recorded_incomplete(self):
        """No price yet is legitimate; it must not abort the whole snapshot."""
        row = _build(
            [_holding(override=None)],
            {},
            exchange_overrides=None,
            derived_cdr_companies={1},
        )
        h = row["holdings_json"][0]
        assert h["price_data_quality"] == "UNAVAILABLE"
        assert h["current_value"] == 0.0


class TestCacheCannotOverruleTransactions:
    def test_stale_tor_flag_is_overruled_by_transactions(self):
        """An empty classification is a real 'not a CDR' answer, not 'unknown'."""
        row = _build(
            [_holding()],
            _TOR_PRICE,
            exchange_overrides={1: "TOR"},
            derived_cdr_companies=set(),
        )
        h = row["holdings_json"][0]
        assert h["current_price"] == 350.0
        assert h["cdr_ratio"] is None
        assert h["exchange_override"] is None
        assert h["cdr_ratio_source"] is None

    def test_disagreement_is_reported(self):
        row = _build(
            [_holding()],
            _TOR_PRICE,
            exchange_overrides={1: "TOR"},
            derived_cdr_companies=set(),
        )
        assert any("disagrees" in w for w in row["validation_warnings"])

    def test_flag_is_the_fallback_when_no_classification_is_supplied(self):
        row = _build([_holding()], _TOR_PRICE, exchange_overrides={1: "TOR"})
        h = row["holdings_json"][0]
        assert h["current_price"] == 35.0
        assert h["cdr_ratio_source"] == "holdings_flag"


class TestCdrDerivationPaginates:
    """The daily job's CDR source must survive Supabase's 1000-row page cap.

    Dropping the pagination truncates the scan at 1000 rows, which silently loses
    CDR rows and reproduces the original defect for any busy account.
    """

    def test_cdr_past_the_first_page_is_still_found(self):
        from infrastructure.repositories.portfolio_repository import (
            PortfolioRepository,
        )

        plain = {"account_id": 1, "company_id": 7, "security_name": "Apple Inc.", "raw_data": None}
        cdr = {"account_id": 1, "company_id": 9, "security_name": "AAPL CDR", "raw_data": None}
        pages = [[plain] * 1000, [cdr]]

        class _Client:
            def __init__(self):
                self.ranges = []

            def table(self, _name):
                return self

            def select(self, _cols):
                return self

            def order(self, _col):
                return self

            def range(self, start, end):
                self.ranges.append((start, end))
                return self

            def execute(self):
                page = len(self.ranges) - 1
                return SimpleNamespace(data=pages[page] if page < len(pages) else [])

        client = _Client()
        repo = PortfolioRepository.__new__(PortfolioRepository)
        repo.client = client

        assert repo.get_cdr_company_ids_by_account() == {1: {9}}
        assert client.ranges == [(0, 999), (1000, 1999)]
