# Frontend stack enforcement

Three files, one job: make the mandated stack an executable gate instead of a style guide.

| File | Role |
| --- | --- |
| `../frontend_stack.yaml` | The contract. Required tier, conditional tier, mechanical file rules. |
| `stack_check.py` | The checker. Exit 0 pass, 1 violation, 2 blocked, 4 not-applicable. |
| `effect_justifications.yaml` | The ledger permitting Magic UI, Aceternity, GSAP, R3F. |
| `../gates/g5_frontend_stack.sh` | Gate wrapper mapping exit codes to gate semantics. |
| `../gates/g6_browser.sh` | Browser verification. Exit 3 = unverifiable, never pass. |

## Why ratchet, not sweep

Required tools are enforced, but only on files the current task changed. A brownfield repo has
pre-existing violations; blocking on those produces a permanently red gate that teams learn to
route around. Baseline debt is reported and recorded, never blocking.

Record known debt in `baseline.json` as `{"path/to/file.tsx:rule_id": "reason"}`.

## Escape hatches

Mechanical rules accept an inline waiver, which must carry a reason:

```tsx
<div style={{ transform: `translateX(${x}px)` }} /> {/* stack-allow: inline-style — computed */}
```

There is no escape hatch for `motion_import_path`. `framer-motion` is the deprecated alias;
the project standardises on `motion/react`.

## Conditional tools

An empty ledger means conditional tools are not permitted. That is the correct default:
permission is granted per requirement, not once per repository. Each entry needs `tool`,
`requirement`, `scope`, `justification`, `approved_by`. GSAP additionally needs
`motion_insufficient_because` — a measured reason, not a preference.

Scope is enforced. A tool approved for onboarding that appears in billing fails the gate.

## Verified behaviour

Eleven scenarios, each confirmed to produce the right exit code:

| Scenario | Result |
| --- | --- |
| `react-icons` added | FAIL — forbidden alternate |
| `lucide-react` removed | FAIL — required tool absent |
| `framer-motion` import path | FAIL — wrong import |
| GSAP, empty ledger | FAIL — no justification |
| GSAP, ledger missing `motion_insufficient_because` | FAIL — incomplete entry |
| GSAP, complete ledger entry | PASS |
| GSAP outside approved scope | FAIL — scope violation |
| inline style + raw `<button>` | FAIL — two findings |
| one viewport configured | FAIL — responsive unprovable |
| `iconLibrary: heroicons` | FAIL — shadcn config mismatch |
| clean | PASS |

Note the ninth: naive keyword counting scored a single project as two viewports because
`devices[...]` and `viewport:` both matched. The checker counts distinct project widths.
