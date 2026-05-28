'use client';

import { useAccountHoldings, useAllHoldings } from '../hooks/usePortfolio';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface HoldingsTabProps {
    accountIds?: number[];
}

export function HoldingsTab({ accountIds }: HoldingsTabProps) {
    const isAllAccounts = !accountIds || accountIds.length === 0;
    const { data: accountHoldings, isLoading: singleLoading } = useAccountHoldings(
        !isAllAccounts && accountIds!.length === 1 ? accountIds![0] : null
    );
    const { data: allHoldings, isLoading: allLoading } = useAllHoldings();

    const isLoading = isAllAccounts || (accountIds && accountIds.length > 1) ? allLoading : singleLoading;

    let holdingRecords: any[] = [];
    if (isAllAccounts) {
        holdingRecords = allHoldings ?? [];
    } else if (accountIds && accountIds.length === 1) {
        holdingRecords = Array.isArray(accountHoldings)
            ? accountHoldings
            : (accountHoldings?.holdings ?? []);
    } else if (accountIds && accountIds.length > 1) {
        holdingRecords = (allHoldings ?? []).filter(
            (h) => h.account_id != null && accountIds.includes(h.account_id)
        );
    }

    if (isLoading) {
        return (
            <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                ))}
            </div>
        );
    }

    if (holdingRecords.length === 0) {
        return (
            <div className="glass-panel rounded-lg p-8 text-center">
                <p className="text-white/40 text-sm">No holdings found</p>
            </div>
        );
    }

    const totalValue = holdingRecords.reduce((sum, h) => sum + (h.current_value || 0), 0);

    return (
        <div className="space-y-3">
            {holdingRecords.map((h) => {
                const value = h.current_value || 0;
                const weight = totalValue > 0 ? (value / totalValue) * 100 : 0;
                const change = h.unrealized_gain_loss_pct;

                return (
                    <div
                        key={`${h.symbol}-${h.holding_id}`}
                        className="glass-panel rounded-lg p-4 flex items-center justify-between"
                    >
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-xs font-bold text-blue-400">
                                {h.symbol?.slice(0, 2)}
                            </div>
                            <div>
                                <p className="text-sm font-bold text-white">{h.symbol}</p>
                                <p className="text-xs text-white/40">
                                    {h.quantity != null ? `${h.quantity} shares` : ''}
                                    {h.quantity != null && h.currency ? ' · ' : ''}
                                    {h.currency || ''}
                                </p>
                            </div>
                        </div>

                        <div className="flex items-center gap-6">
                            <div className="text-right">
                                <p className="text-sm font-bold text-white">
                                    ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </p>
                                <p className="text-xs text-white/40">{weight.toFixed(1)}%</p>
                            </div>
                            {change != null && (
                                <div className="text-right">
                                    <p className={cn(
                                        'text-sm font-bold',
                                        change >= 0 ? 'text-green-400' : 'text-red-400'
                                    )}>
                                        {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
