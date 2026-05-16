import { useWatchlistHandlesOverviewQuery } from "@features/watchlist";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("useWatchlistHandlesOverviewQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches configured handle overview rows", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      requests.push(url.pathname);
      return jsonResponse({
        ok: true,
        data: { window: "7d", items: [] },
      });
    });

    renderHook(() => useWatchlistHandlesOverviewQuery({ token: "secret" }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(requests).toEqual(["/api/watchlist/handles/overview"]));
  });
});

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
