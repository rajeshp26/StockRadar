'use client';

import { cn } from '@/lib/utils';
import { AccentLine, SectionHeader } from './DividendsSharedUI';
import type { UpcomingExDate } from '../types/portfolio.types';

interface DividendsUpcomingCardProps {
    data: UpcomingExDate[] | undefined;
    isLoading: boolean;
    error: Error | null;
}

export function DividendsUpcomingCard({ data, isLoading, error }: DividendsUpcomingCardProps) {
    if (error) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Upcoming Ex-Dates" subtitle="Expected dividend payments" />
                <p className="text-xs text-rose-400">Failed to load upcoming ex-dates</p>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Upcoming Ex-Dates" subtitle="Expected dividend payments" />
                <div className="space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="h-12 rounded-xl bg-white/5 glass-shimmer" />
                    ))}
                </div>
            </div>
        );
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Upcoming Ex-Dates" subtitle="Expected dividend payments" />
                <p className="text-sm text-white/30 italic">No upcoming ex-dates found</p>
            </div>
        );
    }

    const formatCurrency = (v: number) =>
        v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

    return (
        <div className="glass-panel p-8 relative overflow-hidden">
            <AccentLine />
            <SectionHeader title="Upcoming Ex-Dates" subtitle="Expected dividend payments" />
            <div className="space-y-1.5">
                {data.map((item, i) => (
                    <div key={`${item.symbol}-${i}`} className="flex items-center justify-between py-2 border-b border-white/6 last:border-0">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-black text-white">{item.symbol}</span>
                            <span className={cn(
                                'text-[10px] px-1.5 py-0.5 rounded-full font-black uppercase tracking-widest',
                                item.confidence === 'high' ? 'bg-emerald-500/12 border border-emerald-500/25 text-emerald-400' : item.confidence === 'medium' ? 'bg-amber-500/12 border border-amber-500/25 text-amber-400' : 'bg-rose-500/12 border border-rose-500/25 text-rose-400'
                            )}>
                                {item.trust_label ?? item.confidence}
                            </span>
                        </div>
                        <div className="text-right">
                            <p className="text-sm text-emerald-400 font-black">{formatCurrency(item.estimated_income)}</p>
                            <p className="text-[10px] text-white/30">{item.ex_dividend_date} · {formatCurrency(item.amount_per_share)}/sh</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
