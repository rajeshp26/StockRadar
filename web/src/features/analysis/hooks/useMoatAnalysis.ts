// web/src/features/analysis/hooks/useMoatAnalysis.ts
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
    fetchMoatCached,
    fetchMoatValuation,
} from "../services/analysis.service";
import type { MoatResponse } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export type MoatQueryData =
    | { notComputed: true }
    | (MoatResponse & { notComputed: false });

export async function moatQueryFn(
    symbol: string
): Promise<MoatQueryData> {
    const outcome = await fetchMoatCached(symbol);
    if (outcome.status === "not_computed") return { notComputed: true };
    if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
    throw new Error(outcome.message || "Failed to load Moat analysis.");
}

export function useMoatAnalysis(symbol: string) {
    const upper = (symbol ?? "").toUpperCase();
    const queryClient = useQueryClient();

    const { data, isPending, error } = useQuery<MoatQueryData, Error>({
        queryKey: QK.moat(upper),
        queryFn: () => moatQueryFn(upper),
        enabled: !!upper,
        staleTime: STALE.VALUATION,
        gcTime: GC.VALUATION,
        retry: 1,
    });

    const recompute = useCallback(async (): Promise<void> => {
        if (!upper) return;
        const fresh = await fetchMoatValuation(upper, { force: true });
        queryClient.setQueryData<MoatQueryData>(QK.moat(upper), {
            ...fresh,
            notComputed: false,
        });
    }, [upper, queryClient]);

    const notComputed = data?.notComputed ?? false;
    const responseData = notComputed
        ? null
        : (data as MoatResponse & { notComputed: false }) ?? null;

    return {
        data: responseData,
        loading: isPending,
        error: error?.message ?? null,
        notComputed,
        recompute,
    };
}