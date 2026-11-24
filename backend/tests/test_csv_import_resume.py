"""CSV imports must resume: append only new rows, never rewrite existing history.

The event log is the source of truth for holdings. An overlapping export must
therefore resolve to the same idempotency keys for rows already imported and
append only genuinely new rows. The old ``import_{batch_id}_{index}`` key made
every re-upload look brand new, so replay would double every position.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.parsers.portfolio_parser import WealthsimpleParser, canonical_brokerage_code
from application.services import portfolio_service as service_module
from shared.portfolio_event_payload import csv_import_event_key

HEADER = (
    "effective_date,effective_time,settlement_date,account_id,account_type,"
    "activity_type,activity_sub_type,description,direction,symbol,"
    "underlying symbol,name,currency,quantity,unit_price,commission,net_cash_amount"
)

BASE_ROWS = [
    "2026-01-07,00:00:00,,HQ035ZHK5CAD,TFSA,Dividend,-,\"QDTE - ETF: Cash dividend distribution, received on 2026-01-07\",,QDTE,QDTE,ETF,USD,4.81,,,4.81",
    "2026-01-08,00:00:00,,HQ035ZHK5CAD,TFSA,Dividend,-,\"QDTE - ETF: Cash dividend distribution, received on 2026-01-08\",,QDTE,QDTE,ETF,USD,5.00,,,5.00",
]
EXTRA_ROW = "2026-01-09,00:00:00,,HQ035ZHK5CAD,TFSA,Dividend,-,\"QDTE - ETF: Cash dividend distribution, received on 2026-01-09\",,QDTE,QDTE,ETF,USD,6.00,,,6.00"


def make_csv(rows):
    return "\n".join([HEADER, *rows]) + "\n"


class FakeEventStore:
    """In-memory stand-in that enforces the real unique idempotency_key rule."""

    def __init__(self):
        self.events: list[dict] = []
        self.append_calls: list[list[dict]] = []

    def get_existing_idempotency_keys(self, keys):
        wanted = set(keys)
        return {
            event["idempotency_key"]
            for event in self.events
            if event.get("idempotency_key") in wanted
        }

    def append_events_batch(self, events):
        existing = self.get_existing_idempotency_keys(
            [event.get("idempotency_key") for event in events]
        )
        new = [event for event in events if event.get("idempotency_key") not in existing]
        self.events.extend(new)
        self.append_calls.append(list(events))
        return new


def build_service():
    repo = MagicMock()
    repo.get_brokerage_by_code.return_value = {"brokerage_id": 1}
    repo.get_or_create_account.side_effect = lambda **kwargs: {
        "account_id": 10,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    repo.create_import_job.return_value = 77

    service = service_module.PortfolioService(
        portfolio_repo=repo,
        financial_repo=MagicMock(),
        stock_provider=MagicMock(),
        defeat_beta_provider=MagicMock(),
    )
    service._ensure_companies_exist_with_tracking = AsyncMock(return_value=({}, []))
    service._extract_dividends = AsyncMock(return_value=0)
    return service, repo


async def run_background(store, csv_content, *, batch_id=None):
    service, repo = build_service()
    parse_result = WealthsimpleParser().parse_csv(csv_content)
    assert parse_result.success, parse_result.errors

    with patch("infrastructure.repositories.event_store.EventStore", return_value=store):
        result = await service._process_import_background(
            import_batch_id=batch_id or uuid.uuid4(),
            csv_hash="hash",
            csv_size=len(csv_content),
            account_filter=None,
            parse_result=parse_result,
            brokerage_id=1,
            user_id=1,
            brokerage_code="wealthsimple",
        )
    return result, repo


class TestStableRowIdentity:
    def test_decimal_spelling_and_settlement_date_do_not_change_identity(self):
        original = make_csv([
            "2026-01-07,00:00:00,,HQ035ZHK5CAD,TFSA,Trade,BUY,\"Purchase of 2 shares\",LONG,AAPL,AAPL,Apple Inc.,USD,2,150.00,1.00,-301.00",
        ])
        reformatted = make_csv([
            "2026-01-07,00:00:00,2026-01-09,HQ035ZHK5CAD,TFSA,Trade,BUY,\"Purchase of 2 shares\",LONG,AAPL,AAPL,Apple Inc.,USD,2.0000000000,150.0000,1.0000,-301.0000",
        ])

        first = WealthsimpleParser().parse_csv(original).transactions[0]
        second = WealthsimpleParser().parse_csv(reformatted).transactions[0]

        assert first.row_fingerprint == second.row_fingerprint
        assert csv_import_event_key("wealthsimple", first.row_fingerprint, 0) == (
            csv_import_event_key("wealthsimple", second.row_fingerprint, 0)
        )

    def test_changed_economic_content_changes_identity(self):
        original = make_csv([BASE_ROWS[0]])
        amended = make_csv([BASE_ROWS[0].replace("4.81", "5.81")])

        first = WealthsimpleParser().parse_csv(original).transactions[0]
        second = WealthsimpleParser().parse_csv(amended).transactions[0]

        assert first.row_fingerprint != second.row_fingerprint


class TestReimportDoesNotDuplicateHistory:
    @pytest.mark.asyncio
    async def test_second_import_of_same_csv_appends_nothing(self):
        store = FakeEventStore()
        csv_content = make_csv(BASE_ROWS)

        first, _ = await run_background(store, csv_content)
        second, repo = await run_background(store, csv_content)

        assert first["transactions_imported"] == 2
        assert first["transactions_duplicate"] == 0
        assert second["transactions_imported"] == 0
        assert second["transactions_duplicate"] == 2
        assert len(store.events) == 2
        assert all(event["idempotency_key"].startswith("csv_wealthsimple_") for event in store.events)
        assert all(
            update.kwargs.get("rows_inserted") == 0
            for update in repo.update_import_progress.call_args_list[-2:]
        )

    @pytest.mark.asyncio
    async def test_overlapping_export_only_appends_new_rows(self):
        store = FakeEventStore()

        await run_background(store, make_csv(BASE_ROWS))
        result, _ = await run_background(store, make_csv([*BASE_ROWS, EXTRA_ROW]))

        assert result["transactions_imported"] == 1
        assert result["transactions_duplicate"] == 2
        assert len(store.events) == 3

    @pytest.mark.asyncio
    async def test_identical_rows_in_one_file_get_distinct_stable_keys(self):
        store = FakeEventStore()
        csv_content = make_csv([BASE_ROWS[0], BASE_ROWS[0]])

        result, _ = await run_background(store, csv_content)

        keys = [event["idempotency_key"] for event in store.events]
        assert result["transactions_imported"] == 2
        assert len(set(keys)) == 2

        second, _ = await run_background(store, csv_content)
        assert second["transactions_imported"] == 0
        assert len(store.events) == 2

    @pytest.mark.asyncio
    async def test_resume_never_updates_or_deletes_existing_events(self):
        store = FakeEventStore()

        await run_background(store, make_csv(BASE_ROWS))
        with patch.object(store, "append_events_batch", wraps=store.append_events_batch) as append:
            await run_background(store, make_csv(BASE_ROWS))

        assert append.call_args_list == []
        assert len(store.events) == 2


class TestEventStoreFailure:
    @pytest.mark.asyncio
    async def test_event_lookup_failure_fails_the_job_instead_of_reporting_zero_imported(self):
        service, repo = build_service()
        parse_result = WealthsimpleParser().parse_csv(make_csv(BASE_ROWS))
        failing_store = MagicMock()
        failing_store.get_existing_idempotency_keys.side_effect = RuntimeError("database unavailable")

        with patch("infrastructure.repositories.event_store.EventStore", return_value=failing_store):
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
        assert "database unavailable" in result["error"]
        failed = [
            call for call in repo.update_import_progress.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failed) == 1
        assert "database unavailable" in failed[0].kwargs["error_message"]


class TestDuplicateCsvUploadIsAResume:
    @pytest.mark.asyncio
    async def test_same_hash_returns_a_queueable_success(self):
        service, _ = build_service()
        service.check_duplicate_import = AsyncMock(
            return_value={
                "started_at": "2026-01-01T00:00:00Z",
                "import_id": 9,
                "imported_rows": 2,
            }
        )
        service._process_import_background = AsyncMock()

        result = await service.queue_import(
            user_id=1,
            brokerage_code="wealthsimple",
            csv_content=make_csv(BASE_ROWS),
            account_filter=None,
            csv_filename="activities-export.csv",
        )
        await asyncio.sleep(0)

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["import_batch_id"]
        assert "already been imported" in result["warning"]


class TestDuplicateWarningUsesTheRealImport:
    @pytest.mark.asyncio
    async def test_no_op_reupload_does_not_become_the_previous_import(self):
        rows = [
            {
                "user_id": 1,
                "csv_hash": "hash",
                "import_id": 11,
                "status": "completed",
                "imported_rows": 0,
                "started_at": "2026-11-23T23:26:05Z",
            },
            {
                "user_id": 1,
                "csv_hash": "hash",
                "import_id": 10,
                "status": "completed",
                "imported_rows": 2463,
                "started_at": "2026-11-23T23:25:52Z",
            },
        ]

        class FakeQuery:
            def __init__(self):
                self.filters = {}
                self.limit_n = None

            def select(self, *_args):
                return self

            def eq(self, key, value):
                self.filters[key] = value
                return self

            def gt(self, key, value):
                self.filters[key] = ("gt", value)
                return self

            def order(self, *_args, **_kwargs):
                return self

            def limit(self, n):
                self.limit_n = n
                return self

            def execute(self):
                result = rows
                for key, value in self.filters.items():
                    if isinstance(value, tuple) and value[0] == "gt":
                        result = [row for row in result if (row.get(key) or 0) > value[1]]
                    else:
                        result = [row for row in result if row.get(key) == value]
                return SimpleNamespace(data=result[: self.limit_n])

        fake_supabase = MagicMock()
        fake_supabase.table.side_effect = lambda _name: FakeQuery()
        service, _ = build_service()

        with patch.object(service_module, "supabase", fake_supabase):
            previous = await service.check_duplicate_import(1, "hash")

        assert previous["import_id"] == 10
        assert previous["imported_rows"] == 2463


class TestLegacyBrokerageLabels:
    @pytest.mark.asyncio
    async def test_ws_trade_uses_the_wealthsimple_namespace(self):
        service, repo = build_service()
        service.check_duplicate_import = AsyncMock(return_value=None)
        service._process_import_background = AsyncMock()

        result = await service.queue_import(
            user_id=1,
            brokerage_code="WS_TRADE",
            csv_content=make_csv(BASE_ROWS),
            account_filter=None,
        )
        await asyncio.sleep(0)

        assert result["success"] is True, result
        assert result.get("error") is None
        repo.get_brokerage_by_code.assert_called_once_with("wealthsimple")
        assert canonical_brokerage_code("WS_TRADE") == "wealthsimple"
