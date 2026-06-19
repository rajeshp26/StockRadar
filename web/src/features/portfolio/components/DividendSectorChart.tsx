'use client';

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

interface SectorDataPoint {
    sector: string;
    value: number;
}

interface DividendSectorChartProps {
    data: SectorDataPoint[];
    isLoading?: boolean;
}

const COLORS = ['#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

export function DividendSectorChart({ data, isLoading }: DividendSectorChartProps) {
    if (isLoading) {
        return <div className="glass-panel rounded-lg p-4 h-48 flex items-center justify-center"><p className="text-white/20 text-sm">Loading sectors...</p></div>;
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel rounded-lg p-4 h-48 flex items-center justify-center">
                <p className="text-white/20 text-sm">No sector data</p>
            </div>
        );
    }

    return (
        <div className="glass-panel rounded-lg p-4">
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-3">Income by Sector</p>
            <div className="h-48">
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
                            contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                            labelStyle={{ color: 'rgba(255,255,255,0.7)' }}
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
