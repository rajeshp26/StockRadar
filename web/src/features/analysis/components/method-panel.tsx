"use client";

import { ReactNode } from "react";

interface MethodPanelProps {
  summary:     ReactNode;
  how:         ReactNode;
  suitability: ReactNode;
  history:     ReactNode;
}

export function MethodPanel({ summary, how, suitability, history }: MethodPanelProps) {
  return (
    <div className="space-y-6">
      {summary}
      {how}
      {suitability}
      {/* Glass divider replaces shadcn Separator */}
      <div className="glass-divider my-2" />
      {history}
    </div>
  );
}