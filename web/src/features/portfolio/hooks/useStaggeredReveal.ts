'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

function stableKey<T>(items: T[]): string {
    const len = items.length;
    if (len === 0) return '';
    const first = (items[0] as Record<string, unknown>)?.id
        ?? (items[0] as Record<string, unknown>)?.holding_id
        ?? JSON.stringify(items[0]);
    const last = (items[len - 1] as Record<string, unknown>)?.id
        ?? (items[len - 1] as Record<string, unknown>)?.holding_id
        ?? JSON.stringify(items[len - 1]);
    return `${len}:${first}:${last}`;
}

export function useStaggeredReveal<T>(
    items: T[],
    delayMs: number = 40
): { visible: T[]; isComplete: boolean; reset: () => void } {
    const [count, setCount] = useState(0);
    const prevKeyRef = useRef('');

    const reset = useCallback(() => {
        setCount(0);
    }, []);

    useEffect(() => {
        const key = stableKey(items);
        if (key !== prevKeyRef.current) {
            setCount(0);
            prevKeyRef.current = key;
        }
    }, [items]);

    useEffect(() => {
        if (count >= items.length) return;

        const timer = setTimeout(() => {
            setCount((c) => Math.min(c + 1, items.length));
        }, delayMs);

        return () => clearTimeout(timer);
    }, [count, items.length, delayMs]);

    return {
        visible: items.slice(0, count),
        isComplete: count >= items.length,
        reset,
    };
}
