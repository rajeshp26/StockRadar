'use client';

import { useState } from 'react';
import { usePortfolioAccounts } from '../hooks/usePortfolio';
import {
    useRiskMetrics,
    useDrawdown,
    useEfficientFrontier,
    useRiskContribution,
    useMarketExposure,
} from '../hooks/usePortfolio';
import { AccountSelector } from './AccountSelector';
import { TimePeriodSelector } from './TimePeriodSelector';
import { RiskMetricCard } from './RiskMetricCard';
import { DrawdownChart } from './DrawdownChart';
import { RiskContributionBar } from './RiskContributionBar';
import { EfficientFrontierChart } from './EfficientFrontierChart';
import type { TimePeriod } from '../types/portfolio.types';

export function RiskPanel() {
    const [period, setPeriod] = useState<TimePeriod>('1Y');
    const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([]);
    const [showFrontier, setShowFrontier] = useState(false);
    const [showContributions, setShowContributions] = useState(false);

    const { data: accounts } = usePortfolioAccounts();
    const { data: metrics, isLoading: metricsLoading, isError: metricsError } = useRiskMetrics(period, selectedAccountIds);
    const { data: drawdown, isLoading: ddLoading, isError: ddError } = useDrawdown(period, selectedAccountIds);
    const { data: frontier, isLoading: frontierLoading, isError: frontierError } = useEfficientFrontier(20, selectedAccountIds);
    const { data: contributions, isLoading: contribLoading, isError: contribError } = useRiskContribution(selectedAccountIds);
    const { data: exposure, isLoading: exposureLoading } = useMarketExposure(selectedAccountIds);

    const fmtPct = (val: number | null | undefined, digits: number = 2) =>
        val != null ? `${val >= 0 ? '+' : ''}${(val * 100).toFixed(digits)}%` : '—';

    const fmtNum = (val: number | null | undefined, digits: number = 2) =>
        val != null ? val.toFixed(digits) : '—';

    return (
        <div className="space-y-6">
            {/* Controls */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <h3 className="text-sm font-black text-white/60 uppercase tracking-widest">
                    Portfolio Risk Analytics
                </h3>
                <div className="flex items-center gap-3">
                    <AccountSelector
                        accounts={accounts || []}
                        selected={selectedAccountIds}
                        onChange={setSelectedAccountIds}
                    />
                    <TimePeriodSelector value={period} onChange={setPeriod} />
                </div>
            </div>

            {/* Error State */}
            {metricsError && (
                <div className="glass-panel p-6 text-center">
                    <p className="text-red-400/60 text-sm">Unable to load risk metrics</p>
                    <p className="text-white/20 text-xs mt-1">{(metrics as any)?.error || (metrics as any)?.error_code || ''}</p>
                </div>
            )}

            {/* Loading State */}
            {metricsLoading && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {[...Array(8)].map((_, i) => (
                        <div key={i} className="glass-panel rounded-lg p-4">
                            <div className="h-3 w-16 rounded bg-white/5 animate-pulse mb-2" />
                            <div className="h-7 w-24 rounded bg-white/5 animate-pulse" />
                        </div>
                    ))}
                </div>
            )}

            {/* Metric Cards */}
            {metrics && !metricsLoading && (
                <>
                    {/* Primary Metrics */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <RiskMetricCard
                            label="Sharpe Ratio"
                            value={fmtNum(metrics.sharpe_ratio)}
                            trend={metrics.sharpe_ratio >= 1 ? 'up' : metrics.sharpe_ratio >= 0 ? 'neutral' : 'down'}
                            trendLabel={metrics.sharpe_ratio >= 1 ? 'Good' : metrics.sharpe_ratio >= 0 ? 'Adequate' : 'Poor'}
                        />
                        <RiskMetricCard
                            label="Sortino Ratio"
                            value={fmtNum(metrics.sortino_ratio)}
                        />
                        <RiskMetricCard
                            label="Volatility (σ)"
                            value={fmtPct(metrics.std_deviation)}
                            subtitle="Annualized"
                            trend={metrics.std_deviation < 0.15 ? 'up' : metrics.std_deviation < 0.25 ? 'neutral' : 'down'}
                            trendLabel={metrics.std_deviation < 0.15 ? 'Low' : metrics.std_deviation < 0.25 ? 'Moderate' : 'High'}
                        />
                        <RiskMetricCard
                            label="Max Drawdown"
                            value={fmtPct(metrics.max_drawdown_pct)}
                            subtitle="Peak-to-trough"
                            trend="down"
                        />
                    </div>

                    {/* Secondary Metrics */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <RiskMetricCard
                            label="VaR (95%)"
                            value={fmtPct(metrics.value_at_risk_95)}
                            subtitle="Value at Risk"
                        />
                        <RiskMetricCard
                            label="CVaR (95%)"
                            value={fmtPct(metrics.conditional_var_95)}
                            subtitle="Expected tail loss"
                        />
                        <RiskMetricCard
                            label="Downside Dev."
                            value={fmtPct(metrics.downside_deviation)}
                        />
                        <RiskMetricCard
                            label="Beta"
                            value={fmtNum(metrics.beta, 2)}
                            subtitle={metrics.beta != null ? (metrics.beta >= 1 ? 'More volatile than market' : 'Less volatile than market') : undefined}
                            trend={metrics.beta != null ? (metrics.beta <= 1 ? 'up' : 'neutral') : undefined}
                            trendLabel={metrics.beta != null ? (metrics.beta <= 1 ? 'Defensive' : 'Aggressive') : undefined}
                        />
                        <RiskMetricCard
                            label="Alpha"
                            value={fmtPct(metrics.alpha)}
                            trend={metrics.alpha != null ? (metrics.alpha >= 0 ? 'up' : 'down') : undefined}
                            trendLabel={metrics.alpha != null ? (metrics.alpha >= 0 ? 'Outperforming' : 'Underperforming') : undefined}
                        />
                        <RiskMetricCard
                            label="Tracking Error"
                            value={fmtPct(metrics.tracking_error)}
                        />
                        <RiskMetricCard
                            label="Info Ratio"
                            value={fmtNum(metrics.information_ratio)}
                        />
                        <RiskMetricCard
                            label="Return (Period)"
                            value={fmtPct(metrics.alpha != null && metrics.tracking_error != null && metrics.information_ratio != null ? null : null)}
                            subtitle="Portfolio return for period"
                        />
                        {exposure && (
                            <RiskMetricCard
                                label="Market R²"
                                value={fmtPct(exposure.r_squared, 1)}
                                subtitle="Fit to market"
                                trend={exposure.r_squared >= 0.7 ? 'up' : exposure.r_squared >= 0.4 ? 'neutral' : 'down'}
                                trendLabel={exposure.r_squared >= 0.7 ? 'Strong' : exposure.r_squared >= 0.4 ? 'Moderate' : 'Weak'}
                            />
                        )}
                    </div>
                </>
            )}

            {/* Drawdown Chart */}
            <DrawdownChart data={drawdown} isLoading={ddLoading} isError={ddError} />

            {/* Advanced Toggle */}
            <div className="flex items-center gap-4">
                <button
                    onClick={() => setShowContributions(!showContributions)}
                    className="text-xs font-bold text-white/40 hover:text-white/60 transition-colors"
                >
                    {showContributions ? '▼' : '▶'} Risk Contribution
                </button>
                <button
                    onClick={() => setShowFrontier(!showFrontier)}
                    className="text-xs font-bold text-white/40 hover:text-white/60 transition-colors"
                >
                    {showFrontier ? '▼' : '▶'} Efficient Frontier
                </button>
            </div>

            {/* Risk Contribution */}
            {showContributions && (
                <RiskContributionBar
                    data={contributions}
                    isLoading={contribLoading}
                    isError={contribError}
                />
            )}

            {/* Efficient Frontier */}
            {showFrontier && (
                <EfficientFrontierChart
                    data={frontier}
                    isLoading={frontierLoading}
                    isError={frontierError}
                />
            )}
        </div>
    );
}
