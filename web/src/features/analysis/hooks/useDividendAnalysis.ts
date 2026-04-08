// web/src/features/analysis/hooks/useDividendAnalysis.ts
"use client";
import { useQuery } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import type { DividendAnalysis } from "../types/analysis.types";

const DEFAULT_TIMEOUT = 15_000;

async function fetchDividendAnalysis(symbol: string): Promise<DividendAnalysis | null> {
    const url = `/api/proxy/analysis/${encodeURIComponent(symbol)}/dividend`;
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT);
    try {
        const res = await fetch(url, {
            method: "GET",
            credentials: "include",
            cache: "no-store",
            signal: controller.signal,
            headers: { Accept: "application/json" },
        });
        if (!res.ok) return null;
        return (await res.json()) as DividendAnalysis;
    } catch {
        return null;
    } finally {
        clearTimeout(id);
    }
}

export function useDividendAnalysis(symbol: string) {
    const upper = symbol.toUpperCase().trim();
    const { data, isPending, error } = useQuery<DividendAnalysis | null, Error>({
        queryKey: QK.dividend(upper),
        queryFn: () => fetchDividendAnalysis(upper),
        enabled: !!upper,
        staleTime: STALE.VALUATION,
        gcTime: GC.VALUATION,
        retry: 1,
    });

    return {
        data,
        loading: isPending,
        error: error?.message ?? null,
        paysDividend: data?.pays_dividend ?? null,
    };
}