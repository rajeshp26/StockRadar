# backend/tracing.py
"""Server-side tracing for §4.1 evidence (event-loop lag, sync .execute() timing).

Provides:
  - a ring-buffer sampler for event-loop lag (how late callbacks run relative to
    when they were queued — a direct measure of loop blocking),
  - a wrapper that times every sync `.execute()` call on the Supabase client,
  - a request span counter (duration + active-request gauge),
  - a JSON summary exposed at GET /internal/trace.

All structures are bounded; overhead is O(1) per sample.
"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

logger = __import__("logging").getLogger("stockerpro.tracing")

_MAX_SAMPLES = 5000


class _RingBuffer:
    """Bounded buffer of float samples with percentile/stat queries."""

    def __init__(self, maxlen: int = _MAX_SAMPLES):
        self._buf: deque[float] = deque(maxlen=maxlen)

    def add(self, value: float) -> None:
        self._buf.append(value)

    def _sorted(self) -> list:
        return sorted(self._buf)

    def count(self) -> int:
        return len(self._buf)

    def percentile(self, p: float) -> float | None:
        if not self._buf:
            return None
        arr = self._sorted()
        k = max(0, min(len(arr) - 1, int(len(arr) * p / 100.0)))
        return arr[k]

    def max(self) -> float | None:
        return max(self._buf) if self._buf else None

    def total(self) -> float:
        return sum(self._buf)


@dataclass
class _Counter:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    on_loop_count: int = 0
    on_loop_total_ms: float = 0.0
    on_loop_max_ms: float = 0.0


class Tracer:
    def __init__(self) -> None:
        self.loop_lag_ms = _RingBuffer()
        self.execute_ms = _RingBuffer()
        self.request_ms = _RingBuffer()
        self.execute_by_table: defaultdict[str, _Counter] = defaultdict(_Counter)
        self.active_requests: int = 0
        self.started_at = time.monotonic()

    # ------------------------------------------------------------------ loops
    def record_loop_lag(self, lag_ms: float) -> None:
        self.loop_lag_ms.add(lag_ms)

    def record_execute(self, table: str, duration_ms: float, on_loop: bool) -> None:
        self.execute_ms.add(duration_ms)
        c = self.execute_by_table[table]
        c.count += 1
        c.total_ms += duration_ms
        c.max_ms = max(c.max_ms, duration_ms)
        if on_loop:
            c.on_loop_count += 1
            c.on_loop_total_ms += duration_ms
            c.on_loop_max_ms = max(c.on_loop_max_ms, duration_ms)

    def record_request(self, duration_ms: float) -> None:
        self.request_ms.add(duration_ms)

    # -------------------------------------------------------------- summary
    def summary(self) -> dict[str, Any]:
        def _pct(ring: _RingBuffer) -> dict[str, Any]:
            return {
                "samples": ring.count(),
                "p50": round(ring.percentile(50) or 0, 2),
                "p95": round(ring.percentile(95) or 0, 2),
                "p99": round(ring.percentile(99) or 0, 2),
                "max": round(ring.max() or 0, 2),
                "total": round(ring.total(), 1),
            }

        by_table = {
            table: {
                "count": c.count,
                "total_ms": round(c.total_ms, 1),
                "max_ms": round(c.max_ms, 2),
                "on_loop_count": c.on_loop_count,
                "on_loop_total_ms": round(c.on_loop_total_ms, 1),
                "on_loop_max_ms": round(c.on_loop_max_ms, 2),
            }
            for table, c in sorted(self.execute_by_table.items())
        }

        on_loop_count = sum(c.on_loop_count for c in self.execute_by_table.values())
        on_loop_total = sum(c.on_loop_total_ms for c in self.execute_by_table.values())
        on_loop_max = max((c.on_loop_max_ms for c in self.execute_by_table.values()), default=0.0)

        return {
            "uptime_s": round(time.monotonic() - self.started_at, 1),
            "event_loop_lag_ms": _pct(self.loop_lag_ms),
            "execute_ms": _pct(self.execute_ms),
            "execute_by_table": by_table,
            "on_loop_executes": {
                "count": on_loop_count,
                "total_ms": round(on_loop_total, 1),
                "max_ms": round(on_loop_max, 2),
            },
            "requests": _pct(self.request_ms),
            "active_requests": self.active_requests,
        }


tracer = Tracer()


def _is_on_event_loop() -> bool:
    """True when the current thread is running the asyncio event loop.

    Sync endpoints run in a threadpool (no running loop → False); async
    endpoints run on the loop itself (True). This is the §4.1 discriminator:
    a blocking call with on_loop=True stalls every other request.
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


# ---------------------------------------------------------------------------
# Event-loop lag sampler
# ---------------------------------------------------------------------------
def _mark_lag(loop: asyncio.AbstractEventLoop, scheduled: float) -> None:
    tracer.record_loop_lag((loop.time() - scheduled) * 1000.0)


async def start_loop_lag_sampler(interval: float = 0.05) -> None:
    """Continuously measure how late queued callbacks run (loop blocking).

    Each iteration queues a callback and sleeps. If the event loop is blocked by
    a long-running sync call (e.g. a sync `.execute()`), the callback runs late —
    that delay is the lag sample. Runs until cancelled.
    """
    loop = asyncio.get_running_loop()
    while True:
        scheduled = loop.time()
        handle = loop.call_soon(_mark_lag, loop, scheduled)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            handle.cancel()
            raise


# ---------------------------------------------------------------------------
# Sync .execute() timing wrapper (the §4.1 instrument)
# ---------------------------------------------------------------------------
class TimedBuilder:
    """Recursively wraps a postgrest query builder so the terminal sync
    `.execute()` is timed. Every chained call that returns another builder is
    re-wrapped, so reads like `table("x").select(...).eq(...).execute()` land on
    a timed execute regardless of chain length."""

    def __init__(self, inner: Any, table: str) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_table", table)

    def __getattr__(self, name: str) -> Any:
        inner = object.__getattribute__(self, "_inner")
        attr = getattr(inner, name)

        if name == "execute":
            def _timed_execute(*a: Any, **kw: Any) -> Any:
                t0 = time.perf_counter()
                try:
                    return attr(*a, **kw)
                finally:
                    on_loop = _is_on_event_loop()
                    tracer.record_execute(
                        object.__getattribute__(self, "_table"),
                        (time.perf_counter() - t0) * 1000.0,
                        on_loop,
                    )
            return _timed_execute

        if callable(attr):
            def _wrap(*a: Any, **kw: Any) -> Any:
                result = attr(*a, **kw)
                if result is not None and hasattr(result, "execute"):
                    return TimedBuilder(result, object.__getattribute__(self, "_table"))
                return result
            return _wrap

        return attr


class TimedClient:
    """Delegates to the raw supabase client, wrapping `table()` and `rpc()`
    builders so their sync `.execute()` calls are timed."""

    def __init__(self, inner: Any) -> None:
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name: str) -> Any:
        inner = object.__getattribute__(self, "_inner")
        attr = getattr(inner, name)

        if name == "table":
            def _table(*a: Any, **kw: Any) -> Any:
                table_name = a[0] if a else str(kw.get("name", "?"))
                return TimedBuilder(attr(*a, **kw), str(table_name))
            return _table

        if name == "rpc":
            def _rpc(*a: Any, **kw: Any) -> Any:
                fn = a[0] if a else str(kw.get("fn", "?"))
                return TimedBuilder(attr(*a, **kw), f"rpc:{fn}")
            return _rpc

        return attr
