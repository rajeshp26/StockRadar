// web/src/features/analysis/hooks/useDdmHistory.ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchDdmHistory } from "@/features/analysis/services/analysis.service";
import type { DdmHistory, DdmVariant } from "../types/analysis.types";

export function useDdmHistory(
  symbol: string,
  variant: DdmVariant
): {
  loading: boolean;
  error?: string;
  history?: DdmHistory;
  reload: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const key = `${currentSymbol}::${variant}`;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<DdmHistory | undefined>(undefined);

  const ranForKey = useRef<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!currentSymbol) return;

    setLoading(true);
    setError(undefined);

    try {
      const h = await fetchDdmHistory(currentSymbol, variant);
      setHistory(h);
    } catch (e: any) {
      // History is non-blocking; keep it quiet but visible
      setError(e?.message || "Failed to load DDM history.");
      setHistory({ symbol: currentSymbol, items: [] });
    } finally {
      setLoading(false);
    }
  }, [currentSymbol, variant]);

  useEffect(() => {
    if (!currentSymbol) return;

    if (!ranForKey.current[key]) {
      ranForKey.current[key] = true;
      void load();
    }
  }, [currentSymbol, key, load]);

  return { loading, error, history, reload: load };
}