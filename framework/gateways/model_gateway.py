"""Model gateway + Pattern 16 — Resource-Aware Optimization (Gulli Ch 16;
Lanham Ch 8 cost control/model routing).

One entry point for model calls: classify the step, route execution to
the cheapest capable model, meter tokens/cost, and walk a fallback chain
on failure. Budgets ride in the RunContext.

The two books differ on one point, and the framework keeps both halves:
execution routing is cheapest-capable-first (Gulli Ch 16), but the
routing *decision itself* defaults to a frontier model (Lanham Ch 8) —
'small model routes, large model reasons' is an optimisation to adopt
only after measuring routing quality against the frontier baseline. In
production, wire `classify` to the frontier model until that measurement
exists; the heuristic classifier here is the offline stand-in."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from llm import LLM, estimate_tokens
from skill_contracts.skill_spec import RunContext

# Illustrative relative prices (per 1k tokens); replace with provider data.
PRICES = {"mini": 0.15, "standard": 0.60, "frontier": 2.50, "reasoner": 3.00}


@dataclass
class ModelRoute:
    task_type: str
    model_name: str  # key into the models dict and PRICES
    fallbacks: list[str] = field(default_factory=list)


@dataclass
class ModelGateway:
    models: dict[str, LLM]
    routes: dict[str, ModelRoute] = field(default_factory=dict)
    default_route: str = "standard"
    stats: dict[str, dict] = field(default_factory=dict)

    def add_route(self, route: ModelRoute) -> "ModelGateway":
        self.routes[route.task_type] = route
        return self

    def classify(self, prompt: str) -> str:
        """Cheap heuristic classifier; swap for an LLM/ML router in prod."""
        if not isinstance(prompt, str):
            raise TypeError("classify() expects a string prompt")
        import re
        p = prompt.lower()
        # Whole-token matching (round-3): substring matching routed
        # "improve", "approved" and "proven" to the reasoning tier
        # (priced 5x standard) because they contain "prove", and
        # "plan ahead" tripped "plan a". Tokens + a word-bounded phrase.
        tokens = set(re.findall(r"[a-z']+", p))
        if (tokens & {"prove", "derive", "optimise", "optimize"}
                or re.search(r"\bplan a\b", p)):
            return "reasoning"
        if len(prompt.split()) < 20:
            return "simple"
        return "standard"

    def complete(self, ctx: RunContext, prompt: str, *, task_type: Optional[str] = None,
                 system: str = "") -> str:
        kind = task_type or self.classify(prompt)
        route = self.routes.get(kind) or ModelRoute(kind, self.default_route)
        chain = [route.model_name, *route.fallbacks]
        # The system prompt is sent on every attempt and billed by
        # providers; meter it too (round-3: it was invisible — a
        # 1,000-token system prompt charged as 0).
        prompt_tokens = estimate_tokens(prompt) + (
            estimate_tokens(system) if system else 0)
        last_error: Optional[Exception] = None
        for name in chain:
            model = self.models.get(name)
            if model is None:  # route names a model we don't have: a failed
                last_error = KeyError(f"unknown model '{name}'")  # attempt,
                self._meter(ctx, name, prompt_tokens, failed=True)
                continue                                   # not a crash
            try:
                out = model.complete(prompt, system=system)
            except Exception as e:  # provider failure -> next in chain
                last_error = e
                # Failed attempts are metered too: providers may bill
                # them, and they always cost latency. Hiding them makes
                # cost reports understate spend on flaky routes.
                self._meter(ctx, name, prompt_tokens, failed=True)
                continue
            self._meter(ctx, name, prompt_tokens + estimate_tokens(out))
            return out
        raise RuntimeError(f"all models failed for task '{kind}': {last_error}")

    def _meter(self, ctx: RunContext, name: str, tokens: int,
               *, failed: bool = False) -> None:
        ctx.charge(tokens)
        s = self.stats.setdefault(
            name, {"calls": 0, "tokens": 0, "cost": 0.0, "failures": 0})
        s["calls"] += 1
        s["tokens"] += tokens
        s["cost"] += tokens / 1000 * PRICES.get(name, 1.0)
        if failed:
            s["failures"] += 1

    def cost_report(self) -> dict:
        return {
            name: {**s, "cost": round(s["cost"], 4)} for name, s in self.stats.items()
        }
