// web/src/app/(authenticated)/analysis/[symbol]/page.tsx
// CHANGES vs previous version:
//   1. Imports OwnerEarningsPanel and ResidualIncomePanel
//   2. Adds {method === "ownerEarnings"} and {method === "residualIncome"} renders
//   3. "Others" coming-soon panel no longer lists "Residual Income" (it ships now)
// Everything else is IDENTICAL to the existing file.
"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useLivePrice } from "@/features/analysis/hooks/useLivePrice";
import { formatTimestamp } from "@/lib/time";
import { prefetchAllValuations } from "@/features/analysis/utils/prefetch-valuations";
import {
  MethodSelector,
  type IntrinsicMethod,
} from "@/features/analysis/components/method-selector";
import { ValuationOverview } from "@/features/analysis/components/valuation-overview";
import { IntrinsicPanel } from "@/features/analysis/components/intrinsic-panel";
import { DcfPanel } from "@/features/analysis/components/dcf-panel";
import { DdmPanel } from "@/features/analysis/components/ddm-panel";
import { OwnerEarningsPanel } from "@/features/analysis/components/owner-earnings-panel";   // ← NEW
import { ResidualIncomePanel } from "@/features/analysis/components/residual-income-panel"; // ← NEW
import { DividendPanel } from "@/features/analysis/components/dividend-panel";

import {
  TrendingUp,
  Heart,
  Shield,
  TrendingDown,
  BarChart2,
  Users,
  MoreHorizontal,
  ArrowLeft,
} from "lucide-react";



/* ── Tab definitions ──────────────────────────────────────────── */
const TOP_TABS = [
  { id: "intrinsic", label: "Intrinsic Value", icon: TrendingUp },
  { id: "health", label: "Financial Health", icon: Heart },
  { id: "moat", label: "Moat", icon: Shield },
  { id: "dividend", label: "Dividend", icon: TrendingDown },
  { id: "technical", label: "Technical", icon: BarChart2 },
  { id: "investors", label: "Super Investors", icon: Users },
  { id: "others", label: "Others", icon: MoreHorizontal },
] as const;

type TopTab = (typeof TOP_TABS)[number]["id"];

/* ── Coming-soon placeholder panel ───────────────────────────── */
function ComingSoonPanel({
  title,
  description,
  items,
  icon: Icon,
}: {
  title: string;
  description: string;
  items: string[];
  icon: React.ElementType;
}) {
  return (
    <div className="glass-panel p-12 flex flex-col items-center text-center space-y-6 animate-fade-up">
      <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-white/5 border border-white/10">
        <Icon className="h-9 w-9 text-white/25" />
      </div>
      <div>
        <h3 className="text-xl font-black text-white tracking-tight">{title}</h3>
        <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">
          {description}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {items.map((item) => (
          <span
            key={item}
            className="px-3 py-1.5 rounded-xl bg-white/5 border border-white/8 text-[10px] font-bold uppercase tracking-widest text-white/30"
          >
            {item}
          </span>
        ))}
      </div>
      <div className="px-4 py-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-black uppercase tracking-widest text-indigo-400">
        Coming Soon
      </div>
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────────────── */
export default function AnalysisPage() {
  const router = useRouter();
  const { symbol } = useParams<{ symbol: string }>();
  const upperSymbol = symbol?.toString().toUpperCase() ?? "";
  const queryClient = useQueryClient();

  const [method, setMethod] = useState<IntrinsicMethod>("overview");
  const [tab, setTab] = useState<TopTab>("intrinsic");

  const { price, change, changePercent, lastUpdated } = useLivePrice(upperSymbol);

  // ── Prefetch all valuation methods on page load ──────────────────────────
  // Fires 5 parallel GET requests the moment this page mounts.
  // By the time the user clicks any method tab, data is already in cache.
  // prefetchAllValuations is a no-op for methods already cached within staleTime.
  useEffect(() => {
    prefetchAllValuations(upperSymbol, queryClient);
  }, [upperSymbol, queryClient]);

  const priceDisplay = price != null ? `$${price.toFixed(2)}` : "—";
  const changeDisplay =
    change != null
      ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}`
      : null;
  const pctDisplay =
    changePercent != null
      ? `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`
      : null;
  const updatedDisplay = formatTimestamp(lastUpdated, "relative");
  const isPositiveChange = (change ?? 0) >= 0;

  return (
    <div className="space-y-6 animate-fade-up">
      {/* ── Sticky hero header ──────────────────────────────── */}
      <div className="sticky top-14 z-20">
        <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
          <div
            className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-indigo-600/10 blur-[80px]"
            aria-hidden="true"
          />
          <div className="relative flex flex-col gap-4 md:flex-row md:items-center">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.back()}
                className="glass-btn flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0"
                aria-label="Go back"
              >
                <ArrowLeft className="h-4 w-4 text-white/60" />
              </button>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-indigo-500/20 border border-indigo-500/30 text-sm font-black text-indigo-300">
                  {upperSymbol[0]}
                </div>
                <h1 className="text-2xl font-black tracking-tighter text-white uppercase">
                  {upperSymbol}
                </h1>
              </div>
            </div>
            <div className="flex items-baseline gap-3 md:ml-auto">
              <span className="text-2xl font-black text-white tracking-tight">
                {priceDisplay}
              </span>
              {changeDisplay && pctDisplay && (
                <span
                  className={cn(
                    "text-sm font-bold",
                    isPositiveChange ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  {changeDisplay} ({pctDisplay})
                </span>
              )}
              {updatedDisplay && (
                <span className="text-[10px] font-medium text-white/25 hidden md:inline">
                  · {updatedDisplay}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Top-level tab bar ───────────────────────────────── */}
      <div className="glass-segmented overflow-x-auto no-scrollbar w-full">
        {TOP_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "glass-segmented-item flex items-center gap-1.5",
              tab === id && "active"
            )}
          >
            <Icon className="h-3 w-3 flex-shrink-0" />
            <span className="hidden sm:inline">{label}</span>
            <span className="sm:hidden">{label.split(" ")[0]}</span>
          </button>
        ))}
      </div>

      {/* ── Tab content ─────────────────────────────────────── */}
      <div className="min-h-[40vh]">
        {/* Intrinsic Value */}
        {tab === "intrinsic" && (
          <div className="space-y-6 animate-fade-up">
            <MethodSelector method={method} onChange={setMethod} />
            {method === "overview" && (
              <ValuationOverview
                symbol={upperSymbol}
                onSelectMethod={setMethod}
              />
            )}
            {method === "rule1" && <IntrinsicPanel symbol={upperSymbol} />}
            {method === "dcf" && <DcfPanel symbol={upperSymbol} />}
            {method === "ddm" && <DdmPanel symbol={upperSymbol} />}
            {method === "ownerEarnings" && <OwnerEarningsPanel symbol={upperSymbol} />} {/* ← NEW */}
            {method === "residualIncome" && <ResidualIncomePanel symbol={upperSymbol} />} {/* ← NEW */}
          </div>
        )}

        {tab === "health" && (
          <ComingSoonPanel
            title="Financial Health"
            description="Balance sheet quality, leverage, cash flows, and risk indicators."
            items={["Altman Z-Score", "Piotroski F-Score", "Ohlson O-Score", "Leverage Trends"]}
            icon={Heart}
          />
        )}
        {tab === "moat" && (
          <ComingSoonPanel
            title="Moat Analysis"
            description="Moat durability across ROIC, margins, and industry positioning."
            items={["ROIC vs WACC", "Margin Durability", "Return Stability", "Capital Efficiency"]}
            icon={Shield}
          />
        )}
        {tab === "dividend" && (
          <div className="animate-fade-up">
            <DividendPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "technical" && (
          <ComingSoonPanel
            title="Technical Analysis"
            description="Momentum, trend, and market behavior indicators."
            items={["RSI", "Moving Averages", "MACD", "Trend Strength"]}
            icon={BarChart2}
          />
        )}
        {tab === "investors" && (
          <ComingSoonPanel
            title="Super Investors"
            description="Insights from major value investors and 13F tracking."
            items={["Buffett / Munger", "Pabrai Tracking", "High-Conviction Ideas", "Portfolio Overlap"]}
            icon={Users}
          />
        )}
        {tab === "others" && (
          <ComingSoonPanel
            title="Other Models"
            description="Additional valuation frameworks and investment models."
            items={["Magic Formula", "CAN SLIM", "Relative Valuation", "Graham Number"]}
            // NOTE: "Residual Income" removed — it now lives in the Intrinsic Value tab (RI button)
            icon={MoreHorizontal}
          />
        )}
      </div>
    </div>
  );
}