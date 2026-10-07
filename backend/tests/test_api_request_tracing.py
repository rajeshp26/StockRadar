"""Contract for the HTTP request lifecycle emitted by RequestTracingMiddleware.

The job path is covered by tests/test_snapshot_run_observability.py. These tests
cover the request path, and they assert against a real ``TestClient`` so the ASGI
plumbing (header echo, exception propagation, contextvar lifetime) is exercised
end to end rather than against a hand-built fake.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared import debug_trace
from shared.api_tracing import RequestTracingMiddleware
from shared.debug_trace import TRACE_HEADER


class _PayloadCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[dict] = []

    def emit(self, record):
        payload = debug_trace.payload_of(record)
        if payload is not None:
            self.records.append(payload)


@pytest.fixture
def traced():
    """Turn tracing on and collect every emitted payload.

    Logger levels are set after ``configure`` because configure derives the level
    from the flag; a capture handler on a WARNING-level logger collects nothing,
    which is the same invisible failure the job-path tests exist to catch.
    """
    capture = _PayloadCapture()
    saved_level = debug_trace.trace_logger.level
    debug_trace.configure(enabled=True, always_on_prefixes=())
    debug_trace.trace_logger.addHandler(capture)
    debug_trace.trace_logger.setLevel(logging.DEBUG)
    try:
        yield capture.records
    finally:
        debug_trace.trace_logger.removeHandler(capture)
        debug_trace.trace_logger.setLevel(saved_level)
        debug_trace.configure(enabled=False, always_on_prefixes=())


def _capture_under(enabled: bool, always_on_prefixes: tuple):
    """Configure debug_trace exactly as production does, then collect records."""
    capture = _PayloadCapture()
    saved_level = debug_trace.trace_logger.level
    debug_trace.configure(enabled=enabled, always_on_prefixes=always_on_prefixes)
    debug_trace.trace_logger.addHandler(capture)
    debug_trace.trace_logger.setLevel(logging.DEBUG)
    try:
        yield capture.records
    finally:
        debug_trace.trace_logger.removeHandler(capture)
        debug_trace.trace_logger.setLevel(saved_level)
        debug_trace.configure(enabled=False, always_on_prefixes=())


@pytest.fixture
def shipped():
    """The real production configuration: global flag off, scopes allowlisted.

    Anything asserted here is asserted for a real user. A middleware that
    emits only when DEBUG_TRACE_ENABLED is on would pass every other test in
    this file and still write nothing in production, because the shipped
    default for that flag is False.
    """
    yield from _capture_under(enabled=False, always_on_prefixes=("snapshot", "http"))


def _client(seen: list, handler=None) -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestTracingMiddleware)

    @app.get("/ok")
    async def ok():
        seen.append(debug_trace.current_trace_id())
        return {"ok": True}

    if handler is not None:

        @app.get("/boom")
        async def boom():
            raise handler

    return TestClient(app, raise_server_exceptions=False)


def _events(records: list, name: str) -> list[dict]:
    return [r for r in records if r["event"] == name]


def _bare_asgi_app(seen: list, raise_exc: Exception | None = None):
    """A minimal downstream ASGI app, so the middleware can be driven directly.

    ``TestClient`` runs each request in its own task, so a contextvar set inside
    the middleware dies with that task whether or not ``reset`` is called. That
    makes leak assertions through ``TestClient`` vacuous -- they pass against a
    broken middleware. Driving the app in the caller's own task is the only way
    to observe whether the token is actually reset.
    """

    async def app(scope, receive, send):
        seen.append(debug_trace.current_trace_id())
        if raise_exc is not None:
            raise raise_exc
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return RequestTracingMiddleware(app)


async def _drive(app, path: str = "/ok") -> list:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
        "headers": [],
    }
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


class TestRequestLifecycle:
    def test_start_and_end_are_both_recorded(self, traced):
        client = _client([])
        assert client.get("/ok").status_code == 200
        assert len(_events(traced, "request_start")) == 1
        assert len(_events(traced, "request_end")) == 1

    def test_start_names_the_method_and_path(self, traced):
        _client([]).get("/ok")
        start = _events(traced, "request_start")[0]
        assert start["method"] == "GET"
        assert start["path"] == "/ok"
        assert start["layer"] == "http"

    def test_end_records_status_and_duration(self, traced):
        _client([]).get("/ok")
        end = _events(traced, "request_end")[0]
        assert end["status_code"] == 200
        assert isinstance(end["duration_ms"], (int, float))
        assert end["duration_ms"] >= 0

    def test_a_failing_status_is_recorded_as_its_own_code(self, traced):
        _client([]).get("/missing")
        end = _events(traced, "request_end")[0]
        assert end["status_code"] == 404


class TestTraceIdCorrelation:
    def test_handler_sees_the_trace_id(self, traced):
        seen: list = []
        _client(seen).get("/ok")
        assert seen and seen[0] is not None

    def test_every_record_in_one_request_shares_the_trace_id(self, traced):
        seen: list = []
        client = _client(seen)
        client.get("/ok")
        ids = {r["trace_id"] for r in traced}
        assert len(ids) == 1
        assert ids == {seen[0]}

    def test_trace_id_is_echoed_on_the_response(self, traced):
        response = _client([]).get("/ok")
        assert response.headers[TRACE_HEADER]

    def test_a_supplied_trace_id_is_reused(self, traced):
        seen: list = []
        _client(seen).get("/ok", headers={TRACE_HEADER: "caller-supplied-123"})
        assert seen == ["caller-supplied-123"]

    def test_two_requests_do_not_share_a_trace_id(self, traced):
        seen: list = []
        client = _client(seen)
        client.get("/ok")
        client.get("/ok")
        assert seen[0] != seen[1]

    @pytest.mark.asyncio
    async def test_trace_id_is_set_inside_the_downstream_app(self, traced):
        seen: list = []
        await _drive(_bare_asgi_app(seen))
        assert seen and seen[0] is not None

    @pytest.mark.asyncio
    async def test_trace_id_is_cleared_after_the_request_in_the_same_task(self, traced):
        seen: list = []
        await _drive(_bare_asgi_app(seen))
        assert debug_trace.current_trace_id() is None


class TestFailures:
    def test_a_raising_endpoint_is_recorded_as_an_error(self, traced):
        _client([], handler=RuntimeError("boom")).get("/boom")
        errors = _events(traced, "request_error")
        assert len(errors) == 1
        assert errors[0]["error"] == "RuntimeError"
        assert not _events(traced, "request_end")

    @pytest.mark.asyncio
    async def test_a_failure_records_the_error_in_the_same_task(self, traced):
        seen: list = []
        with pytest.raises(RuntimeError):
            await _drive(_bare_asgi_app(seen, raise_exc=RuntimeError("boom")))
        errors = _events(traced, "request_error")
        assert len(errors) == 1
        assert errors[0]["error"] == "RuntimeError"
        assert debug_trace.current_trace_id() is None


class TestDisabled:
    def test_nothing_is_emitted_when_tracing_is_off(self):
        capture = _PayloadCapture()
        saved_level = debug_trace.trace_logger.level
        debug_trace.configure(enabled=False, always_on_prefixes=())
        debug_trace.trace_logger.addHandler(capture)
        debug_trace.trace_logger.setLevel(logging.DEBUG)
        try:
            response = _client([]).get("/ok")
        finally:
            debug_trace.trace_logger.removeHandler(capture)
            debug_trace.trace_logger.setLevel(saved_level)
        assert response.status_code == 200
        assert capture.records == []

    def test_the_endpoint_still_works_while_tracing_is_off(self):
        seen: list = []
        assert _client(seen).get("/ok").status_code == 200
        assert seen and seen[0] is not None


class TestShippedConfiguration:
    """The records must appear with the flag off, which is how it ships.

    ``DEBUG_TRACE_ENABLED`` defaults to False and only the allowlisted scopes
    emit. If the middleware did not bind an allowlisted scope prefix, every
    record would be dropped in production while all the tests above stayed
    green, because they force the global flag on.
    """

    def test_start_and_end_are_recorded_with_the_global_flag_off(self, shipped):
        assert debug_trace.is_enabled() is False
        _client([]).get("/ok")
        assert len(_events(shipped, "request_start")) == 1
        assert len(_events(shipped, "request_end")) == 1

    def test_a_supplied_trace_id_survives_under_the_shipped_config(self, shipped):
        seen: list = []
        _client(seen).get("/ok", headers={TRACE_HEADER: "caller-supplied-456"})
        assert seen == ["caller-supplied-456"]
        assert {r["trace_id"] for r in shipped} == {"caller-supplied-456"}

    def test_a_failure_is_recorded_with_the_global_flag_off(self, shipped):
        _client([], handler=RuntimeError("boom")).get("/boom")
        assert _events(shipped, "request_error")[0]["error"] == "RuntimeError"

    def test_the_shipped_default_allowlist_covers_the_http_scope(self):
        from config import settings

        assert "http" in settings.DEBUG_TRACE_ALWAYS_ON_SCOPES

