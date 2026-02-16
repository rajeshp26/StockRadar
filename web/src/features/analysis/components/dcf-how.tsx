import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDcfAnalysis } from "../hooks/useDcfAnalysis";

export function DcfHow({ symbol }: { symbol: string }) {
  const { data, loading } = useDcfAnalysis(symbol);

  if (loading || !data) return null;

  const v = data.valuation;

  return (
    <Card>
      <CardHeader>
        <CardTitle>How this DCF was calculated</CardTitle>
      </CardHeader>

      <CardContent className="space-y-2 text-sm">
        <div>
          <strong>Forecast horizon:</strong> {v.forecastYears} years
        </div>

        <div>
          <strong>Free Cash Flow forecast:</strong>{" "}
          {v.forecastFcf.length > 0
            ? `${v.forecastFcf.length} years projected`
            : "Not available"}
        </div>

        <div>
          <strong>Discount rate (WACC):</strong>{" "}
          {(v.waccUsed * 100).toFixed(2)}%
        </div>

        <div>
          <strong>Terminal value method:</strong> {v.terminalMethod}
        </div>

        {v.terminalValue != null && (
          <div>
            <strong>Terminal value:</strong>{" "}
            {v.terminalValue.toLocaleString()}
          </div>
        )}

        <div className="text-slate-500 text-xs pt-2">
          All assumptions are resolved by the backend using reported financials,
          method defaults, and company overrides. No frontend calculations are
          performed.
        </div>
      </CardContent>
    </Card>
  );
}