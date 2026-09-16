'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/currency';
import type { AllocationSegment, TypeAllocationSegment } from '../types/portfolio.types';
import { buildAllocationRows, computeAllocationMetrics, computeTypeShares } from '../lib/allocation-breakdown';

export type { AllocationRow as CombinedRow } from '../lib/allocation-breakdown';

const DONUT_COLORS = [
    '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#f97316', '#ec4899', '#14b8a6', '#84cc16',
    '#a855f7', '#0ea5e9',
];

const CX = 140;
const CY = 140;
const OUTER_R = 120;
const INNER_R = 73;
const POP_DISTANCE = 8;

interface AllocationOverviewCardProps {
    types: TypeAllocationSegment[];
    segments: AllocationSegment[];
    totalValue: number;
    currency?: string | null;
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function createDonutSlicePath(
    cx: number,
    cy: number,
    outerR: number,
    innerR: number,
    startAngle: number,
    endAngle: number,
): string {
    const outerStart = polarToCartesian(cx, cy, outerR, startAngle);
    const outerEnd = polarToCartesian(cx, cy, outerR, endAngle);
    const innerStart = polarToCartesian(cx, cy, innerR, startAngle);
    const innerEnd = polarToCartesian(cx, cy, innerR, endAngle);
    const largeArcFlag = endAngle - startAngle > 180 ? 1 : 0;

    return [
        `M ${outerStart.x} ${outerStart.y}`,
        `A ${outerR} ${outerR} 0 ${largeArcFlag} 1 ${outerEnd.x} ${outerEnd.y}`,
        `L ${innerEnd.x} ${innerEnd.y}`,
        `A ${innerR} ${innerR} 0 ${largeArcFlag} 0 ${innerStart.x} ${innerStart.y}`,
        'Z',
    ].join(' ');
}

function popVector(angleDeg: number, distance: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: Math.cos(rad) * distance, y: Math.sin(rad) * distance };
}

export function AllocationOverviewCard({
    types,
    segments,
    totalValue,
    currency,
}: AllocationOverviewCardProps) {
    const reduce = useReducedMotion();
    const [hoverKey, setHoverKey] = useState<string | null>(null);
    const [selectKey, setSelectKey] = useState<string | null>(null);
    const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
    const stageRef = useRef<HTMLDivElement>(null);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        const t = setTimeout(() => setMounted(true), 800);
        return () => clearTimeout(t);
    }, []);

    const { rows, metrics, typeShares } = useMemo(() => {
        const built = buildAllocationRows(types, segments).map((row, i) => ({
            ...row,
            color: DONUT_COLORS[i % DONUT_COLORS.length],
        }));
        return { rows: built, metrics: computeAllocationMetrics(built), typeShares: computeTypeShares(built) };
    }, [types, segments]);
    const activeKey = hoverKey ?? selectKey;

    const visibleSlices = rows.filter((r) => r.pct > 0);
    const totalPct = visibleSlices.reduce((sum, r) => sum + r.pct, 0);
    const maxPct = Math.max(...rows.map((r) => r.pct), 0);
    const hasTypedRows = typeShares.length > 0;

    const total = totalValue > 0 ? totalValue : rows.reduce((sum, r) => sum + r.value, 0);
    const hoveredRow = rows.find((r) => r.key === hoverKey) ?? null;

    const toggleSelect = (key: string) => setSelectKey((cur) => (cur === key ? null : key));
    const clearHover = () => setHoverKey(null);

    const onStageMove = (e: React.MouseEvent) => {
        const rect = stageRef.current?.getBoundingClientRect();
        if (!rect) return;
        setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });

        // Deterministic hit-test: map pointer polar coords (viewBox space) onto the
        // RAW slice angle ranges (before gaps), so the ring band highlights exactly
        // one slice — no flicker across gap wedges or the inner/outer edges.
        const dx = ((e.clientX - rect.left) / rect.width) * 280 - CX;
        const dy = ((e.clientY - rect.top) / rect.height) * 280 - CY;
        const r = Math.hypot(dx, dy);
        if (r < INNER_R - 2 || r > OUTER_R + 6) {
            setHoverKey(null);
            return;
        }
        const pointerAngle = ((Math.atan2(dy, dx) * 180) / Math.PI + 90 + 360) % 360;
        let cursorAngle = 0;
        let hovered: string | null = null;
        for (const row of visibleSlices) {
            const rawEnd = cursorAngle + (row.pct / totalPct) * 360;
            if (pointerAngle >= cursorAngle && pointerAngle < rawEnd) {
                hovered = row.key;
                break;
            }
            cursorAngle = rawEnd;
        }
        // Float-safety: map the tail of the wrap gap to the last slice.
        setHoverKey(hovered ?? visibleSlices[visibleSlices.length - 1]?.key ?? null);
    };

    const onSpotlightMove = (e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty('--mx', `${e.clientX - rect.left}px`);
        e.currentTarget.style.setProperty('--my', `${e.clientY - rect.top}px`);
    };

    let currentAngle = 0;
    const slices = visibleSlices.map((row) => {
        const angleSpan = (row.pct / totalPct) * 360;
        const rawStart = currentAngle;
        const rawEnd = currentAngle + angleSpan;
        const gap = Math.min(1.05, angleSpan * 0.32);
        const startAngle = rawStart + gap;
        const endAngle = rawEnd - gap;
        const midAngle = rawStart + angleSpan / 2;
        const pop = popVector(midAngle, POP_DISTANCE);
        currentAngle = rawEnd;

        return { row, d: createDonutSlicePath(CX, CY, OUTER_R, INNER_R, startAngle, endAngle), pop, midAngle };
    });

    const sliceActive = (key: string) => activeKey != null && activeKey === key;
    const anyActive = activeKey != null;

    return (
        <div
            className="glass-panel overflow-hidden"
            onPointerMove={onSpotlightMove}
        >
            {/* Cursor spotlight */}
            <div
                aria-hidden
                className="pointer-events-none absolute inset-0 z-0 opacity-0 transition-opacity duration-300 hover:opacity-100"
                style={{
                    background:
                        'radial-gradient(520px circle at var(--mx, 50%) var(--my, 50%), rgba(96,165,250,0.10), transparent 42%)',
                }}
            />

            <div className="relative z-10 p-6">
                {/* Header */}
                <div className="flex items-start justify-between gap-4 mb-5">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
                            Animated allocation
                        </p>
                        <h3 className="text-base font-black text-white tracking-tight">
                            Sector &amp; Asset Classes
                        </h3>
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-widest text-white/30 whitespace-nowrap">
                        Sorted by weight
                    </span>
                </div>

                {/* Metrics strip */}
                <div data-testid="assets-metrics" className="flex flex-wrap gap-3 mb-5">
                    {[
                        { label: 'Total value', value: formatCurrency(total, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 }) },
                        ...(hasTypedRows
                            ? typeShares.map((t) => ({ label: t.label, value: `${t.pct.toFixed(1)}%` }))
                            : [
                                { label: 'Sectors', value: `${rows.length}` },
                                { label: 'Holdings', value: `${metrics.holdingsCount}` },
                            ]),
                    ].map((m) => (
                        <div
                            key={m.label}
                            className="flex-1 min-w-[110px] rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2.5"
                        >
                            <p className="text-[9px] font-black uppercase tracking-widest text-white/35 mb-1">
                                {m.label}
                            </p>
                            <p className="text-sm font-black text-white tabular-nums">{m.value}</p>
                        </div>
                    ))}
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-[minmax(300px,0.9fr)_minmax(0,1.1fr)] gap-6">
                    {/* ── Left: donut ── */}
                    <div className="flex flex-col gap-5 min-w-0">
                        <div
                            ref={stageRef}
                            className="relative mx-auto w-full max-w-[300px] aspect-square select-none"
                            onMouseMove={onStageMove}
                            onMouseLeave={() => {
                                clearHover();
                                setTooltipPos(null);
                            }}
                        >
                            <svg
                                viewBox="0 0 280 280"
                                role="img"
                                aria-label="Donut chart of sector and asset class allocation"
                                className="h-full w-full overflow-visible"
                            >
                                <circle className="fill-none" cx={CX} cy={CY} r={96} stroke="rgba(148,163,184,0.11)" strokeWidth={46} />
                                {slices.map(({ row, d, pop }, i) => {
                                    const active = sliceActive(row.key);
                                    const dimmed = anyActive && !active;
                                    return (
                                        <motion.path
                                            key={row.key}
                                            d={d}
                                            fill={row.color}
                                            tabIndex={0}
                                            aria-label={`${row.type} ${row.sector}, ${row.pct.toFixed(1)}%, ${formatCurrency(row.value, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`}
                                            className="cursor-pointer outline-none"
                                            style={{ transformBox: 'view-box', transformOrigin: '140px 140px' }}
                                            initial={reduce ? false : { opacity: 0, transform: 'translate(0px, 0px) scale(1)' }}
                                            animate={{
                                                opacity: dimmed ? 0.22 : 1,
                                                transform: active
                                                    ? `translate(${pop.x}px, ${pop.y}px) scale(1.035)`
                                                    : 'translate(0px, 0px) scale(1)',
                                            }}
                                            transition={
                                                reduce
                                                    ? { duration: 0 }
                                                    : {
                                                        opacity: mounted
                                                            ? { duration: 0.3, ease: [0.16, 1, 0.3, 1] }
                                                            : { duration: 0.22, delay: i * 0.045 },
                                                        transform: mounted
                                                            ? { type: 'spring', stiffness: 280, damping: 30 }
                                                            : { type: 'spring', stiffness: 380, damping: 26, delay: i * 0.045 },
                                                    }
                                            }
                                            onFocus={() => setHoverKey(row.key)}
                                            onBlur={clearHover}
                                            onClick={() => toggleSelect(row.key)}
                                        />
                                    );
                                })}
                                <circle className="fill-none" cx={CX} cy={CY} r={70} stroke="rgba(255,255,255,0.10)" strokeWidth={1} />
                            </svg>

                            {/* Center bubble */}
                            <div className="pointer-events-none absolute inset-[27.5%] grid place-items-center rounded-full border border-white/[0.09] bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.09),transparent_55%),linear-gradient(180deg,rgba(15,23,42,0.98),rgba(9,14,27,0.98))] text-center shadow-[inset_0_0_0_10px_rgba(255,255,255,0.025),0_18px_42px_rgba(0,0,0,0.34)]">
                                <AnimatePresence mode="wait" initial={false}>
                                    <motion.div
                                        key={hoveredRow?.key ?? 'total'}
                                        initial={reduce ? false : { opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: -6 }}
                                        transition={reduce ? { duration: 0 } : { duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                                        className="px-4"
                                    >
                                        <p className="mb-1 text-[9px] font-black uppercase tracking-widest text-white/50">
                                            {hoveredRow ? hoveredRow.type : 'Total value'}
                                        </p>
                                        <p className="text-2xl font-black tracking-tight text-white tabular-nums">
                                            {hoveredRow
                                                ? `${hoveredRow.pct.toFixed(1)}%`
                                                : formatCurrency(total, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                        </p>
                                        <p className="mx-auto mt-1 max-w-[120px] text-[10px] font-bold leading-tight text-indigo-200/90">
                                            {hoveredRow
                                                ? `${hoveredRow.sector} • ${formatCurrency(hoveredRow.value, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
                                                : 'Hover a slice or row'}
                                        </p>
                                    </motion.div>
                                </AnimatePresence>
                            </div>

                            {/* Tooltip */}
                            {hoveredRow && tooltipPos && (
                                <motion.div
                                    aria-hidden
                                    initial={reduce ? false : { opacity: 0, scale: 0.96 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    className="pointer-events-none absolute z-20 min-w-[180px] rounded-2xl border border-white/20 bg-[rgba(5,10,20,0.94)] p-3 shadow-[0_18px_50px_rgba(0,0,0,0.45)]"
                                    style={{
                                        left: tooltipPos.x,
                                        top: tooltipPos.y,
                                        transform: 'translate(-50%, -138%)',
                                    }}
                                >
                                    <div className="mb-2 flex items-center gap-2">
                                        <span
                                            className="h-2.5 w-2.5 shrink-0 rounded-full"
                                            style={{ background: hoveredRow.color, boxShadow: `0 0 18px ${hoveredRow.color}` }}
                                        />
                                        <div className="min-w-0">
                                            <p className="text-xs font-bold text-white leading-tight">{hoveredRow.sector}</p>
                                            <p className="text-[10px] font-black uppercase tracking-wider text-white/50">{hoveredRow.type}</p>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[11px]">
                                        <span className="font-bold text-white/60">Weight</span>
                                        <b className="font-black text-white tabular-nums">{hoveredRow.pct.toFixed(1)}%</b>
                                        <span className="font-bold text-white/60">Value</span>
                                        <b className="font-black text-white tabular-nums">
                                            {formatCurrency(hoveredRow.value, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                        </b>
                                        <span className="font-bold text-white/60">Gain / Loss</span>
                                        <b className={cn('font-black tabular-nums', hoveredRow.gain_loss >= 0 ? 'text-financial-up' : 'text-financial-down')}>
                                            {hoveredRow.gain_loss >= 0 ? '+' : ''}
                                            {formatCurrency(hoveredRow.gain_loss, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                        </b>
                                    </div>
                                </motion.div>
                            )}
                        </div>
                    </div>

                    {/* ── Right: full table, scrollable ── */}
                    <div className="overflow-hidden">
                        <div className="max-h-[440px] overflow-y-auto pr-1 styled-scrollbar">
                            <table className="-mt-1.5 w-full border-separate border-spacing-y-1.5" aria-label="Combined sector and asset class allocation">
                                <thead className="sticky top-0 z-10">
                                    <tr className="text-left text-[9px] font-black uppercase tracking-widest text-au-text-tertiary">
                                        <th className="bg-au-bg-elevated pb-1.5 pr-3 pt-1 font-black shadow-[0_7px_0_0_var(--au-bg-elevated)]">Sector</th>
                                        <th className="bg-au-bg-elevated pb-1.5 pr-3 pt-1 font-black text-right shadow-[0_7px_0_0_var(--au-bg-elevated)]">Weight</th>
                                        <th className="bg-au-bg-elevated pb-1.5 pr-3 pt-1 font-black text-right shadow-[0_7px_0_0_var(--au-bg-elevated)]">Value</th>
                                        <th className="bg-au-bg-elevated pb-1.5 pt-1 font-black text-right shadow-[0_7px_0_0_var(--au-bg-elevated)]">Exposure</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map((row, i) => {
                                        const active = sliceActive(row.key);
                                        const relativeWidth = row.pct > 0 ? Math.max((row.pct / maxPct) * 100, 3) : 0;
                                        return (
                                            <motion.tr
                                                key={row.key}
                                                tabIndex={0}
                                                initial={reduce ? false : { opacity: 0, y: 10 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                transition={{ delay: reduce ? 0 : i * 0.04 + 0.18, duration: 0.32 }}
                                                className={cn(
                                                    'cursor-pointer outline-none',
                                                    active && '[&_td]:bg-white/[0.08]'
                                                )}
                                                onMouseEnter={() => setHoverKey(row.key)}
                                                onMouseLeave={clearHover}
                                                onFocus={() => setHoverKey(row.key)}
                                                onBlur={clearHover}
                                                onClick={() => toggleSelect(row.key)}
                                            >
                                                <td className="rounded-l-xl border-y border-l border-white/[0.06] bg-white/[0.03] px-3 py-2.5 transition-colors">
                                                    <div className="flex items-center gap-2.5">
                                                        <span
                                                            className="h-2 w-2 shrink-0 rounded-full"
                                                            style={{ background: row.color, boxShadow: `0 0 10px ${row.color}` }}
                                                        />
                                                        <div className="min-w-0">
                                                            <p className="truncate text-xs font-bold text-white leading-tight">{row.sector}</p>
                                                            <span className="mt-0.5 inline-flex rounded-full border border-white/10 bg-white/[0.06] px-1.5 py-px text-[9px] font-black uppercase tracking-wider text-white/50">
                                                                {row.type}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="border-y border-white/[0.06] bg-white/[0.03] px-3 py-2.5 text-right text-xs font-black text-white tabular-nums transition-colors">
                                                    {row.pct.toFixed(1)}%
                                                </td>
                                                <td className="border-y border-white/[0.06] bg-white/[0.03] px-3 py-2.5 text-right text-xs font-bold text-indigo-100/80 tabular-nums transition-colors">
                                                    {formatCurrency(row.value, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                                </td>
                                                <td className="rounded-r-xl border-y border-r border-white/[0.06] bg-white/[0.03] px-3 py-2.5 transition-colors">
                                                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]">
                                                        <motion.span
                                                            className="block h-full rounded-full"
                                                            style={{
                                                                background: `linear-gradient(90deg, rgba(255,255,255,0.18), transparent 30%), ${row.color}`,
                                                                width: `${relativeWidth}%`,
                                                                transformOrigin: 'left',
                                                            }}
                                                            initial={reduce ? false : { scaleX: 0 }}
                                                            animate={{ scaleX: 1 }}
                                                            transition={{ delay: reduce ? 0 : i * 0.04 + 0.26, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                                                        />
                                                    </div>
                                                </td>
                                            </motion.tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}