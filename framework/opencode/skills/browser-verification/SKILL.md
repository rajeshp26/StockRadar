---
name: browser-verification
description: Prove visible behaviour with a real browser. Use when a requirement concerns visual alignment, an interaction flow, responsive layout, or console cleanliness — anything a unit test cannot demonstrate. Covers Playwright specs, the G6 gate, and the Playwright MCP tools.
---

# Browser verification

A unit test cannot prove a button is aligned or that a flow works. Per
`framework/opencode/rules/evidence.md`, visible-behaviour requirements need browser evidence, and
reasoning is not a substitute.

## The gate

```bash
bash framework/gates/g6_browser.sh
```

Exit codes, and this distinction is the whole point:

| Exit | Meaning | What you may claim |
| --- | --- | --- |
| 0 | specs ran and passed | requirement verified |
| 1 | specs ran and failed | requirement violated |
| 3 | UNVERIFIABLE — no driver, no config, or no specs | **nothing** |

Exit 3 is deliberately not 0. Report the requirement as unproven and name what is missing.
Never round an unverifiable result up to a pass.

## Writing assertions that mean something

Assert measurable facts, not impressions.

- Alignment: compare `boundingBox()` gaps against the viewport, with a stated tolerance.
- Responsive: branch on `page.viewportSize()`, and assert a different expectation per width.
- Console: collect `console` errors and `pageerror`, then assert the array is empty.
- Prefer `getByTestId` / roles over CSS selectors, so a class rename does not fake a failure.

See `framework/reference-app/tests/e2e/session-card.spec.ts` for the pattern, and the
application's own specs under `web/e2e/`.

## Playwright MCP

The `playwright` MCP server is available for exploration and diagnosis — navigating, clicking,
reading the accessibility tree, capturing screenshots. It is configured `--headless
--isolated --caps=testing`.

Use MCP to author or debug a spec. Do not use it as the evidence itself: MCP output is a
transcript in a conversation, and OpenCode prunes tool output. Committed specs plus the G6
exit code are the durable artefact. Author with MCP, then verify with the gate.

## Artefacts

Screenshots and traces land in `framework/telemetry/browser/artifacts/`, the run log in
`last-run.txt`. Reference these paths in the handoff so the evidence outlives the session.
