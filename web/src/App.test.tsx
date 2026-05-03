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
      window: "1h",
      scope: "all",
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
        return ok({ scope: options?.params?.scope, events: [], items: [] });
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
              market: {
                market_status: "missing",
                price: null,
                market_cap: null,
                snapshot_age_ms: null,
                snapshot_received_at_ms: null,
                price_change_window_pct: null,
                price_at_window_start: null,
                price_at_window_end: null,
                price_change_status: "missing_market"
              },
              flow: {
                window: "1h",
                window_start_ms: 1_777_746_000_000,
                window_end_ms: 1_777_746_300_000,
                mentions: 4,
                watched_mentions: 1,
                previous_mentions: 1,
                mention_delta: 3,
                mention_delta_pct: 3,
                z_score: null,
                stream_dominance: 0.25,
                baseline_status: "insufficient_history",
                baseline_sample_count: 0
              },
              sources: {
                unique_authors: 2,
                watched_authors: 1,
                weighted_reach: 169_125,
                top_author_share: 0.75,
                top_authors: [
                  { handle: "traderpow", count: 1, followers: 168_905, watched_count: 1 },
                  { handle: "alien19710628", count: 3, followers: 220, watched_count: 0 }
                ],
                source_quality_score: 25,
                source_quality_reasons: ["watched_evidence", "multi_author", "unresolved_symbol"]
              },
              fresh: {
                latest_evidence_age_ms: 290_000,
                first_seen_age_ms: 300_000,
                market_snapshot_age_ms: null,
                is_new_token: true,
                is_first_seen_by_watched: true
              },
              signal: {
                decision: "discard",
                score: 25,
                reasons: ["coverage_public_stream", "watched_evidence", "multi_author_flow"],
                risks: ["unresolved_symbol", "market_missing"],
                evidence_id: "event-upeg-1"
              },
              evidence_best: {
                event_id: "event-upeg-1",
                score: 35,
                handle: "traderpow",
                received_at_ms: 1_777_746_010_000,
                text: "$UPEG watched account evidence",
                url: "https://x.com/traderpow/status/1",
                reasons: ["watched_source"]
              },
              evidence: [
                {
                  event_id: "event-upeg-1",
                  score: 35,
                  handle: "traderpow",
                  received_at_ms: 1_777_746_010_000,
                  text: "$UPEG watched account evidence",
                  url: "https://x.com/traderpow/status/1",
                  reasons: ["watched_source"]
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
    const { container } = renderWithQuery(<App />);

    expect(await screen.findByText("MATCHED")).toBeInTheDocument();
    expect(await screen.findByText("7")).toBeInTheDocument();
    expect(await screen.findByText("MCap")).toBeInTheDocument();
    expect(await screen.findByText("Δ")).toBeInTheDocument();
    expect(await screen.findByText("Sources")).toBeInTheDocument();
    expect(await screen.findByText("Signal")).toBeInTheDocument();
    await screen.findByRole("button", { name: "select token $UPEG" });
    expect(container.querySelector(".direction.flat")?.textContent).toBe("-");
    expect(container.querySelector(".source-cell b")?.textContent).toBe("2 src");
    expect(container.querySelector(".source-cell small")?.textContent).toBe("1 watch / qual 25");
    expect(container.querySelector(".token-symbol > span")?.textContent).toBe("$UPEG");
    expect(container.querySelector(".token-symbol small")?.textContent).toBe("unknown · unresolved_symbol");
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

  it("uses all stream as the default token flow scope", async () => {
    renderWithQuery(<App />);

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/token-flow" && options?.params?.scope === "all"
        )
      ).toBe(true);
    });
  });

  it("applies scope changes to token flow reads", async () => {
    renderWithQuery(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "watched" }));

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/token-flow" && options?.params?.scope === "matched"
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
    expect(await screen.findByText("4 mentions (+3), 1/2 watched sources, market missing.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("$UPEG watched account evidence").length).toBeGreaterThan(0);
    });
    expect(await screen.findByText("traderpow x1")).toBeInTheDocument();
  });

  it("manual search clears stale token focus and owns the focus panel", async () => {
    renderWithQuery(<App />);

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "select token $UPEG" }));
    expect(await screen.findByText("4 mentions (+3), 1/2 watched sources, market missing.")).toBeInTheDocument();

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
