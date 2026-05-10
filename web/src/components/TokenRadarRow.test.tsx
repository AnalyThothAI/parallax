import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TokenFlowItem } from "../api/types";

import { TokenRadarRow } from "./TokenRadarRow";

afterEach(() => cleanup());

describe("TokenRadarRow", () => {
  it("does not render unresolved intent ids as address-like token subtitles", () => {
    render(<TokenRadarRow item={unresolvedSymbolOnly()} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText("$SLOP")).toBeInTheDocument();
    expect(
      screen.getByText("symbol-only · 候选价格过期 · 2 candidates · found:2"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/8ff41158.*e70faa/i)).not.toBeInTheDocument();
  });
});

function unresolvedSymbolOnly(): TokenFlowItem {
  return {
    identity: {
      identity_key: "8ff41158250b70866f20284037a06ed483d97883fd0eaa4ac11932f4b3e70faa",
      identity_status: "AMBIGUOUS",
      target_type: null,
      target_id: null,
      asset_id: null,
      chain: null,
      address: null,
      symbol: "SLOP",
      resolution_reasons: ["SYMBOL_CANDIDATES_STALE"],
      candidate_count: 2,
      discovery_status: "found:2",
    },
    market: { market_status: "missing", price_change_status: "missing" },
    flow: {
      window: "5m",
      mentions: 1,
      watched_mentions: 0,
      previous_mentions: 0,
      mention_delta: 1,
      stream_dominance: 1,
      baseline_status: "insufficient_history",
      baseline_sample_count: 0,
    },
    social_heat: {
      score_version: "social_heat_v1",
      score: 44,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      window: "5m",
      mentions: 1,
      mentions_5m: 1,
      mentions_1h: 1,
      mentions_4h: 1,
      mentions_24h: 1,
      weighted_mentions: 1,
      previous_mentions: 0,
      mention_delta: 1,
      stream_share: 1,
      watched_share: 0,
      status: "insufficient_history",
    },
    discussion_quality: {
      score_version: "discussion_quality_v1",
      score: 43,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      evidence_specificity: 0,
      avg_post_quality: 43,
      avg_attribution_confidence: 0,
      duplicate_text_share: 0,
      informative_post_count: 1,
      watched_source_count: 0,
    },
    propagation: {
      score_version: "propagation_v1",
      score: 50,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      independent_authors: 1,
      effective_authors: 1,
      new_authors: 1,
      top_author_share: 1,
      duplicate_text_share: 0,
      author_entropy: 0,
      phase: "seed",
      top_authors: [],
    },
    tradeability: {
      score_version: "tradeability_v1",
      score: 0,
      reasons: [],
      risks: ["identity_not_tradeable"],
      contributions: [],
      risk_caps: [],
      identity_tradeable: false,
      market_fresh: false,
      market_cap_present: false,
      liquidity_present: false,
      pool_present: false,
    },
    timing: {
      score_version: "timing_v4",
      score: 0,
      status: "market_unavailable",
      chase_risk: false,
      reasons: [],
      risks: ["no_resolved_target"],
      market_observation_status: "no_resolved_target",
    },
    opportunity: {
      score_version: "social_opportunity_v3",
      score: 44,
      decision: "investigate",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      components: { heat: 44, quality: 43, propagation: 50, tradeability: 0, timing: 0 },
    },
    watch: {
      status: "seed",
      direct_mentions: 1,
      direct_authors: 1,
      seed_link_count: 0,
      top_seed: null,
      reasons: [],
      risks: [],
    },
    evidence_total_count: 1,
    posts_query: {
      target_type: null,
      target_id: null,
      window: "5m",
      scope: "all",
      range: "current_window",
    },
    timeline_query: { target_type: null, target_id: null, window: "5m", scope: "all" },
  };
}
