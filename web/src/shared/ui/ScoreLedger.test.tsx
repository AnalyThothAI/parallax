import type { TokenFlowItem } from "@lib/types";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { tokenMarketBlockFixture } from "../../test/marketFixtures";

import { ScoreLedger } from "./ScoreLedger";

afterEach(() => cleanup());

describe("ScoreLedger", () => {
  it("renders v2 alpha cards separately from gate and data-health context", () => {
    render(<ScoreLedger token={token()} />);

    const scoreCards = document.querySelectorAll(".score-card");
    expect(scoreCards).toHaveLength(4);
    expect(screen.getByText("Social demand")).toBeInTheDocument();
    expect(screen.getByText("Evidence quality")).toBeInTheDocument();
    expect(screen.getByText("Diffusion")).toBeInTheDocument();
    expect(screen.getByText("Timing risk")).toBeInTheDocument();
    expect(screen.queryByText("Tradeability")).not.toBeInTheDocument();
    expect(screen.queryByText("Identity")).not.toBeInTheDocument();
    expect(screen.queryByText("Market")).not.toBeInTheDocument();

    expect(screen.getByText("market freshness missing")).toBeInTheDocument();
    expect(screen.getByText("#7 / 42")).toBeInTheDocument();
    expect(screen.getByText("market:partial")).toBeInTheDocument();
    expect(screen.getByText("alpha:partial")).toBeInTheDocument();

    const gatePanel = screen.getByText("Gate").closest("section");
    expect(gatePanel).not.toBeNull();
    expect(within(gatePanel as HTMLElement).getByText("blocked")).toBeInTheDocument();
    expect(within(gatePanel as HTMLElement).getByText("watch")).toBeInTheDocument();
  });
});

function token(): TokenFlowItem {
  return {
    identity: {
      identity_key: "asset:test",
      identity_status: "EXACT",
      target_type: "Asset",
      target_id: "asset:test",
      symbol: "TEST",
      venue_type: "dex",
    },
    market: tokenMarketBlockFixture({
      market_status: "stale",
      price_change_status: "insufficient_history",
    }),
    flow: {
      window: "1h",
      mentions: 3,
      watched_mentions: 1,
      previous_mentions: 1,
      mention_delta: 2,
      stream_dominance: 0,
      baseline_status: "ready",
      baseline_sample_count: 30,
    },
    social_heat: {
      ...scoreBlock(
        "token_factor_snapshot_v3_social_attention:social_heat",
        76,
        "social_heat.mentions_1h",
      ),
      window: "1h",
      mentions: 3,
      mentions_5m: 1,
      mentions_1h: 3,
      mentions_4h: 5,
      mentions_24h: 8,
      weighted_mentions: 3,
      previous_mentions: 1,
      mention_delta: 2,
      stream_share: 0.1,
      watched_share: 0.33,
      status: "rising",
    },
    discussion_quality: {
      ...scoreBlock(
        "token_factor_snapshot_v3_social_attention:discussion_quality",
        64,
        "semantic_catalyst.impact_mean",
      ),
      evidence_specificity: 0.6,
      avg_post_quality: 64,
      avg_attribution_confidence: 0.9,
      duplicate_text_share: 0.1,
      informative_post_count: 2,
      watched_source_count: 1,
    },
    propagation: {
      ...scoreBlock(
        "token_factor_snapshot_v3_social_attention:propagation",
        58,
        "social_propagation.independent_authors",
      ),
      independent_authors: 3,
      effective_authors: 2.5,
      new_authors: 3,
      top_author_share: 0.4,
      duplicate_text_share: 0.1,
      author_entropy: 1,
      phase: "ignition",
      top_authors: [],
    },
    tradeability: {
      ...scoreBlock("token_factor_snapshot_v3_social_attention:gates", 60, "data_health.market"),
      identity_tradeable: true,
      market_fresh: false,
      market_cap_present: false,
      liquidity_present: true,
      pool_present: false,
      hard_risks: ["market_freshness_missing"],
    },
    timing: {
      score: 42,
      score_version: "token_factor_snapshot_v3_social_attention:timing",
      status: "neutral",
      chase_risk: false,
      reasons: ["timing_risk.price_change_since_social_pct"],
      risks: [],
      contributions: [
        { feature: "timing_risk.price_change_since_social_pct", value: 42, reason: "ready" },
      ],
      risk_caps: [],
    },
    opportunity: {
      ...scoreBlock(
        "token_factor_snapshot_v3_social_attention:composite",
        67,
        "factor_family_score",
      ),
      decision: "watch",
      hard_risks: ["legacy_should_not_win"],
      components: { heat: 76, quality: 64, propagation: 58, timing: 42 },
    },
    watch: {
      status: "public_only",
      direct_mentions: 0,
      direct_authors: 0,
      seed_link_count: 0,
      reasons: [],
      risks: [],
    },
    factor_data_health: { identity: "ready", market: "partial", social: "ready", alpha: "partial" },
    factor_gates: {
      eligible_for_high_alert: false,
      max_decision: "watch",
      blocked_reasons: ["market_freshness_missing"],
      risk_reasons: ["thin_author_set"],
    },
    factor_normalization: {
      status: "ready",
      cohort: {},
      factor_ranks: {},
      alpha_rank: 7,
      cohort_size: 42,
    },
    evidence_total_count: 3,
    posts_query: { window: "1h", scope: "all", range: "current_window" },
    timeline_query: { window: "1h", scope: "all" },
  };
}

function scoreBlock(scoreVersion: string, score: number, feature: string) {
  return {
    score,
    score_version: scoreVersion,
    reasons: [feature],
    risks: [],
    contributions: [{ feature, value: score, reason: "ready" }],
    risk_caps: [],
  };
}
