import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { App } from "./App";
import type { ApiResponse, BootstrapData, StatusData } from "./api/types";
import { getApi, getBootstrap } from "./api/client";
import { useTraderStore } from "./store/useTraderStore";

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return {
    ...actual,
    getApi: vi.fn(),
    getBootstrap: vi.fn()
  };
});

vi.mock("./api/useIntelSocket", () => ({
  useIntelSocket: () => ({
    status: "connected",
    events: [],
    lastMessageAt: 1_777_770_000_000
  })
}));

const mockedGetApi = vi.mocked(getApi);
const mockedGetBootstrap = vi.mocked(getBootstrap);

const statusData: StatusData = {
  ok: true,
  reasons: [],
  handles: ["toly", "traderpow"],
  store: "/root/.gmgn-twitter-intel/twitter_intel.sqlite3",
  collector: {
    started_at_ms: 1_777_770_000_000,
    frames_received: 88,
    twitter_events: 44,
    matched_twitter_events: 7,
    events_published: 7,
    duplicate_twitter_events: 2,
    duplicate_matched_twitter_events: 0,
    parse_errors: 0,
    last_frame_at_ms: 1_777_770_100_000,
    last_event_at_ms: 1_777_770_100_000,
    last_matched_event_at_ms: 1_777_770_090_000
  },
  enrichment: {
    llm_configured: false,
    worker_running: false,
    job_counts: { pending: 3, running: 0, failed: 0, dead: 0, done: 1 }
  }
};

describe("App cockpit value flow", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockedGetApi.mockReset();
    mockedGetBootstrap.mockReset();
    useTraderStore.setState({
      token: "",
      window: "5m",
      scope: "matched",
      handles: "",
      search: "$PEPE",
      submittedSearch: "$PEPE"
    });

    mockedGetBootstrap.mockResolvedValue(
      ok({
        ws_token: "secret",
        handles: ["toly", "traderpow"],
        replay_limit: 100
      })
    );
    mockedGetApi.mockImplementation(async (path, options) => {
      if (path === "/api/status") {
        return ok(statusData);
      }
      if (path === "/api/recent") {
        return ok({ scope: "matched", events: [], items: [] });
      }
      if (path === "/api/token-flow") {
        return ok({
              window: options?.params?.window,
          items: [
            {
              identity: {
                identity_key: "symbol:UPEG",
                identity_status: "unresolved_symbol",
                token_id: null,
                chain: null,
                address: null,
                symbol: "UPEG"
              },
              social: {
                window: "5m",
                window_start_ms: 1_777_746_000_000,
                window_end_ms: 1_777_746_300_000,
                mention_count: 4,
                watched_mention_count: 1,
                unique_author_count: 2,
                market_mindshare: 0.25,
                watched_mindshare: 1,
                velocity: 0.8,
                top_authors: [
                  { handle: "traderpow", count: 1, followers: 168_905 },
                  { handle: "alien19710628", count: 3, followers: 220 }
                ]
              },
              baseline: {
                baseline_status: "insufficient_history",
                sample_count: 0,
                baseline_mean: null,
                baseline_stddev: null,
                delta_pct: null,
                z_score: null,
                percentile: null,
                acceleration: null
              },
              anomaly: {
                score: 58,
                reasons: ["watched_first_mention", "market_data_missing", "symbol_unresolved"]
              },
              market: {
                market_status: "missing",
                market_confirmed: false,
                price: null,
                previous_price: null,
                price_change_pct: null,
                market_cap: null,
                snapshot_age_ms: null,
                snapshot_received_at_ms: null
              },
              confidence: {
                score: 25,
                coverage: "public_stream",
                coverage_boundary: "GMGN anonymous public stream; not a full X firehose",
                identity_status: "unresolved_symbol",
                market_status: "missing",
                baseline_status: "insufficient_history",
                reasons: ["coverage public_stream", "watched evidence", "multi-author evidence", "insufficient baseline", "unresolved_symbol"]
              },
              evidence: [
                {
                  event_id: "event-upeg-1",
                  author_handle: "traderpow",
                  received_at_ms: 1_777_746_010_000,
                  text_clean: "$UPEG watched account evidence",
                  canonical_url: "https://x.com/traderpow/status/1"
                }
              ]
            }
          ]
        });
      }
      if (path === "/api/account-alerts") {
        return ok({
          window: options?.params?.window,
          alert_type: null,
          items: [
            {
              alert_type: "account_token",
              event_id: "event-upeg-1",
              author_handle: "traderpow",
              entity_key: "symbol:UPEG",
              normalized_value: "UPEG",
              received_at_ms: 1_777_746_010_000,
              is_first_seen_global: 0,
              is_first_seen_by_author: 1
            }
          ]
        });
      }
      if (path === "/api/narrative-flow") {
        return ok({ window: options?.params?.window, items: [] });
      }
      if (path === "/api/enrichment-jobs") {
        return ok({ items: [], counts: { pending: 3, running: 0, failed: 0, dead: 0, done: 1 } });
      }
      if (path === "/api/search") {
        const query = String(options?.params?.q ?? "");
        if (query === "@traderpow") {
          return ok({
            query: { kind: "handle", text: query, scope: "all", handle: "traderpow" },
            result_count: 2,
            items: [
              {
                match_type: "handle",
                score: 100,
                event: {
                  event_id: "event-traderpow-1",
                  canonical_url: "https://x.com/traderpow/status/2",
                  author_handle: "traderpow",
                  received_at_ms: 1_777_746_100_000,
                  text_clean: "Some people forgot how to dream",
                  is_watched: 1
                }
              },
              {
                match_type: "handle",
                score: 100,
                event: {
                  event_id: "event-traderpow-2",
                  canonical_url: "https://x.com/traderpow/status/3",
                  author_handle: "traderpow",
                  received_at_ms: 1_777_746_200_000,
                  text_clean: "EXODIA",
                  is_watched: 1
                }
              }
            ]
          });
        }
        return ok({
          query: { kind: "symbol", text: query, scope: "all", symbol: "UPEG" },
          result_count: 1,
          items: [
            {
              match_type: "exact_symbol",
              score: 90,
              event: {
                event_id: "event-upeg-1",
                canonical_url: "https://x.com/traderpow/status/1",
                author_handle: "traderpow",
                received_at_ms: 1_777_746_010_000,
                text_clean: "$UPEG watched account evidence",
                cashtags: ["UPEG"],
                is_watched: 1
              }
            }
          ]
        });
      }
      throw new Error(`unexpected path ${path}`);
    });
  });

  it("renders current collector matched count from the backend contract", async () => {
    renderWithQuery(<App />);

    expect(await screen.findByText("MATCHED")).toBeInTheDocument();
    expect(await screen.findByText("7")).toBeInTheDocument();
  });

  it("keeps watched-account alerts on the 24h decision window", async () => {
    renderWithQuery(<App />);

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/account-alerts" && options?.params?.window === "24h"
        )
      ).toBe(true);
    });
  });

  it("turns token flow clicks into evidence-focused search", async () => {
    renderWithQuery(<App />);

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    expect(tokenPanel).not.toBeNull();
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "select token $UPEG" }));

    expect(await screen.findByDisplayValue("$UPEG")).toBeInTheDocument();
    expect(await screen.findByText("焦点证据")).toBeInTheDocument();
    expect(await screen.findByText("25% market mindshare, 1 watched / 4 total mentions across 2 accounts.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("$UPEG watched account evidence").length).toBeGreaterThan(0);
    });
    expect(await screen.findByText("traderpow x1")).toBeInTheDocument();
  });

  it("manual search clears stale token focus and owns the focus panel", async () => {
    renderWithQuery(<App />);

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "select token $UPEG" }));
    expect(await screen.findByText("25% market mindshare, 1 watched / 4 total mentions across 2 accounts.")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("搜索 CA / $TOKEN / @handle / 文本"), { target: { value: "@traderpow" } });
    fireEvent.click(screen.getByRole("button", { name: "检索" }));

    const focusPanel = screen.getByText("焦点证据").closest("section");
    expect(focusPanel).not.toBeNull();
    expect(await within(focusPanel!).findByText("search query")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(focusPanel!).getAllByText("@traderpow").length).toBeGreaterThan(0);
    });
    expect(await within(focusPanel!).findByText("2 evidence hits for @traderpow. Exact CA, symbol, and handle matches are ranked before FTS text.")).toBeInTheDocument();
    expect(within(focusPanel!).queryByText("$UPEG")).not.toBeInTheDocument();
  });
});

function renderWithQuery(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0
      }
    }
  });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

function ok<T>(data: T): ApiResponse<T> {
  return { ok: true, data };
}
