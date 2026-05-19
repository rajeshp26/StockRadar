"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserNav } from "@/components/user-nav";
import { ErrorBoundary } from "react-error-boundary";
import { Suspense } from "react";
import { Eye, PieChart } from "lucide-react";
import { cn } from "@/lib/utils";

/* ── Nav link definition ────────────────────────────────────── */
const NAV_LINKS = [
  { href: "/dashboard", label: "Watchlist", icon: Eye },
  { href: "/portfolio", label: "Portfolio", icon: PieChart },
] as const;

/* ── Skeleton for UserNav while loading ─────────────────────── */
function UserNavSkeleton() {
  return (
    <div className="h-8 w-8 animate-pulse rounded-full bg-white/10" />
  );
}

/* ── Header ─────────────────────────────────────────────────── */
export function Header() {
  const pathname = usePathname();

  return (
    <header
      className="glass-nav sticky top-0 z-50 w-full"
      role="navigation"
      aria-label="Main navigation"
    >
      <div className="mx-auto flex h-14 max-w-screen-2xl items-center justify-between px-4 md:px-8">

        {/* ── Left: Logo + Nav links ───────────────────────── */}
        <div className="flex items-center gap-8">

          {/* Logo */}
          <Link
            href="/dashboard"
            className="group flex items-center gap-2.5"
            aria-label="StockerPro — Back to Dashboard"
          >
            {/* Icon mark */}
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600/80 shadow-glow-indigo ring-1 ring-indigo-500/40 transition-all group-hover:bg-indigo-500/90 group-hover:ring-indigo-400/50">
              <svg
                viewBox="0 0 16 16"
                fill="none"
                className="h-4 w-4"
                aria-hidden="true"
              >
                {/* Simple upward trend line mark */}
                <polyline
                  points="2,12 6,7 9,9 14,3"
                  stroke="white"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="14" cy="3" r="1.5" fill="white" />
              </svg>
            </div>

            {/* Wordmark */}
            <span className="text-sm font-black tracking-tight text-white/90 transition-colors group-hover:text-white">
              StockerPro
            </span>
          </Link>

          {/* Desktop nav links */}
          <nav className="hidden items-center gap-1 md:flex" aria-label="Primary navigation">
            {NAV_LINKS.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + '/');
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "relative rounded-xl px-4 py-1.5 text-xs font-bold uppercase tracking-widest transition-all duration-200",
                    isActive
                      ? "bg-white/10 text-white shadow-sm"
                      : "text-white/40 hover:bg-white/5 hover:text-white/70",
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  <Icon className="mr-1.5 inline-block h-3.5 w-3.5" aria-hidden="true" />
                  {label}
                  {/* Active underline accent */}
                  {isActive && (
                    <span
                      className="absolute bottom-0.5 left-1/2 h-px w-4 -translate-x-1/2 rounded-full bg-indigo-400"
                      aria-hidden="true"
                    />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* ── Right: User nav ──────────────────────────────── */}
        <div className="flex items-center gap-3">
          <ErrorBoundary fallback={<div className="text-xs text-white/30">Menu unavailable</div>}>
            <Suspense fallback={<UserNavSkeleton />}>
              <UserNav />
            </Suspense>
          </ErrorBoundary>
        </div>

      </div>

      {/* Mobile nav strip */}
      <nav
        className="flex items-center gap-1 overflow-x-auto border-t border-white/5 px-4 pb-2 pt-1 no-scrollbar md:hidden"
        aria-label="Mobile navigation"
      >
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "rounded-lg px-4 py-1.5 text-[10px] font-black uppercase tracking-widest whitespace-nowrap transition-all",
                isActive
                  ? "bg-white/10 text-white"
                  : "text-white/40 hover:text-white/70",
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon className="mr-1 inline-block h-3 w-3" aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}