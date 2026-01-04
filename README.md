# StockerPro: Deep Financial Analytics Platform

StockerPro is a professional-grade personal stock analytics platform built with **Next.js 15**, **FastAPI**, and **Supabase**. It automates the ingestion of historical financial statements to provide deep fundamental insights and real-time portfolio tracking.

## 📂 Project Structure

This monorepo is organized into three primary tiers:

*   **`/backend`**: Python FastAPI server. Handles data ingestion, `yfinance` integration, and Supabase data orchestration.
*   **`/web`**: Primary Web Frontend built with Next.js 15, React 19, and Tailwind CSS.
*   **`/mobile`**: Cross-platform Mobile App built with Flutter 3.22 and Riverpod.

---

## 🚀 Quick Start (Development)

### 1. Prerequisite: The Nix Environment
This project uses **Nix** to ensure binary compatibility across development environments (resolving common issues with `libstdc++` and `glibc`).

### 2. Launch the Backend
The backend must run in an isolated Nix shell to support C-extensions like NumPy/Pandas:
```bash
# From the project root
nix-shell shell.nix --run "cd backend && ./start.sh"
```
*   **Port:** 8001
*   **Health:** `http://localhost:8001/health`

### 3. Launch the Web Frontend
```bash
cd web
npm install
npm run dev
```
*   **Port:** 9002 (Preview)
*   **Proxy:** Automatically bridges to the backend on Port 8001.

---

## 🧪 Testing

### Functional Backend Testing
Verify the data ingestion pipeline independently:
1.  Ensure backend is running.
2.  Run the deep sync test suite:
    ```bash
    source backend/venv/bin/activate
    pytest backend/tests/test_deep_sync.py
    ```

### Mobile Verification
```bash
cd mobile
flutter analyze
flutter test
```

---

## 🛡️ Architecture Highlights

*   **Secure API Bridge:** Next.js acts as a secure proxy between the browser and Python, forwarding Firebase Auth tokens and preventing CORS leaks.
*   **Real-time Streaming:** Implements **Stream Piping** for Server-Sent Events (SSE) to deliver live stock prices with zero-buffering.
*   **Nix Isolation:** Uses `shell.nix` to resolve system library conflicts (`libstdc++.so.6`) without affecting the host OS.
*   **Fail-Fast Initialization:** The mobile app implements a "Bootstrap Guard" to ensure Firebase configuration is valid before the UI renders.

## 🔗 Documentation

*   **[Full Architecture Guide](ARCHITECTURE.md):** Deep dive into schemas, data flow, and the bridge pattern.
*   **[Environment Setup Guide](docs/ENVIRONMENT_SETUP_GUIDE.md):** Detailed platform-specific configuration and troubleshooting.
*   **[Testing Guide](docs/TESTING_GUIDE.md):** Quality assurance protocols for all tiers.
