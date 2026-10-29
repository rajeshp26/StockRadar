'use client';

import { useEffect, useMemo, useState } from 'react';
import { useDividendSummary, useDividendUpcoming, useDividendHoldings, useAllDividends } from '../hooks/usePortfolio';
import { DividendsSummarySection } from './DividendsSummarySection';
import { DividendsUpcomingCard } from './DividendsUpcomingCard';
import { DividendsHoldingsSection } from './DividendsHoldingsSection';
import { DividendTrendChart } from './DividendTrendChart';
import { DividendSectorChart } from './DividendSectorChart';
import type { MonthlyDividendSummary, DividendResolutionLevel } from '../types/portfolio.types';

interface DividendsTabProps {
    accountIds?: number[];
}

export function DividendsTab({ accountIds }: DividendsTabProps) {
    const { data: summary, isLoading: summaryLoading, error: summaryError } = useDividendSummary(accountIds);
    const { data: upcoming, isLoading: upcomingLoading, error: upcomingError } = useDividendUpcoming(accountIds);
    const { data: holdings, isLoading: holdingsLoading, error: holdingsError } = useDividendHoldings(accountIds);
    const { data: allDivs } = useAllDividends(accountIds);
    const [resolution, setResolution] = useState<DividendResolutionLevel>('unknown');

    useEffect(() => {
        const fetchResolution = async () => {
            try {
                const params = accountIds && accountIds.length > 0 ? `?${accountIds.map(id => `account_ids=${id}`).join('&')}` : '';
                const res = await fetch(`/api/proxy/portfolio/dividends/resolution${params}`, {
                    credentials: 'include',
                    cache: 'no-store',
                });
                if (res.ok) {
                    const json = await res.json();
                    if (json?.effective) {
                        setResolution(json.effective);
                        return;
                    }
                }
                // Fallback to analysis endpoint for any symbol with dividends
                try {
                    const res2 = await fetch('/api/proxy/analysis/V/dividend', {
                        credentials: 'include',
                        cache: 'no-store',
                    });
                    if (res2.ok) {
                        const json2 = await res2.json();
                        if (json2?.data_resolution?.effective) {
                            setResolution(json2.data_resolution.effective);
                        }
                    }
                } catch {
                    // ignore
                }
            } catch {
                // ignore
            }
        };
        fetchResolution();
    }, [accountIds]);

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
        <div className="space-y-6 animate-fade-up">
            {/* Page Header */}
            <div className="flex justify-between items-start gap-5 flex-wrap">
                <div>
                    <h1 className="text-2xl font-black text-white tracking-tight">Dividend Dashboard</h1>
                    <p className="text-sm text-white/35 mt-1">
                        Portfolio-level dividend income, upcoming payments, and holdings analysis.
                    </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                    {["Summary", "Trend", "Upcoming", "Holdings"].map((chip) => (
                        <span key={chip} className="glass-chip">{chip}</span>
                    ))}
                </div>
            </div>

            <DividendsSummarySection data={summary} isLoading={summaryLoading} error={summaryError} />

            <div className="space-y-4">
                <DividendTrendChart data={monthlyData} resolution={resolution} />
                <DividendSectorChart data={sectorData} />
            </div>

            <DividendsUpcomingCard data={upcoming} isLoading={upcomingLoading} error={upcomingError} />

            <DividendsHoldingsSection
                data={holdings}
                isLoading={holdingsLoading}
                error={holdingsError}
                accountIds={accountIds}
            />
        </div>
    );
}
