'use client';

import { ArrowUp, ArrowDown } from 'lucide-react';
import type { Holding } from '../types/portfolio.types';

interface TopMoversProps {
    holdings: Holding[];
    limit?: number;
}

export function TopMovers({ holdings, limit = 7 }: TopMoversProps) {
    const sorted = [...holdings].sort(
        (a, b) => (b.unrealized_gain_loss_pct ?? 0) - (a.unrealized_gain_loss_pct ?? 0)
    );

    const gainers = sorted.filter((h) => (h.unrealized_gain_loss_pct ?? 0) > 0).slice(0, limit);
    const losers = sorted
        .filter((h) => (h.unrealized_gain_loss_pct ?? 0) < 0)
        .reverse()
        .slice(0, limit);

    if (gainers.length === 0 && losers.length === 0) return null;

    function renderRow(holding: Holding, isGainer: boolean) {
        const pct = holding.unrealized_gain_loss_pct ?? 0;
        return (
            <div
                key={holding.company_id}
                data-testid="mover-row"
                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/5 transition-colors"
            >
                <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-bold text-white truncate">{holding.symbol}</span>
                    <span className="text-xs text-white/40 truncate hidden sm:inline">
                        {holding.company_name}
                    </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-white/50">
                        ${holding.current_price?.toFixed(2) ?? '—'}
                    </span>
                    <span
                        data-testid="gain-pct"
                        className={`flex items-center gap-1 text-xs font-bold ${
                            isGainer ? 'text-green-400' : 'text-red-400'
                        }`}
                    >
                        {isGainer ? (
                            <ArrowUp className="h-3 w-3" />
                        ) : (
                            <ArrowDown className="h-3 w-3" />
                        )}
                        {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                </div>
            </div>
        );
    }

    return (
        <div className="glass-panel rounded-lg p-4 space-y-3">
            <h3 className="text-xs font-black uppercase tracking-widest text-white/40">
                Top Movers
            </h3>

            {gainers.length > 0 && (
                <div data-testid="top-gainers">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-green-400/60 mb-1">
                        Gainers
                    </p>
                    {gainers.map((h) => renderRow(h, true))}
                </div>
            )}

            {gainers.length > 0 && losers.length > 0 && (
                <div className="border-t border-white/5" />
            )}

            {losers.length > 0 && (
                <div data-testid="top-losers">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-red-400/60 mb-1">
                        Losers
                    </p>
                    {losers.map((h) => renderRow(h, false))}
                </div>
            )}
        </div>
    );
}
