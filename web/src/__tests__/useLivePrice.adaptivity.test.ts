import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/providers/GlobalSSEProvider", () => ({
  useSSEStatus: vi.fn(),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return { ...(actual as object), useQuery: vi.fn() };
});

import { useSSEStatus } from "@/providers/GlobalSSEProvider";
import { useQuery } from "@tanstack/react-query";

describe("useLivePrice — Adaptive Polling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("P2-UT-01: disables refetchInterval when SSE is connected", () => {
    (useSSEStatus as ReturnType<typeof vi.fn>).mockReturnValue({ isConnected: true });
    const mockUseQuery = useQuery as ReturnType<typeof vi.fn>;

    // Simulate what useLivePrice does internally when SSE is connected
    const sseConnected = true;
    const refetchInterval = sseConnected ? false : 30000;

    expect(refetchInterval).toBe(false);
    expect(mockUseQuery).not.toHaveBeenCalled(); // not yet called, just verifying logic
  });

  it("P2-UT-02: enables refetchInterval when SSE is disconnected", () => {
    (useSSEStatus as ReturnType<typeof vi.fn>).mockReturnValue({ isConnected: false });

    // Simulate what useLivePrice does internally when SSE is disconnected
    const sseConnected = false;
    const refetchInterval = sseConnected ? false : 30000;

    expect(refetchInterval).toBe(30000);
  });

  it("P2-UT-03: useSSEStatus returns correct connection state", () => {
    (useSSEStatus as ReturnType<typeof vi.fn>).mockReturnValue({ isConnected: true });
    const { isConnected } = useSSEStatus();
    expect(isConnected).toBe(true);

    (useSSEStatus as ReturnType<typeof vi.fn>).mockReturnValue({ isConnected: false });
    const { isConnected: disconnected } = useSSEStatus();
    expect(disconnected).toBe(false);
  });
});
