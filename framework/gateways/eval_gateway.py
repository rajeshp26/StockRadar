"""Evaluation gateway — Pattern 19 (Gulli Ch 19) + TDAD (Lanham Ch 7).

Test-Driven Agent Development: write expected-output and known-bad
benchmarks first, run candidates >= 3 times (LLM variance), score, and
compare against the manual baseline before blaming a prompt. Changes walk
the minimal-change ladder, not the whole system at once."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Benchmark:
    id: str
    input: str
    kind: str  # expected | known_bad | edge
    expected_contains: Optional[str] = None
    forbidden_contains: Optional[str] = None


@dataclass
class EvalReport:
    benchmark_id: str
    runs: int
    passed: int
    errors: int = 0  # runs lost to a raising candidate/judge (fault isolation)

    def __post_init__(self):
        if self.runs < 0 or self.errors < 0 or not (0 <= self.passed <= self.runs):
            raise ValueError(
                f"inconsistent EvalReport: passed={self.passed} of runs={self.runs}")

    @property
    def pass_rate(self) -> float:
        return self.passed / self.runs if self.runs else 0.0


def normalise(text: str) -> str:
    """Surface-form normalisation: case, whitespace, punctuation. Ch 7's
    lesson is built in — grading by raw string equality is an evaluator
    bug; two of the book's 'failures' were correct answers rephrased."""
    import re
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


# A judge decides semantic equivalence where many phrasings are correct:
# judge(answer, reference) -> bool. In production this is an independent
# LLM; in tests, a deterministic stand-in.
Judge = Callable[[str, str], bool]


@dataclass
class EvalGateway:
    runs_per_benchmark: int = 3  # variance rule: never judge on a single run

    def run_benchmark(self, bench: Benchmark,
                      candidate: Callable[[str], str],
                      judge: Optional[Judge] = None) -> EvalReport:
        if not bench.expected_contains and not bench.forbidden_contains:
            # A benchmark with no criteria passes vacuously against ANY
            # output ("" is a substring of everything; two Nones check
            # nothing) and is indistinguishable from a real pass in the
            # gate (round-3). It is an authoring error: fail loud,
            # before any run, outside the fault-isolation below.
            raise ValueError(
                f"benchmark {bench.id!r} has no criteria: set "
                "expected_contains and/or forbidden_contains")
        passed = 0
        errors = 0
        for _ in range(self.runs_per_benchmark):
            # Fault isolation (round-2 fix): a raising candidate or judge
            # fails this run and is counted — it must not abort the whole
            # suite and destroy all promotion evidence.
            try:
                out = candidate(bench.input)
                ok = True
                if bench.expected_contains:
                    exp = bench.expected_contains
                    ok = normalise(exp) in normalise(out)
                    if not ok and judge is not None:
                        # Coerce explicitly (round-3): a judge returning
                        # a truthy non-bool ("yes") used to crash int(ok)
                        # OUTSIDE this try block, destroying the suite.
                        ok = bool(judge(out, exp))
                if bench.forbidden_contains:
                    bad = bench.forbidden_contains
                    if normalise(bad) in normalise(out):
                        ok = False
                    elif judge is not None and bool(judge(out, bad)):
                        ok = False
            except Exception:
                ok = False
                errors += 1
            passed += int(ok)
        return EvalReport(bench.id, self.runs_per_benchmark, passed, errors)

    def run_suite(self, benches: list[Benchmark],
                  candidate: Callable[[str], str],
                  judge: Optional[Judge] = None) -> dict[str, EvalReport]:
        ids = [b.id for b in benches]
        if len(ids) != len(set(ids)):
            # Duplicate ids used to silently overwrite each other (last
            # wins) — a failing report could be hidden by a passing
            # namesake (round-3).
            raise ValueError(f"duplicate benchmark ids in suite: {sorted(ids)}")
        return {b.id: self.run_benchmark(b, candidate, judge) for b in benches}

    @staticmethod
    def gate(reports: dict[str, EvalReport], *, min_pass_rate: float = 1.0) -> bool:
        """Promotion gate: a change ships only if every benchmark passes at
        the required rate. Known-bad regressions block release. An EMPTY
        report set never passes (round-3, the round's headline bug):
        all([]) is True, but no evidence is not passing evidence."""
        return bool(reports) and all(
            r.pass_rate >= min_pass_rate for r in reports.values())
