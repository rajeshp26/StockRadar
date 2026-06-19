'use client';

import { DividendHoldingsTable } from './DividendHoldingsTable';
import { DividendDetailDrawer } from './DividendDetailDrawer';
import { Skeleton } from '@/components/ui/skeleton';
import { useState } from 'react';
import type { PortfolioDividendHolding } from '../types/portfolio.types';

interface DividendsHoldingsSectionProps {
    data: PortfolioDividendHolding[] | undefined;
    isLoading: boolean;
    error: Error | null;
    accountIds?: number[];
}

export function DividendsHoldingsSection({ data, isLoading, error, accountIds }: DividendsHoldingsSectionProps) {
    const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

    if (error) {
        return (
            <div className="glass-panel rounded-lg p-4 text-center">
                <p className="text-xs text-red-400">Failed to load dividend holdings</p>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full rounded-lg" />
                ))}
            </div>
        );
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel rounded-lg p-4 text-center">
                <p className="text-xs text-white/20">No dividend holdings</p>
            </div>
        );
    }

    return (
        <div className="glass-panel rounded-lg p-4">
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-3">Holdings</p>
            <DividendHoldingsTable data={data} onSelect={setSelectedSymbol} />
            <DividendDetailDrawer symbol={selectedSymbol} accountIds={accountIds} onClose={() => setSelectedSymbol(null)} />
        </div>
    );
}
