import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type {
  ApiResponse,
  AttentionFrontierData,
  BootstrapData,
  LivePayload,
  NarrativeFlowData,
  NarrativeFlowItem,
  StatusData,
  AttentionFrontierItem,
  TokenFlowData,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData
} from "./api/types";
import { getApi, getBootstrap } from "./api/client";
import { useTraderStore } from "./store/useTraderStore";

const socketMock: { status: string; events: LivePayload[]; lastMessageAt: number | null } = {
  status: "connected",
  events: [],
  lastMessageAt: 1_777_770_000_000
};

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return {
    ...actual,
    getApi: vi.fn(),
    getBootstrap: vi.fn()
  };
});

vi.mock("./api/useIntelSocket", () => ({
  useIntelSocket: () => socketMock
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
    llm_configured: true,
    worker_running: true,
    job_counts: { pending: 1, running: 0, failed: 0, dead: 0, done: 8 }
  }
};

describe("App Token Radar social heat cockpit", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockedGetApi.mockReset();
    mockedGetBootstrap.mockReset();
    socketMock.status = "connected";
    socketMock.events = [liveUpegEvent()];
    socketMock.lastMessageAt = 1_777_770_000_000;
    useTraderStore.setState({
      token: "",
      window: "1h",
      scope: "all",
      handles: "",
      search: "$PEPE",
      submittedSearch: "$PEPE",
      radarSortMode: "opportunity",
      detailTab: "timeline",
      timelineBucket: "1m",
      postSortMode: "recent",
      hideDuplicateClusters: false,
      watchedPostsOnly: false,
      manualDecisions: {}
    });
    mockedGetBootstrap.mockResolvedValue(ok<BootstrapData>({ ws_token: "secret", handles: ["toly", "traderpow"], replay_limit: 100 }));
    mockApi();
  });

  it("renders the new radar contract and keeps Select Token detail plus realtime tape", async () => {
    renderWithQuery(<App />);

    expect(await screen.findByText("Token")).toBeInTheDocument();
    expect(screen.getAllByText("Heat").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Quality").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Propagation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Market").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Timing").length).toBeGreaterThan(0);
    expect(screen.getByText("Decision")).toBeInTheDocument();
    expect(screen.queryByText("EV")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "select token $UPEG" })).toBeInTheDocument();
    expect(screen.getAllByText("Driver").length).toBeGreaterThan(0);
    expect(await screen.findByText("实时信号 Tape")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("$UPEG").length).toBeGreaterThan(0));
  });

  it("opens Timeline by default, requests timeline/posts, and exposes score ledger tabs", async () => {
    renderWithQuery(<App />);

    const tokenButton = await screen.findByRole("button", { name: "select token $UPEG" });
    fireEvent.click(tokenButton);

    expect(await screen.findByRole("button", { name: "Timeline" })).toHaveClass("active");
    await waitFor(() => {
      expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-social-timeline")).toBe(true);
      expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-posts")).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Posts" }));
    expect(await screen.findByText("$UPEG watched account evidence")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Score" }));
    await waitFor(() => expect(screen.getAllByText("Opportunity").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Tradeability").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    await waitFor(() => expect(screen.getAllByText("样本不足").length).toBeGreaterThan(0));
  });

  it("shows Chinese narrative display and surfaces missing display as an error state", async () => {
    renderWithQuery(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Narratives" }));
    await waitFor(() => expect(screen.getAllByText("Grok 叙事带动 UPEG 社交扩散").length).toBeGreaterThan(0));
    expect(screen.queryByText("ai_agent_upeg")).not.toBeInTheDocument();

    cleanup();
    mockApi({ missingNarrativeDisplay: true });
    renderWithQuery(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Narratives" }));
    await waitFor(() => expect(screen.getAllByText("narrative_display_missing").length).toBeGreaterThan(0));
  });

  it("dedupes replay/live tape rows and token tape click does not change sort mode", async () => {
    renderWithQuery(<App />);

    await screen.findByText("实时信号 Tape");
    expect(await screen.findByText("@traderpow -> $UPEG")).toBeInTheDocument();
    expect(screen.getAllByText("@traderpow -> $UPEG")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Heat" }));
    expect(screen.getByRole("button", { name: "Heat" })).toHaveClass("active");
    fireEvent.click(screen.getByText("@traderpow -> $UPEG"));
    expect(screen.getByRole("button", { name: "Heat" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "Timeline" })).toHaveClass("active");
  });

  it("keeps replay rows visible when websocket disconnects", async () => {
    socketMock.status = "disconnected";
    renderWithQuery(<App />);

    expect(await screen.findByText("ws disconnected")).toBeInTheDocument();
    expect(await screen.findByText("@traderpow -> $UPEG")).toBeInTheDocument();
  });

  it("requests selected token detail by chain and address when token_id is absent", async () => {
    mockApi({ missingTokenId: true });
    renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    await waitFor(() => {
      const timelineCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-social-timeline");
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-posts");
      expect(timelineCall?.[1]?.params).toMatchObject({ chain: "eth", address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933" });
      expect(postsCall?.[1]?.params).toMatchObject({ chain: "eth", address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933" });
    });
  });

  it("uses live token attribution before ambiguous cashtag matching in the tape", async () => {
    socketMock.events = [liveUpegEvent({ tokenId: "token:eth:0x1111111111111111111111111111111111111111", address: "0x1111111111111111111111111111111111111111" })];
    mockApi({ duplicateSymbol: true });
    const { container } = renderWithQuery(<App />);

    await screen.findAllByRole("button", { name: "select token $UPEG" });
    await screen.findByText("@traderpow -> $UPEG");
    fireEvent.click(screen.getByText("@traderpow -> $UPEG"));

    await waitFor(() => {
      const drawer = container.querySelector(".detail-drawer") as HTMLElement;
      expect(within(drawer).getByText((content) => content.includes("0x111111"))).toBeInTheDocument();
      expect(within(drawer).queryByText((content) => content.includes("0x222222"))).not.toBeInTheDocument();
    });
  });
});

function mockApi(options: { missingNarrativeDisplay?: boolean; missingTokenId?: boolean; duplicateSymbol?: boolean } = {}) {
  mockedGetApi.mockImplementation(async (path, requestOptions) => {
    if (path === "/api/status") return ok(statusData);
    if (path === "/api/recent") return ok({ scope: requestOptions?.params?.scope, events: [], items: [liveUpegEvent()] });
    if (path === "/api/token-flow") {
      if (options.duplicateSymbol) {
        return ok<TokenFlowData>({
          window: "1h",
          scope: "all",
          items: [
            tokenFlowItem({ tokenId: "token:eth:0x1111111111111111111111111111111111111111", address: "0x1111111111111111111111111111111111111111" }),
            tokenFlowItem({ tokenId: "token:eth:0x2222222222222222222222222222222222222222", address: "0x2222222222222222222222222222222222222222", score: 60 })
          ]
        });
      }
      return ok<TokenFlowData>({ window: "1h", scope: "all", items: [tokenFlowItem({ tokenId: options.missingTokenId ? null : undefined })] });
    }
    if (path === "/api/token-social-timeline") return ok<TokenSocialTimelineData>(timelineData());
    if (path === "/api/token-posts") return ok<TokenPostsData>(postsData());
    if (path === "/api/account-quality") {
      return ok({
        query: { handles: ["traderpow", "alien19710628"] },
        accounts: [
          {
            profile: { handle: "traderpow", first_seen_ms: 1_777_746_010_000, latest_seen_ms: 1_777_746_010_000, follower_max: 168_905, watched_status: "watched" },
            summary: { status: "insufficient_sample", sample_size: 1, precision_score: null, early_call_score: 100, spam_risk_score: 0, avg_realized_return: null },
            token_call_stats: [],
            quality_snapshots: []
          }
        ]
      });
    }
    if (path === "/api/account-alerts") return ok({ window: "24h", alert_type: null, items: [] });
    if (path === "/api/narrative-flow") return ok<NarrativeFlowData>({ window: "1h", items: [narrativeFlowItem(options)] });
    if (path === "/api/attention-frontier") return ok<AttentionFrontierData>({ window: "1h", items: [frontierItem(options)] });
    if (path === "/api/enrichment-jobs") return ok({ items: [], counts: { pending: 1, running: 0, failed: 0, dead: 0, done: 8 } });
    if (path === "/api/search") {
      return ok({
        query: { kind: "symbol", text: String(requestOptions?.params?.q ?? ""), scope: "all", symbol: "PEPE" },
        total_count: 0,
        returned_count: 0,
        has_more: false,
        items: []
      });
    }
    throw new Error(`unexpected path ${path}`);
  });
}

function tokenFlowItem(options: { tokenId?: string | null; address?: string; score?: number } = {}): TokenFlowItem {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const tokenId = options.tokenId === undefined ? `token:eth:${address}` : options.tokenId;
  return {
    identity: {
      identity_key: tokenId ?? `eth:${address}`,
      identity_status: "resolved_ca",
      token_id: tokenId,
      chain: "eth",
      address,
      symbol: "UPEG"
    },
    market: {
      market_status: "fresh",
      price: 0.001,
      market_cap: 60490,
      liquidity: 250000,
      pool_status: "ready",
      snapshot_age_ms: 120_000,
      snapshot_received_at_ms: 1_777_746_050_000,
      price_change_window_pct: 0.12,
      price_at_window_start: 0.001,
      price_at_window_end: 0.00112,
      price_change_status: "ready"
    },
    flow: {
      window: "1h",
      window_start_ms: 1_777_746_000_000,
      window_end_ms: 1_777_746_300_000,
      mentions: 4,
      direct_mentions: 3,
      watched_mentions: 1,
      previous_mentions: 1,
      mention_delta: 3,
      mention_delta_pct: 3,
      z_score: 3.2,
      new_burst_score: null,
      stream_dominance: 0.25,
      baseline_status: "ready",
      baseline_sample_count: 20
    },
    social_heat: scoreBlock({
      score_version: "social_heat_v1",
      score: 86,
      reasons: ["z_score_above_3", "positive_mention_delta"],
      risks: ["public_stream_coverage"],
      window: "1h",
      mentions: 4,
      weighted_mentions: 3.8,
      previous_mentions: 1,
      mention_delta: 3,
      mention_delta_pct: 3,
      z_score: 3.2,
      new_burst_score: null,
      stream_share: 0.25,
      watched_share: 0.25,
      status: "burst"
    }),
    discussion_quality: scoreBlock({
      score_version: "discussion_quality_v1",
      score: 78,
      reasons: ["resolved_direct_evidence", "informative_discussion"],
      risks: [],
      evidence_specificity: 0.75,
      avg_post_quality: 82,
      avg_attribution_confidence: 1,
      duplicate_text_share: 0,
      informative_post_count: 3,
      watched_source_count: 1
    }),
    propagation: scoreBlock({
      score_version: "propagation_v1",
      score: 72,
      reasons: ["independent_expansion"],
      risks: [],
      independent_authors: 3,
      effective_authors: 2.6,
      new_authors: 3,
      top_author_share: 0.5,
      duplicate_text_share: 0,
      author_entropy: 1,
      reproduction_rate: 1.5,
      phase: "expansion",
      top_authors: [{ handle: "traderpow", count: 1, followers: 168_905, watched_count: 1 }]
    }),
    tradeability: scoreBlock({
      score_version: "tradeability_v1",
      score: 80,
      reasons: ["resolved_ca", "fresh_market"],
      risks: [],
      identity_tradeable: true,
      market_fresh: true,
      market_cap_present: true,
      liquidity_present: true,
      pool_present: true
    }),
    timing: {
      score_version: "timing_v1",
      score: 70,
      status: "social_confirms_price",
      chase_risk: false,
      social_start_ms: 1_777_746_000_000,
      first_price_move_ms: 1_777_746_050_000,
      price_change_window_pct: 0.12,
      reasons: ["social_and_price_confirm"],
      risks: []
    },
    opportunity: scoreBlock({
      score_version: "social_opportunity_v1",
      score: options.score ?? 79,
      decision: "driver",
      decision_priority: 3,
      reasons: ["z_score_above_3", "independent_expansion"],
      risks: ["public_stream_coverage"],
      components: { heat: 86, quality: 78, propagation: 72, tradeability: 80, timing: 70 }
    }),
    evidence_total_count: 4,
    posts_query: { token_id: tokenId, chain: "eth", address, window: "1h", scope: "all" },
    timeline_query: { token_id: tokenId, chain: "eth", address, window: "1h", bucket: "1m", scope: "all" }
  };
}

function timelineData(): TokenSocialTimelineData {
  return {
    query: tokenFlowItem().timeline_query,
    summary: {
      posts: 3,
      authors: 2,
      effective_authors: 1.8,
      first_seen_ms: 1_777_746_010_000,
      latest_seen_ms: 1_777_746_060_000,
      phase: "expansion",
      top_author_share: 0.5,
      duplicate_text_share: 0
    },
    buckets: [
      { start_ms: 1_777_746_000_000, end_ms: 1_777_746_060_000, posts: 2, new_authors: 1, watched_posts: 1, duplicate_text_share: 0, price: null, price_change_from_start_pct: null },
      { start_ms: 1_777_746_060_000, end_ms: 1_777_746_120_000, posts: 1, new_authors: 1, watched_posts: 0, duplicate_text_share: 0, price: null, price_change_from_start_pct: null }
    ],
    authors: [
      { handle: "traderpow", first_seen_ms: 1_777_746_010_000, latest_seen_ms: 1_777_746_010_000, posts: 1, followers: 168_905, role: "watched", quality_score: null },
      { handle: "alien19710628", first_seen_ms: 1_777_746_060_000, latest_seen_ms: 1_777_746_060_000, posts: 2, followers: 220, role: "amplifier", quality_score: null }
    ],
    posts: postsData().items.map((item) => ({ ...item, bucket_start_ms: 1_777_746_000_000 })),
    returned_count: 3,
    has_more: false,
    next_cursor: null
  };
}

function postsData(): TokenPostsData {
  return {
    query: tokenFlowItem().posts_query,
    total_count: 3,
    returned_count: 3,
    has_more: false,
    next_cursor: null,
    items: [
      post("event-upeg-1", "traderpow", "$UPEG watched account evidence", true, 86),
      post("event-upeg-2", "alien19710628", "$UPEG public follow-through", false, 74),
      post("event-upeg-3", "alien19710628", "$UPEG another public post", false, 68)
    ]
  };
}

function post(eventId: string, handle: string, text: string, watched: boolean, score: number) {
  return {
    event_id: eventId,
    handle,
    received_at_ms: 1_777_746_010_000,
    text,
    url: `https://x.com/${handle}/status/${eventId}`,
    mention_source: "gmgn_token_payload",
    attribution_status: "direct",
    attribution_confidence: 1,
    attribution_weight: 1,
    is_watched: watched,
    post_quality: {
      score_version: "post_quality_v1",
      score,
      reasons: ["structured_token_payload"],
      risks: [],
      contributions: [{ feature: "source_specificity", value: 18, reason: "structured_token_payload" }],
      risk_caps: []
    }
  };
}

function narrativeFlowItem(options: { missingNarrativeDisplay?: boolean }): NarrativeFlowItem {
  return {
    narrative_label: "ai_agent_upeg",
    window: "1h",
    display: display(options),
    mention_count: 6,
    watched_mention_count: 1,
    unique_author_count: 3,
    velocity: 3,
    top_authors: [],
    top_events: []
  };
}

function frontierItem(options: { missingNarrativeDisplay?: boolean }): AttentionFrontierItem {
  return {
    seed: {
      seed_id: "seed-upeg",
      narrative_label: "ai_agent_upeg",
      author_handle: "traderpow",
      evidence: "Grok is getting scary good",
      summary: "watched account seed",
      display: display(options),
      received_at_ms: 1_777_746_000_000,
      seed_terms: ["grok", "ai"]
    },
    link: {
      identity: tokenFlowItem().identity,
      flow: { window: "1h", mentions: 4, watched_mentions: 1, unique_authors: 2, weighted_reach: 169_125, lag_ms: 30_000 },
      market: { market_status: "fresh", market_cap: 60490, price_change_after_seed_pct: 0.12 },
      scores: { seed: 70, diffusion: 72, token_link: 76, tradeability: 80 },
      signal: { decision: "driver", reasons: ["watched_handle_seed"], risks: ["public_stream_coverage"] },
      evidence: { first_linked_event_id: "event-upeg-1", best_evidence_event_id: "event-upeg-1", link_reason: "seed_symbol_candidate_confirmed", matched_terms: ["upeg"], link_confidence: 0.65 }
    }
  };
}

function display(options: { missingNarrativeDisplay?: boolean }) {
  if (options.missingNarrativeDisplay) {
    return { name_zh: "", headline_zh: "", summary_zh: "", market_interpretation_zh: "", readability_status: "narrative_display_missing" };
  }
  return {
    name_zh: "Grok AI Agent",
    headline_zh: "Grok 叙事带动 UPEG 社交扩散",
    summary_zh: "关注账号提到 Grok 后，公开流出现 UPEG 相关讨论。",
    market_interpretation_zh: "交易员应观察 AI Agent 主题是否继续扩散到独立作者。",
    readability_status: "ready"
  };
}

function liveUpegEvent(options: { tokenId?: string; address?: string } = {}): LivePayload {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const tokenId = options.tokenId ?? `token:eth:${address}`;
  return {
    type: "event",
    event: {
      event_id: "event-upeg-1",
      canonical_url: "https://x.com/traderpow/status/1",
      author_handle: "traderpow",
      received_at_ms: 1_777_746_010_000,
      text_clean: "$UPEG watched account evidence",
      cashtags: ["UPEG"],
      is_watched: 1
    },
    entities: [{ entity_type: "symbol", normalized_value: "UPEG", received_at_ms: 1_777_746_010_000 }],
    token_attributions: [
      {
        token_id: tokenId,
        identity_key: tokenId,
        identity_status: "resolved_ca",
        chain: "eth",
        address,
        symbol: "UPEG",
        attribution_status: "direct",
        attribution_confidence: 1,
        attribution_weight: 1,
        attribution_rank: 0
      }
    ],
    alerts: [],
    enrichment: null
  };
}

function scoreBlock<T extends Record<string, unknown>>(extra: T) {
  return {
    contributions: [{ feature: "test", value: 10, reason: "test_reason" }],
    risk_caps: [],
    ...extra
  } as T & { contributions: Array<{ feature: string; value: number; reason: string }>; risk_caps: [] };
}

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
