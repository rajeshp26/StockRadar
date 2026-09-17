'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useDividendHoldingDetail } from '../hooks/usePortfolio';
import { getDateAxis, formatAxisTick } from '@/lib/chart-time-axis';
import { useChartWidth } from '@/lib/use-chart-width';

interface DividendDetailDrawerProps {
    symbol: string | null;
    accountIds?: number[];
    onClose: () => void;
}

export function DividendDetailDrawer({ symbol, accountIds, onClose }: DividendDetailDrawerProps) {
    const { ref: widthRef, width: chartWidth } = useChartWidth();
    const { data, isLoading, error } = useDividendHoldingDetail(symbol, accountIds);

    useEffect(() => {
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [onClose]);

    if (!symbol) return null;

    const formatCurrency = (v: number) =>
        v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

    const dividendChartData = data?.dividend_history.map((d) => ({ ...d, date: d.date.slice(0, 7) })) ?? [];
    const dividendAxis = getDateAxis('ALL', dividendChartData.map((d) => d.date), { widthPx: chartWidth });

    return (
        <>
            <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
            <div className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-[#0a0a1a] border-l border-white/10 z-50 overflow-y-auto">
                <div className="p-6">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-black text-white tracking-tight">{symbol}</h2>
                        <button onClick={onClose} className="text-white/40 hover:text-white/60">
                            <X className="h-5 w-5" />
                        </button>
                    </div>

                    {isLoading && (
                        <div className="space-y-4">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <div key={i} className="h-12 rounded-2xl bg-white/5 glass-shimmer" />
                            ))}
                        </div>
                    )}

                    {error && (
                        <div className="glass-panel p-8 relative overflow-hidden text-center">
                            <p className="text-xs text-rose-400">Failed to load holding details. Retry.</p>
                        </div>
                    )}

                    {data && (
                        <div className="space-y-6">
                            {/* Income Summary */}
                            <div className="glass-panel p-5 relative overflow-hidden">
                                <p className="glass-overline">Income Summary</p>
                                <div className="grid grid-cols-2 gap-3 mt-3">
                                    <MetricRow label="Trailing 12M" value={formatCurrency(data.income.trailing_12m)} />
                                    <MetricRow label="Forward Est." value={formatCurrency(data.income.forward)} />
                                    <MetricRow label="YTD" value={formatCurrency(data.income.ytd)} />
                                    <MetricRow label="Yield on Cost" value={data.income.yield_on_cost != null ? `${data.income.yield_on_cost.toFixed(2)}%` : '—'} />
                                    <MetricRow label="Market Value" value={formatCurrency(data.income.market_value)} />
                                    <MetricRow label="Cost Basis" value={formatCurrency(data.income.cost_basis)} />
                                </div>
                            </div>

                            {/* Quality Metrics */}
                            <div className="glass-panel p-5 relative overflow-hidden">
                                <p className="glass-overline">Quality Metrics</p>
                                {data.quality_metrics ? (
                                    <div className="grid grid-cols-2 gap-3 mt-3">
                                        <MetricRow label="Safety" value={data.quality_metrics.safety_score != null ? data.quality_metrics.safety_score.toFixed(1) : '—'} />
                                        <MetricRow label="Payout Ratio" value={data.quality_metrics.payout_ratio != null ? `${data.quality_metrics.payout_ratio.toFixed(1)}%` : '—'} />
                                        <MetricRow label="Growth 5Y" value={data.quality_metrics.growth_5yr != null ? `${data.quality_metrics.growth_5yr.toFixed(2)}%` : '—'} />
                                        <MetricRow label="Inc. Streak" value={data.quality_metrics.increase_streak != null ? `${data.quality_metrics.increase_streak}y` : '—'} />
                                        <MetricRow label="Current Yield" value={data.quality_metrics.current_yield != null ? `${data.quality_metrics.current_yield.toFixed(2)}%` : '—'} />
                                    </div>
                                ) : (
                                    <p className="text-sm text-white/30 italic mt-3">No quality data available</p>
                                )}
                            </div>

                            {/* Dividend History Chart */}
                            {data.dividend_history.length > 0 && (
                                <div className="glass-panel p-5 relative overflow-hidden">
                                    <p className="glass-overline">Dividend History</p>
                                    <div ref={widthRef} className="h-36 mt-3">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={dividendChartData}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                                <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} ticks={dividendAxis.ticks} tickFormatter={(val: string) => formatAxisTick(val, dividendAxis.tickFormat)} axisLine={false} tickLine={false} />
                                                <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                                                <Tooltip
                                                    contentStyle={{ backgroundColor: '#111827', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                                                />
                                                <Bar dataKey="amount" fill="#818cf8" radius={[4, 4, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* Recent Payments */}
                            {data.recent_payments.length > 0 && (
                                <div className="glass-panel p-5 relative overflow-hidden">
                                    <p className="glass-overline">Recent Payments</p>
                                    <div className="space-y-1 mt-3">
                                        {data.recent_payments.map((p, i) => (
                                            <div key={i} className="flex items-center justify-between text-xs py-2 border-b border-white/6 last:border-0">
                                                <span className="text-white/60">{p.payment_date}</span>
                                                <div className="text-right">
                                                    <span className="text-emerald-400 font-black">{formatCurrency(p.amount)}</span>
                                                    {p.shares_held != null && (
                                                        <span className="text-white/30 ml-2">{p.shares_held} shares</span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}

function MetricRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center justify-between py-1.5 border-b border-white/6 last:border-0">
            <span className="text-xs text-white/50">{label}</span>
            <span className="text-xs text-white font-black">{value}</span>
        </div>
    );
}
