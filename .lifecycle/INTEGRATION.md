# INTEGRATION.md — binding to the existing framework

Spec version: 1.1 · Normative source: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §15

## 1. Two layers, one governance chain

The lifecycle is the **feature-engineering front end**. The existing 7-agent framework's G1–G6 remain the **executable enforcement layer**. The lifecycle adds evidence to them; it does not redefine them.

```
FEATURE LIFECYCLE (this pack)
  F0 qualification · F1–F5 requirements & test basis · F6–F11 design
  F12–F16 execution · F17 defect learning · trace.yml · baselines
        │
        │  supplies artifacts + baselines + immutable evidence
        ▼
EXISTING GATES (unchanged)
  G1 Contract · G2 Impact · G3 Architecture · G4 Executable · G5 Frontend · G6 Browser/HMI
        │
        ▼
LIFECYCLE GATES (additive)
  G0 · G0.5 · G3.5 · G7 · G8
        │
        ▼
HUMAN GATES (owned elsewhere)
  H1 Architecture approval · H2 Incompatible contract change · H3 Release approval
```

## 2. Rule of precedence

Where this pack's description of G1–G6 differs from the existing authoritative definition, **the existing definition wins**. Bind `external_gates.definitions_location` in `config.yml` to that authoritative location. Until it is bound, treat the G1–G6 checklists here as supplements, not as definitions.

The lifecycle owns exactly five gates: G0, G0.5, G3.5, G7, G8.

## 3. Inbound contracts to the human gates

The lifecycle guarantees the handover below. It asserts nothing about H-gate internals, quorum, or decision criteria.

### H1 — Architecture approval

| Lifecycle hands over | Source |
|---|---|
| Architecture description | `F8-architecture.md` |
| Detailed design | `F9-detailed-design.md` |
| Alternatives record (L3+) | `F8-architecture.md` §alternatives |
| State ownership register | `F6-decomposition.md` §ownership |
| Concurrency model | `F8-architecture.md` §concurrency |
| Reuse search records | `F8-architecture.md` §reuse |
| Ledger entries | `gates/G3.md` PASS, `gates/G3.5.md` PASS |
| Design baseline id | `trace.yml` `baselines[]` where `kind: design` |

H1 receives a design that has already survived G3 and G3.5. If either is FAIL or CONDITIONAL, the lifecycle does not hand over.

### H2 — Incompatible contract change

| Lifecycle hands over | Source |
|---|---|
| Contract diff, before and after | `F7-contracts/IFC-*.yml` or `EVT-*.yml`, both baselines |
| Baseline supersession record | `trace.yml` `changes[]` |
| Consumer impact set | `F10-impact-analysis.md` §reverse |
| Selected regression cases per impacted path | `trace.yml` `impacted_paths[]` |
| Ledger entries | `gates/G1.md`, `gates/G2.md` |

Trigger: a contract change that is not backward compatible, detected at F7 or discovered at F12. The Implementer charter forbids absorbing it in code.

### H3 — Release approval

| Lifecycle hands over | Source |
|---|---|
| Sealed evidence package with checksums | `evidence/` + manifest |
| G8 Part A readiness ledger | `gates/G8.md` §part-a |
| G8 Part B acceptance ledger and recommendation | `gates/G8.md` §part-b |
| Measured NFR values, not pass assertions | `evidence/F15-system/`, `evidence/F16-validation/` |
| Residual known limitations with customer impact | `gates/G8.md` §part-b |
| Open defect dispositions | `defects/DEF-*.md` |

G8 Part B emits `RECOMMEND_RELEASE`, `RECOMMEND_RELEASE_WITH_LIMITATIONS`, or `RECOMMEND_HOLD`. **H3 owns the accept-or-reject decision.** There is no G9.

## 4. What the lifecycle does not own

Release decisions, deployment, rollout sequencing, branch and merge policy, staffing, schedule commitments, and the internals of G1–G6 or H1–H3.

## 5. Installation order

1. Bind `commands`, `ui_surface`, `external_gates.definitions_location` in `config.yml`.
2. Add the §1.2 block to the host runtime entry file (`AGENTS.md` is provided).
3. Wire `scripts/orphan-check.py` and `scripts/lifecycle-validate.py` into CI beside the existing gate machinery.
4. Reconcile: if the existing framework already implements G1–G6 checks, mark the local checklists as supplements in review.
