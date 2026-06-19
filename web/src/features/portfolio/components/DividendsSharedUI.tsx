"use client";
import type { ReactNode } from "react";

export function AccentLine() {
    return (
        <div
            className="pointer-events-none absolute inset-x-0 top-0 h-px z-10"
            style={{
                background:
                    "linear-gradient(90deg,transparent,rgba(99,102,241,0.5) 40%,rgba(139,92,246,0.3) 70%,transparent)",
            }}
            aria-hidden="true"
        />
    );
}

export function SectionHeader({
    title,
    subtitle,
}: {
    title: string;
    subtitle?: string;
}) {
    return (
        <div className="flex items-start justify-between gap-4 mb-6">
            <div>
                <h3 className="text-lg font-black text-white tracking-tight">{title}</h3>
                {subtitle && (
                    <p className="text-xs text-white/35 mt-1">{subtitle}</p>
                )}
            </div>
        </div>
    );
}
