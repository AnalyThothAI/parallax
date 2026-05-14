import { buildSearchCaseView } from "@features/search/model/searchCase";
import { buildSearchRadarSummary } from "@features/search/model/searchRadar";
import { buildTopicBuckets } from "@features/search/model/searchTopicTimeline";
import type { SearchInspectData } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("buildSearchCaseView", () => {
  it("maps token search inspect data into the shared case grammar", () => {
    const view = buildSearchCaseView(searchInspectFixture());

    expect(view.resultKind).toBe("token_result");
    expect(view.title).toBe("$RKC");
    expect(view.official.value).toBe("Rockchain");
    expect(view.official.source).toBe("official");
    expect(view.community.value).toBe("73 posts · 18 authors");
    expect(view.narrative.source).toBe("agent");
    expect(view.market.value).toBe("$51M");
    expect(view.resolver.value).toBe("94%");
    expect(view.evidence.value).toBe("12 events");
  });

  it("derives search radar summary outside the route component", () => {
    const data = searchInspectFixture();
    data.token_result!.radar_item = {
      data_health: { identity: "ready", market: "live" },
      market: {
        decision_latest: {
          market_cap_usd: 51_000_000,
          price_usd: 0.0078,
          provider: "okx_dex_ws_price_info",
        },
        event_anchor: {
          market_cap_usd: 33_000_000,
          provider: "gmgn_dex_quote",
        },
        readiness: { anchor_status: "anchored", latest_status: "live" },
      },
      score: { rank_score: 74, recommended_decision: "token_watch" },
      target: { target_id: "asset:solana:rkc", target_type: "Asset" },
    };

    const summary = buildSearchRadarSummary(data.token_result!);

    expect(summary.primaryMarketLabel).toBe("market cap");
    expect(summary.primaryMarketValue).toBe("$51M");
    expect(summary.primaryMarketDetail).toBe("live · okx_dex_ws_price_info");
    expect(summary.scoreSummary).toEqual([
      { label: "rank", value: "74" },
      { label: "decision", value: "token_watch" },
      { label: "gate", value: "-" },
    ]);
  });

  it("builds topic buckets outside the route component", () => {
    const buckets = buildTopicBuckets([
      searchItem("e1", 1_700_000_000_000),
      searchItem("e2", 1_700_000_010_000),
      searchItem("e3", 1_700_004_000_000),
    ]);

    expect(buckets).toEqual([
      { posts: 2, startMs: 1_700_000_000_000 },
      { posts: 1, startMs: 1_700_003_600_000 },
    ]);
  });
});

function searchInspectFixture(): SearchInspectData {
  return {
    query: {
      normalized_q: "rkc",
      q: "$RKC",
      result_kind: "token_result",
      scope: "all",
      window: "24h",
    },
    resolver: {
      confidence: 0.94,
      reasons: ["one_resolved_target"],
      selected_target: {
        reason: "CANONICAL_SYMBOL_MATCH",
        source: "asset_identity_current",
        status: "resolved",
        symbol: "RKC",
        target_id: "asset:solana:rkc",
        target_type: "Asset",
      },
      target_candidates: [],
    },
    token_result: {
      agent_brief: {
        schema_version: "search_agent_brief_v1",
        generated_by: "deterministic",
        project_summary: {
          current_state: "active",
          data_gaps: [],
          evidence_event_ids: ["e1", "e2"],
          one_liner: "Runtime narrative",
          summary_zh: "Runtime narrative",
        },
        propagation: {
          key_accounts: [],
          phases: [],
          summary_zh: "expansion",
        },
        bull_bear: {
          stance: "watch",
          bear: { evidence_event_ids: [], invalidations_zh: [], thesis_zh: "risk" },
          bull: { evidence_event_ids: [], thesis_zh: "thesis", triggers_zh: [] },
        },
      },
      market_overlay: {
        price_series_type: "ohlc",
        decision_latest: {
          market_cap_usd: 51_000_000,
          price_usd: 0.0078,
          provider: "okx_dex_ws_price_info",
        },
      },
      posts: {
        has_more: false,
        items: [],
        query: {
          range: "current_window",
          scope: "all",
          target_id: "asset:solana:rkc",
          target_type: "Asset",
          window: "24h",
        },
        returned_count: 12,
        score_window: { window: "24h" },
        total_count: 12,
      },
      profile: {
        status: "ready",
        identity: {
          description: "Official profile description.",
          name: "Rockchain",
          symbol: "RKC",
        },
        links: { website_url: "https://rock.example" },
        provider: "gmgn",
      },
      radar_item: null,
      target: {
        reason: "CANONICAL_SYMBOL_MATCH",
        source: "asset_identity_current",
        status: "resolved",
        symbol: "RKC",
        target_id: "asset:solana:rkc",
        target_type: "Asset",
      },
      timeline: {
        authors: [],
        buckets: [],
        cascade: { edges: [], unresolved_parents: [] },
        has_more: false,
        next_cursor: null,
        posts: [],
        query: {
          bucket: "1h",
          scope: "all",
          target_id: "asset:solana:rkc",
          target_type: "Asset",
          window: "24h",
        },
        returned_count: 0,
        stages: [],
        summary: {
          authors: 18,
          duplicate_text_share: 0.12,
          effective_authors: 18,
          peak_new_authors_per_bucket: 4,
          peak_posts_per_bucket: 9,
          phase: "expansion",
          posts: 73,
          reproduction_rate: 1.4,
          top_author_share: 0.22,
          watched_posts: 6,
        },
      },
    },
  };
}

function searchItem(eventId: string, receivedAtMs: number) {
  return {
    event: {
      action: "post",
      author_handle: "toly",
      canonical_url: null,
      content: { text: "topic mention" },
      event_id: eventId,
      is_watched: true,
      received_at_ms: receivedAtMs,
      search_text: "topic mention",
      text_clean: "topic mention",
    },
    match_type: "topic",
    match_reasons: ["text_match"],
    route_scores: {},
    score: 1,
  };
}
