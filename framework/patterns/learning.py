"""Pattern 9 — Learning & Adaptation (Gulli Ch 9), in its safe form.

Feedback/outcomes are captured, distilled into a candidate procedural
memory update, and promoted only if the evaluation suite still passes —
self-modification governed by regression gates, never silent drift."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..gateways.eval_gateway import Benchmark, EvalGateway
from ..gateways.memory_gateway import ProceduralMemory


@dataclass
class Feedback:
    situation: str
    outcome: str  # success | failure
    lesson: str


@dataclass
class LearningLoop:
    procedural: ProceduralMemory
    evaluator: EvalGateway = field(default_factory=EvalGateway)
    feedback_log: list[Feedback] = field(default_factory=list)

    def record(self, fb: Feedback) -> None:
        self.feedback_log.append(fb)

    def propose_update(self, skill_name: str, new_instructions: str,
                       benchmarks: list[Benchmark],
                       candidate: Callable[[str], str]) -> bool:
        """Promote a procedural update only through the regression gate."""
        if not benchmarks:
            # Belt and braces with the gate's own empty-set rule: a
            # caller that accidentally passes an empty/filtered list
            # must never disable the regression gate (round-3, R3P-1).
            return False
        reports = self.evaluator.run_suite(benchmarks, candidate)
        if not self.evaluator.gate(reports):
            return False
        self.procedural.set(skill_name, new_instructions)
        return True
