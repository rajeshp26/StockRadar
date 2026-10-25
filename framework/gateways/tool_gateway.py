"""Tool gateway (Lanham Ch 3 MCP gateway principles; Gulli Ch 5/10/12/18).

The model proposes; the gateway executes: allow-list per skill, argument
validation, identity veto hooks, effect-tier policy, timeouts, selective
retry (transient only — never retry semantically invalid actions), and a
standard result/error envelope. In production this boundary is an MCP
client; locally registered tools follow the same contract."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from skill_contracts.skill_spec import RunContext, SkillSpec, ToolFn, ToolResult, ToolSpec

VetoHook = Callable[[RunContext, str, dict], Optional[dict]]


@dataclass
class RetryPolicy:
    max_retries: int = 2
    base_delay_s: float = 0.0  # tests keep 0; production: backoff + jitter

    def __post_init__(self):
        # A negative base delay used to crash call() mid-retry with
        # time.sleep's ValueError instead of a ToolResult (round-3).
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.base_delay_s < 0:
            raise ValueError("base_delay_s must be >= 0")

    def delay(self, attempt: int) -> float:
        return self.base_delay_s * (2 ** attempt)


@dataclass
class ToolGateway:
    registry: dict[str, tuple[ToolSpec, ToolFn]] = field(default_factory=dict)
    veto_hooks: list[VetoHook] = field(default_factory=list)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    audit: list[dict] = field(default_factory=list)

    def register(self, spec: ToolSpec, fn: ToolFn) -> "ToolGateway":
        self.registry[spec.name] = (spec, fn)
        return self

    def add_veto(self, hook: VetoHook) -> "ToolGateway":
        self.veto_hooks.append(hook)
        return self

    def tools_for(self, skill: SkillSpec) -> list[ToolSpec]:
        """Per-agent allow-list: a skill only ever sees its own tools."""
        return [self.registry[t.name][0] for t in skill.tools if t.name in self.registry]

    def call(self, ctx: RunContext, skill: SkillSpec, tool: str, /,
             **args) -> ToolResult:
        # Positional-only parameters (round-3): a model may legitimately
        # emit a tool argument named "ctx"/"skill"/"tool" — with named
        # parameters that collided at binding time and the TypeError
        # escaped the executor instead of becoming an Observation.
        allowed = {t.name for t in skill.tools}
        record = {"tool": tool, "args": args, "run_id": ctx.run_id}
        if tool not in allowed or tool not in self.registry:
            result = ToolResult.failure(f"tool '{tool}' not in skill allow-list", "policy")
            record["result"] = "policy-denied"
            self.audit.append(record)
            return result
        for hook in self.veto_hooks:
            try:
                veto = hook(ctx, tool, args)
            except Exception as e:
                # A broken hook must not break the envelope (round-3):
                # fail closed, audited, as a policy denial.
                record["result"] = f"veto-hook-error: {e}"
                self.audit.append(record)
                return ToolResult.failure(f"veto hook failed: {e}", "policy")
            if veto:  # only a NON-EMPTY dict vetoes; {} means abstain
                record["result"] = f"vetoed: {veto}"
                self.audit.append(record)
                return ToolResult.failure(str(veto.get("error", "vetoed")), "policy")
        spec, fn = self.registry[tool]
        # Ch 8 safety fields: filesystem scope and egress allowlist are
        # enforced in code at the gateway, not requested in prompts.
        # The scope applies to every path-shaped argument, not only one
        # literally named "path" (round-3).
        path_args = [k for k in ("path", "file", "filepath", "filename",
                                 "directory", "dir") if k in args]
        if spec.fs_scope and path_args:
            import posixpath
            # Segment-aware containment on the normalised path: a raw
            # string prefix check passes '/project-evil' and
            # '/project/../etc' — both must be denied.
            scope = posixpath.normpath(spec.fs_scope)
            for key in path_args:
                p = posixpath.normpath(str(args[key]))
                if not (p == scope or p.startswith(scope.rstrip("/") + "/")):
                    record["result"] = "fs-scope-denied"
                    self.audit.append(record)
                    return ToolResult.failure(
                        f"path '{p}' outside filesystem scope '{spec.fs_scope}'", "policy")
        if spec.egress_allowlist and "url" in args:
            from urllib.parse import urlparse
            host = urlparse(str(args["url"])).hostname or ""
            if host not in spec.egress_allowlist:
                record["result"] = "egress-denied"
                self.audit.append(record)
                return ToolResult.failure(
                    f"host '{host}' not in egress allowlist", "policy")
        required = spec.schema.get("required", [])
        missing = [k for k in required if k not in args]
        if missing:
            record["result"] = "invalid-args"
            self.audit.append(record)
            return ToolResult.failure(f"missing required args: {missing}", "invalid")
        attempt = 0
        while True:
            started = time.time()
            try:
                result = fn(**args)
                if not isinstance(result, ToolResult):
                    # The envelope is the contract (round-3): a handler
                    # returning a bare string/None used to crash the
                    # gateway with AttributeError on .ok.
                    result = ToolResult.failure(
                        f"tool '{tool}' returned {type(result).__name__}, "
                        "not a ToolResult", "invalid")
            except Exception as e:
                # Exceptions are classified, not blanket-stamped
                # transient: a semantic failure raised as an exception
                # must not be retried (the framework's own rule).
                from ..patterns.errors import ErrorClassifier
                kind = ErrorClassifier().classify(e)
                mapped = {"transient": "transient", "policy": "policy"}.get(
                    kind, "invalid")
                result = ToolResult.failure(str(e), mapped)
            elapsed = time.time() - started
            if result.ok and elapsed > spec.timeout_s:
                # A slow SUCCESS stands (round-3): the old code rewrote
                # it to a transient timeout and RETRIED, re-executing a
                # side-effecting tool up to 3x for work that had already
                # completed. A synchronous call cannot be un-executed;
                # the overrun is recorded in the audit instead.
                record["timeout_exceeded"] = round(elapsed, 3)
            if result.ok or result.error_kind != "transient" or attempt >= self.retry.max_retries:
                record["result"] = "ok" if result.ok else f"{result.error_kind}: {result.error}"
                record["attempts"] = attempt + 1
                self.audit.append(record)
                return result
            attempt += 1
            delay = self.retry.delay(attempt)
            if delay:
                time.sleep(delay)


def identity_veto(ctx: RunContext, tool: str, args: dict) -> Optional[dict]:
    """The ADK-callback pattern from Gulli Ch 18: a tool may not act on a
    user_id different from the session identity."""
    if "user_id" in args and args["user_id"] != ctx.user_id:
        return {"error": "tool argument user_id does not match session identity"}
    return None
