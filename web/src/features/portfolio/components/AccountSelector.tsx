'use client';

import { useState, useMemo } from 'react';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ACCOUNT_TYPE_COLORS } from '../types/portfolio.types';
import type { PortfolioAccount } from '../types/portfolio.types';

const ACCOUNT_TYPE_BADGE: Record<string, string> = {
    'TFSA': 'border-emerald-500/30 text-emerald-400',
    'RRSP': 'border-indigo-500/30 text-indigo-400',
    'Non-registered': 'border-amber-500/30 text-amber-400',
    'FHSA': 'border-violet-500/30 text-violet-400',
    '401k': 'border-blue-500/30 text-blue-400',
    'IRA': 'border-rose-500/30 text-rose-400',
    'Roth IRA': 'border-pink-500/30 text-pink-400',
};

interface AccountSelectorProps {
    accounts: PortfolioAccount[];
    selected: number[];
    onChange: (ids: number[]) => void;
}

export function AccountSelector({ accounts, selected, onChange }: AccountSelectorProps) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');

    const sorted = useMemo(() =>
        [...accounts].sort((a, b) => {
            if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
            const aLabel = `${a.brokerage_name} ${a.account_name}`;
            const bLabel = `${b.brokerage_name} ${b.account_name}`;
            return aLabel.localeCompare(bLabel);
        }),
        [accounts]
    );

    const filtered = useMemo(() => {
        if (!search.trim()) return sorted;
        const q = search.toLowerCase();
        return sorted.filter((a) =>
            a.account_name.toLowerCase().includes(q) ||
            a.brokerage_name.toLowerCase().includes(q) ||
            a.account_type.toLowerCase().includes(q)
        );
    }, [sorted, search]);

    const allSelected = selected.length === 0 || selected.length === accounts.length;
    const someSelected = selected.length > 0 && selected.length < accounts.length;

    const buttonLabel = allSelected
        ? 'All Accounts'
        : selected.length === 1
            ? sorted.find((a) => a.account_id === selected[0])?.account_name || '1 Account'
            : `${sorted.find((a) => a.account_id === selected[0])?.account_name || ''} +${selected.length - 1}`;

    if (accounts.length === 0) return null;

    return (
        <div className="relative">
            <button
                onClick={() => { setOpen(!open); setSearch(''); }}
                className={cn(
                    'glass-btn px-3 py-1.5 text-xs font-bold flex items-center gap-1.5 max-w-[200px]',
                    !allSelected && 'text-indigo-400'
                )}
            >
                <span className="truncate">{buttonLabel}</span>
                <ChevronDown
                    className={cn(
                        'h-3 w-3 shrink-0 transition-transform',
                        open && 'rotate-180'
                    )}
                />
            </button>

            {open && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
                    <div
                        className={cn(
                            'absolute right-0 top-full mt-2 z-50',
                            'min-w-[260px] rounded-xl overflow-hidden',
                            'bg-[rgba(12,15,28,0.95)] border border-white/[0.07]',
                            'backdrop-blur-2xl shadow-glass-lg'
                        )}
                    >
                        {/* Search */}
                        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.06]">
                            <Search className="h-3.5 w-3.5 text-white/30 shrink-0" />
                            <input
                                type="text"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search accounts..."
                                className="flex-1 bg-transparent text-xs text-white placeholder-white/30 outline-none"
                                autoFocus
                            />
                            {search && (
                                <button onClick={() => setSearch('')} className="text-white/30 hover:text-white/60">
                                    <X className="h-3 w-3" />
                                </button>
                            )}
                        </div>

                        {/* Select All / Deselect All */}
                        <button
                            onClick={() => {
                                if (allSelected) {
                                    onChange([]);
                                } else {
                                    onChange([]);
                                }
                            }}
                            className={cn(
                                'w-full flex items-center gap-3 px-4 py-2 text-left',
                                'hover:bg-white/[0.04] transition-colors text-xs font-bold text-white/60'
                            )}
                        >
                            <div
                                className={cn(
                                    'h-4 w-4 rounded border flex items-center justify-center',
                                    allSelected
                                        ? 'bg-indigo-500 border-indigo-500'
                                        : someSelected
                                            ? 'border-indigo-500/50 bg-indigo-500/20'
                                            : 'border-white/20'
                                )}
                            >
                                {allSelected && <Check className="h-3 w-3 text-white" />}
                                {someSelected && <div className="h-2 w-2 rounded-sm bg-indigo-400" />}
                            </div>
                            {allSelected ? 'All Accounts Selected' : 'Select All'}
                        </button>

                        {/* Account list */}
                        <div className="max-h-[280px] overflow-y-auto">
                            {filtered.length === 0 ? (
                                <p className="px-4 py-3 text-xs text-white/30">No accounts match</p>
                            ) : (
                                filtered.map((a) => {
                                    const isSelected = selected.length === 0 || selected.includes(a.account_id);
                                    return (
                                        <button
                                            key={a.account_id}
                                            onClick={() => {
                                                if (selected.length === 0) {
                                                    // Start with all selected, remove this one
                                                    const rest = sorted
                                                        .filter((acc) => acc.account_id !== a.account_id)
                                                        .map((acc) => acc.account_id);
                                                    onChange(rest);
                                                } else if (isSelected) {
                                                    if (selected.length === 1) return; // minimum 1
                                                    onChange(selected.filter((id) => id !== a.account_id));
                                                } else {
                                                    onChange([...selected, a.account_id]);
                                                }
                                            }}
                                            className={cn(
                                                'w-full flex items-center gap-3 px-4 py-2.5 text-left',
                                                'hover:bg-white/[0.04] transition-colors',
                                                isSelected && 'bg-indigo-500/10'
                                            )}
                                        >
                                            <div
                                                className={cn(
                                                    'h-4 w-4 rounded border flex items-center justify-center shrink-0',
                                                    isSelected
                                                        ? 'bg-indigo-500 border-indigo-500'
                                                        : 'border-white/20'
                                                )}
                                            >
                                                {isSelected && <Check className="h-3 w-3 text-white" />}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-bold text-white truncate">
                                                    {a.brokerage_name} {a.account_name}
                                                </p>
                                                <div className="flex items-center gap-2">
                                                    <span className={cn(
                                                        'text-[10px] px-1.5 py-0.5 rounded border font-medium',
                                                        ACCOUNT_TYPE_BADGE[a.account_type] || 'border-white/20 text-white/40'
                                                    )}>
                                                        {a.account_type}
                                                    </span>
                                                    {!a.is_active && (
                                                        <span className="text-[10px] text-white/30">Inactive</span>
                                                    )}
                                                </div>
                                            </div>
                                        </button>
                                    );
                                })
                            )}
                        </div>

                        {/* Footer */}
                        <div className="px-4 py-2 text-[10px] text-white/30 border-t border-white/[0.06] flex justify-between">
                            <span>
                                {selected.length === 0 ? accounts.length : selected.length} / {accounts.length} accounts
                            </span>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
