"""Pattern 12 — Exception Handling & Recovery (Gulli Ch 12).

Detect -> handle -> recover at three scopes (step, node, system) with the
four recovery families: failover, graceful degradation, state rollback,
human escalation. Honest note: the book names retries but develops no
backoff or circuit-breaker mechanics; the CircuitBreaker here is a
framework addition, included because production loops need one."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    """Opens after N consecutive failures; half-opens after a cooldown.

    Semantics (tightened in the round-2 review): `is_open` is a pure
    check and never mutates state; the half-open state allows a single
    trial — if it fails, the breaker re-opens immediately rather than
    needing a full new threshold of failures; failures recorded while
    already open do not extend the cooldown."""
    failure_threshold: int = 3
    cooldown_s: float = 30.0
    _failures: int = 0
    _opened_at: Optional[float] = None

    def __post_init__(self):
        # Degenerate configs silently disable the breaker (threshold 0
        # opens on the first failure regardless; cooldown 0 never
        # blocks) — reject them at construction (round-3 observation).
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.cooldown_s <= 0:
            raise ValueError("cooldown_s must be > 0")

    def _state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.time() - self._opened_at >= self.cooldown_s:
            return "half_open"
        return "open"

    @property
    def is_open(self) -> bool:
        return self._state() == "open"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        state = self._state()
        if state == "open":
            return  # do not extend the cooldown
        if state == "half_open":
            self._opened_at = time.time()  # failed trial: re-open at once
            self._failures = self.failure_threshold
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.time()


@dataclass
class Recovery:
    """Run fn, and on failure walk the recovery ladder in order."""
    retries: int = 1
    fallback: Optional[Callable[[Exception], T]] = None  # graceful degradation
    escalate: Optional[Callable[[Exception], T]] = None   # human escalation

    def __post_init__(self):
        if self.retries < 0:
            # range(retries + 1) would be empty: fn never runs, `last`
            # stays None, and the fallback receives None instead of an
            # exception (or `raise None` masks everything) — round-3.
            raise ValueError("retries must be >= 0")

    def run(self, fn: Callable[[], T]) -> T:
        last: Optional[Exception] = None
        for _ in range(self.retries + 1):
            try:
                return fn()
            except Exception as e:
                last = e
        if self.fallback is not None:
            return self.fallback(last)  # type: ignore[arg-type]
        if self.escalate is not None:
            return self.escalate(last)  # type: ignore[arg-type]
        raise last  # type: ignore[misc]


@dataclass
class ErrorClassifier:
    """Transient (retry) vs semantic (never retry) vs policy (escalate)."""
    transient_markers: tuple = ("timeout", "rate limit", "503", "connection")

    def classify(self, exc: Exception) -> str:
        msg = str(exc).lower()
        # Precedence is policy FIRST (round-3): an error that is
        # policy-flavoured must never be retried just because its message
        # also mentions a status code or a connection ("503 policy
        # violation" used to classify transient and get retried).
        if "policy" in msg or "permission" in msg:
            return "policy"
        if any(m in msg for m in self.transient_markers):
            return "transient"
        return "semantic"
