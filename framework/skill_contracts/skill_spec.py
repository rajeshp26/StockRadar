"""Core types: the skill (agent) contract and shared value objects.

Implements the agent definition both source books converge on: persona +
pinned model + typed I/O + curated tools + reasoning strategy + memory
scopes + evaluation set + risk class + fallbacks.
(Lanham, AI Agents in Action 2e, Ch 2/11; Gulli, Agentic Design Patterns.)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

Risk = Literal["low", "medium", "high"]
Effect = Literal["read", "write_internal", "external"]
Reasoning = Literal["none", "cot", "react", "plan", "tot", "reflexion"]


@dataclass
class ToolSpec:
    """One tool in a skill's allow-list. The description is the selection
    surface: write it as 'Use when ...'. Safety fields follow Lanham Ch 8:
    a production tool spec declares more than name and schema."""
    name: str
    description: str
    effect: Effect = "read"
    timeout_s: float = 30.0
    schema: dict = field(default_factory=dict)  # JSON-schema-ish argument spec
    strict_schema: bool = True
    egress_allowlist: tuple[str, ...] = ()   # hosts a URL argument may reach;
    # NOTE: empty means UNRESTRICTED (not configured), not deny-all
    fs_scope: str | None = None              # prefix every path-shaped argument
    # (path/file/filepath/filename/directory) must stay under
    cpu_limit_s: float | None = None
    memory_limit_mb: int | None = None


@dataclass
class SkillSpec:
    """A skill = one agent, defined as a typed, versioned contract."""
    name: str  # domain.role.version, e.g. "support.answer.v1"
    persona: str
    model: str  # pinned model id, never "latest"
    temperature: float = 0.0
    reasoning: Reasoning = "react"
    max_iterations: int = 5
    tools: list[ToolSpec] = field(default_factory=list)
    risk: Risk = "low"
    eval_set: str = ""  # benchmark set id; empty means draft, not production
    fallback: str = "escalate"  # terminal state when retries exhaust
    memory_scopes: tuple[str, ...] = ("session",)
    description: str = ""  # router-facing one-liner

    def validate(self) -> list[str]:
        # A validator must never crash on the malformed input it exists to
        # catch (round-3: tools=None raised TypeError), and must check the
        # whole contract, not three fields of it.
        problems = []
        if not self.name:
            problems.append("name is empty (want domain.role.version)")
        if not self.persona:
            problems.append("persona is empty")
        if not self.model:
            problems.append("model is empty (pin a model id, never 'latest')")
        if self.risk not in ("low", "medium", "high"):
            problems.append(f"risk {self.risk!r} is not low|medium|high")
        if not (0.0 <= self.temperature <= 2.0):
            problems.append(f"temperature {self.temperature} outside 0..2")
        if self.max_iterations < 1:
            problems.append("max_iterations must be >= 1")
        if not self.eval_set:
            problems.append("no eval_set: skill is a draft, not production-ready")
        tools = self.tools
        if tools is None:
            problems.append("tools is None (want a list, possibly empty)")
            tools = []
        if len(tools) > 10:
            problems.append(f"{len(tools)} tools exceeds the ~10 tool budget")
        if self.risk == "high" and self.fallback == "escalate":
            pass  # high risk defaulting to human escalation is correct
        names = [t.name for t in tools]
        if len(names) != len(set(names)):
            problems.append("duplicate tool names")
        return problems


@dataclass
class RunContext:
    """Everything a run carries: identity, budgets, trace, session."""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str = "user"
    session_id: str = "default"
    tier: str = "standard"
    budget_tokens: int = 100_000
    spent_tokens: int = 0
    started_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def charge(self, tokens: int) -> bool:
        # Negative charges would "refund" budget and can push spent_tokens
        # below zero, minting budget out of a buggy meter (round-3).
        # bool is rejected explicitly: bool is an int subclass, and
        # charge(True) silently charging 1 token is a footgun.
        if isinstance(tokens, bool) or not isinstance(tokens, int):
            raise TypeError("charge amount must be an int token count")
        if tokens < 0:
            raise ValueError("charge amount must be >= 0")
        self.spent_tokens += tokens
        return self.spent_tokens <= self.budget_tokens

    @property
    def over_budget(self) -> bool:
        return self.spent_tokens > self.budget_tokens


@dataclass
class ToolResult:
    ok: bool
    value: Any = None
    error: Optional[str] = None
    error_kind: Optional[str] = None  # transient | invalid | policy | unknown

    @classmethod
    def success(cls, value: Any) -> "ToolResult":
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, error: str, kind: str = "unknown") -> "ToolResult":
        return cls(ok=False, error=error, error_kind=kind)


ToolFn = Callable[..., ToolResult]
