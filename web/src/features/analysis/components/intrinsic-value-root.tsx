"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ValuationOverview } from "./valuation-overview";
import { Rule1Panel } from "./rule1-panel";
import { VALUATION_METHODS } from "../valuation/methods";

export function IntrinsicValueRoot({ symbol }: { symbol: string }) {
  return (
    <Tabs defaultValue="overview">
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>

        {VALUATION_METHODS.filter(m => m.enabled).map(m => (
          <TabsTrigger key={m.id} value={m.id}>
            {m.shortLabel}
          </TabsTrigger>
        ))}
      </TabsList>

      <TabsContent value="overview">
        <ValuationOverview />
      </TabsContent>

      <TabsContent value="rule1">
        <Rule1Panel symbol={symbol} />
      </TabsContent>

      {/* Future methods drop in here */}
      {/* <TabsContent value="dcf"><DcfPanel /></TabsContent> */}
    </Tabs>
  );
}