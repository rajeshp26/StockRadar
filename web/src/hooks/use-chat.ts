"use client";

import { useState, useRef, useCallback } from "react";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export function useChat(symbol: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const accumulatedRef = useRef("");

  messagesRef.current = messages;

  const send = useCallback(
    async (content: string) => {
      if (!content.trim() || isStreaming) return;

      setError(null);
      const userMsg: ChatMessage = { role: "user", content: content.trim() };
      const updatedMessages = [...messagesRef.current, userMsg];
      setMessages(updatedMessages);
      setIsStreaming(true);
      setStreamingContent("");
      accumulatedRef.current = "";

      const abortController = new AbortController();
      abortRef.current = abortController;

      try {
        const res = await fetch(
          `/api/proxy/valuations/${symbol}/chat`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              messages: updatedMessages.map((m) => ({
                role: m.role,
                content: m.content,
              })),
            }),
            signal: abortController.signal,
          }
        );

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(
            res.status === 503
              ? "AI assistant is not available right now."
              : `Request failed (${res.status})${text ? `: ${text}` : ""}`
          );
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) {
                const assistantContent = accumulatedRef.current;
                if (assistantContent) {
                  setMessages((prev) => [
                    ...prev,
                    { role: "assistant", content: assistantContent },
                  ]);
                }
                accumulatedRef.current = "";
                setStreamingContent("");
                setIsStreaming(false);
              } else if (data.token) {
                accumulatedRef.current += data.token;
                setStreamingContent(accumulatedRef.current);
              } else if (data.error) {
                setError(data.error);
                setIsStreaming(false);
              }
            } catch {
              // skip malformed JSON in SSE
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setIsStreaming(false);
          return;
        }
        const msg = err instanceof Error ? err.message : "Something went wrong";
        setError(msg);
        setIsStreaming(false);
      } finally {
        abortRef.current = null;
      }
    },
    [symbol, isStreaming]
  );

  const clear = useCallback(() => {
    setMessages([]);
    setStreamingContent("");
    accumulatedRef.current = "";
    setError(null);
    setIsStreaming(false);
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }, []);

  return {
    messages,
    streamingContent,
    isStreaming,
    error,
    send,
    clear,
  };
}
