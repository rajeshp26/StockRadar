# Architecture design checklist

## Why this is the only checklist

Every gate tests an artefact — a diff, a schema, a build, a rendered page. The Architect's
output is a **decision**. No code exists yet, so there is nothing to execute a check against.
That is the one gap a checklist fills.

Implementation, review, and testing do **not** get checklists. Their lessons reduce to
conditions a gate can assert: "domain must not import transport" is a declared boundary G3
enforces; "use Lucide, not react-icons" is G5. Routing those here would replace an exit code
with an unverifiable claim — a downgrade, not a process.

## Admission test

An item may exist only if all four hold:

1. It is a **question requiring judgement**, not a condition a gate could assert.
2. It applies at **design time**, before code exists.
3. It traces to a **retro id** — a real escape, not a plausible worry.
4. No fix target ranked above `agent_instruction` can express it.

`checklist_check.py structure` rejects items that read like executable conditions.

## Disposition, not review

Loading the checklist is not compliance. The Architect returns a verdict per item:

| Verdict | Requires |
|---|---|
| `applied` | `changed` — what the item changed in the design |
| `not_applicable` | `reason` — why the precondition does not hold |
| `accepted_risk` | `reason` and `approved_by` |

There is no `reviewed` verdict. An item with no disposition is a gap, not a pass.

## Lifecycle

Items are not permanent. Unbounded growth does not make a checklist stricter — an agent spreads
attention across every item, so each addition dilutes the rest.

- **Expire.** Dispositioned `expiry_cycles` times without ever changing a design → retire.
- **Graduate.** Condition became machine-checkable → add `graduated_to: <gate>`, the gate owns it.
- **Ceiling.** `max_items` is enforced. Adding an item requires retiring one.

## Commands

```bash
python3 framework/architecture/checklist_check.py show
python3 framework/architecture/checklist_check.py structure
python3 framework/architecture/checklist_check.py dispositions --task 06-01
python3 framework/architecture/checklist_check.py lifecycle
```

## Enforcement

G3 fails when a disposition is owed and missing, or invalid. Owed only when the Team Lead sets
`ARCHITECTURE_TASK=1` — a gate that demands dispositions on a typo fix gets routed around, and a
gate that gets routed around enforces nothing.

```bash
RETRO_TASK=06-01 ARCHITECTURE_TASK=1 bash framework/gates/g3_architecture.sh
```
