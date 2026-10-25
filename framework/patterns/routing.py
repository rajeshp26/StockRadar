"""Pattern 2 — Routing (Gulli Ch 2), doubling as the routing gateway.

Router families in cost order: rules -> embeddings/classifier -> LLM with a
closed label set. A fallback route is mandatory and must be reachable.
Every decision is logged so the router itself can be evaluated."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from llm import LLM


@dataclass
class RoutingDecision:
    label: str
    method: str  # rules | llm | fallback
    raw: str = ""


@dataclass
class Router:
    labels: list[str]
    llm: Optional[LLM] = None
    fallback: str = "unclear"
    rules: list[tuple[str, str]] = field(default_factory=list)  # (regex, label)
    log: list[RoutingDecision] = field(default_factory=list)

    def add_rule(self, pattern: str, label: str) -> "Router":
        if label not in self.labels:
            raise ValueError(f"rule label {label!r} not in labels {self.labels}")
        re.compile(pattern)  # fail fast: an invalid regex raises here, at
        # configuration time, not inside route() on the first request
        self.rules.append((pattern, label))
        return self

    def route(self, request: str) -> RoutingDecision:
        if not isinstance(request, str):
            raise TypeError("route() expects a string request")
        for pattern, label in self.rules:
            if re.search(pattern, request, re.I):
                d = RoutingDecision(label, "rules")
                self.log.append(d)
                return d
        if self.llm is not None:
            raw = self.llm.complete(
                "Classify the request into exactly one label from "
                f"{self.labels}. Reply with only the label.\nRequest: {request}"
            ).strip().lower()
            # Compare case-insensitively but RETURN the label as
            # registered: labels are a closed set with canonical case,
            # and "Billing" must be reachable (round-3).
            canonical = {label.lower(): label for label in self.labels}
            if raw in canonical:
                d = RoutingDecision(canonical[raw], "llm", raw)
                self.log.append(d)
                return d
            d = RoutingDecision(self.fallback, "fallback", raw)
            self.log.append(d)
            return d
        d = RoutingDecision(self.fallback, "fallback")
        self.log.append(d)
        return d

    def dispatch(self, request: str, handlers: dict[str, Callable[[str], Any]]) -> Any:
        # The fallback label is an escape hatch that may sit outside the
        # closed label set (default "unclear"); dispatch must fail with a
        # clear error, not a bare KeyError, when no handler covers either.
        decision = self.route(request)
        handler = handlers.get(decision.label) or handlers.get(self.fallback)
        if handler is None:
            raise LookupError(
                f"no handler for routed label {decision.label!r} "
                f"or fallback {self.fallback!r}")
        return handler(request)
