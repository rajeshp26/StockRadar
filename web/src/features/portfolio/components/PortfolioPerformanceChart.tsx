'use client';

import { useState, useEffect } from 'react';
import {
    Area,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
    Line,
    ComposedChart,
    Legend,
} from 'recharts';
import { usePortfolioPerformance, useBenchmarks, useBenchmarkCompare, usePortfolioAccounts } from '../hooks/usePortfolio';
import { TimePeriodSelector } from './TimePeriodSelector';
import { BenchmarkSelector } from '@/components/ui/benchmark-selector';
import { AccountSelector } from './AccountSelector';
import type { TimePeriod, BenchmarkCompareResponse } from '../types/portfolio.types';
import { BENCHMARK_COLORS, FALLBACK_COLORS } from '@/lib/colors';

export function PortfolioPerformanceChart() {
    const [period, setPeriod] = useState<TimePeriod>('1Y');
    const [selectedBenchmarks, setSelectedBenchmarks] = useState<string[]>([]);
    const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([]);

    const { data: accounts } = usePortfolioAccounts();
    const { data: perf, isLoading: perfLoading, isError: perfError, isFetching } = usePortfolioPerformance(period, selectedAccountIds);
    const { data: benchmarks } = useBenchmarks();
    const { data: compareData, isLoading: compareLoading, isError: compareError } = useBenchmarkCompare(period, selectedBenchmarks, selectedAccountIds);

    const loggedRef = useEffect((() => {
        console.log('[PERF] PortfolioPerformanceChart mounted — fired accounts, performance, benchmarks requests');
        return () => {};
    }) as any, []);

    useEffect(() => {
        if (accounts) console.log(`[PERF] PortfolioPerformanceChart accounts received: ${accounts.length} accounts`);
    }, [accounts]);

    useEffect(() => {
        if (perf && !perfLoading) {
            const snaps = perf.snapshots ?? [];
            console.log(`[PERF] performance_response period=${perf.period} source=${perf.data_source} rows=${snaps.length} ret=${perf.total_return_pct}%`);
            snaps.forEach(s => console.log(`[PERF]   date=${s.date} V=${s.value} ND=${s.net_deposits}`));
        }
    }, [perf, perfLoading]);

    useEffect(() => {
        if (benchmarks) console.log(`[PERF] PortfolioPerformanceChart benchmarks received: ${benchmarks.length} benchmarks`);
    }, [benchmarks]);

    const chartData = buildChartData(perf?.snapshots, compareData, selectedBenchmarks);
    if (chartData.length > 0 && !perfLoading) {
        console.log(`[PERF] chart_data period=${period} rows=${chartData.length}`);
        chartData.forEach(d => console.log(`[PERF]   date=${d.date} V=${d.portfolio} ND=${d.netDeposits}`));
    } else if (!perfLoading) {
        console.log(`[PERF] chart_data period=${period} rows=0 (empty)`);
    }
    const hasData = chartData.length > 1 && chartData.some((d) => (d.portfolio as number) > 0 || (d.netDeposits as number) > 0);
    const showBenchmarks = selectedBenchmarks.length > 0;

    if (perfError) {
        return (
            <div className="glass-panel p-6">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-black text-white/60 uppercase tracking-widest">
                        Portfolio Performance
                    </h3>
                </div>
                <div className="h-[300px] md:h-[400px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">Unable to load performance data</p>
                </div>
            </div>
        );
    }

    if (perfLoading) {
        return (
            <div className="glass-panel p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="h-5 w-32 rounded bg-white/5 animate-pulse" />
                    <div className="h-8 w-64 rounded-full bg-white/5 animate-pulse" />
                </div>
                <div className="h-[300px] rounded-xl bg-white/[0.02]" />
            </div>
        );
    }

    return (
        <div className="glass-panel p-6 overflow-visible">
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
                <h3 className="text-sm font-black text-white/60 uppercase tracking-widest">
                    Portfolio Performance
                </h3>
                <div className="flex items-center gap-3">
                    <AccountSelector
                        accounts={accounts || []}
                        selected={selectedAccountIds}
                        onChange={setSelectedAccountIds}
                    />
                    <BenchmarkSelector
                        benchmarks={benchmarks || []}
                        selected={selectedBenchmarks}
                        onToggle={(symbol) =>
                            setSelectedBenchmarks((prev) =>
                                prev.includes(symbol)
                                    ? prev.filter((s) => s !== symbol)
                                    : [...prev, symbol]
                            )
                        }
                    />
                    <TimePeriodSelector value={period} onChange={setPeriod} />
                </div>
            </div>

            {isFetching && !perfLoading && (
                <div className="h-0.5 rounded-full bg-indigo-500/30 overflow-hidden mb-2">
                    <div className="h-full w-1/3 bg-indigo-400 rounded-full animate-pulse" />
                </div>
            )}
            {perf?.spike_detected && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
                    <p className="text-xs text-amber-400/80">
                        Data quality notice: One or more data points may reflect pricing inconsistencies and could be corrected as newer data becomes available.
                    </p>
                </div>
            )}
            {perf?.data_quality_flag && perf.data_quality_flag !== 'OK' && !perf.spike_detected && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06]">
                    <p className="text-xs text-white/30">
                        Data quality: {perf.data_quality_flag.replace(/_/g, ' ').toLowerCase()}
                    </p>
                </div>
            )}
            {showBenchmarks && compareLoading && (
                <div className="mb-2 text-xs text-white/30 italic">
                    Loading benchmark data...
                </div>
            )}
            {showBenchmarks && compareError && (
                <div className="mb-2 text-xs text-red-400/60">
                    Failed to load benchmark data
                </div>
            )}
            <div className="h-[300px] md:h-[400px]">
                {hasData ? (
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={chartData}>
                            <CartesianGrid
                                strokeDasharray="3 3"
                                stroke="rgba(255,255,255,0.06)"
                            />
                            <XAxis
                                dataKey="date"
                                tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                                axisLine={false}
                                tickLine={false}
                                tickFormatter={(val: string) => {
                                    const d = new Date(val);
                                    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                                }}
                            />
                            <YAxis
                                tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                                axisLine={false}
                                tickLine={false}
                                tickFormatter={(val: number) =>
                                    val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(0)
                                }
                            />
                            <Tooltip
                                contentStyle={{
                                    background: 'rgba(12,15,28,0.95)',
                                    border: '1px solid rgba(255,255,255,0.1)',
                                    borderRadius: '12px',
                                    backdropFilter: 'blur(20px)',
                                }}
                                labelStyle={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}
                                itemStyle={{ fontSize: 13 }}
                            />
                            <Area
                                type="monotone"
                                dataKey="portfolio"
                                stroke="#818cf8"
                                fill="#818cf8"
                                fillOpacity={0.15}
                                strokeWidth={2}
                                name="Portfolio Value"
                                dot={false}
                            />
                            <Area
                                type="monotone"
                                dataKey="netDeposits"
                                stroke="#34d399"
                                fill="#34d399"
                                fillOpacity={0.1}
                                strokeWidth={2}
                                name="Net Deposits"
                                dot={false}
                            />
                            {selectedBenchmarks.map((sym, i) => (
                                <Line
                                    key={sym}
                                    type="monotone"
                                    dataKey={sym}
                                    stroke={BENCHMARK_COLORS[sym] || FALLBACK_COLORS[i % FALLBACK_COLORS.length]}
                                    strokeWidth={2}
                                    strokeDasharray="6 3"
                                    name={sym}
                                    dot={false}
                                />
                            ))}
                            <Legend
                                wrapperStyle={{
                                    fontSize: 12,
                                    color: 'rgba(255,255,255,0.5)',
                                }}
                            />
                        </ComposedChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="flex h-full items-center justify-center">
                        <p className="text-white/20 text-sm">
                            {!perf?.snapshots
                                ? 'Unable to load performance data'
                                : chartData.length <= 1
                                    ? 'Need at least 2 data points to render a chart'
                                    : 'All portfolio values are zero'}
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}

function buildChartData(
    snapshots: { date: string; value: number; cost_basis: number; net_deposits: number }[] | undefined,
    compareData: BenchmarkCompareResponse | undefined,
    selectedBenchmarks: string[]
): Record<string, unknown>[] {
    if (!snapshots || snapshots.length === 0) return [];

    if (!compareData || selectedBenchmarks.length === 0) {
        return snapshots.map((s) => ({
            date: s.date,
            portfolio: s.value,
            cost_basis: s.cost_basis,
            netDeposits: s.net_deposits,
        }));
    }

    const dateMap: Record<string, Record<string, number>> = {};
    for (const s of snapshots) {
        dateMap[s.date] = { ...dateMap[s.date], portfolio: s.value, cost_basis: s.cost_basis, netDeposits: s.net_deposits };
    }
    if (compareData.benchmarks) {
        for (const bs of compareData.benchmarks) {
            for (const point of bs.data) {
                dateMap[point.date] = { ...dateMap[point.date], [bs.symbol]: point.value };
            }
        }
    }

    const sortedDates = Object.keys(dateMap).sort();
    return sortedDates.map((date) => ({
        date,
        ...dateMap[date],
    }));
}
