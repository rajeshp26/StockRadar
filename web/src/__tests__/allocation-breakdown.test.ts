import { describe, expect, it } from 'vitest';
import {
    buildAllocationRows,
    computeAllocationMetrics,
    computeTypeShares,
    isEtfTypeKey,
    isStockTypeKey,
} from '@/features/portfolio/lib/allocation-breakdown';
import type { AllocationSegment, TypeAllocationSegment } from '@/features/portfolio/types/portfolio.types';

// Faithful subset of the real /portfolio/allocation payload: singular type keys
// ('stock'/'etf'), types[].weight = portfolio share, types[].sectors[].weight =
// share WITHIN that type only (sums to 100 per type, NOT across types).
const types: TypeAllocationSegment[] = [
    {
        type: 'stock',
        type_label: 'Stocks',
        value: 165663.05,
        weight: 88.11,
        count: 125,
        gain_loss: 80037.18,
        sectors: [
            { segment: 'Communication Services', value: 37728.54, weight: 22.77, count: 14, gain_loss: 26087.05 },
            { segment: 'Technology', value: 33208.45, weight: 20.05, count: 19, gain_loss: 16539.22 },
            { segment: 'Consumer Cyclical', value: 29473.7, weight: 17.79, count: 16, gain_loss: 23161.28 },
            { segment: 'Financial Services', value: 28986.25, weight: 17.5, count: 21, gain_loss: 11346.78 },
            { segment: 'Consumer Defensive', value: 12175.95, weight: 7.35, count: 11, gain_loss: 817.68 },
            { segment: 'Energy', value: 7131.46, weight: 4.3, count: 6, gain_loss: 459.98 },
            { segment: 'Industrials', value: 4844.24, weight: 2.92, count: 9, gain_loss: 1039.2 },
            { segment: 'Real Estate', value: 3937.5, weight: 2.38, count: 10, gain_loss: -731.17 },
            { segment: 'Utilities', value: 3279.89, weight: 1.98, count: 7, gain_loss: -562.51 },
            { segment: 'Healthcare', value: 3219.55, weight: 1.94, count: 8, gain_loss: 1411.91 },
            { segment: 'Basic Materials', value: 1473.16, weight: 0.89, count: 3, gain_loss: 409.63 },
            { segment: 'Unknown', value: 204.36, weight: 0.12, count: 1, gain_loss: 58.11 },
        ],
    },
    {
        type: 'etf',
        type_label: 'ETFs',
        value: 22361.47,
        weight: 11.89,
        count: 18,
        gain_loss: 7627.51,
        sectors: [
            { segment: 'Unknown', value: 21422.54, weight: 95.8, count: 15, gain_loss: 7999.6 },
            { segment: 'Financial Services', value: 929.71, weight: 4.16, count: 2, gain_loss: -320.28 },
            { segment: 'Healthcare', value: 9.22, weight: 0.04, count: 1, gain_loss: -51.81 },
        ],
    },
];

const segments: AllocationSegment[] = [
    { segment: 'Stocks / Communication Services', value: 37728.54, weight: 20.07, count: 14, gain_loss: 26087.05 },
    { segment: 'Stocks / Technology', value: 33208.45, weight: 17.66, count: 19, gain_loss: 16539.22 },
    { segment: 'Stocks / Consumer Cyclical', value: 29473.7, weight: 15.68, count: 16, gain_loss: 23161.28 },
    { segment: 'Stocks / Financial Services', value: 28986.25, weight: 15.42, count: 21, gain_loss: 11346.78 },
    { segment: 'Stocks / Consumer Defensive', value: 12175.95, weight: 6.48, count: 11, gain_loss: 817.68 },
    { segment: 'Stocks / Energy', value: 7131.46, weight: 3.79, count: 6, gain_loss: 459.98 },
    { segment: 'Stocks / Industrials', value: 4844.24, weight: 2.58, count: 9, gain_loss: 1039.2 },
    { segment: 'Stocks / Real Estate', value: 3937.5, weight: 2.09, count: 10, gain_loss: -731.17 },
    { segment: 'Stocks / Utilities', value: 3279.89, weight: 1.74, count: 7, gain_loss: -562.51 },
    { segment: 'Stocks / Healthcare', value: 3219.55, weight: 1.71, count: 8, gain_loss: 1411.91 },
    { segment: 'Stocks / Basic Materials', value: 1473.16, weight: 0.78, count: 3, gain_loss: 409.63 },
    { segment: 'Stocks / Unknown', value: 204.36, weight: 0.11, count: 1, gain_loss: 58.11 },
    { segment: 'ETFs / Unknown', value: 21422.54, weight: 11.39, count: 15, gain_loss: 7999.6 },
    { segment: 'ETFs / Financial Services', value: 929.71, weight: 0.49, count: 2, gain_loss: -320.28 },
    { segment: 'ETFs / Healthcare', value: 9.22, weight: 0.0, count: 1, gain_loss: -51.81 },
];

const round = (n: number, digits = 1) => Number(n.toFixed(digits));

describe('buildAllocationRows', () => {
    it('flattens types[].sectors into rows sorted by portfolio share', () => {
        const rows = buildAllocationRows(types, segments);
        expect(rows).toHaveLength(15);
        expect(rows[0].key).toBe('stock|Communication Services');
        expect(round(rows[0].pct)).toBeCloseTo(20.1, 0);
        // Largest row is the biggest stock sector, NOT the within-type ETF 95.8.
        expect(rows[0].sector).toBe('Communication Services');
    });

    it('converts within-type weights to portfolio shares (ETF Unknown 95.8 => 11.4)', () => {
        const rows = buildAllocationRows(types, segments);
        const etfUnknown = rows.find((r) => r.typeKey === 'etf' && r.sector === 'Unknown');
        expect(etfUnknown).toBeDefined();
        expect(round(etfUnknown!.pct)).toBeCloseTo(11.4, 0);
    });

    it('never lets percentages exceed the portfolio (Top 5 must be <= 100)', () => {
        const rows = buildAllocationRows(types, segments);
        const metrics = computeAllocationMetrics(rows);
        expect(metrics.topFivePct).toBeLessThanOrEqual(100);
        // Within-type weights would have produced 173.9 for Top 5; normalized it is ~80.2.
        expect(round(metrics.topFivePct)).toBeCloseTo(80.2, 0);
        expect(round(metrics.sumPct)).toBeCloseTo(100.0, 0);
    });

    it('matches singular type keys stock/etf (real payload) and plural (legacy)', () => {
        expect(isStockTypeKey('stock')).toBe(true);
        expect(isStockTypeKey('stocks')).toBe(true);
        expect(isStockTypeKey('etf')).toBe(false);
        expect(isEtfTypeKey('etf')).toBe(true);
        expect(isEtfTypeKey('etfs')).toBe(true);
        expect(isEtfTypeKey('stock')).toBe(false);
    });

    it('normalizes stray type weights so metrics still sum to ~100', () => {
        const broken = types.map((t) => ({ ...t, weight: t.weight * 3 }));
        const rows = buildAllocationRows(broken, segments);
        const metrics = computeAllocationMetrics(rows);
        expect(round(metrics.sumPct)).toBeCloseTo(100.0, 0);
        expect(round(metrics.stocksPct)).toBeCloseTo(88.1, 0);
        expect(round(metrics.etfsPct)).toBeCloseTo(11.9, 0);
        expect(metrics.topFivePct).toBeLessThanOrEqual(100);
    });

    it('falls back to plain segments when types is empty and still sums to ~100', () => {
        const rows = buildAllocationRows([], segments);
        const metrics = computeAllocationMetrics(rows);
        expect(rows).toHaveLength(15);
        expect(round(metrics.sumPct)).toBeCloseTo(100.0, 0);
        expect(metrics.topFivePct).toBeLessThanOrEqual(100);
        expect(metrics.stocksPct).toBe(0);
        expect(metrics.etfsPct).toBe(0);
    });

    it('is safe on an empty payload', () => {
        const rows = buildAllocationRows([], []);
        expect(rows).toEqual([]);
        const metrics = computeAllocationMetrics(rows);
        expect(metrics.sumPct).toBe(0);
        expect(metrics.topFivePct).toBe(0);
    });
});

describe('computeAllocationMetrics', () => {
    it('derives stock/etf/top5 from the real payload', () => {
        const rows = buildAllocationRows(types, segments);
        const metrics = computeAllocationMetrics(rows);
        expect(round(metrics.stocksPct)).toBeCloseTo(88.1, 0);
        expect(round(metrics.etfsPct)).toBeCloseTo(11.9, 0);
        expect(round(metrics.stocksPct + metrics.etfsPct)).toBeCloseTo(100.0, 0);
        expect(metrics.holdingsCount).toBe(125 + 18);
    });
});

describe('computeTypeShares', () => {
    it('aggregates per asset class from payload type keys (crypto and cash included)', () => {
        const multiTypes: TypeAllocationSegment[] = [
            { type: 'stock', type_label: 'Stocks', value: 131600, weight: 70.0, count: 10, gain_loss: 20000, sectors: [{ segment: 'Technology', value: 131600, weight: 100.0, count: 10, gain_loss: 20000 }] },
            { type: 'etf', type_label: 'ETFs', value: 37600, weight: 20.0, count: 4, gain_loss: 1000, sectors: [{ segment: 'Unknown', value: 37600, weight: 100.0, count: 4, gain_loss: 1000 }] },
            { type: 'crypto', type_label: 'Crypto', value: 15040, weight: 8.0, count: 3, gain_loss: -500, sectors: [{ segment: 'Bitcoin', value: 15040, weight: 100.0, count: 3, gain_loss: -500 }] },
            { type: 'cash', type_label: 'Cash', value: 3760, weight: 2.0, count: 1, gain_loss: 0, sectors: [{ segment: 'Cash', value: 3760, weight: 100.0, count: 1, gain_loss: 0 }] },
        ];
        const rows = buildAllocationRows(multiTypes, []);
        const shares = computeTypeShares(rows);
        expect(shares.map((s) => s.label)).toEqual(['Stocks', 'ETFs', 'Crypto', 'Cash']);
        expect(round(shares.reduce((sum, s) => sum + s.pct, 0))).toBeCloseTo(100.0, 0);
        expect(round(shares[0].pct)).toBeCloseTo(70.0, 0);
        expect(round(shares[2].pct)).toBeCloseTo(8.0, 0);
        expect(shares[3]).toMatchObject({ label: 'Cash', count: 1, value: 3760 });
    });

    it('returns an empty list when no type keys exist (segments fallback)', () => {
        const rows = buildAllocationRows([], segments);
        expect(computeTypeShares(rows)).toEqual([]);
    });
});