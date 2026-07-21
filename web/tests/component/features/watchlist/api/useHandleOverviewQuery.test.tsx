import { useHandleOverviewQuery } from "@features/watchlist";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("useHandleOverviewQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches the selected handle overview without a compatibility scope", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      requests.push(`${url.pathname}?${url.searchParams.toString()}`);
      return jsonResponse({
        ok: true,
        data: {
          query: { handle: "marionawfal", window: "7d" },
          metrics: {
            source_event_count: 0,
            resolved_token_count: 0,
            candidate_mention_count: 0,
            narrative_count: 0,
            last_source_event_at_ms: null,
          },
          resolved_token_clusters: [],
          candidate_mention_clusters: [],
          narrative_clusters: [],
          clusters_truncated: false,
          risk_notes: [],
        },
      });
    });

    renderHook(() => useHandleOverviewQuery({ handle: "marionawfal", token: "secret" }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(requests).toEqual(["/api/watchlist/handle/marionawfal/overview?"]));
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
