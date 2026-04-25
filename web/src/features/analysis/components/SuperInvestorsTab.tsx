import React, { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSuperInvestors } from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SuperInvestorData, SuperInvestorHolder } from "../types/analysis.types";

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export function SuperInvestorsTab({ symbol }: { symbol: string }) {
    const { data, isLoading, error, refetch } = useQuery<SuperInvestorData, Error>({
        queryKey: QK.superInvestors(symbol),
        queryFn: () => fetchSuperInvestors(symbol),
        staleTime: 1000 * 60 * 60 * 24, // 13F data updates quarterly, cache for 24h
    });

    const [refreshing, setRefreshing] = useState(false);

    const handleRefresh = useCallback(async () => {
        setRefreshing(true);
        try {
            await refetch();
        } finally {
            setRefreshing(false);
        }
    }, [refetch]);

    if (isLoading) {
        return (
            <div className="glass-panel p-8">
                <div className="flex items-center justify-center space-x-3">
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
                    <p className="text-sm text-slate-400">Loading institutional holdings...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="glass-panel p-8">
                <p className="text-sm text-rose-400">Failed to load super investor data</p>
            </div>
        );
    }

    if (!data || data.overlap_count === 0) {
        return <EmptyState symbol={symbol} onRefresh={handleRefresh} refreshing={refreshing} />;
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-200">Super Investors</h2>
                <button
                    onClick={handleRefresh}
                    disabled={isLoading || refreshing}
                    className={cn(
                        "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                        "text-[10px] font-black uppercase tracking-widest",
                        (isLoading || refreshing) && "opacity-50 cursor-not-allowed",
                    )}
                >
                    <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                    {refreshing ? "Refreshing..." : "Refresh"}
                </button>
            </div>

            {/* Header Stats */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <StatCard
                    label="Notable Holders"
                    value={data.overlap_count}
                    suffix="investors"
                />
                <StatCard
                    label="Avg Portfolio Weight"
                    value={`${(data.avg_portfolio_weight * 100).toFixed(2)}%`}
                />
                <StatCard
                    label="Conviction Level"
                    value={data.conviction_level.replace("_", " ").toUpperCase()}
                    valueClassName={getConvictionColor(data.conviction_level)}
                />
            </div>

            {/* Current Holders */}
            <div className="glass-panel">
                <div className="border-b border-white/5 p-4">
                    <h3 className="text-sm font-medium text-slate-200">Current Holders</h3>
                    <p className="mt-1 text-xs text-slate-400">
                        Most recent 13F filings (quarterly disclosure)
                    </p>
                </div>
                <div className="divide-y divide-white/5">
                    {data.holders.map((holder, idx) => (
                        <HolderRow key={idx} holder={holder} />
                    ))}
                </div>
            </div>

            {/* Recent Activity */}
            {(data.recent_activity.buyers.length > 0 || data.recent_activity.sellers.length > 0) && (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    {/* Buyers */}
                    {data.recent_activity.buyers.length > 0 && (
                        <div className="glass-panel">
                            <div className="border-b border-white/5 p-4">
                                <h3 className="text-sm font-medium text-emerald-400">Recent Buyers</h3>
                                <p className="mt-1 text-xs text-slate-400">Added or increased positions</p>
                            </div>
                            <div className="divide-y divide-white/5">
                                {data.recent_activity.buyers.map((holder, idx) => (
                                    <ActivityRow key={idx} holder={holder} type="buy" />
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Sellers */}
                    {data.recent_activity.sellers.length > 0 && (
                        <div className="glass-panel">
                            <div className="border-b border-white/5 p-4">
                                <h3 className="text-sm font-medium text-rose-400">Recent Sellers</h3>
                                <p className="mt-1 text-xs text-slate-400">Reduced or exited positions</p>
                            </div>
                            <div className="divide-y divide-white/5">
                                {data.recent_activity.sellers.map((holder, idx) => (
                                    <ActivityRow key={idx} holder={holder} type="sell" />
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({
    label,
    value,
    suffix,
    valueClassName,
}: {
    label: string;
    value: string | number;
    suffix?: string;
    valueClassName?: string;
}) {
    return (
        <div className="glass-stat">
            <p className="text-xs text-slate-400">{label}</p>
            <p className={`mt-1 text-2xl font-semibold ${valueClassName || "text-slate-100"}`}>
                {value} {suffix && <span className="text-sm text-slate-400">{suffix}</span>}
            </p>
        </div>
    );
}

function HolderRow({ holder }: { holder: SuperInvestorHolder }) {
    return (
        <div className="p-4 hover:bg-white/[0.02] transition-colors">
            <div className="flex items-start justify-between">
                <div className="flex-1">
                    <div className="flex items-center space-x-2">
                        <span className="inline-flex items-center rounded-full bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-400">
                            {holder.tag}
                        </span>
                        <ChangeIndicator type={holder.change_type} change={holder.change_pct} />
                    </div>
                    <p className="mt-1.5 font-medium text-slate-100">{holder.investor_name}</p>
                    <p className="text-xs text-slate-400">{holder.firm}</p>
                    <p className="mt-1 text-xs text-slate-500">{holder.style}</p>
                    {holder.quarter_date && (
                        <p className="mt-1 text-xs text-indigo-400">
                            {getQuarterLabel(holder.quarter_date)} holding
                        </p>
                    )}
                </div>
                <div className="text-right">
                    <p className="text-sm font-medium text-slate-200">
                        {formatLargeNumber(holder.shares)} shares
                    </p>
                    <p className="text-xs text-slate-400">${formatMoney(holder.value)}</p>
                    <p className="mt-1 text-xs text-slate-500">
                        {(holder.portfolio_weight * 100).toFixed(2)}% of portfolio
                    </p>
                </div>
            </div>
        </div>
    );
}

function ActivityRow({ holder, type }: { holder: SuperInvestorHolder; type: "buy" | "sell" }) {
    const color = type === "buy" ? "emerald" : "rose";
    return (
        <div className="p-3">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm font-medium text-slate-200">{holder.investor_name}</p>
                    <p className="text-xs text-slate-400">{holder.firm}</p>
                </div>
                <div className="text-right">
                    <p className={`text-sm font-medium text-${color}-400`}>
                        {type === "buy" ? "+" : ""}
                        {holder.change_pct.toFixed(1)}%
                    </p>
                    <p className="text-xs text-slate-500">${formatMoney(holder.value)}</p>
                </div>
            </div>
        </div>
    );
}

function ChangeIndicator({ type, change }: { type: string; change: number }) {
    if (type === "new") {
        return (
            <span className="inline-flex items-center text-xs text-emerald-400">
                ✨ New
            </span>
        );
    }
    if (type === "sold") {
        return (
            <span className="inline-flex items-center text-xs text-rose-400">
                ✗ Sold
            </span>
        );
    }
    if (type === "held") {
        return (
            <span className="inline-flex items-center text-xs text-slate-400">
                ⟳ Held
            </span>
        );
    }
    const color = change > 0 ? "emerald" : "rose";
    const symbol = change > 0 ? "↑" : "↓";
    return (
        <span className={`inline-flex items-center text-xs text-${color}-400`}>
            {symbol} {Math.abs(change).toFixed(1)}%
        </span>
    );
}

function EmptyState({ symbol, onRefresh, refreshing }: { symbol: string; onRefresh?: () => void; refreshing?: boolean }) {
    return (
        <div className="glass-panel p-12 text-center">
            <div className="mx-auto h-16 w-16 rounded-full bg-slate-700/50 flex items-center justify-center mb-4">
                <svg className="h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
            </div>
            <h3 className="text-lg font-medium text-slate-200 mb-2">No Notable Holders</h3>
            <p className="text-sm text-slate-400 max-w-md mx-auto mb-6">
                {symbol} is not currently held by any tracked super investors in their latest 13F filings.
                This could mean it's under the radar or outside their investment mandate.
            </p>
            {onRefresh && (
                <button
                    onClick={onRefresh}
                    disabled={refreshing}
                    className={cn(
                        "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                        "text-[10px] font-black uppercase tracking-widest",
                        refreshing && "opacity-50 cursor-not-allowed",
                    )}
                >
                    <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                    {refreshing ? "Refreshing..." : "Refresh"}
                </button>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function formatLargeNumber(num: number): string {
    if (num >= 1_000_000) {
        return `${(num / 1_000_000).toFixed(2)}M`;
    }
    if (num >= 1_000) {
        return `${(num / 1_000).toFixed(1)}K`;
    }
    return num.toLocaleString();
}

function formatMoney(value: number): string {
    if (value >= 1_000_000_000) {
        return `${(value / 1_000_000_000).toFixed(2)}B`;
    }
    if (value >= 1_000_000) {
        return `${(value / 1_000_000).toFixed(1)}M`;
    }
    return `${(value / 1_000).toFixed(0)}K`;
}

function getQuarterLabel(quarterDate: string): string {
    // quarterDate format: "2025-12-31"
    const month = parseInt(quarterDate.slice(5, 7));
    const year = quarterDate.slice(0, 4);
    const q = month <= 3 ? 1 : month <= 6 ? 2 : month <= 9 ? 3 : 4;
    return `Q${q} ${year}`;
}

function getConvictionColor(level: string): string {
    switch (level) {
        case "very_high":
            return "text-emerald-400";
        case "high":
            return "text-emerald-500";
        case "moderate":
            return "text-amber-400";
        case "low":
            return "text-slate-400";
        default:
            return "text-slate-500";
    }
}