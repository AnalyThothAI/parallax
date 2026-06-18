import { useSignalLabCompactQuery } from "@features/signal-lab";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createApiMock, ok, resetApiMock } from "@tests/msw/fixtures";
import { apiHandlers } from "@tests/msw/handlers";
import { server } from "@tests/msw/server";
import { beforeEach, describe, expect, it } from "vitest";

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

describe("useSignalLabCompactQuery", () => {
  it("loads the 4h Signal Pulse window for the compact deck", async () => {
    apiMock.getApiImpl = async () =>
      ok({
        query: { window: "4h", scope: "all" },
        health: {},
        summary: {},
        items: [],
        returned_count: 0,
        has_more: false,
        next_cursor: null,
      });

    const { result } = renderHook(() => useSignalLabCompactQuery({ token: "tok" }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.overviewData).toBeDefined());
    expect(apiMock.getApi).toHaveBeenCalledWith(
      "/api/signal-lab/pulse",
      expect.objectContaining({
        token: "tok",
        params: expect.objectContaining({ window: "4h", scope: "all" }),
      }),
    );
    expect(apiMock.getApi).toHaveBeenCalledWith(
      "/api/signal-lab/pulse",
      expect.objectContaining({
        token: "tok",
        params: expect.objectContaining({
          window: "4h",
          scope: "all",
          limit: 80,
          sort: "recent",
        }),
      }),
    );
    expect(apiMock.getApi).toHaveBeenCalledWith(
      "/api/signal-lab/pulse",
      expect.objectContaining({
        token: "tok",
        params: expect.objectContaining({
          window: "4h",
          scope: "all",
          visibility: "hidden",
        }),
      }),
    );
  });
});
