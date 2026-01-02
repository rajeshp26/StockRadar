# Project Architecture and Environment Guide

This document provides a comprehensive overview of the project's technical architecture and development environment. It is the single source of truth for understanding how the system is built and how to run it correctly.

## 1. Core Technologies

*   **Frontend:**
    *   **Framework:** Next.js 15 (App Router), React 19.
    *   **Authentication:** [Firebase Authentication](https://firebase.google.com/docs/auth). The client-side application uses the Firebase Web SDK to manage user sign-in and retrieve authentication tokens.
    *   **UI Components:** Tailwind CSS with shadcn/ui.
    *   **Reactivity:** Firebase Firestore for reactive document synchronization where needed.

*   **Backend (SOLID Layered Architecture):**
    *   **Framework:** FastAPI (Python 3.11+).
    *   **Database:** [Supabase](https://supabase.io/). 
    *   **Data Provider:** `yfinance` for fetching financial stock data.
    *   **AI Layer:** Google Genkit AI (`src/ai/`) for advanced stock analysis and flow orchestration.

*   **Communication:**
    *   **Secure Bridge:** Next.js API Bridge (`src/app/api/proxy/`) for REST commands.
    *   **Real-time:** Server-Sent Events (SSE) for stock price synchronization.

---

## 2. System Architecture & The "Secure Bridge"

The system uses a decoupled architecture: **Firebase for authentication** and **Supabase for the database**. To avoid CORS and simplify security, the frontend communicates with the Python backend via a **Secure Bridge**.

`Browser` <---> `Next.js API Bridge (Proxy)` <---> `FastAPI Backend` <---> `Supabase / yfinance`

---

## 3. Backend Layered Architecture (SOLID)

To ensure maintainability and testability, the backend follows a strict layered architecture:

| Layer | Directory | Responsibility |
| :--- | :--- | :--- |
| **API** | `backend/api/` | Route handlers, request/response schemas (Pydantic), and controller logic. |
| **Application** | `backend/application/` | Orchestration of business logic and use cases (Services). |
| **Domain** | `backend/domain/` | Core business entities and abstract interfaces (The "Heart" of the system). |
| **Infrastructure** | `backend/infrastructure/` | Concrete implementations of interfaces (Repositories, external providers). |
| **Shared** | `backend/shared/` | Common utilities, custom exceptions, and cross-cutting concerns. |

### 3.1 Key Design Patterns
*   **Repository Pattern:** Data access logic is encapsulated in `backend/infrastructure/repositories/`, allowing the business logic to remain database-agnostic.
*   **Dependency Inversion:** High-level services depend on abstract interfaces (defined in `domain/interfaces/`) rather than concrete database clients.
*   **Interface Segregation:** Providers and Repositories are split into focused interfaces (e.g., `StockProvider`, `WatchlistRepository`).

---

## 4. Directory Map (Detailed)

| Path | Description |
| :--- | :--- |
| `src/app/(authenticated)/` | Protected Next.js routes. |
| `src/app/api/proxy/` | The Secure Bridge implementation. |
| `backend/application/services/` | Use cases like `WatchlistService`. |
| `backend/domain/interfaces/` | Abstract definitions for Repositories and Providers. |
| `backend/infrastructure/repositories/` | Supabase-specific data access logic. |
| `backend/providers/` | Concrete external data providers (e.g., `yfinance`). |

---

## 5. User Flows & Technical Sequences

### 5.1 Flow: Startup & Authentication
**Trigger:** User visits the root URL.
*   **Frontend:** `AuthProvider` initializes Firebase. `middleware.ts` redirects to `/dashboard` if a session exists.

### 5.2 Flow: Dashboard Loading (Handshake)
1.  **Frontend:** `Watchlist.tsx` calls `POST /watchlists/default-with-items`.
2.  **Backend (API):** `watchlists.py` receives the request and calls `WatchlistService`.
3.  **Backend (Service):** `WatchlistService` uses a `WatchlistRepository` to fetch data and a `StockProvider` for live prices.
4.  **Backend (Response):** Returns a unified `WatchlistWithStocks` domain object.

---

## 6. Running the Application

### Frontend
*   **Command:** `npm run dev` (Starts on port 9002).

### Backend (Python)
The backend port **must** be `8001` to match the Secure Bridge configuration.
```bash
uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8001 --reload
```
