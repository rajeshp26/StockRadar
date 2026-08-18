"use client";
import { useState, useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { prefetchAllValuations } from "@/features/analysis/utils/prefetch-valuations";
import { useHoldingExists } from "@/features/portfolio/hooks/usePortfolio";
import { usePredictiveTabPrefetch } from "@/features/analysis/hooks/usePredictiveTabPrefetch";
import {
  MethodSelector,
  type IntrinsicMethod,
} from "@/features/analysis/components/method-selector";
import { ValuationOverviewTab } from "@/components/analysis/valuation-overview-tab";
import { IntrinsicPanel } from "@/features/analysis/components/intrinsic-panel";
import { DcfPanel } from "@/features/analysis/components/dcf-panel";
import { DdmPanel } from "@/features/analysis/components/ddm-panel";
import { OwnerEarningsPanel } from "@/features/analysis/components/owner-earnings-panel";
import { ResidualIncomePanel } from "@/features/analysis/components/residual-income-panel";

import {
  TrendingUp,
  Heart,
  Shield,
  TrendingDown,
  BarChart2,
  Users,
  MoreHorizontal,
  AlertTriangle,
} from "lucide-react";

const DividendPanel = dynamic(
  () => import("@/features/analysis/components/dividend-panel").then((m) => ({ default: m.DividendPanel })),
  { ssr: false },
);
const MurphyPanel = dynamic(
  () => import("@/features/analysis/components/murphy-panel").then((m) => ({ default: m.MurphyPanel })),
  { ssr: false },
);
const MagicFormulaPanel = dynamic(
  () => import("@/features/analysis/components/magic-formula-panel").then((m) => ({ default: m.MagicFormulaPanel })),
  { ssr: false },
);
const CANSlimPanel = dynamic(
  () => import("@/features/analysis/components/canslim-panel").then((m) => ({ default: m.CANSlimPanel })),
  { ssr: false },
);
const MoatPanel = dynamic(
  () => import("@/features/analysis/components/moat-panel").then((m) => ({ default: m.MoatPanel })),
  { ssr: false },
);
const RiskPanel = dynamic(
  () => import("@/features/analysis/components/risk-panel").then((m) => ({ default: m.RiskPanel })),
  { ssr: false },
);
const SuperInvestorsTab = dynamic(
  () => import("@/features/analysis/components/SuperInvestorsTab").then((m) => ({ default: m.SuperInvestorsTab })),
  { ssr: false },
);
const StockVsIndexPanel = dynamic(
  () => import("@/features/analysis/components/stock-vs-index-panel").then((m) => ({ default: m.StockVsIndexPanel })),
  { ssr: false },
);
const FundamentalsPanel = dynamic(
  () => import("@/features/analysis/components/fundamentals-panel").then((m) => ({ default: m.FundamentalsPanel })),
  { ssr: false },
);
const StockPerformancePanel = dynamic(
  () => import("@/features/analysis/components/stock-performance-panel").then((m) => ({ default: m.StockPerformancePanel })),
  { ssr: false },
);

type OthersMethod = "magic_formula" | "canslim";

const BASE_TABS = [
  { id: "intrinsic", label: "Intrinsic Value", icon: TrendingUp },
  { id: "health", label: "Fundamentals", icon: Heart },
  { id: "moat", label: "Moat", icon: Shield },
  { id: "dividend", label: "Dividend", icon: TrendingDown },
  { id: "comparison", label: "Market Comparison", icon: BarChart2 },
  { id: "technical", label: "Technical", icon: BarChart2 },
  { id: "risk", label: "Risk Assessment", icon: AlertTriangle },
  { id: "investors", label: "Super Investors", icon: Users },
  { id: "others", label: "Others", icon: MoreHorizontal },
] as const;

type TopTab = (typeof BASE_TABS)[number]["id"] | "performance";

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
        <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">{description}</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {items.map((item) => (
          <span key={item} className="px-3 py-1.5 rounded-xl bg-white/5 border border-white/8 text-[10px] font-bold uppercase tracking-widest text-white/30">{item}</span>
        ))}
      </div>
      <div className="px-4 py-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-black uppercase tracking-widest text-indigo-400">Coming Soon</div>
    </div>
  );
}

export function ClientTabs({ symbol }: { symbol: string }) {
  const queryClient = useQueryClient();
  const upperSymbol = symbol.toUpperCase();

  const [method, setMethod] = useState<IntrinsicMethod>("overview");

  const handleSelectMethod = (m: IntrinsicMethod) => {
    setMethod(m);
  };
  const [tab, setTab] = useState<TopTab>("intrinsic");
  const [othersMethod, setOthersMethod] = useState<OthersMethod>("magic_formula");

  // holdings/exists is not on the page critical path — defer it to idle so a
  // fresh page load issues exactly 2 valuation requests (summary + quote).
  const [idleReady, setIdleReady] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined" && "requestIdleCallback" in window) {
      const id = requestIdleCallback(() => setIdleReady(true), { timeout: 2000 });
      return () => cancelIdleCallback(id);
    }
    const t = setTimeout(() => setIdleReady(true), 1000);
    return () => clearTimeout(t);
  }, []);

  const { data: holdingExists } = useHoldingExists(upperSymbol, { enabled: idleReady });
  const isHeld = holdingExists?.held ?? false;

  const TOP_TABS = useMemo(() => {
    const tabs: { id: TopTab; label: string; icon: React.ElementType }[] = [...BASE_TABS];
    if (isHeld) {
      tabs.splice(5, 0, { id: "performance", label: "Performance", icon: TrendingUp });
    }
    return tabs;
  }, [isHeld]);

  usePredictiveTabPrefetch(upperSymbol, tab);

  useEffect(() => {
    prefetchAllValuations(upperSymbol, queryClient);
  }, [upperSymbol, queryClient]);

  return (
    <>
      <div className="glass-segmented overflow-x-auto w-full styled-scrollbar">
        {TOP_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn("glass-segmented-item flex items-center gap-1.5", tab === id && "active")}
          >
            <Icon className="h-3 w-3 flex-shrink-0" />
            <span className="hidden sm:inline">{label}</span>
            <span className="sm:hidden">{label.split(" ")[0]}</span>
          </button>
        ))}
      </div>

      <div className="min-h-[40vh]">
        {tab === "intrinsic" && (
          <div className="space-y-6 animate-fade-up">
            <MethodSelector method={method} onChange={setMethod} />
            {method === "overview" && <ValuationOverviewTab symbol={upperSymbol} onSelectMethod={handleSelectMethod} />}
            {method === "rule1" && <IntrinsicPanel symbol={upperSymbol} />}
            {method === "dcf" && <DcfPanel symbol={upperSymbol} />}
            {method === "ddm" && <DdmPanel symbol={upperSymbol} />}
            {method === "ownerEarnings" && <OwnerEarningsPanel symbol={upperSymbol} />}
            {method === "residualIncome" && <ResidualIncomePanel symbol={upperSymbol} />}
          </div>
        )}

        {tab === "health" && (
          <div className="animate-fade-up">
            <FundamentalsPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "moat" && (
          <div className="animate-fade-up">
            <MoatPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "risk" && (
          <div className="space-y-6 animate-fade-up">
            <RiskPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "dividend" && (
          <div className="animate-fade-up">
            <DividendPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "comparison" && (
          <div className="animate-fade-up">
            <StockVsIndexPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "performance" && (
          <div className="animate-fade-up">
            <StockPerformancePanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "technical" && (
          <div className="animate-fade-up">
            <MurphyPanel symbol={upperSymbol} />
          </div>
        )}
        {tab === "investors" && (
          <div className="animate-fade-up">
            <SuperInvestorsTab symbol={upperSymbol} />
          </div>
        )}
        {tab === "others" && (
          <div className="space-y-6 animate-fade-up">
            <div className="glass-segmented overflow-x-auto no-scrollbar w-full">
              <button
                onClick={() => setOthersMethod("magic_formula")}
                className={cn("glass-segmented-item flex items-center gap-1.5", othersMethod === "magic_formula" && "active")}
              >
                <span className="hidden sm:inline">Magic Formula</span>
                <span className="sm:hidden">Magic</span>
              </button>
              <button
                onClick={() => setOthersMethod("canslim")}
                className={cn("glass-segmented-item flex items-center gap-1.5", othersMethod === "canslim" && "active")}
              >
                <span className="hidden sm:inline">CANSlim</span>
                <span className="sm:hidden">CANS</span>
              </button>
              <button disabled className="glass-segmented-item flex items-center gap-1.5 opacity-35 cursor-not-allowed">
                <span className="hidden sm:inline">Relative Valuation</span>
                <span className="sm:hidden">Relative</span>
              </button>
              <button disabled className="glass-segmented-item flex items-center gap-1.5 opacity-35 cursor-not-allowed">
                <span className="hidden sm:inline">Graham Number</span>
                <span className="sm:hidden">Graham</span>
              </button>
            </div>
            {othersMethod === "magic_formula" && <MagicFormulaPanel symbol={upperSymbol} />}
            {othersMethod === "canslim" && <CANSlimPanel symbol={upperSymbol} />}
          </div>
        )}
      </div>
    </>
  );
}
