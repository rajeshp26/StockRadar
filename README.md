# StockRadar

StockRadar is a stock portfolio tracking and research app. It consists of a FastAPI
backend and a Next.js web front end, backed by Supabase.

## Repository layout

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI service: data ingestion, Supabase orchestration, domain logic, schedulers and background workers. |
| `web/` | Next.js 15 front end (App Router, shadcn/ui, Tailwind). |

The remaining top-level entries are development tooling: `.devcontainer/` and `.idx/`
for cloud/container development, `.github/workflows/` for CI, and `tasks.py`, a small
runner for the backend checks and migrations.

Documentation lives with its owner: `backend/docs/` and `web/docs/`.
`backend/tests/README.md` describes the backend test layers, and the Playwright browser
specs live in `web/e2e/`.

## Running locally (Windows)

Prerequisites: Docker Desktop, WSL with the project Python virtualenv, the Supabase CLI,
and Node.js/npm. From the repository root:

```powershell
.\backend\scripts\dev-setupfinal.ps1
```

The script starts Supabase in Docker, the backend on `http://127.0.0.1:8001`, the web app
on `http://localhost:3000`, and the scheduler worker. Leave the terminal open; Ctrl+C
stops the stack. Optional switches: `-SkipCleanup` (keep existing processes) and
`-SkipNetworkCheck` (diagnostic only — the backend cannot start without WSL egress).

## Backend

Common checks from the repository root:

```bash
python tasks.py                          # lint changed files, then the unit suite
python tasks.py lint                     # ruff on Python files changed vs HEAD
python tasks.py test                     # unit suite (no live stack required)
python tasks.py db-check                 # integration tests against a live stack
python tasks.py migrate <file.sql>       # apply one SQL migration, idempotently
```

## Web

From `web/`:

```bash
npm install
npm run dev                              # http://localhost:3000
npm run check                            # lint, format check, typecheck and unit tests
npm run build                            # production build
npm run test:e2e                         # Playwright browser specs
```
