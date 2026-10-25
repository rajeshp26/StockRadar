"""The cognitive agent (Lanham Ch 10): cognition + metacognition.

Modules: workspace (bounded shared state), perception (complexity routing),
planning, execution, evaluation (confidence gates), attention, memory
(short-term queue + boundary awareness). Metacognition: monitor progress,
detect stagnation, know knowledge boundaries, adapt strategy — with the
book's numeric thresholds."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .task_loop import jaccard, token_set

# Lanham Ch 10 thresholds (as reported in the chapter)
COMPLEXITY_FAST = 0.3     # below: fast, direct path
COMPLEXITY_FULL = 0.7     # above: full cognitive cycle
CONF_LOW = 0.3            # below: escalate if no alternative strategy
CONF_MID = 0.6            # 0.3-0.6: one revision, then escalate
STAGNATION_OVERLAP = 0.7  # word overlap with a previous attempt -> pivot
PLATEAU_DELTA = 0.05      # quality improvement below this over 3 steps
BOUNDARY_INSIDE = 0.6     # boundary score above: plausibly answerable
BOUNDARY_EDGE = 0.3       # 0.3-0.6: attempt with caveats


def classify_perception(task: str) -> dict:
    """Perception module estimates (Lanham Ch 10 takeaway thresholds,
    corrected per audit): a question that looks simple but needs
    cross-referencing scores at least 0.5; one containing
    'but'/'however'/'already tried' is likely contradictory, at least 0.6.
    Perception classifies — it does not route (attention routes)."""
    t = task.lower()
    # Token-boundary matching (round-3): the old space-padded substrings
    # missed markers at string boundaries — a leading "But ..." and the
    # punctuated "A vs. B" both scored 0.0.
    cross_ref = 0.5 if (re.search(r"\b(compare|versus)\b", t)
                        or re.search(r"\bvs\.?\b", t)
                        or "difference between" in t) else 0.0
    contradictory = 0.6 if (re.search(r"\b(but|however)\b", t)
                            or "already tried" in t
                            or "didn't work" in t
                            or "did not work" in t) else 0.0
    return {"cross_reference_score": cross_ref,
            "contradiction_score": contradictory}


def route_attention(*, complexity: float, memory_hits: bool,
                    active_signal: str = "NONE", confidence: float = 0.5) -> str:
    """The attention module: deterministic routing, no LLM (Ch 10).
    FAST_RESPOND needs all three: complexity < 0.3, memory hits present,
    and no active signal. ESCALATE fires below confidence 0.2. Signal
    routes take priority over fall-through routes."""
    if active_signal == "STAGNATION":
        return "META_PLAN"
    if confidence < 0.2:
        return "ESCALATE"
    if complexity < COMPLEXITY_FAST and memory_hits and active_signal == "NONE":
        return "FAST_RESPOND"
    if complexity > COMPLEXITY_FULL:
        return "PLAN"
    return "EXECUTE"


@dataclass
class CognitiveWorkspace:
    capacity: int = 7  # Miller-style bounded workspace
    items: list[str] = field(default_factory=list)
    focus: Optional[str] = None

    def push(self, item: str) -> None:
        self.items.append(item)
        if len(self.items) > self.capacity:
            self.items.pop(0)  # attention drops the least recent item
        self.focus = item


@dataclass
class Attempt:
    strategy: str
    output: str
    confidence: float
    quality: float


@dataclass
class CognitiveAgent:
    strategies: dict[str, Callable[[str], tuple[str, float]]]  # name -> fn(task)->(output, confidence)
    workspace: CognitiveWorkspace = field(default_factory=CognitiveWorkspace)
    attempts: list[Attempt] = field(default_factory=list)
    short_term: list[str] = field(default_factory=list)
    # Confidence is framework state (Ch 10's DMC lesson): starts at 0.5,
    # updated by evaluation deltas (-0.3..+0.3), never taken from the
    # model's stated confidence in its own prose.
    confidence: float = 0.5
    excluded_strategies: set[str] = field(default_factory=set)

    def perceive_complexity(self, task: str) -> float:
        """Heuristic complexity: length + constraint markers. Real systems
        use a small model; the routing bands are the book's."""
        words = len(task.split())
        # Whole-token markers only (round-3): substring counting made
        # "command" and "understand" register as "and", inflating the
        # complexity of ordinary English across the routing bands.
        tokens = re.findall(r"[a-z']+", task.lower())
        markers = sum(tokens.count(m) for m in
                      ("and", "then", "if", "compare", "optimise", "optimize", "all"))
        return min(1.0, words / 120 + markers * 0.08)

    def boundary_score(self, task: str, known_topics: list[str]) -> float:
        toks = token_set(task)
        if not toks:
            return 0.0
        known = set()
        for t in known_topics:
            known |= token_set(t)
        return len(toks & known) / len(toks)

    def run(self, task: str, *, known_topics: Optional[list[str]] = None) -> dict:
        complexity = self.perceive_complexity(task)
        boundary = self.boundary_score(task, known_topics or [])
        result: dict = {"complexity": round(complexity, 3),
                        "boundary": round(boundary, 3),
                        "perception": classify_perception(task)}
        if boundary < BOUNDARY_EDGE:
            result.update(status="out_of_boundary",
                          action="abstain/escalate: outside knowledge boundary")
            return result
        names = [n for n in self.strategies if n not in self.excluded_strategies]
        if complexity < COMPLEXITY_FAST:
            order = names[:1]  # fast path: default strategy only
        else:
            order = names        # full cycle: strategies available for pivots
        # Stagnation is judged WITHIN a run (round-3): attempts from
        # earlier, unrelated run() calls used to contaminate the check —
        # a fresh task's first attempt was flagged stagnant against a
        # previous task's output and its strategy excluded.
        run_start = len(self.attempts)
        quality_history: list[float] = []
        for i, name in enumerate(order):
            output, confidence = self.strategies[name](task)
            if confidence != confidence:  # NaN: comparisons all False, so
                confidence = 0.0          # min(0.3, nan) quietly became
            confidence = max(0.0, min(1.0, confidence))  # a +0.3 delta
            # evaluation delta updates the framework-held confidence
            delta = max(-0.3, min(0.3, confidence - 0.5))
            self.confidence = max(0.0, min(1.0, self.confidence + delta))
            quality = confidence  # evaluation module: confidence as quality proxy
            attempt = Attempt(name, output, confidence, quality)
            self.attempts.append(attempt)
            self.workspace.push(output[:80])
            quality_history.append(quality)
            # Metacognitive stagnation: high overlap with a previous
            # attempt FROM THIS RUN
            stagnated = any(
                jaccard(token_set(output), token_set(a.output)) > STAGNATION_OVERLAP
                for a in self.attempts[run_start:-1])
            plateau = (len(quality_history) >= 4 and
                       quality_history[-1] - quality_history[-4] < PLATEAU_DELTA)
            if confidence >= CONF_MID and not stagnated:
                result.update(status="answered", strategy=name,
                              output=output, confidence=confidence)
                return result
            if confidence < CONF_LOW and i == len(order) - 1:
                result.update(status="escalate", strategy=name,
                              output=output, confidence=confidence,
                              reason="confidence below 0.3 with no strategy left")
                return result
            if stagnated or plateau:
                # META_PLAN path (Ch 10): replan with the failed strategy
                # explicitly excluded — not a tool/model swap.
                self.excluded_strategies.add(name)
                result.setdefault("pivots", []).append(
                    {"from": name, "excluded": name,
                     "reason": "stagnation" if stagnated else "plateau"})
                continue  # pivot to the next strategy
        if not order:
            # Round-2 fix: an empty effective strategy set (empty dict, or
            # every strategy excluded by earlier runs) crashed on
            # attempts[-1] — or worse, on a reused agent silently returned
            # a previous run's output as if it were fresh.
            result.update(status="no_strategy_available",
                          action="register a strategy or clear exclusions")
            return result
        last = self.attempts[run_start:][-1]  # this run's last attempt
        result.update(status="answered_low_confidence", strategy=last.strategy,
                      output=last.output, confidence=last.confidence,
                      caveat="attempted with caveats (edge of boundary)"
                      if boundary < BOUNDARY_INSIDE else "")
        return result
