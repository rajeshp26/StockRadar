// web/src/lib/compact-number.ts
//
// Compact scale-aware formatting for chart axis ticks ("20k", "1.5M", "2B").
//
// The previous inline formatter in PortfolioPerformanceChart rendered every
// value ≥ 1,000 as `(x/1000).toFixed(1) + "k"` — producing "20.0k", "100.0k",
// and, past seven figures, "1500.0k". This module adds the M/B tiers and
// strips the trailing ".0" so axis labels read like a finance dashboard:
//
//   0 → "0"        1,500    → "1.5k"      1,234,567 → "1.2M"
//   500 → "500"    20,000   → "20k"       12,000,000 → "12.0M" -> "12M"
//   977 → "977"    197,667  → "197.7k"    1e9+      → "1B"
//   1,000 → "1k"   1,000,000 → "1M"

export function formatAxisNumber(value: number): string {
    const abs = Math.abs(value);
    if (abs >= 1_000_000_000) return withUnit(value, 1_000_000_000, "B");
    if (abs >= 1_000_000) return withUnit(value, 1_000_000, "M");
    if (abs >= 1_000) return withUnit(value, 1_000, "k");
    return String(Math.round(value));
}

function withUnit(value: number, divisor: number, unit: string): string {
    const trimmed = (value / divisor).toFixed(1).replace(/\.0$/, "");
    return `${trimmed}${unit}`;
}