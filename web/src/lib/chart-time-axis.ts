// web/src/lib/chart-time-axis.ts
//
// Single source of truth for time-series chart X-axis ticks.
//
// Every date-axis chart previously rendered every category tick as "MMM d" and
// parsed date-only strings as UTC midnight (which rolls labels back a calendar
// day for timezones west of UTC). This module replaces that with a range-aware
// tick strategy:
//
//   getTickConfig(range, start, end)  ->  { unit, step, format }
//   getDateAxis(range, dates)         ->  { ticks, tickFormat } ready for Recharts
//
// Design notes:
//
//   1. Ticks are generated from the actual data span anchored to clean unit
//      boundaries (start of hour/day/month/year), so labels read naturally:
//      "2:00 PM", "Mon", "Jan", "2021".
//
//   2. Because Recharts category axes position ticks only at values that exist
//      in the data, ideal tick times are snapped to the nearest real data date
//      (e.g. a weekend ideal tick snaps to the nearest trading day).
//
//   3. Date-only strings ("2026-02-23") are parsed as LOCAL midnight, never UTC
//      midnight — same rule as lib/time.ts. Datetime strings keep their own
//      timezone semantics via `new Date`.
//
//   4. If a range's configured format would render every tick identically (e.g.
//      "h:mm a" over date-only data), it falls back to "MMM d" so the axis is
//      never useless.
//
//   5. The ALL range sizes its tick grid to a label-density target (8 labels by
//      default; narrower charts request fewer via getDateAxis({ widthPx }))
//      using a nice-interval ladder (1/2/3/6/12 h, 1/2/3/7 d, 1/3/6 mo,
//      1/2/5/10 y) — the same shape professional chart libraries use. A 5.5-year
//      span therefore gets annual labels, never a repeating month/quarter grid.
//
//   6. After ideal ticks are snapped to real data dates, adjacent ticks whose
//      rendered labels collide (two ideal months landing in the same calendar
//      month) are collapsed to the first occurrence, so an axis never shows
//      "Jan Jan" or "Jul Jul".

import {
    addDays,
    addHours,
    addMonths,
    addYears,
    format,
    startOfDay,
    startOfHour,
    startOfMonth,
    startOfYear,
} from 'date-fns';

export type TimeTickUnit = 'hour' | 'day' | 'month' | 'year';

export interface TickConfig {
    unit: TimeTickUnit;
    step: number;
    /** date-fns format tokens (e.g. 'h:mm a', 'EEE', 'MMM d', 'MMM', 'yyyy'). */
    format: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tick config per range
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Pick the X-axis tick strategy for a time range.
 *
 * Fixed spans (1D/1W/1M/3M/YTD/1Y) use spec-pinned densities. The variable-span
 * ALL range sizes its grid to a label-density target via the duration ladder.
 *
 * @param range            Period key ('1D' | '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL').
 * @param dataStartDate    First date present in the chart data.
 * @param dataEndDate      Last date present in the chart data.
 * @param targetTickCount  Optional label-density target for the ALL range
 *                         (default 8). Ignored by fixed-span ranges.
 */
export function getTickConfig(range: string, dataStartDate: Date, dataEndDate: Date, targetTickCount?: number): TickConfig {
    switch (range) {
        case '1D':
            return { unit: 'hour', step: 2, format: 'h:mm a' };
        case '1W':
            return { unit: 'day', step: 1, format: 'EEE' }; // Mon, Tue...
        case '1M':
            return { unit: 'day', step: 5, format: 'MMM d' };
        case '3M':
        case 'YTD':
        case '1Y':
            return { unit: 'month', step: 1, format: 'MMM' };
        case 'ALL':
            return pickNiceConfig(dataStartDate, dataEndDate, targetTickCount);
        default:
            return { unit: 'month', step: 1, format: 'MMM' };
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ALL-range density ladder (professional tick sizing)
// ─────────────────────────────────────────────────────────────────────────────

const MS_PER_DAY = 86_400_000;
const DEFAULT_TARGET_TICKS = 8;

/** Approximate pixels a rendered tick label occupies; width->target budget. */
export const LABEL_BUDGET_PX = 80;
const MIN_TARGET_TICKS = 3;
/**
 * Upper clamp for width-derived targets. A larger budget would push a 5.5-year
 * ALL span onto a 6-month grid (repeating "Jan ... Jul ..." labels) — exactly
 * the defect this module replaced.
 */
const MAX_TARGET_TICKS = 8;

/**
 * Derive an ALL-range label-density target from a chart's rendered width.
 *
 * `widthPx / LABEL_BUDGET_PX` labels, clamped to [MIN_TARGET_TICKS,
 * MAX_TARGET_TICKS]. Unknown/zero width (SSR, jsdom, pre-measurement) yields
 * the default target so charts are never degenerate before ResizeObserver
 * fires.
 */
export function targetTickCountForWidth(widthPx: number | undefined): number {
    if (typeof widthPx !== 'number' || !Number.isFinite(widthPx) || widthPx <= 0) {
        return DEFAULT_TARGET_TICKS;
    }
    const fromWidth = Math.floor(widthPx / LABEL_BUDGET_PX);
    return Math.min(MAX_TARGET_TICKS, Math.max(MIN_TARGET_TICKS, fromWidth));
}

function resolveTarget(target?: number | { widthPx?: number }): number {
    if (typeof target === 'number') return Math.max(1, Math.round(target));
    return targetTickCountForWidth(target?.widthPx);
}

interface NiceInterval {
    unit: TimeTickUnit;
    step: number;
    /** Nominal duration, used only to keep the ladder ordered. */
    ms: number;
}

/**
 * Candidate tick steps from dense to sparse. Month/year lengths are the
 * calendar averages (30.4375d, 365.2425d) so ordering stays stable against
 * real calendar spans (e.g. 4 Jul-to-Jul years tie a half-year grid).
 */
const NICE_INTERVALS: NiceInterval[] = [
    { unit: 'hour', step: 1, ms: MS_PER_DAY / 24 },
    { unit: 'hour', step: 2, ms: 2 * (MS_PER_DAY / 24) },
    { unit: 'hour', step: 3, ms: 3 * (MS_PER_DAY / 24) },
    { unit: 'hour', step: 6, ms: 6 * (MS_PER_DAY / 24) },
    { unit: 'hour', step: 12, ms: 12 * (MS_PER_DAY / 24) },
    { unit: 'day', step: 1, ms: MS_PER_DAY },
    { unit: 'day', step: 2, ms: 2 * MS_PER_DAY },
    { unit: 'day', step: 3, ms: 3 * MS_PER_DAY },
    { unit: 'day', step: 7, ms: 7 * MS_PER_DAY },
    { unit: 'month', step: 1, ms: 30.4375 * MS_PER_DAY },
    { unit: 'month', step: 3, ms: 3 * 30.4375 * MS_PER_DAY },
    { unit: 'month', step: 6, ms: 6 * 30.4375 * MS_PER_DAY },
    { unit: 'year', step: 1, ms: 365.2425 * MS_PER_DAY },
    { unit: 'year', step: 2, ms: 2 * 365.2425 * MS_PER_DAY },
    { unit: 'year', step: 5, ms: 5 * 365.2425 * MS_PER_DAY },
    { unit: 'year', step: 10, ms: 10 * 365.2425 * MS_PER_DAY },
];

/**
 * Size the ALL-range tick grid to a label density, the way d3's
 * `scaleTime().ticks(count)` and professional chart libraries do: the chosen
 * interval is the smallest nice step whose nominal duration is at least
 * `span / targetLabels`. Ticks never exceed the target, and adjacent spans
 * cannot flip formats the way a hard-coded year threshold did (5.0y and 5.5y
 * both land on an annual grid).
 */
function pickNiceConfig(dataStartDate: Date, dataEndDate: Date, targetTickCount?: number): TickConfig {
    const target = Math.max(1, Math.round(targetTickCount ?? DEFAULT_TARGET_TICKS));
    const spanMs = dataEndDate.getTime() - dataStartDate.getTime();
    if (spanMs <= 0) {
        // Zero-length span: keep a readable, stable default.
        return { unit: 'month', step: 3, format: 'MMM yyyy' };
    }

    const ideal = spanMs / target;
    let chosen = NICE_INTERVALS[NICE_INTERVALS.length - 1];
    for (const interval of NICE_INTERVALS) {
        if (interval.ms >= ideal) {
            chosen = interval;
            break;
        }
    }

    return { unit: chosen.unit, step: chosen.step, format: pickNiceFormat(chosen, dataStartDate, dataEndDate) };
}

function pickNiceFormat(interval: NiceInterval, dataStartDate: Date, dataEndDate: Date): string {
    switch (interval.unit) {
        case 'year':
            return 'yyyy';
        case 'month':
            // The year disambiguates month labels only when the data crosses a
            // calendar year; a single-year span stays "Jan, Feb, ...".
            return dataStartDate.getFullYear() === dataEndDate.getFullYear() ? 'MMM' : 'MMM yyyy';
        case 'day':
            return 'MMM d';
        case 'hour':
            return 'h:mm a';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Parsing
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Parse a chart date string into a local Date.
 *
 * "2026-02-23"        -> local midnight (never UTC midnight, which would
 *                       roll the calendar day back west of UTC).
 * "2026-03"           -> local midnight on the 1st of the month (month-only
 *                       keys, e.g. bar charts grouped by YYYY-MM).
 * "2026-02-23T14:30"  -> its own instant (new Date semantics).
 */
export function parseChartDate(value: string): Date {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        const [y, m, d] = value.split('-').map(Number);
        return new Date(y, m - 1, d);
    }
    if (/^\d{4}-\d{2}$/.test(value)) {
        const [y, m] = value.split('-').map(Number);
        return new Date(y, m - 1, 1);
    }
    return new Date(value);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tick generation
// ─────────────────────────────────────────────────────────────────────────────

const MAX_TICKS = 100;

/**
 * Generate ideal tick instants between `start` and `end` at the config's unit
 * and step, anchored to clean unit boundaries (00:00, the 1st of the month,
 * Jan 1). The first tick is the boundary at or before `start`, so the series
 * start edge always carries a label.
 */
export function buildTickDates(start: Date, end: Date, config: TickConfig): Date[] {
    const ticks: Date[] = [];
    let cursor = anchorToUnit(start, config.unit);

    while (cursor.getTime() <= end.getTime() && ticks.length < MAX_TICKS) {
        ticks.push(cursor);
        cursor = advanceBy(cursor, config.unit, config.step);
    }
    return ticks;
}

function anchorToUnit(date: Date, unit: TimeTickUnit): Date {
    switch (unit) {
        case 'hour':
            return startOfHour(date);
        case 'day':
            return startOfDay(date);
        case 'month':
            return startOfMonth(date);
        case 'year':
            return startOfYear(date);
    }
}

function advanceBy(date: Date, unit: TimeTickUnit, step: number): Date {
    switch (unit) {
        case 'hour':
            return addHours(date, step);
        case 'day':
            return addDays(date, step);
        case 'month':
            return addMonths(date, step);
        case 'year':
            return addYears(date, step);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Snapping to real data dates
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Map ideal tick instants onto the nearest real data date.
 *
 * Recharts category axes render a tick only when its value is a key present in
 * the data rows, so weekend/holiday ideal ticks snap to the nearest actual data
 * point. Duplicates are dropped and the result is returned chronologically.
 */
export function snapTicksToData(tickDates: Date[], dataDates: string[]): string[] {
    const points = dataDates
        .map((key) => ({ key, time: parseChartDate(key).getTime() }))
        .filter((p) => Number.isFinite(p.time))
        .sort((a, b) => a.time - b.time);

    if (points.length === 0) return [];

    const seen = new Set<string>();
    const snapped: string[] = [];

    for (const tick of tickDates) {
        const target = tick.getTime();
        let lo = 0;
        let hi = points.length - 1;
        while (lo < hi) {
            const mid = lo + ((hi - lo) >> 1);
            if (points[mid].time < target) lo = mid + 1;
            else hi = mid;
        }
        let best = lo;
        if (lo > 0 && target - points[lo - 1].time <= points[lo].time - target) {
            best = lo - 1;
        }
        const key = points[best].key;
        if (!seen.has(key)) {
            seen.add(key);
            snapped.push(key);
        }
    }

    return snapped.sort((a, b) => parseChartDate(a).getTime() - parseChartDate(b).getTime());
}

// ─────────────────────────────────────────────────────────────────────────────
// Public convenience API
// ─────────────────────────────────────────────────────────────────────────────

export interface DateAxis {
    /** Chart data keys (ISO date strings) that should carry an X-axis label. */
    ticks: string[];
    /** date-fns format tokens applied to each tick value. */
    tickFormat: string;
}

/**
 * Compute the X-axis ticks for a time-series chart in one call.
 *
 * @param range  Period key ('1D' | '1W' | ... | 'ALL') or a raw span label.
 * @param dates  Every date present in the chart data (any order; duplicates ok).
 * @param target ALL-range label-density control. A legacy number is the raw
 *               target (tests, custom callers). `{ widthPx }` derives a target
 *               from the rendered chart width. Omitted -> default (8).
 */
export function getDateAxis(range: string, dates: string[], target?: number | { widthPx?: number }): DateAxis {
    const parsed = dates
        .map((key) => ({ key, time: parseChartDate(key).getTime() }))
        .filter((p) => Number.isFinite(p.time))
        .sort((a, b) => a.time - b.time);

    if (parsed.length === 0) {
        return { ticks: [], tickFormat: 'MMM d' };
    }

    const start = new Date(parsed[0].time);
    const end = new Date(parsed[parsed.length - 1].time);
    const config = getTickConfig(range, start, end, resolveTarget(target));
    const keys = parsed.map((p) => p.key);

    let ticks = snapTicksToData(buildTickDates(start, end, config), keys);
    let tickFormat = config.format;

    // Degenerate span: no ideal tick landed inside the data (single point).
    if (ticks.length === 0) {
        return { ticks: [keys[0]], tickFormat };
    }

    // Discard a range format that renders every tick identically (e.g. "h:mm a"
    // over date-only daily data): all-same labels are a useless axis. Fall back
    // to a day grid sized to the data span so labels stay readable.
    const uniqueLabels = new Set(ticks.map((t) => formatAxisTick(t, tickFormat)));
    if (uniqueLabels.size === 1 && ticks.length > 1) {
        const spanDays = Math.max(1, Math.round((end.getTime() - start.getTime()) / MS_PER_DAY) + 1);
        const fallback: TickConfig = { unit: 'day', step: Math.max(1, Math.ceil(spanDays / 6)), format: 'MMM d' };
        ticks = snapTicksToData(buildTickDates(start, end, fallback), keys);
        tickFormat = fallback.format;
    }

    return {
        ticks: ensureTerminalTick(
            collapseAdjacentDuplicateLabels(ticks, tickFormat),
            keys[keys.length - 1],
            tickFormat,
        ),
        tickFormat,
    };
}

/**
 * Guarantee the newest observation carries an x-axis label.
 *
 * Ideal ticks sit on calendar boundaries, so the terminal data date is rarely
 * one: over a 1Y span ending 2026-09-26 the last ideal tick is 2026-09-01,
 * which `snapTicksToData` maps to 2026-08-31 (1 day away) over 2026-09-26
 * (25 days away). The chart stopped a month short of its own data.
 *
 * Collision handling is taken from the production libraries rather than
 * invented. Recharts `AxisInterval` (src/util/types.ts) documents
 * `'preserveEnd'` as "keeps the right tick on collision and ensures that the
 * last tick is always shown", and it is the library default for `interval`.
 * ECharts `axisLabel.showMaxLabel` forces the end label the same way, and
 * `AxisBuilder.ts` `fixMinMaxLabelShow` breaks the tie by ignoring the INNER
 * label. Do not reverse that direction: the interior tick yields, the terminal
 * label survives.
 *
 * Costs at most one label beyond the density target, which both libraries also
 * accept — the target sizes the grid, it does not license hiding the newest
 * observation.
 */
function ensureTerminalTick(ticks: string[], terminalKey: string, tickFormat: string): string[] {
    // Nothing survived snapping; the terminal date is all there is to show.
    if (ticks.length === 0) return [terminalKey];
    // `ticks` is ascending and a subset of the data keys, so a present
    // terminal key can only already be in final position.
    if (ticks[ticks.length - 1] === terminalKey) return ticks;

    const collides = formatAxisTick(terminalKey, tickFormat) === formatAxisTick(ticks[ticks.length - 1], tickFormat);
    return collides ? [...ticks.slice(0, -1), terminalKey] : [...ticks, terminalKey];
}

/**
 * Collapse adjacent tick labels that render identically after snapping.
 *
 * Snap-to-data can map several ideal months into the same calendar month (the
 * trailing days of one month and the leading days of the next both land in
 * "Jan"), producing "Jan Jan" or "Jul Jul". Keep the first occurrence; the
 * labels stay unique and the axis stays clean without hiding legitimately
 * distinct calendar coverage.
 */
function collapseAdjacentDuplicateLabels(ticks: string[], tickFormat: string): string[] {
    const collapsed: string[] = [];
    let previous: string | undefined;
    for (const tick of ticks) {
        const label = formatAxisTick(tick, tickFormat);
        if (label !== previous) {
            collapsed.push(tick);
            previous = label;
        }
    }
    return collapsed;
}

/** Format a chart data key with a date-fns format string. */
export function formatAxisTick(value: string, tickFormat: string): string {
    const date = parseChartDate(value);
    if (Number.isNaN(date.getTime())) return value;
    return format(date, tickFormat);
}