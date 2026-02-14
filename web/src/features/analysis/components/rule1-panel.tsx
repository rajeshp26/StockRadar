"use client";

import { MethodPanel } from "./method-panel";
import { IntrinsicPanel } from "./intrinsic-panel";

export function Rule1Panel({ symbol }: { symbol: string }) {
  return (
    <IntrinsicPanel symbol={symbol} />
  );
}