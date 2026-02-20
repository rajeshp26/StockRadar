"use client";

import { cn } from "@/lib/utils";

export type IntrinsicMethod = "overview" | "rule1" | "dcf" | "ddm";

const METHODS: { id: IntrinsicMethod; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "rule1",    label: "Rule #1"  },
  { id: "dcf",      label: "DCF"      },
  { id: "ddm",      label: "DDM"      },
];

export function MethodSelector({
  method,
  onChange,
}: {
  method:   IntrinsicMethod;
  onChange: (m: IntrinsicMethod) => void;
}) {
  return (
    <div className="flex items-center gap-2" role="tablist" aria-label="Valuation method">
      {METHODS.map(({ id, label }) => (
        <button
          key={id}
          role="tab"
          aria-selected={method === id}
          onClick={() => onChange(id)}
          className={cn(
            "px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-[0.2em]",
            "border transition-all duration-200",
            method === id
              ? "bg-indigo-600 border-indigo-400/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)]"
              : "bg-white/5 border-white/8 text-white/30 hover:text-white/60 hover:bg-white/8",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}