// web/src/features/analysis/hooks/useRule1History.ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRule1History } from "@/features/analysis/services/analysis.service";
import type { Rule1History } from "../types/analysis.types";

export function useRule1History(symbol: string): {
  loading: boolean;
  error?: string;
  history?: Rule1History;
  reload: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<Rule1History | undefined>(undefined);

  const ranForSymbol = useRef<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!currentSymbol) return;

    setLoading(true);
    setError(undefined);

    try {
      const h = await fetchRule1History(currentSymbol);
      setHistory(h);
    } catch (e: any) {
      // History is non-blocking; keep it quiet but visible
      setError(e?.message || "Failed to load history.");
      setHistory({ symbol: currentSymbol, items: [] });
    } finally {
      setLoading(false);
    }
  }, [currentSymbol]);

  useEffect(() => {
    if (!currentSymbol) return;

    if (!ranForSymbol.current[currentSymbol]) {
      ranForSymbol.current[currentSymbol] = true;
      void load();
    }
  }, [currentSymbol, load]);

  return { loading, error, history, reload: load };
}