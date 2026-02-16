"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { IntrinsicPanel } from "./intrinsic-panel";
import { MethodSelector, type IntrinsicMethod } from "./method-selector";
import { ValuationOverview } from "./valuation-overview";

const DdmPanel = dynamic(() => import("./ddm-panel").then((m) => m.DdmPanel), {
  loading: () => <p className="text-sm text-slate-500">Loading DDM…</p>,
  ssr: false,
});

export function IntrinsicValueRoot({ symbol }: { symbol: string }) {
  const [method, setMethod] = useState<IntrinsicMethod>("rule1");

  return (
    <div className="space-y-6">
      <ValuationOverview />

     
      {method === "rule1" ? <IntrinsicPanel symbol={symbol} /> : <DdmPanel symbol={symbol} />}
    </div>
  );
}