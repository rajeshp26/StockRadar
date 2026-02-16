import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useDcfAnalysis } from "../hooks/useDcfAnalysis";

function categoryColor(category?: string) {
  switch (category) {
    case "Good":
      return "bg-green-100 text-green-800";
    case "Caution":
      return "bg-yellow-100 text-yellow-800";
    case "Poor":
      return "bg-red-100 text-red-800";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

export function DcfSuitability({ symbol }: { symbol: string }) {
  const { data, loading } = useDcfAnalysis(symbol);

  if (loading || !data) return null;

  const { applicability } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>DCF Suitability</CardTitle>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="text-2xl font-semibold">
            {applicability.score ?? "—"}
          </div>

          <Badge className={categoryColor(applicability.category)}>
            {applicability.category ?? "Unknown"}
          </Badge>
        </div>

        {applicability.flags && applicability.flags.length > 0 && (
          <div className="space-y-2 pt-2">
            {applicability.flags.map((f, idx) => (
              <div
                key={idx}
                className="text-sm text-slate-600 border-l-2 pl-3"
              >
                <div className="font-medium">{f.code}</div>
                <div>{f.message}</div>
              </div>
            ))}
          </div>
        )}

        {(!applicability.flags || applicability.flags.length === 0) && (
          <div className="text-sm text-slate-500">
            No major suitability concerns identified for this DCF.
          </div>
        )}
      </CardContent>
    </Card>
  );
}