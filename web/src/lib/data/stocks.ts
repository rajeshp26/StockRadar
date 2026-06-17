import { cache } from "react";
import { cookies } from "next/headers";

const BACKEND_URL = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8001";

async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const jar = await cookies();
    const session = jar.get("__session")?.value;
    return session ? { Authorization: `Bearer ${session}` } : {};
  } catch {
    return {};
  }
}

export interface QuoteData {
  symbol: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  lastUpdated: string | null;
  currency?: string | null;
}

export const getStockQuote = cache(async (symbol: string): Promise<QuoteData | null> => {
  try {
    const auth = await getAuthHeaders();
    const res = await fetch(`${BACKEND_URL}/stocks/${symbol}/quote`, {
      headers: { ...auth, Accept: "application/json" },
      next: { revalidate: 10, tags: [`quote-${symbol}`] },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
});

interface ValuationMethodSummary {
  method: string;
  status: "computed" | "not_computed" | "error";
  intrinsicValue: number | null;
  currentPrice: number | null;
  upsideDownside: number | null;
  score: number | null;
  category: string | null;
  lastComputedAt: string | null;
}

export interface ValuationOverviewData {
  methods: ValuationMethodSummary[];
  symbol: string;
}

const METHOD_KEYS = [
  "rule1",
  "dcf",
  "ddm_gordon",
  "owner_earnings",
  "residual_income",
] as const;

export const getValuationOverview = cache(async (symbol: string): Promise<ValuationOverviewData | null> => {
  try {
    const auth = await getAuthHeaders();
    const res = await fetch(`${BACKEND_URL}/valuations/${symbol}/overview`, {
      headers: { ...auth, Accept: "application/json" },
      next: { revalidate: 300, tags: [`valuations-${symbol}`] },
    });
    if (!res.ok) return null;
    const raw: Record<string, unknown> = await res.json();

    const methodsRaw = raw.methods;
    const methods: ValuationMethodSummary[] = METHOD_KEYS
      .filter((k) => methodsRaw && typeof methodsRaw === "object" && k in (methodsRaw as Record<string, unknown>))
      .map((k) => {
        const entry = (methodsRaw as Record<string, unknown>)[k] as Record<string, unknown> | undefined;
        return {
          method: k,
          status: (entry?.status as ValuationMethodSummary["status"]) ?? "not_computed",
          intrinsicValue: (entry?.intrinsicValue as number | null | undefined) ?? null,
          currentPrice: (entry?.currentPrice as number | null | undefined) ?? null,
          upsideDownside: (entry?.upsideDownside as number | null | undefined) ?? null,
          score: (entry?.score as number | null | undefined) ?? null,
          category: (entry?.category as string | null | undefined) ?? null,
          lastComputedAt: (entry?.lastComputedAt as string | null | undefined) ?? null,
        };
      });

    return { symbol: (raw.symbol as string) ?? symbol, methods };
  } catch {
    return null;
  }
});

export const getIndividualValuation = cache(async (symbol: string, method: string): Promise<unknown | null> => {
  try {
    const auth = await getAuthHeaders();
    const res = await fetch(`${BACKEND_URL}/valuations/${symbol}/${method}`, {
      headers: { ...auth, Accept: "application/json" },
      next: { revalidate: 300, tags: [`valuations-${symbol}`] },
    });
    if (res.status === 404) return { notComputed: true };
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
});
