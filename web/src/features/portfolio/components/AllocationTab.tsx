'use client';

import { usePortfolioAllocation } from '../hooks/usePortfolio';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useState } from 'react';

interface AllocationTabProps {
    accountIds?: number[];
}

const GROUP_BY_OPTIONS = [
    { value: 'sector', label: 'Sector' },
    { value: 'geography', label: 'Geography' },
    { value: 'account', label: 'Account Type' },
] as const;

export function AllocationTab({ accountIds }: AllocationTabProps) {
    const [groupBy, setGroupBy] = useState<string>('sector');
    const { data, isLoading } = usePortfolioAllocation(groupBy, accountIds);

    const maxWeight = data?.segments
        ? Math.max(...data.segments.map((s) => s.weight), 0)
        : 0;

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-2">
                {GROUP_BY_OPTIONS.map((opt) => (
                    <button
                        key={opt.value}
                        onClick={() => setGroupBy(opt.value)}
                        className={cn(
                            'px-4 py-1.5 rounded-full text-xs font-bold transition-all border',
                            groupBy === opt.value
                                ? 'bg-blue-600 text-white border-blue-600'
                                : 'bg-transparent text-white/60 border-white/10 hover:border-white/20 hover:text-white/80'
                        )}
                    >
                        {opt.label}
                    </button>
                ))}
            </div>

            {isLoading ? (
                <Skeleton className="h-64 w-full" />
            ) : data && data.segments.length > 0 ? (
                <div className="space-y-3">
                    {data.segments.map((segment) => (
                        <div key={segment.segment} className="glass-panel rounded-lg p-4">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <p className="text-sm font-bold text-white">{segment.segment}</p>
                                    <span className="text-xs text-white/30">({segment.count})</span>
                                </div>
                                <div className="text-right">
                                    <p className="text-sm font-bold text-white">
                                        ${segment.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </p>
                                    <p className="text-xs text-white/40">{segment.weight.toFixed(1)}%</p>
                                </div>
                            </div>
                            <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                                <div
                                    className={cn(
                                        'h-full rounded-full transition-all duration-500',
                                        segment.gain_loss >= 0 ? 'bg-green-500' : 'bg-red-500'
                                    )}
                                    style={{ width: `${maxWeight > 0 ? (segment.weight / maxWeight) * 100 : 0}%` }}
                                />
                            </div>
                            {segment.gain_loss != null && (
                                <p className={cn(
                                    'text-xs mt-1',
                                    segment.gain_loss >= 0 ? 'text-green-400' : 'text-red-400'
                                )}>
                                    {segment.gain_loss >= 0 ? '+' : ''}
                                    ${segment.gain_loss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </p>
                            )}
                        </div>
                    ))}
                </div>
            ) : (
                <div className="glass-panel rounded-lg p-8 text-center">
                    <p className="text-white/40 text-sm">No allocation data available</p>
                </div>
            )}
        </div>
    );
}
