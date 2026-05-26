import { useNewsPageWithToken } from "@features/news/useNewsPage";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { server } from "@tests/msw/server";
import { HttpResponse, http } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

describe("useNewsPage", () => {
  it("normalizes news rows from the hard-cut signal contract only", async () => {
    server.use(
      http.get(/.*\/api\/news$/, () =>
        HttpResponse.json({
          ok: true,
          data: {
            items: [
              {
                row_id: "row-1",
                news_item_id: "news-1",
                lifecycle_status: "processed",
                headline: "BTC headline",
                latest_at_ms: 1_779_000_000_000,
                signal: {
                  source: "provider",
                  status: "ready",
                  direction: "bullish",
                  label_zh: "利好",
                  score: 82,
                  grade: "A",
                },
                token_lanes: [
                  {
                    symbol: "BTC",
                    provider_score: 82,
                    provider_signal: "long",
                    provider_grade: "A",
                  },
                ],
                fact_lanes: [],
              },
            ],
            next_cursor: null,
          },
        }),
      ),
    );

    const { result } = renderHook(() => useNewsPageWithToken("token"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.data?.items[0].signal.label_zh).toBe("利好"));
    expect(result.current.data?.items[0].agent_brief).toBeUndefined();
    expect(result.current.data?.items[0].token_lanes[0].provider_score).toBe(82);
  });

  it("requests only hard-cut token, signal, score, and search filters", async () => {
    const observedParams: Record<string, string | null> = {};
    let observedKeys: string[] = [];
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const searchParams = new URL(request.url).searchParams;
        observedKeys = [...searchParams.keys()].sort();
        ["has_token", "signal", "min_score", "q"].forEach((key) => {
          observedParams[key] = searchParams.get(key);
        });
        return HttpResponse.json({ ok: true, data: { items: [], next_cursor: null } });
      }),
    );

    renderHook(
      () =>
        useNewsPageWithToken("token", {
          has_token: true,
          signal: "bullish",
          min_score: 70,
          q: "btc",
        }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(observedParams.q).toBe("btc"));
    expect(observedParams.has_token).toBe("true");
    expect(observedParams.signal).toBe("bullish");
    expect(observedParams.min_score).toBe("70");
    expect(observedParams.q).toBe("btc");
    expect(observedKeys).toEqual(["has_token", "limit", "min_score", "q", "signal"].sort());
  });
});

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}
