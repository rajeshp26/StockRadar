'use client';

import { usePriceHistory } from '../hooks/usePortfolio';

interface PriceSparklineProps {
    symbol: string;
    days?: number;
    width?: number;
    height?: number;
    className?: string;
}

function SparklineSvg({
    data,
    width = 80,
    height = 28,
}: {
    data: { close: number | null }[];
    width?: number;
    height?: number;
}) {
    const values = data.map((d) => d.close).filter((v): v is number => v !== null);
    if (values.length < 2) return null;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    const points = values.map((v, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = height - ((v - min) / range) * (height - 2) - 1;
        return `${x},${y}`;
    });

    const isUp = values[values.length - 1] >= values[0];

    return (
        <svg
            width={width}
            height={height}
            className="overflow-visible"
            data-testid="price-sparkline"
        >
            <polyline
                fill="none"
                stroke={isUp ? '#4ade80' : '#f87171'}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={points.join(' ')}
            />
        </svg>
    );
}

export function PriceSparkline({
    symbol,
    days = 30,
    width = 80,
    height = 28,
    className,
}: PriceSparklineProps) {
    const { data, isLoading } = usePriceHistory(symbol, days);

    if (isLoading) {
        return (
            <div
                className={`animate-pulse rounded bg-white/10 ${className || ''}`}
                style={{ width, height }}
            />
        );
    }

    if (!data?.data || data.data.length < 2) return null;

    return (
        <div className={className}>
            <SparklineSvg data={data.data} width={width} height={height} />
        </div>
    );
}
