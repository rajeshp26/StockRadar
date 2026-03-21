'use client';

import { useAuth } from "@/providers/auth-provider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Header } from "@/components/header";
import { GlobalSSEProvider } from "@/providers/GlobalSSEProvider";

/* ── Full-page glass loading spinner ───────────────────────── */
function FullPageSpinner() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="relative flex items-center justify-center">
        {/* Outer ring */}
        <div className="h-16 w-16 rounded-full border border-white/10" />
        {/* Spinning arc */}
        <div className="absolute h-16 w-16 animate-spin rounded-full border-t-2 border-indigo-500" />
        {/* Inner dot */}
        <div className="absolute h-3 w-3 rounded-full bg-indigo-500/60 animate-pulse-glow" />
      </div>
    </div>
  );
}

/* ── Authenticated shell ────────────────────────────────────── */
export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === 'unauthenticated' || status === 'error') {
      router.push('/login');
    }
  }, [status, router]);

  if (
    status === 'initializing' ||
    status === 'unauthenticated' ||
    status === 'error'
  ) {
    return <FullPageSpinner />;
  }

  if (status === 'authenticated') {
    return (
      /*
        Shell structure:
        - Header is sticky glass nav
        - main gets top padding to clear the header
        - max-w-screen-2xl centers content on very wide displays
      */
      <GlobalSSEProvider>
      <div className="relative flex min-h-screen flex-col">
        <Header />
        <main className="flex-1 px-4 pb-12 pt-6 md:px-8 md:pt-8">
          <div className="mx-auto w-full max-w-screen-2xl">
            {children}
          </div>
        </main>
      </div>
      </GlobalSSEProvider>
    );
  }

  return null;
}