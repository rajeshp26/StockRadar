'use client';

import { useEffect, useMemo, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { AlertTriangle } from 'lucide-react';
import { AccentLine } from './DividendsSharedUI';
import { TimePeriodSelector } from './TimePeriodSelector';
import type { MonthlyDividendSummary, TimePeriod, DividendResolutionLevel } from '../types/portfolio.types';

interface DividendTrendChartProps {
    data: MonthlyDividendSummary[];
    isLoading?: boolean;
    resolution?: DividendResolutionLevel;
}

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const PERIOD_ORDER: TimePeriod[] = ['1D', '1W', '1M', '3M', '1Y', 'YTD', 'ALL'];

function getMinPeriodForResolution(resolution?: DividendResolutionLevel): TimePeriod {
    if (resolution === 'monthly') return '1M';
    if (resolution === 'weekly') return '1W';
    if (resolution === 'quarterly') return '3M';
    if (resolution === 'daily') return '1D';
    return '1W';
}

function isPeriodAllowed(period: TimePeriod, minPeriod: TimePeriod): boolean {
    const pIdx = PERIOD_ORDER.indexOf(period);
    const mIdx = PERIOD_ORDER.indexOf(minPeriod);
    if (pIdx === -1 || mIdx === -1) return true;
    return pIdx >= mIdx;
}

function filterByPeriod(data: Array<{ fiscal_year: number; fiscal_month: number; total_amount: number }>, period: TimePeriod): Array<{ fiscal_year: number; fiscal_month: number; total_amount: number }> {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1; // 1-12

    if (period === 'ALL') {
        return data;
    }
    if (period === 'YTD') {
        return data.filter((d) => d.fiscal_year === currentYear);
    }
    if (period === '1Y') {
        const result = [];
        for (let i = 0; i < 12; i++) {
            let m = currentMonth - i;
            let y = currentYear;
            if (m <= 0) {
                m += 12;
                y -= 1;
            }
            const found = data.find((d) => d.fiscal_year === y && d.fiscal_month === m);
            if (found) {
                result.push(found);
            }
        }
        return result.reverse();
    }
    if (period === '1M') {
        const found = data.filter((d) => d.fiscal_year === currentYear && d.fiscal_month === currentMonth);
        if (found.length > 0) return found;
        return data.slice(-1);
    }
    if (period === '1W') {
        return data.slice(-1);
    }
    return data;
}

export function DividendTrendChart({ data, isLoading, resolution }: DividendTrendChartProps) {
    const minPeriod = getMinPeriodForResolution(resolution);
    const [period, setPeriod] = useState<TimePeriod>(resolution === 'monthly' ? '1M' : '1Y');

    useEffect(() => {
        if (!isPeriodAllowed(period, minPeriod)) {
            setPeriod(minPeriod);
        }
    }, [minPeriod, period]);

    const filteredData = useMemo(() => {
        if (!data || data.length === 0) return [];
        const sorted = [...data].sort((a, b) => a.fiscal_year - b.fiscal_year || a.fiscal_month - b.fiscal_month);
        return filterByPeriod(sorted, period);
    }, [data, period]);

    if (isLoading) {
        return (
            <div className="glass-panel p-6 relative overflow-hidden">
                <AccentLine />
                <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
                    <div>
                        <h3 className="text-sm font-black text-white/60 uppercase tracking-widest">Monthly Dividend Income</h3>
                        <p className="text-xs text-white/35 mt-1">Portfolio income trend</p>
                    </div>
                    <div className="h-8 w-64 rounded-full bg-white/5 animate-pulse" />
                </div>
                <div className="h-[250px] rounded-xl bg-white/5 glass-shimmer" />
            </div>
        );
    }

    const chartData = filteredData
        .map((d) => {
            const now = new Date();
            const currentYear = now.getFullYear();
            const showYear = period === 'ALL' || period === '1Y' || d.fiscal_year !== currentYear;
            return {
                name: `${MONTH_LABELS[d.fiscal_month - 1] || d.fiscal_month} '${String(d.fiscal_year).slice(-2)}`,
                income: d.total_amount,
                shortName: showYear ? `${MONTH_LABELS[d.fiscal_month - 1] || d.fiscal_month}'${String(d.fiscal_year).slice(-2)}` : `${MONTH_LABELS[d.fiscal_month - 1] || d.fiscal_month}`,
            };
        });

    return (
        <div className="glass-panel p-6 overflow-visible relative">
            <AccentLine />
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
                <div>
                    <h3 className="text-sm font-black text-white/60 uppercase tracking-widest">Monthly Dividend Income</h3>
                    <p className="text-xs text-white/35 mt-1">
                        Portfolio income trend
                        {resolution && resolution !== 'daily' && (
                            <span className="ml-2 text-amber-400/80">
                                • Min period {minPeriod} (data resolution: {resolution})
                            </span>
                        )}
                    </p>
                </div>
                <TimePeriodSelector value={period} onChange={setPeriod} resolution={resolution} />
            </div>
            {resolution === 'monthly' && (
                <div className="flex items-start gap-2 mb-3 p-2.5 rounded-lg bg-amber-500/6 border border-amber-500/20">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
                    <p className="text-[11px] text-white/50 leading-relaxed">
                        Dividend data is monthly/statement level (Wealthsimple). Timeframes below 1M are disabled.
                    </p>
                </div>
            )}
            <div className="h-[250px]">
                {chartData.length === 0 ? (
                    <div className="h-full flex items-center justify-center">
                        <p className="text-sm text-white/30 italic">No dividend data for selected period</p>
                    </div>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                            <XAxis dataKey="shortName" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                            <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} tickFormatter={(val) => `$${val}`} />
                            <Tooltip
                                contentStyle={{
                                    background: "rgba(12,15,28,0.95)",
                                    border: "1px solid rgba(255,255,255,0.1)",
                                    borderRadius: "12px",
                                    backdropFilter: "blur(20px)",
                                }}
                                labelStyle={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}
                                itemStyle={{ fontSize: 13 }}
                                formatter={(value: number) => [`$${value.toFixed(2)}`, "Income"]}
                                labelFormatter={(label, payload) => {
                                    if (payload && payload[0]) {
                                        return payload[0].payload.name;
                                    }
                                    return label;
                                }}
                            />
                            <Bar dataKey="income" fill="#818cf8" radius={[4, 4, 0, 0]} maxBarSize={40} />
                        </BarChart>
                    </ResponsiveContainer>
                )}
            </div>
        </div>
    );
}
