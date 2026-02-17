"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type IntrinsicMethod = "overview" | "rule1" | "dcf" | "ddm";

export function MethodSelector({
  method,
  onChange,
}: {
  method: IntrinsicMethod;
  onChange: (m: IntrinsicMethod) => void;
}) {
  return (
    <Tabs value={method} onValueChange={(v) => onChange(v as IntrinsicMethod)}>
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="rule1">Rule #1</TabsTrigger>
        <TabsTrigger value="dcf">DCF</TabsTrigger>
        <TabsTrigger value="ddm">DDM</TabsTrigger>
      </TabsList>
    </Tabs>
  );
}