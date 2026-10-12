---
name: retrospective
version: 2
description: >
  Analyse a defect escape and identify the framework gap that allowed it. Load when a defect
  is found after the change that introduced it was accepted - a previously-green test failing,
  a review rejection, a reopened task, an integration failure, or a production defect.
  Also load when a human corrects an agent's understanding (human-correction path).
---

# Retrospective

The defect is already fixed by the time you run. Your subject is not the defect. Your subject
is **the framework that let it through**.

Three questions, in order:

1. Where was the defect **injected** - requirements, research, architecture, planning,
   implementation, or test design?
2. Which checkpoints did it **pass through** before it was caught?
3. What is the **earliest point** in the lifecycle at which this defect could reasonably
   have been prevented?

Question 2 is arithmetic, not judgement. Compute it:

```bash
python3 framework/retro/escape_path.py \
  --injected architecture --caught production \
  --defect-class contract_mismatch \
  --scope component --complexity L2 [--contract-change] [--frontend] [--shape visible_behaviour]
```

Pass the task's **original** classification, not a corrected one. The question is what the
framework did with the classification it had.

## Read the output

Each escaped checkpoint is classified as exactly one of:

| Classification | Meaning | Where the fix goes |
| --- | --- | --- |
| `routing_gap` | The checkpoint catches this class but was not active | The routing, not the check |
| `containment_miss` | The checkpoint was active and missed it | The check itself |
| `not_applicable` | The checkpoint never catches this class | Nowhere - record no finding |

**Routing gaps outrank containment misses.** Activating a gate that already exists is cheaper
and more reliable than making an active gate smarter. If G6 never ran because the requirement
had no `visible_behaviour` shape, the fix is the shape - not a better Playwright assertion.

## Counterfactual analysis (Question 3)

For every significant defect, answer:

> **What is the earliest point in the lifecycle at which this defect could reasonably
> have been prevented?**

Then:

> **What evidence or control was available at that point?**

Then:

> **Why did that control fail?**

This produces a gap classification:

| Gap type | Meaning | Example fix |
| --- | --- | --- |
| Knowledge | Agent did not know something | Research finding, knowledge artifact |
| Reasoning | Agent had info but failed to reason about it | Skill improvement |
| Skill | Methodology did not require the analysis | Skill rule update |
| Routing | Correct skill existed but was not invoked | Routing rules |
| Tool-use | Correct tool existed but was not used | Tool selection rules |
| Validation | Workflow did not adequately validate | Gate or evidence rules |
| Gate/workflow | Entire lifecycle allowed the problem through | Impact classification, gate rules |

### When to run counterfactual analysis

Always trigger for:

* production defects
* data loss or security issues
* framework gaps (retro itself missed something)

Trigger if rework was required for:

* test failures on previously-green code
* review rejections
* integration failures

Skip for:

* trivial typos or formatting
* comment fixes
* changes that were caught at the first capable checkpoint (the framework working)

### Recording the counterfactual

Add these fields to the ledger entry:

```json
{
  "counterfactual": {
    "earliest_prevention_point": "architecture",
    "evidence_available": "database schema was visible in existing code",
    "why_control_failed": "architecture skill did not require production-scale analysis",
    "gap_type": "skill_gap"
  }
}
```

## Human-correction path

A human correction is a **parallel observation path**, not part of the defect escape flow.

When you (the user) tell the agent:

> "No, that is not how this system works."

or

> "You are misunderstanding the requirement."

or

> "That approach will not work because..."

that is a **human correction** - high-value evidence that the agent's model was wrong.

### Why this is separate from defect escapes

A human correction means the agent's understanding was incorrect, but the engineering
system may have prevented the error from becoming a defect. The correction is valuable
because it may reveal **latent reasoning or routing weaknesses before they produce
escaped defects**.

### How to record a human correction

```bash
python3 framework/retro/ledger.py append --json '{
  "task_id": "07-03",
  "type": "human_correction",
  "what": "agent assumed API was synchronous",
  "correction": "API is asynchronous, requires await",
  "gap_type": "knowledge",
  "phase": "architecture",
  "no_counterfactual": true
}'
```

Fields:

* `type`: always `"human_correction"`
* `what`: the agent incorrect understanding
* `correction`: what the correct understanding is
* `gap_type`: one of knowledge, reasoning, assumption
* `phase`: which phase the correction applied to
* `no_counterfactual`: always `true` (not a defect, just a correction)

Human corrections do **not** trigger counterfactual analysis. They are observations,
not escapes. But they are recorded in the same ledger for retrieval later.

## The recommendation must be falsifiable

Name exactly one target from `candidate_fix_targets`. Every target is a file you can change
and a check that can prove you changed it. If none applies, the answer is
`none_human_judgement` **with a reason** - that is a valid, respected outcome.

Rejected recommendations, without exception:

* "The reviewer should be more careful"
* "Add more tests"
* "Improve the architecture review process"
* "Better communication between agents"
* Anything that cannot fail

Each is unfalsifiable, so it cannot be verified, so it will not change behaviour. The gap
recurs and the ledger will say so.

## Record it

```bash
python3 framework/retro/ledger.py append --json '{
  "task_id": "05-01",
  "injected_at": "implementation",
  "caught_at": "production",
  "defect_class": "visible_behaviour_defect",
  "primary_gap": "routing_gap",
  "routing_gaps": ["gate_g6"],
  "containment_misses": [],
  "fix_target": "requirement_shape",
  "fix_landed": true,
  "fix_verified_by": "python3 framework/validate.py (exit 0)",
  "counterfactual": {
    "earliest_prevention_point": "requirements",
    "evidence_available": "requirement shape was absent",
    "why_control_failed": "no routing rule for visible_behaviour without shape",
    "gap_type": "routing_gap"
  }
}'
```

`fix_verified_by` is a **command and its exit code**. "Updated the docs" is not verification.
A fix marked landed without it fails G7.

## Recurrence means your last fix did not work

The ledger matches on structural signature - injection phase, defect class, primary gap,
escaped checkpoints - deliberately ignoring the task id and your prose. A rephrased finding
for the same structural gap is still the same gap. The second occurrence escalates to a human
with zero retries, because the framework has now demonstrated it cannot close this gap on its
own.

When you hit a recurrence, do not file a third variation of the same fix. Report that the
prior fix failed and say why you believe it failed.

## Scope discipline

One retrospective covers one escape. Do not bundle. Do not open findings against checkpoints
marked `not_applicable` - that is noise, and noise is how a retrospective becomes a box-tick.
