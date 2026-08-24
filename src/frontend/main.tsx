import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SessionCard } from "@/features/auth/SessionCard";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <main className="min-h-dvh bg-neutral-50 p-4 sm:p-8">
      <SessionCard initialToken="seed-refresh-token" />
    </main>
  </StrictMode>,
);
