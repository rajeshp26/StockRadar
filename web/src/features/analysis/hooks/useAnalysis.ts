// src/features/analysis/hooks/useAnalysis.ts
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AnalysisState,
  Rule1Response,
  Rule1History,
  FreshnessInfo,
} from "../types/analysis.types";
import {
  fetchRule1,
  fetchRule1History,
  recomputeRule1,
  type RequestOpts,
  type Rule1Overrides,
} from "../services/analysis.service";

/** Optional analytics hook-in for your events pipeline */
export interface AnalysisAnalytics {
  onPageViewed?: (symbol: string) => void;
  onTabSelected?: (tab: string, symbol: string) => void;
  onRecomputed?: (symbol: string, durationMs: number, ok: boolean) => void;
  onHistoryViewed?: (symbol: string) => void;
  onError?: (symbol: string, message: string) => void;
}

export interface UseAnalysisOptions {
  timeoutMs?: number;
  analytics?: AnalysisAnalytics;
  initialOverrides?: Rule1Overrides;
}

/* ---------------------------------------------------------- */
/* Freshness helpers                                           */
/* ---------------------------------------------------------- */

function toFreshnessInfo(lastComputedAt?: unknown): FreshnessInfo | undefined {
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;
  const d = new Date(lastComputedAt);
  if (Number.isNaN(d.getTime())) return undefined;
  return {
    lastEvaluatedIso: lastComputedAt,
    lastEvaluatedDisplay: d.toLocaleString(),
  };
}

function inferFreshness(resp?: Rule1Response): FreshnessInfo | undefined {
  const last = resp?.dataQuality?.freshnessDays?.["lastComputedAt"];
  return toFreshnessInfo(last);
}

/* ---------------------------------------------------------- */
/* State mapper                                                */
/* ---------------------------------------------------------- */

function toState(
  response?: Rule1Response,
  history?: Rule1History
): Pick<
  AnalysisState,
  "valuation" | "applicability" | "dataQuality" | "history" | "freshness"
> {
  return {
    valuation: response?.valuation,
    applicability: response?.applicability,
    dataQuality: response?.dataQuality,
    history,
    freshness: inferFreshness(response),
  };
}

/* ---------------------------------------------------------- */
/* Hook                                                        */
/* ---------------------------------------------------------- */

export function useAnalysis(
  symbol: string,
  opts: UseAnalysisOptions = {}
): AnalysisState & {
  reload: () => Promise<void>;
  recompute: (overrides?: Rule1Overrides) => Promise<void>;
} {
  const { timeoutMs, analytics, initialOverrides } = opts;

  const [state, setState] = useState<AnalysisState>({
    loading: true,
    loadingHistory: true,
    error: undefined,
    valuation: undefined,
    applicability: undefined,
    dataQuality: undefined,
    history: undefined,
    freshness: undefined,
  });

  const ctrlRef = useRef<AbortController | null>(null);
  const currentSymbol = symbol?.toUpperCase() ?? "";

  /* ------------------------------------------------------ */
  /* LOAD (valuation + history in parallel)                 */
  /* ------------------------------------------------------ */
  const load = useCallback(
    async (overrides?: Rule1Overrides) => {
      if (!currentSymbol) {
        setState((s) => ({
          ...s,
          loading: false,
          loadingHistory: false,
          error: "No symbol provided",
        }));
        analytics?.onError?.(currentSymbol, "No symbol provided");
        return;
      }

      ctrlRef.current?.abort();
      const ctrl = new AbortController();
      ctrlRef.current = ctrl;

      setState((s) => ({
        ...s,
        loading: true,
        loadingHistory: true,
        error: undefined,
      }));

      try {
        const req: RequestOpts = {
          timeoutMs,
          signal: ctrl.signal,
          overrides: overrides ?? initialOverrides,
        };

        // MINIMAL CHANGE FOR FILE 9 — catch history safely
        const [response, history] = await Promise.all([
          fetchRule1(currentSymbol, req),
          fetchRule1History(currentSymbol, req).catch(() => ({
            symbol: currentSymbol,
            items: [],
          })),
        ]);

        setState({
          loading: false,
          loadingHistory: false,
          error: undefined,
          ...toState(response, history),
        });
      } catch (err: unknown) {
        if ((err as any)?.name === "AbortError") return;

        const msg = (err as Error)?.message ?? "Failed to load analysis";
        setState((s) => ({
          ...s,
          loading: false,
          loadingHistory: false,
          error: msg,
        }));
        analytics?.onError?.(currentSymbol, msg);
      }
    },
    [currentSymbol, timeoutMs, analytics, initialOverrides]
  );

  /* ------------------------------------------------------ */
  /* INITIAL + SYMBOL CHANGE                                */
  /* ------------------------------------------------------ */
  useEffect(() => {
    analytics?.onPageViewed?.(currentSymbol);
    load();
    return () => ctrlRef.current?.abort();
  }, [currentSymbol]); // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(async () => {
    await load();
  }, [load]);

  /* ------------------------------------------------------ */
  /* RECOMPUTE                                              */
  /* ------------------------------------------------------ */
  const recompute = useCallback(
    async (overrides?: Rule1Overrides) => {
      if (!currentSymbol) return;

      const t0 = performance.now();
      setState((s) => ({ ...s, loading: true, error: undefined }));

      try {
        const response = await recomputeRule1(currentSymbol, {
          timeoutMs,
          overrides,
        });

        // MINIMAL CHANGE FOR FILE 9 — catch history safely
        const history = await fetchRule1History(currentSymbol, {
          timeoutMs,
        }).catch(() => ({
          symbol: currentSymbol,
          items: [],
        }));

        setState({
          loading: false,
          loadingHistory: false,
          error: undefined,
          ...toState(response, history),
        });

        analytics?.onRecomputed?.(currentSymbol, performance.now() - t0, true);
      } catch (err: unknown) {
        const msg = (err as Error)?.message ?? "Recompute failed";
        setState((s) => ({ ...s, loading: false, error: msg }));
        analytics?.onRecomputed?.(currentSymbol, performance.now() - t0, false);
        analytics?.onError?.(currentSymbol, msg);
      }
    },
    [currentSymbol, timeoutMs, analytics]
  );

  /* ------------------------------------------------------ */
  /* FRESHNESS (stable memo)                                */
  /* ------------------------------------------------------ */
  const freshness = useMemo<FreshnessInfo | undefined>(() => {
    return (
      inferFreshness(
        state.valuation && state.applicability && state.dataQuality
          ? ({
              valuation: state.valuation,
              applicability: state.applicability,
              dataQuality: state.dataQuality,
            } as Rule1Response)
          : undefined
      ) ?? state.freshness
    );
  }, [state.valuation, state.applicability, state.dataQuality, state.freshness]);

  return {
    ...state,
    freshness,
    reload,
    recompute,
  };
}