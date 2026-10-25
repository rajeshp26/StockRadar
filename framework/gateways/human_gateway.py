"""Human gateway — Pattern 13, Human-in-the-Loop (Gulli Ch 13; Lanham Ch 8).

Risk-based tiers decide what autonomy means per action: approve,
escalate, or notify. The queue is injectable: an approver is any callable
returning a decision, so UIs, CLIs, and tests all plug in the same way."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from skill_contracts.skill_spec import ToolSpec

TIER_POLICY = {
    # effect -> (low stakes, high stakes) behaviour
    "read": ("auto", "auto"),
    "write_internal": ("auto", "approve"),
    "external": ("approve", "escalate"),
}


@dataclass
class ApprovalRequest:
    action: str
    detail: str
    stakes: str = "low"  # low | high
    decision: Optional[str] = None  # approved | denied | escalated
    error: Optional[str] = None     # set when the approver misbehaved


Approver = Callable[[ApprovalRequest], str]


def auto_approver(req: ApprovalRequest) -> str:
    return "approved"


def deny_approver(req: ApprovalRequest) -> str:
    return "denied"


@dataclass
class HumanGateway:
    approver: Approver = auto_approver
    queue: list[ApprovalRequest] = field(default_factory=list)
    notifications: list[str] = field(default_factory=list)

    def required_for(self, spec: ToolSpec, stakes: str = "low") -> str:
        """Returns 'auto' | 'approve' | 'escalate' for a tool call."""
        if spec.effect not in TIER_POLICY:
            # A bare KeyError for an unknown effect tier helps no one
            # (round-3).
            raise ValueError(f"unknown effect tier {spec.effect!r}")
        if stakes not in ("low", "high"):
            # Every non-"low" value used to silently select the
            # high-stakes behaviour ("banana", "", "Low") — a typo
            # changed approval behaviour without a trace (round-3).
            raise ValueError(f"stakes must be 'low' or 'high', got {stakes!r}")
        return TIER_POLICY[spec.effect][0 if stakes == "low" else 1]

    def request(self, action: str, detail: str, stakes: str = "low") -> ApprovalRequest:
        req = ApprovalRequest(action, detail, stakes)
        # Queue FIRST (round-3): a raising approver used to lose the
        # request entirely — the action vanished without a record.
        self.queue.append(req)
        try:
            decision = self.approver(req)
        except Exception as e:
            req.decision = "escalated"  # broken approver -> human looks
            req.error = f"approver raised: {e}"
            return req
        if decision not in ("approved", "denied", "escalated"):
            # Unvalidated approver output ("maybe-later") used to be
            # stored as the decision, outside the documented vocabulary
            # downstream code switches on (round-3).
            req.decision = "escalated"
            req.error = f"approver returned invalid decision {decision!r}"
            return req
        req.decision = decision
        return req

    def notify(self, message: str) -> None:
        self.notifications.append(message)
