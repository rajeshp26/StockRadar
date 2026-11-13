# Project Architecture and Environment Guide

This document is the single source of truth for the StockerPro technical architecture.

## 1. System Topology

The system implements a **Decoupled Bridge Architecture**. Authentication is handled by Firebase, while persistent data resides in Supabase.

`Browser (Next.js)` <---> `API Proxy (Port 9002)` <---> `FastAPI Backend (Port 8001)` <---> `Supabase / yfinance`

### 1.1 The Secure Bridge (Next.js API Routes)
Located in `web/src/app/api/proxy/`, this layer serves three critical professional functions:
1.  **Identity Forwarding**: Extracts the Firebase JWT from the browser and injects it into the backend request.
2.  **CORS Management**: Eliminates cross-origin issues by keeping the Backend "private" to the frontend server.
3.  **Stream Piping**: Uses `ReadableStream` to pipe Server-Sent Events (SSE) from Python directly to the browser for low-latency price updates.

---

## 2. Backend Layered Architecture (SOLID)

The Python backend follows the **Hexagonal/Clean Architecture** principles to ensure maintainability.

| Layer | Path | Responsibility |
| :--- | :--- | :--- |
| **API** | `backend/api/` | FastAPI routers and Pydantic validation schemas. |
| **Application** | `backend/application/` | Orchestrates use cases (e.g., `WatchlistService`). |
| **Domain** | `backend/domain/` | Abstract interfaces and core business logic. |
| **Infrastructure** | `backend/infrastructure/` | Concrete implementations (Repositories, yfinance). |

### 2.1 Dependency Injection in FastAPI

To maintain the separation of concerns, the API layer is responsible for **injecting** concrete infrastructure implementations into the application services. This is done using a factory function with FastAPI's `Depends` system.

**Example from `backend/api/watchlists.py`:**

```python
from application.services.watchlist_service import WatchlistService
from infrastructure.repositories.supabase_repository import SupabaseUserRepository, SupabaseWatchlistRepository
from providers.yfinance_provider import YFinanceProvider
from database import supabase

# This function acts as a factory and dependency injector.
def get_watchlist_service() -> WatchlistService:
    # 1. Instantiate concrete repositories from the Infrastructure layer
    user_repo = SupabaseUserRepository(client=supabase)
    watchlist_repo = SupabaseWatchlistRepository(client=supabase)
    
    # 2. Instantiate the external service provider
    stock_provider = YFinanceProvider()
    
    # 3. Inject the dependencies into the Application service
    return WatchlistService(
        user_repo=user_repo, 
        watchlist_repo=watchlist_repo, 
        stock_provider=stock_provider
    )

# The endpoint uses Depends to get the fully constructed service.
@router.post("/watchlists/default-with-items")
def get_default_watchlist_with_items(
    service: WatchlistService = Depends(get_watchlist_service),
    # ...
):
    # ... service is now ready to use ...
```

This pattern ensures that the `WatchlistService` remains decoupled from the specific database or stock provider implementation, adhering to the Dependency Inversion Principle.

---

## 3. Environment and Operations

### 3.1 The Nix Environment

The entire project is designed to run within a Nix-based sandboxed environment. This ensures that all developers and deployment environments have the exact same system-level dependencies, eliminating "works on my machine" problems.

-   **Definition**: The environment is defined in the `backend/shell.nix` file.
-   **Activation**: To enter the environment, run `nix-shell backend/shell.nix` from the project root. **All development and operational scripts MUST be run from within this shell.**

### 3.2 Backend Operations

**Starting the Server:**
To start the backend server correctly, use the following command from the project root:

```bash
nix-shell backend/shell.nix --run 'bash backend/start.sh'
```

This command ensures the Nix environment is activated before executing the startup script.

**Stopping the Server:**
To stop the background server process, use the provided script:

```bash
bash backend/stop.sh
```

**Troubleshooting: "Address already in use"**
If the server doesn't shut down cleanly, you must manually find and terminate the process holding the port.

1.  **Find the Process ID (PID)**: `lsof -t -i:8001`
2.  **Terminate the Process**: `kill -9 <PID>`

### 3.3 Authentication Flow: User Sync Logic

The `POST /api/proxy/users/sync` endpoint contains critical logic for synchronizing users between Firebase and Supabase.

-   **The Problem**: A previous version of this endpoint attempted to create a new user on every login, causing a `duplicate key value` error in the database for existing users.

-   **The Solution (Robust Upsert)**: The corrected logic, implemented in `backend/api/users.py`, now follows a multi-step process:
    1.  It first checks if a user exists with the provided `auth_id`.
    2.  If not, it checks if a user exists with the provided `email`.
    3.  Only if neither exists does it create a new user record.
    This prevents duplicate user creation and ensures a smooth login experience.

---

## 4. Port Configuration

- **Backend**: Port `8001`
- **Web/Frontend**: Port `3000` (by default, but can be configured via the `PORT` environment variable)

---

## 5. Deployment Environments

### 5.1 Cloud Workstations (IDX)
The workstation environment is constrained by RAM (OOM Killer).
*   **Fix**: Switched from Flutter Web to Next.js for the primary preview to reduce memory footprint by ~3GB.
*   **Isolation**: Uses `backend/shell.nix` to provide `libstdc++` and `zlib` to Python without poisoning system binaries.

### 5.2 Mobile (Flutter)
The mobile app targets native Android/iOS and local development.
*   **Bootstrap Guard**: Implemented in `main.dart`. It prevents initialization if `--dart-define` flags are missing, ensuring developers catch config errors immediately.

---

## 6. Shared Data Contract

All services must align with the following key identifiers:
*   **User ID**: Linked via `auth_id` (UID from Firebase token).
*   **Schema**: Frontend uses `username` (matching Backend `UserSync` schema) rather than `display_name`.

---

## 7. Directory Map

.
├── backend/                  FastAPI service
│   ├── api/                  HTTP routers
│   ├── application/          use cases, schedulers, domain services
│   ├── domain/               entities, interfaces, valuation models
│   ├── infrastructure/       Supabase repositories
│   ├── providers/            external data connectors (yfinance, ...)
│   ├── shared/               cross-cutting helpers
│   ├── scripts/              operational scripts (run.sh, dev-setup.sh, ...)
│   ├── supabase/             local Supabase config + migrations
│   ├── tests/                unit, integration, e2e and system tests
│   ├── docs/                 backend documentation
│   └── shell.nix             backend Nix environment
├── web/                      Next.js front end
│   ├── src/                  app router, components, lib
│   ├── e2e/                  Playwright specs and evidence
│   ├── docs/                 UI/UX and component documentation
│   ├── public/               static assets
│   └── playwright.config.ts
├── mobile/                   Flutter app
│   ├── lib/                  app code
│   ├── test/                 widget tests
│   ├── web/                  Flutter web assets
│   ├── scripts/              mobile diagnostics
│   └── docs/                 Flutter documentation
├── framework/                Agentic lifecycle framework
│   ├── gates/                executable gates (G1-G19)
│   ├── adapters/             GSD state adapter
│   ├── contracts/            contract validation and type generation
│   ├── verifier/             evidence, matrix and routing contract
│   ├── testing/              system-test harness
│   ├── opencode/             agents, skills, commands, rules
│   ├── design/skills/        advisory design-skill corpus
│   ├── reference-app/        framework-owned reference application
│   └── docs/                 framework documentation
├── .github/  .devcontainer/  .idx/  .lifecycle/  .opencode/
├── AGENTS.md  opencode.json  framework.config.json    framework binding
├── pyproject.toml  MANIFEST.in  requirements-framework.txt    packaging
└── README.md

The repository holds exactly two projects: the StockerPro product (`backend/`, `web/`,
`mobile/`) and the agentic lifecycle framework (`framework/`). Each project owns its
documentation under `<project>/docs/`.
