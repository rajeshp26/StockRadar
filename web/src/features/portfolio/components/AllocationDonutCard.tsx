'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { AllocationSegment } from '../types/portfolio.types';

const DONUT_COLORS = [
    '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#f97316', '#ec4899', '#14b8a6', '#84cc16',
    '#a855f7', '#0ea5e9',
];

interface AllocationDonutCardProps {
    segments: AllocationSegment[];
    selectedSegment?: string | null;
    onSegmentClick: (segment: string | null) => void;
    isLoading?: boolean;
    totalValue: number;
}

export function AllocationDonutCard({
    segments,
    selectedSegment,
    onSegmentClick,
    isLoading,
    totalValue,
}: AllocationDonutCardProps) {
    if (isLoading) {
        return (
            <div className="glass-panel rounded-lg p-6">
                <div className="flex flex-col md:flex-row items-center gap-8">
                    <Skeleton className="h-[220px] w-[220px] rounded-full flex-shrink-0" />
                    <div className="flex-1 w-full space-y-3">
                        {Array.from({ length: 4 }).map((_, i) => (
                            <Skeleton key={i} className="h-10 w-full" />
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    if (!segments.length) {
        return (
            <div className="glass-panel rounded-lg p-6 text-center">
                <p className="text-white/40 text-sm">No allocation data available</p>
            </div>
        );
    }

    const chartData = segments.map((s, i) => ({
        name: s.segment,
        value: s.value,
        weight: s.weight,
        count: s.count,
        gain_loss: s.gain_loss,
        color: DONUT_COLORS[i % DONUT_COLORS.length],
    }));

    const handleClick = (entryName: string) => {
        onSegmentClick(selectedSegment === entryName ? null : entryName);
    };

    return (
        <div className="glass-panel rounded-lg p-6">
            <div className="flex flex-col md:flex-row items-center gap-8">
                {/* Donut Chart */}
                <div className="flex-shrink-0" style={{ width: 220, height: 220 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={chartData}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={90}
                                paddingAngle={2}
                                dataKey="value"
                                cursor="pointer"
                            >
                                {chartData.map((entry) => (
                                    <Cell
                                        key={entry.name}
                                        fill={entry.color}
                                        opacity={selectedSegment && selectedSegment !== entry.name ? 0.3 : 1}
                                        stroke={selectedSegment === entry.name ? '#fff' : 'transparent'}
                                        strokeWidth={selectedSegment === entry.name ? 2 : 0}
                                        onClick={() => handleClick(entry.name)}
                                    />
                                ))}
                            </Pie>
                            <Tooltip
                                contentStyle={{
                                    background: 'rgba(0,0,0,0.85)',
                                    border: '1px solid rgba(255,255,255,0.1)',
                                    borderRadius: '8px',
                                    fontSize: '12px',
                                }}
                                formatter={(value: number) => [
                                    `$${(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                                    'Value',
                                ]}
                                labelFormatter={(label: string) => label}
                            />
                        </PieChart>
                    </ResponsiveContainer>
                </div>

                {/* Legend Table */}
                <div className="flex-1 w-full overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-xs text-white/30 uppercase tracking-wider border-b border-white/5">
                                <th className="text-left py-2 pr-4 font-medium">Sector</th>
                                <th className="text-right py-2 pr-4 font-medium">Weight</th>
                                <th className="text-right py-2 pr-4 font-medium">Value</th>
                                <th className="text-right py-2 font-medium">Holdings</th>
                            </tr>
                        </thead>
                        <tbody>
                            {chartData.map((entry) => (
                                <tr
                                    key={entry.name}
                                    onClick={() => handleClick(entry.name)}
                                    className={cn(
                                        'border-b border-white/5 cursor-pointer transition-colors hover:bg-white/[0.02]',
                                        selectedSegment === entry.name && 'bg-white/[0.04]'
                                    )}
                                >
                                    <td className="py-2.5 pr-4">
                                        <div className="flex items-center gap-2">
                                            <div
                                                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                                style={{ backgroundColor: entry.color }}
                                            />
                                            <span className={cn(
                                                'font-medium',
                                                selectedSegment === entry.name ? 'text-white' : 'text-white/70'
                                            )}>
                                                {entry.name}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="text-right py-2.5 pr-4 font-bold text-white">
                                        {entry.weight.toFixed(1)}%
                                    </td>
                                    <td className="text-right py-2.5 pr-4 text-white/60">
                                        ${entry.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                    </td>
                                    <td className="text-right py-2.5 text-white/40 text-xs">
                                        {entry.count}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
