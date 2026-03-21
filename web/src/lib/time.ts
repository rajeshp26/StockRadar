// web/src/lib/time.ts
//
// Single source of truth for all timestamp display in the app.
//
// Design principles:
//
//   1. Never hardcode a timezone.
//      Intl / toLocaleString with no explicit timeZone option automatically
//      uses the user's OS timezone. A user in ET sees ET times, a user in
//      IST sees IST times, a user in BST sees BST times — zero configuration.
//
//   2. Distinguish datetime strings from date-only strings.
//      "2026-03-14T17:02:41Z"  → a moment in time → timezone-convert for display
//      "2026-02-23"            → a calendar date   → NEVER timezone-convert
//      JavaScript's new Date("2026-02-23") parses as UTC midnight, which rolls
//      back one calendar day for any user west of UTC. We parse date-only strings
//      via year/month/day components into local midnight instead.
//
//   3. Defensive UTC normalisation.
//      If a datetime string arrives without a timezone marker (no Z, no ±hh:mm),
//      we append "Z" before parsing. This handles backends that omit the suffix
//      on UTC timestamps — without this, Chrome and Safari disagree on whether
//      the bare string is local or UTC.
//
//   4. Age-based display strategy (same as Robinhood / Alpaca):
//      < 1 min   → "just now"
//      1–59 min  → "14m ago"
//      today     → "2:32 PM"           (user's local time)
//      yesterday → "Yesterday, 2:32 PM"
//      this year → "Mar 14, 2:32 PM"
//      older     → "Mar 14, 2025"
//
//   5. Two strategies exposed to callers:
//      "relative"  — for live prices and recent events (stock cards, analysis header)
//      "absolute"  — for valuation computed dates, history entries
//      "date-only" — for fiscal snapshot dates (snapshotDate, period_end_date)
//                    renders as "Feb 23, 2026" with no time component

export type TimestampStrategy = "relative" | "absolute" | "date-only";

// ─────────────────────────────────────────────────────────────────────────────
// Internal parser
// ─────────────────────────────────────────────────────────────────────────────

function parseTimestamp(value: string): Date | null {
  if (!value) return null;

  // Date-only: "2026-02-23"
  // Construct via components → local midnight, no UTC conversion.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    const date = new Date(y, m - 1, d);
    return isNaN(date.getTime()) ? null : date;
  }

  // DateTime string — ensure it has a timezone marker.
  // Strings already ending in Z or ±hh:mm are left as-is.
  // Bare strings like "2026-03-14T17:02:41.004933" get Z appended.
  const hasMarker = value.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(value);
  const normalised = hasMarker ? value : value + "Z";

  const date = new Date(normalised);
  return isNaN(date.getTime()) ? null : date;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared locale helpers — no explicit timeZone → browser fills in user's TZ
// ─────────────────────────────────────────────────────────────────────────────

function timeStr(date: Date): string {
  return date.toLocaleTimeString(undefined, {
    hour:   "2-digit",
    minute: "2-digit",
  });
}

function dateStr(date: Date): string {
  return date.toLocaleDateString(undefined, {
    month: "short",
    day:   "numeric",
  });
}

function isToday(date: Date, now: Date): boolean {
  return date.toDateString() === now.toDateString();
}

function isYesterday(date: Date, now: Date): boolean {
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  return date.toDateString() === yesterday.toDateString();
}

function isSameYear(date: Date, now: Date): boolean {
  return date.getFullYear() === now.getFullYear();
}

// ─────────────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Format a timestamp string for display.
 *
 * @param value     ISO 8601 string, date-only string, or null/undefined.
 * @param strategy  "relative"  — age-aware, best for live prices.
 *                  "absolute"  — always shows a human date+time, best for
 *                                computed dates (valuations, history).
 *                  "date-only" — fiscal calendar dates, no time or TZ conversion.
 * @returns         Formatted string, or null if value is empty/unparseable.
 */
export function formatTimestamp(
  value: string | null | undefined,
  strategy: TimestampStrategy = "relative",
): string | null {
  if (!value) return null;

  const date = parseTimestamp(value);
  if (!date) return null;

  // ── date-only ─────────────────────────────────────────────────────────────
  // Fiscal dates ("2026-02-23") — display as calendar date with no time.
  // Never involves a timezone conversion.
  if (strategy === "date-only") {
    return date.toLocaleDateString(undefined, {
      year:  "numeric",
      month: "short",
      day:   "numeric",
    });
  }

  const now = new Date();
  const ageMs  = now.getTime() - date.getTime();
  const ageSec = ageMs / 1_000;
  const ageMin = ageSec / 60;

  // ── relative ──────────────────────────────────────────────────────────────
  // Used for live prices and SSE-driven updates.
  // Shows "just now" / "14m ago" for very recent timestamps, then falls back
  // to time-of-day for older ones.
  if (strategy === "relative") {
    if (ageSec < 60)  return "just now";
    if (ageMin < 60)  return `${Math.floor(ageMin)}m ago`;
    if (isToday(date, now))     return timeStr(date);
    if (isYesterday(date, now)) return `Yesterday, ${timeStr(date)}`;
    if (isSameYear(date, now))  return `${dateStr(date)}, ${timeStr(date)}`;
    return date.toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  }

  // ── absolute ──────────────────────────────────────────────────────────────
  // Used for valuation computed-at and history timestamps.
  // Always shows a specific date/time — never a relative "ago" string —
  // so the user can reason about how fresh the data is.
  if (strategy === "absolute") {
    if (isToday(date, now))     return `Today, ${timeStr(date)}`;
    if (isYesterday(date, now)) return `Yesterday, ${timeStr(date)}`;
    if (isSameYear(date, now))  return `${dateStr(date)}, ${timeStr(date)}`;
    return date.toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  }

  return null;
}