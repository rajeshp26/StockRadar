'use client';

import { useMemo } from 'react';
import { useDividendSummary, useDividendUpcoming, useDividendHoldings, useAllDividends } from '../hooks/usePortfolio';
import { DividendsSummarySection } from './DividendsSummarySection';
import { DividendsUpcomingCard } from './DividendsUpcomingCard';
import { DividendsHoldingsSection } from './DividendsHoldingsSection';
import { DividendTrendChart } from './DividendTrendChart';
import { DividendSectorChart } from './DividendSectorChart';
import type { MonthlyDividendSummary } from '../types/portfolio.types';

interface DividendsTabProps {
    accountIds?: number[];
}

export function DividendsTab({ accountIds }: DividendsTabProps) {
    const { data: summary, isLoading: summaryLoading, error: summaryError } = useDividendSummary(accountIds);
    const { data: upcoming, isLoading: upcomingLoading, error: upcomingError } = useDividendUpcoming(accountIds);
    const { data: holdings, isLoading: holdingsLoading, error: holdingsError } = useDividendHoldings(accountIds);
    const { data: allDivs } = useAllDividends(accountIds);

    const sectorData = useMemo(() => {
        if (!holdings) return [];
        const map = new Map<string, number>();
        let total = 0;
        for (const h of holdings) {
            const sector = h.sector || 'Other';
            const fwd = h.forward_income;
            map.set(sector, (map.get(sector) || 0) + fwd);
            total += fwd;
        }
        if (total === 0) return [];
        return Array.from(map.entries())
            .map(([sector, value]) => ({ sector, value: Math.round(value * 100) / 100 }))
            .sort((a, b) => b.value - a.value);
    }, [holdings]);

    const monthlyData: MonthlyDividendSummary[] = useMemo(() => {
        if (!allDivs?.monthly_summaries) return [];
        return allDivs.monthly_summaries;
    }, [allDivs]);

    return (
        <div className="space-y-4">
            <DividendsSummarySection data={summary} isLoading={summaryLoading} error={summaryError} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-2">
                    <DividendTrendChart data={monthlyData} />
                </div>
                <div>
                    <DividendSectorChart data={sectorData} />
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-1">
                    <DividendsUpcomingCard data={upcoming} isLoading={upcomingLoading} error={upcomingError} />
                </div>
                <div className="lg:col-span-2">
                    <DividendsHoldingsSection
                        data={holdings}
                        isLoading={holdingsLoading}
                        error={holdingsError}
                        accountIds={accountIds}
                    />
                </div>
            </div>
        </div>
    );
}
