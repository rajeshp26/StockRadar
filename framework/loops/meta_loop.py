"""The meta loop (Lanham Ch 9 layer 3; Gulli Ch 7 multi-agent).

The orchestrator holds the goal and the registry of skills; per task it
chooses delegate / answer directly / combine the team's work, replans on
delegation failure, and finalises by synthesising sub-results. Sub-agents
report results, never raw transcripts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..gateways.handoffs import AgentRegistry, HandoffRequest
from llm import LLM


@dataclass
class MetaLoop:
    llm: LLM
    registry: AgentRegistry
    name: str = "orchestrator"
    max_delegations: int = 6

    def _substitute(self, goal: str, task: str, failed: str) -> Optional[str]:
        """Ask the LLM for one substitute agent for a failed delegation."""
        others = [n for n in self.registry.cards if n != failed]
        if not others:
            return None
        reply = self.llm.complete(
            f"Goal: {goal}\nDelegation to agent '{failed}' for the task "
            f"'{task}' failed. Choose ONE substitute agent from: {others}. "
            "Reply with only the agent name.").strip()
        return reply if reply in others else None

    def run(self, goal: str, plan: list[tuple[str, str, dict]]) -> str:
        """plan: ordered (agent, task, payload) delegations chosen by the
        caller's planner. Executes them, replans once on failure by asking
        the LLM for a substitute agent, then synthesises."""
        if len(plan) > self.max_delegations:
            # Never silently truncate a plan (round-3): the caller must
            # be able to tell a full run from a cut one.
            raise ValueError(
                f"plan has {len(plan)} delegations; "
                f"max_delegations is {self.max_delegations}")
        # Results are an ordered list, not a dict keyed by agent name:
        # delegating to the same agent twice used to discard the first
        # result silently (round-3).
        results: list[tuple[str, str]] = []
        delegations = 0
        chain_id = ""  # thread the registry chain so its loop cap counts
        for agent, task, payload in plan:
            res = self.registry.handoff(HandoffRequest(
                from_agent=self.name, to_agent=agent, task=task,
                payload=payload, iterations=delegations, chain_id=chain_id))
            chain_id = res.chain_id or chain_id
            delegations += 1
            if not res.ok:
                # The docstring always promised this replan; the code
                # never did it (round-3). One substitute attempt.
                sub = self._substitute(goal, task, agent)
                if sub is None:
                    return f"Delegation to {agent} failed: {res.error}"
                res2 = self.registry.handoff(HandoffRequest(
                    from_agent=self.name, to_agent=sub, task=task,
                    payload=payload, iterations=delegations,
                    chain_id=chain_id))
                chain_id = res2.chain_id or chain_id
                delegations += 1
                if not res2.ok:
                    return (f"Delegation to {agent} failed: {res.error}; "
                            f"substitute {sub} also failed: {res2.error}")
                results.append((sub, res2.output or ""))
                continue
            results.append((agent, res.output or ""))
        brief = "\n\n".join(f"[{a}]\n{r}" for a, r in results)
        return self.llm.complete(
            f"Goal: {goal}\nSynthesise a final answer from these team "
            f"results only:\n\n{brief}")
