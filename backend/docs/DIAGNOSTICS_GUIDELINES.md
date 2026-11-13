# 🔍 Data-Driven Diagnostics Guidelines

This document defines the standard procedure for identifying and resolving technical issues within the StockerPro project.

## 📜 Core Principles

### 1. Zero Assumptions
*   **Definition**: Never assume a process is running, a port is open, a file exists, or a configuration is being applied as intended.
*   **Action**: Always verify state using standard system tools (`ps`, `lsof`, `netstat`, `ls`, `cat`).

### 2. Evidence-First
*   **Definition**: A solution should only be proposed after the underlying error has been explicitly captured in logs or terminal output.
*   **Action**: Capture and analyze stack traces, HTTP error codes, and system events before attempting a fix.

### 3. Verification Loop
*   **Definition**: A "fix" is only confirmed when the original diagnostic command that failed now succeeds.
*   **Action**: Rerun the specific test or command that demonstrated the failure to prove resolution.

### 4. Root Cause Isolation
*   **Definition**: Distinguish between "Symptoms" and "Causes."
*   **Symptoms**: User-facing errors (e.g., `502 Bad Gateway`).
*   **Causes**: The technical reason for the symptom (e.g., `Port 8000 already in use`).

---

## 🛠️ Standard Diagnostic Toolkit

| Command | Purpose |
| :--- | :--- |
| `ps aux \| grep <process>` | Check if a specific service is running. |
| `lsof -i :<port>` | Identify which process is holding a network port. |
| `tail -n 50 <log_file>` | Inspect the most recent error logs. |
| `curl -v <url>` | Test connectivity and inspect HTTP headers. |
| `ls -la <path>` | Verify file existence and permissions. |

---

## 📝 Traceability
For complex or persistent issues, document the journey in `backend/docs/TROUBLESHOOTING_LOG.md`. This prevents repetitive failed attempts and provides a reference for future developers.
