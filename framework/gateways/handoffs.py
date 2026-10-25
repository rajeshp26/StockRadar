"""Handoffs + Pattern 15, A2A (Lanham Ch 4; Gulli Ch 15).

Inter-agent transfer is a control-plane event: a typed payload validated
against the target's input contract, both sides traced, eligibility and
loop checks (identity change + iteration caps) applied first. Cross-process
agents sit behind the same boundary using Agent Cards and the task
lifecycle; here the registry is in-process."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class AgentCard:
    """The A2A identity/contract artefact, in miniature."""
    name: str
    description: str
    skills: list[str]
    streaming: bool = False
    auth: list[str] = field(default_factory=lambda: ["apiKey"])


@dataclass
class HandoffRequest:
    from_agent: str
    to_agent: str
    task: str
    payload: dict
    iterations: int = 0
    chain_id: str = ""  # thread result.chain_id to link a handoff chain


@dataclass
class HandoffResult:
    ok: bool
    output: Optional[str] = None
    error: Optional[str] = None
    chain_id: str = ""  # pass into the next request of the same chain


AgentFn = Callable[[str, dict], str]


@dataclass
class AgentRegistry:
    cards: dict[str, AgentCard] = field(default_factory=dict)
    handlers: dict[str, AgentFn] = field(default_factory=dict)
    requires: dict[str, set[str]] = field(default_factory=dict)  # payload keys
    payload_types: dict[str, dict[str, type]] = field(default_factory=dict)
    max_handoffs: int = 10
    log: list[HandoffRequest] = field(default_factory=list)
    # Every attempt — accepted, rejected, or crashed — leaves a trace
    # entry (round-3: rejections used to leave nothing, and a handler
    # crash looked exactly like a success).
    trace: list[dict] = field(default_factory=list)
    _chains: dict[str, int] = field(default_factory=dict)

    def register(self, card: AgentCard, handler: AgentFn,
                 required_payload_keys: Optional[set[str]] = None,
                 required_payload_types: Optional[dict[str, type]] = None,
                 *, replace: bool = False) -> None:
        if isinstance(card.skills, str) or not isinstance(
                card.skills, (list, tuple, set)):
            # A bare-string skills field silently degraded discover()
            # to substring matching (round-3 minor).
            raise ValueError("AgentCard.skills must be a list of skill names")
        if card.name in self.handlers and not replace:
            # Silent re-registration used to overwrite the handler AND
            # drop the payload contract (round-3). Replacement must be
            # an explicit act.
            raise ValueError(
                f"agent '{card.name}' already registered; "
                "pass replace=True to overwrite deliberately")
        self.cards[card.name] = card
        self.handlers[card.name] = handler
        self.requires[card.name] = required_payload_keys or set()
        self.payload_types[card.name] = required_payload_types or {}

    def discover(self, skill: str) -> list[AgentCard]:
        return [c for c in self.cards.values() if skill in c.skills]

    def handoff(self, req: HandoffRequest) -> HandoffResult:
        import uuid
        chain = req.chain_id or uuid.uuid4().hex[:8]
        def done(ok: bool, output: Optional[str] = None,
                 error: Optional[str] = None) -> HandoffResult:
            self.log.append(req)
            self.trace.append({"from": req.from_agent, "to": req.to_agent,
                               "task": req.task, "ok": ok, "error": error,
                               "chain_id": chain})
            return HandoffResult(ok, output=output, error=error,
                                 chain_id=chain)
        # The loop cap is enforced against the registry's own chain
        # count, not caller honesty alone (round-3): thread chain_id
        # through a chain and the count is real. (A caller that mints a
        # fresh chain per call is indistinguishable from independent
        # calls — stated plainly rather than pretended away.)
        prior = self._chains.get(chain, 0)
        if max(req.iterations, prior) >= self.max_handoffs:
            return done(False, error="handoff loop cap reached")
        if req.to_agent not in self.handlers:
            return done(False, error=f"unknown agent '{req.to_agent}'")
        if not isinstance(req.payload, dict):
            return done(False, error="payload must be an object (dict)")
        missing = self.requires[req.to_agent] - set(req.payload)
        if missing:
            return done(False, error=f"payload missing keys: {sorted(missing)}")
        for key, typ in self.payload_types.get(req.to_agent, {}).items():
            if key in req.payload:
                v = req.payload[key]
                # bool is an int subclass: True is not a valid int here.
                if not isinstance(v, typ) or (typ is int and isinstance(v, bool)):
                    return done(False, error=(
                        f"payload key '{key}' must be {typ.__name__}, "
                        f"got {type(v).__name__}"))
        self._chains[chain] = prior + 1
        try:
            out = self.handlers[req.to_agent](req.task, req.payload)
        except Exception as e:
            # Handler crashes stay inside the envelope (round-3).
            return done(False, error=f"handler for '{req.to_agent}' raised: {e}")
        return done(True, output=out)
