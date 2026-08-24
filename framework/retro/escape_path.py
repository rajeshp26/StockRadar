#!/usr/bin/env python3
"""Escape path analyser.

Given where a defect was INJECTED and where it was CAUGHT, compute which checkpoints the
defect passed through. That set is the framework's failure, and it is arithmetic — not an
opinion an agent can talk itself out of.

For each escaped checkpoint it classifies the failure as exactly one of:

  routing_gap      the checkpoint would have caught this class, but was not ACTIVE
                   (impact class or requirement shape never triggered it)
                   -> fix the routing, not the check
  containment_miss the checkpoint WAS active and did not catch it
                   -> fix the check
  not_applicable   the checkpoint does not catch this defect class at all
                   -> no finding; recording one would be noise

Exit codes:
  0  analysis complete, at least one actionable gap identified
  1  bad input (unknown phase, unknown defect class)
  4  no actionable gap — defect was caught at the first checkpoint that could catch it
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP = HERE / "containment_map.yaml"


def _load() -> dict:
    try:
        import yaml
    except ImportError:
        # A missing parser must not read as "no gaps". Refuse loudly.
        print(json.dumps({"error": "BLOCKED: pyyaml required for escape path analysis",
                          "remedy": "pip install pyyaml"}), file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(MAP.read_text())


def _active(cp: dict, ctx: dict) -> bool:
    """Was this checkpoint active for the task's classification?"""
    cond = cp.get("active_when")
    if not cond:
        return True
    if cond.get("always"):
        return True
    for key, want in cond.items():
        got = ctx.get(key.removeprefix("or_"))
        if isinstance(want, list):
            if got in want:
                return True
        elif got == want:
            return True
    return False


# ── Lesson destination ───────────────────────────────────────────────────────────
# A retrospective produces a lesson. WHERE the lesson goes decides whether it changes
# anything. Ranked most-enforceable first — a lesson lands at the highest tier that can
# express it, never a lower one for convenience.
#
#   executable_check  a gate asserts it            -> exit code
#   declared_rule     a rule file declares it      -> gate reads the declaration
#   design_checklist  a judgement question at      -> recorded disposition (weakest)
#                     design time, before code
#   accepted          prevention costs more than   -> ledger note
#                     recurrence
#
# The checklist tier is deliberately hard to reach. It exists ONLY because the Architect's
# output is a decision with no artefact to execute against. Implementation, review, and
# testing lessons resolve to checks and skill rules, so they never route here — replacing an
# exit code with an unverifiable claim is a downgrade, not a process.

CHECK_TARGETS = {"gate_check", "gate_routing", "validation_check", "contract_tightening",
                 "requirement_shape", "evidence_mapping", "retry_policy"}
RULE_TARGETS = {"architecture_boundary", "skill_rule"}


def destination(matched: list[str], injected: str, unmapped: bool = False) -> dict:
    """Classify where the lesson belongs, and justify anything weaker than a check."""
    if unmapped:
        # No mapped target closes this gap. That is NOT the same as accepting the risk:
        # accepting means a change would not pay for itself, whereas unmapped means the map has
        # no row for this combination. Conflating them silently converts a missing row into a
        # deliberate decision, and the row never gets added.
        return {
            "tier": "unmapped_combination",
            "why": ("no fix target in containment_map.yaml closes this gap for this "
                    "(injection_phase, defect_class) pair — adding the row IS the fix"),
            "file": "framework/retro/containment_map.yaml",
            "not_accepted": ("do not record this as accepted risk; an absent map row is a gap "
                             "in the retrospective machinery, not a decision"),
        }
    if any(t in CHECK_TARGETS for t in matched):
        tier = "executable_check"
        why = "a gate or routing table can assert this; it needs no human judgement at design time"
    elif any(t in RULE_TARGETS for t in matched):
        tier = "declared_rule"
        why = "expressible as a declared rule that an existing gate already reads"
    elif "agent_instruction" in matched:
        if injected == "architecture":
            tier = "design_checklist"
            why = ("the defect was injected at design time, where no artefact exists for a gate "
                   "to execute against — the only condition under which a checklist item is "
                   "justified")
        else:
            tier = "agent_instruction"
            why = ("instruction text for a non-architecture phase. Prefer a check: if this "
                   "lesson cannot be made executable, it is probably too vague to act on")
    else:
        tier = "accepted"
        why = "no framework change would catch this without unacceptable false positives"

    out = {"tier": tier, "why": why}
    if tier == "design_checklist":
        out["admission_test"] = [
            "is a QUESTION requiring judgement, not a condition a gate could assert",
            "applies at design time, before code exists",
            "traces to this retro id",
            "no target ranked above agent_instruction can express it",
        ]
        out["file"] = "framework/architecture/design_checklist.yaml"
        out["ceiling"] = ("max_items is enforced; adding an item requires retiring one. An "
                          "unbounded checklist dilutes the items that matter.")
    return out


def analyse(injected: str, caught: str, defect_class: str, ctx: dict) -> dict:
    doc = _load()
    cps = doc["checkpoints"]
    ids = [c["id"] for c in cps]

    # Injection phase maps to the checkpoint that OWNS that phase.
    phase_to_cp = {
        "requirements": "requirements", "research": "research",
        "architecture": "architecture", "planning": "planning",
        "implementation": "implementation", "test_design": "planning",
        "framework": "implementation",
    }
    start_id = phase_to_cp.get(injected)
    if start_id is None:
        return {"error": f"unknown injection phase: {injected}",
                "valid": sorted(phase_to_cp)}
    if caught not in ids:
        return {"error": f"unknown caught-at checkpoint: {caught}", "valid": ids}

    known = {d for c in cps for d in c.get("catches", [])}
    if defect_class not in known:
        return {"error": f"unknown defect class: {defect_class}", "valid": sorted(known)}

    start, end = ids.index(start_id), ids.index(caught)
    if end <= start:
        return {"error": "caught-at precedes injection — check inputs",
                "injected_at": start_id, "caught_at": caught}

    escaped, routing, containment = [], [], []
    for cp in cps[start + 1:end]:
        catches = cp.get("catches", [])
        if defect_class not in catches:
            escaped.append({"checkpoint": cp["id"], "owner": cp["owner"],
                            "classification": "not_applicable"})
            continue
        act = _active(cp, ctx)
        kind = "containment_miss" if act else "routing_gap"
        rec = {"checkpoint": cp["id"], "owner": cp["owner"], "classification": kind,
               "active": act, "artefact": cp.get("artefact")}
        if not act:
            rec["inactive_because"] = cp.get("active_when")
        escaped.append(rec)
        (containment if act else routing).append(cp["id"])

    actionable = bool(routing or containment)
    # Routing gaps outrank containment misses: activating an existing gate is cheaper and more
    # reliable than making an active gate smarter.
    primary = ("routing_gap" if routing else "containment_miss" if containment else "none")

    prefer = doc["preferred_fix"].get(injected, {}).get(defect_class, ["none_human_judgement"])
    ft = doc["fix_targets"]
    # A target that does not close the PRIMARY gap is not a candidate for it. Recommending
    # `contract_tightening` (closes containment_miss) for an inactive gate would leave the
    # routing gap open and look productive doing it.
    matched = [t for t in prefer if primary in ft.get(t, {}).get("closes", [])]
    if not matched:
        # No mapped target closes the primary gap. Do NOT dump every target that closes it —
        # a seven-item candidate list is noise, and noise is how a retrospective becomes a
        # box-tick. Report the gap as unmapped so the map gets a row, which is itself the fix.
        matched = ["none_human_judgement"]
        unmapped = True
    else:
        unmapped = False
    other = [t for t in prefer if t not in matched]
    targets = [{"target": t, "addresses": primary, **ft.get(t, {})} for t in matched]
    secondary = [{"target": t, "addresses": "secondary", **ft.get(t, {})} for t in other]
    dest = destination(matched, injected, unmapped)
    return {
        "injected_at": start_id,
        "caught_at": caught,
        "defect_class": defect_class,
        "classification_context": ctx,
        "checkpoints_traversed": len(escaped),
        "escaped": escaped,
        "routing_gaps": routing,
        "containment_misses": containment,
        "actionable": actionable,
        "primary_gap": primary,
        "candidate_fix_targets": targets,
        "secondary_fix_targets": secondary,
        "unmapped_combination": unmapped,
        "destination": dest,
        "constraint": ("A recommendation must name one target from candidate_fix_targets, or "
                       "none_human_judgement with a reason. Prose recommendations are rejected."),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compute defect escape path")
    ap.add_argument("--injected", required=True,
                    help="requirements|research|architecture|planning|implementation|test_design|framework")
    ap.add_argument("--caught", required=True, help="checkpoint id where the defect surfaced")
    ap.add_argument("--defect-class", required=True)
    ap.add_argument("--scope", default="local")
    ap.add_argument("--complexity", default="L1")
    ap.add_argument("--contract-change", action="store_true")
    ap.add_argument("--data-change", action="store_true")
    ap.add_argument("--frontend", action="store_true")
    ap.add_argument("--shape", default="")
    a = ap.parse_args()

    ctx = {"scope": a.scope, "complexity": a.complexity,
           "contract_change": a.contract_change, "data_change": a.data_change,
           "frontend_files_changed": a.frontend}
    if a.shape:
        ctx["requirement_shape"] = a.shape

    out = analyse(a.injected, a.caught, a.defect_class, ctx)
    print(json.dumps(out, indent=2))
    if "error" in out:
        sys.exit(1)
    sys.exit(0 if out["actionable"] else 4)
