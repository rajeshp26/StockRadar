# 🛠️ Environment Setup & Service Management

This document provides the definitive guide for managing the StockerPro monorepo.

---

## 📂 Project Structure

*   `/backend`: Python FastAPI server.
*   `/web`: Next.js React frontend.
*   `/mobile`: Flutter cross-platform app.

---

## 🚀 Environment Prerequisites (The Nix Shell)

This project uses **Nix** to resolve system library conflicts. All backend operations MUST be run through the Nix shell to avoid `ImportError` or `Segmentation Fault` (Segfault) caused by `libstdc++.so.6`.

**Activate the shell:**
```bash
nix-shell shell.nix
```

---

## 🐍 Backend Management (Port 8001)

Always use the provided management scripts inside the Nix shell.

```bash
# Start Backend
./backend/start.sh

# Check Status
./backend/status.sh

# View Logs
tail -f backend/logs/backend.log
```

**Troubleshooting:**
*   If you see `422 Unprocessable Content`, verify the frontend is sending `username` and not `display_name`.
*   If you see `502 Bad Gateway`, ensure the backend is actually running on Port 8001.

---

## 🌐 Web Frontend (Port 9002)

The Next.js app is the primary interface for Cloud Workstations due to its low RAM usage (~600MB).

```bash
cd web
npm install
npm run dev
```

---

## 📱 Mobile Management (Flutter)

The mobile application is intended for **local development** or **native building**.

### 1. Run Mobile (Local)
```bash
./mobile/manage.sh run android
```

### 2. Configuration
Ensure `mobile/.env` is populated with Firebase keys. The app will fail-fast with a red screen if these are missing.

---

## ⚙️ Configuration Matrix

| Tier | Config File | Key Variable |
| :--- | :--- | :--- |
| **Backend** | `backend/.env` | `SUPABASE_SERVICE_ROLE_KEY` |
| **Web** | `web/.env.local` | `NEXT_PUBLIC_FIREBASE_API_KEY` |
| **Mobile** | `mobile/.env` | `FIREBASE_API_KEY` |

---

## 🔍 Resource Management (Workstation)

**Memory (OOM) Protection:**
Flutter Web compilation requires >4GB RAM. If your workstation has 8GB total, avoid running Flutter Web alongside the Next.js preview. Use Next.js for web testing.
