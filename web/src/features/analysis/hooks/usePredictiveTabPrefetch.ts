"use client";
import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { riskQueryFn } from "@/features/analysis/hooks/useRiskAssessment";
import { moatQueryFn } from "@/features/analysis/hooks/useMoatAnalysis";
import { magicFormulaQueryFn } from "@/features/analysis/hooks/useMagicFormula";
import { canslimQueryFn } from "@/features/analysis/hooks/useCANSlim";
import {
  fetchFundamentals,
  fetchMurphyTechnical,
  fetchSuperInvestors,
} from "@/features/analysis/services/analysis.service";

type TabId = string;

interface TabConfig {
  id: TabId;
  prefetchQueryKey: (symbol: string) => readonly unknown[];
  queryFn?: (symbol: string) => Promise<unknown>;
}

const TAB_PREFETCH_CONFIG: Record<string, TabConfig> = {
  health: {
    id: "health",
    prefetchQueryKey: (s) => QK.fundamentals(s),
    queryFn: (s) => fetchFundamentals(s),
  },
  moat: {
    id: "moat",
    prefetchQueryKey: (s) => QK.moat(s),
    queryFn: (s) => moatQueryFn(s),
  },
  dividend: {
    id: "dividend",
    prefetchQueryKey: (s) => QK.dividend(s),
    queryFn: (s) =>
      fetch(`/api/proxy/analysis/${encodeURIComponent(s)}/dividend`, {
        credentials: "include",
      }).then((r) => {
        if (!r.ok) throw new Error(`dividend fetch failed (${r.status})`);
        return r.json();
      }),
  },
  risk: {
    id: "risk",
    prefetchQueryKey: (s) => QK.riskAssessment(s),
    queryFn: (s) => riskQueryFn(s),
  },
  investors: {
    id: "investors",
    prefetchQueryKey: (s) => QK.superInvestors(s),
    queryFn: (s) => fetchSuperInvestors(s),
  },
  technical: {
    id: "technical",
    prefetchQueryKey: (s) => QK.murphyTechnical(s),
    queryFn: (s) => fetchMurphyTechnical(s),
  },
  others_magic_formula: {
    id: "others_magic_formula",
    prefetchQueryKey: (s) => QK.magicFormula(s),
    queryFn: (s) => magicFormulaQueryFn(s),
  },
  others_canslim: {
    id: "others_canslim",
    prefetchQueryKey: (s) => QK.canslim(s),
    queryFn: (s) => canslimQueryFn(s),
  },
};

const TAB_ORDER: TabId[] = [
  "intrinsic", "health", "moat", "dividend",
  "comparison", "technical", "risk", "investors", "others",
];

function getAdjacentTabs(currentTab: TabId): TabId[] {
  const idx = TAB_ORDER.indexOf(currentTab);
  if (idx === -1) return [];
  const neighbors: TabId[] = [];
  if (idx > 0) neighbors.push(TAB_ORDER[idx - 1]);
  if (idx < TAB_ORDER.length - 1) neighbors.push(TAB_ORDER[idx + 1]);
  return neighbors;
}

function prefetchTabData(
  tabId: TabId,
  symbol: string,
  queryClient: ReturnType<typeof useQueryClient>,
): void {
  if (tabId === "intrinsic") return;

  const config = TAB_PREFETCH_CONFIG[tabId];
  if (!config || !config.queryFn) return;

  const qk = config.prefetchQueryKey(symbol);
  queryClient.prefetchQuery({
    queryKey: qk,
    queryFn: () => config.queryFn!(symbol),
    staleTime: STALE.VALUATION,
    gcTime: GC.VALUATION,
  });
}

export function usePredictiveTabPrefetch(
  symbol: string,
  currentTab: TabId,
): void {
  const queryClient = useQueryClient();
  const prefetchDone = useRef<Set<string>>(new Set());

  useEffect(() => {
    const upper = symbol.toUpperCase();
    const neighbors = getAdjacentTabs(currentTab);

    const schedule = () => {
      neighbors.forEach((tabId) => {
        const key = `${upper}:${tabId}`;
        if (prefetchDone.current.has(key)) return;
        prefetchDone.current.add(key);

        if (process.env.NODE_ENV !== 'production') {
          console.log(`[PREFETCH] Tab data for "${tabId}" (${upper})`);
        }
        prefetchTabData(tabId, upper, queryClient);
      });
    };

    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      const id = requestIdleCallback(schedule, { timeout: 2000 });
      return () => cancelIdleCallback(id);
    } else {
      const timer = setTimeout(schedule, 1000);
      return () => clearTimeout(timer);
    }
  }, [symbol, currentTab, queryClient]);
}
