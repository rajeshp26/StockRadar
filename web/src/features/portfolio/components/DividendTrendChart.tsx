'use client';

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { AccentLine, SectionHeader } from './DividendsSharedUI';
import type { MonthlyDividendSummary } from '../types/portfolio.types';

interface DividendTrendChartProps {
    data: MonthlyDividendSummary[];
    isLoading?: boolean;
}

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function DividendTrendChart({ data, isLoading }: DividendTrendChartProps) {
    if (isLoading) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Monthly Dividend Income" subtitle="Portfolio income trend" />
                <div className="h-[250px] rounded-xl bg-white/5 glass-shimmer" />
            </div>
        );
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Monthly Dividend Income" subtitle="Portfolio income trend" />
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-sm text-white/30 italic">No dividend data yet</p>
                </div>
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
        <div className="glass-panel p-8 relative overflow-hidden">
            <AccentLine />
            <SectionHeader title="Monthly Dividend Income" subtitle="Portfolio income trend" />
            <div className="h-[250px]">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                        <XAxis dataKey="name" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                        <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#111827', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                            formatter={(value: number) => [`$${value.toFixed(2)}`, "Income"]}
                        />
                        <Line type="monotone" dataKey="income" stroke="#6366f1" strokeWidth={3} dot={{ r: 4, fill: "#6366f1" }} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
