'use client';

import { useMemo } from 'react';
import { AllocationOverviewCard } from './AllocationOverviewCard';
import type { AllocationSegment, TypeAllocationSegment } from '../types/portfolio.types';

interface SectorDataPoint {
    sector: string;
    value: number;
}

interface DividendSectorChartProps {
    data: SectorDataPoint[];
    isLoading?: boolean;
}

export function DividendSectorChart({ data, isLoading }: DividendSectorChartProps) {
    const { segments, totalValue } = useMemo(() => {
        if (!data || data.length === 0) {
            return { segments: [], totalValue: 0 };
        }
        const total = data.reduce((sum, d) => sum + (d.value || 0), 0);
        const segments: AllocationSegment[] = data.map((d, i) => ({
            segment: d.sector,
            value: d.value,
            weight: total > 0 ? (d.value / total) * 100 : 0,
            count: 1,
            gain_loss: 0,
        }));
        return { segments, totalValue: total };
    }, [data]);

    if (isLoading) {
        return (
            <div className="glass-panel p-6 relative overflow-hidden">
                <div className="h-5 w-32 rounded bg-white/5 animate-pulse mb-2" />
                <div className="h-4 w-48 rounded bg-white/5 animate-pulse mb-4" />
                <div className="h-[300px] rounded-xl bg-white/[0.02]" />
            </div>
        );
    }

    if (!segments || segments.length === 0) {
        return (
            <div className="glass-panel p-6 relative overflow-hidden">
                <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
                    Income by Sector
                </p>
                <h3 className="text-base font-black text-white tracking-tight mb-4">
                    Sector &amp; Asset Classes
                </h3>
                <div className="h-[250px] flex items-center justify-center">
                    <p className="text-sm text-white/30 italic">No sector data</p>
                </div>
            </div>
        );
    }

    const types: TypeAllocationSegment[] = [];

    return (
        <AllocationOverviewCard
            types={types}
            segments={segments}
            totalValue={totalValue}
            currency={null}
        />
    );
}
