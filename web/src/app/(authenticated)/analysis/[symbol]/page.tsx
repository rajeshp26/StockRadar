// src/app/(authenticated)/analysis/[symbol]/page.tsx
"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

import { IntrinsicPanel } from "@/features/analysis/components/intrinsic-panel";

/* ----------------------------------------------------------
   Placeholder panel for all non-Rule1 sections
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

  const [tab, setTab] = useState("intrinsic");

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
      {/* ------------------------------------------------------ */}
      {/* STICKY HEADER                                          */}
      {/* ------------------------------------------------------ */}
      <div className="sticky top-0 bg-white z-20 pb-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={() => router.back()}>
            ← Back
          </Button>

          <h1 className="text-2xl font-bold tracking-tight">{upperSymbol}</h1>

          {/* You can fill Current Price here later when data provider is in place */}
          <span className="text-slate-400 text-sm">(Price unavailable)</span>
        </div>

        <Separator className="mt-3" />
      </div>

      {/* ------------------------------------------------------ */}
      {/* TABS                                                   */}
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
        {/* INTRINSIC VALUE TAB (Rule #1)                          */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="intrinsic" className="pt-4">
          <IntrinsicPanel symbol={upperSymbol} />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* FINANCIAL HEALTH                                      */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="health" className="pt-4">
          <ComingSoonPanel
            title="Financial Health"
            description="We will analyze balance sheet quality, leverage, cash flows, and risk indicators."
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
            description="Moat durability across ROIC, operating margins, and industry positioning."
            items={[
              "ROIC vs WACC",
              "Gross margin durability",
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
              "Stability profile",
              "Dividend CAGR",
              "Coverage vs Cash Flow",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* TECHNICAL TAB                                         */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="technical" className="pt-4">
          <ComingSoonPanel
            title="Technical Analysis"
            description="Momentum, RSI, trend lines, support/resistance patterns."
            items={[
              "RSI",
              "Moving Averages",
              "MACD",
              "Trend strength indicators",
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
              "Pabrai clone tracking",
              "Buffett/Munger insights",
              "High‑conviction ideas",
              "Portfolio overlap analysis",
            ]}
          />
        </TabsContent>

        {/* ------------------------------------------------------ */}
        {/* OTHERS TAB                                            */}
        {/* ------------------------------------------------------ */}
        <TabsContent value="others" className="pt-4">
          <ComingSoonPanel
            title="Other Models"
            description="Additional valuation models and investment frameworks."
            items={[
              "Magic Formula",
              "CAN SLIM",
              "Relative Valuation",
              "Owner Earnings",
            ]}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}