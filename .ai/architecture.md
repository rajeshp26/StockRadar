# Architecture

## System Overview

Decoupled Bridge Architecture:
```
Browser (Next.js) <-> API Proxy (Port 9002) <-> FastAPI Backend (Port 8001) <-> Supabase / yfinance
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15, React 19, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Database | Supabase (PostgreSQL) |
| Auth | Firebase (migrating to Supabase Auth) |
| Mobile | Flutter 3.22, Riverpod |
| Testing | pytest, httpx, Playwright |

## Backend Layered Architecture (SOLID)

```
backend/
├── api/            # FastAPI routers, Pydantic schemas, Depends injection
├── application/    # Use cases, service orchestration
├── domain/         # Abstract interfaces, business entities
└── infrastructure/ # Concrete repos, yfinance, Supabase client
```

**Rule**: Business logic never calls database drivers directly. Use Repository pattern.

## Key Patterns

- **Dependency Injection**: Factory functions with FastAPI `Depends`
- **Repository Pattern**: Abstract data access in `domain/interfaces/`
- **Strategy Pattern**: Interchangeable algorithms (e.g., portfolio pricing)
- **Bridge Pattern**: Next.js proxies requests to Python backend

## Frontend Organization

Feature-based structure: `features/watchlists`, `features/stocks`, etc.

## Ports

- Backend: `localhost:8001` (API docs at `/docs`)
- Frontend: `localhost:9002` (auto-proxies to backend)
