import { useHandleTimelineQuery } from "@features/watchlist";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("useHandleTimelineQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("passes the server next_cursor into the next page request", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      requests.push(`${url.pathname}?${url.searchParams.toString()}`);
      const cursor = url.searchParams.get("cursor");
      return jsonResponse({
        ok: true,
        data: {
          query: { handle: "toly", limit: 30 },
          items: [timelineItem(cursor ? "event-2" : "event-1", cursor ? 900 : 1_000)],
          has_more: !cursor,
          next_cursor: cursor ? null : "cursor-1",
        },
      });
    });

    const { result } = renderHook(
      () => useHandleTimelineQuery({ handle: "toly", limit: 30, token: "secret" }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.data).toBeDefined(), { timeout: 1_000 });
    expect((result.current.data as any).pages[0].data.next_cursor).toBe("cursor-1");
    await result.current.fetchNextPage();

    expect(requests).toEqual([
      "/api/watchlist/handle/toly/timeline?limit=30",
      "/api/watchlist/handle/toly/timeline?cursor=cursor-1&limit=30",
    ]);
  });
});

function timelineItem(eventId: string, receivedAtMs: number) {
  return {
    event_id: eventId,
    received_at_ms: receivedAtMs,
    author_handle: "toly",
    action: "tweet",
    text_clean: "source event",
    canonical_url: `https://x.com/toly/status/${eventId}`,
    cashtags: [],
    hashtags: [],
    mentions: [],
    event: { event_id: eventId },
    token_resolutions: [],
  };
}

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
