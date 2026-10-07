"""Wiring for the durable structured debug log.

``backend/main.py`` is console-only by design: ``logging.basicConfig`` with no
``filename`` means every record goes to stdout and is gone when the process
exits. That is the right default for a container and the wrong default for
debugging, because you cannot read a log that no longer exists.

This module adds a rotating JSON-lines file sink *alongside* the existing
console output. It attaches only to the ``<LOG_NAMESPACE>.debug`` logger tree, never
touches the root logger, and never removes or replaces an existing handler, so
enabling it cannot change what any current code path prints.

It is also the only place that imports ``config``, because ``config.settings`` is
validated at import time against live Supabase credentials. Keeping that import
here is what allows ``shared.debug_trace`` to stay dependency-free.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from shared import debug_trace


def _handler_flag() -> str:
    """Marks a handler this module already installed, so setup stays idempotent.

    Derived from the active namespace rather than hardcoded, so two namespaces
    in one process cannot collide on the same marker attribute.
    """
    return f"_{debug_trace.namespace()}_debug_sink"

# Lives beside the stamping below so the format and the attribute it reads
# cannot drift apart.
CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s [%(correlation_id)s] %(name)s %(message)s"

# ---------------------------------------------------------------------------
# Correlation id on every record
# ---------------------------------------------------------------------------
# A record factory is used rather than a logging.Filter because a filter attached
# to the root logger never runs: logger filters are consulted only in
# ``Logger.handle()``, for the logger that created the record, so records from
# any child logger reach root's handlers without passing them. ``main.py`` had
# exactly that arrangement and ``record.correlation_id`` was never set. A record
# factory runs once per record at creation instead, which makes the attribute
# total and keeps ``CONSOLE_FORMAT`` from raising KeyError.
_CORRELATION_INSTALLED = False
_previous_record_factory: Any = None


def _correlation_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _previous_record_factory(*args, **kwargs)
    record.correlation_id = debug_trace.current_trace_id() or "-"
    return record


def install_correlation_stamping() -> None:
    """Stamp ``record.correlation_id`` on every record. Safe to call repeatedly."""
    global _CORRELATION_INSTALLED, _previous_record_factory
    if _CORRELATION_INSTALLED:
        return
    _previous_record_factory = logging.getLogRecordFactory()
    logging.setLogRecordFactory(_correlation_record_factory)
    _CORRELATION_INSTALLED = True


def uninstall_correlation_stamping() -> None:
    """Restore the factory that was active before installation.

    The record factory is process-global, so whatever installs it must be able to
    take it back out. Tests rely on this: a stamped factory left installed would
    otherwise silently change the shape of records in unrelated assertions.
    """
    global _CORRELATION_INSTALLED, _previous_record_factory
    if not _CORRELATION_INSTALLED:
        return
    logging.setLogRecordFactory(_previous_record_factory)
    _previous_record_factory = None
    _CORRELATION_INSTALLED = False


def _jsonable(value: Any) -> Any:
    """Coerce a payload value into something ``json.dumps`` accepts.

    Instrumented code passes Decimals (money), dates (snapshot dates) and
    sometimes sets. A formatter that raises here would turn a debug facility
    into an outage, so every failure degrades to ``str``.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (set, frozenset, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list,)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


class JsonLineFormatter(logging.Formatter):
    """One JSON object per line, carrying the structured payload.

    The trace id is read from the structured payload rather than from
    ``record.correlation_id``. The record factory guarantees that attribute on
    every record, but the payload is the authoritative trace record -- it also
    holds the emitter's layer, event name and redacted fields, so reading the id
    from the same object keeps each line internally consistent.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = debug_trace.payload_of(record) or {}
        document: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": payload.get("trace_id"),
        }
        for key, value in payload.items():
            if key == "trace_id":
                continue
            document[key] = _jsonable(value)
        if record.exc_info:
            document["exc"] = self.formatException(record.exc_info)
        return json.dumps(document, default=str)


def _resolve_log_dir(configured: str) -> Path:
    """Resolve DEBUG_LOG_DIR, anchoring a relative path to the backend package.

    Anchoring matters because schedulers and one-off scripts are started from
    different working directories; without it the same setting would scatter
    logs across the repo depending on who launched the process.
    """
    path = Path(configured)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def setup_debug_logging() -> None:
    """Enable tracing and, when configured, attach the rotating file sink.

    Safe to call more than once, and safe to call when the log directory cannot
    be created -- a debug facility must never be the reason the API fails to
    boot.
    """
    try:
        from config import settings
    except Exception:  # pragma: no cover - config import already fails loudly elsewhere
        return

    debug_trace.configure(
        enabled=settings.DEBUG_TRACE_ENABLED,
        namespace=settings.LOG_NAMESPACE,
        always_on_prefixes=settings.DEBUG_TRACE_ALWAYS_ON_SCOPES,
    )

    if not settings.DEBUG_LOG_ENABLED:
        return

    log_dir = _resolve_log_dir(settings.DEBUG_LOG_DIR)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Debug log directory %s unavailable (%s); continuing without file sink",
            log_dir,
            exc,
        )
        return

    debug_logger = logging.getLogger(debug_trace.debug_logger_name())
    flag = _handler_flag()
    for handler in debug_logger.handlers:
        if getattr(handler, flag, False):
            return

    try:
        handler = logging.handlers.RotatingFileHandler(
            log_dir / settings.DEBUG_LOG_FILENAME,
            maxBytes=settings.DEBUG_LOG_MAX_BYTES,
            backupCount=settings.DEBUG_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Debug log file unavailable (%s); continuing without file sink", exc
        )
        return

    setattr(handler, flag, True)
    handler.setFormatter(JsonLineFormatter())
    debug_logger.addHandler(handler)
    debug_logger.setLevel(
        getattr(logging, str(settings.DEBUG_LOG_LEVEL).upper(), logging.DEBUG)
    )
    # Keep these records out of the console handler. Without this every
    # structured record would be printed twice once tracing is switched on.
    debug_logger.propagate = False
