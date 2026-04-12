// web/src/features/analysis/hooks/useCANSlim.ts
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
    fetchCANSlimCached,
    fetchCANSlimValuation,
} from "../services/analysis.service";
import type { CANSlimResponse } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export type CANSlimQueryData =
    | { notComputed: true }
    | (CANSlimResponse & { notComputed: false });

export async function canslimQueryFn(
    symbol: string
): Promise<CANSlimQueryData> {
    const outcome = await fetchCANSlimCached(symbol);
    if (outcome.status === "not_computed") return { notComputed: true };
    if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
    throw new Error(outcome.message || "Failed to load CANSlim analysis.");
}

export function useCANSlim(symbol: string) {
    const upper = (symbol ?? "").toUpperCase();
    const queryClient = useQueryClient();

    const { data, isPending, error } = useQuery<CANSlimQueryData, Error>({
        queryKey: QK.canslim(upper),
        queryFn: () => canslimQueryFn(upper),
        enabled: !!upper,
        staleTime: STALE.VALUATION,
        gcTime: GC.VALUATION,
        retry: 1,
    });

    const recompute = useCallback(async (): Promise<void> => {
        if (!upper) return;
        const fresh = await fetchCANSlimValuation(upper, { force: true });
        queryClient.setQueryData<CANSlimQueryData>(QK.canslim(upper), {
            ...fresh,
            notComputed: false,
        });
    }, [upper, queryClient]);

    const notComputed = data?.notComputed ?? false;
    const responseData = notComputed
        ? null
        : (data as CANSlimResponse & { notComputed: false }) ?? null;

    return {
        data: responseData,
        loading: isPending,
        error: error?.message ?? null,
        notComputed,
        recompute,
    };
}