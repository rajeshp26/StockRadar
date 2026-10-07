"""Tests pinning down how the trace id reaches log output.

The trace id reaches records two different ways, and this file holds both:

* ``record.correlation_id`` -- stamped on *every* record by the
  ``LogRecordFactory`` installed by ``logging_setup.install_correlation_stamping``.
* the structured payload -- attached by ``debug_trace`` and read by
  ``JsonLineFormatter``.

A record factory is used rather than a ``logging.Filter`` because a filter
attached to the root logger never runs. Python consults a logger's filters only
in ``Logger.handle()``, for the logger that *created* the record, so records
propagating up from any child logger reach root's handlers without passing root's
filters. ``main.py`` previously had exactly that arrangement, which meant
``correlation_id`` was never set on any record. The two semantics tests below
keep that reasoning pinned so the factory is not "simplified" back into a root
filter.
"""

import json
import logging

import pytest

from shared import debug_trace
from shared.debug_trace import TRACE_LOGGER_NAME, trace_id_var
from shared.logging_setup import (
    CONSOLE_FORMAT,
    JsonLineFormatter,
    install_correlation_stamping,
    uninstall_correlation_stamping,
)


class _MarkFilter(logging.Filter):
    """Stamps a marker attribute, so a test can detect whether it ran."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.filter_ran = True
        return True


class _Recorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def isolated_root():
    """Detach root handlers/filters for the duration of one test.

    Without this the suite's own logging config leaks in and the assertions
    below would pass or fail for reasons outside the test.
    """
    root = logging.getLogger()
    saved_handlers, saved_filters, saved_level = (
        list(root.handlers),
        list(root.filters),
        root.level,
    )
    root.handlers, root.filters, root.level = [], [], logging.DEBUG
    try:
        yield root
    finally:
        root.handlers, root.filters, root.level = (
            saved_handlers,
            saved_filters,
            saved_level,
        )


@pytest.fixture
def stamped(isolated_root):
    """Install the correlation record factory, capture records, then remove it."""
    isolated_root.handlers = []
    uninstall_correlation_stamping()
    install_correlation_stamping()
    recorder = _Recorder()
    isolated_root.addHandler(recorder)
    try:
        yield recorder
    finally:
        uninstall_correlation_stamping()


class TestWhyARecordFactory:
    """These justify the mechanism; a root filter cannot pass them."""

    def test_root_filter_does_not_fire_for_child_records(self, isolated_root):
        isolated_root.addFilter(_MarkFilter())
        recorder = _Recorder()
        isolated_root.addHandler(recorder)

        child = logging.getLogger("app.test.child")
        child.propagate = True
        child.setLevel(logging.DEBUG)
        child.info("hello")

        assert len(recorder.records) == 1, "record never reached the root handler"
        assert not hasattr(recorder.records[0], "filter_ran"), (
            "expected a root-logger filter to be skipped for a child record"
        )

    def test_handler_filter_does_fire_for_child_records(self, isolated_root):
        recorder = _Recorder()
        recorder.addFilter(_MarkFilter())
        isolated_root.addHandler(recorder)

        child = logging.getLogger("app.test.child")
        child.propagate = True
        child.setLevel(logging.DEBUG)
        child.info("hello")

        assert len(recorder.records) == 1
        assert getattr(recorder.records[0], "filter_ran", False) is True


class TestCorrelationStamping:
    def test_child_record_is_stamped_with_the_active_trace_id(self, stamped):
        child = logging.getLogger("app.test.child")
        child.propagate = True
        child.setLevel(logging.DEBUG)

        with debug_trace.trace_scope("req"):
            child.info("hello")

        assert len(stamped.records) == 1
        assert stamped.records[0].correlation_id.startswith("req-")

    def test_record_outside_a_scope_gets_a_placeholder(self, stamped):
        child = logging.getLogger("app.test.child")
        child.propagate = True
        child.setLevel(logging.DEBUG)

        child.info("hello")

        assert stamped.records[0].correlation_id == "-"

    def test_installation_is_idempotent(self):
        uninstall_correlation_stamping()
        try:
            install_correlation_stamping()
            first = logging.getLogRecordFactory()
            install_correlation_stamping()

            assert logging.getLogRecordFactory() is first
        finally:
            uninstall_correlation_stamping()

    def test_uninstall_restores_the_previous_factory(self):
        original = logging.getLogRecordFactory()
        uninstall_correlation_stamping()
        try:
            install_correlation_stamping()
            uninstall_correlation_stamping()

            assert logging.getLogRecordFactory() is original
        finally:
            uninstall_correlation_stamping()

    def test_console_format_renders_for_any_logger(self, stamped):
        """CONSOLE_FORMAT references correlation_id, so it must always exist."""
        child = logging.getLogger("app.test.child")
        child.propagate = True
        child.setLevel(logging.DEBUG)
        child.info("hello")

        formatted = logging.Formatter(CONSOLE_FORMAT).format(stamped.records[0])

        assert "app.test.child" in formatted
        assert "hello" in formatted

    def test_stamping_does_not_disturb_an_existing_factory(self, isolated_root):
        """A factory already installed by the host must still be called."""
        original = logging.getLogRecordFactory()
        calls: list[tuple] = []
        created: list[logging.LogRecord] = []

        def stub(*args, **kwargs):
            calls.append(args)
            record = logging.LogRecord(
                name="app.test.outer",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="outer",
                args=(),
                exc_info=None,
            )
            created.append(record)
            return record

        uninstall_correlation_stamping()
        try:
            logging.setLogRecordFactory(stub)
            install_correlation_stamping()

            child = logging.getLogger("app.test.child")
            child.propagate = True
            child.setLevel(logging.DEBUG)
            child.info("x")
        finally:
            uninstall_correlation_stamping()
            logging.setLogRecordFactory(original)

        assert len(calls) == 1, "the pre-existing factory was bypassed"
        assert created[0].correlation_id == "-"


class TestJsonFormatterTraceId:
    def _emit(self, trace_id, extra_payload):
        record = logging.LogRecord(
            name=TRACE_LOGGER_NAME,
            level=logging.DEBUG,
            pathname=__file__,
            lineno=1,
            msg="event",
            args=(),
            exc_info=None,
        )
        if extra_payload is not None:
            setattr(record, debug_trace.payload_attribute(), extra_payload)
        return json.loads(JsonLineFormatter().format(record))

    def test_trace_id_comes_from_payload(self):
        document = self._emit("abc-123", {"trace_id": "abc-123", "layer": "replay"})

        assert document["trace_id"] == "abc-123"

    def test_survives_a_record_with_no_payload(self):
        record = logging.LogRecord(
            name=TRACE_LOGGER_NAME,
            level=logging.DEBUG,
            pathname=__file__,
            lineno=1,
            msg="event",
            args=(),
            exc_info=None,
        )
        assert debug_trace.payload_of(record) is None

        document = json.loads(JsonLineFormatter().format(record))

        assert document["trace_id"] is None
        assert document["logger"] == TRACE_LOGGER_NAME

    def test_payload_fields_are_merged_and_trace_id_not_duplicated(self):
        document = self._emit(
            "tid",
            {"trace_id": "tid", "fetched": 3, "matched": 2},
        )

        assert document["fetched"] == 3
        assert document["matched"] == 2
        assert list(document).count("trace_id") == 1

    def test_falls_back_to_null_trace_id_outside_a_scope(self):
        document = self._emit(None, {"trace_id": None, "layer": "job"})

        assert document["trace_id"] is None
        assert document["layer"] == "job"

    def test_contextvar_is_the_single_source_of_truth(self):
        """The contextvar and the payload agree, so a job's records join."""
        token = trace_id_var.set("job-42")
        try:
            document = self._emit("job-42", {"trace_id": "job-42"})
        finally:
            trace_id_var.reset(token)

        assert trace_id_var.get() is None
        assert document["trace_id"] == "job-42"


class TestNamespacePortability:
    """The modules must carry no product name, so they drop into any project."""

    def test_default_namespace_is_generic(self):
        assert debug_trace.DEFAULT_NAMESPACE == "app"

    def test_configure_repoints_names_loggers_and_payload_attribute(self):
        previous = debug_trace.snapshot()
        try:
            debug_trace.configure(enabled=True, namespace="acme")
            debug_trace.configure(enabled=True, namespace="acme")

            assert debug_trace.namespace() == "acme"
            assert debug_trace.TRACE_LOGGER_NAME == "acme.debug.trace"
            assert debug_trace.INTEGRITY_LOGGER_NAME == "acme.debug.integrity"
            assert debug_trace.debug_logger_name() == "acme.debug"
            assert debug_trace.trace_logger.name == "acme.debug.trace"
            assert debug_trace.integrity_logger.name == "acme.debug.integrity"
            assert debug_trace.payload_attribute() == "_acme_debug_payload"
        finally:
            debug_trace.restore(previous)

    def test_emitted_payload_lands_on_the_active_attribute(self):
        previous = debug_trace.snapshot()
        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                captured.append(record)

        handler = _Capture()
        try:
            debug_trace.configure(enabled=True, namespace="acme")
            logger = debug_trace.trace_logger
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False

            debug_trace.trace_event("event_store", "page_fetch", count=3)

            assert len(captured) == 1
            payload = debug_trace.payload_of(captured[0])
            assert payload is not None
            assert payload["event"] == "page_fetch"
            assert payload["count"] == 3
        finally:
            for name in (debug_trace.TRACE_LOGGER_NAME, "acme.debug.trace"):
                target = logging.getLogger(name)
                if handler in target.handlers:
                    target.removeHandler(handler)
            debug_trace.restore(previous)

    def test_no_product_name_remains_in_the_logging_modules(self):
        """Guards the portability claim itself, not just the default value."""
        import pathlib

        shared = pathlib.Path(debug_trace.__file__).parent
        for name in ("debug_trace.py", "logging_setup.py"):
            source = (shared / name).read_text(encoding="utf-8")
            assert "stockerpro" not in source.lower(), (
                f"{name} still contains a product name"
            )
