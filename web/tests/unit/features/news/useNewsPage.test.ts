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
                ...requiredNewsRowSections(),
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
                }),
                token_lanes: [
                  {
                    lane: "resolved",
                    symbol: "BTC",
                    market_type: "cex",
                    resolution_status: "resolved",
                    target_id: "asset:btc",
                  },
                ],
                token_impacts: [],
                fact_lanes: [],
                agent_brief: { status: "pending" },
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
    expect(result.current.data?.items[0].agent_brief.status).toBe("pending");
    expect(result.current.data?.items[0].token_lanes[0]).toMatchObject({
      lane: "resolved",
      market_type: "cex",
      symbol: "BTC",
      target_id: "asset:btc",
    });
  });

  it("requests only hard-cut signal and search filters", async () => {
    const observedParams: Record<string, string | null> = {};
    let observedKeys: string[] = [];
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const searchParams = new URL(request.url).searchParams;
        observedKeys = [...searchParams.keys()].sort();
        ["signal", "q"].forEach((key) => {
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
          q: "btc",
        } as Parameters<typeof useNewsPageWithToken>[1] & { has_token: boolean }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(observedParams.q).toBe("btc"));
    expect(observedParams.signal).toBe("bullish");
    expect(observedParams.q).toBe("btc");
    expect(observedKeys).toEqual(["limit", "q", "signal"].sort());
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
                  ...requiredNewsRowSections(),
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
                  token_impacts: [],
                  token_lanes: [],
                  fact_lanes: [],
                  agent_brief: { status: "pending" },
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
                      ...requiredNewsRowSections(),
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
                      token_impacts: [],
                      token_lanes: [],
                      fact_lanes: [],
                      agent_brief: { status: "pending" },
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
    agent_signal: { status: "pending" },
    alert_eligibility: {
      in_app_eligible: true,
      external_push_ready: false,
      agent_status: "pending",
      market_scope: {
        scope: ["crypto"],
        primary: "crypto",
        status: "classified",
        reason: "market_scope_classified",
        basis: { subject: "crypto" },
        version: "news_market_scope_v1",
      },
    },
  };
}

function requiredNewsRowSections() {
  return {
    source_domain: "example.com",
    source: {
      source_domain: "example.com",
      provider_type: "opennews",
      source_role: "aggregator",
      trust_tier: "standard",
      coverage_tags: [],
      source_quality_status: "healthy",
    },
    content_tags: [],
    content_classification: {},
  };
}
