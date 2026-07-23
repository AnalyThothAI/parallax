import { useNewsPageWithToken } from "@features/news/useNewsPage";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { newsRowFixture } from "@tests/fixtures/newsFixture";
import { server } from "@tests/msw/server";
import { HttpResponse, http } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

describe("useNewsPage", () => {
  it("loads the exact source-backed news row contract", async () => {
    server.use(
      http.get(/.*\/api\/news$/, () =>
        HttpResponse.json({
          ok: true,
          data: { items: [newsRowFixture()], next_cursor: null },
        }),
      ),
    );

    const { result } = renderHook(() => useNewsPageWithToken("token"), { wrapper: wrapper() });

    await waitFor(() =>
      expect(result.current.data?.items[0].headline).toBe("BTC ETF flows expand"),
    );
    expect(result.current.data?.items[0].story.member_count).toBe(2);
    expect(result.current.data?.items[0].token_lanes[0]).toMatchObject({
      lane: "resolved",
      symbol: "BTC",
      target_id: "token:btc",
    });
  });

  it("requests only pagination, lifecycle, and search filters", async () => {
    let observedKeys: string[] = [];
    const observedParams: Record<string, string | null> = {};
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const searchParams = new URL(request.url).searchParams;
        observedKeys = [...searchParams.keys()].sort();
        for (const key of ["limit", "q", "status"]) {
          observedParams[key] = searchParams.get(key);
        }
        return HttpResponse.json({ ok: true, data: { items: [], next_cursor: null } });
      }),
    );

    renderHook(
      () =>
        useNewsPageWithToken("token", {
          q: "btc",
          status: "accepted",
        }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(observedParams.q).toBe("btc"));
    expect(observedParams).toEqual({ limit: "100", q: "btc", status: "accepted" });
    expect(observedKeys).toEqual(["limit", "q", "status"]);
  });

  it("clears previous filter rows while the next filter is loading", async () => {
    let releaseEth: (() => void) | null = null;
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const q = new URL(request.url).searchParams.get("q");
        if (q === "btc") {
          return HttpResponse.json({
            ok: true,
            data: { items: [newsRowFixture()], next_cursor: null },
          });
        }
        return new Promise((resolve) => {
          releaseEth = () =>
            resolve(
              HttpResponse.json({
                ok: true,
                data: {
                  items: [
                    newsRowFixture({
                      headline: "ETH source update",
                      news_item_id: "news-eth",
                      row_id: "row-eth",
                    }),
                  ],
                  next_cursor: null,
                },
              }),
            );
        });
      }),
    );

    const { result, rerender } = renderHook(
      ({ q }: { q: string }) => useNewsPageWithToken("token", { q }),
      { initialProps: { q: "btc" }, wrapper: wrapper() },
    );

    await waitFor(() =>
      expect(result.current.data?.items[0]?.headline).toBe("BTC ETF flows expand"),
    );

    rerender({ q: "eth" });

    await waitFor(() => expect(releaseEth).not.toBeNull());
    expect(result.current.data).toBeUndefined();

    await act(async () => {
      releaseEth?.();
    });
    await waitFor(() => expect(result.current.data?.items[0]?.headline).toBe("ETH source update"));
  });
});

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}
