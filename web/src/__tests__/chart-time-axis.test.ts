import { describe, it, expect } from 'vitest';
import {
    getTickConfig,
    getDateAxis,
    buildTickDates,
    snapTicksToData,
    parseChartDate,
    formatAxisTick,
    targetTickCountForWidth,
} from '@/lib/chart-time-axis';

const JAN_1_2019 = new Date(2019, 0, 1);
const JUL_1_2026 = new Date(2026, 6, 1);

describe('getTickConfig', () => {
    it('1D -> hourly every 2 hours, clock format', () => {
        expect(getTickConfig('1D', new Date(2026, 8, 16, 9, 30), new Date(2026, 8, 16, 16, 0))).toEqual({
            unit: 'hour', step: 2, format: 'h:mm a',
        });
    });

    it('1W -> daily, weekday label', () => {
        const cfg = getTickConfig('1W', new Date(2026, 8, 14), new Date(2026, 8, 20));
        expect(cfg).toEqual({ unit: 'day', step: 1, format: 'EEE' });
    });

    it('1M -> every 5 days, MMM d', () => {
        expect(getTickConfig('1M', new Date(2026, 8, 1), new Date(2026, 9, 1))).toEqual({
            unit: 'day', step: 5, format: 'MMM d',
        });
    });

    it('3M/YTD/1Y -> monthly, MMM within a single calendar year', () => {
        const start = new Date(2026, 0, 1);
        const end = new Date(2026, 11, 31);
        expect(getTickConfig('3M', start, end)).toEqual({ unit: 'month', step: 1, format: 'MMM' });
        expect(getTickConfig('YTD', start, end)).toEqual({ unit: 'month', step: 1, format: 'MMM' });
        expect(getTickConfig('1Y', start, end)).toEqual({ unit: 'month', step: 1, format: 'MMM' });
    });

    it("3M/YTD/1Y -> monthly, MMM'yy when the span crosses a calendar year", () => {
        // The 1Y defect: a trailing 12-month window (Sep 2025 .. Aug 2026) must
        // carry the year, or every month label is ambiguous about its year.
        const start = new Date(2025, 8, 1);
        const end = new Date(2026, 7, 31);
        expect(getTickConfig('1Y', start, end)).toEqual({ unit: 'month', step: 1, format: "MMM''yy" });
        expect(getTickConfig('3M', new Date(2025, 10, 1), new Date(2026, 1, 1))).toEqual({
            unit: 'month', step: 1, format: "MMM''yy",
        });
    });

    it("ALL spanning 7.5 years -> every-other quarter (still inside the 8-year quarter band)", () => {
        // 30 quarters > the 24-quarter dense cap, so step 2 — but still quarters,
        // never year ticks.
        expect(getTickConfig('ALL', JAN_1_2019, JUL_1_2026)).toEqual({
            unit: 'quarter', step: 2, format: "QQQ''yy",
        });
    });

    it("ALL spanning exactly 5 years -> every-quarter ticks, Qn'yy", () => {
        // The 8-year quarter band: a 5-year history shows its 20 quarters rather
        // than collapsing to five year labels.
        const cfg = getTickConfig('ALL', new Date(2021, 0, 1), new Date(2026, 0, 1));
        expect(cfg).toEqual({ unit: 'quarter', step: 1, format: "QQQ''yy" });
    });

    it("ALL spanning 5.49 years -> every-quarter ticks, never a month grid", () => {
        // 2021-01-01 -> 2026-07-01: the span that used to render the repeating
        // "Jan 2021 Jul 2021 ..." month grid. It now lands on an all-quarter grid
        // (22 quarters), neither monthly nor yearly.
        const cfg = getTickConfig('ALL', new Date(2021, 0, 1), new Date(2026, 6, 1));
        expect(cfg).toEqual({ unit: 'quarter', step: 1, format: "QQQ''yy" });
    });

    it('ALL spanning 5.9 and 6.0 years -> quarter ticks (still inside the 8-year band)', () => {
        expect(getTickConfig('ALL', new Date(2021, 0, 1), new Date(2026, 10, 30))).toEqual({ unit: 'quarter', step: 1, format: "QQQ''yy" });
        expect(getTickConfig('ALL', new Date(2020, 0, 1), new Date(2026, 0, 1))).toEqual({ unit: 'quarter', step: 1, format: "QQQ''yy" });
    });

    it('ALL spanning just over 8 years -> annual grid (quarters no longer fit)', () => {
        // 2018-01-01 -> 2026-07-01 = 8.5y, past the quarter band.
        expect(getTickConfig('ALL', new Date(2018, 0, 1), new Date(2026, 6, 1))).toEqual({ unit: 'year', step: 2, format: 'yyyy' });
    });

    it("ALL spanning 4 years -> every-quarter ticks, Qn'yy", () => {
        expect(getTickConfig('ALL', new Date(2023, 6, 1), new Date(2027, 6, 1))).toEqual({
            unit: 'quarter', step: 1, format: "QQQ''yy",
        });
    });

    it("ALL spanning 3 years -> every-quarter ticks, Qn'yy", () => {
        expect(getTickConfig('ALL', new Date(2023, 6, 15), new Date(2026, 6, 14))).toEqual({
            unit: 'quarter', step: 1, format: "QQQ''yy",
        });
    });

    it("ALL spanning 2 years -> quarterly ticks, Qn'yy", () => {
        expect(getTickConfig('ALL', new Date(2024, 6, 1), new Date(2026, 6, 1))).toEqual({
            unit: 'quarter', step: 1, format: "QQQ''yy",
        });
    });

    it('ALL spanning 10 years -> 2-year ticks', () => {
        expect(getTickConfig('ALL', new Date(2016, 0, 1), new Date(2026, 0, 1))).toEqual({ unit: 'year', step: 2, format: 'yyyy' });
    });

    it('ALL spanning 20 years -> 5-year ticks', () => {
        expect(getTickConfig('ALL', new Date(2006, 0, 1), new Date(2026, 0, 1))).toEqual({ unit: 'year', step: 5, format: 'yyyy' });
    });

    it("ALL with equal start/end dates -> stable quarterly default", () => {
        const d = new Date(2026, 0, 1);
        expect(getTickConfig('ALL', d, d).format).toBe("QQQ''yy");
    });

    it('ALL honors a custom density target inside the quarter band (narrow budget thins to every other)', () => {
        const start = new Date(2021, 0, 1);
        const end = new Date(2026, 6, 1);
        expect(getTickConfig('ALL', start, end, 4)).toEqual({ unit: 'quarter', step: 2, format: "QQQ''yy" });
        expect(getTickConfig('ALL', start, end, 16)).toEqual({ unit: 'quarter', step: 1, format: "QQQ''yy" });
    });

    it("5Y -> every-quarter ticks over a five-year span", () => {
        expect(getTickConfig('5Y', new Date(2021, 0, 1), new Date(2026, 0, 1))).toEqual({
            unit: 'quarter', step: 1, format: "QQQ''yy",
        });
    });

    it('unknown range -> sensible monthly default (year shown when it crosses a year)', () => {
        expect(getTickConfig('MAX', new Date(2021, 0, 1), new Date(2026, 0, 1))).toEqual({
            unit: 'month', step: 1, format: "MMM''yy",
        });
    });
});

describe('parseChartDate', () => {
    it('parses date-only strings as LOCAL midnight (never UTC midnight)', () => {
        const d = parseChartDate('2026-02-23');
        expect(d.getFullYear()).toBe(2026);
        expect(d.getMonth()).toBe(1); // Feb
        expect(d.getDate()).toBe(23);
        expect(d.getHours()).toBe(0);
        expect(d.getMinutes()).toBe(0);
    });

    it('keeps datetime strings on their own instant', () => {
        const parsed = parseChartDate('2026-02-23T14:30:00Z');
        expect(parsed.getTime()).toBe(new Date('2026-02-23T14:30:00Z').getTime());
    });

    it('parses month-only keys (YYYY-MM) as LOCAL midnight on the 1st', () => {
        // Bar charts grouped by month (e.g. dividend history) key data as
        // "2026-03"; the axis must read those as calendar months, not fail.
        const d = parseChartDate('2026-03');
        expect(d.getFullYear()).toBe(2026);
        expect(d.getMonth()).toBe(2); // Mar
        expect(d.getDate()).toBe(1);
        expect(d.getHours()).toBe(0);
    });

    it('formats a date-only key with the LOCAL calendar day label', () => {
        // UTC midnight would render "Feb 22" west of UTC — local midnight never does.
        expect(formatAxisTick('2026-02-23', 'MMM d')).toBe('Feb 23');
    });
});

describe('buildTickDates', () => {
    it('1Y span -> monthly ticks anchored to the 1st, start edge labeled', () => {
        const start = new Date(2025, 6, 15); // Jul 15
        const end = new Date(2026, 6, 14);   // Jul 14
        const ticks = buildTickDates(start, end, { unit: 'month', step: 1, format: 'MMM' });
        expect(ticks.length).toBe(13);
        expect(ticks[0]).toEqual(new Date(2025, 6, 1)); // anchor at-or-before start (Jul 1)
        expect(ticks[ticks.length - 1]).toEqual(new Date(2026, 6, 1)); // Jul 1
        for (const t of ticks) {
            expect(t.getDate()).toBe(1);
            expect(t.getTime()).toBeLessThanOrEqual(end.getTime());
        }
    });

    it('1W span (Mon-Sun) -> 7 daily midnight ticks', () => {
        const start = new Date(2026, 8, 14); // Mon
        const end = new Date(2026, 8, 20);   // Sun
        const ticks = buildTickDates(start, end, { unit: 'day', step: 1, format: 'EEE' });
        expect(ticks.length).toBe(7);
        expect(ticks[0].getDay()).toBe(1); // Monday
        expect(ticks[0].getHours()).toBe(0);
    });

    it('1D intraday span -> ticks every 2 hours, anchor hour labeled', () => {
        const start = new Date(2026, 8, 16, 9, 30);
        const end = new Date(2026, 8, 16, 16, 0);
        const ticks = buildTickDates(start, end, { unit: 'hour', step: 2, format: 'h:mm a' });
        expect(ticks).toEqual([
            new Date(2026, 8, 16, 9, 0),
            new Date(2026, 8, 16, 11, 0),
            new Date(2026, 8, 16, 13, 0),
            new Date(2026, 8, 16, 15, 0),
        ]);
    });

    it('ALL spanning 7+ years -> yearly ticks from Jan 1', () => {
        const ticks = buildTickDates(JAN_1_2019, JUL_1_2026, { unit: 'year', step: 1, format: 'yyyy' });
        expect(ticks[0]).toEqual(new Date(2019, 0, 1));
        expect(ticks[ticks.length - 1]).toEqual(new Date(2026, 0, 1));
    });

    it('ALL spanning 3 years -> ticks every 3 months', () => {
        const start = new Date(2023, 6, 15);
        const end = new Date(2026, 6, 14);
        const ticks = buildTickDates(start, end, { unit: 'month', step: 3, format: 'MMM yyyy' });
        expect(ticks[0]).toEqual(new Date(2023, 6, 1)); // Jul 2023 (anchor at-or-before start)
        expect(ticks.length).toBe(13);
        for (const t of ticks) expect(t.getDate()).toBe(1);
    });
});

describe('snapTicksToData', () => {
    const dataDates = [
        '2026-09-11', // Fri
        '2026-09-14', // Mon
        '2026-09-15',
        '2026-09-16',
        '2026-09-17',
        '2026-09-18', // Fri
        '2026-09-21', // Mon
    ];

    it('snaps a weekend ideal tick to the nearest trading day', () => {
        // Sat 2026-09-12 and Sun 2026-09-13 are absent — nearest is Fri 09-11 or Mon 09-14.
        const sat = new Date(2026, 8, 12);
        const sun = new Date(2026, 8, 13);
        const result = snapTicksToData([sat, sun], dataDates);
        expect(result).toEqual(['2026-09-11', '2026-09-14']);
    });

    it('returns only keys that exist in the data', () => {
        const result = snapTicksToData([new Date(2026, 8, 16)], dataDates);
        expect(result).toEqual(['2026-09-16']);
        result.forEach((key) => expect(dataDates).toContain(key));
    });

    it('dedupes ticks that snap to the same data date and sorts chronologically', () => {
        const ideal = [
            new Date(2026, 8, 13), // Sun -> Mon 09-14
            new Date(2026, 8, 14), // Mon 09-14
            new Date(2026, 8, 15), // Tue 09-15
        ];
        expect(snapTicksToData(ideal, dataDates)).toEqual(['2026-09-14', '2026-09-15']);
    });

    it('returns [] for empty data', () => {
        expect(snapTicksToData([new Date(2026, 8, 14)], [])).toEqual([]);
    });

    it('ignores unparseable data keys', () => {
        expect(snapTicksToData([new Date(2026, 8, 14)], ['not-a-date', '2026-09-14'])).toEqual(['2026-09-14']);
    });
});

describe('getDateAxis (end-to-end)', () => {
    it("1Y with monthly data crossing a year -> real data keys, MMM'yy labels", () => {
        const dates = ['2025-08-01', '2025-09-01', '2025-10-01', '2025-11-01', '2025-12-01', '2026-01-01', '2026-02-01', '2026-03-01', '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01'];
        const axis = getDateAxis('1Y', dates);
        expect(axis.tickFormat).toBe("MMM''yy");
        expect(axis.ticks.length).toBeGreaterThanOrEqual(8);
        axis.ticks.forEach((t) => expect(dates).toContain(t));
        expect(formatAxisTick(axis.ticks[0], axis.tickFormat)).toBe("Aug'25");
    });

    it("ALL over 7 years of yearly data -> Qn'yy quarter labels", () => {
        const dates = ['2019-03-01', '2020-03-01', '2021-03-01', '2022-03-01', '2023-03-01', '2024-03-01', '2025-03-01', '2026-03-01'];
        const axis = getDateAxis('ALL', dates);
        expect(axis.tickFormat).toBe("QQQ''yy");
        axis.ticks.forEach((t) => expect(dates).toContain(t));
        expect(formatAxisTick(axis.ticks[0], axis.tickFormat)).toBe("Q1'19"); // anchor at-or-before start: 2019-03-01
    });

    it("ALL over a 3-year span -> Qn'yy quarter labels", () => {
        const dates = ['2023-07-01', '2023-10-01', '2024-01-01', '2024-04-01', '2024-07-01', '2024-10-01', '2025-01-01', '2025-04-01', '2025-07-01', '2025-10-01', '2026-01-01', '2026-04-01', '2026-07-01'];
        const axis = getDateAxis('ALL', dates);
        expect(axis.tickFormat).toBe("QQQ''yy");
        axis.ticks.forEach((t) => expect(dates).toContain(t));
        expect(formatAxisTick(axis.ticks[0], axis.tickFormat)).toBe("Q3'23"); // anchor at-or-before start: 2023-07-01
    });

    it("ALL over a 5.49-year span -> Qn'yy quarter labels, never month labels (reported Jan/Jul repeat)", () => {
        // Regression pin: 67 monthly points from 2021-01-01 to 2026-07-01 must
        // render an all-quarter axis, never the repeating month grid from the bug.
        const dates: string[] = [];
        for (let m = 0; m < 67; m++) {
            const d = new Date(2021, m, 1);
            dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`);
        }
        const axis = getDateAxis('ALL', dates);
        expect(axis.tickFormat).toBe("QQQ''yy");
        axis.ticks.forEach((t) => expect(dates).toContain(t));
        const labels = axis.ticks.map((t) => formatAxisTick(t, axis.tickFormat));
        expect(labels[0]).toBe("Q1'21");
        expect(labels.every((l) => /^Q[1-4]'\d\d$/.test(l))).toBe(true);
    });

    it('getDateAxis honors a custom density target (sparse budget thins to every other quarter)', () => {
        const dates = ['2021-01-01', '2022-01-01', '2023-01-01', '2024-01-01', '2025-01-01', '2026-01-01', '2026-07-01'];
        const axis = getDateAxis('ALL', dates, 4);
        expect(axis.tickFormat).toBe("QQQ''yy");
        // The sparse budget thins the 22-quarter span to every other quarter;
        // 2026-07-01 stays as the terminal tick so the newest observation is labelled.
        expect(axis.ticks).toEqual(['2021-01-01', '2022-01-01', '2023-01-01', '2024-01-01', '2025-01-01', '2026-01-01', '2026-07-01']);
    });

    it('1W over daily data -> weekday labels', () => {
        const dates = ['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-19', '2026-09-20'];
        const axis = getDateAxis('1W', dates);
        expect(axis.tickFormat).toBe('EEE');
        expect(formatAxisTick(axis.ticks[0], axis.tickFormat)).toBe('Mon');
    });

    it('1D over intraday data -> clock labels', () => {
        const dates = ['2026-09-16T09:30:00', '2026-09-16T10:00:00', '2026-09-16T10:30:00', '2026-09-16T11:00:00', '2026-09-16T11:30:00', '2026-09-16T12:00:00', '2026-09-16T12:30:00', '2026-09-16T13:00:00', '2026-09-16T13:30:00', '2026-09-16T14:00:00', '2026-09-16T14:30:00', '2026-09-16T15:00:00', '2026-09-16T15:30:00'];
        const axis = getDateAxis('1D', dates);
        expect(axis.tickFormat).toBe('h:mm a');
        expect(formatAxisTick(axis.ticks[0], axis.tickFormat)).toBe('9:30 AM'); // anchor 09:00 snaps to nearest data 09:30
    });

    it('falls back to MMM d when the range format renders identical labels (date-only 1D data)', () => {
        const dates = ['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18'];
        const axis = getDateAxis('1D', dates);
        expect(axis.tickFormat).toBe('MMM d');
        const labels = new Set(axis.ticks.map((t) => formatAxisTick(t, axis.tickFormat)));
        expect(labels.size).toBeGreaterThan(1);
    });

    it('returns empty axis for no data', () => {
        expect(getDateAxis('1Y', [])).toEqual({ ticks: [], tickFormat: 'MMM d' });
    });

    it('returns at least one tick for a single data point', () => {
        const axis = getDateAxis('1Y', ['2026-09-16']);
        expect(axis.ticks).toEqual(['2026-09-16']);
    });

    it('handles unsorted and duplicated input dates', () => {
        const dates = ['2026-07-01', '2026-01-01', '2026-04-01', '2026-01-01', '2026-10-01'];
        const axis = getDateAxis('1Y', dates);
        expect(axis.ticks).toEqual(['2026-01-01', '2026-04-01', '2026-07-01', '2026-10-01']);
    });
});

describe('targetTickCountForWidth (width-derived density)', () => {
    it('80px per tick, clamped to [3, 8]', () => {
        expect(targetTickCountForWidth(240)).toBe(3);
        expect(targetTickCountForWidth(320)).toBe(4);
        expect(targetTickCountForWidth(640)).toBe(8);
    });

    it('clamps excessive widths back to 8', () => {
        expect(targetTickCountForWidth(720)).toBe(8);
        expect(targetTickCountForWidth(1600)).toBe(8);
    });

    it('clamps tiny widths up to 3', () => {
        expect(targetTickCountForWidth(79)).toBe(3);
        expect(targetTickCountForWidth(160)).toBe(3);
    });

    it('falls back to the default of 8 for unmeasurable widths', () => {
        expect(targetTickCountForWidth(undefined)).toBe(8);
        expect(targetTickCountForWidth(0)).toBe(8);
        expect(targetTickCountForWidth(NaN)).toBe(8);
        expect(targetTickCountForWidth(-320)).toBe(8);
    });
});

describe('getDateAxis with { widthPx } target', () => {
    const fiveYearMonthlyKeys = () => {
        const keys: string[] = [];
        for (let m = 0; m < 67; m++) {
            const d = new Date(2021, m, 1);
            keys.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`);
        }
        return keys;
    };

    it('narrow panel (320px -> 4 ticks) thins a 5.49y ALL span to every other quarter', () => {
        const axis = getDateAxis('ALL', fiveYearMonthlyKeys(), { widthPx: 320 });
        expect(axis.tickFormat).toBe("QQQ''yy");
        // Every-other quarter (Q1/Q3) end to end; the terminal key is already the
        // last quarter start so the snap keeps it.
        expect(axis.ticks).toEqual([
            '2021-01-01', '2021-07-01', '2022-01-01', '2022-07-01', '2023-01-01', '2023-07-01',
            '2024-01-01', '2024-07-01', '2025-01-01', '2025-07-01', '2026-01-01', '2026-07-01',
        ]);
    });

    it('wide panel (640px -> 8 ticks) keeps every quarter on a 5.49y ALL span', () => {
        const axis = getDateAxis('ALL', fiveYearMonthlyKeys(), { widthPx: 640 });
        expect(axis.tickFormat).toBe("QQQ''yy");
        // 23 quarter starts from Q1'21 through Q3'26 inclusive.
        expect(axis.ticks.length).toBe(23);
        expect(axis.ticks[0]).toBe('2021-01-01');
        expect(axis.ticks[axis.ticks.length - 1]).toBe('2026-07-01');
    });

    it('240px (clamped to 3) behaves identically to 320px on the same span', () => {
        expect(getDateAxis('ALL', fiveYearMonthlyKeys(), { widthPx: 240 })).toEqual(
            getDateAxis('ALL', fiveYearMonthlyKeys(), { widthPx: 320 }),
        );
    });

    it('number target and { widthPx } target resolve the same ladder', () => {
        expect(getDateAxis('ALL', fiveYearMonthlyKeys(), 4)).toEqual(
            getDateAxis('ALL', fiveYearMonthlyKeys(), { widthPx: 320 }),
        );
    });

    it('width is inert on fixed-ladder ranges', () => {
        const monthlyKeys = [
            '2025-01-05', '2025-02-05', '2025-03-05', '2025-04-05', '2025-05-05', '2025-06-05',
            '2025-07-05', '2025-08-05', '2025-09-05', '2025-10-05', '2025-11-05', '2025-12-05',
            '2026-01-05',
        ];
        expect(getDateAxis('1Y', monthlyKeys, { widthPx: 320 })).toEqual(getDateAxis('1Y', monthlyKeys));
    });

    it("reads YYYY-MM month keys (dividend history) and emits quarter ticks in the same key space", () => {
        const quarterlyMonthKeys: string[] = [];
        for (let y = 2021; y <= 2026; y++) {
            for (const m of [1, 4, 7, 10]) {
                quarterlyMonthKeys.push(`${y}-${String(m).padStart(2, '0')}`);
            }
        }
        const axis = getDateAxis('ALL', quarterlyMonthKeys);
        expect(axis.tickFormat).toBe("QQQ''yy");
        // 24 quarter keys, Q1'21 .. Q4'26, all present in the key space.
        expect(axis.ticks.length).toBe(24);
        for (const tick of axis.ticks) {
            expect(quarterlyMonthKeys).toContain(tick);
        }
        const labels = axis.ticks.map((t) => formatAxisTick(t, axis.tickFormat));
        expect(new Set(labels).size).toBe(labels.length);
        expect(labels.every((l) => /^Q[1-4]'\d\d$/.test(l))).toBe(true);
    });
});

describe('adjacent duplicate label collapse', () => {
    it('collapses only adjacent duplicate month labels caused by snap collisions', () => {
        const dates = [
            '2025-10-01', '2025-11-05', '2025-11-28', '2025-12-10',
            '2026-01-05', '2026-02-05', '2026-03-05', '2026-04-05',
            '2026-05-05', '2026-06-05', '2026-07-05', '2026-08-05', '2026-09-05',
        ];
        const axis = getDateAxis('1Y', dates);
        expect(axis.tickFormat).toBe("MMM''yy");
        const labels = axis.ticks.map((t) => formatAxisTick(t, axis.tickFormat));
        expect(new Set(labels).size).toBe(labels.length);
        expect(labels[0]).toBe("Oct'25");
        expect(labels[1]).toBe("Nov'25");
        expect(axis.ticks).not.toContain('2025-11-28');
    });

    it('keeps a same month label that repeats only across the year boundary', () => {
        const dates = [
            '2025-01-05', '2025-02-05', '2025-03-05', '2025-04-05', '2025-05-05', '2025-06-05',
            '2025-07-05', '2025-08-05', '2025-09-05', '2025-10-05', '2025-11-05', '2025-12-05',
            '2026-01-05',
        ];
        const axis = getDateAxis('1Y', dates);
        expect(axis.ticks).toHaveLength(13);
        const labels = axis.ticks.map((t) => formatAxisTick(t, axis.tickFormat));
        expect(labels[0]).toBe("Jan'25");
        expect(labels[12]).toBe("Jan'26");
        expect(new Set(labels).size).toBe(13);
    });
});

describe('terminal tick guarantee (newest observation is always labelled)', () => {
    const MONTHLY_TO_AUG31 = [
        '2025-10-01', '2025-11-01', '2025-12-01', '2026-01-01', '2026-02-01', '2026-03-01',
        '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-31',
    ];

    it('labels a terminal date that is not a calendar boundary (regression: axis stopped at Aug while data ran to Sep 26)', () => {
        // The 2026-09-01 ideal tick is 1 day from 2026-08-31 and 25 days from
        // 2026-09-26, so snapping lands on Aug and the newest point goes unlabelled.
        const axis = getDateAxis('1Y', [...MONTHLY_TO_AUG31, '2026-09-26']);

        expect(axis.ticks).toContain('2026-08-31');
        expect(axis.ticks[axis.ticks.length - 1]).toBe('2026-09-26');
    });

    it('drops the interior tick when the terminal label would collide, keeping the newest date', () => {
        // 2026-09-01 snaps to 2026-09-05; the terminal 2026-09-26 renders the same
        // "Sep". Recharts `preserveEnd` and ECharts `fixMinMaxLabelShow` both keep
        // the outmost label and drop the inner one.
        const dates = [...MONTHLY_TO_AUG31.slice(0, -1), '2026-08-05', '2026-09-05', '2026-09-26'];
        const axis = getDateAxis('1Y', dates);
        const labels = axis.ticks.map((t) => formatAxisTick(t, axis.tickFormat));

        expect(axis.ticks[axis.ticks.length - 1]).toBe('2026-09-26');
        expect(axis.ticks).not.toContain('2026-09-05');
        expect(new Set(labels).size).toBe(labels.length);
    });

    it('leaves ticks untouched when the terminal date is already the final tick', () => {
        const dates = [...MONTHLY_TO_AUG31];
        const axis = getDateAxis('1Y', dates);

        expect(axis.ticks[axis.ticks.length - 1]).toBe('2026-08-31');
        expect(new Set(axis.ticks).size).toBe(axis.ticks.length);
    });

    it('labels the final intraday observation on the 1D axis', () => {
        const dates: string[] = [];
        for (let m = 9 * 60 + 30; m <= 15 * 60 + 30; m += 30) {
            const h = String(Math.floor(m / 60)).padStart(2, '0');
            const min = String(m % 60).padStart(2, '0');
            dates.push(`2026-09-16T${h}:${min}:00`);
        }
        const axis = getDateAxis('1D', dates);

        expect(axis.tickFormat).toBe('h:mm a');
        expect(axis.ticks[axis.ticks.length - 1]).toBe('2026-09-16T15:30:00');
    });

    it('still labels both edges for a single observation', () => {
        const axis = getDateAxis('1Y', ['2026-09-16']);

        expect(axis.ticks).toEqual(['2026-09-16']);
    });

    it('emits no ticks when there is no data', () => {
        expect(getDateAxis('1Y', [])).toEqual({ ticks: [], tickFormat: 'MMM d' });
    });
});