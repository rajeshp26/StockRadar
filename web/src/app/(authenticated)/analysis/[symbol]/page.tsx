"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

import { useLivePrice } from "@/features/analysis/hooks/useLivePrice";

import { MethodSelector, type IntrinsicMethod } from "@/features/analysis/components/method-selector";
import { ValuationOverview } from "@/features/analysis/components/valuation-overview";
import { IntrinsicPanel } from "@/features/analysis/components/intrinsic-panel";
import { DcfPanel } from "@/features/analysis/components/dcf-panel";
import { DdmPanel } from "@/features/analysis/components/ddm-panel";

/* ----------------------------------------------------------
   Placeholder panel for all non‑Intrinsic sections
   ---------------------------------------------------------- */
function ComingSoonPanel({
  title,
  description,
  items,
}: {
  title: string;
  description: string;
  items: string[];
}) {
  return (
    <Card className="glass rounded-3xl border border-white/5 text-white">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>

      <CardContent className="space-y-3">
        <p className="text-slate-400 text-sm">{description}</p>

        <div className="rounded bg-white/5 border border-white/10 p-3 inline-block text-xs text-slate-400">
          Coming Soon
        </div>

        <ul className="list-disc ml-6 text-sm text-slate-400">
          {items.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/* ----------------------------------------------------------
   MAIN PAGE
   ---------------------------------------------------------- */
export default function AnalysisPage() {
  const router = useRouter();
  const { symbol } = useParams<{ symbol: string }>();
  const upperSymbol = symbol?.toString().toUpperCase() ?? "";

  // Intrinsic METHOD state (single source of truth)
  const [method, setMethod] = useState<IntrinsicMethod>("overview");

  // Top-level tab state
  const [tab, setTab] = useState("intrinsic");

  // Real-time price
  const { price, change, changePercent, lastUpdated } = useLivePrice(upperSymbol);

  const priceDisplay = price != null ? `$${price.toFixed(2)}` : "Price unavailable";

  const changeDisplay =
    change != null ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}` : null;

  const pctDisplay =
    changePercent != null
      ? `(${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%)`
      : null;

  const updatedDisplay = lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : null;

  return (
    <div className="app-backdrop min-h-screen text-white">
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
        {/* ------------------------------------------------------ */}
        {/* STICKY HEADER                                          */}
        {/* ------------------------------------------------------ */}
        <div className="sticky top-0 z-20 pt-3">
          <div className="glass rounded-3xl p-6 border border-white/5 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-600/10 blur-[100px] -mr-32 -mt-32" />

            <div className="relative flex flex-col md:flex-row md:items-center md:gap-3 gap-2">
              <Button
                variant="ghost"
                className="bg-white/5 border border-white/10 text-slate-300 hover:text-white hover:bg-white/10 w-fit"
                onClick={() => router.back()}
              >
                ← Back
              </Button>

              <h1 className="text-2xl font-black tracking-tight uppercase">
                {upperSymbol}
              </h1>

              <div className="text-sm text-slate-400 flex items-center gap-2 md:ml-auto">
                <span>{priceDisplay}</span>

                {changeDisplay && pctDisplay && (
                  <span className={change != null && change >= 0 ? "text-emerald-400" : "text-rose-400"}>
                    {changeDisplay} {pctDisplay}
                  </span>
                )}

                {updatedDisplay && (
                  <span className="text-slate-500 text-xs">• updated {updatedDisplay}</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ------------------------------------------------------ */}
        {/* TOP‑LEVEL TABS                                         */}
        {/* ------------------------------------------------------ */}
        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <div className="glass rounded-2xl p-2 border border-white/5">
            <TabsList className="flex flex-wrap">
              <TabsTrigger value="intrinsic">Intrinsic Value</TabsTrigger>
              <TabsTrigger value="health">Financial Health</TabsTrigger>
              <TabsTrigger value="moat">Moat</TabsTrigger>
              <TabsTrigger value="dividend">Dividend</TabsTrigger>
              <TabsTrigger value="technical">Technical</TabsTrigger>
              <TabsTrigger value="investors">Super Investors</TabsTrigger>
              <TabsTrigger value="others">Others</TabsTrigger>
            </TabsList>
          </div>

          {/* ------------------------------------------------------ */}
          {/* INTRINSIC VALUE                                       */}
          {/* ------------------------------------------------------ */}
          <TabsContent value="intrinsic" className="pt-4 space-y-6">
            <MethodSelector method={method} onChange={setMethod} />

            {method === "overview" && <ValuationOverview />}

            {method === "rule1" && <IntrinsicPanel symbol={upperSymbol} />}

            {method === "dcf" && <DcfPanel symbol={upperSymbol} />}

            {method === "ddm" && <DdmPanel symbol={upperSymbol} />}
          </TabsContent>

          {/* ------------------------------------------------------ */}
          {/* OTHER TABS (placeholders)                              */}
          {/* ------------------------------------------------------ */}
          <TabsContent value="health" className="pt-4">
            <ComingSoonPanel
              title="Financial Health"
              description="Balance sheet quality, leverage, cash flows, and risk indicators."
              items={["Altman Z‑Score", "Piotroski F‑Score", "Ohlson O‑Score", "Leverage trends"]}
            />
          </TabsContent>

          <TabsContent value="moat" className="pt-4">
            <ComingSoonPanel
              title="Moat Analysis"
              description="Moat durability across ROIC, margins, and industry positioning."
              items={["ROIC vs WACC", "Margin durability", "Return stability", "Capital efficiency"]}
            />
          </TabsContent>

          <TabsContent value="dividend" className="pt-4">
            <ComingSoonPanel
              title="Dividend Safety"
              description="Dividend payout stability, coverage ratios, and consistency."
              items={["Payout ratio", "Dividend CAGR", "Cash flow coverage", "Stability profile"]}
            />
          </TabsContent>

          <TabsContent value="technical" className="pt-4">
            <ComingSoonPanel
              title="Technical Analysis"
              description="Momentum, trend, and market behavior indicators."
              items={["RSI", "Moving averages", "MACD", "Trend strength"]}
            />
          </TabsContent>

          <TabsContent value="investors" className="pt-4">
            <ComingSoonPanel
              title="Super Investors"
              description="Insights from major value investors and 13F tracking."
              items={["Buffett / Munger positions", "Pabrai clone tracking", "High‑conviction ideas", "Portfolio overlap"]}
            />
          </TabsContent>

          <TabsContent value="others" className="pt-4">
            <ComingSoonPanel
              title="Other Models"
              description="Additional valuation frameworks and investment models."
              items={["Residual Income", "Magic Formula", "CAN SLIM", "Relative valuation"]}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}