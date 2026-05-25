"use client";

import { useState } from "react";
import { Sparkles, X } from "lucide-react";
import { ChatPanel } from "./chat-panel";

interface AIChatBotProps {
  symbol: string;
}

export function AIChatBot({ symbol }: AIChatBotProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {open && (
        <ChatPanel symbol={symbol} onClose={() => setOpen(false)} />
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="w-14 h-14 rounded-full glass-panel flex items-center justify-center animate-pulse-glow shadow-glass-lg cursor-pointer hover:scale-105 transition-all duration-200 border border-indigo-500/30"
        aria-label={open ? "Close AI assistant" : "Open AI assistant"}
      >
        {open ? (
          <X className="w-6 h-6 text-white/80" />
        ) : (
          <Sparkles className="w-6 h-6 text-indigo-300" />
        )}
      </button>
    </div>
  );
}
