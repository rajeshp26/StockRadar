// web/src/lib/rate-limit.ts
/**
 * Rate limiting for the Next.js proxy layer.
 *
 * Dev / single-instance:   In-memory sliding window, LRU-bounded to prevent memory leaks.
 * Prod / multi-instance:   Upstash Redis (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN).
 *
 * The in-memory store is bounded to MAX_ENTRIES. Old entries are evicted when
 * the store is full, preventing unbounded memory growth.
 */

// ── Tier configuration ────────────────────────────────────────────────────────

export type RateLimitTier = "read" | "write" | "auth" | "sse";

interface TierConfig {
    windowMs: number;
    maxRequests: number;
}

export const RATE_LIMIT_TIERS: Record<RateLimitTier, TierConfig> = {
    read: { windowMs: 10_000, maxRequests: 30 }, // 30 GETs per 10s
    write: { windowMs: 10_000, maxRequests: 10 }, // 10 mutations per 10s
    auth: { windowMs: 60_000, maxRequests: 5 }, // 5 auth attempts per minute
    sse: { windowMs: 60_000, maxRequests: 3 }, // 3 SSE connections per minute
};

// ── In-memory store ───────────────────────────────────────────────────────────

/** Maximum number of unique identifier+tier combinations to track. */
const MAX_ENTRIES = 10_000;

interface RateRecord {
    count: number;
    resetAt: number;
}

const store = new Map<string, RateRecord>();

/**
 * Evict expired entries when the store is full.
 * Map preserves insertion order, so we iterate from oldest.
 */
function evictExpired(): void {
    const now = Date.now();
    const targetSize = Math.floor(MAX_ENTRIES * 0.8); // Free 20% headroom
    for (const [key, record] of store) {
        if (store.size <= targetSize) break;
        if (now > record.resetAt) {
            store.delete(key);
        }
    }
    // If still full after evicting expired, delete oldest entries
    for (const key of store.keys()) {
        if (store.size <= targetSize) break;
        store.delete(key);
    }
}

function inMemoryCheck(key: string, tier: TierConfig): boolean {
    const now = Date.now();
    const record = store.get(key);

    if (!record || now > record.resetAt) {
        // New window: start fresh
        if (store.size >= MAX_ENTRIES) evictExpired();
        store.set(key, { count: 1, resetAt: now + tier.windowMs });
        return true;
    }

    if (record.count >= tier.maxRequests) {
        return false; // Rate limited
    }

    record.count++;
    return true;
}

// ── Upstash Redis (production multi-instance) ─────────────────────────────────

type UpstashChecker = (key: string) => Promise<{ success: boolean }>;
let _upstashChecker: UpstashChecker | null | undefined = undefined; // undefined = not yet attempted

async function getUpstashChecker(tier: TierConfig): Promise<UpstashChecker | null> {
    // Only attempt once per process lifetime
    if (_upstashChecker !== undefined) return _upstashChecker;

    if (
        !process.env.UPSTASH_REDIS_REST_URL ||
        !process.env.UPSTASH_REDIS_REST_TOKEN
    ) {
        _upstashChecker = null;
        return null;
    }

    try {
        // Upstash is an optional runtime dependency: next.config.js resolves both
        // modules to false and the env guard above skips this path when they are
        // absent, so the unresolved types here are expected, not a missing install.
        // @ts-expect-error optional dependency intentionally not installed
        const { Ratelimit } = await import("@upstash/ratelimit");
        // @ts-expect-error optional dependency intentionally not installed
        const { Redis } = await import("@upstash/redis");

        const rl = new Ratelimit({
            redis: Redis.fromEnv(),
            limiter: Ratelimit.slidingWindow(
                tier.maxRequests,
                `${tier.windowMs}ms` as `${number}ms`
            ),
            prefix: "stockerpro:rl:",
        });

        _upstashChecker = (key: string) => rl.limit(key);
        return _upstashChecker;
    } catch (err) {
        console.error("[rate-limit] Failed to initialize Upstash:", err);
        _upstashChecker = null;
        return null;
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Check rate limit for an identifier + tier combination.
 * Returns true if the request is allowed, false if rate limited.
 *
 * @param identifier  Unique key, e.g. `${ip}:${topLevelResource}`
 * @param tier        Rate limit tier based on request type
 */
export async function checkRateLimit(
    identifier: string,
    tier: RateLimitTier = "read"
): Promise<boolean> {
    const config = RATE_LIMIT_TIERS[tier];

    // Prefer Upstash in production
    if (process.env.NODE_ENV === "production") {
        const upstash = await getUpstashChecker(config);
        if (upstash) {
            const { success } = await upstash(`${identifier}:${tier}`);
            return success;
        }
    }

    // Fallback: in-memory (dev + prod fallback)
    return inMemoryCheck(`${identifier}:${tier}`, config);
}

/**
 * Determine the appropriate rate limit tier from HTTP method and path.
 */
export function getTierForRequest(method: string, path: string): RateLimitTier {
    const upperMethod = method.toUpperCase();

    // SSE streams get their own very tight tier
    if (path.startsWith("watchlists/stream")) return "sse";

    // Safe (idempotent) methods
    if (upperMethod === "GET" || upperMethod === "HEAD") return "read";

    // Auth endpoints (proxied — the /api/auth routes are handled by Next.js directly)
    // This covers any backend auth-related paths if they exist
    if (path.startsWith("auth/")) return "auth";

    // All other mutations
    return "write";
}