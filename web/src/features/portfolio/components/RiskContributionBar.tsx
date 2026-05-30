'use client';

import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
} from 'recharts';
import type { RiskContributionResponse } from '../types/portfolio.types';

interface RiskContributionBarProps {
    data: RiskContributionResponse | undefined;
    isLoading: boolean;
    isError: boolean;
}

export function RiskContributionBar({ data, isLoading, isError }: RiskContributionBarProps) {
    if (isError) {
        return (
            <div className="glass-panel p-6">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                    Risk Contribution
                </h4>
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">Unable to load risk contribution</p>
                </div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel p-6">
                <div className="h-5 w-32 rounded bg-white/5 animate-pulse mb-4" />
                <div className="h-[250px] rounded-xl bg-white/[0.02]" />
            </div>
        );
    }

    if (!data || !data.contributions || data.contributions.length === 0) {
        return (
            <div className="glass-panel p-6">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                    Risk Contribution
                </h4>
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">No contribution data available</p>
                </div>
            </div>
        );
    }

    const chartData = [...data.contributions]
        .sort((a, b) => b.risk_pct - a.risk_pct)
        .slice(0, 15)
        .map((c) => ({
            name: c.symbol,
            risk: +(c.risk_pct * 100).toFixed(1),
            weight: +(c.weight * 100).toFixed(1),
        }));

    return (
        <div className="glass-panel p-6">
            <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                Risk Contribution
            </h4>
            <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical" margin={{ left: 40, right: 20 }}>
                        <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255,255,255,0.06)"
                            horizontal={false}
                        />
                        <XAxis
                            type="number"
                            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={(val: number) => `${val}%`}
                            domain={[0, 'auto']}
                        />
                        <YAxis
                            type="category"
                            dataKey="name"
                            tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            width={60}
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
                            formatter={(value: number, name: string) => [
                                `${value}%`,
                                name === 'risk' ? 'Risk Contribution' : 'Portfolio Weight',
                            ]}
                        />
                        <Bar
                            dataKey="risk"
                            fill="#f59e0b"
                            radius={[0, 4, 4, 0]}
                            name="risk"
                        />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
