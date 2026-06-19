'use client';

import { AccentLine, SectionHeader } from './DividendsSharedUI';
import { DividendHoldingsTable } from './DividendHoldingsTable';
import { DividendDetailDrawer } from './DividendDetailDrawer';
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
            <div className="glass-panel p-8 relative overflow-hidden text-center">
                <AccentLine />
                <p className="text-xs text-rose-400">Failed to load dividend holdings</p>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Holdings" subtitle="Dividend-paying positions" />
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
            <div className="glass-panel p-8 relative overflow-hidden text-center">
                <AccentLine />
                <SectionHeader title="Holdings" subtitle="Dividend-paying positions" />
                <p className="text-sm text-white/30 italic">No dividend holdings</p>
            </div>
        );
    }

    return (
        <div className="glass-panel p-8 relative overflow-hidden">
            <AccentLine />
            <SectionHeader title="Holdings" subtitle="Dividend-paying positions" />
            <DividendHoldingsTable data={data} onSelect={setSelectedSymbol} />
            <DividendDetailDrawer symbol={selectedSymbol} accountIds={accountIds} onClose={() => setSelectedSymbol(null)} />
        </div>
    );
}
