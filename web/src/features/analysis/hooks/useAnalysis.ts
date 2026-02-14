"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type {
  AnalysisState,
  Rule1Valuation as CamelValuation,
  DataQuality as UiDataQuality,
  Applicability as UiApplicability,
  FreshnessInfo,
} from "../types/analysis.types";

import { fetchRule1Outcome } from "@/features/analysis/services/analysis.service";

function toFreshnessInfoFromDataQuality(dq?: UiDataQuality): FreshnessInfo | undefined {
  const lastComputedAt = (dq?.freshnessDays as any)?.lastComputedAt;
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;

  const d = new Date(lastComputedAt);
  if (Number.isNaN(d.getTime())) return undefined;

  return {
    lastEvaluatedIso: lastComputedAt,
    lastEvaluatedDisplay: d.toLocaleString(),
  };
}

export function useAnalysis(
  symbol: string,
  opts: { analytics?: any } = {}
): AnalysisState & {
  reload: () => Promise<void>;
  recompute: () => Promise<void>;
} {
  const { analytics } = opts;
  const currentSymbol = (symbol ?? "").toUpperCase();

  const [state, setState] = useState<AnalysisState>({
    loading: false,
    loadingHistory: false,
    error: undefined,
    valuation: undefined,
    applicability: undefined,
    dataQuality: undefined,
    history: undefined,
    freshness: undefined,
  });

  const ranForSymbol = useRef<Record<string, boolean>>({});

  const doCompute = useCallback(async () => {
    if (!currentSymbol) {
      setState((s) => ({ ...s, loading: false, error: "No symbol provided" }));
      return;
    }

    setState((s) => ({ ...s, loading: true, error: undefined }));

    const outcome = await fetchRule1Outcome(currentSymbol);

    if (outcome.status === "ok") {
      const payload = outcome.payload;

      const valuation = payload.valuation as unknown as CamelValuation;
      const applicability = payload.applicability as unknown as UiApplicability;
      const dataQuality = payload.dataQuality as unknown as UiDataQuality;

      setState({
        loading: false,
        loadingHistory: false,
        error: undefined,
        valuation,
        applicability,
        dataQuality,
        history: undefined,
        freshness: toFreshnessInfoFromDataQuality(dataQuality),
      });

      return;
    }

    const msg = outcome.message || "Failed to compute valuation.";
    setState((s) => ({ ...s, loading: false, error: msg }));
    analytics?.onError?.(currentSymbol, msg);
  }, [currentSymbol, analytics]);

  useEffect(() => {
    if (!currentSymbol) return;
    if (!ranForSymbol.current[currentSymbol]) {
      ranForSymbol.current[currentSymbol] = true;
      void doCompute();
    }
  }, [currentSymbol, doCompute]);

  const recompute = useCallback(async () => {
    if (!currentSymbol) return;
    await doCompute();
  }, [currentSymbol, doCompute]);

  const reload = recompute;

  return { ...state, reload, recompute };
}