import * as client from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";


import { useSignalPulseCandidate } from "./useSignalPulseQueries";

beforeEach(() => {
  vi.restoreAllMocks();
});

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useSignalPulseCandidate", () => {
  it("calls /api/signal-lab/pulse/{id} with token", async () => {
    const getApi = vi
      .spyOn(client, "getApi")
      .mockResolvedValue({ ok: true, data: { candidate_id: "cand-1" } } as any);
    const { result } = renderHook(
      () => useSignalPulseCandidate({ token: "tok", candidateId: "cand-1" }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getApi).toHaveBeenCalledWith(
      "/api/signal-lab/pulse/cand-1",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("is disabled when candidateId is null", () => {
    const getApi = vi.spyOn(client, "getApi");
    renderHook(() => useSignalPulseCandidate({ token: "tok", candidateId: null }), {
      wrapper: wrapper(),
    });
    expect(getApi).not.toHaveBeenCalled();
  });

  it("is disabled when token is empty", () => {
    const getApi = vi.spyOn(client, "getApi");
    renderHook(() => useSignalPulseCandidate({ token: "", candidateId: "cand-1" }), {
      wrapper: wrapper(),
    });
    expect(getApi).not.toHaveBeenCalled();
  });
});
