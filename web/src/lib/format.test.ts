import { describe, expect, it } from "vitest";

import type { TokenFlowItem } from "../api/types";

import {
  compactNumber,
  eventHandle,
  formatPercentShare,
  formatPropagationPhase,
  formatRelativeTime,
  formatRisk,
  formatScoreDelta,
  formatSignedPercent,
  formatTokenPriceUsd,
  formatTimingStatus,
  formatUsdCompact,
  tokenLabel,
} from "./format";

describe("format helpers", () => {
  it("compacts large numbers for dense cockpit cells", () => {
    expect(compactNumber(1250)).toBe("1.3K");
    expect(compactNumber(1_250_000)).toBe("1.3M");
  });

  it("formats relative milliseconds without locale noise", () => {
    expect(formatRelativeTime(1_000, 31_000)).toBe("30s");
    expect(formatRelativeTime(1_000, 181_000)).toBe("3m");
  });

  it("formats normalized mindshare as a compact percent", () => {
    expect(formatPercentShare(0.5)).toBe("50%");
    expect(formatPercentShare(0.0123)).toBe("1.2%");
  });

  it("formats market cap and signed price changes for radar cells", () => {
    expect(formatUsdCompact(15_200)).toBe("$15K");
    expect(formatSignedPercent(0.124)).toBe("+12%");
    expect(formatSignedPercent(-0.084)).toBe("-8.4%");
    expect(formatSignedPercent(null)).toBe("-");
  });

  it("formats token prices without rounding away tradable decimals", () => {
    expect(formatTokenPriceUsd(2.753)).toBe("$2.75");
    expect(formatTokenPriceUsd(0.24668459858168806)).toBe("$0.2467");
    expect(formatTokenPriceUsd(0.00001360704303591779)).toBe("$0.00001361");
    expect(formatTokenPriceUsd(0.0000000006522)).toBe("$6.52e-10");
    expect(formatTokenPriceUsd(null)).toBe("-");
  });

  it("normalizes event handles and token labels", () => {
    expect(eventHandle({ event_id: "1", author: { handle: "@Toly" } })).toBe("toly");
    expect(tokenLabel(sampleToken())).toBe("$PEPE");
  });

  it("formats social heat rebuild labels", () => {
    expect(formatTimingStatus("neutral")).toBe("中性");
    expect(formatTimingStatus("chase_risk")).toBe("追高风险");
    expect(formatPropagationPhase("expansion")).toBe("扩散");
    expect(formatRisk("author_concentration_high")).toBe("作者集中");
    expect(formatScoreDelta(11)).toBe("+11");
  });
});

function sampleToken(): TokenFlowItem {
  return {
    identity: {
      identity_key: "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
      identity_status: "EXACT",
      target_type: "Asset",
      target_id: "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
      asset_id: "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
      chain: "eip155:1",
      address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
      symbol: "PEPE",
    },
    market: { market_status: "fresh", price_change_status: "insufficient_history" },
    flow: {
      window: "5m",
      mentions: 1,
      watched_mentions: 1,
      previous_mentions: 0,
      mention_delta: 1,
      stream_dominance: 1,
      baseline_status: "insufficient_history",
      baseline_sample_count: 0,
    },
    social_heat: {
      score_version: "social_heat_v1",
      score: 50,
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
      watched_share: 1,
      status: "new_burst",
    },
    discussion_quality: {
      score_version: "discussion_quality_v1",
      score: 50,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      evidence_specificity: 1,
      avg_post_quality: 50,
      avg_attribution_confidence: 1,
      duplicate_text_share: 0,
      informative_post_count: 1,
      watched_source_count: 1,
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
      score: 50,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      identity_tradeable: true,
      market_fresh: true,
      market_cap_present: false,
      liquidity_present: false,
      pool_present: false,
    },
    timing: {
      score_version: "timing_v4",
      score: 50,
      status: "neutral",
      chase_risk: false,
      reasons: [],
      risks: [],
    },
    opportunity: {
      score_version: "social_opportunity_v3",
      score: 50,
      decision: "watch",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      components: {
        heat: 50,
        quality: 50,
        propagation: 50,
        tradeability: 50,
        timing: 50,
      },
    },
    watch: {
      status: "direct_watch",
      direct_mentions: 1,
      direct_authors: 1,
      seed_link_count: 0,
      top_seed: null,
      reasons: [],
      risks: [],
    },
    evidence_total_count: 0,
    posts_query: {
      target_type: "Asset",
      target_id: "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
      window: "5m",
      scope: "all",
      range: "current_window",
    },
    timeline_query: {
      target_type: "Asset",
      target_id: "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
      window: "5m",
      scope: "all",
    },
  };
}
