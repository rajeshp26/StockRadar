"""Failed imports must not leave orphan companies or provider noise.

Regression coverage for the residue found after the real-stack 414 failure:
14 minimal companies (UNKNOWN exchange, name == ticker) were created before the
event-key lookup failed, and option identifiers were sent to yfinance where they
raised validation errors. These tests exercise the production code paths.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services import portfolio_service as service_module
from application.services.portfolio_service import (
    PortfolioService,
    _is_provider_ticker,
    _provider_lookup_symbol,
)


def build_service():
    return PortfolioService(
        portfolio_repo=MagicMock(),
        financial_repo=MagicMock(),
        stock_provider=MagicMock(),
        defeat_beta_provider=MagicMock(),
    )


class FakeEventStore:
    def get_existing_idempotency_keys(self, keys):
        return set()

    def append_events_batch(self, events):
        return events


class TestProviderSymbolBoundary:
    def test_stored_hyphen_suffix_is_converted_for_provider_only(self):
        # The CSV parser stores ENB.TO as ENB-TO to keep fingerprints stable.
        # Yahoo understands only the dotted form.
        assert _provider_lookup_symbol("ENB-TO") == "ENB.TO"
        assert _provider_lookup_symbol("BCE-TO") == "BCE.TO"
        assert _provider_lookup_symbol("BEP-UN") == "BEP-UN"
        assert _provider_lookup_symbol("AAPL") == "AAPL"

    def test_override_does_not_produce_doubled_suffix(self):
        assert _provider_lookup_symbol("ENB-TO", "TOR") == "ENB.TO"
        assert _provider_lookup_symbol("ENB", "TOR") == "ENB.TO"
        assert _provider_lookup_symbol("ENB.TO", "TOR") == "ENB.TO"
        assert _provider_lookup_symbol("BBD.A", None) == "BBD.A"

    def test_option_identifiers_are_rejected_before_provider_call(self):
        assert not _is_provider_ticker("GIS   260918P00030000")
        assert not _is_provider_ticker("INFY  261016P00010000")
        assert _is_provider_ticker("GIS")
        assert _is_provider_ticker("AQN-TO")
        assert _is_provider_ticker("BBD.A")

    @pytest.mark.asyncio
    async def test_create_company_uses_dot_form_and_never_doubles_suffix(self):
        provider = MagicMock()
        provider.get_stock_details.return_value = MagicMock(
            long_name="Enbridge Inc.",
            exchange="TSX",
            sector="Energy",
            industry="Oil & Gas",
            currency="CAD",
            description="",
            website="",
            quote_type="EQUITY",
        )
        service = build_service()
        service.stock_provider = provider
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.return_value.data = [
            {"company_id": 99}
        ]

        with patch.object(service_module, "supabase", client):
            company_id = await service._create_company_from_symbol("ENB-TO")

        assert company_id == 99
        provider.get_stock_details.assert_called_once_with("ENB.TO")
        inserted = client.table.return_value.insert.call_args.args[0]
        assert inserted["ticker_symbol"] == "ENB-TO"  # stored form unchanged


class TestCompanyCreationSkipsContractIdentifiers:
    @pytest.mark.asyncio
    async def test_option_symbol_never_reaches_provider(self, mock_supabase_client):
        service = build_service()
        service._create_company_from_symbol = AsyncMock(return_value=123)
        symbols = {
            "GIS": None,
            "GIS   260918P00030000": None,
            "AQN-TO": "TOR",
        }

        with patch.object(service_module, "supabase", mock_supabase_client):
            _, created = await service._ensure_companies_exist_with_tracking(symbols)

        assert set(created) == {"GIS", "AQN-TO"}
        called_symbols = [
            call.args[0] for call in service._create_company_from_symbol.await_args_list
        ]
        assert "GIS   260918P00030000" not in called_symbols
        assert len(called_symbols) == 2


class TestFailedImportCleanup:
    @pytest.mark.asyncio
    async def test_lookup_failure_happens_before_any_company_or_account_write(self):
        service, repo = self._service_with_real_company_tracking()
        parse_result = self._parse_two_rows()

        with patch(
            "infrastructure.repositories.event_store.EventStore",
            side_effect=RuntimeError("414 URI too long"),
        ):
            result = await service._process_import_background(
                import_batch_id=uuid.uuid4(),
                csv_hash="hash",
                csv_size=100,
                account_filter=None,
                parse_result=parse_result,
                brokerage_id=1,
                brokerage_code="wealthsimple",
                user_id=1,
            )

        assert result["success"] is False
        assert "414" in result["error"]
        repo.get_or_create_account.assert_not_called()
        service._ensure_companies_exist_with_tracking.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_companies_created_before_a_later_failure_are_purged(self):
        service, _ = self._service_with_real_company_tracking()
        service._ensure_companies_exist_with_tracking = AsyncMock(
            return_value=({"AAPL": 501}, ["AAPL"])
        )
        parse_result = self._parse_two_rows()
        client = MagicMock()
        client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []
        delete = client.table.return_value.delete.return_value

        with (
            patch(
                "infrastructure.repositories.event_store.EventStore",
                return_value=FakeEventStore(),
            ),
            patch.object(service_module, "supabase", client),
            patch.object(
                service_module, "reconcile_transfers", side_effect=RuntimeError("append failed")
            ),
        ):
            result = await service._process_import_background(
                import_batch_id=uuid.uuid4(),
                csv_hash="hash",
                csv_size=100,
                account_filter=None,
                parse_result=parse_result,
                brokerage_id=1,
                brokerage_code="wealthsimple",
                user_id=1,
            )

        assert result["success"] is False
        delete.in_.assert_called_once_with("company_id", [501])

    @pytest.mark.asyncio
    async def test_referenced_company_is_never_purged(self):
        service = build_service()
        client = MagicMock()
        client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {"data": {"company_id": 501}}
        ]
        with patch.object(service_module, "supabase", client):
            service._purge_unreferenced_companies([501])

        delete = client.table.return_value.delete.return_value
        delete.in_.assert_not_called()

    @staticmethod
    def _service_with_real_company_tracking():
        service = build_service()
        service.portfolio_repo.get_brokerage_by_code.return_value = {"brokerage_id": 1}
        service.portfolio_repo.get_or_create_account.side_effect = lambda **kwargs: {
            "account_id": 10,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        service._ensure_companies_exist_with_tracking = AsyncMock(return_value=({}, []))
        service._extract_dividends = AsyncMock(return_value=0)
        return service, service.portfolio_repo

    @staticmethod
    def _parse_two_rows():
        from application.parsers.portfolio_parser import WealthsimpleParser

        header = (
            "effective_date,effective_time,settlement_date,account_id,account_type,"
            "activity_type,activity_sub_type,description,direction,symbol,"
            "underlying symbol,name,currency,quantity,unit_price,commission,net_cash_amount"
        )
        row = (
            "2026-01-07,00:00:00,,HQ035ZHK5CAD,TFSA,Dividend,-,\"Dividend\","
            ",QDTE,QDTE,ETF,USD,4.81,,,4.81"
        )
        result = WealthsimpleParser().parse_csv("\n".join([header, row, row]) + "\n")
        assert result.success, result.errors
        return result
