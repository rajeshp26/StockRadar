// web/src/features/analysis/hooks/useValuationOverview.ts
"use client";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { IntrinsicMethod } from "../components/method-selector";
import type {
  DdmVariant,
  DcfResponse,
  DdmResponse,
  OwnerEarningsResponse,
  ResidualIncomeResponse,
} from "../types/analysis.types";
import type { Rule1Data } from "./useAnalysis";
import { rule1QueryFn }                 from "./useAnalysis";
import { dcfQueryFn }                   from "./useDcfAnalysis";
import {
  fetchDdmCached,
  fetchOwnerEarningsCached,
  fetchResidualIncomeCached,
} from "../services/analysis.service";
import { fetchOverviewSummary }         from "../services/analysis.service";
import { QK }                           from "@/lib/query-keys";
import { STALE, GC }                    from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type MethodStatus = "loading" | "computed" | "not_computed" | "error";

export type MethodSummary = {
  id:             IntrinsicMethod;
  label:          string;
  description:    string;
  status:         MethodStatus;
  intrinsicValue: number | null;    // primary per-share value
  currentPrice:   number | null;
  upsideDownside: number | null;    // fraction e.g. 0.25 = 25% upside
  score:          number | null;    // 0–100
  category:       string | null;    // "Good" | "Caution" | "Poor"
  lastComputedAt: string | null;    // ISO timestamp
  currency:       string;
  errorMessage?:  string;
};

export type OverviewRecommendation = {
  bestMethod:       string;
  bestMethodLabel:  string;
  reasoning:        string;
  consensus:        string;   // "Undervalued" | "Fairly Valued" | "Overvalued" | "Mixed"
  confidenceNote:   string;
};

export type ValuationOverviewData = {
  methods:        MethodSummary[];
  recommendation: OverviewRecommendation | null;
  loadingRec:     boolean;
  anyComputed:    boolean;
  allLoading:     boolean;
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

// ─────────────────────────────────────────────────────────────────────────────
// Extractor helpers
// Returns null for any field that is missing or not yet computed.
// ─────────────────────────────────────────────────────────────────────────────

function extractRule1(data: Rule1Data | undefined, id: IntrinsicMethod): Partial<MethodSummary> {
  if (!data || data.notComputed) return {};
  const v   = data.valuation as any;
  const app = data.applicability as any;
  const dq  = data.dataQuality   as any;
  const iv  = v?.stickerPrice ?? null;
  const cur = v?.currentPrice  ?? null;
  const upside = iv && cur && cur > 0 ? (iv - cur) / cur : null;
  return {
    intrinsicValue: iv,
    currentPrice:   cur,
    upsideDownside: upside,
    score:          app?.score          ?? null,
    category:       app?.category       ?? null,
    lastComputedAt: dq?.freshnessDays?.lastComputedAt ?? null,
    currency:       "USD",
  };
}

function extractFromSnapshot(
  data:     any | undefined,
  ivField:  string,
): Partial<MethodSummary> {
  if (!data || data.notComputed) return {};
  const v   = data.valuation     as any;
  const app = data.applicability as any;
  const dq  = data.dataQuality   as any;
  const iv  = v?.[ivField]       ?? null;
  const cur = v?.currentPrice    ?? null;
  const upside = iv && cur && cur > 0 ? (iv - cur) / cur : null;
  return {
    intrinsicValue: iv    != null ? Number(iv)    : null,
    currentPrice:   cur   != null ? Number(cur)   : null,
    upsideDownside: upside != null ? Number(upside) : null,
    score:          app?.score    ?? null,
    category:       app?.category ?? null,
    lastComputedAt: (dq?.freshnessDays as any)?.lastComputedAt ?? null,
    currency:       v?.currency ?? "USD",
  };
}

function resolveStatus(isPending: boolean, isError: boolean, isNotComputed: boolean): MethodStatus {
  if (isPending)      return "loading";
  if (isError)        return "error";
  if (isNotComputed)  return "not_computed";
  return "computed";
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Reads from the SAME React Query cache keys as the individual method tabs.
// When a user visits the Rule1 tab and it computes, the overview reflects that
// update immediately — no extra network calls, no synchronisation needed.
//
// The AI recommendation is a separate lightweight query (QK.overview) that
// fires once all methods have been attempted.
// ─────────────────────────────────────────────────────────────────────────────

export function useValuationOverview(
  symbol:      string,
  onSelectMethod?: (method: IntrinsicMethod) => void,
): ValuationOverviewData {
  const upper = (symbol ?? "").toUpperCase();
  const ddmVariant: DdmVariant = "gordon";

  // ── Read all 5 method caches (same keys as individual hooks) ───────────────
  const rule1Q = useQuery({
    queryKey:  QK.rule1(upper),
    queryFn:   () => rule1QueryFn(upper),
    enabled:   !!upper,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const dcfQ = useQuery({
    queryKey:  QK.dcf(upper),
    queryFn:   () => dcfQueryFn(upper),
    enabled:   !!upper,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const ddmQ = useQuery({
    queryKey:  QK.ddm(upper, ddmVariant),
    queryFn:   async () => {
      const outcome = await fetchDdmCached(upper, ddmVariant);
      if (outcome.status === "not_computed") return { notComputed: true };
      if (outcome.status === "ok")           return { ...outcome.payload, notComputed: false };
      throw new Error(outcome.message);
    },
    enabled:   !!upper,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const oeQ = useQuery({
    queryKey:  QK.ownerEarnings(upper),
    queryFn:   async () => {
      const outcome = await fetchOwnerEarningsCached(upper);
      if (outcome.status === "not_computed") return { notComputed: true };
      if (outcome.status === "ok")           return { ...outcome.payload, notComputed: false };
      throw new Error(outcome.message);
    },
    enabled:   !!upper,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const riQ = useQuery({
    queryKey:  QK.residualIncome(upper),
    queryFn:   async () => {
      const outcome = await fetchResidualIncomeCached(upper);
      if (outcome.status === "not_computed") return { notComputed: true };
      if (outcome.status === "ok")           return { ...outcome.payload, notComputed: false };
      throw new Error(outcome.message);
    },
    enabled:   !!upper,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  // ── Build per-method summaries ─────────────────────────────────────────────
  const methods: MethodSummary[] = [
    {
      id:    "rule1",
      ...METHOD_META.rule1,
      status: resolveStatus(
        rule1Q.isPending,
        rule1Q.isError,
        !!(rule1Q.data as any)?.notComputed,
      ),
      ...extractRule1(rule1Q.data as Rule1Data, "rule1"),
      intrinsicValue: (rule1Q.data as any)?.valuation?.stickerPrice ?? null,
      currentPrice:   (rule1Q.data as any)?.valuation?.currentPrice  ?? null,
      upsideDownside: null, // computed below
      score:          (rule1Q.data as any)?.applicability?.score    ?? null,
      category:       (rule1Q.data as any)?.applicability?.category ?? null,
      lastComputedAt: (rule1Q.data as any)?.dataQuality?.freshnessDays?.lastComputedAt ?? null,
      currency:       "USD",
      errorMessage:   rule1Q.error?.message,
    },
    {
      id:    "dcf",
      ...METHOD_META.dcf,
      status: resolveStatus(
        dcfQ.isPending,
        dcfQ.isError,
        !!(dcfQ.data as any)?.notComputed,
      ),
      ...extractFromSnapshot(dcfQ.data, "intrinsicValuePerShare"),
      errorMessage: dcfQ.error?.message,
    },
    {
      id:    "ddm",
      ...METHOD_META.ddm,
      status: resolveStatus(
        ddmQ.isPending,
        ddmQ.isError,
        !!(ddmQ.data as any)?.notComputed,
      ),
      ...extractFromSnapshot(ddmQ.data, "intrinsicValue"),
      errorMessage: ddmQ.error?.message,
    },
    {
      id:    "ownerEarnings",
      ...METHOD_META.ownerEarnings,
      status: resolveStatus(
        oeQ.isPending,
        oeQ.isError,
        !!(oeQ.data as any)?.notComputed,
      ),
      ...extractFromSnapshot(oeQ.data, "intrinsicValuePerShare"),
      errorMessage: oeQ.error?.message,
    },
    {
      id:    "residualIncome",
      ...METHOD_META.residualIncome,
      status: resolveStatus(
        riQ.isPending,
        riQ.isError,
        !!(riQ.data as any)?.notComputed,
      ),
      ...extractFromSnapshot(riQ.data, "intrinsicValuePerShare"),
      errorMessage: riQ.error?.message,
    },
  ];

  // Fix upside for Rule1 (stickerPrice vs currentPrice)
  const r1 = methods[0];
  if (r1.intrinsicValue != null && r1.currentPrice != null && r1.currentPrice > 0) {
    r1.upsideDownside = (r1.intrinsicValue - r1.currentPrice) / r1.currentPrice;
  }

  // ── AI recommendation ──────────────────────────────────────────────────────
  // Only fires when at least one method is computed and none are still loading.
  const anyComputed = methods.some((m) => m.status === "computed");
  const allLoading  = methods.every((m) => m.status === "loading");
  const anyLoading  = methods.some((m) => m.status === "loading");

  const recQ = useQuery<OverviewRecommendation | null, Error>({
    queryKey:  QK.overview(upper),
    queryFn:   () => fetchOverviewSummary(upper),
    enabled:   !!upper && anyComputed && !anyLoading,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     0,  // AI call — don't retry on failure, just show no recommendation
  });

  return {
    methods,
    recommendation: recQ.data ?? null,
    loadingRec:     recQ.isPending && anyComputed && !anyLoading,
    anyComputed,
    allLoading,
  };
}