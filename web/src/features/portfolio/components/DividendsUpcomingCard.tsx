'use client';

import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import type { UpcomingExDate } from '../types/portfolio.types';

interface DividendsUpcomingCardProps {
    data: UpcomingExDate[] | undefined;
    isLoading: boolean;
    error: Error | null;
}

export function DividendsUpcomingCard({ data, isLoading, error }: DividendsUpcomingCardProps) {
    if (error) {
        return (
            <div className="glass-panel rounded-lg p-4">
                <p className="text-xs text-red-400">Failed to load upcoming ex-dates</p>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel rounded-lg p-4 space-y-2">
                <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Upcoming Ex-Dates</p>
                {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                ))}
            </div>
        );
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel rounded-lg p-4">
                <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-1">Upcoming Ex-Dates</p>
                <p className="text-xs text-white/20">No upcoming ex-dates found</p>
            </div>
        );
    }

    const formatCurrency = (v: number) =>
        v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

    return (
        <div className="glass-panel rounded-lg p-4">
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Upcoming Ex-Dates</p>
            <div className="space-y-1.5">
                {data.map((item, i) => (
                    <div key={`${item.symbol}-${i}`} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-white">{item.symbol}</span>
                            <span className={cn(
                                'text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                                item.confidence === 'high' ? 'bg-green-900/40 text-green-400' : item.confidence === 'medium' ? 'bg-yellow-900/40 text-yellow-400' : 'bg-red-900/40 text-red-400'
                            )}>
                                {item.confidence}
                            </span>
                        </div>
                        <div className="text-right">
                            <p className="text-sm text-green-400 font-bold">{formatCurrency(item.estimated_income)}</p>
                            <p className="text-[10px] text-white/30">{item.ex_dividend_date} · {formatCurrency(item.amount_per_share)}/sh</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
