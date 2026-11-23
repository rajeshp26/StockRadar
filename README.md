# StockRadar

StockRadar is a stock portfolio tracking and research app. It consists of a FastAPI
backend, a Next.js web front end, and a Flutter mobile client, backed by Supabase.

## Repository layout

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI service: data ingestion, Supabase orchestration, domain logic, schedulers and background workers. |
| `web/` | Next.js 15 front end (App Router, shadcn/ui, Tailwind). |
| `mobile/` | Flutter 3.22 app. |

The remaining top-level entries are development tooling: `.devcontainer/` and `.idx/`
for cloud/container development, `.github/workflows/` for CI, and `tasks.py`, a small
runner for the backend checks and migrations.

Documentation lives with its owner: `backend/docs/`, `web/docs/`, `mobile/docs/`.
`backend/tests/README.md` describes the backend test layers, and the Playwright browser
specs live in `web/e2e/`.

## Backend

The backend runs inside its Nix environment:

```bash
nix-shell backend/shell.nix --run 'bash backend/start.sh'
```

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

## Mobile

From `mobile/`:

```bash
flutter pub get
flutter run
```
