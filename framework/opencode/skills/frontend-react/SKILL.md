---
name: frontend-react
description: Implement or modify React UI in this repository. Use when the task touches src/frontend, components, styling, icons, animation, or any visible behaviour. Covers the mandated stack — shadcn/ui, Tailwind v4, Lucide, Motion — and the rules G5 enforces.
---

# Frontend React implementation

The stack is a contract, not a preference. `framework/frontend_stack.yaml` is the source of
truth and `framework/gates/g5_frontend_stack.sh` enforces it on changed files. Read the YAML
rather than trusting this summary if the two ever disagree.

## Design language

This skill covers the implementation stack only. The design system for this repo (dark glass finance UI: tokens in `tokens.css`, component/pattern/data-viz specs, accessibility and motion rules) lives in `apple-ui` — load it together with this skill on every UI task. It is a mandatory pairing, not an option.

## Required, no exceptions

| Concern | Tool | Notes |
| --- | --- | --- |
| Standard UI component | shadcn/ui | `npx shadcn@latest add <name>`. Never hand-roll a primitive that exists. |
| Styling | Tailwind v4 | Config lives in CSS via `@theme`. `components.json` `tailwind.config` stays empty. |
| Icons | `lucide-react` | Never inline an `<svg>` outside `components/ui/`. |
| Animation | `motion` | Import from `motion/react`. Not `framer-motion` — that alias is deprecated. |
| Browser testing | `@playwright/test` | Specs in `tests/e2e/`. |
| Responsive validation | Playwright projects | At least two distinct viewport widths. |

## Mechanical rules on files you touch

- No `style={{ ... }}`. Use Tailwind utilities. Escape hatch, only with a reason on the line:
  `// stack-allow: inline-style`
- No raw `<button>`, `<input>`, `<select>`, `<textarea>`, `<dialog>` outside
  `src/frontend/components/ui/`. Import the shadcn primitive.
- No inline `<svg>` outside `components/ui/`. Use a Lucide icon.

These are checked only on files the current task changed. Pre-existing violations elsewhere
are baseline debt — do not fix them opportunistically inside an unrelated task.

## Conditional tools

Magic UI, Aceternity, GSAP, and React Three Fiber require an entry in
`framework/frontend/effect_justifications.yaml` before they may appear. The entry must name a
requirement ID, a file scope, and an approver. GSAP additionally requires
`motion_insufficient_because` — a measured reason Motion cannot do the job, not a preference.

If you believe one of these is needed, stop and hand back to the Team Lead with the
requirement ID. Do not add the dependency and then request the justification.

## Contracts

Never redeclare a request or response type that a contract already defines. Import from
`src/frontend/contracts/`, which is generated. Those files carry a do-not-edit banner and G1
compares them against the schema — hand edits are detected as drift.

Transport code goes in a hand-authored sibling module (see
`src/frontend/features/auth/client.ts`), never inside the generated file.

## Definition of done for a UI task

Implementation is not done because the component renders. A visible-behaviour requirement
needs browser evidence: `bash framework/gates/g6_browser.sh`. If it reports UNVERIFIABLE,
the requirement is unproven — say so, do not report success.
