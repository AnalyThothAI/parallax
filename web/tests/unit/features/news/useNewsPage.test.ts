import { useNewsPageWithToken } from "@features/news/useNewsPage";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
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
                signal: newsSignalEnvelope({
                  source: "provider",
                  status: "ready",
                  direction: "bullish",
                  label_zh: "利好",
                  score: 82,
                  grade: "A",
                }),
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

    await waitFor(() =>
      expect(result.current.data?.items[0].signal.display_signal.label_zh).toBe("利好"),
    );
    expect(result.current.data?.items[0].agent_brief).toBeUndefined();
    expect(result.current.data?.items[0].token_lanes[0].provider_score).toBe(82);
  });

  it("requests only hard-cut signal, score, and search filters", async () => {
    const observedParams: Record<string, string | null> = {};
    let observedKeys: string[] = [];
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const searchParams = new URL(request.url).searchParams;
        observedKeys = [...searchParams.keys()].sort();
        ["signal", "min_score", "q"].forEach((key) => {
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
        } as Parameters<typeof useNewsPageWithToken>[1] & { has_token: boolean }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(observedParams.q).toBe("btc"));
    expect(observedParams.signal).toBe("bullish");
    expect(observedParams.min_score).toBe("70");
    expect(observedParams.q).toBe("btc");
    expect(observedKeys).toEqual(["limit", "min_score", "q", "signal"].sort());
  });

  it("clears previous filter rows while the next filter is loading", async () => {
    let releaseEth: (() => void) | null = null;
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const q = new URL(request.url).searchParams.get("q");
        if (q === "btc") {
          return HttpResponse.json({
            ok: true,
            data: {
              items: [
                {
                  row_id: "row-btc",
                  news_item_id: "news-btc",
                  lifecycle_status: "processed",
                  headline: "BTC headline",
                  latest_at_ms: 1_779_000_000_000,
                  signal: newsSignalEnvelope({
                    source: "provider",
                    status: "ready",
                    direction: "bullish",
                  }),
                  token_lanes: [],
                  fact_lanes: [],
                },
              ],
              next_cursor: null,
            },
          });
        }
        return new Promise((resolve) => {
          releaseEth = () =>
            resolve(
              HttpResponse.json({
                ok: true,
                data: {
                  items: [
                    {
                      row_id: "row-eth",
                      news_item_id: "news-eth",
                      lifecycle_status: "processed",
                      headline: "ETH headline",
                      latest_at_ms: 1_779_000_000_100,
                      signal: newsSignalEnvelope({
                        source: "provider",
                        status: "ready",
                        direction: "bearish",
                      }),
                      token_lanes: [],
                      fact_lanes: [],
                    },
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

    await waitFor(() => expect(result.current.data?.items[0]?.headline).toBe("BTC headline"));

    rerender({ q: "eth" });

    await waitFor(() => expect(releaseEth).not.toBeNull());
    expect(result.current.data).toBeUndefined();

    await act(async () => {
      releaseEth?.();
    });
    await waitFor(() => expect(result.current.data?.items[0]?.headline).toBe("ETH headline"));
  });
});

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

function newsSignalEnvelope(displaySignal: Record<string, unknown>) {
  return {
    display_signal: displaySignal,
    provider_signal: displaySignal.source === "provider" ? displaySignal : null,
    agent_signal: { status: "pending" },
    alert_eligibility: {
      in_app_eligible: true,
      external_push_ready: false,
      agent_status: "pending",
      provider_score: displaySignal.score,
    },
  };
}
