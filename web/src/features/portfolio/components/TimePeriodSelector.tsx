'use client';

import { cn } from '@/lib/utils';
import { PERIOD_OPTIONS, type TimePeriod, type DividendResolutionLevel } from '../types/portfolio.types';

interface TimePeriodSelectorProps {
    value: TimePeriod;
    onChange: (period: TimePeriod) => void;
    minPeriod?: TimePeriod;
    resolution?: DividendResolutionLevel;
}

const PERIOD_ORDER: TimePeriod[] = ['1D', '1W', '1M', '3M', '1Y', 'YTD', 'ALL'];

function isPeriodAllowed(period: TimePeriod, minPeriod: TimePeriod): boolean {
    const pIdx = PERIOD_ORDER.indexOf(period);
    const mIdx = PERIOD_ORDER.indexOf(minPeriod);
    if (pIdx === -1 || mIdx === -1) return true;
    return pIdx >= mIdx;
}

function getMinPeriodForResolution(resolution?: DividendResolutionLevel): TimePeriod | undefined {
    if (!resolution) return undefined;
    if (resolution === 'monthly') return '1M';
    if (resolution === 'weekly') return '1W';
    if (resolution === 'quarterly') return '3M';
    if (resolution === 'daily') return undefined;
    if (resolution === 'unknown') return undefined;
    return undefined;
}

export function TimePeriodSelector({ value, onChange, minPeriod: minPeriodProp, resolution }: TimePeriodSelectorProps) {
    const minPeriod = minPeriodProp ?? getMinPeriodForResolution(resolution);

    return (
        <div className="glass-segmented">
            {PERIOD_OPTIONS.map((opt) => {
                const disabled = minPeriod ? !isPeriodAllowed(opt.value, minPeriod) : false;
                return (
                    <button
                        key={opt.value}
                        onClick={() => {
                            if (disabled) return;
                            onChange(opt.value);
                        }}
                        disabled={disabled}
                        title={disabled && minPeriod ? `Minimum period is ${minPeriod} due to data resolution` : undefined}
                        className={cn(
                            'glass-segmented-item',
                            value === opt.value && 'active',
                            disabled && 'opacity-40 cursor-not-allowed'
                        )}
                    >
                        {opt.label}
                    </button>
                );
            })}
        </div>
    );
}
