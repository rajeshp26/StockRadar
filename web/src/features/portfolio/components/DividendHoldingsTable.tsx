'use client';

import { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Search, ChevronDown, ChevronUp } from 'lucide-react';
import type { PortfolioDividendHolding } from '../types/portfolio.types';

interface DividendHoldingsTableProps {
    data: PortfolioDividendHolding[];
    onSelect: (symbol: string) => void;
}

type SortKey = 'symbol' | 'forward_income' | 'trailing_12m_income' | 'current_yield' | 'forward_yield_on_cost' | 'safety_score';

export function DividendHoldingsTable({ data, onSelect }: DividendHoldingsTableProps) {
    const [search, setSearch] = useState('');
    const [sectorFilter, setSectorFilter] = useState<string>('');
    const [sortKey, setSortKey] = useState<SortKey>('forward_income');
    const [sortAsc, setSortAsc] = useState(false);

    const sectors = useMemo(() => {
        const set = new Set(data.map((h) => h.sector).filter(Boolean));
        return Array.from(set).sort() as string[];
    }, [data]);

    const filtered = useMemo(() => {
        let result = [...data];
        if (search) {
            const q = search.toLowerCase();
            result = result.filter((h) =>
                h.symbol.toLowerCase().includes(q) || h.company_name.toLowerCase().includes(q)
            );
        }
        if (sectorFilter) {
            result = result.filter((h) => h.sector === sectorFilter);
        }
        result.sort((a, b) => {
            const aVal = a[sortKey] ?? 0;
            const bVal = b[sortKey] ?? 0;
            if (typeof aVal === 'string' && typeof bVal === 'string') {
                return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            }
            return sortAsc ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
        });
        return result;
    }, [data, search, sectorFilter, sortKey, sortAsc]);

    const toggleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortAsc(!sortAsc);
        } else {
            setSortKey(key);
            setSortAsc(false);
        }
    };

    const SortIcon = ({ col }: { col: SortKey }) => {
        if (sortKey !== col) return null;
        return sortAsc ? <ChevronUp className="inline h-3 w-3 ml-0.5" /> : <ChevronDown className="inline h-3 w-3 ml-0.5" />;
    };

    const formatCurrency = (v: number) =>
        v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

    const formatPct = (v: number | null) => (v != null ? `${v.toFixed(2)}%` : '—');

    return (
        <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
                <div className="relative flex-1 min-w-[150px] max-w-xs">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/20" />
                    <input
                        type="text"
                        placeholder="Search symbol or name..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-white/20"
                    />
                </div>
                <select
                    value={sectorFilter}
                    onChange={(e) => setSectorFilter(e.target.value)}
                    className="bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white/60 focus:outline-none focus:border-white/20"
                >
                    <option value="">All sectors</option>
                    {sectors.map((s) => (
                        <option key={s} value={s}>{s}</option>
                    ))}
                </select>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="border-b border-white/5">
                            <Th onClick={() => toggleSort('symbol')}>Symbol <SortIcon col="symbol" /></Th>
                            <Th>Name</Th>
                            <Th>Sector</Th>
                            <Th numeric>Qty</Th>
                            <Th numeric>Mkt Value</Th>
                            <Th numeric onClick={() => toggleSort('forward_income')}>Fwd Income <SortIcon col="forward_income" /></Th>
                            <Th numeric onClick={() => toggleSort('trailing_12m_income')}>Trailing 12M <SortIcon col="trailing_12m_income" /></Th>
                            <Th numeric onClick={() => toggleSort('current_yield')}>Yield <SortIcon col="current_yield" /></Th>
                            <Th numeric onClick={() => toggleSort('forward_yield_on_cost')}>YoC <SortIcon col="forward_yield_on_cost" /></Th>
                            <Th numeric>Payout</Th>
                            <Th numeric>Streak</Th>
                            <Th numeric onClick={() => toggleSort('safety_score')}>Safety <SortIcon col="safety_score" /></Th>
                            <Th>Next Event</Th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map((h) => (
                            <tr
                                key={h.symbol}
                                onClick={() => onSelect(h.symbol)}
                                className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                            >
                                <Td className="font-bold text-white">{h.symbol}</Td>
                                <Td className="text-white/60 max-w-[120px] truncate">{h.company_name}</Td>
                                <Td className="text-white/40">{h.sector || '—'}</Td>
                                <Td numeric>{h.quantity.toLocaleString()}</Td>
                                <Td numeric className="text-white/60">{formatCurrency(h.market_value)}</Td>
                                <Td numeric className="text-green-400 font-medium">{formatCurrency(h.forward_income)}</Td>
                                <Td numeric className="text-green-400/70">{formatCurrency(h.trailing_12m_income)}</Td>
                                <Td numeric>{formatPct(h.current_yield)}</Td>
                                <Td numeric>{formatPct(h.forward_yield_on_cost)}</Td>
                                <Td numeric>{formatPct(h.payout_ratio)}</Td>
                                <Td numeric>{h.increase_streak != null ? `${h.increase_streak}y` : '—'}</Td>
                                <Td numeric>
                                    {h.safety_score != null ? (
                                        <span className={cn(
                                            'font-medium',
                                            h.safety_score >= 70 ? 'text-green-400' : h.safety_score >= 40 ? 'text-yellow-400' : 'text-red-400'
                                        )}>
                                            {h.safety_score.toFixed(0)}
                                        </span>
                                    ) : '—'}
                                </Td>
                                <Td>
                                    {h.next_event ? (
                                        <span className="text-white/60 text-[10px]">{h.next_event.ex_dividend_date}</span>
                                    ) : '—'}
                                </Td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {filtered.length === 0 && (
                    <p className="text-center text-white/20 text-xs py-6">No holdings match your search.</p>
                )}
            </div>
        </div>
    );
}

function Th({ children, numeric, onClick }: { children: React.ReactNode; numeric?: boolean; onClick?: () => void }) {
    return (
        <th
            onClick={onClick}
            className={cn(
                'px-3 py-2 text-[10px] font-medium text-white/30 uppercase tracking-wider select-none',
                numeric && 'text-right',
                onClick && 'cursor-pointer hover:text-white/50'
            )}
        >
            {children}
        </th>
    );
}

function Td({ children, numeric, className }: { children: React.ReactNode; numeric?: boolean; className?: string }) {
    return (
        <td className={cn('px-3 py-2 text-xs', numeric && 'text-right', className)}>
            {children}
        </td>
    );
}
