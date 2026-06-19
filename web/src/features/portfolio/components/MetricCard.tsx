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
        <div className={cn('glass-stat', className)}>
            <p className="glass-overline">{label}</p>
            <p className="text-2xl font-black tracking-tighter text-white leading-tight break-words">{value}</p>
            {subtitle && (
                <p className="text-[10px] text-white/30 leading-relaxed mt-1">{subtitle}</p>
            )}
            <div className="flex items-center gap-2 mt-2">
                {trend && (
                    <span className={cn(
                        'text-xs font-black',
                        trend === 'up' && 'text-emerald-400',
                        trend === 'down' && 'text-rose-400',
                        trend === 'neutral' && 'text-amber-400',
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
