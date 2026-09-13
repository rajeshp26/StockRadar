"use client";
// web/src/app/(authenticated)/super-investors/page.tsx
// Super Investors analysis page (authenticated layout).
// Route: /super-investors
//
// Tab order: Overview → Top Stocks → Conviction Overlap → Activity → By Investor → Sectors

import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import { AlertTriangle, SearchX } from "lucide-react";
import {
    fetchSuperInvestorsOverview,
    fetchTopStocks,
    fetchOverlap,
    fetchActivity,
    fetchInvestorsList,
    fetchInvestorPortfolio,
    fetchSectors,
} from "@/features/super-investors/services/super-investors-page.service";
import type {
    OverviewData,
    TopStock,
    OverlapStock,
    ActivityItem,
    InvestorSummary,
    InvestorPortfolioData,
    SectorRow,
    ChangeType,
    ConvictionLevel,
} from "@/features/super-investors/types/super-investors-page.types";

// ─────────────────────────────────────────────────────────────────────────────
// Shared formatting helpers
// ─────────────────────────────────────────────────────────────────────────────

function fmtMoney(v: number | null | undefined): string {
    if (v == null) return "—";
    if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
    if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
    if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    return `$${(v / 1e3).toFixed(0)}K`;
}

function fmtShares(v: number | null | undefined): string {
    if (v == null) return "—";
    if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toLocaleString();
}

function fmtPct(v: number | null | undefined, decimals = 2): string {
    if (v == null) return "—";
    return `${(v * 100).toFixed(decimals)}%`;
}

function fmtQuarter(dateStr: string): string {
    if (!dateStr) return "";
    const m = parseInt(dateStr.slice(5, 7));
    const y = dateStr.slice(2, 4);
    const q = m <= 3 ? 1 : m <= 6 ? 2 : m <= 9 ? 3 : 4;
    return `Q${q} '${y}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared UI atoms
// ─────────────────────────────────────────────────────────────────────────────

const SURFACE =
    "rounded-2xl border border-au-border bg-au-bg-elevated shadow-[var(--au-shadow-sm)]";

const FOCUS_RING =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50";

function Spinner() {
    return (
        <div className="space-y-3 px-4 py-6" role="status" aria-label="Loading">
            {[100, 84, 92, 76, 60].map((w, i) => (
                <div
                    key={i}
                    className={cn(
                        "h-4 rounded-md",
                        i === 4 && "border-b border-transparent",
                        "animate-shimmer bg-[linear-gradient(100deg,rgba(255,255,255,0.04),rgba(255,255,255,0.10),rgba(255,255,255,0.04))] bg-[length:200%_100%] motion-reduce:animate-none motion-reduce:bg-white/5"
                    )}
                    style={{ width: `${w}%` }}
                />
            ))}
        </div>
    );
}

function ErrorState({ message }: { message: string }) {
    return (
        <div className={cn(SURFACE, "flex flex-col items-center gap-2 p-8 text-center")}>
            <AlertTriangle className="h-6 w-6 text-financial-warn" aria-hidden="true" />
            <p className="text-sm text-au-text-tertiary">{message}</p>
        </div>
    );
}

function EmptyState({ title, hint }: { title: string; hint?: string }) {
    return (
        <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
            <SearchX className="h-6 w-6 text-au-text-faint" aria-hidden="true" />
            <p className="text-sm text-au-text-tertiary">{title}</p>
            {hint && <p className="text-xs text-au-text-faint">{hint}</p>}
        </div>
    );
}

function MetricCard({
    label,
    value,
    sub,
    accent,
}: {
    label: string;
    value: string | number;
    sub?: string;
    accent?: string;
}) {
    return (
        <div className={cn(SURFACE, "p-4")}>
            <p className="text-xs text-au-text-tertiary">{label}</p>
            <p
                className={cn(
                    "mt-1 text-2xl font-semibold tabular-nums",
                    accent ?? "text-au-text"
                )}
            >
                {value}
            </p>
            {sub && <p className="mt-0.5 text-xs text-au-text-faint tabular-nums">{sub}</p>}
        </div>
    );
}

function ChangeTypeBadge({ type }: { type: ChangeType }) {
    const map: Record<ChangeType, { label: string; cls: string }> = {
        new: { label: "New", cls: "bg-violet-500/15 text-violet-300" },
        increased: { label: "Added", cls: "bg-financial-up-bg text-financial-up-muted" },
        decreased: { label: "Trimmed", cls: "bg-financial-warn-bg text-financial-warn" },
        held: { label: "Held", cls: "bg-financial-neutral-bg text-au-text-tertiary" },
        sold: { label: "Exited", cls: "bg-financial-down-bg text-financial-down-muted" },
    };
    const { label, cls } = map[type] ?? { label: type, cls: "text-au-text-tertiary" };
    return (
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", cls)}>
            {label}
        </span>
    );
}

function ConvictionBadge({ level }: { level: ConvictionLevel }) {
    const map: Record<ConvictionLevel, { label: string; cls: string }> = {
        very_high: { label: "Very High", cls: "text-financial-up-muted" },
        high: { label: "High", cls: "text-financial-up" },
        moderate: { label: "Moderate", cls: "text-financial-warn" },
        low: { label: "Low", cls: "text-au-text-tertiary" },
        none: { label: "None", cls: "text-au-text-faint" },
    };
    const { label, cls } = map[level] ?? { label: level, cls: "text-au-text-tertiary" };
    return <span className={cn("text-xs font-medium", cls)}>{label}</span>;
}

function InvestorDot({ tag }: { tag: string }) {
    // Stable color per tag initial
    const colors = [
        "bg-indigo-500/25 text-indigo-400",
        "bg-emerald-500/25 text-emerald-400",
        "bg-amber-500/25 text-amber-400",
        "bg-rose-500/25 text-rose-400",
        "bg-cyan-500/25 text-cyan-400",
        "bg-violet-500/25 text-violet-400",
    ];
    const idx = (tag.charCodeAt(0) + (tag.charCodeAt(1) ?? 0)) % colors.length;
    return (
        <span
            className={cn(
                "inline-flex h-6 w-6 items-center justify-center rounded-full text-[9px] font-semibold",
                colors[idx]
            )}
            title={tag}
        >
            {tag.slice(0, 2)}
        </span>
    );
}

function SectionHeader({ title, sub }: { title: string; sub?: string }) {
    return (
        <div className="border-b border-au-border p-4">
            <h3 className="text-sm font-medium text-au-text-secondary">{title}</h3>
            {sub && <p className="mt-0.5 text-xs text-au-text-tertiary">{sub}</p>}
        </div>
    );
}

function FilterChip({
    label,
    active,
    onClick,
}: {
    label: string;
    active: boolean;
    onClick: () => void;
}) {
    return (
        <button
            onClick={onClick}
            className={cn(
                "rounded-full border px-3 py-1 text-xs tabular-nums transition-colors",
                FOCUS_RING,
                active
                    ? "border-violet-400/60 bg-violet-500/15 text-violet-300"
                    : "border-au-border text-au-text-tertiary hover:border-au-border-strong hover:text-au-text-secondary"
            )}
        >
            {label}
        </button>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab definitions
// ─────────────────────────────────────────────────────────────────────────────

type TabId =
    | "overview"
    | "top-stocks"
    | "overlap"
    | "activity"
    | "by-investor"
    | "sectors";

const TABS: { id: TabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "top-stocks", label: "Top Stocks" },
    { id: "overlap", label: "Conviction Overlap" },
    { id: "activity", label: "Activity Feed" },
    { id: "by-investor", label: "By Investor" },
    { id: "sectors", label: "Sectors" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Overview
// ─────────────────────────────────────────────────────────────────────────────

function OverviewTab() {
    const { data, isLoading, error } = useQuery({
        queryKey: QK.superInvestorsOverview(),
        queryFn: fetchSuperInvestorsOverview,
        staleTime: 1000 * 60 * 60, // 1h — data is quarterly
    });

    if (isLoading) return <Spinner />;
    if (error || !data) return <ErrorState message="Failed to load overview." />;

    return (
        <div className="space-y-6">
            {/* Summary metrics */}
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <MetricCard label="Investors tracked" value={data.investors_tracked} />
                <MetricCard label="Stocks held" value={data.stocks_held} />
                <MetricCard
                    label="New positions"
                    value={data.new_positions}
                    sub={fmtQuarter(data.latest_quarter)}
                    accent="text-financial-up"
                />
                <MetricCard
                    label="Full exits"
                    value={data.full_exits}
                    sub={fmtQuarter(data.latest_quarter)}
                    accent="text-financial-down"
                />
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <MoverCard
                    title="Most added"
                    sub={`Most investors added — ${fmtQuarter(data.latest_quarter)}`}
                    items={data.most_added}
                    variant="buy"
                />
                <MoverCard
                    title="Most trimmed / exited"
                    sub={`Most investors reduced — ${fmtQuarter(data.latest_quarter)}`}
                    items={data.most_exited}
                    variant="sell"
                />
            </div>
        </div>
    );
}

function MoverCard({
    title,
    sub,
    items,
    variant,
}: {
    title: string;
    sub: string;
    items: OverviewData["most_added"];
    variant: "buy" | "sell";
}) {
    return (
        <div className={cn(SURFACE, "overflow-hidden")}>
            <SectionHeader title={title} sub={sub} />
            <div className="divide-y divide-au-border">
                {items.slice(0, 8).map((item) => (
                    <div
                        key={item.ticker}
                        className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02]"
                    >
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                                <span className="font-medium text-au-text text-sm">
                                    {item.ticker}
                                </span>
                                <span className="truncate text-xs text-au-text-tertiary">
                                    {item.company_name}
                                </span>
                            </div>
                            <div className="mt-1 flex flex-wrap gap-1">
                                {item.investor_tags.slice(0, 5).map((t) => (
                                    <InvestorDot key={t} tag={t} />
                                ))}
                                {item.investor_tags.length > 5 && (
                                    <span className="text-xs text-au-text-faint tabular-nums">
                                        +{item.investor_tags.length - 5}
                                    </span>
                                )}
                            </div>
                        </div>
                        <span
                            className={cn(
                                "rounded-full px-2.5 py-0.5 text-xs font-medium tabular-nums shrink-0",
                                variant === "buy"
                                    ? "bg-financial-up-bg text-financial-up-muted"
                                    : "bg-financial-down-bg text-financial-down-muted"
                            )}
                        >
                            {variant === "buy" ? "+" : "−"}
                            {item.investor_count} investors
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Top Stocks
// ─────────────────────────────────────────────────────────────────────────────

const SECTORS = ["All", "Technology", "Financials", "Consumer", "Healthcare", "Energy", "Industrials"];
const STYLES = ["All", "value", "growth", "activist", "lt_compounder", "sector"];
const STYLE_LABELS: Record<string, string> = {
    value: "Value", growth: "Growth", activist: "Activist",
    lt_compounder: "Compounders", sector: "Sector",
};

function TopStocksTab() {
    const [sector, setSector] = useState<string | undefined>();
    const [style, setStyle] = useState<string | undefined>();
    const [minInv, setMinInv] = useState(1);

    const { data, isLoading, error } = useQuery({
        queryKey: QK.superInvestorsTopStocks(sector, style, minInv),
        queryFn: () => fetchTopStocks({ sector, style, minInvestors: minInv, limit: 100 }),
        staleTime: 1000 * 60 * 60,
    });

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className={cn(SURFACE, "px-4 py-3")}>
                <div className="flex flex-wrap gap-4">
                    <div className="flex flex-wrap gap-2">
                        <span className="text-xs text-au-text-tertiary self-center mr-1">Sector</span>
                        {SECTORS.map((s) => (
                            <FilterChip
                                key={s}
                                label={s}
                                active={(sector ?? "All") === s}
                                onClick={() => setSector(s === "All" ? undefined : s)}
                            />
                        ))}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <span className="text-xs text-au-text-tertiary self-center mr-1">Style</span>
                        {STYLES.map((s) => (
                            <FilterChip
                                key={s}
                                label={s === "All" ? "All" : (STYLE_LABELS[s] ?? s)}
                                active={(style ?? "All") === s}
                                onClick={() => setStyle(s === "All" ? undefined : s)}
                            />
                        ))}
                    </div>
                    <div className="flex gap-2 items-center">
                        <span className="text-xs text-au-text-tertiary">Min investors</span>
                        {[1, 2, 3, 4, 5].map((n) => (
                            <FilterChip
                                key={n}
                                label={String(n) + "+"}
                                active={minInv === n}
                                onClick={() => setMinInv(n)}
                            />
                        ))}
                    </div>
                </div>
            </div>

            {/* Table */}
            <div className={cn(SURFACE, "overflow-hidden")}>
                <SectionHeader
                    title="Most widely held stocks"
                    sub={data ? `${data.total_stocks} stocks · ${fmtQuarter(data.quarter ?? "")}` : undefined}
                />
                {isLoading ? (
                    <Spinner />
                ) : error || !data ? (
                    <ErrorState message="Failed to load top stocks." />
                ) : (
                    <div className="divide-y divide-au-border">
                        {data.stocks.map((stock) => (
                            <TopStockRow key={stock.ticker} stock={stock} totalInvestors={data.total_stocks} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function TopStockRow({ stock, totalInvestors }: { stock: TopStock; totalInvestors: number }) {
    const barWidth = Math.round(stock.investor_breadth_pct * 100);
    return (
        <div className="flex items-center gap-4 px-4 py-3 hover:bg-white/[0.02]">
            <span className="w-6 text-right text-xs text-au-text-faint tabular-nums shrink-0">{stock.rank}</span>
            <div className="w-28 shrink-0">
                <p className="font-medium text-au-text text-sm">{stock.ticker}</p>
                <p className="truncate text-xs text-au-text-tertiary">{stock.company_name}</p>
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-white/5">
                        <div
                            className="h-1.5 rounded-full bg-violet-500/60"
                            style={{ width: `${barWidth}%` }}
                        />
                    </div>
                    <span className="text-xs text-au-text-secondary tabular-nums shrink-0">
                        {stock.investor_count} investors
                    </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                    {stock.investor_tags.slice(0, 6).map((t) => (
                        <InvestorDot key={t} tag={t} />
                    ))}
                </div>
            </div>
            <div className="text-right shrink-0 hidden md:block">
                <p className="text-sm text-au-text tabular-nums">{fmtMoney(stock.total_position_value)}</p>
                <ConvictionBadge level={stock.conviction_level} />
            </div>
            <div className="text-right shrink-0 w-16">
                <p className="text-xs text-au-text-tertiary tabular-nums">{fmtPct(stock.avg_portfolio_weight)} avg</p>
                {stock.sector && (
                    <p className="text-[10px] text-au-text-faint mt-0.5">{stock.sector}</p>
                )}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Conviction Overlap
// ─────────────────────────────────────────────────────────────────────────────

function OverlapTab() {
    const [minInv, setMinInv] = useState(3);
    const [sector, setSector] = useState<string | undefined>();

    const { data, isLoading, error } = useQuery({
        queryKey: QK.superInvestorsOverlap(minInv, sector),
        queryFn: () => fetchOverlap({ minInvestors: minInv, sector, limit: 100 }),
        staleTime: 1000 * 60 * 60,
    });

    return (
        <div className="space-y-4">
            <div className={cn(SURFACE, "px-4 py-3 flex flex-wrap gap-4")}>
                <div className="flex gap-2 items-center">
                    <span className="text-xs text-au-text-tertiary">Min overlap</span>
                    {[2, 3, 4, 5, 6].map((n) => (
                        <FilterChip
                            key={n}
                            label={`${n}+`}
                            active={minInv === n}
                            onClick={() => setMinInv(n)}
                        />
                    ))}
                </div>
                <div className="flex gap-2 items-center">
                    <span className="text-xs text-au-text-tertiary">Sector</span>
                    {SECTORS.map((s) => (
                        <FilterChip
                            key={s}
                            label={s}
                            active={(sector ?? "All") === s}
                            onClick={() => setSector(s === "All" ? undefined : s)}
                        />
                    ))}
                </div>
            </div>

            <div className={cn(SURFACE, "overflow-hidden")}>
                <SectionHeader
                    title="Consensus picks"
                    sub={`Stocks held by ${minInv}+ tracked investors — smart money overlap`}
                />
                {isLoading ? (
                    <Spinner />
                ) : error || !data ? (
                    <ErrorState message="Failed to load overlap data." />
                ) : data.stocks.length === 0 ? (
                    <EmptyState
                        title={`No stocks held by ${minInv}+ investors.`}
                        hint="Try lowering the overlap threshold."
                    />
                ) : (
                    <div className="divide-y divide-au-border">
                        {data.stocks.map((stock) => (
                            <OverlapRow key={stock.ticker} stock={stock} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function OverlapRow({ stock }: { stock: OverlapStock }) {
    const [expanded, setExpanded] = useState(false);
    return (
        <div>
            <button
                className={cn(
                    "w-full flex items-center gap-4 px-4 py-3 hover:bg-white/[0.02] text-left",
                    FOCUS_RING
                )}
                onClick={() => setExpanded((e) => !e)}
            >
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <span className="font-medium text-au-text text-sm">{stock.ticker}</span>
                        <span className="truncate text-xs text-au-text-tertiary">{stock.company_name}</span>
                        {stock.sector && (
                            <span className="hidden md:inline text-[10px] text-au-text-faint border border-au-border rounded px-1.5 py-0.5">
                                {stock.sector}
                            </span>
                        )}
                    </div>
                    <div className="mt-1.5 flex gap-1 flex-wrap">
                        {stock.investors.map((inv) => (
                            <InvestorDot key={inv.tag} tag={inv.tag} />
                        ))}
                    </div>
                </div>
                <div className="text-right shrink-0">
                    <p className="text-sm font-medium text-au-text tabular-nums">
                        {stock.investor_count} investors
                    </p>
                    <ConvictionBadge level={stock.conviction_level} />
                </div>
                <span className="text-au-text-faint text-xs ml-2">{expanded ? "▲" : "▼"}</span>
            </button>

            {expanded && (
                <div className="bg-white/[0.01] px-4 py-3 divide-y divide-au-border">
                    {stock.investors.map((inv) => (
                        <div key={inv.tag} className="flex items-center justify-between py-2">
                            <div className="flex items-center gap-2">
                                <InvestorDot tag={inv.tag} />
                                <div>
                                    <p className="text-sm text-au-text-secondary">{inv.investor_name}</p>
                                    <p className="text-xs text-au-text-faint">{inv.style}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <span className="text-xs text-au-text-tertiary tabular-nums">
                                    {fmtPct(inv.portfolio_weight)} of portfolio
                                </span>
                                <ChangeTypeBadge type={inv.change_type} />
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Activity Feed
// ─────────────────────────────────────────────────────────────────────────────

const CHANGE_TYPES = ["all", "new", "increased", "decreased", "sold"];
const CHANGE_LABELS: Record<string, string> = {
    all: "All", new: "New", increased: "Added",
    decreased: "Trimmed", sold: "Exited",
};

function ActivityTab() {
    const [changeType, setChangeType] = useState<string | undefined>();
    const [investorTag, setInvestorTag] = useState<string | undefined>();
    const [quarters, setQuarters] = useState(4);

    const { data, isLoading, error } = useQuery({
        queryKey: QK.superInvestorsActivity(changeType, investorTag, quarters),
        queryFn: () =>
            fetchActivity({ changeType, investorTag, quarters, limit: 200 }),
        staleTime: 1000 * 60 * 30,
    });

    // Build investor tag options from results
    const investorTags = useMemo(() => {
        if (!data) return [];
        const tags = [...new Set(data.activity.map((a) => a.investor_tag))].sort();
        return tags;
    }, [data]);

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className={cn(SURFACE, "px-4 py-3 space-y-3")}>
                <div className="flex flex-wrap gap-2 items-center">
                    <span className="text-xs text-au-text-tertiary mr-1">Action</span>
                    {CHANGE_TYPES.map((ct) => (
                        <FilterChip
                            key={ct}
                            label={CHANGE_LABELS[ct] ?? ct}
                            active={(changeType ?? "all") === ct}
                            onClick={() => setChangeType(ct === "all" ? undefined : ct)}
                        />
                    ))}
                </div>
                <div className="flex flex-wrap gap-2 items-center">
                    <span className="text-xs text-au-text-tertiary mr-1">Quarters</span>
                    {[2, 4, 8, 12].map((q) => (
                        <FilterChip
                            key={q}
                            label={`${q}Q`}
                            active={quarters === q}
                            onClick={() => setQuarters(q)}
                        />
                    ))}
                    {investorTags.length > 0 && (
                        <>
                            <span className="text-xs text-au-text-tertiary ml-3 mr-1">Investor</span>
                            <FilterChip
                                label="All"
                                active={!investorTag}
                                onClick={() => setInvestorTag(undefined)}
                            />
                            {investorTags.slice(0, 10).map((t) => (
                                <FilterChip
                                    key={t}
                                    label={t}
                                    active={investorTag === t}
                                    onClick={() => setInvestorTag(t)}
                                />
                            ))}
                        </>
                    )}
                </div>
            </div>

            <div className={cn(SURFACE, "overflow-hidden")}>
                <SectionHeader
                    title="Activity feed"
                    sub={
                        data
                            ? `${data.activity.length} moves across ${data.quarters_shown.map(fmtQuarter).join(", ")}`
                            : undefined
                    }
                />
                {isLoading ? (
                    <Spinner />
                ) : error || !data ? (
                    <ErrorState message="Failed to load activity." />
                ) : data.activity.length === 0 ? (
                    <EmptyState
                        title="No activity matching current filters."
                        hint="Adjust the action or quarter filters."
                    />
                ) : (
                    <div className="divide-y divide-au-border">
                        {data.activity.map((item, idx) => (
                            <ActivityRow key={idx} item={item} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function ActivityRow({ item }: { item: ActivityItem }) {
    const changeSign =
        (item.shares_change_pct ?? 0) > 0
            ? "+"
            : "";

    return (
        <div className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02]">
            <span className="text-xs text-au-text-faint tabular-nums shrink-0 w-14">
                {fmtQuarter(item.quarter_end_date)}
            </span>
            <InvestorDot tag={item.investor_tag} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-au-text-secondary">
                        {item.investor_name}
                    </span>
                    <ChangeTypeBadge type={item.change_type} />
                    <span className="font-medium text-au-text text-sm">{item.ticker}</span>
                    <span className="truncate text-xs text-au-text-tertiary hidden md:inline">
                        {item.company_name}
                    </span>
                </div>
                <p className="mt-0.5 text-xs text-au-text-faint">{item.style}</p>
            </div>
            <div className="text-right shrink-0">
                <p className="text-sm text-au-text tabular-nums">{fmtMoney(item.position_value)}</p>
                {item.shares_change_pct != null && Math.abs(item.shares_change_pct) >= 0.5 && (
                    <p
                        className={cn(
                            "text-xs tabular-nums",
                            (item.shares_change_pct ?? 0) > 0
                                ? "text-financial-up-muted"
                                : "text-financial-down-muted"
                        )}
                    >
                        {changeSign}
                        {item.shares_change_pct.toFixed(1)}%
                    </p>
                )}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: By Investor
// ─────────────────────────────────────────────────────────────────────────────

function ByInvestorTab() {
    const [selectedTag, setSelectedTag] = useState<string | null>(null);

    const { data: listData, isLoading: listLoading } = useQuery({
        queryKey: QK.superInvestorsList(),
        queryFn: fetchInvestorsList,
        staleTime: 1000 * 60 * 60,
    });

    // Auto-select first investor once list loads
    const activeTag = selectedTag ?? listData?.investors[0]?.tag ?? null;

    const { data: portfolioData, isLoading: portfolioLoading } = useQuery({
        queryKey: QK.superInvestorPortfolio(activeTag ?? "", 8),
        queryFn: () => fetchInvestorPortfolio(activeTag!, 8),
        enabled: !!activeTag,
        staleTime: 1000 * 60 * 60,
    });

    return (
        <div className="space-y-4">
            {/* Investor selector */}
            {listLoading ? (
                <Spinner />
            ) : (
                <div className={cn(SURFACE, "px-4 py-3")}>
                    <div className="flex flex-wrap gap-2">
                        {(listData?.investors ?? []).map((inv) => (
                            <FilterChip
                                key={inv.tag}
                                label={inv.investor_name.split(" ").slice(0, 2).join(" ")}
                                active={activeTag === inv.tag}
                                onClick={() => setSelectedTag(inv.tag)}
                            />
                        ))}
                    </div>
                </div>
            )}

            {/* Investor summary cards */}
            {listData && activeTag && (
                <InvestorSummaryCards
                    summary={listData.investors.find((i) => i.tag === activeTag)}
                />
            )}

            {/* Portfolio detail */}
            {portfolioLoading ? (
                <Spinner />
            ) : portfolioData ? (
                <InvestorPortfolioDetail data={portfolioData} />
            ) : null}
        </div>
    );
}

function InvestorSummaryCards({ summary }: { summary?: InvestorSummary }) {
    if (!summary) return null;
    return (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <MetricCard
                label="Portfolio value"
                value={fmtMoney(summary.portfolio_value)}
            />
            <MetricCard
                label="Positions"
                value={summary.positions_count}
            />
            <MetricCard
                label="Top holding"
                value={summary.top_holding_ticker || "—"}
                sub={fmtPct(summary.top_holding_weight)}
            />
            <MetricCard
                label="Last filed"
                value={summary.last_filed_period ? fmtQuarter(summary.last_filed_period) : "—"}
            />
        </div>
    );
}

function InvestorPortfolioDetail({ data }: { data: InvestorPortfolioData }) {
    return (
        <div className="space-y-4">
            {/* Sector breakdown */}
            {data.sector_breakdown.length > 0 && (
                <div className={cn(SURFACE, "overflow-hidden")}>
                    <SectionHeader title="Sector allocation" />
                    <div className="p-4 space-y-2">
                        {data.sector_breakdown.map((s) => (
                            <div key={s.sector} className="flex items-center gap-3">
                                <span className="w-32 shrink-0 text-xs text-au-text-tertiary">
                                    {s.sector}
                                </span>
                                <div className="flex-1 h-1.5 rounded-full bg-white/5">
                                    <div
                                        className="h-1.5 rounded-full bg-violet-500/50"
                                        style={{ width: `${Math.round(s.weight * 100)}%` }}
                                    />
                                </div>
                                <span className="text-xs text-au-text-secondary w-12 text-right tabular-nums">
                                    {fmtPct(s.weight)}
                                </span>
                                <span className="text-xs text-au-text-faint w-20 text-right hidden md:block tabular-nums">
                                    {fmtMoney(s.value)}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Holdings table */}
            <div className={cn(SURFACE, "overflow-hidden")}>
                <SectionHeader
                    title="Portfolio holdings"
                    sub={`${data.positions_count} positions · ${fmtQuarter(data.latest_quarter ?? "")}`}
                />
                <div className="divide-y divide-au-border">
                    {data.holdings.map((h) => (
                        <HoldingRow key={h.ticker} holding={h} />
                    ))}
                </div>
            </div>
        </div>
    );
}

function HoldingRow({ holding }: { holding: InvestorPortfolioData["holdings"][number] }) {
    const [expanded, setExpanded] = useState(false);
    const barW = Math.round((holding.portfolio_weight ?? 0) * 100);

    return (
        <div>
            <button
                className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02] text-left",
                    FOCUS_RING,
                    holding.history.length === 0 && "cursor-default"
                )}
                onClick={() => setExpanded((e) => !e)}
                disabled={holding.history.length === 0}
            >
                <span className="text-xs text-au-text-faint w-6 text-right tabular-nums shrink-0">
                    {holding.rank}
                </span>
                <div className="w-24 shrink-0">
                    <p className="font-medium text-sm text-au-text">{holding.ticker}</p>
                    <p className="text-xs text-au-text-faint truncate">{holding.company_name}</p>
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <div className="h-1.5 flex-1 rounded-full bg-white/5 max-w-[120px]">
                            <div
                                className="h-1.5 rounded-full bg-violet-500/50"
                                style={{ width: `${Math.min(barW * 2, 100)}%` }}
                            />
                        </div>
                        <span className="text-xs text-au-text-secondary tabular-nums">{fmtPct(holding.portfolio_weight)}</span>
                    </div>
                </div>
                <div className="text-right shrink-0">
                    <p className="text-sm text-au-text tabular-nums">{fmtMoney(holding.position_value)}</p>
                    <p className="text-xs text-au-text-tertiary tabular-nums">{fmtShares(holding.shares_held)} sh</p>
                </div>
                <ChangeTypeBadge type={holding.change_type} />
                {holding.history.length > 0 && (
                    <span className="text-au-text-faint text-xs ml-1">{expanded ? "▲" : "▼"}</span>
                )}
            </button>

            {expanded && holding.history.length > 0 && (
                <div className="bg-white/[0.015] border-t border-au-border px-8 py-2">
                    <div className="flex gap-4 overflow-x-auto pb-1">
                        {holding.history.map((h) => (
                            <div key={h.quarter} className="shrink-0 text-center">
                                <p className="text-[10px] text-au-text-faint">{fmtQuarter(h.quarter)}</p>
                                <p className="text-xs text-au-text-secondary mt-0.5 tabular-nums">
                                    {fmtShares(h.shares_held)}
                                </p>
                                <ChangeTypeBadge type={h.change_type} />
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Sectors
// ─────────────────────────────────────────────────────────────────────────────

function SectorsTab() {
    const [style, setStyle] = useState<string | undefined>();

    const { data, isLoading, error } = useQuery({
        queryKey: QK.superInvestorsSectors(style),
        queryFn: () => fetchSectors(style),
        staleTime: 1000 * 60 * 60,
    });

    const maxValue = useMemo(
        () => Math.max(...(data?.sectors ?? []).map((s) => s.total_value)),
        [data]
    );

    return (
        <div className="space-y-4">
            <div className={cn(SURFACE, "px-4 py-3 flex gap-2 items-center")}>
                <span className="text-xs text-au-text-tertiary mr-1">Style</span>
                {STYLES.map((s) => (
                    <FilterChip
                        key={s}
                        label={s === "All" ? "All" : (STYLE_LABELS[s] ?? s)}
                        active={(style ?? "All") === s}
                        onClick={() => setStyle(s === "All" ? undefined : s)}
                    />
                ))}
            </div>

            <div className={cn(SURFACE, "overflow-hidden")}>
                <SectionHeader
                    title="Sector exposure"
                    sub={data ? `Aggregate across all investors · ${fmtQuarter(data.quarter ?? "")}` : undefined}
                />
                {isLoading ? (
                    <Spinner />
                ) : error || !data ? (
                    <ErrorState message="Failed to load sectors." />
                ) : (
                    <div className="divide-y divide-au-border">
                        {data.sectors.map((sector) => (
                            <SectorRow key={sector.sector} sector={sector} maxValue={maxValue} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function SectorRow({ sector, maxValue }: { sector: SectorRow; maxValue: number }) {
    const [expanded, setExpanded] = useState(false);
    const barW = maxValue > 0 ? Math.round((sector.total_value / maxValue) * 100) : 0;

    return (
        <div>
            <button
                className={cn(
                    "w-full flex items-center gap-4 px-4 py-3 hover:bg-white/[0.02] text-left",
                    FOCUS_RING
                )}
                onClick={() => setExpanded((e) => !e)}
            >
                <div className="w-36 shrink-0">
                    <p className="text-sm font-medium text-au-text-secondary">{sector.sector}</p>
                    <p className="text-xs text-au-text-faint tabular-nums">
                        {sector.stock_count} stocks · {sector.investor_count} investors
                    </p>
                </div>
                <div className="flex-1">
                    <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-white/5">
                            <div
                                className="h-2 rounded-full bg-violet-500/50"
                                style={{ width: `${barW}%` }}
                            />
                        </div>
                        <span className="text-sm text-au-text tabular-nums shrink-0 w-20 text-right">
                            {fmtMoney(sector.total_value)}
                        </span>
                    </div>
                </div>
                <span className="text-au-text-faint text-xs ml-2">{expanded ? "▲" : "▼"}</span>
            </button>

            {expanded && (
                <div className="bg-white/[0.01] px-4 pb-3 pt-1">
                    <p className="text-xs text-au-text-faint mb-2">Top holdings</p>
                    <div className="flex flex-wrap gap-3">
                        {sector.top_stocks.map((s) => (
                            <div
                                key={s.ticker}
                                className="flex items-center gap-2 rounded-lg border border-au-border px-3 py-1.5"
                            >
                                <span className="text-sm font-medium text-au-text-secondary">{s.ticker}</span>
                                <span className="text-xs text-au-text-tertiary tabular-nums">{fmtMoney(s.total_value)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Root page
// ─────────────────────────────────────────────────────────────────────────────

export default function SuperInvestorsPage() {
    const [activeTab, setActiveTab] = useState<TabId>("overview");

    return (
        <div className="mx-auto max-w-6xl space-y-6">
            {/* Page header */}
            <div>
                <h1 className="text-2xl font-bold tracking-tight text-au-text">Super Investors</h1>
                <p className="mt-1 text-sm text-au-text-tertiary">
                    13F institutional holdings from 24 tracked value and growth investors
                </p>
            </div>

            {/* Tab nav — the single glass slot on this page */}
            <div className="glass-segmented w-fit max-w-full overflow-x-auto styled-scrollbar">
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={cn(
                            "glass-segmented-item",
                            activeTab === tab.id && "active si-tab-active"
                        )}
                        aria-current={activeTab === tab.id ? "page" : undefined}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            <div>
                {activeTab === "overview" && <OverviewTab />}
                {activeTab === "top-stocks" && <TopStocksTab />}
                {activeTab === "overlap" && <OverlapTab />}
                {activeTab === "activity" && <ActivityTab />}
                {activeTab === "by-investor" && <ByInvestorTab />}
                {activeTab === "sectors" && <SectorsTab />}
            </div>
        </div>
    );
}