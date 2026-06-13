"use client";
import { cn } from "@/lib/utils";

const G = "#1D9E75";
const A = "#EF9F27";
const R = "#E24B4A";
const TRACK = "#B4B2A9";

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function valueToAngle(value: number, min: number, max: number): number {
  const range = Math.max(max - min, 1);
  const clamped = Math.max(min, Math.min(max, value));
  return 180 + ((clamped - min) / range) * 180;
}

function describeArc(cx: number, cy: number, r: number, fromAngle: number, toAngle: number): string {
  const start = polarToCartesian(cx, cy, r, fromAngle);
  const end = polarToCartesian(cx, cy, r, toAngle);
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function fmt(v: number): string {
  return v.toFixed(1);
}

function getValuation(current: number, avg: number): { label: string; className: string } {
  if (current < avg * 0.85) {
    return {
      label: "Undervalued",
      className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
    };
  }
  if (current > avg * 1.25) {
    return {
      label: "Overvalued",
      className: "bg-rose-500/15 text-rose-400 border-rose-500/25",
    };
  }
  return {
    label: "Fairly valued",
    className: "bg-amber-500/15 text-amber-400 border-amber-500/25",
  };
}

interface StatPillProps {
  label: string;
  value: string;
  highlighted: boolean;
}

function StatPill({ label, value, highlighted }: StatPillProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center px-3 py-1.5 rounded-lg min-w-[52px] transition-colors",
        highlighted
          ? "bg-white/[0.10] border border-white/20"
          : "bg-white/[0.04] border border-white/[0.08]",
      )}
    >
      <span className="text-[10px] text-white/40 font-medium uppercase tracking-wider leading-none mb-0.5">
        {label}
      </span>
      <span
        className={cn(
          "text-[13px] font-semibold tabular-nums leading-none",
          highlighted ? "text-white" : "text-white/70",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export interface PERatioGaugeProps {
  current: number;
  min: number;
  max: number;
  avg: number;
  ticker?: string;
}

export function PERatioGauge({ current, min, max, avg }: PERatioGaugeProps) {
  const cx = 120;
  const cy = 112;
  const r = 86;
  const range = Math.max(max - min, 1);

  const threshold = avg * 1.5;
  const greenEndVal = Math.min(avg, max);
  const amberEndVal = Math.min(threshold, max);
  const redStartVal = Math.max(threshold, min);

  const minAngle = valueToAngle(min, min, max);
  const maxAngle = valueToAngle(max, min, max);
  const greenEndAngle = valueToAngle(greenEndVal, min, max);
  const amberEndAngle = valueToAngle(amberEndVal, min, max);
  const redStartAngle = valueToAngle(redStartVal, min, max);
  const currentAngle = valueToAngle(current, min, max);

  const hasGreen = greenEndVal > min && range > 0;
  const hasAmber = amberEndVal > greenEndVal && range > 0;
  const hasRed = max > redStartVal && range > 0;

  const needleEnd = polarToCartesian(cx, cy, r, currentAngle);

  const valuation = getValuation(current, avg);

  return (
    <div className="mb-3">
      <div className="relative mx-auto" style={{ width: 240, height: 150 }}>
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 240 150"
          aria-label={`P/E Ratio Gauge: ${fmt(current)}`}
        >
          <path
            d={describeArc(cx, cy, r, minAngle, maxAngle)}
            fill="none"
            stroke={TRACK}
            strokeWidth="10"
            strokeLinecap="butt"
          />

          {hasGreen && (
            <path
              d={describeArc(cx, cy, r, minAngle, greenEndAngle)}
              fill="none"
              stroke={G}
              strokeWidth="10"
              strokeLinecap="butt"
            />
          )}

          {hasAmber && (
            <path
              d={describeArc(cx, cy, r, greenEndAngle, amberEndAngle)}
              fill="none"
              stroke={A}
              strokeWidth="10"
              strokeLinecap="butt"
            />
          )}

          {hasRed && (
            <path
              d={describeArc(cx, cy, r, redStartAngle, maxAngle)}
              fill="none"
              stroke={R}
              strokeWidth="10"
              strokeLinecap="butt"
            />
          )}

          <line
            x1={cx}
            y1={cy}
            x2={needleEnd.x}
            y2={needleEnd.y}
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <circle cx={cx} cy={cy} r="3.5" fill="white" />
          <circle cx={needleEnd.x} cy={needleEnd.y} r="3.5" fill="white" />

          <text
            x={cx}
            y={cy + 12}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="white"
            fontSize="28"
            fontWeight="900"
            fontFamily="inherit"
          >
            {fmt(current)}
          </text>
          <text
            x={cx}
            y={cy + 34}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="rgba(255,255,255,0.4)"
            fontSize="10"
            fontWeight="700"
            fontFamily="inherit"
            letterSpacing="1.5"
          >
            P/E Ratio
          </text>
        </svg>
      </div>

      <div className="flex items-center justify-center gap-2 mt-1">
        <StatPill label="Min" value={fmt(min)} highlighted={false} />
        <StatPill label="Avg" value={fmt(avg)} highlighted={false} />
        <StatPill label="Max" value={fmt(max)} highlighted={false} />
        <StatPill label="Current" value={fmt(current)} highlighted={true} />
      </div>

      <div className="flex justify-center mt-2.5">
        <span
          className={cn(
            "text-[11px] font-semibold uppercase tracking-wide px-3 py-0.5 rounded-full border",
            valuation.className,
          )}
        >
          {valuation.label}
        </span>
      </div>
    </div>
  );
}
