"""Pattern 6 — Planning (Gulli Ch 6; Lanham Ch 5), plus Pattern 11 —
Goal Setting & Monitoring (Gulli Ch 11).

Plans are explicit, inspectable artefacts. Execution is stepwise; a blocked
step triggers re-planning, not failure. Goals carry measurable success
criteria and a machine-readable stop verdict."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

from llm import LLM


@dataclass
class PlanStep:
    description: str
    status: str = "pending"  # pending | in_progress | done | blocked


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        # An empty plan is not "complete" — all([]) is True, but a plan
        # with no steps evidences no work (round-3).
        return len(self.steps) > 0 and all(s.status == "done" for s in self.steps)


def make_plan(llm: LLM, goal: str, constraints: str = "") -> Plan:
    raw = llm.complete(
        f"Goal: {goal}\nConstraints: {constraints}\n"
        'Reply with a JSON array of step strings, e.g. ["step one", "step two"].'
    )
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        # A JSON object would otherwise be "iterated" into its keys and
        # silently become a plan of key names (round-3).
        raise ValueError(f"plan must be a JSON array of steps, got {type(parsed).__name__}")
    # null items are dropped rather than coerced into a step named "None".
    steps = [PlanStep(str(s)) for s in parsed if s is not None]
    return Plan(goal=goal, steps=steps)


def execute_plan(
    llm: LLM,
    plan: Plan,
    executor: Callable[[PlanStep, Plan], str],
    *,
    max_replans: int = 2,
) -> Plan:
    """executor returns 'done' or 'blocked: <reason>' per step."""
    replans = 0
    i = 0
    while i < len(plan.steps):
        step = plan.steps[i]
        step.status = "in_progress"
        outcome = executor(step, plan)
        if outcome == "done":
            step.status = "done"
            i += 1
            continue
        step.status = "blocked"
        if replans >= max_replans:
            break
        replans += 1
        fresh = make_plan(
            llm,
            f"{plan.goal} (re-plan: step '{step.description}' blocked: {outcome})",
        )
        plan.steps = [s for s in plan.steps if s.status == "done"] + fresh.steps
        i = len([s for s in plan.steps if s.status == "done"])
    return plan


@dataclass
class GoalMonitor:
    """Generate -> evaluate -> refine with a True/False stop verdict and a
    framework-level iteration cap (Gulli Ch 11). The fallback artefact is
    the best-scoring candidate when a `scorer` is supplied, otherwise the
    latest candidate (round-3: the old code labelled the last candidate
    "best-so-far" with no scoring anywhere, so a degrading run returned
    its worst artefact under the name `best`)."""
    llm: LLM
    goal_description: str
    max_iterations: int = 5
    scorer: Optional[Callable[[str], float]] = None

    def __post_init__(self):
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")

    def goals_met(self, artefact: str) -> bool:
        raw = self.llm.complete(
            f"Goal: {self.goal_description}\nArtefact:\n{artefact}\n"
            "Reply with exactly 'true' if the goal is fully met, else 'false'."
        ).strip().lower()
        return raw == "true"

    def run(self, generator: Callable[[Optional[str]], str]) -> tuple[str, bool, int]:
        fallback, fallback_score, feedback = "", float("-inf"), None
        for i in range(1, self.max_iterations + 1):
            candidate = generator(feedback)
            if self.goals_met(candidate):
                return candidate, True, i
            if candidate:
                if self.scorer is not None:
                    s = self.scorer(candidate)
                    if s == s and s > fallback_score:  # skip NaN scores
                        fallback, fallback_score = candidate, s
                else:
                    fallback = candidate  # latest-so-far
            feedback = f"Goal not yet met: {self.goal_description}"
        return fallback, False, self.max_iterations
