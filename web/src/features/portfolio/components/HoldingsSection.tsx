'use client';

import { useState, useMemo, useEffect } from 'react';
import { Search, ChevronDown, ChevronRight, LayoutGrid, List } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAllHoldings } from '../hooks/usePortfolio';
import { useStaggeredReveal } from '../hooks/useStaggeredReveal';
import type { Holding } from '../types/portfolio.types';

type GroupBy = 'none' | 'account' | 'sector' | 'market';
type SortBy = 'value' | 'gain' | 'quantity' | 'symbol';
type ViewMode = 'table' | 'card';

const MARKET_BADGE_COLORS: Record<string, string> = {
    US: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    CA: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    INTL: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    OTHER: 'bg-white/5 text-white/30 border-white/10',
};

export function HoldingsSection() {
    const { data: holdings, isLoading, error } = useAllHoldings();
    const [search, setSearch] = useState('');
    const [searchOpen, setSearchOpen] = useState(false);
    const searchInputRef = useState<HTMLInputElement | null>(null);
    const [groupBy, setGroupBy] = useState<GroupBy>('none');
    const [sortBy, setSortBy] = useState<SortBy>('value');
    const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
    const [showAll, setShowAll] = useState(false);
    const [viewMode, setViewMode] = useState<ViewMode>('table');
    const [isMobile, setIsMobile] = useState(false);

    useEffect(() => {
        const check = () => setIsMobile(window.innerWidth < 768);
        check();
        window.addEventListener('resize', check);
        return () => window.removeEventListener('resize', check);
    }, []);

    const effectiveView = isMobile ? 'card' : viewMode;
    const INITIAL_VISIBLE = isMobile ? 5 : 10;

    const filtered = useMemo(() => {
        if (!holdings) return [];
        let items = [...holdings];

        if (search) {
            const q = search.toLowerCase();
            items = items.filter(
                (h) =>
                    h.symbol.toLowerCase().includes(q) ||
                    h.company_name.toLowerCase().includes(q)
            );
        }

        items.sort((a, b) => {
            switch (sortBy) {
                case 'value':
                    return (b.current_value || 0) - (a.current_value || 0);
                case 'gain': {
                    const aGain = (a.current_value || 0) - a.total_cost;
                    const bGain = (b.current_value || 0) - b.total_cost;
                    return bGain - aGain;
                }
                case 'quantity':
                    return b.quantity - a.quantity;
                case 'symbol':
                    return a.symbol.localeCompare(b.symbol);
                default:
                    return 0;
            }
        });

        return items;
    }, [holdings, search, sortBy]);

    const grouped = useMemo(() => {
        if (groupBy === 'none') return null;

        const groups: Record<string, Holding[]> = {};
        for (const h of filtered) {
            let key = 'Other';
            if (groupBy === 'account') key = h.account_name || 'Unknown Account';
            else if (groupBy === 'sector') key = h.sector || 'Unknown';
            else if (groupBy === 'market') key = h.market_group || 'OTHER';
            if (!groups[key]) groups[key] = [];
            groups[key].push(h);
        }
        return groups;
    }, [filtered, groupBy]);

    const visibleFiltered = showAll ? filtered : filtered.slice(0, INITIAL_VISIBLE);
    const { visible: staggeredItems, isComplete } = useStaggeredReveal(visibleFiltered, 40);

    const toggleGroup = (key: string) => {
        setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    if (isLoading) {
        return (
            <div className="glass-panel p-6">
                <div className="h-5 w-24 rounded bg-white/5 animate-pulse mb-6" />
                {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-4 py-3">
                        <div className="h-8 w-8 rounded-lg bg-white/5 animate-pulse" />
                        <div className="flex-1 space-y-1">
                            <div className="h-4 w-20 rounded bg-white/5 animate-pulse" />
                            <div className="h-3 w-32 rounded bg-white/5 animate-pulse" />
                        </div>
                        <div className="h-4 w-16 rounded bg-white/5 animate-pulse" />
                    </div>
                ))}
            </div>
        );
    }

    if (error || !holdings) {
        return (
            <div className="glass-panel p-6 text-center">
                <p className="text-white/30 text-sm">Failed to load holdings</p>
            </div>
        );
    }

    if (holdings.length === 0) return null;

    const showFilteredEmpty = search && filtered.length === 0;

    return (
        <div className="glass-panel p-6">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
                <h3 className="text-sm font-black text-white/60 uppercase tracking-widest">
                    Holdings
                    <span className="ml-2 text-white/20 font-normal normal-case">
                        {search ? `${filtered.length} of ${holdings.length}` : `(${holdings.length})`}
                    </span>
                </h3>

                <div className="flex items-center gap-2">
                    {/* Search */}
                    <div className="relative">
                        {searchOpen && (
                            <input
                                ref={(el) => { if (el) searchInputRef[1](el); }}
                                type="text"
                                placeholder="Search symbol or name..."
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                onBlur={() => { if (!search) setSearchOpen(false); }}
                                autoFocus
                                className="glass-input py-1.5 pl-8 pr-3 text-xs w-36 animate-fade-in"
                            />
                        )}
                        <Search
                            className={cn(
                                'absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 cursor-pointer transition-colors',
                                searchOpen ? 'text-indigo-400' : 'text-white/20 hover:text-white/40'
                            )}
                            onClick={() => setSearchOpen(true)}
                        />
                    </div>

                    {/* View mode toggle (desktop only) */}
                    {!isMobile && (
                        <div className="glass-segmented">
                            <button
                                onClick={() => setViewMode('table')}
                                className={cn('glass-segmented-item px-2', viewMode === 'table' && 'active')}
                            >
                                <List className="h-3.5 w-3.5" />
                            </button>
                            <button
                                onClick={() => setViewMode('card')}
                                className={cn('glass-segmented-item px-2', viewMode === 'card' && 'active')}
                            >
                                <LayoutGrid className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    )}

                    {/* Group by */}
                    <select
                        value={groupBy}
                        onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                        className="glass-input py-1.5 px-2 text-xs w-24"
                    >
                        <option value="none">Group: None</option>
                        <option value="account">Account</option>
                        <option value="sector">Sector</option>
                        <option value="market">Market</option>
                    </select>

                    {/* Sort by */}
                    <select
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value as SortBy)}
                        className="glass-input py-1.5 px-2 text-xs w-28"
                    >
                        <option value="value">Sort: Value</option>
                        <option value="gain">Gain/Loss</option>
                        <option value="quantity">Quantity</option>
                        <option value="symbol">Symbol</option>
                    </select>
                </div>
            </div>

            {/* Filtered empty state */}
            {showFilteredEmpty && (
                <div className="py-12 text-center">
                    <p className="text-white/20 text-sm">No holdings match &quot;{search}&quot;</p>
                    <button
                        onClick={() => { setSearch(''); setSearchOpen(false); }}
                        className="text-xs text-indigo-400/60 hover:text-indigo-400 mt-2"
                    >
                        Clear search
                    </button>
                </div>
            )}

            {/* Grouped view */}
            {!showFilteredEmpty && grouped && (
                <div className="space-y-2">
                    {Object.entries(grouped).map(([key, items]) => {
                        const isExpanded = expandedGroups[key] !== false;
                        const groupValue = items.reduce(
                            (sum, h) => sum + (h.current_value || 0),
                            0
                        );

                        return (
                            <div key={key}>
                                <button
                                    onClick={() => toggleGroup(key)}
                                    className="w-full flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-white/[0.02] transition-colors"
                                >
                                    {isExpanded ? (
                                        <ChevronDown className="h-3 w-3 text-white/30 flex-shrink-0" />
                                    ) : (
                                        <ChevronRight className="h-3 w-3 text-white/30 flex-shrink-0" />
                                    )}
                                    <span className="text-xs font-bold text-white/60 uppercase">
                                        {key}
                                    </span>
                                    <span className="text-[10px] text-white/20">
                                        {items.length} position{items.length !== 1 ? 's' : ''}
                                        {groupValue > 0 && ` · $${groupValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                                    </span>
                                </button>

                                {isExpanded && (
                                    <div className="space-y-1 pl-6">
                                        {items.map((h) => (
                                            <HoldingRow
                                                key={h.holding_id}
                                                holding={h}
                                                viewMode={effectiveView}
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Flat view */}
            {!showFilteredEmpty && !grouped && (
                <div className="space-y-1">
                    {staggeredItems.map((h) => (
                        <HoldingRow
                            key={h.holding_id}
                            holding={h}
                            viewMode={effectiveView}
                        />
                    ))}
                </div>
            )}

            {/* Show more / less */}
            {!showFilteredEmpty && !grouped && filtered.length > INITIAL_VISIBLE && (
                <button
                    onClick={() => setShowAll(!showAll)}
                    className="w-full mt-3 py-2 text-xs font-bold text-indigo-400/60 hover:text-indigo-400 transition-colors"
                >
                    {showAll
                        ? 'Show less'
                        : `Show all ${filtered.length}`}
                </button>
            )}
        </div>
    );
}

function MarketBadge({ group }: { group: string }) {
    const colorClass = MARKET_BADGE_COLORS[group] || MARKET_BADGE_COLORS.OTHER;
    return (
        <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full border font-bold uppercase leading-none', colorClass)}>
            {group}
        </span>
    );
}

function HoldingRow({ holding, viewMode }: { holding: Holding; viewMode: ViewMode }) {
    const gain = (holding.current_value || 0) - holding.total_cost;
    const isPositive = gain >= 0;

    if (viewMode === 'card') {
        return (
            <div className="glass-card p-3 space-y-2 animate-fade-up">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="h-8 w-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-[10px] font-black text-indigo-400 ring-1 ring-indigo-500/20">
                            {holding.symbol.substring(0, 2)}
                        </div>
                        <div>
                            <div className="flex items-center gap-1.5">
                                <p className="text-sm font-bold text-white">{holding.symbol}</p>
                                <MarketBadge group={holding.market_group || 'OTHER'} />
                            </div>
                            <p className="text-xs text-white/40 truncate max-w-[180px]">
                                {holding.company_name}
                            </p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-sm font-bold text-white">
                            ${(holding.current_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </p>
                        <p className={cn('text-xs font-bold', isPositive ? 'text-emerald-400' : 'text-rose-400')}>
                            {isPositive ? '+' : ''}${Math.abs(gain).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            {holding.unrealized_gain_loss_pct !== null &&
                                ` (${isPositive ? '+' : ''}${holding.unrealized_gain_loss_pct.toFixed(1)}%)`}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-4 text-[11px] text-white/30">
                    <span>{holding.quantity.toFixed(2)} shares</span>
                    <span>Avg ${holding.average_cost.toFixed(2)}</span>
                </div>
            </div>
        );
    }

    return (
        <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/[0.02] transition-colors animate-fade-up">
            <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className="h-8 w-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-[10px] font-black text-indigo-400 ring-1 ring-indigo-500/20 flex-shrink-0">
                    {holding.symbol.substring(0, 2)}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                        <p className="text-sm font-bold text-white">{holding.symbol}</p>
                        <MarketBadge group={holding.market_group || 'OTHER'} />
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/30 uppercase font-bold">
                            {holding.account_type || 'N/A'}
                        </span>
                    </div>
                    <p className="text-xs text-white/40 truncate">
                        {holding.company_name}
                    </p>
                </div>
            </div>

            <div className="flex items-center gap-6">
                <div className="text-right hidden md:block">
                    <p className="text-xs text-white/40">{holding.quantity.toFixed(2)}</p>
                </div>
                <div className="text-right hidden md:block">
                    <p className="text-xs text-white/40">
                        ${holding.average_cost.toFixed(2)}
                    </p>
                </div>
                <div className="text-right">
                    <p className="text-sm font-bold text-white">
                        ${(holding.current_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                    <p className={cn('text-xs font-bold', isPositive ? 'text-emerald-400' : 'text-rose-400')}>
                        {isPositive ? '+' : ''}${Math.abs(gain).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        {holding.unrealized_gain_loss_pct !== null &&
                            ` (${isPositive ? '+' : ''}${holding.unrealized_gain_loss_pct.toFixed(1)}%)`}
                    </p>
                </div>
            </div>
        </div>
    );
}
