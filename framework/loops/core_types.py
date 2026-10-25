"""First-class loop core types (Lanham Ch 9's central implication):
frameworks that only offer 'run the agent again' force every long-horizon
system to reinvent state, planning, and stopping. Goal / Plan / State /
Decision / Termination are typed objects owned by code, and every state
object can project itself compactly for the controller (to_context)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Goal:
    description: str
    success_criteria: str  # measurable; SMART-shaped (Gulli Ch 11)
    budget: int = 50_000


@dataclass
class PlanItem:
    name: str
    status: str = "pending"  # pending | in_progress | complete
    notes: str = ""


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)
    strategy_notes: str = ""

    def progress_summary(self) -> str:
        done = sum(1 for i in self.items if i.status == "complete")
        doing = sum(1 for i in self.items if i.status == "in_progress")
        return f"{done}/{len(self.items)} complete, {doing} in progress"


@dataclass
class LoopState:
    goal: Goal
    plan: Plan = field(default_factory=Plan)
    findings: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 10
    status: str = "in_progress"

    def to_context(self) -> str:
        """Compact projection for the controller/model — never raw state."""
        return (f"goal={self.goal.description} | plan: {self.plan.progress_summary()} | "
                f"findings={len(self.findings)} | open={len(self.follow_up_questions)} | "
                f"iter={self.iteration_count}/{self.max_iterations} | status={self.status}")


@dataclass
class Decision:
    action: str  # delegate | replan | finalize | continue | escalate
    rationale: str = ""
    confidence: float = 0.5


def should_continue(state: LoopState) -> bool:
    """Ch 9's conjunction: running AND under cap AND work remains."""
    return (state.status == "in_progress"
            and state.iteration_count < state.max_iterations
            and len(state.follow_up_questions) > 0)
