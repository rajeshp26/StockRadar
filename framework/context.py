"""Context assembly: the framework's context-engineering service.

Context is a budgeted resource, assembled stable-first (persona, then
retrieved knowledge, then memory, then the live request) so prompt caching
works and the window is never a transcript dump.
(Lanham Ch 1/6; Gulli Intro + Ch 8, App A: context engineering.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from llm import estimate_tokens


@dataclass
class ContextPart:
    kind: str  # persona | knowledge | memory | history | request
    text: str
    priority: int = 5  # lower survives trimming longer

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


@dataclass
class ContextAssembler:
    budget_tokens: int = 8_000
    parts: list[ContextPart] = field(default_factory=list)

    def add(self, kind: str, text: str, priority: int = 5) -> "ContextAssembler":
        self.parts.append(ContextPart(kind, text, priority))
        return self

    @staticmethod
    def _rendered_tokens(part: ContextPart) -> int:
        # The rendered form adds a "[kind]" header and separators; the
        # budget applies to what the model actually receives, so headers
        # are counted too (round-2 fix: uncounted headers let rendered
        # output exceed the budget).
        return part.tokens + estimate_tokens(f"[{part.kind}]") + 1

    def build(self) -> str:
        # Stable-first ordering: persona(0) < knowledge(1) < memory(2)
        # < history(3) < request(4), then trim lowest-value parts (highest
        # priority number, latest first) until under budget.
        order = {"persona": 0, "knowledge": 1, "memory": 2, "history": 3, "request": 4}
        # build() is a projection, not a mutation: work on copies so the
        # hard-cap truncation below can never rewrite the caller's stored
        # parts (round-3: one build permanently destroyed the original).
        parts = [ContextPart(p.kind, p.text, p.priority)
                 for p in sorted(self.parts, key=lambda p: order.get(p.kind, 5))]
        total = sum(self._rendered_tokens(p) for p in parts)
        while total > self.budget_tokens and len(parts) > 1:
            # drop the part with the worst (priority, position) value,
            # never the persona or the request itself
            droppable = [p for p in parts if p.kind not in ("persona", "request")]
            if not droppable:
                break
            victim = max(droppable, key=lambda p: (p.priority, parts.index(p)))
            parts.remove(victim)
            total -= self._rendered_tokens(victim)
        if total > self.budget_tokens and parts:
            # Hard cap (round-2 fix): persona/request are never dropped,
            # so a single oversized part could otherwise blow the budget
            # by orders of magnitude. Truncate the largest part's text to
            # fit what remains. Estimate is ~4 chars/token.
            overhead = sum(estimate_tokens(f"[{p.kind}]") + 1 for p in parts)
            text_budget = max(0, (self.budget_tokens - overhead) * 4)
            largest = max(parts, key=lambda p: len(p.text))
            others = sum(len(p.text) for p in parts if p is not largest)
            marker = " …[truncated to budget]"
            allowed = max(0, text_budget - others - len(marker))
            if len(largest.text) > allowed:
                largest.text = largest.text[:allowed] + marker
        return "\n\n".join(f"[{p.kind}]\n{p.text}" for p in parts)
