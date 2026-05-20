import type { TokenFlowItem } from "@lib/types";
import { buildTokenRadarCompactCase } from "@shared/model/tokenRadarCompactCase";
import { describe, expect, it } from "vitest";

describe("buildTokenRadarCompactCase", () => {
  it("drives WHY NOW from a ready discussion digest", () => {
    const view = buildTokenRadarCompactCase(tokenFlowFixture());

    expect(view.narrative.value).toBe("Expansion chase · bullish 62%");
    expect(view.narrative.detail).toContain("retail is rotating into contract-confirmed posts");
    expect(view.narrative.detail).toContain("coverage 82%");
    expect(view.narrative.detail).not.toContain("有效讨论");
  });

  it.each([
    ["pending", "semantic_labeling_pending", "叙事分析中"],
    ["insufficient", "low_source_volume", "叙事样本不足"],
    ["semantic_unavailable", "low_semantic_coverage", "语义覆盖不足"],
  ] as const)("surfaces %s not-ready currentness without falling back to factor text", (status, reason, title) => {
    const view = buildTokenRadarCompactCase({
      ...tokenFlowFixture(),
      discussion_digest: {
        status,
        currentness: {
          display_status: "not_ready",
          reason: "no_ready_digest",
        },
        data_gaps: [{ reason }],
      },
    });

    expect(view.narrative.value).toBe(title);
    expect(view.narrative.detail).toBe(title);
    expect(view.narrative.detail).not.toContain("关注源");
    expect(view.narrative.detail).not.toContain("催化");
  });

  it("keeps last-ready digest visible while currentness is updating", () => {
    const view = buildTokenRadarCompactCase({
      ...tokenFlowFixture(),
      discussion_digest: {
        ...tokenFlowFixture().discussion_digest!,
        currentness: {
          display_status: "updating",
          reason: "digest_updating",
          delta_source_event_count: 6,
          delta_independent_author_count: 2,
          last_ready_computed_at_ms: 1_777_746_000_000,
        },
        data_gaps: [{ reason: "digest_updating", delta_source_event_count: 6 }],
      },
    });

    expect(view.narrative.value).toBe("Expansion chase · 更新中 +6");
    expect(view.narrative.detail).toContain("retail is rotating into contract-confirmed posts");
  });

  it("marks stale ready digest as the previous version", () => {
    const view = buildTokenRadarCompactCase({
      ...tokenFlowFixture(),
      discussion_digest: {
        ...tokenFlowFixture().discussion_digest!,
        currentness: {
          display_status: "stale",
          reason: "out_of_frontier",
          delta_source_event_count: 0,
          last_ready_computed_at_ms: 1_777_746_000_000,
        },
        data_gaps: [{ reason: "out_of_frontier" }],
      },
    });

    expect(view.narrative.value).toBe("Expansion chase · 上一版");
    expect(view.narrative.detail).toContain("coverage 82%");
  });

  it("renders unsupported 5m windows as realtime signal only", () => {
    const view = buildTokenRadarCompactCase({
      ...tokenFlowFixture(),
      flow: { ...tokenFlowFixture().flow, window: "5m" },
      discussion_digest: {
        status: "pending",
        currentness: {
          display_status: "unsupported_window",
          reason: "unsupported_window",
        },
        data_gaps: [{ reason: "narrative_not_supported_for_window" }],
      },
    });

    expect(view.narrative.value).toBe("5m 实时信号");
    expect(view.narrative.detail).toBe("5m 实时信号");
  });
});

function tokenFlowFixture(): TokenFlowItem {
  return {
    identity: {
      identity_key: "asset:dex:sol:hansa",
      identity_status: "EXACT",
      target_type: "Asset",
      target_id: "asset:dex:sol:hansa",
      asset_type: "Asset",
      venue_type: "dex",
      exchange: "gmgn",
      chain: "solana",
      address: "FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      symbol: "HANSA",
      resolution_reasons: [],
    },
    profile: { status: "missing" },
    market: {
      event_anchor: null,
      decision_latest: null,
      readiness: {
        anchor_status: "ready",
        latest_status: "live",
        dex_floor_status: "ready",
        missing_fields: [],
        stale_fields: [],
      },
      market_status: "fresh",
      price: 0.001,
      price_status: "fresh",
      market_cap: 5_100_000,
      market_cap_status: "fresh",
      liquidity: 180_000,
      liquidity_status: "fresh",
      holder_count: 12_000,
      holder_count_status: "fresh",
      price_change_since_social_pct: 0.14,
      price_change_status: "ready",
    },
    flow: {
      window: "1h",
      mentions: 21,
      watched_mentions: 3,
      previous_mentions: 4,
      mention_delta: 17,
      stream_dominance: 0.004,
      baseline_status: "ready",
      baseline_sample_count: 21,
    },
    social_heat: {
      score_version: "fixture",
      score: 86,
      reasons: ["z_score_above_3"],
      risks: [],
      contributions: [],
      risk_caps: [],
      window: "1h",
      mentions: 21,
      mentions_5m: 2,
      mentions_1h: 21,
      mentions_4h: 21,
      mentions_24h: 21,
      weighted_mentions: 21,
      previous_mentions: 4,
      mention_delta: 17,
      stream_share: 0.004,
      watched_share: 0.14,
      status: "new_burst",
    },
    discussion_quality: {
      score_version: "fixture",
      score: 72,
      reasons: ["old catalyst text"],
      risks: [],
      contributions: [],
      risk_caps: [],
      evidence_specificity: 0.9,
      avg_post_quality: 72,
      avg_attribution_confidence: 0.91,
      duplicate_text_share: 0.08,
      informative_post_count: 12,
      watched_source_count: 3,
    },
    propagation: {
      score_version: "fixture",
      score: 74,
      reasons: ["independent_expansion"],
      risks: [],
      contributions: [],
      risk_caps: [],
      independent_authors: 9,
      effective_authors: 8,
      new_authors: 7,
      top_author_share: 0.22,
      duplicate_text_share: 0.08,
      author_entropy: 0.8,
      phase: "expansion",
      top_authors: [],
    },
    tradeability: {
      score_version: "fixture",
      score: 100,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      identity_tradeable: true,
      market_fresh: true,
      market_cap_present: true,
      liquidity_present: true,
      pool_present: true,
    },
    timing: {
      score_version: "fixture",
      score: 88,
      status: "neutral",
      chase_risk: false,
      reasons: [],
      risks: [],
      price_change_since_social_pct: 0.14,
      market_observation_status: "ready",
    },
    opportunity: {
      score_version: "fixture",
      score: 83,
      decision: "driver",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      components: { heat: 86, quality: 72, propagation: 74, timing: 88 },
    },
    watch: {
      status: "public_only",
      direct_mentions: 0,
      direct_authors: 0,
      seed_link_count: 0,
      top_seed: null,
      reasons: [],
      risks: [],
    },
    discussion_digest: {
      status: "ready",
      currentness: {
        display_status: "current",
        reason: "fingerprint_match",
        delta_source_event_count: 0,
        delta_independent_author_count: 0,
        last_ready_computed_at_ms: 1_777_746_000_000,
      },
      dominant_narrative: {
        title: "Expansion chase",
        summary_zh: "retail is rotating into contract-confirmed posts",
        evidence_refs: [{ ref_type: "event", event_id: "event-hansa-1" }],
      },
      stance_mix: { bullish: 0.62, bearish: 0.16, neutral: 0.22 },
      coverage: { semantic_coverage: 0.82, labeled_mentions: 18, source_mentions: 22 },
      data_gaps: [],
    },
    evidence_total_count: 21,
    posts_query: { window: "1h", scope: "all", range: "current_window" },
    timeline_query: { window: "1h", scope: "all" },
  };
}
