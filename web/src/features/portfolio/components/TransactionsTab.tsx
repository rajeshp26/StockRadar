'use client';

import { useAccountTransactionsFiltered, useAllTransactions } from '../hooks/usePortfolio';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import type { TransactionFilter } from '../types/portfolio.types';

interface TransactionsTabProps {
    accountIds?: number[];
}

const ACTIVITY_TYPES = ['', 'BUY', 'SELL', 'DIVIDEND', 'CONTRIBUTION', 'WITHDRAWAL'];
const ACTIVITY_COLORS: Record<string, string> = {
    BUY: 'text-green-400',
    SELL: 'text-red-400',
    DIVIDEND: 'text-blue-400',
    CONTRIBUTION: 'text-violet-400',
    WITHDRAWAL: 'text-amber-400',
};

export function TransactionsTab({ accountIds }: TransactionsTabProps) {
    const [filter, setFilter] = useState<TransactionFilter>({});
    const [showFilters, setShowFilters] = useState(false);

    const isAllAccounts = !accountIds || accountIds.length === 0;
    const singleAccountId = !isAllAccounts && accountIds!.length === 1 ? accountIds![0] : null;

    const { data: allData, isLoading: allLoading } = useAllTransactions(
        isAllAccounts ? undefined : accountIds, filter
    );
    const { data: perData, isLoading: perLoading } = useAccountTransactionsFiltered(singleAccountId, filter);

    const data = singleAccountId ? perData : allData;
    const isLoading = singleAccountId ? perLoading : allLoading;

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className="text-xs font-bold text-blue-400 hover:text-blue-300 transition-colors"
                >
                    {showFilters ? 'Hide Filters' : 'Show Filters'}
                </button>
            </div>

            {showFilters && (
                <div className="glass-panel rounded-lg p-4 grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label className="text-xs text-white/40 block mb-1">Activity Type</label>
                        <select
                            value={filter.activity_type || ''}
                            onChange={(e) => setFilter((f) => ({ ...f, activity_type: e.target.value || undefined }))}
                            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs text-white"
                        >
                            {ACTIVITY_TYPES.map((t) => (
                                <option key={t} value={t}>{t || 'All'}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="text-xs text-white/40 block mb-1">From</label>
                        <input
                            type="date"
                            value={filter.from_date || ''}
                            onChange={(e) => setFilter((f) => ({ ...f, from_date: e.target.value || undefined }))}
                            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs text-white"
                        />
                    </div>
                    <div>
                        <label className="text-xs text-white/40 block mb-1">To</label>
                        <input
                            type="date"
                            value={filter.to_date || ''}
                            onChange={(e) => setFilter((f) => ({ ...f, to_date: e.target.value || undefined }))}
                            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs text-white"
                        />
                    </div>
                    <div>
                        <label className="text-xs text-white/40 block mb-1">Search</label>
                        <input
                            type="text"
                            value={filter.search || ''}
                            onChange={(e) => setFilter((f) => ({ ...f, search: e.target.value || undefined }))}
                            placeholder="Symbol or description..."
                            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs text-white placeholder-white/20"
                        />
                    </div>
                </div>
            )}

            {isLoading ? (
                <Skeleton className="h-64 w-full" />
            ) : data && data.transactions.length > 0 ? (
                <div className="space-y-2">
                    {data.transactions.map((t) => (
                        <div
                            key={t.transaction_id || `${t.symbol}-${t.transaction_date}-${Math.random()}`}
                            className="glass-panel rounded-lg p-4 flex items-center justify-between"
                        >
                            <div className="flex items-center gap-3">
                                <div>
                                    <p className="text-sm font-bold text-white">{t.symbol || '—'}</p>
                                    <p className="text-xs text-white/40">{t.security_name || t.activity_type}</p>
                                    <p className="text-xs text-white/30">{t.transaction_date}</p>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className={cn(
                                    'text-sm font-bold',
                                    ACTIVITY_COLORS[t.activity_type] || 'text-white'
                                )}>
                                    {t.activity_type}
                                </p>
                                {t.net_cash_amount != null && (
                                    <p className="text-sm font-bold text-white">
                                        ${Math.abs(t.net_cash_amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="glass-panel rounded-lg p-8 text-center">
                    <p className="text-white/40 text-sm">No transactions found matching filters</p>
                </div>
            )}
        </div>
    );
}
