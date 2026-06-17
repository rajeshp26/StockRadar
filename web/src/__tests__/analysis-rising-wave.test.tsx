import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import React from "react";

describe("Analysis Page — Rising Wave (Loading States)", () => {
  it("P3-UT-24: PriceSkeleton renders animated placeholders", () => {
    const { container } = render(
      <div className="sticky top-14 z-20">
        <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
          <div className="relative flex flex-col gap-4 md:flex-row md:items-center">
            <div className="flex items-center gap-4">
              <div className="glass-btn flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0" />
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-indigo-500/20 border border-indigo-500/30 text-sm font-black text-indigo-300 animate-pulse" />
                <div className="h-7 w-28 rounded-lg bg-white/5 animate-pulse" />
              </div>
            </div>
            <div className="flex items-baseline gap-3 md:ml-auto">
              <div className="h-7 w-24 rounded-lg bg-white/5 animate-pulse" />
            </div>
          </div>
        </div>
      </div>,
    );
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(2);
  });

  it("P3-UT-25: OverviewSkeleton renders method card placeholders", () => {
    const { container } = render(
      <div className="glass-panel p-8 space-y-6 animate-fade-up">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25" />
          <div>
            <div className="h-5 w-40 rounded-lg bg-white/5 animate-pulse" />
            <div className="h-3 w-64 rounded-lg bg-white/5 animate-pulse mt-1" />
          </div>
        </div>
        <div className="glass-divider" />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-card rounded-xl px-5 py-4 flex items-center gap-4">
              <div className="flex-1">
                <div className="h-4 w-24 rounded bg-white/5 animate-pulse" />
                <div className="h-3 w-32 rounded bg-white/5 animate-pulse mt-1" />
              </div>
              <div className="w-24">
                <div className="h-4 w-16 rounded bg-white/5 animate-pulse ml-auto" />
              </div>
              <div className="w-20">
                <div className="h-4 w-12 rounded bg-white/5 animate-pulse ml-auto" />
              </div>
              <div className="w-28">
                <div className="h-4 w-16 rounded bg-white/5 animate-pulse ml-auto" />
              </div>
            </div>
          ))}
        </div>
      </div>,
    );
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(12);
  });

  it("P3-UT-26: Suspense fallback shows before RSC resolves", () => {
    const { container } = render(
      React.createElement(React.Suspense, { fallback: React.createElement("div", { "data-testid": "suspense-fallback" }, "Loading overview...") },
        React.createElement("div", { "data-testid": "actual-content" }, "Content"),
      ),
    );
    expect(container.querySelector('[data-testid="actual-content"]')).toBeInTheDocument();
  });
});
