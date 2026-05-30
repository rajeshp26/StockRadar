'use client';

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';

interface RiskMetricCardProps {
    label: string;
    value: string;
    subtitle?: string;
    trend?: 'up' | 'down' | 'neutral';
    trendLabel?: string;
    info?: string;
    className?: string;
}

const TREND_COLORS: Record<string, string> = {
    up: 'text-green-400',
    down: 'text-red-400',
    neutral: 'text-yellow-400',
};

export function RiskMetricCard({ label, value, subtitle, trend, trendLabel, info, className }: RiskMetricCardProps) {
    const [showInfo, setShowInfo] = useState(false);
    const infoRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!showInfo) return;
        const handleClick = (e: MouseEvent) => {
            if (infoRef.current && !infoRef.current.contains(e.target as Node)) {
                setShowInfo(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [showInfo]);

    return (
        <div className={cn('glass-panel rounded-lg p-4 relative', className)}>
            <div className="flex items-center gap-1.5">
                <p className="text-xs text-white/40 font-medium uppercase tracking-wider">
                    {label}
                </p>
                {info && (
                    <div ref={infoRef} className="relative">
                        <button
                            onClick={() => setShowInfo(!showInfo)}
                            className="w-3.5 h-3.5 rounded-full border border-white/20 text-white/40 hover:text-white/60 hover:border-white/40 text-[9px] flex items-center justify-center leading-none transition-colors"
                            aria-label={`Info about ${label}`}
                        >
                            i
                        </button>
                        {showInfo && (
                            <div className="absolute z-50 top-full mt-2 left-0 w-56 bg-gray-900 border border-white/10 rounded-lg p-3 shadow-xl">
                                <p className="text-xs text-white/70 leading-relaxed">{info}</p>
                            </div>
                        )}
                    </div>
                )}
            </div>
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
