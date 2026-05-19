import { buildSearchCaseView } from "@features/search/model/searchCase";
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
    expect(view.narrative.source).toBe("social");
    expect(view.narrative.value).toBe("RKC rotation");
    expect(view.market.value).toBe("$51M");
    expect(view.resolver.value).toBe("94%");
    expect(view.evidence.value).toBe("12 events");
  });

  it("keeps topic and ambiguous search narratives on the agent brief boundary", () => {
    const data = searchInspectFixture();
    const topicBrief = data.token_result!.discussion_digest;
    data.query.result_kind = "topic_result";
    data.token_result = null;
    data.topic_result = {
      summary: { posts: 2, authors: 2 },
      items: [],
      agent_brief: {
        schema_version: "search_agent_brief_v1",
        generated_by: "deterministic",
        project_summary: {
          current_state: "topic",
          data_gaps: [],
          evidence_event_ids: [],
          one_liner: "Topic agent memo",
          summary_zh: "Topic agent memo",
        },
        propagation: { key_accounts: [], phases: [], summary_zh: "topic" },
        bull_bear: {
          stance: "research",
          bear: { evidence_event_ids: [], invalidations_zh: [], thesis_zh: "" },
          bull: { evidence_event_ids: [], thesis_zh: "", triggers_zh: [] },
        },
      },
    };

    const view = buildSearchCaseView(data);

    expect(topicBrief.status).toBe("ready");
    expect(view.narrative.source).toBe("agent");
    expect(view.narrative.value).toBe("Topic agent memo");
  });

  it("normalizes structured token digest data gaps", () => {
    const data = searchInspectFixture();
    data.token_result!.discussion_digest = {
      status: "pending",
      data_gaps: [{ reason: "digest_not_ready" }],
    };

    const view = buildSearchCaseView(data);

    expect(view.narrative.value).toBe("Narrative pending");
    expect(view.narrative.detail).toBe("digest not ready");
  });

  it("reads token market facts from market_live instead of market candle metadata", () => {
    const data = searchInspectFixture();
    data.token_result!.market_live = {
      status: "ready",
      target_type: "Asset",
      target_id: "asset:solana:rkc",
      price_usd: 0.0078,
      market_cap_usd: 51_000_000,
      liquidity_usd: null,
      holders: null,
      observed_at_ms: 1_700_000_000_000,
      provider: "live-market",
    };
    data.token_result!.timeline.market_candles = {
      price_series_type: "anchor_line",
      provider: "candles-identity",
    };

    const view = buildSearchCaseView(data);

    expect(view.market.detail).toBe("live-market");
    expect(view.market.value).toBe("$51M");
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
      discussion_digest: {
        status: "ready",
        dominant_narrative: {
          title: "RKC rotation",
          summary_zh: "Runtime narrative",
          evidence_refs: [{ ref_type: "event", event_id: "e1" }],
        },
        coverage: { semantic_coverage: 0.76, labeled_mentions: 9, source_mentions: 12 },
        data_gaps: [],
      },
      narrative_clusters: [],
      pulse_overlay: null,
      market_live: {
        status: "ready",
        target_type: "Asset",
        target_id: "asset:solana:rkc",
        price_usd: 0.0078,
        market_cap_usd: 51_000_000,
        liquidity_usd: null,
        holders: null,
        observed_at_ms: 1_700_000_000_000,
        provider: "okx_dex_ws_price_info",
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
        market_candles: {
          price_series_type: "ohlc",
          candle_status: "ready",
          candle_bar: "1H",
          candles: [],
          target_type: "Asset",
          target_id: "asset:solana:rkc",
          chain_id: "solana",
          address: "Rkc111111111111111111111111111111111111111",
          symbol: "RKC",
        },
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
