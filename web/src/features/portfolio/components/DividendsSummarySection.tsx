'use client';

import { AccentLine, SectionHeader } from './DividendsSharedUI';
import { MetricCard } from './MetricCard';
import { GoalProgressCard } from './GoalProgressCard';
import { Skeleton } from '@/components/ui/skeleton';
import type { PortfolioDividendSummary } from '../types/portfolio.types';

interface DividendsSummarySectionProps {
    data: PortfolioDividendSummary | undefined;
    isLoading: boolean;
    error: Error | null;
}

export function DividendsSummarySection({ data, isLoading, error }: DividendsSummarySectionProps) {
    if (error) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden text-center">
                <AccentLine />
                <p className="text-xs text-rose-400">Failed to load dividend summary</p>
            </div>
        );
    }

    if (isLoading || !data) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Dividend Summary" subtitle="Portfolio-level income metrics" />
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    {Array.from({ length: 6 }).map((_, i) => (
                        <div key={i} className="h-24 rounded-2xl bg-white/5 glass-shimmer" />
                    ))}
                </div>
            </div>
        );
    }

    const formatCurrency = (v: number) =>
        v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

    return (
        <div className="glass-panel p-8 relative overflow-hidden">
            <AccentLine />
            <SectionHeader title="Dividend Summary" subtitle="Portfolio-level income metrics" />
            <div className="space-y-6">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <MetricCard
                        label="Trailing 12M"
                        value={formatCurrency(data.trailing_12m_income)}
                        subtitle="actual dividends received"
                    />
                    <MetricCard
                        label="Forward Est. Annual"
                        value={formatCurrency(data.forward_annual_estimate)}
                        subtitle="shares × latest DPS × 4"
                    />
                    <MetricCard
                        label="YTD Dividends"
                        value={formatCurrency(data.ytd_dividends)}
                        subtitle="calendar year to date"
                    />
                    <MetricCard
                        label="Forward Yield on Cost"
                        value={data.forward_yield_on_cost != null ? `${data.forward_yield_on_cost.toFixed(2)}%` : '—'}
                        subtitle="dividend payers only"
                    />
                    <MetricCard
                        label="Avg Monthly (Trailing)"
                        value={formatCurrency(data.avg_monthly_trailing)}
                        subtitle="trailing 12M / 12"
                    />
                    <MetricCard
                        label="Avg Monthly (Forward)"
                        value={formatCurrency(data.avg_monthly_forward)}
                        subtitle="forward estimate / 12"
                    />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MetricCard
                        label="Portfolio Growth 5Y"
                        value={data.portfolio_growth_5yr.value != null ? `${data.portfolio_growth_5yr.value.toFixed(2)}%` : '—'}
                        subtitle="weighted avg by forward income"
                        coveragePct={data.portfolio_growth_5yr.coverage_pct}
                    />
                    <MetricCard
                        label="Portfolio Safety"
                        value={data.portfolio_safety.value != null ? data.portfolio_safety.value.toFixed(1) : '—'}
                        subtitle={`${data.portfolio_safety.value != null && data.portfolio_safety.value >= 70 ? 'safe' : data.portfolio_safety.value != null && data.portfolio_safety.value >= 40 ? 'fair' : data.portfolio_safety.value != null ? 'risky' : ''}`}
                        coveragePct={data.portfolio_safety.coverage_pct}
                    />
                    <GoalProgressCard
                        monthlyIncome={data.goal_progress?.monthly_income ?? data.avg_monthly_forward}
                        monthlyGoal={data.goal_progress?.monthly_goal ?? null}
                    />
                </div>
            </div>
        </div>
    );
}
