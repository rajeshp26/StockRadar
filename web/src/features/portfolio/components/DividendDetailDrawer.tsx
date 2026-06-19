'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useDividendHoldingDetail } from '../hooks/usePortfolio';

interface DividendDetailDrawerProps {
    symbol: string | null;
    accountIds?: number[];
    onClose: () => void;
}

export function DividendDetailDrawer({ symbol, accountIds, onClose }: DividendDetailDrawerProps) {
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

    return (
        <>
            <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
            <div className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-gray-900 border-l border-white/10 z-50 overflow-y-auto">
                <div className="p-4">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-bold text-white">{symbol}</h2>
                        <button onClick={onClose} className="text-white/40 hover:text-white/60">
                            <X className="h-5 w-5" />
                        </button>
                    </div>

                    {isLoading && (
                        <div className="space-y-3">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <Skeleton key={i} className="h-12 w-full" />
                            ))}
                        </div>
                    )}

                    {error && (
                        <div className="glass-panel rounded-lg p-4 text-center">
                            <p className="text-xs text-red-400">Failed to load holding details. Retry.</p>
                        </div>
                    )}

                    {data && (
                        <div className="space-y-4">
                            {/* Income Summary */}
                            <div className="glass-panel rounded-lg p-3">
                                <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Income Summary</p>
                                <div className="grid grid-cols-2 gap-2">
                                    <MetricRow label="Trailing 12M" value={formatCurrency(data.income.trailing_12m)} />
                                    <MetricRow label="Forward Est." value={formatCurrency(data.income.forward)} />
                                    <MetricRow label="YTD" value={formatCurrency(data.income.ytd)} />
                                    <MetricRow label="Yield on Cost" value={data.income.yield_on_cost != null ? `${data.income.yield_on_cost.toFixed(2)}%` : '—'} />
                                    <MetricRow label="Market Value" value={formatCurrency(data.income.market_value)} />
                                    <MetricRow label="Cost Basis" value={formatCurrency(data.income.cost_basis)} />
                                </div>
                            </div>

                            {/* Quality Metrics */}
                            <div className="glass-panel rounded-lg p-3">
                                <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Quality Metrics</p>
                                {data.quality_metrics ? (
                                    <div className="grid grid-cols-2 gap-2">
                                        <MetricRow label="Safety" value={data.quality_metrics.safety_score != null ? data.quality_metrics.safety_score.toFixed(1) : '—'} />
                                        <MetricRow label="Payout Ratio" value={data.quality_metrics.payout_ratio != null ? `${data.quality_metrics.payout_ratio.toFixed(1)}%` : '—'} />
                                        <MetricRow label="Growth 5Y" value={data.quality_metrics.growth_5yr != null ? `${data.quality_metrics.growth_5yr.toFixed(2)}%` : '—'} />
                                        <MetricRow label="Inc. Streak" value={data.quality_metrics.increase_streak != null ? `${data.quality_metrics.increase_streak}y` : '—'} />
                                        <MetricRow label="Current Yield" value={data.quality_metrics.current_yield != null ? `${data.quality_metrics.current_yield.toFixed(2)}%` : '—'} />
                                    </div>
                                ) : (
                                    <p className="text-xs text-white/20">No quality data available</p>
                                )}
                            </div>

                            {/* Dividend History Chart */}
                            {data.dividend_history.length > 0 && (
                                <div className="glass-panel rounded-lg p-3">
                                    <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Dividend History</p>
                                    <div className="h-32">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={data.dividend_history.map((d) => ({ ...d, date: d.date.slice(0, 7) }))}>
                                                <XAxis dataKey="date" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                                                <YAxis tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                                                <Tooltip
                                                    contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                                                />
                                                <Bar dataKey="amount" fill="#22c55e" radius={[2, 2, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* Recent Payments */}
                            {data.recent_payments.length > 0 && (
                                <div className="glass-panel rounded-lg p-3">
                                    <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Recent Payments</p>
                                    <div className="space-y-1">
                                        {data.recent_payments.map((p, i) => (
                                            <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-white/5 last:border-0">
                                                <span className="text-white/60">{p.payment_date}</span>
                                                <div className="text-right">
                                                    <span className="text-green-400 font-medium">{formatCurrency(p.amount)}</span>
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
        <div className="flex items-center justify-between">
            <span className="text-xs text-white/40">{label}</span>
            <span className="text-xs text-white font-medium">{value}</span>
        </div>
    );
}
