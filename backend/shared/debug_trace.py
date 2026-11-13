"""Structured, correlatable debug tracing for a long-running Python service.

Why this module exists
----------------------
A production defect (``backend/docs/EVENT_REPLAY_SEAM_DROP_ROOT_CAUSE_ANALYSIS.md``)
silently dropped and duplicated rows inside a paginated query. It could only be
diagnosed by hand-written probe scripts, for two reasons:

1. Log output went to ephemeral stdout with no on-disk artifact, so nothing
   survived to be read after the fact.
2. The correlation-id contextvar lived *inside* ``main.py`` as a module-local,
   so no repository or service could read it -- and the job that owned the bug
   runs in a separate worker process with no HTTP request at all.

This module owns the canonical trace-id contextvar and the structured emitters so
that every layer can be correlated, including layers that have no request.

Dependency rule
---------------
This module deliberately imports NOTHING from the rest of the backend.
In particular it does not import ``config``: ``config.settings`` is validated at
import time and requires live Supabase credentials, which would make this module
unimportable in a unit test. ``shared/logging_setup.py`` injects the enabled flag
via :func:`configure` at application startup instead.

Because repositories import this module, :func:`trace_event` and
:func:`integrity_finding` MUST stay cheap. When tracing is disabled they return
immediately, before building any payload or touching the filesystem.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

# The existing HTTP correlation header, kept as the canonical name so the
# request path and the background-job path agree on what a trace id is.
TRACE_HEADER = "X-Request-ID"

DEFAULT_NAMESPACE = "app"

_namespace = DEFAULT_NAMESPACE
_payload_attribute = "_debug_trace_payload"


def namespace() -> str:
    return _namespace


def payload_attribute() -> str:
    """Name of the ``LogRecord`` attribute holding the structured payload."""
    return _payload_attribute


def payload_of(record: logging.LogRecord) -> dict[str, Any] | None:
    """The structured payload attached to a record, or None if it has none."""
    return getattr(record, _payload_attribute, None)


def _names(ns: str) -> tuple[str, str, str]:
    return (f"{ns}.debug.trace", f"{ns}.debug.integrity", f"{ns}.debug")


def debug_logger_name() -> str:
    """Root of the debug logger tree that the rotating file sink attaches to."""
    return DEBUG_LOGGER_NAME


# Names stay as module attributes rather than functions so callers can compare
# them without a call, and so configure() can re-point them in lockstep with the
# loggers below -- a name that disagreed with its logger would silently misroute
# every handler and caplog assertion that keys off it.
TRACE_LOGGER_NAME, INTEGRITY_LOGGER_NAME, DEBUG_LOGGER_NAME = _names(DEFAULT_NAMESPACE)
trace_logger = logging.getLogger(TRACE_LOGGER_NAME)
integrity_logger = logging.getLogger(INTEGRITY_LOGGER_NAME)

# The one canonical trace-id contextvar. ContextVar (not threading.local)
# because a single request can hop between a threadpool worker (sync endpoint)
# and the event loop (async endpoint), and background jobs have neither.
trace_id_var: ContextVar[str | None] = ContextVar("debug_trace_id", default=None)

# The prefix of the innermost active trace_scope, or None outside any scope.
# Kept beside trace_id_var so is_enabled() can tell "tracing is off" apart from
# "tracing is off except inside a scope the operator marked always-on".
_scope_prefix_var: ContextVar[str | None] = ContextVar(
    "debug_trace_scope_prefix", default=None
)

_REDACTED = "***"

# Redaction is token-based rather than substring-based on purpose: a substring
# rule on "key" would also mask "idempotency_key", which is exactly the sort of
# field a debug record most needs to carry. Whole-token matching keeps
# diagnostic value while still catching real secrets.
_SENSITIVE_TOKENS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "apikey",
    }
)
_SENSITIVE_SUBSTRINGS = (
    "service_role",
    "private_key",
    "secret_key",
    "access_key",
    "signing_key",
    "jwt_secret",
    "api_key",
)

_TOKEN_SEPARATORS = "_-. /"

_enabled = False
_always_on_prefixes: frozenset[str] = frozenset()


def configure(
    *,
    enabled: bool,
    namespace: str | None = None,
    always_on_prefixes: Iterable[str] | None = None,
) -> None:
    """Enable or disable structured emission, and optionally re-point the namespace.

    Called once at startup. Both values are global rather than per-call because
    every call site wants the same answer; threading a flag through call stacks
    to repeat it is how ad-hoc logging ends up disabled in the path that needed
    it most.

    The namespace is re-pointed only when it actually differs, so a repeated
    call costs one string comparison instead of re-resolving both loggers.
    """
    global _enabled, _namespace, _payload_attribute
    global TRACE_LOGGER_NAME, INTEGRITY_LOGGER_NAME, DEBUG_LOGGER_NAME
    global trace_logger, integrity_logger, _always_on_prefixes
    _enabled = bool(enabled)
    if always_on_prefixes is not None:
        _always_on_prefixes = frozenset(always_on_prefixes)
    if namespace and namespace != _namespace:
        _namespace = namespace
        _payload_attribute = f"_{namespace}_debug_payload"
        TRACE_LOGGER_NAME, INTEGRITY_LOGGER_NAME, DEBUG_LOGGER_NAME = _names(namespace)
        trace_logger = logging.getLogger(TRACE_LOGGER_NAME)
        integrity_logger = logging.getLogger(INTEGRITY_LOGGER_NAME)


def snapshot() -> tuple[str, bool, frozenset[str]]:
    """Capture the namespace, enabled flag and always-on scopes for restore."""
    return (_namespace, _enabled, _always_on_prefixes)


def restore(state: tuple[str, bool] | tuple[str, bool, frozenset[str]]) -> None:
    """Restore a state captured by :func:`snapshot`.

    Re-configuring with the captured namespace is enough: the logger names, the
    loggers, and the payload attribute are all derived from it, so no other
    module state needs saving. A two-tuple from an older caller restores with an
    empty always-on set, which is what that caller would have had.
    """
    namespace, enabled, *rest = state
    always_on = rest[0] if rest else frozenset()
    configure(enabled=enabled, namespace=namespace, always_on_prefixes=always_on)


def _tracing_active() -> bool:
    """The single predicate every emitter and caller must agree on.

    Kept as one function because ``_emit`` and ``is_enabled`` previously carried
    their own copies of the check; two copies of a truthiness test drift, and a
    caller that sees True while the emitter drops the record is the worst
    possible failure for a debugging tool.
    """
    if _enabled:
        return True
    prefix = _scope_prefix_var.get()
    return prefix is not None and prefix in _always_on_prefixes


def is_enabled() -> bool:
    return _tracing_active()


# ---------------------------------------------------------------------------
# Trace id
# ---------------------------------------------------------------------------
def current_trace_id() -> str | None:
    return trace_id_var.get()


def set_trace_id(value: str) -> None:
    trace_id_var.set(value)


def clear_trace_id() -> None:
    trace_id_var.set(None)


def new_trace_id(prefix: str = "job") -> str:
    """Mint a trace id, install it as current, and return it.

    Prefer :func:`trace_scope` when the id is scoped to a block, because this
    function cannot hand back a contextvar token and so cannot restore a
    previous value on the caller's behalf.
    """
    value = f"{prefix}-{uuid.uuid4().hex[:12]}"
    trace_id_var.set(value)
    return value


@contextlib.contextmanager
def bind_trace_id(trace_id: str, prefix: str = "job") -> Iterator[str]:
    """Install an existing trace id and scope prefix for the duration of a block.

    :func:`trace_scope` cannot serve the request path, because it mints its own
    id and a request already has one: a caller-supplied ``X-Request-ID`` must
    survive, or the id the client holds stops matching the id in the log.
    """
    token = trace_id_var.set(trace_id)
    scope_token = _scope_prefix_var.set(prefix)
    try:
        yield trace_id
    finally:
        _scope_prefix_var.reset(scope_token)
        trace_id_var.reset(token)


@contextlib.contextmanager
def trace_scope(prefix: str = "job") -> Iterator[str]:
    """Mint a trace id for the duration of the block, then restore the previous.

    This is what a background job uses: there is no request, so nothing else
    would ever set an id, and without one the job's repository and service
    records are uncorrelatable with each other.
    """
    with bind_trace_id(f"{prefix}-{uuid.uuid4().hex[:12]}", prefix) as value:
        yield value


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
def _is_sensitive(key: str) -> bool:
    """True when a field name looks like it carries a credential.

    Compound secret names are matched as substrings ("supabase_service_role_key"
    contains "service_role"); simple ones are matched as whole tokens so that
    "idempotency_key" survives. Token matching is snake_case-oriented and does
    not split camelCase -- none of this codebase's settings or payload keys use
    that style.
    """
    lowered = key.lower()
    if any(fragment in lowered for fragment in _SENSITIVE_SUBSTRINGS):
        return True
    normalized = lowered
    for separator in _TOKEN_SEPARATORS:
        normalized = normalized.replace(separator, " ")
    return any(token in _SENSITIVE_TOKENS for token in normalized.split())


def redact(fields: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values, recursing into nested dicts."""
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if _is_sensitive(str(key)):
            out[key] = _REDACTED
        elif isinstance(value, dict):
            out[key] = redact(value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------
def fingerprint(ids: Sequence[Any]) -> str:
    """Order-sensitive fingerprint of an id sequence.

    Order-sensitive on purpose. A sorted set would hash two different orderings
    of the same rows identically, which is precisely the failure being detected:
    a paginated query that returns the right rows in a different, or unstable,
    order. Callers compare this across runs to prove a fetch is deterministic
    when row counts cannot.
    """
    digest = hashlib.sha256()
    for value in ids:
        digest.update(b"\x00")
        digest.update(str(value).encode("utf-8", "replace"))
    return digest.hexdigest()[:16]


def summarize_ids(ids: Sequence[Any], head: int = 3, tail: int = 3) -> dict[str, Any]:
    """Compact description of an id sequence: count, boundaries, fingerprint."""
    seq = [str(i) for i in ids]
    return {
        "count": len(seq),
        "first": seq[:head],
        "last": seq[-tail:] if len(seq) > head else [],
        "fingerprint": fingerprint(ids),
    }


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------
def _emit(
    logger: logging.Logger,
    level: int,
    layer: str,
    event: str,
    fields: dict[str, Any],
) -> None:
    if not _tracing_active():
        return
    payload = redact(fields)
    payload["layer"] = layer
    payload["event"] = event
    payload["trace_id"] = current_trace_id()
    logger.log(
        level,
        "%s %s %s",
        layer,
        event,
        json.dumps(payload, default=str, sort_keys=True),
        extra={_payload_attribute: payload},
    )


def trace_event(layer: str, event: str, **fields: Any) -> None:
    """Record a layer boundary: what went in, what came out.

    Emits at DEBUG to ``<namespace>.debug.trace``. No-op when tracing is off.
    """
    _emit(trace_logger, logging.DEBUG, layer, event, fields)


def integrity_finding(kind: str, **fields: Any) -> None:
    """Record a detected data-integrity defect.

    Emits at WARNING to ``<namespace>.debug.integrity`` so it survives a DEBUG
    log level. ``kind`` is a free-form SCREAMING_SNAKE token -- deliberately not
    an enum, so an instrumented caller is never blocked from reporting a defect
    class this module has not heard of.

    Known kinds: ``PAGE_OVERLAP``, ``PAGE_GAP``, ``DUPLICATE_ID``,
    ``ORDER_VIOLATION``, ``TRUNCATED_AT_LIMIT``, ``REPLAY_DRIFT``.
    """
    _emit(integrity_logger, logging.WARNING, "integrity", kind, fields)
