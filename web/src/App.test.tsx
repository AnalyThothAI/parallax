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
    job_counts: { pending: 3, running: 0, failed: 0, dead: 2, done: 1 }
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
                identity_key: "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                identity_status: "resolved_ca",
                token_id: "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                chain: "eth",
                address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                symbol: "UPEG"
              },
              market: {
                market_status: "fresh",
                price: 0.001,
                market_cap: 60490,
                snapshot_age_ms: 120_000,
                snapshot_received_at_ms: null,
                price_change_window_pct: null,
                price_at_window_start: null,
                price_at_window_end: null,
                price_change_status: "insufficient_history"
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
                new_burst_score: 4,
                stream_dominance: 0.25,
                baseline_status: "insufficient_history",
                baseline_sample_count: 0
              },
              baseline: {
                baseline_status: "insufficient_history",
                sample_count: 0,
                zero_slot_count: 0,
                ewma_mean: null,
                ewma_stddev: null,
                simple_mean: null,
                z_score: null,
                new_burst_score: 4
              },
              diffusion: {
                score: 70,
                status: "concentrated",
                independent_authors: 2,
                effective_authors: 2,
                top_author_share: 0.75,
                duplicate_text_share: 0.25,
                repeated_cluster_count: 0,
                shill_author_count: 0,
                top_authors: [
                  { handle: "traderpow", count: 1, followers: 168_905, watched_count: 1 },
                  { handle: "alien19710628", count: 3, followers: 220, watched_count: 0 }
                ],
                reasons: ["multi_author", "watched_author_present"],
                risks: ["author_concentration_high"]
              },
              watch: {
                status: "direct_watch",
                direct_mentions: 1,
                direct_authors: 1,
                seed_link_count: 1,
                top_seed: null,
                reasons: ["watched_direct_mention"],
                risks: []
              },
              fresh: {
                latest_evidence_age_ms: 290_000,
                first_seen_age_ms: 300_000,
                market_snapshot_age_ms: 120_000,
                is_new_local_evidence: true,
                is_first_seen_by_watched: true
              },
              signal: {
                score_version: "token_signal_v1",
                decision: "watch",
                score: 55,
                reasons: ["coverage_public_stream", "watched_evidence", "multi_author_flow"],
                risks: ["author_concentration_high"],
                contributions: [{ feature: "diffusion_health", value: 55, reason: "concentrated" }],
                risk_caps: [{ risk: "author_concentration_high", cap: 65 }],
                evidence_id: "event-upeg-1"
              },
              evidence_highlight_best: {
                event_id: "event-upeg-1",
                evidence_type: "gmgn_token_payload",
                score: 80,
                score_version: "post_score_v1",
                handle: "traderpow",
                received_at_ms: 1_777_746_010_000,
                text: "$UPEG watched account evidence",
                url: "https://x.com/traderpow/status/1",
                reasons: ["watched_source"],
                risks: [],
                contributions: [{ feature: "source_trust", value: 16, reason: "watched_source" }],
                risk_caps: []
              },
              evidence_highlights: [
                {
                  event_id: "event-upeg-1",
                  evidence_type: "gmgn_token_payload",
                  score: 80,
                  score_version: "post_score_v1",
                  handle: "traderpow",
                  received_at_ms: 1_777_746_010_000,
                  text: "$UPEG watched account evidence",
                  url: "https://x.com/traderpow/status/1",
                  reasons: ["watched_source"],
                  risks: [],
                  contributions: [{ feature: "source_trust", value: 16, reason: "watched_source" }],
                  risk_caps: []
                }
              ],
              evidence_total_count: 4,
              posts_query: {
                token_id: "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                chain: "eth",
                address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                window: "1h",
                scope: "all"
              }
            }
          ]
        });
      }
      if (path === "/api/token-posts") {
        const cursor = String(options?.params?.cursor ?? "");
        const baseItem = {
          handle: "traderpow",
          mention_source: "gmgn_token_payload",
          attribution_status: "direct",
          attribution_confidence: 1,
          attribution_weight: 1,
          score: 82,
          score_version: "post_score_v1",
          reasons: ["structured_token_payload"],
          risks: [],
          contributions: [{ feature: "source_specificity", value: 18, reason: "structured_token_payload" }],
          risk_caps: []
        };
        if (cursor === "cursor-2") {
          return ok({
            query: options?.params,
            total_count: 4,
            returned_count: 1,
            has_more: false,
            next_cursor: null,
            items: [
              {
                ...baseItem,
                event_id: "event-upeg-4",
                received_at_ms: 1_777_746_007_000,
                text: "$UPEG final public post",
                url: "https://x.com/traderpow/status/4"
              }
            ]
          });
        }
        return ok({
          query: options?.params,
          total_count: 4,
          returned_count: 3,
          has_more: true,
          next_cursor: "cursor-2",
          items: [
            {
              ...baseItem,
              event_id: "event-upeg-1",
              received_at_ms: 1_777_746_010_000,
              text: "$UPEG watched account evidence",
              url: "https://x.com/traderpow/status/1"
            },
            {
              ...baseItem,
              handle: "alien19710628",
              event_id: "event-upeg-2",
              received_at_ms: 1_777_746_009_000,
              text: "$UPEG public follow-through",
              url: "https://x.com/alien19710628/status/2"
            },
            {
              ...baseItem,
              handle: "alien19710628",
              event_id: "event-upeg-3",
              received_at_ms: 1_777_746_008_000,
              text: "$UPEG another public post",
              url: "https://x.com/alien19710628/status/3"
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
              token_resolution_status: "unresolved_symbol",
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
	      if (path === "/api/attention-frontier") {
	        return ok({
	          window: options?.params?.window,
	          items: [
	            {
	              seed: {
	                seed_id: "seed-1",
	                narrative_label: "ai_agent_grok",
	                author_handle: "traderpow",
	                evidence: "Grok is getting scary good",
	                summary: "watched account seed",
	                received_at_ms: 1_777_746_000_000
	              },
	              link: {
	                identity: {
	                  identity_key: "symbol:GROK",
	                  identity_status: "unresolved_symbol",
	                  token_id: null,
	                  chain: null,
	                  address: null,
	                  symbol: "GROK"
	                },
	                flow: {
	                  window: "1h",
	                  mentions: 3,
	                  watched_mentions: 0,
	                  unique_authors: 2,
	                  weighted_reach: 200,
	                  lag_ms: 60_000
	                },
	                market: {
	                  market_status: "missing",
	                  market_cap: null,
	                  price_change_after_seed_pct: null
	                },
	                scores: {
	                  seed: 70,
	                  diffusion: 30,
	                  token_link: 60,
	                  tradeability: 10
	                },
	                signal: {
	                  decision: "discard",
	                  reasons: ["watched_handle_seed", "seed_term_and_token_mention"],
	                  risks: ["unresolved_symbol", "market_missing"]
	                },
	                evidence: {
	                  first_linked_event_id: "event-grok-1",
	                  best_evidence_event_id: "event-grok-1",
	                  link_reason: "seed_term_and_token_mention",
	                  matched_terms: ["grok"],
	                  link_confidence: 0.6
	                }
	              }
	            },
	            {
	              seed: {
	                seed_id: "seed-2",
	                narrative_label: "ai_agent_upeg",
	                author_handle: "traderpow",
	                evidence: "$UPEG watched account evidence",
	                summary: "watched account linked UPEG",
	                received_at_ms: 1_777_746_010_000
	              },
	              link: {
	                identity: {
	                  identity_key: "symbol:UPEG",
	                  identity_status: "unresolved_symbol",
	                  token_id: null,
	                  chain: null,
	                  address: null,
	                  symbol: "UPEG"
	                },
	                flow: {
	                  window: "1h",
	                  mentions: 4,
	                  watched_mentions: 1,
	                  unique_authors: 2,
	                  weighted_reach: 169_125,
	                  lag_ms: 30_000
	                },
	                market: {
	                  market_status: "missing",
	                  market_cap: null,
	                  price_change_after_seed_pct: null
	                },
	                scores: {
	                  seed: 70,
	                  diffusion: 45,
	                  token_link: 65,
	                  tradeability: 10
	                },
	                signal: {
	                  decision: "discard",
	                  reasons: ["watched_handle_seed", "seed_symbol_candidate_confirmed"],
	                  risks: ["unresolved_symbol", "market_missing"]
	                },
	                evidence: {
	                  first_linked_event_id: "event-upeg-1",
	                  best_evidence_event_id: "event-upeg-1",
	                  link_reason: "seed_symbol_candidate_confirmed",
	                  matched_terms: ["upeg"],
	                  link_confidence: 0.65
	                }
	              }
	            }
	          ]
	        });
      }
      if (path === "/api/enrichment-jobs") {
        return ok({ items: [], counts: { pending: 3, running: 0, failed: 0, dead: 2, done: 1 } });
      }
      if (path === "/api/search") {
        const query = String(options?.params?.q ?? "");
        if (query === "@traderpow") {
          return ok({
            query: { kind: "handle", text: query, scope: "all", handle: "traderpow" },
            total_count: 2,
            returned_count: 2,
            has_more: false,
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
        if (/^0x[a-fA-F0-9]{40}$/.test(query)) {
          return ok({
            query: { kind: "ca", text: query, scope: "all", ca: "0x6982508145454Ce325dDbE47a25d4ec3d2311933", chain: "evm_unknown" },
            total_count: 1,
            returned_count: 1,
            has_more: false,
            items: [
              {
                match_type: "exact_ca",
                score: 100,
                event: {
                  event_id: "event-pepe-ca-1",
                  canonical_url: "https://x.com/traderpow/status/4",
                  author_handle: "traderpow",
                  received_at_ms: 1_777_746_300_000,
                  text_clean: "0x6982508145454ce325ddbe47a25d4ec3d2311933 exact CA evidence",
                  cashtags: ["PEPE"],
                  is_watched: 1
                }
              }
            ]
          });
        }
        return ok({
          query: { kind: "symbol", text: query, scope: "all", symbol: "UPEG" },
          total_count: 1,
          returned_count: 1,
          has_more: false,
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
    expect(await screen.findByText("p3/r0/f0/d2")).toBeInTheDocument();
    await screen.findByRole("button", { name: "select token $UPEG" });
    expect(container.querySelector(".direction.flat")?.textContent).toBe("-");
    expect(container.querySelector(".source-cell b")?.textContent).toBe("concentrated");
    expect(container.querySelector(".source-cell small")?.textContent).toBe("1 direct watch · 2 authors");
    expect(container.querySelector(".token-symbol > span")?.textContent).toBe("$UPEG");
    expect(container.querySelector(".token-symbol small")?.textContent).toBe("eth");
    expect(await screen.findByLabelText("narrative link ai_agent_upeg")).toBeInTheDocument();
    expect(await screen.findByText("叙事前沿")).toBeInTheDocument();
    expect(await screen.findByText("ai_agent_grok · seed_term_and_token_mention")).toBeInTheDocument();
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

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    expect(tokenPanel).not.toBeNull();
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "watched" }));

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/token-flow" && options?.params?.scope === "matched"
        )
      ).toBe(true);
    });
  });

  it("keeps all stream selected when the active toolbar scope is clicked", async () => {
    renderWithQuery(<App />);

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    expect(tokenPanel).not.toBeNull();
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "all" }));

    await waitFor(() => {
      const tokenFlowCalls = mockedGetApi.mock.calls.filter(([path]) => path === "/api/token-flow");
      expect(tokenFlowCalls.at(-1)?.[1]?.params?.scope).toBe("all");
    });
  });

  it("renders manual CA searches as exact CA evidence, not symbol evidence", async () => {
    renderWithQuery(<App />);

    const ca = "0x6982508145454ce325ddbe47a25d4ec3d2311933";
    fireEvent.change(screen.getByPlaceholderText("搜索 CA / $TOKEN / @handle / 文本"), { target: { value: ca } });
    fireEvent.click(screen.getByRole("button", { name: "检索" }));

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/search" && options?.params?.q === ca
        )
      ).toBe(true);
    });
    expect((await screen.findAllByText("exact_ca")).length).toBeGreaterThan(0);
    expect(screen.queryByText("exact_symbol")).not.toBeInTheDocument();
  });

  it("turns token flow clicks into full token posts with signal explanation", async () => {
    renderWithQuery(<App />);

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    expect(tokenPanel).not.toBeNull();
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "select token $UPEG" }));

    expect(await screen.findByDisplayValue("0x6982508145454Ce325dDbE47a25d4ec3d2311933")).toBeInTheDocument();
    expect(await screen.findByText("焦点证据")).toBeInTheDocument();
    expect(await screen.findByText("4 posts / 4 mentions (+3), diffusion concentrated across 2 authors, 1 direct watch, market fresh.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "全部帖子" })).toHaveClass("active");
    await waitFor(() => {
      expect(screen.getAllByText("$UPEG watched account evidence").length).toBeGreaterThan(0);
    });
    expect((await screen.findAllByText("3/4")).length).toBeGreaterThan(0);
    expect(
      mockedGetApi.mock.calls.some(
        ([path, options]) => path === "/api/token-posts" && options?.params?.token_id === "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933"
      )
    ).toBe(true);
    fireEvent.click(await screen.findByRole("button", { name: "加载更多" }));
    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/token-posts" && options?.params?.cursor === "cursor-2"
        )
      ).toBe(true);
    });
    expect(await screen.findByText("$UPEG final public post")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "信号解释" }));
    expect(await screen.findByRole("button", { name: "信号解释" })).toHaveClass("active");
    expect(await screen.findByText("traderpow x1")).toBeInTheDocument();
  });

  it("manual search clears stale token focus and owns the focus panel", async () => {
    renderWithQuery(<App />);

    const tokenPanel = (await screen.findByText("Token Flow")).closest("section");
    fireEvent.click(await within(tokenPanel!).findByRole("button", { name: "select token $UPEG" }));
    expect(await screen.findByText("4 posts / 4 mentions (+3), diffusion concentrated across 2 authors, 1 direct watch, market fresh.")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("搜索 CA / $TOKEN / @handle / 文本"), { target: { value: "@traderpow" } });
    fireEvent.click(screen.getByRole("button", { name: "检索" }));

    const focusPanel = screen.getByText("焦点证据").closest("section");
    expect(focusPanel).not.toBeNull();
    expect(await within(focusPanel!).findByText("search query")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(focusPanel!).getAllByText("@traderpow").length).toBeGreaterThan(0);
    });
    expect(await screen.findByText("2/2 shown")).toBeInTheDocument();
    expect(await within(focusPanel!).findByText("2/2 evidence shown for @traderpow. Exact CA, symbol, and handle matches are ranked before FTS text.")).toBeInTheDocument();
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
