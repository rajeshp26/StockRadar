"""Pattern 1 — Prompt Chaining (Gulli Ch 1; Lanham Ch 2/4).

Fixed sequence of single-purpose steps; the contract between steps is
structured data (JSON), validated before it feeds the next step; one narrow
retry per step, then fail loudly."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from llm import LLM


class ChainError(RuntimeError):
    pass


@dataclass
class ChainStep:
    name: str
    prompt: Callable[[Any], str]
    validate: Optional[Callable[[Any], None]] = None  # raise on bad output
    parse_json: bool = True


def require_keys(*keys: str) -> Callable[[Any], None]:
    def _check(data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("step output is not a JSON object")
        missing = [k for k in keys if k not in data]
        if missing:
            raise ValueError(f"missing keys: {missing}")
    return _check


def run_chain(llm: LLM, steps: list[ChainStep], payload: Any, *, retries: int = 1) -> Any:
    if retries < 0:
        # range(retries + 1) would be empty: every step silently skipped
        # and the input returned as if processed (round-3). Fail loud.
        raise ValueError("retries must be >= 0")
    current = payload
    for step in steps:
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            hint = ""
            if last_error is not None:
                hint = f"\nPrevious attempt failed validation: {last_error}. Fix it."
            raw = llm.complete(step.prompt(current) + hint)
            try:
                data = json.loads(raw) if step.parse_json else raw
                if step.validate:
                    step.validate(data)
                current = data
                last_error = None
                break
            except Exception as e:  # validation failure is control flow
                last_error = e
        if last_error is not None:
            raise ChainError(f"chain step '{step.name}' failed: {last_error}")
    return current
