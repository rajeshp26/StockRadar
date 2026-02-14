"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  DdmState,
  DdmValuation,
  Applicability,
  DataQuality,
  FreshnessInfo,
  DdmVariant,
} from "../types/analysis.types";

import { fetchDdmOutcome } from "@/features/analysis/services/analysis.service";

function toFreshnessInfoFromDataQuality(dq?: DataQuality): FreshnessInfo | undefined {
  const lastComputedAt = (dq?.freshnessDays as any)?.lastComputedAt;
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;

  const d = new Date(lastComputedAt);
  if (Number.isNaN(d.getTime())) return undefined;

  return {
    lastEvaluatedIso: lastComputedAt,
    lastEvaluatedDisplay: d.toLocaleString(),
  };
}

type CachedDdm = {
  valuation: DdmValuation;
  applicability: Applicability;
  dataQuality: DataQuality;
  freshness?: FreshnessInfo;
};

export function useDdmAnalysis(
  symbol: string,
  variant: DdmVariant = "gordon"
): DdmState & {
  reload: () => Promise<void>;
  recompute: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const key = `${currentSymbol}::${variant}`;

  // ✅ Cache results per (symbol, variant) so switching is instant and correct
  const cacheRef = useRef<Record<string, CachedDdm>>({});
  const inflightRef = useRef<Record<string, Promise<void> | null>>({});

  const [state, setState] = useState<DdmState>({
    loading: false,
    loadingHistory: false,
    error: undefined,
    valuation: undefined,
    applicability: undefined,
    dataQuality: undefined,
    history: undefined,
    freshness: undefined,
  });

  const applyFromCache = useCallback(() => {
    const cached = cacheRef.current[key];
    if (!cached) return false;

    setState((s) => ({
      ...s,
      loading: false,
      error: undefined,
      valuation: cached.valuation,
      applicability: cached.applicability,
      dataQuality: cached.dataQuality,
      freshness: cached.freshness,
    }));
    return true;
  }, [key]);

  const doFetch = useCallback(
    async (force: boolean) => {
      if (!currentSymbol) {
        setState((s) => ({ ...s, loading: false, error: "No symbol provided" }));
        return;
      }

      // If not forcing and we have cache, use it immediately.
      if (!force && applyFromCache()) return;

      // Prevent duplicate simultaneous fetches for the same key
      const existing = inflightRef.current[key];
      if (existing) {
        await existing;
        // after inflight finishes, apply cache
        applyFromCache();
        return;
      }

      setState((s) => ({ ...s, loading: true, error: undefined }));

      const p = (async () => {
        const outcome = await fetchDdmOutcome(currentSymbol, variant);

        if (outcome.status === "ok") {
          const payload = outcome.payload;

          const valuation = payload.valuation as unknown as DdmValuation;
          const applicability = payload.applicability as unknown as Applicability;
          const dataQuality = payload.dataQuality as unknown as DataQuality;
          const freshness = toFreshnessInfoFromDataQuality(dataQuality);

          cacheRef.current[key] = { valuation, applicability, dataQuality, freshness };

          setState((s) => ({
            ...s,
            loading: false,
            error: undefined,
            valuation,
            applicability,
            dataQuality,
            freshness,
          }));
          return;
        }

        setState((s) => ({
          ...s,
          loading: false,
          error: outcome.message || "Failed to compute DDM.",
        }));
      })();

      inflightRef.current[key] = p;
      try {
        await p;
      } finally {
        inflightRef.current[key] = null;
      }
    },
    [applyFromCache, currentSymbol, key, variant]
  );

  // ✅ When symbol/variant changes, show cached instantly or fetch once
  useEffect(() => {
    if (!currentSymbol) return;
    void doFetch(false);
  }, [currentSymbol, key, doFetch]);

  const recompute = useCallback(async () => {
    // Force refresh for current variant
    await doFetch(true);
  }, [doFetch]);

  const reload = recompute;

  return useMemo(
    () => ({
      ...state,
      reload,
      recompute,
    }),
    [state, reload, recompute]
  );
}