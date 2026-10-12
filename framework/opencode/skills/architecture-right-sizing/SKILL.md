---
name: architecture-right-sizing
description: Select the design effort a change deserves (Scan, Focus, or Full) from scope evidence instead of habit. Use when planning or reviewing a change that touches multiple modules, introduces a new boundary or interface, or where the previous design depth was chosen by convention. Complements technical-validation by sizing the design work; technical-validation then resolves the unknowns that design uncovers.
---

# Architecture Right-Sizing

Design depth selected by habit produces two failures: over-design on contained changes
(latency, review noise) and under-design on boundary changes (rework, integration
surprise). Effort must be **selected from scope evidence**, not inherited from the last
task.

## The three tiers

| Tier | Scope evidence | Design output expected |
| --- | --- | --- |
| **Scan** | Single module, local impact, no contract or boundary touched | Confirm the fit with the existing architecture; no new design document |
| **Focus** | 3+ modules involved, cross-component data flow, or one contract boundary | Explicit side-effect analysis and contract impact list; a short design note if the flow is non-obvious |
| **Full** | New boundary or service interface, public API change, or security-sensitive design | Formal design (alternatives, trade-offs, risk assessment) matching `software-architecture-design` |

## Promotion rule

Promote the tier when scope evidence expands **during** design, never demote:

- 3+ modules become involved → Scan becomes Focus
- A new boundary or interface appears → Focus becomes Full
- A reviewer question cannot be answered from the current tier's output → redo at the
  next tier before proceeding

Demotion is only allowed when the evidence that justified the higher tier was
disproven, and the reason must be recorded.

## Anti-patterns

- **Habit depth** — applying the previous task's depth to this task.
- **Tick-box depth** — producing a Full design for a Scan change to "look thorough".
- **Silent scope growth** — finishing design at one tier while the implementation grew
  to require the next; promotion happens at design time, not after rework.
- **Checklist-itis** — this skill is not a gate and has no exit checklist; the output of
  the tier is the design review input.

## Relationship to technical-validation

Right-sizing and `technical-validation` work in sequence, not in parallel:

1. Right-sizing selects the tier from scope evidence.
2. Technical-validation resolves the material unknowns the design exposes, using its
   evidence hierarchy (repo → docs → experiment → POC → explicit assumption).

A material assumption surfaced at any tier is resolved through technical-validation;
right-sizing never substitutes evidence, it only sizes the effort to find it.