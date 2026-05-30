'use client';

import { usePortfolioOverview } from '../hooks/usePortfolio';
import { PortfolioPerformanceChart } from './PortfolioPerformanceChart';
import { Skeleton } from '@/components/ui/skeleton';

interface OverviewTabProps {
    accountIds?: number[];
}

export function OverviewTab({ accountIds }: OverviewTabProps) {
    const { data: overview, isLoading: overviewLoading } = usePortfolioOverview();

    if (overviewLoading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-64 w-full" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {overview && (
                <OverviewSummaryCards overview={overview} accountIds={accountIds} />
            )}

            <PortfolioPerformanceChart />
        </div>
    );
}

function OverviewSummaryCards({
    overview,
    accountIds,
}: {
    overview: {
        net_worth: number;
        total_cost_basis?: number;
        total_gain_loss?: number;
        total_gain_loss_pct?: number;
        ytd_dividends?: number;
        accounts_count?: number;
    };
    accountIds?: number[];
}) {
    const cards = [
        {
            label: 'Total Value',
            value: `$${overview.net_worth.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        },
        {
            label: 'Total Gain/Loss',
            value: overview.total_gain_loss != null
                ? `$${overview.total_gain_loss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—',
            color: overview.total_gain_loss != null
                ? overview.total_gain_loss >= 0 ? 'text-green-400' : 'text-red-400'
                : 'text-white/60',
        },
        {
            label: 'Gain/Loss %',
            value: overview.total_gain_loss_pct != null
                ? `${overview.total_gain_loss_pct >= 0 ? '+' : ''}${overview.total_gain_loss_pct.toFixed(2)}%`
                : '—',
            color: overview.total_gain_loss_pct != null
                ? overview.total_gain_loss_pct >= 0 ? 'text-green-400' : 'text-red-400'
                : 'text-white/60',
        },
        {
            label: 'Total Dividends',
            value: overview.ytd_dividends != null
                ? `$${overview.ytd_dividends.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—',
        },
    ];

    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {cards.map((card) => (
                <div key={card.label} className="glass-panel rounded-lg p-4">
                    <p className="text-xs text-white/40 font-medium uppercase tracking-wider">
                        {card.label}
                    </p>
                    <p className={`text-xl font-bold mt-1 ${card.color || 'text-white'}`}>
                        {card.value}
                    </p>
                </div>
            ))}
        </div>
    );
}
