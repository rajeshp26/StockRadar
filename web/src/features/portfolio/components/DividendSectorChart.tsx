'use client';

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { AccentLine, SectionHeader } from './DividendsSharedUI';

interface SectorDataPoint {
    sector: string;
    value: number;
}

interface DividendSectorChartProps {
    data: SectorDataPoint[];
    isLoading?: boolean;
}

const COLORS = ['#6366f1', '#22c55e', '#a855f7', '#f59e0b', '#ef4444', '#06b6d4', '#3b82f6', '#ec4899', '#14b8a6', '#f97316'];

export function DividendSectorChart({ data, isLoading }: DividendSectorChartProps) {
    if (isLoading) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Income by Sector" subtitle="Portfolio income diversification" />
                <div className="h-[250px] rounded-xl bg-white/5 glass-shimmer" />
            </div>
        );
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Income by Sector" subtitle="Portfolio income diversification" />
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-sm text-white/30 italic">No sector data</p>
                </div>
            </div>
        );
    }

    return (
        <div className="glass-panel p-8 relative overflow-hidden">
            <AccentLine />
            <SectionHeader title="Income by Sector" subtitle="Portfolio income diversification" />
            <div className="h-[250px]">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={data}
                            cx="50%"
                            cy="50%"
                            innerRadius={50}
                            outerRadius={70}
                            dataKey="value"
                            nameKey="sector"
                            paddingAngle={2}
                        >
                            {data.map((_, i) => (
                                <Cell key={i} fill={COLORS[i % COLORS.length]} />
                            ))}
                        </Pie>
                        <Tooltip
                            contentStyle={{ backgroundColor: '#111827', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                            formatter={(value: number) => [`$${value.toFixed(2)}`, "Income"]}
                        />
                        <Legend
                            wrapperStyle={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}
                        />
                    </PieChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
