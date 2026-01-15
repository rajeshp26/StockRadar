"use client";

import Link from "next/link";
import { UserNav } from "@/components/user-nav";
import { ErrorBoundary } from "react-error-boundary";
import { Suspense } from "react";

export function Header() {
  return (
    <header
      className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60"
      role="navigation"
      aria-label="Main navigation"
    >
      <div className="container flex h-14 items-center justify-between px-4 md:px-6">
        <Link
          href="/dashboard"
          className="flex items-center space-x-2"
          aria-label="StockerPro - Back to Dashboard"
        >
          {/* Future: Replace with Image component */}
          {/* <Image src="/logo.svg" alt="StockerPro" width={24} height={24} /> */}
          <span className="text-sm font-bold sm:text-base">StockerPro</span>
        </Link>
        <nav aria-label="User account menu">
          <ErrorBoundary fallback={<div>Menu unavailable</div>}>
            <Suspense
              fallback={
                <div className="h-10 w-10 animate-pulse rounded-full bg-gray-200" />
              }
            >
              <UserNav />
            </Suspense>
          </ErrorBoundary>
        </nav>
      </div>
    </header>
  );
}
