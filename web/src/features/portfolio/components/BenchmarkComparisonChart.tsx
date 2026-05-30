'use client';

import {
    Area,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
    ComposedChart,
    Legend,
    Line,
} from 'recharts';
import { BENCHMARK_COLORS, FALLBACK_COLORS } from '@/lib/colors';
import type { BenchmarkCompareResponse } from '../types/portfolio.types';

interface BenchmarkComparisonChartProps {
    data: BenchmarkCompareResponse;
}

export function BenchmarkComparisonChart({ data }: BenchmarkComparisonChartProps) {
    if (!data.portfolio || data.portfolio.length === 0) {
        return (
            <div className="glass-panel p-6">
                <h3 className="text-sm font-black text-white/60 uppercase tracking-widest mb-4">
                    Benchmark Comparison
                </h3>
                <div className="h-[300px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">No benchmark comparison data available</p>
                </div>
            </div>
        );
    }

    const dateMap: Record<string, Record<string, number>> = {};
    for (const pt of data.portfolio) {
        dateMap[pt.date] = { ...dateMap[pt.date], portfolio: pt.value };
    }
    if (data.benchmarks) {
        for (const bs of data.benchmarks) {
            for (const pt of bs.data) {
                dateMap[pt.date] = { ...dateMap[pt.date], [bs.symbol]: pt.value };
            }
        }
    }
    const sortedDates = Object.keys(dateMap).sort();
    const chartData = sortedDates.map((date) => ({ date, ...dateMap[date] }));

    return (
        <div className="glass-panel p-6">
            <h3 className="text-sm font-black text-white/60 uppercase tracking-widest mb-4">
                Benchmark Comparison
            </h3>
            <div className="h-[300px] md:h-[400px]">
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
                            name="Portfolio"
                            dot={false}
                        />
                        {data.benchmarks?.map((bs, i) => (
                            <Line
                                key={bs.symbol}
                                type="monotone"
                                dataKey={bs.symbol}
                                stroke={BENCHMARK_COLORS[bs.symbol] || FALLBACK_COLORS[i % FALLBACK_COLORS.length]}
                                strokeWidth={2}
                                strokeDasharray="6 3"
                                name={bs.symbol}
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
            </div>
        </div>
    );
}
