'use client';

import { cn } from '@/lib/utils';
import { BarChart3, TrendingUp } from 'lucide-react';

export type ChartVariant = 'trend' | 'bar';

interface ChartVariantToggleProps {
    value: ChartVariant;
    onChange: (variant: ChartVariant) => void;
}

const VARIANTS: { value: ChartVariant; label: string; icon: typeof TrendingUp }[] = [
    { value: 'trend', label: 'Trend', icon: TrendingUp },
    { value: 'bar', label: 'Bar', icon: BarChart3 },
];

export function ChartVariantToggle({ value, onChange }: ChartVariantToggleProps) {
    return (
        <div className="glass-segmented" role="group" aria-label="Chart view">
            {VARIANTS.map(({ value: variant, label, icon: Icon }) => (
                <button
                    key={variant}
                    type="button"
                    onClick={() => onChange(variant)}
                    aria-pressed={value === variant}
                    className={cn(
                        'glass-segmented-item inline-flex items-center gap-1.5',
                        value === variant && 'active'
                    )}
                >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                </button>
            ))}
        </div>
    );
}