# StockerPro

This repository holds exactly two projects.

| Project | Path | What it is |
|---|---|---|
| **StockerPro** | `backend/`, `web/`, `mobile/` | The product: FastAPI backend, Next.js web app, Flutter mobile app. |
| **Agentic Lifecycle Framework** | `framework/` | The agentic engineering lifecycle: agents, skills, gates, adapters, and the agent-immutable enforcement plane. |

Nothing else lives at the repository root except the files both projects share:
`.gitignore`, `.gitattributes`, `.github/`, `.devcontainer/`, `.idx/`, and the packaging
inputs (`pyproject.toml`, `MANIFEST.in`, `requirements-framework.txt`).

## StockerPro

- `backend/` — FastAPI service, data ingestion, Supabase orchestration, domain logic.
- `web/` — Next.js 15 front end (App Router, shadcn/ui, Tailwind).
- `mobile/` — Flutter 3.22 app.

Documentation lives with its owner: `backend/docs/`, `web/docs/`, `mobile/docs/`.

The black-box system suite the framework verifier authors and freezes (DID-017) lives in
`backend/tests/system/`; the Playwright browser specs live in `web/e2e/`. `backend/tests/README.md`
describes every test layer and how to run it.

The backend runs inside its Nix environment:

```bash
nix-shell backend/shell.nix --run 'bash backend/start.sh'
```

## Agentic Lifecycle Framework

- `framework/` — framework source: gates, adapters, contracts, skills, verifier, plan and
  testing harnesses.
- `framework/docs/` — framework documentation.
- `framework/design/skills/` — advisory design-skill corpus read by the `ui-designer` agent.
- `framework/reference-app/` — the framework-owned reference application that
  `framework/standalone_check.py` builds against (the only proof an installed wheel binds to a
  consumer app).

The framework binding for this repository is `AGENTS.md`, `opencode.json`, and
`framework.config.json`; together with `framework/opencode/**` they form the enforcement
plane, which is immutable to agents and changes only through a human-applied patch.
`.lifecycle/` holds the lifecycle charters that `framework init` materialises into an
application repository, so it also stays at the root.

## Packaging

`pyproject.toml`, `MANIFEST.in`, and `requirements-framework.txt` build the
`agentic-lifecycle` distribution. Install the framework with `pip install .`; run its CLI
with `framework`.
