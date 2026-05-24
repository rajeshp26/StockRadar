"use client";

import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useStockVsIndex, useAnalysisBenchmarks } from "../hooks/useStockVsIndex";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { TrendingUp, AlertTriangle } from "lucide-react";
import { BenchmarkSelector } from "@/components/ui/benchmark-selector";
import { BENCHMARK_COLORS } from "@/lib/colors";
import {
    Metric,
    SectionHeader,
    fmtPct,
    fmtInt,
} from "./shared-ui";

function MetricSkeleton() {
    return (
        <div className="glass-stat space-y-3">
            <div className="h-2 w-16 rounded-full bg-white/10 glass-shimmer" />
            <div className="h-8 w-24 rounded-lg bg-white/10 glass-shimmer" />
        </div>
    );
}

export function StockVsIndexPanel({ symbol }: { symbol: string }) {
    const [selectedBenchmarks, setSelectedBenchmarks] = useState<string[]>(["SPY"]);
    const { data: availableBenchmarks } = useAnalysisBenchmarks();
    const { loading, error, data } = useStockVsIndex(symbol, selectedBenchmarks);

    const handleToggle = useCallback((bmSymbol: string) => {
        setSelectedBenchmarks((prev) =>
            prev.includes(bmSymbol)
                ? prev.filter((s) => s !== bmSymbol)
                : [...prev, bmSymbol]
        );
    }, []);

    const subtitle = useMemo(() => {
        if (!data) return `${3} years`;
        const primary = data.primary_index;
        const extraCount = selectedBenchmarks.length - 1;
        return extraCount > 0
            ? `vs ${primary} +${extraCount} · ${data.period_years} years`
            : `vs ${primary} · ${data.period_years} years`;
    }, [data, selectedBenchmarks]);

    const summaryCard = useMemo(() => {
        const quant = data?.quantitative;
        const visual = data?.visual;
        const combined = data?.combined_score;
        const recommendation = data?.recommendation;

        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <div
                    className="pointer-events-none absolute inset-x-0 top-0 h-px"
                    style={{
                        background:
                            "linear-gradient(90deg, transparent, rgba(99,102,241,0.5) 40%, rgba(139,92,246,0.3) 70%, transparent)",
                    }}
                    aria-hidden="true"
                />
                <SectionHeader
                    title="Market Outperformance Analysis"
                    subtitle={subtitle}
                />

                {loading ? (
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
                        {Array.from({ length: 4 }).map((_, i) => (
                            <MetricSkeleton key={i} />
                        ))}
                    </div>
                ) : (
                    <>
                        {/* Combined Score */}
                        <div className="mt-6 flex items-center gap-4 p-6 rounded-2xl bg-indigo-500/10 border border-indigo-500/20">
                            <div className="flex-1">
                                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-400/70 mb-2">
                                    Combined Score vs {data?.primary_index ?? "Index"}
                                </div>
                                <div className="text-3xl font-black text-white">
                                    {fmtInt(Math.round((combined ?? 0) * 100))}/100
                                </div>
                                <div className="text-sm text-white/60 mt-1">{recommendation}</div>
                            </div>
                            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500/20 border border-indigo-500/30">
                                <TrendingUp className="h-8 w-8 text-indigo-300" />
                            </div>
                        </div>

                        {/* Quantitative Metrics */}
                        <div className="mt-6">
                            <h3 className="text-xs font-black uppercase tracking-widest text-white/40 mb-4">
                                Quantitative Analysis
                            </h3>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <Metric label="Alpha" value={fmtPct(quant?.alpha)} accent="emerald" />
                                <Metric label="Beta" value={quant?.beta?.toFixed(2) ?? "—"} />
                                <Metric label="Sharpe Ratio" value={quant?.stock_sharpe?.toFixed(2) ?? "—"} />
                                <Metric label="Growth Score" value={`${quant?.growth_score ?? 0}/3`} />
                            </div>
                        </div>

                        {/* Visual Analysis */}
                        <div className="mt-6">
                            <h3 className="text-xs font-black uppercase tracking-widest text-white/40 mb-4">
                                Visual Signals
                            </h3>
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                                <Metric label="RS Trend" value={fmtPct(visual?.rs_trend)} />
                                <Metric label="Outperform Rate" value={fmtPct(visual?.outperform_rate)} />
                                <Metric label="Drawdown Ratio" value={visual?.dd_ratio?.toFixed(2) ?? "—"} />
                            </div>
                        </div>
                    </>
                )}
            </div>
        );
    }, [loading, data, subtitle, availableBenchmarks, selectedBenchmarks]);

    const chartsCard = useMemo(() => {
        if (!data?.charts) return null;

        const { dates, normalized_prices, relative_strength } = data.charts;
        const stock_symbol = data.symbol;
        const benchmarkSymbols = data.benchmarks.map((b) => b.symbol);

        const chartData = dates.map((date, i) => {
            const row: Record<string, any> = { date };
            row[stock_symbol] = normalized_prices[stock_symbol]?.[i];
            for (const bmSym of benchmarkSymbols) {
                row[bmSym] = normalized_prices[bmSym]?.[i];
            }
            for (const bmSym of benchmarkSymbols) {
                row[`rs_${bmSym}`] = relative_strength[bmSym]?.[i];
            }
            return row;
        });

        return (
            <div className="glass-panel p-8">
                <div className="flex items-start justify-between">
                    <SectionHeader title="Performance Charts" subtitle="Normalized to 100 at start" />
                    <BenchmarkSelector
                        benchmarks={availableBenchmarks ?? []}
                        selected={selectedBenchmarks}
                        onToggle={handleToggle}
                        label="+ Compare"
                    />
                </div>

                {/* Normalized Prices */}
                <div className="mt-6">
                    <h3 className="text-xs font-black uppercase tracking-widest text-white/40 mb-4">
                        Normalized Price Performance
                    </h3>
                    <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                            <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                            <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: "rgba(0,0,0,0.8)",
                                    border: "1px solid rgba(255,255,255,0.1)",
                                    borderRadius: "8px",
                                }}
                            />
                            <Legend />
                            <Line
                                type="monotone"
                                dataKey={stock_symbol}
                                stroke="#8b5cf6"
                                strokeWidth={2}
                                dot={false}
                                name={stock_symbol}
                            />
                            {benchmarkSymbols.map((bmSym, i) => (
                                <Line
                                    key={bmSym}
                                    type="monotone"
                                    dataKey={bmSym}
                                    stroke={BENCHMARK_COLORS[bmSym] || "#6366f1"}
                                    strokeWidth={2}
                                    strokeDasharray="6 3"
                                    dot={false}
                                    name={bmSym}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                {/* Relative Strength */}
                <div className="mt-8">
                    <h3 className="text-xs font-black uppercase tracking-widest text-white/40 mb-4">
                        Relative Strength
                    </h3>
                    <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                            <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                            <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: "rgba(0,0,0,0.8)",
                                    border: "1px solid rgba(255,255,255,0.1)",
                                    borderRadius: "8px",
                                }}
                            />
                            <Legend />
                            {benchmarkSymbols.map((bmSym, i) => (
                                <Line
                                    key={`rs_${bmSym}`}
                                    type="monotone"
                                    dataKey={`rs_${bmSym}`}
                                    stroke={BENCHMARK_COLORS[bmSym] || "#10b981"}
                                    strokeWidth={2}
                                    strokeDasharray="6 3"
                                    dot={false}
                                    name={`RS vs ${bmSym}`}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
        );
    }, [data, availableBenchmarks, handleToggle]);

    return (
        <div className="space-y-6 animate-fade-up">
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
                    <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                    <p className="text-sm text-white/60">{error}</p>
                </div>
            )}

            {summaryCard}
            {chartsCard}
        </div>
    );
}