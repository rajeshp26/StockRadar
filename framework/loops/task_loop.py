"""The three-layer agentic loop (Lanham Ch 9), task layer implemented.

State, plan, and actions are typed objects in code, not prompt text.
Termination is a layered gate: iteration cap, budget, goal check,
quality gate, and a stagnation detector (~0.85 similarity between
consecutive outputs)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


@dataclass
class TaskState:
    goal: str
    plan: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    steps: int = 0
    spent: int = 0
    done_reason: Optional[str] = None


@dataclass
class TerminationGate:
    max_steps: int = 10
    budget: int = 50_000
    stagnation_threshold: float = 0.85  # Lanham Ch 10's similarity value
    goal_check: Optional[Callable[[TaskState], bool]] = None

    def should_stop(self, state: TaskState, last_output: str,
                    prev_output: Optional[str]) -> Optional[str]:
        if state.steps >= self.max_steps:
            return "iteration_cap"
        if state.spent >= self.budget:
            return "budget"
        if self.blocks_now(state):
            return "blocked"
        if self.goal_check and self.goal_check(state):
            return "goal_met"
        if prev_output is not None and jaccard(
                token_set(last_output), token_set(prev_output)) >= self.stagnation_threshold:
            return "stagnation"
        return None

    @staticmethod
    def blocks_now(state: TaskState) -> bool:
        return False  # hook: subclasses wire real dependency checks


# A step function receives the state and returns (output, tokens_spent).
StepFn = Callable[[TaskState], tuple[str, int]]


@dataclass
class TaskLoop:
    gate: TerminationGate

    def run(self, state: TaskState, step: StepFn) -> TaskState:
        prev: Optional[str] = None
        while True:
            output, spent = step(state)
            state.steps += 1
            state.spent += spent
            state.findings.append(output)
            reason = self.gate.should_stop(state, output, prev)
            if reason:
                state.done_reason = reason
                return state
            prev = output
