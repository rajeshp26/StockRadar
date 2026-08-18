// web/src/features/analysis/hooks/useValuationOverview.ts
"use client";
import { useQuery } from "@tanstack/react-query";
import type { IntrinsicMethod } from "../components/method-selector";
import {
  fetchValuationSummary,
  type RecommendationSummary,
  type ValuationMethodKey,
} from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type MethodStatus =
  | "loading"
  | "computed"
  | "stale"
  | "not_computed"
  | "not_applicable"
  | "error";

export type MethodSummary = {
  id:             IntrinsicMethod;
  label:          string;
  description:    string;
  status:         MethodStatus;
  intrinsicValue: number | null;
  currentPrice:   number | null;
  upsideDownside: number | null;
  score:          number | null;
  category:       string | null;
  lastComputedAt: string | null;
  currency:       string;
  reasonCode:     string | null;
  freshnessDays:  number | null;
  errorMessage?:  string;
};

export type OverviewRecommendation = RecommendationSummary & {
  bestMethod:      string | null;
  bestMethodLabel: string | null;
  consensus:       string;
  reasoning:       string;
  confidenceNote:  string;
};

export type ValuationOverviewData = {
  methods:        MethodSummary[];
  recommendation: OverviewRecommendation | null;
  loadingRec:     boolean;
  anyComputed:    boolean;
  allLoading:     boolean;
  generatedAt:    string | null;
  currency:       string;
  sector:         string | null;
};

// ─────────────────────────────────────────────────────────────────────────────
// Static method metadata
// ─────────────────────────────────────────────────────────────────────────────

const METHOD_META: Record<IntrinsicMethod, { label: string; description: string }> = {
  overview:       { label: "Overview",                   description: "" },
  rule1:          { label: "Rule #1 (Phil Town)",        description: "Earnings growth & multiple based intrinsic value" },
  dcf:            { label: "Discounted Cash Flow",       description: "Cash-flow based intrinsic value" },
  ddm:            { label: "Dividend Discount Model",    description: "Dividend yield & growth based valuation" },
  ownerEarnings:  { label: "Owner Earnings",             description: "Buffett owner earnings valuation" },
  residualIncome: { label: "Residual Income",            description: "Economic profit based valuation" },
};

const API_TO_METHOD: Record<ValuationMethodKey, IntrinsicMethod> = {
  rule1:           "rule1",
  dcf:             "dcf",
  ddm_gordon:      "ddm",
  owner_earnings:  "ownerEarnings",
  residual_income: "residualIncome",
};

const METHOD_KEYS = Object.keys(API_TO_METHOD) as ValuationMethodKey[];

/** Value is considered stale after this many days since computedAt. */
const STALE_AFTER_DAYS = 7;

// ─────────────────────────────────────────────────────────────────────────────
// Mappers
// ─────────────────────────────────────────────────────────────────────────────

function mapStatus(status: string | undefined, isPending: boolean, isError: boolean): MethodStatus {
  if (isPending) return "loading";
  if (isError) return "error";
  switch (status) {
    case "available": return "computed";
    case "stale":     return "stale";
    case "not_computed": return "not_computed";
    case "not_applicable": return "not_applicable";
    case "failed_without_previous_result": return "error";
    default: return "not_computed";
  }
}

function deriveConsensus(methods: MethodSummary[]): string {
  const computed = methods.filter((m) => m.status === "computed" || m.status === "stale");
  if (computed.length === 0) return "No Data";
  const positive = computed.filter((m) => (m.upsideDownside ?? 0) > 0.02);
  const negative = computed.filter((m) => (m.upsideDownside ?? 0) < -0.02);
  if (negative.length === 0) return "Undervalued";
  if (positive.length === 0) return "Overvalued";
  return "Mixed";
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Single useQuery on the canonical /analysis/{symbol}/valuation-summary
// endpoint (§6.1). One request on the page critical path replaces the five
// per-method GETs + /overview. Statuses are mapped 1:1 from the read-model
// contract; a broken section never fails the whole page.
// ─────────────────────────────────────────────────────────────────────────────

export function useValuationOverview(
  symbol: string,
): ValuationOverviewData {
  const upper = (symbol ?? "").toUpperCase();

  const q = useQuery({
    queryKey:  QK.valuationSummary(upper),
    queryFn:   () => fetchValuationSummary(upper),
    enabled:   !!upper,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const data  = q.data;
  const raw   = data?.methods;
  const isPending = q.isPending;
  const isError   = q.isError;

  const methods: MethodSummary[] = METHOD_KEYS.map((key) => {
    const id  = API_TO_METHOD[key];
    const sec = raw?.[key];
    const status = mapStatus(sec?.status, isPending, isError);
    const isComputed = status === "computed" || status === "stale";
    const lastComputedAt = sec?.computedAt ?? null;
    const freshnessDays  = sec?.freshnessDays ?? null;
    return {
      id,
      ...METHOD_META[id],
      status: status === "computed" && freshnessDays != null && freshnessDays > STALE_AFTER_DAYS
        ? "stale" as MethodStatus
        : status,
      intrinsicValue: sec?.intrinsicValue ?? null,
      currentPrice:   sec?.referencePrice ?? null,
      upsideDownside: sec?.upsideDownside ?? null,
      score:          sec?.score ?? null,
      category:       sec?.category ?? null,
      lastComputedAt,
      currency:       sec?.currency ?? "USD",
      reasonCode:     sec?.reasonCode ?? null,
      freshnessDays,
      errorMessage:   isError
        ? q.error?.message ?? "Failed to load valuation summary"
        : (status === "error" ? (sec?.reasonCode ?? "Computation failed") : undefined),
    } satisfies MethodSummary;
  });

  const anyComputed = methods.some((m) => m.status === "computed" || m.status === "stale");
  const allLoading  = methods.every((m) => m.status === "loading");

  const recRaw: RecommendationSummary | null = data?.recommendation ?? null;

  let recommendation: OverviewRecommendation | null = null;
  if (recRaw) {
    const best = methods
      .filter((m) => m.status === "computed" || m.status === "stale")
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))[0] ?? null;
    const consensus = deriveConsensus(methods);
    const computedCount = methods.filter((m) => m.status === "computed" || m.status === "stale").length;
    const reasoning = recRaw.text ?? (
      computedCount === 0
        ? "No valuation methods have been computed yet."
        : `${consensus} — ${computedCount} of ${methods.length} methods have published values.`
    );
    recommendation = {
      ...recRaw,
      bestMethod:      best?.id ?? null,
      bestMethodLabel: best?.label ?? null,
      consensus,
      reasoning,
      confidenceNote:  recRaw.status === "disabled"
        ? "AI summary disabled — showing deterministic valuation summary."
        : recRaw.status === "pending"
          ? "AI summary pending — showing deterministic valuation summary."
          : "",
    };
  }

  return {
    methods,
    recommendation,
    loadingRec: isPending && anyComputed,
    anyComputed,
    allLoading,
    generatedAt: data?.generatedAt ?? null,
    currency:    data?.currency ?? "USD",
    sector:      data?.sector ?? null,
  };
}
