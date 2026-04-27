import React, { useMemo } from "react";
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from "recharts";
import type { SuperInvestorHistoryData } from "../types/analysis.types";

// ─────────────────────────────────────────────────────────────────────────────
// Color palette (cycling through distinct colors for multiple investors)
// ─────────────────────────────────────────────────────────────────────────────
const INVESTOR_COLORS = [
    { stroke: "#6366f1", fill: "rgba(99, 102, 241, 0.2)" }, // indigo
    { stroke: "#10b981", fill: "rgba(16, 185, 129, 0.2)" }, // emerald
    { stroke: "#f59e0b", fill: "rgba(245, 158, 11, 0.2)" }, // amber
    { stroke: "#ec4899", fill: "rgba(236, 72, 153, 0.2)" }, // pink
    { stroke: "#06b6d4", fill: "rgba(6, 182, 212, 0.2)" }, // cyan
    { stroke: "#8b5cf6", fill: "rgba(139, 92, 246, 0.2)" }, // violet
    { stroke: "#f97316", fill: "rgba(249, 115, 22, 0.2)" }, // orange
    { stroke: "#14b8a6", fill: "rgba(20, 184, 166, 0.2)" }, // teal
];

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────
interface ChartDataPoint {
    quarter: string;
    quarterLabel: string;
    [investorTag: string]: number | string; // dynamic keys for each investor
}

interface TooltipPayload {
    name: string;
    value: number;
    dataKey: string;
    color: string;
    payload: ChartDataPoint;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────
export function SuperInvestorPositionChart({
    data,
}: {
    data: SuperInvestorHistoryData;
}) {
    const chartData = useMemo(() => transformData(data), [data]);

    if (!chartData || chartData.series.length === 0) {
        return (
            <div className="glass-panel p-8 text-center">
                <p className="text-sm text-slate-400">No historical data available</p>
            </div>
        );
    }

    return (
        <div className="glass-panel">
            {/* Header */}
            <div className="border-b border-white/5 p-4">
                <h3 className="text-sm font-medium text-slate-200">Position History</h3>
                <p className="mt-1 text-xs text-slate-400">
                    Quarterly holdings since {formatQuarterLabel(data.earliest_date || "")}
                </p>
            </div>

            {/* Chart */}
            <div className="p-6">
                <ResponsiveContainer width="100%" height={400}>
                    <AreaChart
                        data={chartData.points}
                        margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                    >
                        {/* Grid with glass theme */}
                        <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255, 255, 255, 0.05)"
                            vertical={false}
                        />

                        {/* X-Axis: Quarters */}
                        <XAxis
                            dataKey="quarterLabel"
                            tick={{ fill: "#94a3b8", fontSize: 11 }}
                            stroke="rgba(255, 255, 255, 0.1)"
                            tickLine={false}
                        />

                        {/* Y-Axis: Shares (in millions) */}
                        <YAxis
                            tick={{ fill: "#94a3b8", fontSize: 11 }}
                            stroke="rgba(255, 255, 255, 0.1)"
                            tickLine={false}
                            tickFormatter={(value) => formatSharesAxis(value)}
                            width={60}
                        />

                        {/* Custom Tooltip */}
                        <Tooltip content={<CustomTooltip />} />

                        {/* Legend */}
                        <Legend
                            wrapperStyle={{ paddingTop: "20px" }}
                            iconType="circle"
                            formatter={(value) => (
                                <span className="text-xs text-slate-300">{value}</span>
                            )}
                        />

                        {/* Area series (one per investor) */}
                        {chartData.series.map((series, idx) => {
                            const colorIdx = idx % INVESTOR_COLORS.length;
                            const color = INVESTOR_COLORS[colorIdx];

                            return (
                                <Area
                                    key={series.dataKey}
                                    type="monotone"
                                    dataKey={series.dataKey}
                                    name={series.label}
                                    stroke={color.stroke}
                                    fill={color.fill}
                                    strokeWidth={2}
                                    fillOpacity={0.6}
                                    activeDot={{ r: 6, strokeWidth: 2 }}
                                />
                            );
                        })}
                    </AreaChart>
                </ResponsiveContainer>
            </div>

            {/* Footer Stats */}
            <div className="border-t border-white/5 p-4">
                <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                        <p className="text-xs text-slate-400">Investors Tracked</p>
                        <p className="mt-1 text-lg font-semibold text-slate-200">
                            {chartData.series.length}
                        </p>
                    </div>
                    <div>
                        <p className="text-xs text-slate-400">Quarters</p>
                        <p className="mt-1 text-lg font-semibold text-slate-200">
                            {chartData.points.length}
                        </p>
                    </div>
                    <div>
                        <p className="text-xs text-slate-400">Timespan</p>
                        <p className="mt-1 text-lg font-semibold text-slate-200">
                            {formatQuarterLabel(data.earliest_date || "")} -{" "}
                            {formatQuarterLabel(data.latest_date || "")}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom Tooltip
// ─────────────────────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload }: any) {
    if (!active || !payload || payload.length === 0) {
        return null;
    }

    const data = payload[0].payload as ChartDataPoint;

    return (
        <div className="rounded-xl border border-white/10 bg-slate-900/95 p-3 shadow-xl backdrop-blur-sm">
            <p className="mb-2 text-xs font-medium text-indigo-400">
                {data.quarterLabel}
            </p>
            <div className="space-y-1.5">
                {payload.map((entry: TooltipPayload, idx: number) => (
                    <div key={idx} className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-2">
                            <div
                                className="h-2 w-2 rounded-full"
                                style={{ backgroundColor: entry.color }}
                            />
                            <span className="text-xs text-slate-300">{entry.name}</span>
                        </div>
                        <span className="text-xs font-medium text-slate-100">
                            {formatShares(entry.value)} shares
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Data Transformation
// ─────────────────────────────────────────────────────────────────────────────
function transformData(data: SuperInvestorHistoryData): {
    points: ChartDataPoint[];
    series: Array<{ dataKey: string; label: string }>;
} {
    if (!data.investors || data.investors.length === 0 || !data.quarters) {
        return { points: [], series: [] };
    }

    // Build chart data points (one per quarter)
    const points: ChartDataPoint[] = data.quarters.map((quarter) => {
        const point: ChartDataPoint = {
            quarter,
            quarterLabel: formatQuarterLabel(quarter),
        };

        // Add each investor's shares for this quarter
        data.investors.forEach((investor) => {
            const holding = investor.holdings.find(
                (h) => h.quarter_date === quarter
            );
            point[investor.tag] = holding ? holding.shares_held : 0;
        });

        return point;
    });

    // Build series metadata (one per investor)
    const series = data.investors.map((investor) => ({
        dataKey: investor.tag,
        label: investor.investor_name,
    }));

    return { points, series };
}

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────
function formatQuarterLabel(quarterDate: string): string {
    if (!quarterDate) return "";
    // quarterDate format: "2021-03-31"
    const month = parseInt(quarterDate.slice(5, 7));
    const year = quarterDate.slice(2, 4); // "21" from "2021"
    const q = month <= 3 ? 1 : month <= 6 ? 2 : month <= 9 ? 3 : 4;
    return `Q${q}'${year}`;
}

function formatSharesAxis(value: number): string {
    if (value >= 1_000_000_000) {
        return `${(value / 1_000_000_000).toFixed(1)}B`;
    }
    if (value >= 1_000_000) {
        return `${(value / 1_000_000).toFixed(0)}M`;
    }
    if (value >= 1_000) {
        return `${(value / 1_000).toFixed(0)}K`;
    }
    return value.toString();
}

function formatShares(value: number): string {
    if (value >= 1_000_000_000) {
        return `${(value / 1_000_000_000).toFixed(2)}B`;
    }
    if (value >= 1_000_000) {
        return `${(value / 1_000_000).toFixed(1)}M`;
    }
    if (value >= 1_000) {
        return `${(value / 1_000).toFixed(1)}K`;
    }
    return value.toLocaleString();
}