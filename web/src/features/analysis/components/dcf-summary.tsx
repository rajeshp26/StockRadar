import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDcfAnalysis } from "../hooks/useDcfAnalysis";

export function DcfSummary({ symbol }: { symbol: string }) {
  const { data, loading } = useDcfAnalysis(symbol);

  if (loading || !data) return null;

  const v = data.valuation;

  return (
    <Card>
      <CardHeader>
        <CardTitle>DCF Summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div>Intrinsic Value / Share: {v.intrinsicValuePerShare?.toFixed(2) ?? "—"}</div>
        <div>Terminal Method: {v.terminalMethod}</div>
        <div>WACC: {(v.waccUsed * 100).toFixed(2)}%</div>
        <div>
          Upside / Downside:{" "}
          {v.upsideDownsidePct != null
            ? `${(v.upsideDownsidePct * 100).toFixed(1)}%`
            : "—"}
        </div>
      </CardContent>
    </Card>
  );
}