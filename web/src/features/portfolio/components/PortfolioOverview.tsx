// web/src/features/portfolio/components/PortfolioOverview.tsx
// UPDATE: Replace single Import button with entry selector and add manual entry option

'use client';

import { useState } from 'react';
import { TrendingUp, TrendingDown, DollarSign, PieChart, Upload, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePortfolioOverview } from '../hooks/usePortfolio';
import { PortfolioEntrySelector } from './PortfolioEntrySelector';
import { ImportTransactionsModal } from './ImportTransactionsModal';
import { ManualTradeForm } from './ManualTradeForm';
import { ACCOUNT_TYPE_COLORS } from '../types/portfolio.types';
import { cn } from '@/lib/utils';

export function PortfolioOverview() {
    const { data: overview, isLoading, error } = usePortfolioOverview();
    const [showImportModal, setShowImportModal] = useState(false);
    const [showManualForm, setShowManualForm] = useState(false);

    if (isLoading) {
        return (
            <div className="flex h-64 items-center justify-center">
                <div className="relative flex items-center justify-center">
                    <div className="h-12 w-12 rounded-full border border-white/10" />
                    <div className="absolute h-12 w-12 animate-spin rounded-full border-t-2 border-indigo-500" />
                </div>
            </div>
        );
    }

    if (error || !overview) {
        return (
            <div className="glass-panel p-8 text-center">
                <p className="text-white/40">Failed to load portfolio data</p>
                <Button
                    className="glass-button mt-4"
                    onClick={() => setShowImportModal(true)}
                >
                    <Upload className="mr-2 h-4 w-4" />
                    Import Transactions
                </Button>
            </div>
        );
    }

    // No accounts yet - show entry selector
    if (overview.accounts_count === 0) {
        return <PortfolioEntrySelector />;
    }

    const isPositive = overview.total_gain_loss >= 0;

    return (
        <div className="space-y-6">
            {/* Header with Action Buttons */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h2 className="text-2xl font-black text-white">Portfolio</h2>
                    <p className="text-sm text-white/40 mt-1">
                        {overview.accounts_count} account{overview.accounts_count !== 1 ? 's' : ''} · {overview.total_holdings_count} position{overview.total_holdings_count !== 1 ? 's' : ''}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        className="glass-button-secondary"
                        onClick={() => setShowManualForm(true)}
                    >
                        <Plus className="mr-2 h-4 w-4" />
                        Add Trade
                    </Button>
                    <Button
                        className="glass-button"
                        onClick={() => setShowImportModal(true)}
                    >
                        <Upload className="mr-2 h-4 w-4" />
                        Import CSV
                    </Button>
                </div>
            </div>

            {/* Key Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Net Worth */}
                <div className="glass-panel p-6">
                    <p className="glass-overline mb-2">Net Worth</p>
                    <div className="text-3xl font-black text-white">
                        ${overview.net_worth.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <p className="text-xs text-white/40 mt-1">
                        Cost basis: ${overview.total_cost_basis.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                </div>

                {/* Total Gain/Loss */}
                <div className={cn(
                    'glass-panel p-6',
                    isPositive && 'border-emerald-500/20',
                    !isPositive && 'border-rose-500/20'
                )}>
                    <p className="glass-overline mb-2">Total Gain/Loss</p>
                    <div className={cn(
                        'text-3xl font-black flex items-center gap-2',
                        isPositive ? 'text-emerald-400' : 'text-rose-400'
                    )}>
                        {isPositive ? (
                            <TrendingUp className="h-6 w-6" />
                        ) : (
                            <TrendingDown className="h-6 w-6" />
                        )}
                        {isPositive ? '+' : ''}${Math.abs(overview.total_gain_loss).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <p className={cn(
                        'text-xs font-bold mt-1',
                        isPositive ? 'text-emerald-400/60' : 'text-rose-400/60'
                    )}>
                        {isPositive ? '+' : ''}{overview.total_gain_loss_pct.toFixed(2)}%
                    </p>
                </div>

                {/* YTD Dividends */}
                <div className="glass-panel p-6">
                    <p className="glass-overline mb-2">YTD Dividends</p>
                    <div className="text-3xl font-black text-white flex items-center gap-2">
                        <DollarSign className="h-6 w-6" />
                        {overview.ytd_dividends.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <p className="text-xs text-white/40 mt-1">
                        {new Date().getFullYear()} year-to-date
                    </p>
                </div>

                {/* Holdings Count */}
                <div className="glass-panel p-6">
                    <p className="glass-overline mb-2">Holdings</p>
                    <div className="text-3xl font-black text-white">
                        {overview.total_holdings_count}
                    </div>
                    <p className="text-xs text-white/40 mt-1">
                        Across {overview.accounts_count} account{overview.accounts_count !== 1 ? 's' : ''}
                    </p>
                </div>
            </div>

            {/* Account Breakdown */}
            {overview.account_breakdown.length > 0 && (
                <div className="glass-panel p-6">
                    <h3 className="glass-overline mb-4">Account Breakdown</h3>
                    <div className="space-y-3">
                        {overview.account_breakdown.map((account) => {
                            const accountColor = ACCOUNT_TYPE_COLORS[account.account_type] || 'indigo';
                            const isAccountPositive = account.gain_loss >= 0;

                            return (
                                <div
                                    key={account.account_id}
                                    className="flex items-center justify-between p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.03] transition-colors"
                                >
                                    <div className="flex items-center gap-3 flex-1 min-w-0">
                                        <div className={cn(
                                            'h-10 w-10 rounded-lg flex items-center justify-center text-xs font-black ring-1',
                                            `bg-${accountColor}-500/10 text-${accountColor}-400 ring-${accountColor}-500/20`
                                        )}>
                                            {account.account_type.substring(0, 2).toUpperCase()}
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-bold text-white truncate">
                                                {account.account_name}
                                            </p>
                                            <p className="text-xs text-white/40">
                                                {account.brokerage_name} · {account.holdings_count} position{account.holdings_count !== 1 ? 's' : ''}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            ${account.total_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                        </p>
                                        <p className={cn(
                                            'text-xs font-bold',
                                            isAccountPositive ? 'text-emerald-400' : 'text-rose-400'
                                        )}>
                                            {isAccountPositive ? '+' : ''}${Math.abs(account.gain_loss).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                            {' '}({isAccountPositive ? '+' : ''}{account.gain_loss_pct.toFixed(1)}%)
                                        </p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Top Holdings */}
            {overview.top_holdings.length > 0 && (
                <div className="glass-panel p-6">
                    <h3 className="glass-overline mb-4">Top Holdings</h3>
                    <div className="space-y-2">
                        {overview.top_holdings.map((holding) => {
                            const holdingGain = (holding.current_value || 0) - holding.total_cost;
                            const isHoldingPositive = holdingGain >= 0;

                            return (
                                <div
                                    key={holding.holding_id}
                                    className="flex items-center justify-between p-3 rounded-lg hover:bg-white/[0.02] transition-colors"
                                >
                                    <div className="flex items-center gap-3 flex-1 min-w-0">
                                        <div className="h-8 w-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-[10px] font-black text-indigo-400 ring-1 ring-indigo-500/20">
                                            {holding.symbol.substring(0, 2)}
                                        </div>
                                        <div className="min-w-0">
                                            <p className="text-sm font-bold text-white">{holding.symbol}</p>
                                            <p className="text-xs text-white/40 truncate">
                                                {holding.quantity.toFixed(2)} shares @ ${holding.average_cost.toFixed(2)}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            ${(holding.current_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                        </p>
                                        <p className={cn(
                                            'text-xs font-bold',
                                            isHoldingPositive ? 'text-emerald-400' : 'text-rose-400'
                                        )}>
                                            {isHoldingPositive ? '+' : ''}${Math.abs(holdingGain).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                            {holding.unrealized_gain_loss_pct !== null && (
                                                <> ({isHoldingPositive ? '+' : ''}{holding.unrealized_gain_loss_pct.toFixed(1)}%)</>
                                            )}
                                        </p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Modals */}
            <ImportTransactionsModal
                open={showImportModal}
                onOpenChange={setShowImportModal}
            />
            <ManualTradeForm
                open={showManualForm}
                onOpenChange={setShowManualForm}
            />
        </div>
    );
}