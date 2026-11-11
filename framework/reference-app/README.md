# Reference application

A deliberately minimal consumer application, owned by the framework. It exists for exactly one
reason: **the installed wheel must be proved against an app that contains none of the framework.**

## Why this exists

`framework standalone` (`framework/standalone_check.py`) builds the wheel, installs it into a
throwaway virtualenv, stages *this* application into a scratch directory, runs `framework init`,
then `framework validate --profile app`.

A green `validate.py` inside the framework's own working tree is **not** evidence of
distribution. That tree imports from source and carries the framework surface next to the app, so
either one can mask a package-data file the wheel forgot to ship, or a path that only resolves
in-tree. The only run that can fail on those is one where the framework is an installed wheel and
the application holds none of the framework tree. This directory is that application.

## Contract: this directory must stay framework-free

Nothing in here may import from `framework/`, `.opencode/`, or `.lifecycle/`. That absence is the
test. If the fixture starts depending on the framework, the standalone proof becomes circular and
stops proving anything.

## Layout

```
src/frontend/           React surface (contract API-004 consumer)
src/backend/            boundary validation against the same contract
contracts/              the contract itself (staged into .planning/contracts by `framework init`)
tests/contract/         executable contract gate (runs standalone, no pytest required)
tests/e2e/              Playwright spec, three viewports
package.json            the app's own dependency manifest
vite.config.ts          Vite root; `@` alias resolves to src/frontend
tsconfig.json           TypeScript config for the same root
components.json         shadcn/ui manifest
playwright.config.ts    desktop / tablet / mobile projects
index.html              Vite entry
```

## What it is not

It is **not** the product. The product (StockerPro) lives in `backend/`, `web/`, and `mobile/`.
This fixture is not subject to G3 architecture boundaries, is not the app the frontend stack gate
judges in production, and must never be cited as evidence that product behaviour works.

The gates locate the real application through `framework.config.json` → `readiness` (see
`framework/locate.py`). This fixture is only used when staging for the standalone proof, and by
`framework validate --profile app` when run from the source repository.

## Running it directly

```bash
cd framework/reference-app
npm ci
npm run dev          # Vite dev server
npm run build        # tsc --noEmit + vite build (the type check is the JS-level check)
npm run lint         # eslint
npx playwright test  # three viewport projects
```

There is deliberately no `npm test`: this fixture has no JavaScript unit tests. Its executable
evidence is the contract test (`tests/contract/test_api_004.py`, run by G1), the type check in
`npm run build`, and the Playwright spec. The framework's own JS suites
(`framework/tools/run_tests.mjs`) are framework-owned and are run by G4 directly — a consumer
app must not be the thing that runs them.

`framework standalone` does not use this checkout directly — it stages a copy, so nothing here is
mutated by the proof.
