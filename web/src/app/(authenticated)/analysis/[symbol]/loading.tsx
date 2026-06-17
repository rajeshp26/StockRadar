export default function AnalysisLoading() {
  return (
    <div className="space-y-6 animate-fade-up" data-testid="page-skeleton">
      {/* ── Sticky hero skeleton ──────────────────────────────── */}
      <div className="sticky top-14 z-20">
        <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
          <div className="relative flex flex-col gap-4 md:flex-row md:items-center">
            <div className="flex items-center gap-4">
              <div className="h-9 w-9 rounded-xl bg-white/5 animate-pulse" />
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-2xl bg-white/5 animate-pulse" />
                <div className="h-8 w-24 rounded-lg bg-white/5 animate-pulse" />
              </div>
            </div>
            <div className="md:ml-auto flex items-baseline gap-3">
              <div className="h-8 w-28 rounded-lg bg-white/5 animate-pulse" />
              <div className="h-5 w-32 rounded-lg bg-white/5 animate-pulse" />
            </div>
          </div>
        </div>
      </div>

      {/* ── Tab bar skeleton ──────────────────────────────────── */}
      <div className="glass-segmented p-1.5">
        <div className="flex gap-1">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className="h-9 flex-1 rounded-xl bg-white/5 animate-pulse"
              style={{ animationDelay: `${i * 50}ms` }}
            />
          ))}
        </div>
      </div>

      {/* ── Content skeleton ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="glass-panel rounded-[1.75rem] p-6 space-y-4"
            >
              <div className="h-5 w-40 rounded-lg bg-white/5 animate-pulse" />
              <div className="h-4 w-full rounded-lg bg-white/5 animate-pulse" />
              <div className="h-4 w-3/4 rounded-lg bg-white/5 animate-pulse" />
              {i === 2 && (
                <div className="h-4 w-1/2 rounded-lg bg-white/5 animate-pulse" />
              )}
            </div>
          ))}
        </div>
        <div className="space-y-6">
          <div className="glass-panel rounded-[1.75rem] p-6 space-y-4">
            <div className="h-5 w-32 rounded-lg bg-white/5 animate-pulse" />
            <div className="h-4 w-full rounded-lg bg-white/5 animate-pulse" />
            <div className="h-4 w-3/4 rounded-lg bg-white/5 animate-pulse" />
          </div>
        </div>
      </div>
    </div>
  );
}
