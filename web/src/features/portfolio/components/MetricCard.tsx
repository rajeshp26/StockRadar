'use client';

import { cn } from '@/lib/utils';

interface MetricCardProps {
    label: string;
    value: string;
    subtitle?: string;
    coveragePct?: number;
    trend?: 'up' | 'down' | 'neutral';
    trendLabel?: string;
    className?: string;
}

export function MetricCard({ label, value, subtitle, coveragePct, trend, trendLabel, className }: MetricCardProps) {
    return (
        <div className={cn('glass-panel rounded-lg p-4 flex flex-col', className)}>
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider">{label}</p>
            <p className="text-xl font-bold mt-1 text-white">{value}</p>
            {subtitle && (
                <p className="text-xs text-white/30 mt-0.5">{subtitle}</p>
            )}
            <div className="flex items-center gap-2 mt-1.5">
                {trend && (
                    <span className={cn(
                        'text-xs font-medium',
                        trend === 'up' && 'text-green-400',
                        trend === 'down' && 'text-red-400',
                        trend === 'neutral' && 'text-yellow-400',
                    )}>
                        {trend === 'up' && '↑ '}{trend === 'down' && '↓ '}{trendLabel || trend}
                    </span>
                )}
                {coveragePct !== undefined && (
                    <span className="text-[10px] text-white/20 font-mono">{coveragePct}% coverage</span>
                )}
            </div>
        </div>
    );
}
