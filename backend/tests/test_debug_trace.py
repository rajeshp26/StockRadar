"""Tests for shared.debug_trace: cost when off, correlation, redaction, order sensitivity."""

import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from shared import debug_trace
from shared.logging_setup import JsonLineFormatter

BACKEND_DIR = Path(__file__).resolve().parents[1]


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture(autouse=True)
def _reset_trace_state():
    debug_trace.configure(enabled=False)
    debug_trace.clear_trace_id()
    yield
    debug_trace.configure(enabled=False)
    debug_trace.clear_trace_id()


@pytest.fixture
def captured():
    """Attach a capturing handler to both debug loggers, restoring state after."""
    caps: dict[str, _Capture] = {}
    saved: dict[str, tuple[int, bool]] = {}
    for name in (debug_trace.TRACE_LOGGER_NAME, debug_trace.INTEGRITY_LOGGER_NAME):
        logger = logging.getLogger(name)
        saved[name] = (logger.level, logger.propagate)
        handler = _Capture()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        caps[name] = handler
    try:
        yield caps
    finally:
        for name, handler in caps.items():
            logger = logging.getLogger(name)
            logger.removeHandler(handler)
            logger.setLevel(saved[name][0])
            logger.propagate = saved[name][1]


class TestDisabledIsFree:
    def test_trace_event_emits_nothing_when_disabled(self, captured):
        debug_trace.configure(enabled=False)
        debug_trace.trace_event("event_store", "page_fetch", offset=0)
        assert captured[debug_trace.TRACE_LOGGER_NAME].records == []

    def test_integrity_finding_emits_nothing_when_disabled(self, captured):
        debug_trace.configure(enabled=False)
        debug_trace.integrity_finding("PAGE_OVERLAP", page=1)
        assert captured[debug_trace.INTEGRITY_LOGGER_NAME].records == []

    def test_disabled_does_not_build_a_payload(self, captured, monkeypatch):
        """A disabled emitter must return before constructing its payload.

        Note the guarantee is about work done *inside* the function. Python
        evaluates ``ids=explode()`` at the call site before ``trace_event`` is
        entered, so no callee can prevent that; what it must avoid is the dict
        build, the redaction pass and the json serialisation.
        """
        debug_trace.configure(enabled=False)

        def explode(*args, **kwargs):
            raise AssertionError("payload must not be built when tracing is off")

        monkeypatch.setattr(debug_trace, "redact", explode)
        monkeypatch.setattr(debug_trace.json, "dumps", explode)

        debug_trace.trace_event("event_store", "page_fetch", offset=0, count=500)
        debug_trace.integrity_finding("PAGE_OVERLAP", page=1)

        assert captured[debug_trace.TRACE_LOGGER_NAME].records == []
        assert captured[debug_trace.INTEGRITY_LOGGER_NAME].records == []


class TestEmission:
    def test_trace_event_carries_layer_event_and_trace_id(self, captured):
        debug_trace.configure(enabled=True)
        with debug_trace.trace_scope("job"):
            debug_trace.trace_event("event_store", "page_fetch", offset=100, count=500)
        record = captured[debug_trace.TRACE_LOGGER_NAME].records[0]
        payload = debug_trace.payload_of(record)
        assert payload["layer"] == "event_store"
        assert payload["event"] == "page_fetch"
        assert payload["offset"] == 100
        assert payload["trace_id"].startswith("job-")

    def test_trace_event_without_scope_has_null_trace_id(self, captured):
        debug_trace.configure(enabled=True)
        debug_trace.trace_event("service", "layer", ok=True)
        record = captured[debug_trace.TRACE_LOGGER_NAME].records[0]
        assert debug_trace.payload_of(record)["trace_id"] is None

    def test_trace_event_logs_at_debug(self, captured):
        debug_trace.configure(enabled=True)
        debug_trace.trace_event("service", "layer", ok=True)
        record = captured[debug_trace.TRACE_LOGGER_NAME].records[0]
        assert record.levelno == logging.DEBUG

    def test_integrity_finding_logs_at_warning(self, captured):
        debug_trace.configure(enabled=True)
        debug_trace.integrity_finding("PAGE_OVERLAP", page=1, duplicate=17)
        record = captured[debug_trace.INTEGRITY_LOGGER_NAME].records[0]
        assert record.levelno == logging.WARNING
        assert debug_trace.payload_of(record)["event"] == "PAGE_OVERLAP"
        assert debug_trace.payload_of(record)["duplicate"] == 17

    def test_records_are_never_also_written_to_trace_logger(self, captured):
        debug_trace.configure(enabled=True)
        debug_trace.integrity_finding("PAGE_GAP", page=1)
        assert captured[debug_trace.TRACE_LOGGER_NAME].records == []


class TestTraceScope:
    def test_scope_mints_and_installs_an_id(self):
        with debug_trace.trace_scope("snapshot") as value:
            assert value.startswith("snapshot-")
            assert debug_trace.current_trace_id() == value

    def test_scope_restores_previous_id_on_exit(self):
        with debug_trace.trace_scope("outer"):
            outer = debug_trace.current_trace_id()
            with debug_trace.trace_scope("inner"):
                assert debug_trace.current_trace_id() != outer
            assert debug_trace.current_trace_id() == outer

    def test_scope_restores_previous_id_after_exception(self):
        with pytest.raises(RuntimeError), debug_trace.trace_scope("job") as value:
            raise RuntimeError("boom")
        assert debug_trace.current_trace_id() != value
        assert debug_trace.current_trace_id() is None

    def test_scope_ids_are_unique(self):
        with debug_trace.trace_scope("job") as first:
            pass
        with debug_trace.trace_scope("job") as second:
            pass
        assert first != second

    def test_set_and_clear_round_trip(self):
        debug_trace.set_trace_id("manual-1")
        assert debug_trace.current_trace_id() == "manual-1"
        debug_trace.clear_trace_id()
        assert debug_trace.current_trace_id() is None


class TestFingerprint:
    def test_fingerprint_is_stable_for_identical_input(self):
        assert debug_trace.fingerprint([1, 2, 3]) == debug_trace.fingerprint([1, 2, 3])

    def test_fingerprint_is_order_sensitive(self):
        """The property that makes it able to detect unstable pagination.

        A sorted set would hash these two identically, which is exactly the bug
        being detected: same rows, wrong order, across runs.
        """
        assert debug_trace.fingerprint([1, 2, 3]) != debug_trace.fingerprint([3, 2, 1])

    def test_fingerprint_distinguishes_length(self):
        assert debug_trace.fingerprint([1, 2, 3]) != debug_trace.fingerprint([1, 2, 3, 3])

    def test_fingerprint_of_empty_sequence_is_defined(self):
        assert debug_trace.fingerprint([]) == debug_trace.fingerprint([])

    def test_fingerprint_handles_uuid_and_str_mixture(self):
        assert debug_trace.fingerprint(["a", "a"]) == debug_trace.fingerprint(["a", "a"])

    def test_fingerprint_is_short_enough_for_a_log_line(self):
        assert len(debug_trace.fingerprint(range(100))) <= 16


class TestRedaction:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "PASSWORD",
            "user_password",
            "access_token",
            "refresh_token",
            "Authorization",
            "cookie",
            "api_key",
            "supabase_service_role_key",
        ],
    )
    def test_credential_keys_are_masked(self, key):
        assert debug_trace.redact({key: "leaked"})[key] == "***"

    @pytest.mark.parametrize("key", ["idempotency_key", "sort_key", "primary_key", "count"])
    def test_non_credential_keys_survive(self, key):
        assert debug_trace.redact({key: "value"})[key] == "value"

    def test_redaction_recurses_into_nested_dicts(self):
        out = debug_trace.redact({"outer": {"token": "leaked", "count": 3}})
        assert out["outer"]["token"] == "***"
        assert out["outer"]["count"] == 3

    def test_redaction_leaves_lists_untouched(self):
        """Only dict keys carry names, so a list has nothing to mask by."""
        assert debug_trace.redact({"ids": ["a", "b"]})["ids"] == ["a", "b"]


class TestSummarizeIds:
    def test_short_sequences_report_everything(self):
        out = debug_trace.summarize_ids(["a", "b"])
        assert out["count"] == 2
        assert out["first"] == ["a", "b"]
        assert out["last"] == []

    def test_long_sequences_report_boundaries_only(self):
        ids = [f"e{i}" for i in range(10)]
        out = debug_trace.summarize_ids(ids, head=2, tail=2)
        assert out["count"] == 10
        assert out["first"] == ["e0", "e1"]
        assert out["last"] == ["e8", "e9"]

    def test_summary_fingerprint_matches_full_sequence(self):
        ids = list("abcdefgh")
        assert debug_trace.summarize_ids(ids)["fingerprint"] == debug_trace.fingerprint(ids)


class TestJsonSink:
    def test_formatter_writes_one_parseable_line_with_trace_id(self, captured):
        handler = captured[debug_trace.TRACE_LOGGER_NAME]
        handler.setFormatter(JsonLineFormatter())
        debug_trace.configure(enabled=True)
        with debug_trace.trace_scope("snapshot"):
            debug_trace.trace_event("event_store", "page_fetch", offset=0, count=500)
        document = json.loads(handler.format(handler.records[0]))
        assert document["layer"] == "event_store"
        assert document["event"] == "page_fetch"
        assert document["offset"] == 0
        assert document["count"] == 500
        assert document["trace_id"].startswith("snapshot-")
        assert document["level"] == "DEBUG"

    def test_formatter_survives_values_json_cannot_encode(self, captured):
        from decimal import Decimal

        handler = captured[debug_trace.TRACE_LOGGER_NAME]
        handler.setFormatter(JsonLineFormatter())
        debug_trace.configure(enabled=True)
        debug_trace.trace_event("snapshot", "persist", amount=Decimal("1.50"))
        document = json.loads(handler.format(handler.records[0]))
        assert document["amount"] == "1.50"

    def test_formatter_redacts_before_serialising(self, captured):
        handler = captured[debug_trace.TRACE_LOGGER_NAME]
        handler.setFormatter(JsonLineFormatter())
        debug_trace.configure(enabled=True)
        debug_trace.trace_event("auth", "attempt", access_token="leaked")
        line = handler.format(handler.records[0])
        assert "leaked" not in line
        assert json.loads(line)["access_token"] == "***"


class TestDependencyRule:
    def test_module_imports_without_config_or_credentials(self):
        """debug_trace must import with no Supabase credentials present.

        config.settings is validated at import time against live credentials, so
        a repository importing debug_trace through config would make every unit
        test that touches a repository require a live project.
        """
        probe = (
            "import sys, shared.debug_trace as d; "
            "assert 'config' not in sys.modules, 'debug_trace pulled in config'; "
            "assert 'shared.logging_setup' not in sys.modules, 'pulled in logging_setup'; "
            "print(d.TRACE_HEADER)"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "X-Request-ID"

    def test_logging_setup_is_the_only_module_that_imports_config(self):
        spec = importlib.util.find_spec("shared.logging_setup")
        assert spec is not None and spec.origin is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "from config import settings" in source
