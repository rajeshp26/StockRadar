'use client';

import { usePortfolioOverview, useAllHoldings } from '../hooks/usePortfolio';
import { LazyPerformanceChart } from './LazyPerformanceChart';
import { TopMovers } from './TopMovers';
import { PriceSparkline } from './PriceSparkline';
import { Skeleton } from '@/components/ui/skeleton';
import { TrendingUp, TrendingDown, DollarSign, Wallet } from 'lucide-react';

interface OverviewTabProps {
    accountIds?: number[];
}

export function OverviewTab({ accountIds }: OverviewTabProps) {
    const { data: overview, isLoading: overviewLoading } = usePortfolioOverview(accountIds);
    const { data: holdings, isLoading: holdingsLoading } = useAllHoldings();

    if (overviewLoading) {
        return (
            <div className="space-y-4">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-24 w-full rounded-lg" />
                    ))}
                </div>
                <Skeleton className="h-8 w-full rounded-lg" />
                <Skeleton className="h-64 w-full rounded-lg" />
            </div>
        );
    }

    if (!overview) {
        return (
            <div className="glass-panel rounded-lg p-8 text-center">
                <p className="text-white/40 text-sm">No portfolio data available.</p>
            </div>
        );
    }

    const cards = [
        {
            label: 'Total Value',
            value: `$${overview.net_worth.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
            icon: DollarSign,
            color: 'text-white',
        },
        {
            label: 'Total Gain/Loss',
            value: overview.total_gain_loss != null
                ? `$${overview.total_gain_loss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—',
            icon: overview.total_gain_loss != null && overview.total_gain_loss >= 0 ? TrendingUp : TrendingDown,
            color: overview.total_gain_loss != null
                ? overview.total_gain_loss >= 0 ? 'text-green-400' : 'text-red-400'
                : 'text-white/60',
        },
        {
            label: 'Gain/Loss %',
            value: overview.total_gain_loss_pct != null
                ? `${overview.total_gain_loss_pct >= 0 ? '+' : ''}${overview.total_gain_loss_pct.toFixed(2)}%`
                : '—',
            icon: overview.total_gain_loss_pct != null && overview.total_gain_loss_pct >= 0 ? TrendingUp : TrendingDown,
            color: overview.total_gain_loss_pct != null
                ? overview.total_gain_loss_pct >= 0 ? 'text-green-400' : 'text-red-400'
                : 'text-white/60',
        },
        {
            label: 'Total Dividends',
            value: overview.ytd_dividends != null
                ? `$${overview.ytd_dividends.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—',
            icon: Wallet,
            color: 'text-white',
        },
    ];

    return (
        <div className="space-y-6">
            {/* Summary Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {cards.map((card) => {
                    const Icon = card.icon;
                    return (
                        <div key={card.label} className="glass-panel rounded-lg p-4">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-white/40 font-medium uppercase tracking-wider">
                                    {card.label}
                                </p>
                                <Icon className={`h-4 w-4 ${card.color}`} />
                            </div>
                            <p className={`text-xl font-bold mt-1 ${card.color}`}>
                                {card.value}
                            </p>
                        </div>
                    );
                })}
            </div>

            {/* Account Breakdown */}
            {overview.account_breakdown && overview.account_breakdown.length > 0 && (
                <div className="glass-panel rounded-lg p-4 space-y-3">
                    <h3 className="text-xs font-black uppercase tracking-widest text-white/40">
                        Account Breakdown
                    </h3>
                    <div className="space-y-1">
                        {overview.account_breakdown.map((acct) => (
                            <div
                                key={acct.account_id}
                                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/5 transition-colors"
                            >
                                <div className="flex items-center gap-3 min-w-0">
                                    <span className="text-sm font-bold text-white">
                                        {acct.account_name}
                                    </span>
                                    <span className="text-[10px] uppercase tracking-wider text-white/30 px-2 py-0.5 rounded-full border border-white/10">
                                        {acct.account_type}
                                    </span>
                                    {acct.brokerage_name && (
                                        <span className="text-xs text-white/40 hidden sm:inline">
                                            {acct.brokerage_name}
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-4 shrink-0">
                                    <div className="text-right">
                                        <p className="text-xs text-white/50">
                                            ${acct.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                        </p>
                                        <p className="text-[10px] text-white/30">
                                            {acct.holdings_count} positions
                                        </p>
                                    </div>
                                    <div className="text-right">
                                        <p className={`text-xs font-bold ${acct.gain_loss >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {acct.gain_loss >= 0 ? '+' : ''}${acct.gain_loss.toFixed(2)}
                                        </p>
                                        <p className={`text-[10px] ${acct.gain_loss_pct >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
                                            {acct.gain_loss_pct >= 0 ? '+' : ''}{acct.gain_loss_pct.toFixed(2)}%
                                        </p>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Top Movers + Performance Chart side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Top Movers */}
                <div className="lg:col-span-1">
                    {!holdingsLoading && holdings && holdings.length > 0 && (
                        <div className="space-y-3">
                            <TopMovers holdings={holdings} />
                            {/* Sparklines for top holdings */}
                            <div className="glass-panel rounded-lg p-4 space-y-2">
                                <h3 className="text-xs font-black uppercase tracking-widest text-white/40">
                                    Price Trends
                                </h3>
                                {holdings.slice(0, 5).map((h) => (
                                    <div
                                        key={h.symbol}
                                        className="flex items-center justify-between py-1"
                                    >
                                        <span className="text-xs font-medium text-white/70">
                                            {h.symbol}
                                        </span>
                                        <PriceSparkline symbol={h.symbol} days={30} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Performance Chart — lazy loaded via IntersectionObserver */}
                <LazyPerformanceChart />
            </div>
        </div>
    );
}
