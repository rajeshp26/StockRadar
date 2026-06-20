'use client';

import { useState, useMemo, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { AccentLine, SectionHeader } from './DividendsSharedUI';
import type { UpcomingExDate } from '../types/portfolio.types';

interface DividendsUpcomingCardProps {
    data: UpcomingExDate[] | undefined;
    isLoading: boolean;
    error: Error | null;
}

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function fmtKey(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
}

function fmtLabel(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString(undefined, {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        year: 'numeric',
    });
}

function daysUntil(dateStr: string): number {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const d = new Date(dateStr + 'T00:00:00');
    return Math.ceil((d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

const formatCurrency = (v: number) =>
    v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

export function DividendsUpcomingCard({ data, isLoading, error }: DividendsUpcomingCardProps) {
    const todayKey = useMemo(() => fmtKey(new Date()), []);

    const [viewMonth, setViewMonth] = useState(() => {
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), 1);
    });
    const [selectedKey, setSelectedKey] = useState<string | null>(null);
    const [search, setSearch] = useState('');

    const byDate = useMemo(() => {
        const map = new Map<string, UpcomingExDate[]>();
        if (!data) return map;
        for (const item of data) {
            if (!map.has(item.ex_dividend_date)) map.set(item.ex_dividend_date, []);
            map.get(item.ex_dividend_date)!.push(item);
        }
        return map;
    }, [data]);

    const q = search.trim().toUpperCase();

    const filteredByDate = useMemo(() => {
        if (!q) return byDate;
        const map = new Map<string, UpcomingExDate[]>();
        for (const [date, items] of byDate) {
            const matching = items.filter(i => i.symbol.toUpperCase().includes(q));
            if (matching.length) map.set(date, matching);
        }
        return map;
    }, [byDate, q]);

    useEffect(() => {
        if (!data || selectedKey) return;
        const keys = Array.from(byDate.keys()).sort();
        const next = keys.find(k => k >= todayKey);
        if (next) setSelectedKey(next);
    }, [data, byDate, todayKey, selectedKey]);

    const calendarDays = useMemo(() => {
        const y = viewMonth.getFullYear();
        const m = viewMonth.getMonth();
        const first = new Date(y, m, 1);
        const start = new Date(first);
        start.setDate(first.getDate() - first.getDay());
        const days: Date[] = [];
        for (let i = 0; i < 42; i++) {
            const d = new Date(start);
            d.setDate(start.getDate() + i);
            days.push(d);
        }
        return days;
    }, [viewMonth]);

    const selectedItems = selectedKey ? (filteredByDate.get(selectedKey) ?? []) : [];

    if (error) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Ex-Dates Calendar" subtitle="Expected dividend payments" />
                <p className="text-xs text-rose-400">Failed to load upcoming ex-dates</p>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Ex-Dates Calendar" subtitle="Expected dividend payments" />
                <div className="h-[400px] rounded-xl bg-white/5 glass-shimmer" />
            </div>
        );
    }

    if (!data || data.length === 0) {
        return (
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader title="Ex-Dates Calendar" subtitle="Expected dividend payments" />
                <p className="text-sm text-white/30 italic">No upcoming ex-dates found</p>
            </div>
        );
    }

    return (
        <div className="glass-panel p-6 lg:p-8 relative overflow-hidden">
            <AccentLine />
            <SectionHeader
                title="Ex-Dates Calendar"
                subtitle="Pick a day to see which tickers go ex. Amounts are predicted."
            />

            <div className="flex flex-wrap items-center gap-3 mb-5">
                <input
                    type="text"
                    placeholder="Filter by ticker..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="flex-1 min-w-[180px] glass-input px-4 py-2.5 text-sm"
                />
                <span className="glass-chip flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
                    Predicted
                </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-5">
                <div>
                    <div className="flex items-center justify-between gap-3 mb-3">
                        <button
                            onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1))}
                            className="glass-btn px-3 py-1.5 text-sm"
                            aria-label="Previous month"
                        >
                            ←
                        </button>
                        <span className="font-bold text-base capitalize">
                            {viewMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                        </span>
                        <button
                            onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1))}
                            className="glass-btn px-3 py-1.5 text-sm"
                            aria-label="Next month"
                        >
                            →
                        </button>
                    </div>

                    <div className="grid grid-cols-7 gap-1 mb-1">
                        {DOW.map(d => (
                            <div
                                key={d}
                                className="text-center text-[11px] uppercase tracking-widest text-white/30 font-semibold py-2"
                            >
                                {d}
                            </div>
                        ))}
                    </div>

                    <div className="grid grid-cols-7 gap-1">
                        {calendarDays.map((d, i) => {
                            const key = fmtKey(d);
                            const inMonth = d.getMonth() === viewMonth.getMonth();
                            const isToday = key === todayKey;
                            const isSelected = key === selectedKey;
                            const items = filteredByDate.get(key);
                            const count = items?.length ?? 0;
                            const soon = count > 0 && daysUntil(key) >= 0 && daysUntil(key) <= 3;

                            return (
                                <button
                                    key={i}
                                    onClick={() => setSelectedKey(key)}
                                    className={cn(
                                        'relative aspect-square rounded-xl text-sm font-semibold',
                                        'border border-transparent',
                                        'flex items-center justify-center',
                                        'transition-all duration-150',
                                        inMonth ? 'text-white' : 'text-white/20',
                                        isToday && 'ring-2 ring-indigo-500 ring-offset-2 ring-offset-transparent',
                                        isSelected && 'bg-indigo-500/20 border-indigo-500/40',
                                        count > 0 && !isSelected
                                            && 'border-amber-500/30 bg-gradient-to-b from-amber-500/10 to-amber-500/3',
                                        'hover:border-indigo-500/50 hover:bg-indigo-500/8',
                                        !inMonth && 'pointer-events-none'
                                    )}
                                >
                                    {d.getDate()}
                                    {count > 0 && (
                                        <span
                                            className={cn(
                                                'absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-extrabold flex items-center justify-center leading-none',
                                                soon ? 'bg-rose-500 text-white' : 'bg-amber-400 text-gray-900'
                                            )}
                                        >
                                            {count}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    <div className="flex flex-wrap gap-4 mt-4 text-white/40 text-xs items-center">
                        <span className="inline-flex items-center gap-1.5">
                            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
                            Has ex-date
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
                            ≤3 days away
                        </span>
                    </div>
                </div>

                <div>
                    <h3 className="font-bold text-base mb-3">
                        {selectedKey ? fmtLabel(selectedKey) : 'Select a day'}
                    </h3>
                    {selectedItems.length === 0 ? (
                        <p className="text-white/40 text-sm">
                            {selectedKey
                                ? `No ex-dates on this day${q ? ' for that ticker' : ''}.`
                                : 'Click any day with a dot to see the tickers going ex.'}
                        </p>
                    ) : (
                        <ul className="space-y-3">
                            {selectedItems
                                .slice()
                                .sort((a, b) => a.symbol.localeCompare(b.symbol))
                                .map(item => (
                                    <li
                                        key={item.symbol}
                                        className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3.5"
                                    >
                                        <div className="flex items-center justify-between gap-3 mb-2">
                                            <span className="font-bold text-sm font-mono">{item.symbol}</span>
                                            <span
                                                className={cn(
                                                    'text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border',
                                                    item.confidence === 'high'
                                                        ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400'
                                                        : item.confidence === 'medium'
                                                        ? 'bg-amber-500/10 border-amber-500/25 text-amber-400'
                                                        : 'bg-rose-500/10 border-rose-500/25 text-rose-400'
                                                )}
                                            >
                                                {item.trust_label ?? item.confidence}
                                            </span>
                                        </div>
                                        <div className="space-y-1 text-sm">
                                            <div className="flex justify-between gap-4">
                                                <span className="text-white/40">Dividend / share</span>
                                                <span className="font-semibold tabular-nums">
                                                    {formatCurrency(item.amount_per_share)}
                                                </span>
                                            </div>
                                            <div className="flex justify-between gap-4 border-t border-dashed border-white/[0.06] pt-1">
                                                <span className="text-white/40">Est. total (to date)</span>
                                                <span className="font-semibold tabular-nums">
                                                    {formatCurrency(item.estimated_income)}
                                                </span>
                                            </div>
                                        </div>
                                    </li>
                                ))}
                        </ul>
                    )}
                </div>
            </div>
        </div>
    );
}
