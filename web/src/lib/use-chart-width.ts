'use client';

import { useCallback, useEffect, useRef, useState, type RefCallback } from 'react';

/**
 * Measure a chart container's rendered width for width-derived tick density.
 *
 * Returns `{ ref, width }`; attach `ref` to the element that directly wraps the
 * Recharts `ResponsiveContainer`. `width` is `undefined` until the element is
 * mounted and measured, and stays `undefined` in environments without
 * ResizeObserver (SSR, jsdom) — chart-time-axis falls back to the default
 * target in that case, so axes are never degenerate before measurement.
 *
 * The reconnect-on-remount shape (disconnect/observe per ref callback) keeps
 * the measurement correct for conditionally-mounted chart panels.
 */
export function useChartWidth(): { ref: RefCallback<HTMLDivElement>; width: number | undefined } {
    const [width, setWidth] = useState<number | undefined>(undefined);
    const observerRef = useRef<ResizeObserver | null>(null);

    const ref = useCallback((el: HTMLDivElement | null) => {
        observerRef.current?.disconnect();
        observerRef.current = null;
        if (!el) {
            setWidth(undefined);
            return;
        }
        const measure = () => {
            const w = el.getBoundingClientRect().width;
            setWidth(w > 0 ? w : undefined);
        };
        measure();
        if (typeof ResizeObserver !== 'undefined') {
            observerRef.current = new ResizeObserver(() => measure());
            observerRef.current.observe(el);
        }
    }, []);

    useEffect(() => () => observerRef.current?.disconnect(), []);

    return { ref, width };
}