"""Pattern 20 — Prioritization (Gulli Ch 20), and Pattern 21 —
Exploration & Discovery (Gulli Ch 21).

Prioritisation: criteria -> evaluation -> selection -> dynamic
re-prioritisation, on a small validated scale, with stated defaults.
Exploration: generate / critique / rank / evolve under a supervisor, with
an explicit budget because open-ended search burns compute by design."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

PRIORITIES = ("P0", "P1", "P2")  # P0 highest


@dataclass
class Task:
    id: str
    title: str
    priority: str = "P1"  # stated default for underspecified work
    urgency: int = 0      # 0..3
    importance: int = 0   # 0..3
    blocked_by: list[str] = field(default_factory=list)
    assignee: Optional[str] = None
    done: bool = False

    def __post_init__(self):
        if self.priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
        if not (0 <= self.urgency <= 3) or not (0 <= self.importance <= 3):
            raise ValueError("urgency and importance are on the stated 0..3 scale")


@dataclass
class Prioritizer:
    tasks: dict[str, Task] = field(default_factory=dict)
    _seq: int = 0

    def add(self, title: str, **kw) -> Task:
        self._seq += 1
        t = Task(id=f"TASK-{self._seq:03d}", title=title, **kw)
        self.tasks[t.id] = t
        return t

    def score(self, t: Task) -> tuple:
        # A blocker id that doesn't resolve is NOT silently "ready": a
        # typo'd id used to unblock work (round-3). Unknown or unfinished
        # blockers both mean blocked. Self- and cyclic blockers can never
        # become ready, which is the correct fixed point.
        ready = 0 if all(b in self.tasks and self.tasks[b].done
                         for b in t.blocked_by) else 1
        return (ready, PRIORITIES.index(t.priority), -(t.urgency + t.importance))

    def next_task(self) -> Optional[Task]:
        """The best READY task, or None when nothing is actionable —
        every open task is blocked (or there are none). Returning a
        blocked task as 'next' would hand the caller work it cannot
        start (round-3)."""
        ready = [t for t in self.tasks.values()
                 if not t.done and self.score(t)[0] == 0]
        if not ready:
            return None
        return sorted(ready, key=self.score)[0]

    def reprioritize_on_event(self, task_id: str, priority: str) -> None:
        """Event-driven re-ranking: e.g. an outage report jumps the queue."""
        if priority not in PRIORITIES:
            # Validate at the mutation site, like the constructor does;
            # an invalid value used to sit dormant until score() crashed
            # with a bare tuple.index ValueError (round-3).
            raise ValueError(f"priority must be one of {PRIORITIES}")
        self.tasks[task_id].priority = priority


@dataclass
class ExplorationResult:
    best: str
    best_score: float
    rounds: int
    history: list[tuple[str, float]] = field(default_factory=list)


def explore(
    generate: Callable[[int, list[tuple[str, float]]], str],
    score: Callable[[str], float],
    *,
    rounds: int = 5,
    budget: int = 20,
) -> ExplorationResult:
    """Generate -> score -> evolve loop (AI co-scientist shape, simplified):
    candidates are scored, the best is kept, and history feeds generation."""
    if rounds < 0 or budget < 0:
        raise ValueError("rounds and budget must be >= 0")
    history: list[tuple[str, float]] = []
    best, best_score = "", float("-inf")
    spent = 0
    r = 0
    while r < rounds and spent < budget:
        # generate receives a COPY of history: it used to get the live
        # result list and could inject unscored entries into the record
        # the caller gets back (round-3).
        candidate = generate(r, list(history))
        spent += 1
        s = score(candidate)
        history.append((candidate, s))
        if s == s and s > best_score:  # NaN scores never become "best"
            best, best_score = candidate, s
        r += 1
    return ExplorationResult(best, best_score, r, history)
