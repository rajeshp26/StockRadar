"""LLM access layer.

Real deployments plug a provider client behind the LLM protocol. Tests and
demos use StubLLM, a deterministic rule-based model, so every framework
behaviour is verifiable offline (TDAD needs reproducibility, Lanham Ch 7).
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Protocol


class LLM(Protocol):
    def complete(self, prompt: str, *, system: str = "") -> str: ...


class StubLLM:
    """Deterministic stand-in model.

    Rules are (predicate, responder) pairs checked in order; a responder is a
    string or a callable(prompt) -> str. Falls back to a default response.
    Records every call for tracing/evaluation.
    """

    def __init__(self, default: str = "I don't know."):
        self.rules: list[tuple[Callable[[str], bool], object]] = []
        self.calls: list[str] = []
        self.default = default

    def when(self, predicate: Callable[[str], bool], responder) -> "StubLLM":
        self.rules.append((predicate, responder))
        return self

    def when_contains(self, needle: str, responder) -> "StubLLM":
        return self.when(lambda p, n=needle.lower(): n in p.lower(), responder)

    def when_matches(self, pattern: str, responder) -> "StubLLM":
        rx = re.compile(pattern, re.I | re.S)
        return self.when(lambda p: bool(rx.search(p)), responder)

    def complete(self, prompt: str, *, system: str = "") -> str:
        full = f"{system}\n{prompt}" if system else prompt
        self.calls.append(full)
        for pred, responder in self.rules:
            if pred(full):
                result = responder(full) if callable(responder) else responder
                if result is None:
                    # A forgotten responder must not manufacture the
                    # literal string "None" as model output (round-3).
                    raise TypeError(
                        "StubLLM responder produced None; give the rule a "
                        "string or a callable returning a string")
                return result if isinstance(result, str) else str(result)
        return self.default


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) for budgeting and metering."""
    if not isinstance(text, str):
        raise TypeError(f"estimate_tokens expects str, got {type(text).__name__}")
    return max(1, (len(text) + 3) // 4)
