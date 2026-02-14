"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

import { useLivePrice } from "@/features/analysis/hooks/useLivePrice";
import { IntrinsicValueRoot } from "@/features/analysis/components/intrinsic-value-root";

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
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>

      <CardContent className="space-y-3">
        <p className="text-slate-600 text-sm">{description}</p>

        <div className="rounded bg-slate-100 p-3 inline-block text-xs text-slate-500">
          Coming Soon
        </div>

        <ul className="list-disc ml-6 text-sm text-slate-500">
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

  // Real‑time price (via SSE / watchlist)
  const { price, change, changePercent, lastUpdated } =
    useLivePrice(upperSymbol);

  const [tab, setTab] = useState("intrinsic");

  // Price formatting
  const priceDisplay =
    price != null ? `$${price.toFixed(2)}` : "Price unavailable";

  const changeDisplay =
    change != null
      ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}`
      : null;

  const pctDisplay =
    changePercent != null
      ? `(${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%)`
      : null;

  const updatedDisplay = lastUpdated
    ? new Date(lastUpdated).toLocaleTimeString()
    : null;

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
      {/* ------------------------------------------------------ */}
      {/* STICKY HEADER                                          */}
      {/* ------------------------------------------------------ */}
      <div className="sticky top-0 bg-white z-20 pb-3">
        <div className="flex flex-col md:flex-row md:items-center md:gap-3 gap-1">
          <Button variant="ghost" onClick={() => router.back()}>
            ← Back
          </Button>

          <h1 className="text-2xl font-bold tracking-tight">
            {upperSymbol}
          </h1>

          {/* Real‑time price */}
          <div className="text-sm text-slate-600 flex items-center gap-2">
            <span>{priceDisplay}</span>

            {changeDisplay && pctDisplay && (
              <span
                className={
                  change >= 0 ? "text-green-600" : "text-red-600"
                }
              >
                {changeDisplay} {pctDisplay}
              </span>
            )}

            {updatedDisplay && (
              <span className="text-slate-400 text-xs">
                • updated {updatedDisplay}
              </span>
            )}
          </div>
        </div>

        <Separator className="mt-3" />
      </div>

      {/* ------------------------------------------------------ */}
      {/* TOP‑LEVEL TABS                                         */}
      {/* ------------------------------------------------------ */}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="flex flex-wrap">
          <TabsTrigger value="intrinsic">Intrinsic Value</TabsTrigger>
          <TabsTrigger value="health">Financial Health</TabsTrigger>
          <TabsTrigger value="moat">Moat</TabsTrigger>
          <TabsTrigger value="dividend">Dividend</TabsTrigger>
          <TabsTrigger value="technical">Technical</TabsTrigger>
          <TabsTrigger value="investors">Super Investors</TabsTrigger>
          <TabsTrigger value="others">Others</TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------------ */}
        {/* INTRINSIC VALUE (Overview + Deep Dive)                */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="intrinsic" className="pt-4">
          <IntrinsicValueRoot symbol={upperSymbol} />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* FINANCIAL HEALTH                                      */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="health" className="pt-4">
          <ComingSoonPanel
            title="Financial Health"
            description="Balance sheet quality, leverage, cash flows, and risk indicators."
            items={[
              "Altman Z‑Score",
              "Piotroski F‑Score",
              "Ohlson O‑Score",
              "Leverage trends",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* MOAT TAB                                              */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="moat" className="pt-4">
          <ComingSoonPanel
            title="Moat Analysis"
            description="Moat durability across ROIC, margins, and industry positioning."
            items={[
              "ROIC vs WACC",
              "Margin durability",
              "Return stability",
              "Capital efficiency",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* DIVIDEND TAB                                          */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="dividend" className="pt-4">
          <ComingSoonPanel
            title="Dividend Safety"
            description="Dividend payout stability, coverage ratios, and consistency."
            items={[
              "Payout ratio",
              "Dividend CAGR",
              "Cash flow coverage",
              "Stability profile",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* TECHNICAL TAB                                         */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="technical" className="pt-4">
          <ComingSoonPanel
            title="Technical Analysis"
            description="Momentum, trend, and market behavior indicators."
            items={[
              "RSI",
              "Moving averages",
              "MACD",
              "Trend strength",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* SUPER INVESTORS TAB                                   */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="investors" className="pt-4">
          <ComingSoonPanel
            title="Super Investors"
            description="Insights from major value investors and 13F tracking."
            items={[
              "Buffett / Munger positions",
              "Pabrai clone tracking",
              "High‑conviction ideas",
              "Portfolio overlap",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* OTHERS TAB                                            */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="others" className="pt-4">
          <ComingSoonPanel
            title="Other Models"
            description="Additional valuation frameworks and investment models."
            items={[
              "Residual Income",
              "Magic Formula",
              "CAN SLIM",
              "Relative valuation",
            ]}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}