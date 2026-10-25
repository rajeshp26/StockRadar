"""Guardrails — Pattern 18 (Gulli Ch 18; Lanham Ch 4/7/8).

Policy is code: structured verdicts (Pydantic-style validation), enforced
deterministically at the gateways — input screening before the model,
output checks before the user, and the tool-argument veto in the tool
gateway. Ambiguous model-judged cases escalate to a human by default."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class PolicyEvaluation:
    is_safe: bool  # invariant: is_safe == (risk_level == LOW)
    risk_level: RiskLevel
    categories: list[str] = field(default_factory=list)
    rationale: str = ""

    def __post_init__(self):
        # A real exception, not an assert: asserts are stripped under
        # `python -O`, which would silently drop the one guarantee this
        # class exists to provide (round-3).
        if self.is_safe != (self.risk_level == RiskLevel.LOW):
            raise ValueError(
                "invariant violated: is_safe must equal (risk_level == LOW)")


@dataclass
class GuardrailDecision:
    action: str  # allow | escalate | block
    evaluation: Optional[PolicyEvaluation] = None
    reason: str = ""


_INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|prior) instructions?",
    r"(disregard|forget) (all |the |your )?(previous|prior) instructions?",
    r"reveal (your|the) (system )?prompt",
    r"show me (your|the) (system )?prompt",
    r"you are now (a|an|dan)\b",
]


def _normalize_for_screen(text: str) -> str:
    """Normalise before matching (round-3): the raw patterns were evaded
    by double spaces, newlines, NBSP, zero-width characters, fullwidth
    letters and case-fold quirks (Turkish İ). NFKC + casefold + strip
    combining marks + collapse whitespace closes most of that class.
    Only the screening copy is normalised; the caller's text is untouched."""
    import unicodedata
    t = unicodedata.normalize("NFKC", text)
    t = "".join(c for c in t.casefold() if not unicodedata.combining(c))
    t = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", t)
    return re.sub(r"\s+", " ", t)


def screen_input(text: str) -> GuardrailDecision:
    """Deterministic first layer: known injection shapes are blocked, not
    negotiated with. Model-based layers run behind this one."""
    if not isinstance(text, str):
        raise TypeError("screen_input expects a string")
    low = _normalize_for_screen(text)
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, low):
            return GuardrailDecision(
                "block",
                PolicyEvaluation(False, RiskLevel.HIGH, ["prompt_injection"],
                                 f"matched injection pattern: {pat}"),
                "input blocked by deterministic screen",
            )
    return GuardrailDecision("allow", PolicyEvaluation(True, RiskLevel.LOW))


def adjudicate(evaluation: PolicyEvaluation,
               on_ambiguous: str = "escalate") -> GuardrailDecision:
    """Routing of verdicts: LOW passes; MEDIUM escalates or allows per the
    deployment's explicit choice (never a silent default); HIGH blocks
    and escalates for review; EXTREME is an incident."""
    if on_ambiguous not in ("allow", "escalate", "block"):
        # An unvalidated pass-through turned a typo ("banana") into a
        # decision action downstream (round-3).
        raise ValueError(
            f"on_ambiguous must be allow|escalate|block, got {on_ambiguous!r}")
    if evaluation.risk_level == RiskLevel.LOW:
        return GuardrailDecision("allow", evaluation)
    if evaluation.risk_level == RiskLevel.MEDIUM:
        return GuardrailDecision(on_ambiguous, evaluation, "ambiguous case")
    if evaluation.risk_level == RiskLevel.HIGH:
        return GuardrailDecision("block", evaluation, "high risk: blocked + review")
    return GuardrailDecision("block", evaluation, "extreme risk: incident")


PII_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
    # The canonical PII shapes (round-3: SSN and phone were missing
    # entirely and sailed through as allow/LOW).
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b|\b\d{3} \d{2} \d{4}\b",
    "phone": r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b",
    "iban": r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,6}(?: ?[A-Z0-9]{0,3})?\b",
}

_CARD_CANDIDATE = re.compile(r"\b(?:\d[ .-]*?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _has_card_number(text: str) -> bool:
    """Card detection with a Luhn check (round-3): the old bare regex
    escalated every 13-19 digit run — order ids, ISBNs, build numbers —
    as 'credit_card', while dotted card numbers evaded it entirely.
    Now: digit runs with space/dash/dot separators, 13-19 digits, and
    the number must actually be Luhn-valid."""
    for m in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


def check_output(text: str) -> GuardrailDecision:
    """Output-side check: PII leakage in generated text escalates."""
    if not isinstance(text, str):
        raise TypeError("check_output expects a string")
    found = [name for name, pat in PII_PATTERNS.items() if re.search(pat, text)]
    if _has_card_number(text):
        found.append("credit_card")
        # The phone pattern also matches 3-3-4 windows inside a card's
        # digit groups; a Luhn-valid card is a card, not also a phone.
        if "phone" in found:
            found.remove("phone")
    if found:
        return GuardrailDecision(
            "escalate",
            PolicyEvaluation(False, RiskLevel.MEDIUM, found, "PII in output"),
            f"PII categories present: {found}",
        )
    return GuardrailDecision("allow", PolicyEvaluation(True, RiskLevel.LOW))
