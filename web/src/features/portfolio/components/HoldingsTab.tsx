'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAccountHoldings, useAllHoldings, useAggregatedHoldings, usePortfolioAllocation } from '../hooks/usePortfolio';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { AllocationDonutCard } from './AllocationDonutCard';
import { ChevronDown, ChevronRight, ArrowLeft, BarChart2 } from 'lucide-react';
import type { AggregatedHolding } from '../types/portfolio.types';
import { formatCurrency, getCurrencySymbol } from '@/lib/currency';

interface HoldingsTabProps {
    accountIds?: number[];
}

type ViewMode = 'flat' | 'grouped';

export function HoldingsTab({ accountIds }: HoldingsTabProps) {
    const router = useRouter();
    const isAllAccounts = !accountIds || accountIds.length === 0;
    const { data: accountHoldings, isLoading: singleLoading } = useAccountHoldings(
        !isAllAccounts && accountIds!.length === 1 ? accountIds![0] : null
    );
    const { data: allHoldings, isLoading: allLoading } = useAllHoldings();
    const { data: aggHoldings, isLoading: aggLoading } = useAggregatedHoldings();
    const { data: allocation, isLoading: allocationLoading } = usePortfolioAllocation('sector', accountIds);

    const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<ViewMode>('grouped');
    const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

    const isLoading = (isAllAccounts || (accountIds && accountIds.length > 1) ? allLoading : singleLoading);

    let holdingRecords: any[] = [];
    if (viewMode === 'flat') {
        if (isAllAccounts) {
            holdingRecords = allHoldings ?? [];
        } else if (accountIds && accountIds.length === 1) {
            holdingRecords = Array.isArray(accountHoldings)
                ? accountHoldings
                : (accountHoldings?.holdings ?? []);
        } else if (accountIds && accountIds.length > 1) {
            holdingRecords = (allHoldings ?? []).filter(
                (h) => h.account_id != null && accountIds.includes(h.account_id)
            );
        }
    } else {
        holdingRecords = aggHoldings ?? [];
    }

    const displayHoldings = selectedSegment
        ? holdingRecords.filter((h: any) => {
            const parts = selectedSegment.split(' / ');
            const sectorKey = parts.length > 1 ? parts[1] : parts[0];
            const hSector = h.sector || 'Unknown';
            return hSector === sectorKey;
        })
        : holdingRecords;

    const segmentTotalValue = displayHoldings.reduce((sum: number, h: any) => sum + (h.current_value || 0), 0);

    if (isLoading || aggLoading) {
        return (
            <div className="space-y-4">
                <AllocationDonutCard
                    segments={[]}
                    totalValue={0}
                    isLoading
                    onSegmentClick={() => {}}
                />
                <div className="space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => (
                        <Skeleton key={i} className="h-16 w-full" />
                    ))}
                </div>
            </div>
        );
    }

    if (holdingRecords.length === 0 && !selectedSegment) {
        return (
            <div className="space-y-4">
                <AllocationDonutCard
                    segments={allocation?.segments ?? []}
                    totalValue={allocation?.total_value ?? 0}
                    isLoading={allocationLoading}
                    selectedSegment={selectedSegment}
                    onSegmentClick={setSelectedSegment}
                />
                <div className="glass-panel rounded-lg p-8 text-center">
                    <p className="text-white/40 text-sm">No holdings found</p>
                </div>
            </div>
        );
    }

    const totalValue = holdingRecords.reduce((sum: number, h: any) => sum + (h.current_value || 0), 0);

    return (
        <div className="space-y-4">
            <AllocationDonutCard
                segments={allocation?.segments ?? []}
                totalValue={allocation?.total_value ?? 0}
                isLoading={allocationLoading}
                selectedSegment={selectedSegment}
                onSegmentClick={setSelectedSegment}
            />

            {/* View mode toggle */}
            <div className="flex items-center gap-2">
                <button
                    onClick={() => setViewMode('flat')}
                    className={cn(
                        'px-4 py-1.5 rounded-full text-xs font-bold transition-all border',
                        viewMode === 'flat'
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-transparent text-white/60 border-white/10 hover:border-white/20 hover:text-white/80'
                    )}
                >
                    Per Account
                </button>
                <button
                    onClick={() => setViewMode('grouped')}
                    className={cn(
                        'px-4 py-1.5 rounded-full text-xs font-bold transition-all border',
                        viewMode === 'grouped'
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-transparent text-white/60 border-white/10 hover:border-white/20 hover:text-white/80'
                    )}
                >
                    Grouped by Symbol
                </button>
            </div>

            {/* Sector header when a donut segment is selected */}
            {selectedSegment && (
                <div className="flex items-center gap-3 pb-1">
                    <button
                        onClick={() => setSelectedSegment(null)}
                        className="flex items-center gap-1.5 text-xs font-bold text-indigo-400/60 hover:text-indigo-400 transition-colors"
                    >
                        <ArrowLeft className="h-3.5 w-3.5" />
                        All Sectors
                    </button>
                    <span className="text-white/20">|</span>
                    <h3 className="text-sm font-bold text-white">{selectedSegment}</h3>
                    <span className="text-xs text-white/30">
                        {displayHoldings.length} holding{displayHoldings.length !== 1 ? 's' : ''}
                        {segmentTotalValue > 0 && ` · ${formatCurrency(segmentTotalValue, displayHoldings[0]?.value_currency || displayHoldings[0]?.currency)}`}
                    </span>
                </div>
            )}

            {viewMode === 'flat' ? (
                <div className="space-y-3">
                    {displayHoldings.map((h: any) => {
                        const value = h.current_value || 0;
                        const weight = totalValue > 0 ? (value / totalValue) * 100 : 0;
                        const change = h.unrealized_gain_loss_pct;
                        return (
                            <div
                                key={`${h.symbol}-${h.holding_id}`}
                                className="glass-panel rounded-lg p-4 flex items-center justify-between"
                            >
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-xs font-bold text-blue-400">
                                        {h.symbol?.slice(0, 2)}
                                    </div>
                                    <div>
                                        <p className="text-sm font-bold text-white">{h.symbol}</p>
                                        <p className="text-xs text-white/40">
                                            {h.quantity != null ? `${h.quantity} shares` : ''}
                                            {h.quantity != null && h.currency ? ' · ' : ''}
                                            {h.currency || ''}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-6">
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            {formatCurrency(value, h.value_currency || h.currency)}
                                        </p>
                                        <p className="text-xs text-white/40">{weight.toFixed(1)}%</p>
                                    </div>
                                    {change != null && (
                                        <div className="text-right">
                                            <p className={cn('text-sm font-bold', change >= 0 ? 'text-green-400' : 'text-red-400')}>
                                                {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                                            </p>
                                        </div>
                                    )}
                                    <button
                                        onClick={() => router.push(`/analysis/${h.symbol}`)}
                                        className="flex items-center justify-center w-7 h-7 rounded-lg hover:bg-white/10 transition-colors text-white/30 hover:text-blue-400"
                                        title="View analysis"
                                    >
                                        <BarChart2 className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            ) : (
                <div className="space-y-2">
                    {/* Column header row — visible on wider screens */}
                    <div className="hidden md:grid text-[11px] font-bold text-white/30 uppercase tracking-wider px-4 py-1"
                        style={{
                            gridTemplateColumns: '32px 1fr 100px 90px 90px 130px 130px 32px 20px',
                            gap: '8px',
                        }}
                    >
                        <div />
                        <div>Symbol / Company</div>
                        <div className="text-right">Shares</div>
                        <div className="text-right">Price</div>
                        <div className="text-right">Avg Cost</div>
                        <div className="text-right">Value</div>
                        <div className="text-right">Gain / Loss</div>
                        <div />
                        <div />
                    </div>

                    {(displayHoldings as AggregatedHolding[]).map((h) => {
                        const isExpanded = expandedSymbol === h.symbol;
                        const value = h.current_value || 0;
                        const segWeight = segmentTotalValue > 0 ? (value / segmentTotalValue) * 100 : 0;
                        const allWeight = totalValue > 0 ? (value / totalValue) * 100 : 0;
                        const weight = selectedSegment ? segWeight : allWeight;

                        return (
                            <div key={`agg-${h.symbol}`} className="glass-panel rounded-lg overflow-hidden">
                                <div
                                    className="p-4 cursor-pointer hover:bg-white/[0.04] transition-colors"
                                    onClick={() => setExpandedSymbol(isExpanded ? null : h.symbol)}
                                    role="button"
                                    tabIndex={0}
                                    onKeyDown={(e) => { if (e.key === 'Enter') setExpandedSymbol(isExpanded ? null : h.symbol); }}
                                    style={{
                                        display: 'grid',
                                        gridTemplateColumns: '32px 1fr 100px 90px 90px 130px 130px 32px 20px',
                                        gap: '8px',
                                        alignItems: 'center',
                                    }}
                                >
                                    {/* Icon */}
                                    <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-xs font-bold text-blue-400">
                                        {h.symbol?.slice(0, 2)}
                                    </div>

                                    {/* Symbol / Company */}
                                    <div className="min-w-0">
                                        <p className="text-sm font-bold text-white">{h.symbol}</p>
                                        <p className="text-xs text-white/40 truncate max-w-[180px]">
                                            {h.company_name}
                                        </p>
                                    </div>

                                    {/* Shares */}
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            {h.total_quantity.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                        </p>
                                    </div>

                                    {/* Current price */}
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            {h.current_price != null ? formatCurrency(h.current_price, h.currency, { maximumFractionDigits: 2 }) : '\u2014'}
                                        </p>
                                    </div>

                                    {/* Avg cost */}
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            {h.average_cost > 0 ? formatCurrency(h.average_cost, h.currency, { maximumFractionDigits: 2 }) : '\u2014'}
                                        </p>
                                    </div>

                                    {/* Value */}
                                    <div className="text-right">
                                        <p className="text-sm font-bold text-white">
                                            {formatCurrency(value, h.currency)}
                                        </p>
                                        <p className="text-xs text-white/40">{weight.toFixed(1)}%</p>
                                    </div>

                                    {/* Gain / Loss */}
                                    <div className="text-right">
                                        <p className={cn('text-sm font-bold', h.unrealized_gain_loss >= 0 ? 'text-green-400' : 'text-red-400')}>
                                            {h.unrealized_gain_loss >= 0 ? '+' : ''}
                                            {formatCurrency(Math.abs(h.unrealized_gain_loss), h.currency)}
                                        </p>
                                        <p className={cn('text-xs', h.unrealized_gain_loss >= 0 ? 'text-green-400/60' : 'text-red-400/60')}>
                                            {h.unrealized_gain_loss >= 0 ? '+' : ''}{h.unrealized_gain_loss_pct.toFixed(2)}%
                                        </p>
                                    </div>

                                    {/* Analyze */}
                                    <div className="flex justify-center">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); router.push(`/analysis/${h.symbol}`); }}
                                            className="flex items-center justify-center w-7 h-7 rounded-lg hover:bg-white/10 transition-colors text-white/30 hover:text-blue-400"
                                            title="View analysis"
                                        >
                                            <BarChart2 className="h-4 w-4" />
                                        </button>
                                    </div>

                                    {/* Chevron */}
                                    <div className="flex-shrink-0">
                                        {isExpanded
                                            ? <ChevronDown className="h-4 w-4 text-white/30" />
                                            : <ChevronRight className="h-4 w-4 text-white/30" />
                                        }
                                    </div>
                                </div>

                                {/* Per-account breakdown */}
                                {isExpanded && (
                                    <div className="border-t border-white/5 bg-white/[0.02] px-4 py-3 space-y-2">
                                        <p className="text-[11px] font-bold text-white/30 uppercase tracking-wider">
                                            Across {h.accounts_count} account{h.accounts_count !== 1 ? 's' : ''}
                                        </p>
                                        {h.account_breakdown.map((b) => {
                                            const bWeight = h.total_quantity > 0 ? (b.quantity / h.total_quantity) * 100 : 0;
                                            return (
                                                <div key={b.account_id} className="flex items-center justify-between text-xs pl-1">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-white/50">{b.account_name || `Account #${b.account_id}`}</span>
                                                        <span className="text-white/30">
                                                            {b.quantity.toLocaleString(undefined, { maximumFractionDigits: 2 })} shares
                                                        </span>
                                                    </div>
                                                    <div className="flex items-center gap-4">
                                                        <span className="text-white/40">({bWeight.toFixed(1)}%)</span>
                                                        <span className="text-white/60 font-medium">
                                                            {formatCurrency(b.total_cost, h.currency)}
                                                        </span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
