'use client';

import { useAccountDividends, useDividendHistory, useAllDividends } from '../hooks/usePortfolio';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useState } from 'react';

interface DividendsTabProps {
    accountIds?: number[];
}

type DividendView = 'summary' | 'detail';

export function DividendsTab({ accountIds }: DividendsTabProps) {
    const [view, setView] = useState<DividendView>('summary');

    const isAllAccounts = !accountIds || accountIds.length === 0;
    const singleAccountId = !isAllAccounts && accountIds!.length === 1 ? accountIds![0] : null;

    const { data: allSummary, isLoading: allSummaryLoading } = useAllDividends(
        isAllAccounts ? undefined : accountIds
    );
    const { data: perSummary, isLoading: perSummaryLoading } = useAccountDividends(singleAccountId);
    const { data: detailData, isLoading: detailLoading } = useDividendHistory(singleAccountId);

    const summaryData = singleAccountId ? perSummary : allSummary;
    const summaryLoading = singleAccountId ? perSummaryLoading : allSummaryLoading;

    const isLoading = view === 'summary' ? summaryLoading : detailLoading;
    const isDetailEmpty = view === 'detail' && (!detailData || detailData.dividends.length === 0);
    const isSummaryEmpty = view === 'summary' && (!summaryData || (isAllAccounts ? summaryData.monthly_summaries.length === 0 : (summaryData as any)?.monthly_summaries?.length === 0));

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-2">
                <button
                    onClick={() => setView('summary')}
                    className={cn(
                        'px-4 py-1.5 rounded-full text-xs font-bold transition-all border',
                        view === 'summary'
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-transparent text-white/60 border-white/10'
                    )}
                >
                    Monthly Summary
                </button>
                <button
                    onClick={() => setView('detail')}
                    className={cn(
                        'px-4 py-1.5 rounded-full text-xs font-bold transition-all border',
                        view === 'detail'
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-transparent text-white/60 border-white/10'
                    )}
                >
                    Detailed History
                </button>
            </div>

            {isLoading ? (
                <Skeleton className="h-64 w-full" />
            ) : view === 'summary' && summaryData ? (
                <MonthlySummaryView data={summaryData.monthly_summaries} />
            ) : view === 'detail' && detailData ? (
                <DetailedView data={detailData.dividends} />
            ) : isSummaryEmpty || isDetailEmpty ? (
                <div className="glass-panel rounded-lg p-8 text-center">
                    <p className="text-white/40 text-sm">No dividend data available</p>
                </div>
            ) : null}
        </div>
    );
}

function MonthlySummaryView({ data }: { data: Array<{ fiscal_year: number; fiscal_month: number; total_amount: number }> }) {
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return (
        <div className="space-y-2">
            {data.map((item) => {
                const label = `${monthNames[item.fiscal_month - 1] || item.fiscal_month} ${item.fiscal_year}`;
                return (
                    <div
                        key={`${item.fiscal_year}-${item.fiscal_month}`}
                        className="glass-panel rounded-lg p-4 flex items-center justify-between"
                    >
                        <p className="text-sm font-bold text-white">{label}</p>
                        <p className="text-sm font-bold text-green-400">
                            ${item.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </p>
                    </div>
                );
            })}
        </div>
    );
}

function DetailedView({ data }: { data: Array<{ dividend_id: number; symbol: string; company_name?: string; payment_date: string; amount: number; amount_per_share?: number; shares_held?: number }> }) {
    return (
        <div className="space-y-2">
            {data.map((item) => (
                <div
                    key={item.dividend_id}
                    className="glass-panel rounded-lg p-4 flex items-center justify-between"
                >
                    <div>
                        <p className="text-sm font-bold text-white">{item.symbol}</p>
                        {item.company_name && (
                            <p className="text-xs text-white/40">{item.company_name}</p>
                        )}
                        <p className="text-xs text-white/30">{item.payment_date}</p>
                    </div>
                    <div className="text-right">
                        <p className="text-sm font-bold text-green-400">
                            ${item.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </p>
                        {item.amount_per_share != null && (
                            <p className="text-xs text-white/40">
                                ${item.amount_per_share.toFixed(4)}/share
                            </p>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}
