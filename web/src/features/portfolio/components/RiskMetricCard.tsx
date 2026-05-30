'use client';

import { cn } from '@/lib/utils';

interface RiskMetricCardProps {
    label: string;
    value: string;
    subtitle?: string;
    trend?: 'up' | 'down' | 'neutral';
    trendLabel?: string;
    className?: string;
}

const TREND_COLORS: Record<string, string> = {
    up: 'text-green-400',
    down: 'text-red-400',
    neutral: 'text-yellow-400',
};

export function RiskMetricCard({ label, value, subtitle, trend, trendLabel, className }: RiskMetricCardProps) {
    return (
        <div className={cn('glass-panel rounded-lg p-4', className)}>
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider">
                {label}
            </p>
            <p className="text-xl font-bold mt-1 text-white">
                {value}
            </p>
            {subtitle && (
                <p className="text-xs text-white/30 mt-0.5">{subtitle}</p>
            )}
            {trend && (
                <p className={cn('text-xs font-medium mt-1.5', TREND_COLORS[trend])}>
                    {trend === 'up' && '↑ '}
                    {trend === 'down' && '↓ '}
                    {trendLabel || trend}
                </p>
            )}
        </div>
    );
}
