'use client';

import { cn } from '@/lib/utils';
import { PERIOD_OPTIONS, type TimePeriod } from '../types/portfolio.types';

interface TimePeriodSelectorProps {
    value: TimePeriod;
    onChange: (period: TimePeriod) => void;
}

export function TimePeriodSelector({ value, onChange }: TimePeriodSelectorProps) {
    return (
        <div className="glass-segmented">
            {PERIOD_OPTIONS.map((opt) => (
                <button
                    key={opt.value}
                    onClick={() => onChange(opt.value)}
                    className={cn(
                        'glass-segmented-item',
                        value === opt.value && 'active'
                    )}
                >
                    {opt.label}
                </button>
            ))}
        </div>
    );
}
