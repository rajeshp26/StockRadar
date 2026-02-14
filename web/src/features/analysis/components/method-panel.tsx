"use client";

import { ReactNode } from "react";
import { Separator } from "@/components/ui/separator";

interface MethodPanelProps {
  summary: ReactNode;
  how: ReactNode;
  suitability: ReactNode;
  history: ReactNode;
}

export function MethodPanel({
  summary,
  how,
  suitability,
  history,
}: MethodPanelProps) {
  return (
    <div className="space-y-6">
      {summary}
      {how}
      {suitability}

      <Separator />

      {history}
    </div>
  );
}