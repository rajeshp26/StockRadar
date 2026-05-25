"use client";

import { useEffect, useRef, useState } from "react";
import { X, ArrowUp, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChat, type ChatMessage } from "@/hooks/use-chat";

interface ChatPanelProps {
  symbol: string;
  onClose: () => void;
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex gap-2.5",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {!isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 border border-indigo-500/30 mt-0.5">
          <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
          isUser
            ? "bg-indigo-500/25 border border-indigo-500/30 text-white/90 rounded-tr-md"
            : "glass-panel text-white/80 rounded-tl-md"
        )}
      >
        {message.content}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex gap-2.5">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 border border-indigo-500/30 mt-0.5">
        <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
      </div>
      <div className="glass-panel rounded-2xl rounded-tl-md px-4 py-3 flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-indigo-400/60 animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="h-2 w-2 rounded-full bg-indigo-400/60 animate-bounce" style={{ animationDelay: "200ms" }} />
        <span className="h-2 w-2 rounded-full bg-indigo-400/60 animate-bounce" style={{ animationDelay: "400ms" }} />
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 py-16">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-500/15 border border-indigo-500/25 mb-4">
        <Sparkles className="h-6 w-6 text-indigo-400" />
      </div>
      <p className="text-sm font-bold text-white/70 mb-1">Digital Twin</p>
      <p className="text-xs text-white/40 leading-relaxed max-w-[220px]">
        Ask me about valuation, financial health, or anything about this stock.
      </p>
    </div>
  );
}

export function ChatPanel({ symbol, onClose }: ChatPanelProps) {
  const { messages, streamingContent, isStreaming, error, send, clear } = useChat(symbol);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    send(input);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="w-96 max-h-[560px] glass-panel rounded-2xl shadow-glass-xl border border-glass-border-hi flex flex-col overflow-hidden animate-scale-in origin-bottom-right" style={{ background: 'hsl(222, 47%, 5%)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/20 border border-indigo-500/30">
            <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
          </div>
          <span className="text-sm font-bold text-white/80">
            Digital Twin · <span className="text-indigo-300">{symbol}</span>
          </span>
        </div>
        <div className="flex items-center gap-1">
          {hasMessages && (
            <button
              onClick={clear}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors text-[10px] font-bold uppercase tracking-wider"
              aria-label="Clear chat"
            >
              Clear
            </button>
          )}
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors"
            aria-label="Close chat"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto no-scrollbar px-4 py-3 space-y-3 min-h-[200px] max-h-[380px]">
        {!hasMessages && !isStreaming ? (
          <EmptyState />
        ) : (
          <>
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {isStreaming && streamingContent && (
              <MessageBubble message={{ role: "assistant", content: streamingContent }} />
            )}
            {isStreaming && !streamingContent && <TypingDots />}
            {error && !isStreaming && (
              <div className="text-xs text-rose-400/80 text-center py-2 px-3 rounded-xl bg-rose-500/10 border border-rose-500/20">
                {error}
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-white/[0.06] p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this stock..."
            rows={1}
            disabled={isStreaming}
            className="flex-1 glass-input rounded-xl px-3.5 py-2.5 text-[13px] resize-none max-h-24 disabled:opacity-40"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-500/80 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4 text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
