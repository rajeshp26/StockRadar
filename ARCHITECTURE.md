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

---

## 3. Deployment Environments

### 3.1 Cloud Workstations (IDX)
The workstation environment is constrained by RAM (OOM Killer).
*   **Fix**: Switched from Flutter Web to Next.js for the primary preview to reduce memory footprint by ~3GB.
*   **Isolation**: Uses `shell.nix` to provide `libstdc++` and `zlib` to Python without poisoning system binaries.

### 3.2 Mobile (Flutter)
The mobile app targets native Android/iOS and local development.
*   **Bootstrap Guard**: Implemented in `main.dart`. It prevents initialization if `--dart-define` flags are missing, ensuring developers catch config errors immediately.

---

## 4. Shared Data Contract

All services must align with the following key identifiers:
*   **User ID**: Linked via `firebase_uid` (UID from Firebase token).
*   **Schema**: Frontend uses `username` (matching Backend `UserSync` schema) rather than `display_name`.
*   **Ports**: Backend must always listen on **8001**. Web Preview on **9002**.

---

## 5. Directory Map

| Directory | Content |
| :--- | :--- |
| `web/src/components/auth/` | Firebase Auth providers and sync logic. |
| `backend/providers/` | External data connectors (yfinance, etc). |
| `mobile/lib/core/api/` | Typed Dio client for backend communication. |
| `docs/` | Engineering logs and security guidelines. |
