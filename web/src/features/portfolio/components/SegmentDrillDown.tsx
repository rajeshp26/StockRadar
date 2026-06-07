'use client';

import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import type { Holding } from '../types/portfolio.types';

interface SegmentDrillDownProps {
    segmentName: string;
    holdings: Holding[];
    onBack: () => void;
}

export function SegmentDrillDown({ segmentName, holdings, onBack }: SegmentDrillDownProps) {
    const router = useRouter();
    const totalValue = holdings.reduce((sum, h) => sum + (h.current_value || 0), 0);

    return (
        <div className="glass-panel rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-3 pb-2 border-b border-white/5">
                <button
                    onClick={onBack}
                    className="flex items-center gap-1.5 text-xs font-bold text-indigo-400/60 hover:text-indigo-400 transition-colors"
                >
                    <ArrowLeft className="h-3.5 w-3.5" />
                    All Sectors
                </button>
                <span className="text-white/20">|</span>
                <h3 className="text-sm font-bold text-white">{segmentName}</h3>
                <span className="text-xs text-white/30">
                    {holdings.length} holding{holdings.length !== 1 ? 's' : ''}
                    {totalValue > 0 && ` · $${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                </span>
            </div>

            <div className="space-y-1">
                {holdings.map((h) => {
                    const value = h.current_value || 0;
                    const weight = totalValue > 0 ? (value / totalValue) * 100 : 0;
                    const gain = value - h.total_cost;
                    const isPositive = gain >= 0;

                    return (
                        <div
                            key={`${h.symbol}-${h.holding_id}`}
                            className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/[0.02] transition-colors cursor-pointer"
                            onClick={() => router.push(`/analysis/${h.symbol}`)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => { if (e.key === 'Enter') router.push(`/analysis/${h.symbol}`); }}
                        >
                            <div className="flex items-center gap-3 flex-1 min-w-0">
                                <div className="h-8 w-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-[10px] font-black text-indigo-400 ring-1 ring-indigo-500/20 flex-shrink-0">
                                    {h.symbol.substring(0, 2)}
                                </div>
                                <div>
                                    <p className="text-sm font-bold text-white">{h.symbol}</p>
                                    <p className="text-xs text-white/40 truncate max-w-[200px]">
                                        {h.company_name}
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-6">
                                <div className="text-right">
                                    <p className="text-sm font-bold text-white">
                                        ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </p>
                                    <p className="text-xs text-white/40">{weight.toFixed(1)}%</p>
                                </div>
                                <div className="text-right w-24">
                                    <p className={cn(
                                        'text-sm font-bold',
                                        isPositive ? 'text-green-400' : 'text-red-400'
                                    )}>
                                        {isPositive ? '+' : ''}${Math.abs(gain).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </p>
                                    <p className={cn(
                                        'text-xs',
                                        isPositive ? 'text-green-400/60' : 'text-red-400/60'
                                    )}>
                                        {h.unrealized_gain_loss_pct != null
                                            ? `${isPositive ? '+' : ''}${h.unrealized_gain_loss_pct.toFixed(2)}%`
                                            : '—'}
                                    </p>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {holdings.length === 0 && (
                <div className="py-8 text-center">
                    <p className="text-white/20 text-sm">No holdings in this segment</p>
                </div>
            )}
        </div>
    );
}
