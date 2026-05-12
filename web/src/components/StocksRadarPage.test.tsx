import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";

import { StocksRadarPage } from "./StocksRadarPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <StocksRadarPage token="secret" windowKey="1h" scope="all" />
    </QueryClientProvider>,
  );
}

describe("StocksRadarPage", () => {
  it("loads stocks radar rows and renders partial quote state", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({
      ok: true,
      data: {
        window: "1h",
        scope: "all",
        query: {
          window: "1h",
          scope: "all",
          limit: 48,
          window_start_ms: 1,
          window_end_ms: 2,
        },
        rows: [
          {
            target: {
              target_type: "MarketInstrument",
              target_id: "market_instrument:us_equity:AAPL",
              symbol: "AAPL",
              market: "us_equity",
              exchange: "NASDAQ",
              instrument_type: "equity",
              name: "Apple Inc. Common Stock",
            },
            attention: {
              mentions: 3,
              unique_authors: 2,
              watched_mentions: 1,
              latest_seen_ms: Date.now(),
            },
            latest_event: {
              event_id: "event-aapl",
              author_handle: "toly",
              text: "$AAPL breakout",
              received_at_ms: Date.now(),
            },
            quote: {
              status: "ready",
              price: 291.87,
              reference_close_price: 293.257,
              change_pct: -0.004729,
              asof: "2026-05-12T08:45:45+00:00",
              provider: "yahoo",
              provider_symbol: "AAPL",
              latency_class: "delayed_15m",
              freshness_class: "delayed_15m",
              error: null,
            },
            source_event_ids: ["event-aapl"],
            row_health: [],
          },
          {
            target: {
              target_type: "MarketInstrument",
              target_id: "market_instrument:us_equity:RKLB",
              symbol: "RKLB",
              market: "us_equity",
              exchange: "NASDAQ",
              instrument_type: "equity",
              name: "Rocket Lab USA, Inc.",
            },
            attention: {
              mentions: 1,
              unique_authors: 1,
              watched_mentions: 0,
              latest_seen_ms: Date.now(),
            },
            latest_event: {
              event_id: "event-rklb",
              author_handle: "elonmusk",
              text: "$RKLB launch cadence",
              received_at_ms: Date.now(),
            },
            quote: {
              status: "unavailable",
              price: null,
              reference_close_price: null,
              change_pct: null,
              asof: null,
              provider: null,
              provider_symbol: null,
              latency_class: null,
              freshness_class: null,
              error: "RuntimeError",
            },
            source_event_ids: ["event-rklb"],
            row_health: ["quote_unavailable"],
          },
        ],
        health: {
          returned_count: 2,
          quote_ready_count: 1,
          quote_unavailable_count: 1,
        },
      },
    } as any);

    renderPage();

    expect(await screen.findByRole("heading", { name: "US Stocks" })).toBeInTheDocument();
    expect(await screen.findByLabelText("stock AAPL")).toBeInTheDocument();
    expect(screen.getByLabelText("stock RKLB")).toBeInTheDocument();
    expect(screen.getByText("$291.87")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError")).toBeInTheDocument();

    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith(
        "/api/stocks-radar",
        expect.objectContaining({
          token: "secret",
          params: { window: "1h", scope: "all", limit: 48 },
        }),
      );
    });
  });
});
