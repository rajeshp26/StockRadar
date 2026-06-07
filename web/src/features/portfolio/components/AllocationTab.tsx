'use client';

import { usePortfolioAllocation } from '../hooks/usePortfolio';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import type { TypeAllocationSegment, AllocationSegment } from '../types/portfolio.types';

interface AllocationTabProps {
    accountIds?: number[];
}

const GROUP_BY_OPTIONS = [
    { value: 'sector', label: 'Sector' },
    { value: 'geography', label: 'Geography' },
    { value: 'account', label: 'Account Type' },
] as const;

function AllocationBar({ value, weight, gainLoss, maxWeight }: {
    value: number;
    weight: number;
    gainLoss: number;
    maxWeight: number;
}) {
    return (
        <>
            <div className="flex items-center justify-between mb-2">
                <div className="text-right w-full">
                    <p className="text-sm font-bold text-white">
                        ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                    <p className="text-xs text-white/40">{weight.toFixed(1)}%</p>
                </div>
            </div>
            <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <div
                    className={cn(
                        'h-full rounded-full transition-all duration-500',
                        gainLoss >= 0 ? 'bg-green-500' : 'bg-red-500'
                    )}
                    style={{ width: `${maxWeight > 0 ? (weight / maxWeight) * 100 : 0}%` }}
                />
            </div>
            <p className={cn('text-xs mt-1', gainLoss >= 0 ? 'text-green-400' : 'text-red-400')}>
                {gainLoss >= 0 ? '+' : ''}
                ${gainLoss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
        </>
    );
}

function renderHierarchical(types: TypeAllocationSegment[]) {
    const maxTypeWeight = Math.max(...types.map((t) => t.weight), 0);

    return types.map((typeGroup) => {
        const maxSectorWeight = Math.max(...typeGroup.sectors.map((s) => s.weight), 0);

        return (
            <div key={typeGroup.type} className="space-y-2">
                <div className="glass-panel rounded-lg p-4">
                    <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                            <p className="text-sm font-bold text-white">{typeGroup.type_label}</p>
                            <span className="text-xs text-white/30">({typeGroup.count})</span>
                        </div>
                    </div>

                    <AllocationBar
                        value={typeGroup.value}
                        weight={typeGroup.weight}
                        gainLoss={typeGroup.gain_loss}
                        maxWeight={maxTypeWeight}
                    />

                    <div className="mt-3 space-y-2 pl-4 border-l border-white/10">
                        {typeGroup.sectors.map((sector) => (
                            <div key={sector.segment} className="pt-1">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <p className="text-xs font-medium text-white/80">{sector.segment}</p>
                                        <span className="text-xs text-white/20">({sector.count})</span>
                                    </div>
                                    <p className="text-xs text-white/60">{sector.weight.toFixed(1)}%</p>
                                </div>
                                <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden mt-1">
                                    <div
                                        className={cn(
                                            'h-full rounded-full transition-all duration-500',
                                            sector.gain_loss >= 0 ? 'bg-green-500/70' : 'bg-red-500/70'
                                        )}
                                        style={{ width: `${maxSectorWeight > 0 ? (sector.weight / maxSectorWeight) * 100 : 0}%` }}
                                    />
                                </div>
                                <p className={cn(
                                    'text-xs mt-0.5',
                                    sector.gain_loss >= 0 ? 'text-green-400/70' : 'text-red-400/70'
                                )}>
                                    {sector.gain_loss >= 0 ? '+' : ''}
                                    ${sector.gain_loss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        );
    });
}

function renderFlat(segments: AllocationSegment[]) {
    const maxWeight = Math.max(...segments.map((s) => s.weight), 0);

    return segments.map((segment) => (
        <div key={segment.segment} className="glass-panel rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-white">{segment.segment}</p>
                    <span className="text-xs text-white/30">({segment.count})</span>
                </div>
            </div>
            <AllocationBar
                value={segment.value}
                weight={segment.weight}
                gainLoss={segment.gain_loss}
                maxWeight={maxWeight}
            />
        </div>
    ));
}

export function AllocationTab({ accountIds }: AllocationTabProps) {
    const [groupBy, setGroupBy] = useState<string>('sector');
    const { data, isLoading } = usePortfolioAllocation(groupBy, accountIds);

    const hasHierarchical = data?.types && data.types.length > 0;
    const hasSegments = data?.segments && data.segments.length > 0;

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
            ) : hasHierarchical ? (
                <div className="space-y-3">
                    {renderHierarchical(data!.types!)}
                </div>
            ) : hasSegments ? (
                <div className="space-y-3">
                    {renderFlat(data!.segments)}
                </div>
            ) : (
                <div className="glass-panel rounded-lg p-8 text-center">
                    <p className="text-white/40 text-sm">No allocation data available</p>
                </div>
            )}
        </div>
    );
}
