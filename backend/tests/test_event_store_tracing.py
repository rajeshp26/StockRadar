"""Tests that EventStore pagination instrumentation detects the defects it claims to.

The shared ``mock_supabase_client`` fixture returns one rigid MagicMock for every
query, so it cannot express "page 1 returns 1000 rows, page 2 returns 500". These
tests use a scripted client instead, which makes an overlap, a gap or a reordered
page reproducible rather than incidental.
"""

import logging

import pytest

from infrastructure.repositories.event_store import EventStore
from shared import debug_trace

# Mirrors PAGE_SIZE inside get_all_events. The loop only advances to a second
# page when a page comes back full, so a first page of exactly this size is what
# drives multi-page coverage.
PAGE_SIZE = 1000

CREATED_AT = "2026-01-01T00:00:00.000000+00:00"


def _rows(start: int, count: int, created_at: str = CREATED_AT) -> list[dict]:
    return [
        {"id": f"evt-{i:06d}", "created_at": created_at, "event_type": "tx_imported"}
        for i in range(start, start + count)
    ]


class _FakeResult:
    def __init__(self, data: list[dict] | None = None, count: int | None = None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, client: "_ScriptedClient") -> None:
        self._client = client
        self._is_count = False

    def select(self, *args, **kwargs):
        if kwargs.get("count") == "exact":
            self._is_count = True
        return self

    def order(self, column, desc=False):
        return self

    def range(self, start, end):
        return self

    def eq(self, column, value):
        return self

    def gte(self, column, value):
        return self

    def execute(self):
        if self._is_count:
            self._client.count_queries += 1
            if self._client.count_error:
                raise RuntimeError("count probe unavailable")
            return _FakeResult(data=[], count=self._client.total)
        self._client.data_queries += 1
        index = self._client.data_queries - 1
        pages = self._client.pages
        return _FakeResult(data=list(pages[index]) if index < len(pages) else [])


class _ScriptedClient:
    """Serves scripted pages in call order so a fetch is deterministic."""

    def __init__(self, pages, total=None, count_error=False):
        self.pages = list(pages)
        self.total = total
        self.count_error = count_error
        self.data_queries = 0
        self.count_queries = 0

    def table(self, name):
        return _FakeQuery(self)


@pytest.fixture(autouse=True)
def _reset_trace_state():
    debug_trace.configure(enabled=False)
    debug_trace.clear_trace_id()
    yield
    debug_trace.configure(enabled=False)
    debug_trace.clear_trace_id()


@pytest.fixture
def collected():
    saved: dict[str, tuple[int, bool]] = {}
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    names = (debug_trace.TRACE_LOGGER_NAME, debug_trace.INTEGRITY_LOGGER_NAME)
    for name in names:
        logger = logging.getLogger(name)
        saved[name] = (logger.level, logger.propagate)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.addHandler(_Collect())
    try:
        yield records
    finally:
        for name in names:
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                if isinstance(handler, _Collect):
                    logger.removeHandler(handler)
            logger.setLevel(saved[name][0])
            logger.propagate = saved[name][1]


def kinds(records, logger_name: str) -> list[str]:
    return [debug_trace.payload_of(r)["event"] for r in records if r.name == logger_name]


def payload_for(records, logger_name: str, kind: str) -> dict:
    for record in records:
        if record.name != logger_name:
            continue
        payload = debug_trace.payload_of(record)
        if payload and payload["event"] == kind:
            return payload
    raise AssertionError(f"{kind} was not reported")


class TestZeroCostWhenDisabled:
    def test_no_records_are_emitted(self, collected):
        store = EventStore(client=_ScriptedClient([_rows(0, 3)], total=3))
        store.get_all_events()
        assert collected == []

    def test_no_extra_count_probe_is_issued(self):
        client = _ScriptedClient([_rows(0, 3)], total=3)
        EventStore(client=client).get_all_events()
        assert client.count_queries == 0
        assert client.data_queries == 1

    def test_returned_rows_are_unchanged(self):
        rows = _rows(0, 3)
        result = EventStore(client=_ScriptedClient([rows], total=3)).get_all_events()
        assert [r["id"] for r in result] == [r["id"] for r in rows]


class TestCleanPagination:
    @pytest.fixture(autouse=True)
    def _enable(self):
        debug_trace.configure(enabled=True)

    def test_two_full_pages_report_no_integrity_finding(self, collected):
        client = _ScriptedClient([_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, 500)], total=1500)
        result = EventStore(client=client).get_all_events()
        assert len(result) == 1500
        assert kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME) == []

    def test_summary_reports_expected_versus_actual(self, collected):
        client = _ScriptedClient([_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, 500)], total=1500)
        EventStore(client=client).get_all_events()
        payload = payload_for(
            collected, debug_trace.TRACE_LOGGER_NAME, "get_all_events"
        )
        assert payload["returned"] == 1500
        assert payload["expected_total"] == 1500
        assert payload["distinct_ids"] == 1500
        assert payload["pages"] == 2
        assert payload["truncated"] is False
        assert payload["fingerprint"]

    def test_ids_tied_on_created_at_are_ordered_by_id(self, collected):
        """The documented root cause: identical created_at must still sort stably."""
        client = _ScriptedClient([_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, 500)], total=1500)
        result = EventStore(client=client).get_all_events()
        assert [r["id"] for r in result] == sorted(r["id"] for r in result)
        assert kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME) == []


class TestGapDetection:
    @pytest.fixture(autouse=True)
    def _enable(self):
        debug_trace.configure(enabled=True)

    def test_shortfall_against_expected_total_is_reported(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, 500)], total=2500
        )
        result = EventStore(client=client).get_all_events()
        assert len(result) == 1500
        payload = payload_for(collected, debug_trace.INTEGRITY_LOGGER_NAME, "PAGE_GAP")
        assert payload["returned"] == 1500
        assert payload["expected_total"] == 2500
        assert payload["missing"] == 1000

    def test_count_probe_failure_does_not_break_the_read(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, 500)], total=2500, count_error=True
        )
        result = EventStore(client=client).get_all_events()
        assert len(result) == 1500
        assert "PAGE_GAP" not in kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME)

    def test_unknown_total_suppresses_gap_checks(self, collected):
        client = _ScriptedClient([_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, 500)], total=None)
        EventStore(client=client).get_all_events()
        assert kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME) == []


class TestOverlapDetection:
    @pytest.fixture(autouse=True)
    def _enable(self):
        debug_trace.configure(enabled=True)

    def test_page_restarting_inside_the_previous_page_is_reported(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE - 1, 500)], total=1500
        )
        EventStore(client=client).get_all_events()
        reported = kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME)
        assert "PAGE_OVERLAP" in reported
        assert "DUPLICATE_ID" in reported

    def test_overlap_names_the_boundary_rows(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE - 1, 500)], total=1500
        )
        EventStore(client=client).get_all_events()
        payload = payload_for(collected, debug_trace.INTEGRITY_LOGGER_NAME, "PAGE_OVERLAP")
        assert payload["page"] == 1
        assert payload["previous_last"]["id"] == "evt-000999"
        assert payload["this_page_first"]["id"] == "evt-000999"

    def test_carried_duplicate_is_attributed_to_the_previous_page(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE - 1, 500)], total=1500
        )
        EventStore(client=client).get_all_events()
        payload = payload_for(collected, debug_trace.INTEGRITY_LOGGER_NAME, "DUPLICATE_ID")
        assert payload["carried_from_previous_page"] == 1
        assert payload["within_page"] == 0


class TestOrderAndDuplicateDetection:
    @pytest.fixture(autouse=True)
    def _enable(self):
        debug_trace.configure(enabled=True)

    def test_reversed_page_is_reported(self, collected):
        client = _ScriptedClient([list(reversed(_rows(0, PAGE_SIZE))), []], total=PAGE_SIZE)
        EventStore(client=client).get_all_events()
        payload = payload_for(
            collected, debug_trace.INTEGRITY_LOGGER_NAME, "ORDER_VIOLATION"
        )
        assert payload["page"] == 0
        assert payload["occurrences"] == PAGE_SIZE - 1

    def test_duplicate_id_inside_one_page_is_reported(self, collected):
        rows = _rows(0, PAGE_SIZE)
        rows[500]["id"] = rows[400]["id"]
        client = _ScriptedClient([rows, []], total=PAGE_SIZE)
        EventStore(client=client).get_all_events()
        payload = payload_for(collected, debug_trace.INTEGRITY_LOGGER_NAME, "DUPLICATE_ID")
        assert payload["within_page"] == 1
        assert payload["carried_from_previous_page"] == 0

    def test_distinct_id_count_exposes_a_repeat(self, collected):
        rows = _rows(0, PAGE_SIZE)
        rows[500]["id"] = rows[400]["id"]
        client = _ScriptedClient([rows, []], total=PAGE_SIZE)
        EventStore(client=client).get_all_events()
        payload = payload_for(
            collected, debug_trace.TRACE_LOGGER_NAME, "get_all_events"
        )
        assert payload["returned"] == PAGE_SIZE
        assert payload["distinct_ids"] == PAGE_SIZE - 1


class TestTruncation:
    @pytest.fixture(autouse=True)
    def _enable(self):
        debug_trace.configure(enabled=True)

    def test_limit_larger_than_result_set_does_not_truncate(self, collected):
        client = _ScriptedClient([_rows(0, 10)], total=10)
        result = EventStore(client=client).get_all_events(limit=1000)
        assert len(result) == 10
        assert kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME) == []

    def test_truncation_is_reported_with_expected_total(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, PAGE_SIZE)], total=2000
        )
        result = EventStore(client=client).get_all_events(limit=1200)
        assert len(result) == 1200
        payload = payload_for(
            collected, debug_trace.INTEGRITY_LOGGER_NAME, "TRUNCATED_AT_LIMIT"
        )
        assert payload["returned"] == 1200
        assert payload["limit"] == 1200
        assert payload["expected_total"] == 2000

    def test_truncation_is_not_also_reported_as_a_gap(self, collected):
        """A shortfall the limit already explains must not double-report."""
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, PAGE_SIZE)], total=2000
        )
        EventStore(client=client).get_all_events(limit=1200)
        reported = kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME)
        assert reported == ["TRUNCATED_AT_LIMIT"]

    def test_table_larger_than_limit_stops_exactly_at_limit(self, collected):
        client = _ScriptedClient(
            [_rows(0, PAGE_SIZE), _rows(PAGE_SIZE, PAGE_SIZE)], total=5000
        )
        result = EventStore(client=client).get_all_events(limit=PAGE_SIZE)
        assert len(result) == PAGE_SIZE
        assert "PAGE_GAP" not in kinds(collected, debug_trace.INTEGRITY_LOGGER_NAME)
