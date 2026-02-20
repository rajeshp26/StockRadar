import { cn } from "@/lib/utils";
import { useDcfAnalysis } from "../hooks/useDcfAnalysis";
import { SectionHeader, ScoreBar } from "./shared-ui";

export function DcfSuitability({ symbol }: { symbol: string }) {
  const { data, loading } = useDcfAnalysis(symbol);

  if (loading || !data) return null;

  const { applicability } = data;

  return (
    <div className="glass-panel p-8">
      <SectionHeader title="DCF Suitability" subtitle="Model applicability score and flags" />

      <div className="space-y-5">
        <ScoreBar score={applicability.score} category={applicability.category} />

        {applicability.flags && applicability.flags.length > 0 ? (
          <div className="space-y-3">
            {applicability.flags.map((f, idx) => {
              const tone =
                f.severity === "critical" || f.severity === "high"
                  ? "border-rose-500/20  bg-rose-500/5"
                  : f.severity === "medium"
                  ? "border-amber-500/20 bg-amber-500/5"
                  : "border-white/8      bg-white/3";

              return (
                <div key={idx} className={cn("rounded-xl border px-4 py-3", tone)}>
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
                    {f.code}
                  </p>
                  <p className="text-xs text-white/60 leading-relaxed">{f.message}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-white/30 italic">
            No major suitability concerns identified for this DCF.
          </p>
        )}
      </div>
    </div>
  );
}