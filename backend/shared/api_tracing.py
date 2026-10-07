"""Per-request structured tracing for the HTTP layer.

The job path already emitted a full lifecycle (run_start / run_end / withheld)
through ``shared.debug_trace``. The request path had no equivalent: it minted a
correlation id and fed an in-memory counter, so nothing about a call landed in
``debug.jsonl`` and a request could not be reconstructed after the fact.

This module owns the whole request lifecycle in one place. It deliberately
imports only ``shared.debug_trace``, for the same reason that module imports
nothing from the backend: ``main`` pulls in ``config`` and ``database``, which
validate live Supabase credentials at import time, so middleware living in
``main`` could not be unit-tested at all. Keeping the lifecycle here is what
makes it testable.
"""

from __future__ import annotations

import time
import uuid

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared.debug_trace import TRACE_HEADER, bind_trace_id, trace_event


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


class RequestTracingMiddleware:
    """Set the request trace id and record start/end/error as structured events.

    Implemented as raw ASGI middleware rather than ``BaseHTTPMiddleware`` on
    purpose. ``BaseHTTPMiddleware`` runs the downstream app in a separate task,
    which detaches the contextvar: a repository called under it would read
    ``trace_id_var`` as unset and stamp ``None`` onto its records, silently
    breaking the correlation this module exists to provide.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(TRACE_HEADER)
        trace_id = incoming or f"http-{uuid.uuid4().hex[:12]}"
        method = scope.get("method", "")
        path = scope.get("path", "")
        status: dict[str, int] = {}

        async def send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append(
                    (TRACE_HEADER.lower().encode("latin-1"), trace_id.encode("latin-1"))
                )
                message = {**message, "headers": headers}
            await send(message)

        with bind_trace_id(trace_id, "http"):
            started = time.perf_counter()
            trace_event("http", "request_start", method=method, path=path)
            try:
                await self.app(scope, receive, send_with_trace_id)
            except Exception as exc:
                trace_event(
                    "http",
                    "request_error",
                    method=method,
                    path=path,
                    error=type(exc).__name__,
                    duration_ms=_elapsed_ms(started),
                )
                raise
            else:
                trace_event(
                    "http",
                    "request_end",
                    method=method,
                    path=path,
                    status_code=status.get("code"),
                    duration_ms=_elapsed_ms(started),
                )


__all__ = ["RequestTracingMiddleware"]
