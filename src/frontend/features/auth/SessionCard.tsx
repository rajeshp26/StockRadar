import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { refreshSession, type RefreshResult } from "./client";

// Consumes contract API-004. The contract is the source of truth for the request and
// response shape; this component never redeclares those types.
export function SessionCard({ initialToken }: { initialToken: string }) {
  const [state, setState] = useState<"idle" | "pending" | "ok" | "error">("idle");
  const [result, setResult] = useState<RefreshResult | null>(null);

  async function onRefresh() {
    setState("pending");
    try {
      const r = await refreshSession({ refresh_token: initialToken });
      setResult(r);
      setState("ok");
    } catch {
      setState("error");
    }
  }

  return (
    <section
      data-testid="session-card"
      className="mx-auto flex w-full max-w-md flex-col gap-4 rounded-lg border border-neutral-200 bg-white p-6 shadow-sm"
    >
      <header className="flex items-center gap-2">
        <ShieldCheck aria-hidden className="size-5 text-emerald-600" />
        <h2 className="text-base font-semibold text-neutral-900">Session</h2>
      </header>

      <p className="text-sm text-neutral-600">
        Refresh the access token without signing in again.
      </p>

      <Button
        data-testid="refresh-button"
        onClick={onRefresh}
        disabled={state === "pending"}
        className="w-full sm:w-auto sm:self-start"
      >
        <RefreshCw
          aria-hidden
          className={cn("size-4", state === "pending" && "animate-spin")}
        />
        {state === "pending" ? "Refreshing…" : "Refresh session"}
      </Button>

      <AnimatePresence mode="wait">
        {state === "ok" && result && (
          <motion.output
            key="ok"
            data-testid="refresh-success"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
          >
            Token refreshed. Expires in {result.expires_in}s.
          </motion.output>
        )}
        {state === "error" && (
          <motion.output
            key="err"
            data-testid="refresh-error"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-900"
          >
            <TriangleAlert aria-hidden className="size-4" />
            Could not refresh the session.
          </motion.output>
        )}
      </AnimatePresence>
    </section>
  );
}
