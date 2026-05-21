'use client';

import { useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { BenchmarkInfo } from '../types/portfolio.types';

const MAX_BENCHMARKS = 5;

interface BenchmarkSelectorProps {
    benchmarks: BenchmarkInfo[];
    selected: string[];
    onToggle: (symbol: string) => void;
}

export function BenchmarkSelector({ benchmarks, selected, onToggle }: BenchmarkSelectorProps) {
    const [open, setOpen] = useState(false);

    if (benchmarks.length === 0) return null;

    const atMax = selected.length >= MAX_BENCHMARKS;

    const buttonLabel = selected.length === 0
        ? '+ Compare'
        : selected.length === 1
            ? selected[0]
            : `${selected[0]} +${selected.length - 1}`;

    return (
        <div className="relative">
            <button
                onClick={() => setOpen(!open)}
                className={cn(
                    'glass-btn px-3 py-1.5 text-xs font-bold flex items-center gap-1.5',
                    selected.length > 0 && 'text-indigo-400'
                )}
            >
                {buttonLabel}
                <ChevronDown
                    className={cn(
                        'h-3 w-3 transition-transform',
                        open && 'rotate-180'
                    )}
                />
            </button>

            {open && (
                <>
                    <div
                        className="fixed inset-0 z-40"
                        onClick={() => setOpen(false)}
                    />
                    <div
                        className={cn(
                            'absolute right-0 top-full mt-2 z-50',
                            'min-w-[220px] rounded-xl overflow-hidden',
                            'bg-[rgba(12,15,28,0.95)] border border-white/[0.07]',
                            'backdrop-blur-2xl shadow-glass-lg'
                        )}
                    >
                        {benchmarks.map((b) => {
                            const isSelected = selected.includes(b.symbol);
                            const disabled = !isSelected && atMax;
                            return (
                                <button
                                    key={b.symbol}
                                    onClick={() => {
                                        if (disabled) return;
                                        onToggle(b.symbol);
                                    }}
                                    className={cn(
                                        'w-full flex items-center gap-3 px-4 py-2.5 text-left',
                                        'hover:bg-white/[0.04] transition-colors',
                                        isSelected && 'bg-indigo-500/10',
                                        disabled && 'opacity-30 cursor-not-allowed'
                                    )}
                                >
                                    <div
                                        className={cn(
                                            'h-4 w-4 rounded border flex items-center justify-center',
                                            isSelected
                                                ? 'bg-indigo-500 border-indigo-500'
                                                : 'border-white/20'
                                        )}
                                    >
                                        {isSelected && <Check className="h-3 w-3 text-white" />}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-bold text-white">
                                            {b.name || b.symbol}
                                        </p>
                                        <p className="text-[10px] text-white/30 uppercase tracking-wider">
                                            {b.market}
                                        </p>
                                    </div>
                                </button>
                            );
                        })}
                        {atMax && (
                            <p className="px-4 py-2 text-[10px] text-amber-400/60 border-t border-white/[0.06]">
                                Max {MAX_BENCHMARKS} benchmarks
                            </p>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
