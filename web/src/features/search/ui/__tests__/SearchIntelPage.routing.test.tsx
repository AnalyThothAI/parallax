import { setAuthToken } from "@lib/api/client";
import type { SearchInspectData } from "@lib/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { marketContextFixture, marketObservationFixture } from "../../../../test/marketFixtures";
import { createApiMock, ok, resetApiMock } from "../../../../test/msw/fixtures";
import { apiHandlers } from "../../../../test/msw/handlers";
import { server } from "../../../../test/msw/server";
import { SearchIntelPage } from "../SearchIntelPage";

const apiMock = createApiMock();

beforeEach(() => {
  setAuthToken("test-token");
  resetApiMock(apiMock);
  apiMock.readApiImpl = async () => ok(searchInspectData());
  server.use(...apiHandlers(apiMock));
});

afterEach(() => {
  setAuthToken(null);
  cleanup();
});

function renderAt(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/search" element={<SearchIntelPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SearchIntelPage", () => {
  it("loads search inspect data from the route and renders token evidence", async () => {
    const { container } = renderAt("/search?q=%24RKC&window=24h&scope=all");

    expect(await screen.findByRole("heading", { name: "Search Intel" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Search case $RKC" })).toBeInTheDocument();
    expect(
      await screen.findByRole("region", { name: "Token intelligence for RKC" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("navigation", { name: "Token profile links" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("group", { name: "search window" })).toBeInTheDocument();
    expect(await screen.findByText("项目总结")).toBeInTheDocument();
    expect(screen.getByText("传播")).toBeInTheDocument();
    expect(screen.getByText("多头观点")).toBeInTheDocument();
    expect(screen.getByText("空头观点")).toBeInTheDocument();
    expect(screen.getByText("1H OHLC")).toBeInTheDocument();
    expect(screen.getByText("24h Evidence Stream")).toBeInTheDocument();
    expect(screen.getAllByText(/Runtime narrative/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("navigation", { name: "Search sections" })).not.toBeInTheDocument();
    expect(screen.queryByText("candidates")).not.toBeInTheDocument();
    expect(screen.queryByText("94% confidence")).not.toBeInTheDocument();
    expect(container.querySelector(".search-sidebar-candidates")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/search/inspect",
        expect.objectContaining({
          params: expect.objectContaining({ q: "$RKC", window: "24h", scope: "all", limit: 200 }),
        }),
      );
    });
    expect(await axe(container)).toHaveNoViolations();
  }, 10_000);

  it("keeps candidate compare for ambiguous search results", async () => {
    const base = searchInspectData();
    const tokenResult = requiredTokenResult(base);
    const data: SearchInspectData = {
      ...base,
      query: { ...base.query, result_kind: "ambiguous_result" },
      token_result: null,
      ambiguous_result: {
        candidates: [
          {
            target_type: "Asset",
            target_id: "asset:solana:rkc",
            symbol: "RKC",
            status: "resolved",
            source: "asset_identity_current",
            reason: "CANONICAL_SYMBOL_MATCH",
          },
          {
            target_type: "Asset",
            target_id: "asset:solana:rocky",
            symbol: "ROCKY",
            status: "candidate",
            source: "asset_identity_current",
            reason: "FUZZY_SYMBOL_MATCH",
          },
        ],
        summary: { posts: 9, authors: 4 },
        items: [],
        agent_brief: tokenResult.agent_brief,
      },
    };
    apiMock.readApiImpl = async () => ok(data);

    renderAt("/search?q=%24RKC&window=24h&scope=all");

    expect(await screen.findByText("Ambiguous query")).toBeInTheDocument();
    const compare = screen.getByRole("heading", { name: "Candidate Compare" }).closest("section");
    expect(compare).toBeTruthy();
    expect(within(compare as HTMLElement).getByText("$RKC")).toBeInTheDocument();
    expect(within(compare as HTMLElement).getByText("$ROCKY")).toBeInTheDocument();
  });

  it("uses market cap as the primary DEX market metric in search details", async () => {
    const base = searchInspectData();
    const tokenResult = requiredTokenResult(base);
    const data: SearchInspectData = {
      ...base,
      token_result: {
        ...tokenResult,
        radar_item: {
          target: {
            target_type: "Asset",
            target_id: "asset:solana:rkc",
          },
          score: {
            rank_score: 74,
            recommended_decision: "token_watch",
          },
          factor_snapshot: {
            composite: {
              rank_score: 74,
              recommended_decision: "token_watch",
            },
            gates: {
              max_decision: "token_watch",
            },
            data_health: {
              market: "live",
              identity: "ready",
            },
            market: {
              market_cap_usd: 33_000_000,
            },
          },
          data_health: {
            market: "live",
            identity: "ready",
          },
          market: marketContextFixture({
            event_anchor: marketObservationFixture({
              target_type: "Asset",
              target_id: "asset:solana:rkc",
              source: "event_anchor",
              provider: "gmgn_dex_quote",
              price_usd: 0.007,
              market_cap_usd: 33_000_000,
            }),
            decision_latest: marketObservationFixture({
              target_type: "Asset",
              target_id: "asset:solana:rkc",
              source: "decision_latest",
              provider: "okx_dex_ws_price_info",
              price_usd: 0.0078,
              market_cap_usd: 51_000_000,
            }),
          }),
        },
      },
    };
    apiMock.readApiImpl = async () => ok(data);

    renderAt("/search?q=%24RKC&window=24h&scope=all");

    expect(await screen.findByText("market cap")).toBeInTheDocument();
    expect(screen.getAllByText("$51M").length).toBeGreaterThan(0);
    expect(screen.getByText("live · okx_dex_ws_price_info")).toBeInTheDocument();
  });
});

function requiredTokenResult(data: SearchInspectData) {
  if (!data.token_result) {
    throw new Error("Search inspect fixture is missing token_result");
  }
  return data.token_result;
}

function searchInspectData(): SearchInspectData {
  return {
    query: {
      q: "$RKC",
      normalized_q: "rkc",
      window: "24h",
      scope: "all",
      result_kind: "token_result",
    },
    resolver: {
      confidence: 0.94,
      target_candidates: [
        {
          target_type: "Asset",
          target_id: "asset:solana:rkc",
          symbol: "RKC",
          status: "resolved",
          source: "asset_identity_current",
          reason: "CANONICAL_SYMBOL_MATCH",
        },
      ],
      selected_target: {
        target_type: "Asset",
        target_id: "asset:solana:rkc",
        symbol: "RKC",
        status: "resolved",
        source: "asset_identity_current",
        reason: "CANONICAL_SYMBOL_MATCH",
      },
      reasons: ["one_resolved_target"],
    },
    token_result: {
      target: {
        target_type: "Asset",
        target_id: "asset:solana:rkc",
        symbol: "RKC",
        status: "resolved",
        source: "asset_identity_current",
        reason: "CANONICAL_SYMBOL_MATCH",
      },
      timeline: {
        query: {
          target_type: "Asset",
          target_id: "asset:solana:rkc",
          window: "24h",
          scope: "all",
          bucket: "1h",
        },
        summary: {
          posts: 73,
          authors: 18,
          effective_authors: 18,
          watched_posts: 6,
          phase: "expansion",
          top_author_share: 0.22,
          duplicate_text_share: 0.12,
          peak_posts_per_bucket: 12,
          peak_new_authors_per_bucket: 5,
          reproduction_rate: null,
        },
        market_overlay: {},
        stages: [],
        buckets: [
          {
            start_ms: 1,
            end_ms: 2,
            posts: 8,
            authors: 4,
            new_authors: 4,
            watched_posts: 1,
            duplicate_text_share: 0,
            price: null,
            price_change_from_start_pct: null,
          },
        ],
        authors: [],
        posts: [],
        cascade: { edges: [], unresolved_parents: [] },
        returned_count: 0,
        has_more: false,
      },
      posts: {
        query: {
          target_type: "Asset",
          target_id: "asset:solana:rkc",
          window: "24h",
          scope: "all",
          range: "current_window",
          sort: "recent",
        },
        score_window: { window: "24h" },
        total_count: 1,
        returned_count: 1,
        has_more: false,
        items: [
          {
            event_id: "ev_482",
            handle: "toly",
            text: "Runtime narrative validates $RKC",
            received_at_ms: 1_700_000_000_000,
            stage_phase: "expansion",
            is_watched: true,
            price: { status: "ready", price_usd: 0.0078 },
            post_quality: {
              score_version: "post_quality_v1",
              score: 80,
              reasons: [],
              risks: [],
              contributions: [],
              risk_caps: [],
            },
          },
        ],
      },
      radar_item: null,
      profile: {
        status: "ready",
        provider: "gmgn",
        identity: {
          symbol: "RKC",
          name: "Runtime Coin",
          logo_url: null,
          description: "Runtime narrative token profile",
        },
        links: {
          website_url: "https://rkc.example",
          twitter_url: "https://x.com/rkc",
          gmgn_url: "https://gmgn.ai/sol/token/rkc",
          geckoterminal_url: "https://www.geckoterminal.com/solana/pools/rkc",
        },
        source: {
          provider: "gmgn",
          raw_available: true,
          last_error: null,
        },
      },
      market_overlay: {
        price_series_type: "ohlc",
        candle_status: "ready",
        candle_bar: "1H",
        candles: [
          {
            time_ms: 1_700_000_000_000,
            open: 0.007,
            high: 0.008,
            low: 0.006,
            close: 0.0078,
            volume: 1000,
            volume_quote: null,
            volume_usd: 7800,
            confirmed: true,
          },
        ],
      },
      agent_brief: {
        schema_version: "search_agent_brief_v1",
        generated_by: "deterministic",
        project_summary: {
          one_liner: "$RKC 24h social propagation brief",
          summary_zh: "过去 24 小时，RKC 进入 expansion。",
          current_state: "active_propagation",
          data_gaps: ["缺真实 OHLC/K 线"],
          evidence_event_ids: ["ev_482"],
        },
        propagation: {
          summary_zh: "seed -> expansion",
          phases: [
            {
              phase: "expansion",
              window_label: "11:00-16:00",
              tweets: 31,
              authors: 14,
              lead_accounts: ["toly"],
              read_zh: "作者宽度变大。",
              evidence_event_ids: ["ev_482"],
            },
          ],
          key_accounts: [{ handle: "toly", role: "watched", posts: 1 }],
        },
        bull_bear: {
          stance: "watch",
          bull: {
            thesis_zh: "作者扩散。",
            evidence_event_ids: ["ev_482"],
            triggers_zh: ["新增作者"],
          },
          bear: {
            thesis_zh: "后段 chase。",
            evidence_event_ids: ["ev_556"],
            invalidations_zh: ["无新作者"],
          },
        },
      },
    },
    topic_result: null,
    ambiguous_result: null,
  };
}
