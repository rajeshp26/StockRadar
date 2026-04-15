// web/src/lib/firebase-admin.ts
/**
 * Firebase Admin SDK singleton for Next.js.
 *
 * Uses FIREBASE_ADMIN_* env vars in production.
 * Falls back to Application Default Credentials in development.
 *
 * IMPORTANT: This file runs server-side only.
 * Never import from client components or pages that render on the client.
 */
import { cert, getApps, initializeApp, type App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

// ── Cookie configuration (shared with session/route.ts) ───────────────────────
export const SESSION_COOKIE_NAME =
    process.env.PROXY_IDTOKEN_COOKIE ?? "__session";

/** 5 days — used for createSessionCookie's expiresIn (ms) */
export const SESSION_COOKIE_EXPIRES_MS = 60 * 60 * 24 * 5 * 1000;

/** Matching HTTP cookie maxAge in seconds */
export const SESSION_COOKIE_MAX_AGE_SECONDS =
    SESSION_COOKIE_EXPIRES_MS / 1000;

// ── Singleton initializer ─────────────────────────────────────────────────────
function getAdminApp(): App {
    // Return existing named instance if already initialized (handles hot reloads)
    const existing = getApps().find((a) => a.name === "admin");
    if (existing) return existing;

    const projectId =
        process.env.FIREBASE_ADMIN_PROJECT_ID ??
        process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;

    const clientEmail = process.env.FIREBASE_ADMIN_CLIENT_EMAIL;
    const privateKey = process.env.FIREBASE_ADMIN_PRIVATE_KEY?.replace(
        /\\n/g,
        "\n"
    );

    if (!projectId) {
        throw new Error(
            "[firebase-admin] FIREBASE_ADMIN_PROJECT_ID (or NEXT_PUBLIC_FIREBASE_PROJECT_ID) is required."
        );
    }

    // Production path: explicit service account credentials via env vars
    if (clientEmail && privateKey) {
        return initializeApp(
            {
                credential: cert({ projectId, clientEmail, privateKey }),
            },
            "admin"
        );
    }

    // Development fallback: Application Default Credentials
    // Works if you've run: gcloud auth application-default login
    if (process.env.NODE_ENV !== "production") {
        console.warn(
            "[firebase-admin] FIREBASE_ADMIN_CLIENT_EMAIL/PRIVATE_KEY not set. " +
            "Attempting Application Default Credentials (dev only). " +
            "Set env vars for production."
        );
        return initializeApp({ projectId }, "admin");
    }

    throw new Error(
        "[firebase-admin] FIREBASE_ADMIN_CLIENT_EMAIL and FIREBASE_ADMIN_PRIVATE_KEY " +
        "must be set in production."
    );
}

export function getAdminAuth() {
    return getAuth(getAdminApp());
}