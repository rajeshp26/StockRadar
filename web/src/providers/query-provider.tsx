// web/src/providers/query-provider.tsx
"use client";
import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { makeQueryClient } from "@/lib/query-client";

interface Props {
  children: React.ReactNode;
}

/**
 * ReactQueryProvider
 *
 * Wraps the entire app with a single shared QueryClient.
 *
 * Why useState and not a module-level singleton?
 * In Next.js App Router with React Server Components, a module-level
 * singleton would be shared across requests on the server, leaking
 * data between users. useState runs once per client mount — safe.
 *
 * Placement: must be the outermost provider so that all hooks
 * (including those inside FirebaseClientProvider and AuthProvider)
 * can call useQueryClient().
 */
export function ReactQueryProvider({ children }: Props) {
  const [queryClient] = useState(() => makeQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}