"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { VALUATION_METHODS } from "../valuation/methods";

export function ValuationOverview() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Valuation Overview</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {VALUATION_METHODS.filter(m => m.enabled).map(method => (
          <div
            key={method.id}
            className="flex items-center justify-between rounded border p-3"
          >
            <div>
              <div className="font-medium">{method.label}</div>
              <div className="text-sm text-slate-500">
                {method.description}
              </div>
            </div>

            <Badge variant="secondary">View</Badge>
          </div>
        ))}

        <div className="text-sm text-slate-500 pt-2">
          Compare intrinsic value estimates across multiple valuation techniques.
          Select a method to deep dive into assumptions and diagnostics.
        </div>
      </CardContent>
    </Card>
  );
}