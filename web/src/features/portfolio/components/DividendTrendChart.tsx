'use client';

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { MonthlyDividendSummary } from '../types/portfolio.types';

interface DividendTrendChartProps {
    data: MonthlyDividendSummary[];
    isLoading?: boolean;
}

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function DividendTrendChart({ data, isLoading }: DividendTrendChartProps) {
    if (isLoading) {
        return <div className="glass-panel rounded-lg p-4 h-48 flex items-center justify-center"><p className="text-white/20 text-sm">Loading trend...</p></div>;
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel rounded-lg p-4 h-48 flex items-center justify-center">
                <p className="text-white/20 text-sm">No dividend data yet</p>
            </div>
        );
    }

    const chartData = [...data]
        .sort((a, b) => a.fiscal_year - b.fiscal_year || a.fiscal_month - b.fiscal_month)
        .map((d) => ({
            name: `${MONTH_LABELS[d.fiscal_month - 1] || d.fiscal_month}`,
            income: d.total_amount,
        }));

    return (
        <div className="glass-panel rounded-lg p-4">
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-3">Monthly Dividend Income</p>
            <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                        <XAxis dataKey="name" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }} axisLine={false} tickLine={false} />
                        <Tooltip
                            contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                            labelStyle={{ color: 'rgba(255,255,255,0.7)' }}
                        />
                        <Line type="monotone" dataKey="income" stroke="#22c55e" strokeWidth={2} dot={{ fill: '#22c55e', r: 3 }} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
