# 🤖 AI Debugging & Interaction Protocol

This document defines the strict reliability standards the AI Assistant must follow when debugging, configuring, or modifying the StockerPro codebase.

## 🛡️ The Reliability Protocol

### 1. Verification First Rule
*   **Requirement**: Never state that a service is "running," "fixed," or "ready" without providing proof.
*   **Action**: Every claim of success must be accompanied by the output of a verification command:
    *   `ps aux | grep <process>` (Process existence)
    *   `curl -I http://...` (Network connectivity)
    *   `tail -n 20 <log>` (Recent logs)

### 2. Context Over Invention
*   **Requirement**: Prioritize the developer's existing patterns and scripts over generic "best practices."
*   **Action**: Before proposing changes to startup, networking, or configuration, the AI must:
    *   Read existing `.sh` files.
    *   Consult `docs/ENVIRONMENT_SETUP_GUIDE.md`.
    *   Verify current environment variables.

### 3. Explicit Plan Approval
*   **Requirement**: Complex architectural changes or validation logic must be explained and approved before implementation.
*   **Action**: Present the logic (e.g., regex patterns, length checks, CORS policies) in plain text. Wait for a "Proceed" or feedback before writing to files.

### 4. Transparency in Errors
*   **Requirement**: If a command fails or returns unexpected results (like an empty log), the AI must stop and investigate.
*   **Action**: Do not repeat the same command. Instead, use system tools (`lsof`, `df`, `id`, `env`) to understand why the environment is behaving unexpectedly.

### 5. Failure-Safe Configuration
*   **Requirement**: Configuration logic must be robust but not arbitrary.
*   **Action**: 
    *   Avoid "magic numbers" (e.g., arbitrary min-lengths) unless they are backed by technical specifications.
    *   Support legacy and modern formats (e.g., Supabase `sb_secret_`) simultaneously unless there is a critical security reason to block them.
    *   Use `extra="forbid"` in Pydantic to catch typos, but ensure all environment variables are explicitly accounted for.

### 6. Robust Process Management
*   **Requirement**: Avoid fragile backgrounding (`&`) in Cloud IDE environments.
*   **Action**: 
    *   Use the established `start.sh`, `stop.sh`, and `status.sh` scripts for all backend operations.
    *   Utilize `nohup` and PID file tracking to ensure processes survive terminal hangups (SIGHUP).
    *   Always verify the PID exists after a 2-second delay to catch early crashes.

---

## 🚦 Debugging Checkpoints

When the user asks "What is the status?" or "Why is it failing?", the AI must provide a **Status Block**:

1.  **Backend Process**: [RUNNING/STOPPED] (via `ps` or PID file)
2.  **Port 8001**: [LISTENING/CLOSED] (via `lsof` or `netstat`)
3.  **Database Connection**: [VERIFIED/FAILED] (via health check or log)
4.  **Last Log Entry**: [TIMESTAMP + MESSAGE]

---

## 🧠 Lessons Learned (Retrospective)

*   **2025-01-01**: Learned that Pydantic `BaseSettings` crashes on unknown env vars (like IDE-injected keys). The fix is explicit declaration or prefixing, not ignoring.
*   **2025-01-01**: Learned that `sb_secret_` is a valid legacy Supabase format and should not be blocked by arbitrary character-length validation logic.
*   **2025-01-01**: Learned that standard `&` backgrounding is unreliable in cloud workstation terminals; robust PID management is required for persistence.
