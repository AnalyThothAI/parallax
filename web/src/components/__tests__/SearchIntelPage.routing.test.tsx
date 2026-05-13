import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/client";
import { useTraderStore } from "../../store/useTraderStore";
import { marketContextFixture, marketObservationFixture } from "../../test/marketFixtures";
import { SearchIntelPage } from "../SearchIntelPage";

beforeEach(() => {
  useTraderStore.setState({ token: "test-token" });
  vi.spyOn(client, "getApi").mockResolvedValue({ ok: true, data: searchInspectData() });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
    renderAt("/search?q=%24RKC&window=24h&scope=all");

    expect(await screen.findByRole("heading", { name: "Search Intel" })).toBeInTheDocument();
    expect(await screen.findByText("项目总结")).toBeInTheDocument();
    expect(screen.getByText("传播")).toBeInTheDocument();
    expect(screen.getByText("多头观点")).toBeInTheDocument();
    expect(screen.getByText("空头观点")).toBeInTheDocument();
    expect(screen.getByText("1H OHLC")).toBeInTheDocument();
    expect(screen.getByText("24h Evidence Stream")).toBeInTheDocument();
    expect(screen.getByText(/Runtime narrative/)).toBeInTheDocument();

    await waitFor(() => {
      expect(client.getApi).toHaveBeenCalledWith(
        "/api/search/inspect",
        expect.objectContaining({
          params: expect.objectContaining({ q: "$RKC", window: "24h", scope: "all", limit: 200 }),
        }),
      );
    });
  });

  it("uses market cap as the primary DEX market metric in search details", async () => {
    const data = searchInspectData() as any;
    data.token_result.radar_item = {
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
    };
    vi.mocked(client.getApi).mockResolvedValueOnce({ ok: true, data });

    renderAt("/search?q=%24RKC&window=24h&scope=all");

    expect(await screen.findByText("market cap")).toBeInTheDocument();
    expect(screen.getByText("$51M")).toBeInTheDocument();
    expect(screen.getByText("live · okx_dex_ws_price_info")).toBeInTheDocument();
  });
});

function searchInspectData() {
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
        market_overlay: {
          price_series_type: "ohlc",
          candle_status: "ready",
          candle_bar: "1H",
          candles: [],
        },
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
            author_handle: "toly",
            text: "Runtime narrative validates $RKC",
            received_at_ms: 1_700_000_000_000,
            stage_phase: "expansion",
            is_watched: true,
            price: { status: "ready", price_usd: 0.0078 },
            post_quality: { score_version: "post_quality_v1", score: 80 },
          },
        ],
      },
      radar_item: null,
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
