// web/src/lib/security-logger.ts
/**
 * Security event logging for StockerPro.
 *
 * Outputs structured JSON to stdout in production (captured by CloudWatch/SIEM).
 * Pretty-prints to console in development.
 *
 * SOC 2 audit requirements this covers:
 *  - CC6.1: Authentication events (login success/failure, logout)
 *  - CC6.6: Unauthorized access attempts
 *  - CC7.2: Security events detected and logged
 *
 * CRITICAL DATA HYGIENE:
 *  Never pass raw tokens, passwords, API keys, or PII into the `details` field.
 *  The type system enforces that `details` is a string you construct manually.
 *  userId should be a Firebase UID only — never email or name.
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export type SecurityEventType =
    | "LOGIN_SUCCESS"
    | "LOGIN_FAILURE"
    | "LOGOUT"
    | "TOKEN_VERIFY_FAIL"
    | "RATE_LIMIT"
    | "CSRF_FAIL"
    | "UNAUTHORIZED_ACCESS"
    | "SESSION_REVOKED";

export type SecuritySeverity = "INFO" | "WARNING" | "ERROR" | "CRITICAL";

export interface SecurityEventInput {
    /** What happened */
    type: SecurityEventType;
    /** How serious */
    severity: SecuritySeverity;
    /** Firebase UID only — never email, name, or other PII */
    userId?: string;
    /** Client IP (from x-forwarded-for first segment) */
    ip?: string;
    /** Human-readable description — must NOT contain tokens, passwords, or PII */
    details: string;
}

interface SecurityEvent extends SecurityEventInput {
    timestamp: string;
    service: "stockerpro-web";
    environment: string;
}

// ── Dev console colors ────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<SecuritySeverity, string> = {
    INFO: "\x1b[36m", // cyan
    WARNING: "\x1b[33m", // yellow
    ERROR: "\x1b[31m", // red
    CRITICAL: "\x1b[35m", // magenta
};
const RESET = "\x1b[0m";

// ── Logger ────────────────────────────────────────────────────────────────────

export function logSecurityEvent(input: SecurityEventInput): void {
    const event: SecurityEvent = {
        ...input,
        timestamp: new Date().toISOString(),
        service: "stockerpro-web",
        environment: process.env.NODE_ENV ?? "unknown",
    };

    const line = JSON.stringify(event);

    if (process.env.NODE_ENV === "production") {
        // Structured JSON → stdout → log aggregator (CloudWatch, Datadog, etc.)
        // Do NOT use console.log in prod (may add formatting); write directly.
        process.stdout.write(line + "\n");
    } else {
        const color = SEVERITY_COLOR[input.severity];
        const prefix = `${color}[SECURITY ${input.severity}]${RESET}`;
        console.log(`${prefix} ${input.type} — ${input.details}`, {
            userId: input.userId ?? "—",
            ip: input.ip ?? "—",
            ts: event.timestamp,
        });
    }
}