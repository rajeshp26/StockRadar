'use client';

import {
    Area,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
    AreaChart,
} from 'recharts';
import type { DrawdownResponse } from '../types/portfolio.types';
import { getDateAxis, formatAxisTick } from '@/lib/chart-time-axis';
import { useChartWidth } from '@/lib/use-chart-width';

interface DrawdownChartProps {
    data: DrawdownResponse | undefined;
    isLoading: boolean;
    isError: boolean;
}

export function DrawdownChart({ data, isLoading, isError }: DrawdownChartProps) {
    const { ref: widthRef, width: chartWidth } = useChartWidth();

    if (isError) {
        return (
            <div className="glass-panel p-6">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                    Drawdown
                </h4>
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">Unable to load drawdown data</p>
                </div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel p-6">
                <div className="h-5 w-24 rounded bg-white/5 animate-pulse mb-4" />
                <div className="h-[250px] rounded-xl bg-white/[0.02]" />
            </div>
        );
    }

    if (!data || !data.drawdowns || data.drawdowns.length === 0) {
        return (
            <div className="glass-panel p-6">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                    Drawdown
                </h4>
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">No drawdown data available</p>
                </div>
            </div>
        );
    }

    const maxDD = data.max_drawdown_pct;
    const maxDDStart = data.max_drawdown_start
        ? new Date(data.max_drawdown_start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : '—';
    const maxDDEnd = data.max_drawdown_end
        ? new Date(data.max_drawdown_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : '—';
    const dateAxis = getDateAxis(data.period, data.drawdowns.map((d) => d.date), { widthPx: chartWidth });

    return (
        <div className="glass-panel p-6">
            <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest">
                    Drawdown
                </h4>
                <div className="flex items-center gap-4 text-xs">
                    <span className="text-white/40">
                        Max: <span className="text-red-400 font-semibold">{(maxDD * 100).toFixed(1)}%</span>
                    </span>
                    <span className="text-white/30">
                        {maxDDStart} – {maxDDEnd}
                    </span>
                </div>
            </div>
            <div ref={widthRef} className="h-[250px]">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data.drawdowns}>
                        <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255,255,255,0.06)"
                        />
                        <XAxis
                            dataKey="date"
                            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            ticks={dateAxis.ticks}
                            tickFormatter={(val: string) => formatAxisTick(val, dateAxis.tickFormat)}
                        />
                        <YAxis
                            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={(val: number) => `${(val * 100).toFixed(0)}%`}
                            domain={['auto', 0]}
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
                            formatter={(value: number) => [`${(value * 100).toFixed(2)}%`, 'Drawdown']}
                        />
                        <defs>
                            <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <Area
                            type="monotone"
                            dataKey="drawdown_pct"
                            stroke="#ef4444"
                            fill="url(#drawdownGradient)"
                            strokeWidth={2}
                            name="Drawdown"
                            dot={false}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
