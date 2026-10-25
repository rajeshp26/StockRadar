"""Pattern 5 — Tool Use, as a ReAct executor (Gulli Ch 5/17; Lanham Ch 5).

Thought -> Action -> Observation, executed through the tool gateway (never
directly), with the loop bounds the books insist on: max iterations, step
timeouts, and a mandatory finish action. The model speaks a tiny protocol:

    ACTION: <tool_name> {"arg": "value"}
    FINISH: <final answer>
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from gateways.tool_gateway import ToolGateway
from llm import LLM
from skill_contracts.skill_spec import RunContext, SkillSpec

_ACTION_HEAD = re.compile(r"ACTION:\s*(\w+)\s*")
_FINISH = re.compile(r"FINISH:\s*(.*)", re.S)
_DECODER = json.JSONDecoder()


def _first_directive(reply: str) -> tuple[str, object]:
    """Return ('finish', answer) | ('action', (name, args)) |
    ('error', observation) for the FIRST directive in the reply.

    Round-3 fixes: the old code searched FINISH anywhere first (a FINISH
    later in the reply silently pre-empted an earlier ACTION) and used a
    greedy \\{.*\\} for the arguments, so two ACTIONs in one reply fused
    into one invalid JSON blob and burned the whole iteration budget.
    Now: whichever directive starts first wins, and the arguments are
    exactly one JSON object, parsed with raw_decode (nested objects and
    trailing text are fine)."""
    act = _ACTION_HEAD.search(reply)
    fin = _FINISH.search(reply)
    if fin is not None and (act is None or fin.start() < act.start()):
        return "finish", fin.group(1).strip()
    if act is None:
        return "error", "Observation: protocol error — use ACTION or FINISH."
    brace = reply.find("{", act.end())
    if brace == -1:
        return "error", "Observation: invalid JSON arguments."
    try:
        args, _ = _DECODER.raw_decode(reply[brace:])
    except json.JSONDecodeError:
        return "error", "Observation: invalid JSON arguments."
    if not isinstance(args, dict):
        return "error", "Observation: invalid JSON arguments."
    return "action", (act.group(1), args)


@dataclass
class ReActResult:
    answer: str
    steps: int
    transcript: list[str] = field(default_factory=list)
    finished: bool = False


def run_react(llm: LLM, gateway: ToolGateway, ctx: RunContext,
              skill: SkillSpec, task: str) -> ReActResult:
    tools = gateway.tools_for(skill)
    tool_lines = "\n".join(f"- {t.name}: {t.description}" for t in tools) or "(none)"
    history = [f"Task: {task}\nTools:\n{tool_lines}\n"
               "Reply with 'ACTION: name {json}' or 'FINISH: answer'."]
    for step in range(1, skill.max_iterations + 1):
        reply = llm.complete("\n".join(history))
        history.append(reply)
        kind, payload = _first_directive(reply)
        if kind == "finish":
            return ReActResult(payload, step, history, finished=True)  # type: ignore[arg-type]
        if kind == "error":
            history.append(payload)  # type: ignore[arg-type]
            continue
        name, args = payload  # type: ignore[misc]
        result = gateway.call(ctx, skill, name, **args)
        obs = (f"Observation: {result.value}" if result.ok
               else f"Observation: error ({result.error_kind}): {result.error}")
        history.append(obs)
    return ReActResult("max iterations reached without FINISH",
                       skill.max_iterations, history, finished=False)
