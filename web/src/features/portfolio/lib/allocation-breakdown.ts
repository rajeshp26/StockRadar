// Pure derivation of allocation rows and metrics.
// Single source of truth for every percentage the card renders. Backend weights are
// hierarchical (types[].weight = portfolio share; types[].sectors[].weight = share
// WITHIN that type only), so rows are converted to a single normalized portfolio
// percentage (pct) that always sums to ~100 — the card can never show Top 5 > 100%.
import type { AllocationSegment, TypeAllocationSegment } from '../types/portfolio.types';

export interface AllocationRow {
    key: string;
    typeKey: string;
    type: string;
    sector: string;
    value: number;
    count: number;
    gain_loss: number;
    /** Portfolio share in percent (0-100). All rows sum to ~100 for a well-formed payload. */
    pct: number;
}

const STOCK_TYPE_KEYS = new Set(['stock', 'stocks']);
const ETF_TYPE_KEYS = new Set(['etf', 'etfs']);

export function isStockTypeKey(typeKey: string): boolean {
    return STOCK_TYPE_KEYS.has(typeKey.toLowerCase());
}

export function isEtfTypeKey(typeKey: string): boolean {
    return ETF_TYPE_KEYS.has(typeKey.toLowerCase());
}

function sharePct(weight: number, weightSum: number): number {
    return weightSum > 0 ? (weight / weightSum) * 100 : 0;
}

export function buildAllocationRows(
    types: TypeAllocationSegment[],
    segments: AllocationSegment[],
): AllocationRow[] {
    let rows: Omit<AllocationRow, 'key'>[];

    if (types.length > 0) {
        const typeWeightSum = types.reduce((sum, t) => sum + t.weight, 0);
        rows = [];
        for (const t of types) {
            const typeShare = sharePct(t.weight, typeWeightSum);
            const sectorWeightSum = t.sectors.reduce((sum, s) => sum + s.weight, 0);
            for (const s of t.sectors) {
                const withinTypePct = sharePct(s.weight, sectorWeightSum);
                rows.push({
                    typeKey: t.type,
                    type: t.type_label,
                    sector: s.segment,
                    value: s.value,
                    count: s.count,
                    gain_loss: s.gain_loss,
                    pct: typeShare * (withinTypePct / 100),
                });
            }
        }
    } else {
        const segmentWeightSum = segments.reduce((sum, s) => sum + s.weight, 0);
        rows = segments.map((s) => ({
            typeKey: 'all',
            type: 'All',
            sector: s.segment,
            value: s.value,
            count: s.count,
            gain_loss: s.gain_loss,
            pct: sharePct(s.weight, segmentWeightSum),
        }));
    }

    return rows
        .sort((a, b) => b.pct - a.pct)
        .map((row) => ({ ...row, key: `${row.typeKey}|${row.sector}` }));
}

export interface AllocationMetrics {
    stocksPct: number;
    etfsPct: number;
    topFivePct: number;
    sumPct: number;
    holdingsCount: number;
}

export function computeAllocationMetrics(rows: AllocationRow[]): AllocationMetrics {
    const sumPct = rows.reduce((sum, r) => sum + r.pct, 0);
    const topFivePct = rows.slice(0, 5).reduce((sum, r) => sum + r.pct, 0);
    const stocksPct = rows
        .filter((r) => isStockTypeKey(r.typeKey))
        .reduce((sum, r) => sum + r.pct, 0);
    const etfsPct = rows.filter((r) => isEtfTypeKey(r.typeKey)).reduce((sum, r) => sum + r.pct, 0);
    const holdingsCount = rows.reduce((sum, r) => sum + r.count, 0);
    return { stocksPct, etfsPct, topFivePct, sumPct, holdingsCount };
}

export interface TypeShare {
    key: string;
    label: string;
    pct: number;
    value: number;
    count: number;
}

/** Per-asset-class aggregation (Stocks, ETFs, Crypto, Cash, ...) from the payload's type keys. */
export function computeTypeShares(rows: AllocationRow[]): TypeShare[] {
    const byKey = new Map<string, TypeShare>();
    for (const r of rows) {
        if (r.typeKey === 'all') continue;
        const cur = byKey.get(r.typeKey);
        if (cur) {
            cur.pct += r.pct;
            cur.value += r.value;
            cur.count += r.count;
        } else {
            byKey.set(r.typeKey, { key: r.typeKey, label: r.type, pct: r.pct, value: r.value, count: r.count });
        }
    }
    return [...byKey.values()].sort((a, b) => b.pct - a.pct);
}