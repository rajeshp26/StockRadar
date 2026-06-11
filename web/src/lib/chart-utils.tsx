// web/src/lib/chart-utils.tsx
import React from "react";

interface SparklineDatum {
  date: string;
  value: number;
}

export function TrendSparkline({ data }: { data: SparklineDatum[] }) {
  if (!data.length) return null;

  const LW = 42;
  const TW = 256;
  const CW = TW - LW;
  const CH = 52;
  const XH = 14;
  const TH = CH + XH;
  const PAD = 6;

  const values = data.map((d) => d.value);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;

  const toX = (i: number) =>
    LW + PAD + (i / Math.max(data.length - 1, 1)) * (CW - PAD * 2);
  const toY = (v: number) =>
    PAD + ((maxV - v) / range) * (CH - PAD * 2);

  const points = data.map((_, i) => `${toX(i).toFixed(1)},${toY(data[i].value).toFixed(1)}`);
  const firstX = parseFloat(points[0].split(",")[0]);
  const lastPt = points[points.length - 1];
  const lastX = parseFloat(lastPt.split(",")[0]);
  const fillPath = `M ${firstX},${CH - PAD} L ${points.join(" L ")} L ${lastX},${CH - PAD} Z`;

  const isPositive = data.length >= 2 && data[data.length - 1].value >= data[0].value;
  const stroke = isPositive ? "rgba(52,211,153,0.75)" : "rgba(248,113,113,0.75)";
  const fill = isPositive ? "rgba(52,211,153,0.08)" : "rgba(248,113,113,0.08)";

  const fmtVal = (v: number) =>
    v < 0.1 ? v.toFixed(4) : v < 1 ? v.toFixed(3) : v.toFixed(2);

  const uniqueYears = [...new Set(data.map((d) => d.date?.slice(0, 4) ?? ""))].sort();
  const step = Math.max(1, Math.ceil(uniqueYears.length / 5));
  const xLabels = uniqueYears
    .filter((_, i) => i % step === 0 || i === uniqueYears.length - 1)
    .map((yr) => {
      const idx = data.findIndex((d) => d.date?.startsWith(yr));
      return idx >= 0 ? { yr, x: toX(idx) } : null;
    })
    .filter((v): v is { yr: string; x: number } => v !== null);

  const [lx, ly] = lastPt.split(",").map(Number);

  return (
    <svg viewBox={`0 0 ${TW} ${TH}`} className="w-full" aria-hidden="true">
      <text x={LW - 4} y={toY(maxV) + 4} textAnchor="end" fontSize="7.5"
        fill="rgba(255,255,255,0.28)">{fmtVal(maxV)}</text>
      <text x={LW - 4} y={toY(minV) + 4} textAnchor="end" fontSize="7.5"
        fill="rgba(255,255,255,0.28)">{fmtVal(minV)}</text>

      <line x1={LW} y1={toY(maxV)} x2={TW - PAD} y2={toY(maxV)}
        stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="3 3" />
      <line x1={LW} y1={toY(minV)} x2={TW - PAD} y2={toY(minV)}
        stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="3 3" />

      <path d={fillPath} fill={fill} />
      <polyline points={points.join(" ")} fill="none" stroke={stroke}
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />

      <circle cx={lx} cy={ly} r="3" fill={stroke} />

      {xLabels.map(({ yr, x }) => (
        <text key={yr} x={x} y={TH - 2} textAnchor="middle" fontSize="7.5"
          fill="rgba(255,255,255,0.25)">{yr}</text>
      ))}
    </svg>
  );
}
