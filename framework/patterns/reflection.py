"""Pattern 4 — Reflection (Gulli Ch 4; Lanham Ch 5 Reflexion, Ch 7 critics).

Producer-critic loop with two stopping criteria: a machine-readable
approval sentinel and a hard iteration cap. Use a different model (or an
adversarial persona) for the critic in production."""
from __future__ import annotations

from dataclasses import dataclass, field

from llm import LLM

APPROVED = "APPROVED"


@dataclass
class ReflectionResult:
    output: str
    iterations: int
    critiques: list[str] = field(default_factory=list)
    approved: bool = False


def reflect(
    producer: LLM,
    critic: LLM,
    task: str,
    criteria: list[str],
    *,
    max_iterations: int = 3,
) -> ReflectionResult:
    if max_iterations < 1:
        # 0/-1 would return an empty draft the producer never wrote,
        # labelled with a nonsense iteration count (round-3).
        raise ValueError("max_iterations must be >= 1")
    draft = ""
    critiques: list[str] = []
    for i in range(1, max_iterations + 1):
        feedback = "\n".join(f"- {c}" for c in critiques) or "(none yet)"
        draft = producer.complete(
            f"Task: {task}\nPrevious draft:\n{draft}\nCritic feedback:\n{feedback}\n"
            "Produce the best possible result."
        )
        verdict = critic.complete(
            f"Review the draft against these criteria: {criteria}.\n"
            f"If it meets ALL criteria reply with exactly '{APPROVED}'. "
            f"Otherwise list numbered defects only.\nDraft:\n{draft}"
        ).strip()
        if verdict == APPROVED:
            return ReflectionResult(draft, i, critiques, approved=True)
        critiques.append(verdict)
    return ReflectionResult(draft, max_iterations, critiques, approved=False)
