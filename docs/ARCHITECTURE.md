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

-   **Definition**: The environment is defined in the `shell.nix` file at the root of the project.
-   **Activation**: To enter the environment, run `nix-shell` from the project root. **All development and operational scripts MUST be run from within this shell.**

### 3.2 Backend Operations

**Starting the Server:**
To start the backend server correctly, use the following command from the project root:

```bash
nix-shell --run 'bash backend/start.sh'
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
*   **Isolation**: Uses `shell.nix` to provide `libstdc++` and `zlib` to Python without poisoning system binaries.

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

| Directory | Content |
| :--- | :--- |
| `web/src/components/auth/` | Firebase Auth providers and sync logic. |
| `backend/providers/` | External data connectors (yfinance, etc). |
| `mobile/lib/core/api/` | Typed Dio client for backend communication. |
| `docs/` | Engineering logs and security guidelines. |

.
├── .idx/
│   ├── dev.nix
│   └── icon.png
├── apphosting.yaml
├── backend/
│   ├── api/
│   │   ├── users.py
│   │   ├── valuations.py
│   │   ├── watchlist_items.py
│   │   └── watchlists.py
│   ├── application/
│   │   ├── jobs/
│   │   │   ├── data_quality_audit_job.py
│   │   │   └── derived_financial_metrics_job.py
│   │   ├── normalizers/
│   │   │   └── statement_normalizer.py
│   │   ├── schedulers/
│   │   │   ├── __init__.py
│   │   │   ├── earnings_scheduler.py
│   │   │   └── market_data_scheduler.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── dcf_service.py
│   │   │   ├── dcf_suitability.py
│   │   │   ├── ddm_service.py
│   │   │   ├── ddm_suitability.py
│   │   │   ├── recompute_guard.py
│   │   │   ├── rule1_suitability.py
│   │   │   ├── valuation_service.py
│   │   │   └── watchlist_service.py
│   │   └── __init__.py
│   ├── auth.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   └── watchlist.py
│   │   ├── exceptions.py
│   │   ├── __init__.py
│   │   ├── interfaces/
│   │   │   ├── __init__.py
│   │   │   ├── repository.py
│   │   │   └── stock_provider.py
│   │   ├── model_types.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── valuation_dcf.py
│   │       ├── valuation_ddm.py
│   │       └── valuation_rule1.py
│   ├── google_credentials.json
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── financial_repository.py
│   │       ├── supabase_repository.py
│   │       └── valuation_repository.py
│   ├── main.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── defeat_beta_provider.py
│   │   └── yfinance_provider.py
│   ├── requirements.txt
│   ├── schemas.py
│   ├── service-account.json
│   ├── services/
│   │   └── sync_service.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── exceptions/
│   │   │   ├── __init__.py
│   │   │   └── base.py
│   │   └── finance_math.py
│   ├── start-prod.sh
│   ├── start.sh
│   ├── status.sh
│   └── stop.sh
├── docs/
│   ├── AI_DEBUGGING_PROTOCOL.md
│   ├── ANALYSIS.md
│   ├── ARCHITECTURE.md
│   ├── Authentication_Refactor_Design.md
│   ├── BACKEND_SOFTWARE_DESIGN.md
│   ├── Backend_api_doc.md
│   ├── CHANGE_ANALYSIS_CHECKLIST.md
│   ├── DDM Design.md
│   ├── DESIGN_GUIDELINES.md
│   ├── DIAGNOSTICS_GUIDELINES.md
│   ├── ENVIRONMENT_SETUP_GUIDE.md
│   ├── FLUTTER_GUIDE.md
│   ├── Front_End_Design.md
│   ├── Login_Watchlist_Flow.md
│   ├── README.md
│   ├── SECURITY_GUIDELINES.md
│   ├── Supabase_Schema.md
│   ├── TESTING_GUIDE.md
│   ├── TROUBLESHOOTING_LOG.md
│   ├── VERIFIED_COMMANDS.md
│   ├── backend.json
│   ├── blueprint.md
│   ├── revert_plan.md
│   ├── sync_mapping_reference.md
│   └── test_deep_sync_guide.md
├── firebase.json
├── firestore.rules
├── mobile/
│   ├── README.md
│   ├── analysis_options.yaml
│   ├── lib/
│   │   ├── core/
│   │   │   ├── api/
│   │   │   │   ├── api_client.dart
│   │   │   │   ├── api_exception.dart
│   │   │   │   ├── api_exception.freezed.dart
│   │   │   │   ├── api_result.dart
│   │   │   │   ├── api_result.freezed.dart
│   │   │   │   └── auth_interceptor.dart
│   │   │   ├── config/
│   │   │   │   ├── environment.dart
│   │   │   │   └── firebase_config.dart
│   │   │   ├── models/
│   │   │   │   ├── watchlist.dart
│   │   │   │   ├── watchlist.freezed.dart
│   │   │   │   └── watchlist.g.dart
│   │   │   ├── providers/
│   │   │   │   ├── api_provider.dart
│   │   │   │   └── api_provider.g.dart
│   │   │   └── services/
│   │   │       └── watchlist_service.dart
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   │   └── providers/
│   │   │   │       ├── auth_provider.dart
│   │   │   │       └── auth_provider.g.dart
│   │   │   └── watchlist/
│   │   │       ├── presentation/
│   │   │       │   ├── screens/
│   │   │       │   │   └── watchlist_screen.dart
│   │   │       │   └── widgets/
│   │   │       │       └── stock_card.dart
│   │   │       └── providers/
│   │   │           ├── watchlist_provider.dart
│   │   │           └── watchlist_provider.g.dart
│   │   ├── main.dart
│   │   ├── preview_main.dart
│   │   └── shared/
│   │       └── widgets/
│   │           ├── glass_card.dart
│   │           └── watchlist_shimmer.dart
│   ├── manage.sh
│   ├── pubspec.lock
│   ├── pubspec.yaml
│   ├── test/
│   │   └── widget_test.dart
│   └── web/
│       ├── favicon.png
│       ├── icons/
│       │   ├── Icon-192.png
│       │   ├── Icon-512.png
│       │   ├── Icon-maskable-192.png
│       │   └── Icon-maskable-512.png
│       ├── index.html
│       └── manifest.json
├── package-lock.json
├── run.sh
├── scripts/
│   ├── debug_backend_sync.py
│   ├── debug_stock.py
│   ├── dev-setup.sh
│   ├── diagnostic.sh
│   └── generate_test_token.py
├── shell.nix
├── tests/
│   ├── README.md
│   ├── backend/
│   │   ├── test_deep_sync.py
│   │   ├── test_rule1_service.py
│   │   ├── test_watchlist_flow.py
│   │   └── test_watchlist_service_unit.py
│   └── e2e/
│       └── test_user_sync.py
└── web/
    ├── components.json
    ├── next-env.d.ts
    ├── next.config.js
    ├── package-lock.json
    ├── package.json
    ├── postcss.config.mjs
    ├── public/
    │   ├── icon-192.png
    │   └── manifest.json
    ├── src/
    │   ├── ai/
    │   │   ├── dev.ts
    │   │   └── genkit.ts
    │   ├── app/
    │   │   ├── (authenticated)/
    │   │   │   ├── analysis/
    │   │   │   │   └── [symbol]/
    │   │   │   │       └── page.tsx
    │   │   │   ├── dashboard/
    │   │   │   │   └── page.tsx
    │   │   │   ├── layout.tsx
    │   │   │   ├── profile/
    │   │   │   │   └── page.tsx
    │   │   │   ├── settings/
    │   │   │   │   └── page.tsx
    │   │   │   └── watchlist/
    │   │   │       └── page.tsx
    │   │   ├── api/
    │   │   │   ├── auth/
    │   │   │   │   └── session/
    │   │   │   │       └── route.ts
    │   │   │   └── proxy/
    │   │   │       └── [...path]/
    │   │   │           └── route.ts
    │   │   ├── favicon.ico
    │   │   ├── globals.css
    │   │   ├── layout.tsx
    │   │   ├── login/
    │   │   │   └── page.tsx
    │   │   ├── page.tsx
    │   │   └── signup/
    │   │       └── page.tsx
    │   ├── components/
    │   │   ├── FirebaseErrorListener.tsx
    │   │   ├── auth/
    │   │   │   ├── login-form.tsx
    │   │   │   └── signup-form.tsx
    │   │   ├── dashboard/
    │   │   │   ├── add-stock-dialog.tsx
    │   │   │   ├── stock-card.tsx
    │   │   │   ├── stock-list-row.tsx
    │   │   │   ├── watchlist-switcher.tsx
    │   │   │   ├── watchlist-toolbar.tsx
    │   │   │   └── watchlist.tsx
    │   │   ├── header.tsx
    │   │   ├── icons.tsx
    │   │   ├── ui/
    │   │   │   ├── accordion.tsx
    │   │   │   ├── alert-dialog.tsx
    │   │   │   ├── alert.tsx
    │   │   │   ├── avatar.tsx
    │   │   │   ├── badge.tsx
    │   │   │   ├── button.tsx
    │   │   │   ├── calendar.tsx
    │   │   │   ├── card.tsx
    │   │   │   ├── carousel.tsx
    │   │   │   ├── chart.tsx
    │   │   │   ├── checkbox.tsx
    │   │   │   ├── collapsible.tsx
    │   │   │   ├── dialog.tsx
    │   │   │   ├── dropdown-menu.tsx
    │   │   │   ├── form.tsx
    │   │   │   ├── input.tsx
    │   │   │   ├── label.tsx
    │   │   │   ├── menubar.tsx
    │   │   │   ├── popover.tsx
    │   │   │   ├── progress.tsx
    │   │   │   ├── radio-group.tsx
    │   │   │   ├── scroll-area.tsx
    │   │   │   ├── select.tsx
    │   │   │   ├── separator.tsx
    │   │   │   ├── sheet.tsx
    │   │   │   ├── sidebar.tsx
    │   │   │   ├── skeleton.tsx
    │   │   │   ├── slider.tsx
    │   │   │   ├── switch.tsx
    │   │   │   ├── table.tsx
    │   │   │   ├── tabs.tsx
    │   │   │   ├── textarea.tsx
    │   │   │   ├── toast.tsx
    │   │   │   ├── toaster.tsx
    │   │   │   └── tooltip.tsx
    │   │   └── user-nav.tsx
    │   ├── features/
    │   │   ├── analysis/
    │   │   │   ├── analytics/
    │   │   │   │   └── analysis.analytics.ts
    │   │   │   ├── components/
    │   │   │   │   ├── dcf-history.tsx
    │   │   │   │   ├── dcf-how.tsx
    │   │   │   │   ├── dcf-method.tsx
    │   │   │   │   ├── dcf-panel.tsx
    │   │   │   │   ├── dcf-suitability.tsx
    │   │   │   │   ├── dcf-summary.tsx
    │   │   │   │   ├── ddm-panel.tsx
    │   │   │   │   ├── intrinsic-panel.tsx
    │   │   │   │   ├── method-panel.tsx
    │   │   │   │   ├── method-selector.tsx
    │   │   │   │   ├── rule1-panel.tsx
    │   │   │   │   ├── shared-ui.tsx
    │   │   │   │   └── valuation-overview.tsx
    │   │   │   ├── hooks/
    │   │   │   │   ├── useAnalysis.ts
    │   │   │   │   ├── useDcfAnalysis.ts
    │   │   │   │   ├── useDcfHistory.ts
    │   │   │   │   ├── useDdmAnalysis.ts
    │   │   │   │   ├── useDdmHistory.ts
    │   │   │   │   ├── useLivePrice.ts
    │   │   │   │   └── useRule1History.ts
    │   │   │   ├── services/
    │   │   │   │   └── analysis.service.ts
    │   │   │   ├── types/
    │   │   │   │   └── analysis.types.ts
    │   │   │   └── valuation/
    │   │   │       └── methods.ts
    │   │   ├── auth/
    │   │   │   ├── services/
    │   │   │   │   ├── auth.service.ts
    │   │   │   │   └── token-manager.ts
    │   │   │   └── types/
    │   │   │       └── auth.types.ts
    │   │   └── watchlists/
    │   │       ├── hooks/
    │   │       │   └── useWatchlist.ts
    │   │       ├── services/
    │   │       │   └── watchlist.service.ts
    │   │       └── types/
    │   │           └── watchlist.types.ts
    │   ├── firebase/
    │   │   ├── client-provider.tsx
    │   │   ├── config.ts
    │   │   ├── error-emitter.ts
    │   │   ├── errors.ts
    │   │   ├── firestore/
    │   │   │   ├── use-collection.tsx
    │   │   │   └── use-doc.tsx
    │   │   ├── index.ts
    │   │   ├── non-blocking-login.tsx
    │   │   ├── non-blocking-updates.tsx
    │   │   └── provider.tsx
    │   ├── hooks/
    │   │   ├── use-mobile.tsx
    │   │   ├── use-toast.ts
    │   │   └── useWatchlist.ts
    │   ├── lib/
    │   │   ├── api.ts
    │   │   ├── data.ts
    │   │   ├── performance.ts
    │   │   ├── placeholder-images.json
    │   │   ├── placeholder-images.ts
    │   │   ├── types.ts
    │   │   └── utils.ts
    │   ├── providers/
    │   │   └── auth-provider.tsx
    │   ├── proxy.ts
    │   ├── services/
    │   │   └── watchlist.service.ts
    │   └── shared/
    │       ├── constants.ts
    │       └── contexts/
    │           └── ServiceContext.tsx
    ├── tailwind.config.ts
    └── tsconfig.json


