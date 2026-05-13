import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { createApiMock, ok, resetApiMock } from "../../../test/msw/fixtures";
import { apiHandlers } from "../../../test/msw/handlers";
import { server } from "../../../test/msw/server";

import { useSignalPulseCandidate } from "./useSignalPulseQueries";

const apiMock = createApiMock();

beforeEach(() => {
  resetApiMock(apiMock);
  server.use(...apiHandlers(apiMock));
});

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useSignalPulseCandidate", () => {
  it("calls /api/signal-lab/pulse/{id} with token", async () => {
    apiMock.getApiImpl = async () => ok({ candidate_id: "cand-1" });
    const { result } = renderHook(
      () => useSignalPulseCandidate({ token: "tok", candidateId: "cand-1" }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(apiMock.getApi).toHaveBeenCalledWith(
      "/api/signal-lab/pulse/cand-1",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("is disabled when candidateId is null", () => {
    renderHook(() => useSignalPulseCandidate({ token: "tok", candidateId: null }), {
      wrapper: wrapper(),
    });
    expect(apiMock.getApi).not.toHaveBeenCalled();
  });

  it("is disabled when token is empty", () => {
    renderHook(() => useSignalPulseCandidate({ token: "", candidateId: "cand-1" }), {
      wrapper: wrapper(),
    });
    expect(apiMock.getApi).not.toHaveBeenCalled();
  });
});
