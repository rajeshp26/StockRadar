# ✅ Verified Commands & Syntax Reference

This document lists the specific command strings and syntax that have been proven to work reliably within this Cloud Workstation environment. Use these to avoid "Command Failed" errors during debugging.

## 🚀 Backend Management (Port 8001)

| Action | Command |
| :--- | :--- |
| **Start** | `./backend/start.sh` |
| **Status** | `./backend/status.sh` |
| **Stop** | `./backend/stop.sh` |
| **Health Check** | `curl -s http://127.0.0.1:8001/health` |
| **Ready Check** | `curl -s http://127.0.0.1:8001/ready` |

## 📱 Mobile Management (Port 9003)

| Action | Command |
| :--- | :--- |
| **Start Web** | `./mobile/manage.sh run web` |
| **Stop Web** | `./mobile/manage.sh stop` |
| **Code Gen** | `cd mobile && flutter pub run build_runner build --delete-conflicting-outputs` |

## 🔍 System Verification

| Task | Verified Syntax |
| :--- | :--- |
| **Process Check** | `ps aux | grep uvicorn` (Keep it simple, avoid complex regex in pipes) |
| **Port Check** | `netstat -tuln | grep 8001` |
| **Log Tail** | `tail -n 20 backend/logs/backend.log` |

## ⚠️ Unreliable Syntax (Avoid)

*   **Complex Pipes**: Avoid triple-piping with `grep -v grep` and `grep -E` simultaneously; it has returned empty results even when processes exist.
*   **Backgrounding without Logs**: Never use `&` alone. Always redirect to a log file or use the provided `.sh` scripts which handle PID management.
*   **Relative Paths in Scripts**: Always use `cd "$(dirname "${BASH_SOURCE[0]}")"` inside scripts to ensure they are location-agnostic.
