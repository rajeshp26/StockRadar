"""Tracing: every run emits structured spans (Lanham Ch 2/7/8: trace
everything, with session + metadata; Phoenix/Langfuse-style backends in
production, an in-memory sink here)."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Span:
    name: str
    started_at: float
    ended_at: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.ended_at - self.started_at) * 1000 if self.ended_at else 0.0


class Tracer:
    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self.spans: list[Span] = []

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        s = Span(name=name, started_at=time.time(), attributes=dict(attributes))
        self.spans.append(s)
        try:
            yield s
        finally:
            s.ended_at = time.time()

    def event(self, span: Span, kind: str, **data: Any) -> None:
        span.events.append({"kind": kind, **data})

    def export(self) -> list[dict[str, Any]]:
        # Deep copies: an export is a snapshot. Aliasing the live
        # attributes/events dicts would let a consumer rewrite the
        # tracer's own records by mutating the export (round-3).
        import copy
        return [
            {
                "run_id": self.run_id,
                "span": s.name,
                "duration_ms": round(s.duration_ms, 2),
                "attributes": copy.deepcopy(s.attributes),
                "events": copy.deepcopy(s.events),
            }
            for s in self.spans
        ]
