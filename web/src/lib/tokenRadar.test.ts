import { describe, expect, it } from "vitest";
import type { AssetFlowRow } from "../api/types";
import { tokenRadarRowToTokenItem } from "./tokenRadar";

describe("token radar factor snapshot mapper", () => {
  it("maps production hard-cut rows from factor_snapshot instead of legacy score fields", () => {
    const item = tokenRadarRowToTokenItem(productionFactorSnapshotRow(), "1h", "all");

    expect(item.identity.symbol).toBe("ZEC");
    expect(item.identity.target_type).toBe("CexToken");
    expect(item.flow.mentions).toBe(2);
    expect(item.social_heat.score).toBe(55);
    expect(item.discussion_quality.score).toBe(58);
    expect(item.tradeability.score).toBe(75);
    expect(item.opportunity.score).toBe(78);
    expect(item.opportunity.decision).toBe("driver");
    expect(item.evidence_total_count).toBe(2);
  });
});

function productionFactorSnapshotRow(): AssetFlowRow {
  return {
    intent: { intent_id: "intent-zec", display_symbol: "ZEC", display_name: null, evidence: [] },
    target: {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      symbol: "ZEC",
      native_market_id: "ZEC-USDT",
      feed_type: "SPOT"
    },
    attention: {
      mentions_1h: 2,
      mentions_4h: 6,
      mentions_5m: 0,
      mentions_24h: 12,
      latest_seen_ms: 1_778_425_132_800,
      unique_authors: 2,
      watched_mentions: 1
    },
    market: {
      market_status: "fresh",
      volume_24h_usd: 10_482_890.08,
      native_market_id: "ZEC-USDT",
      target_market_type: "cex"
    },
    price: {
      market_status: "fresh",
      volume_24h_usd: 10_482_890.08,
      native_market_id: "ZEC-USDT",
      target_market_type: "cex"
    },
    resolution: {},
    score: {
      rank_score: 78,
      family_scores: {
        timing: 99,
        identity: 100,
        market_quality: 75,
        social_quality: 58,
        social_attention: 55,
        social_semantics: 84
      },
      recommended_decision: "high_alert"
    },
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v1",
      subject: {
        target_type: "CexToken",
        target_id: "cex_token:ZEC",
        symbol: "ZEC",
        chain: null,
        address: null
      },
      families: {
        social_attention: {
          score: 55,
          facts: {
            mentions_5m: 0,
            mentions_1h: 2,
            mentions_4h: 6,
            mentions_24h: 12,
            unique_authors: 2,
            watched_mentions: 1,
            latest_seen_ms: 1_778_425_132_800
          },
          factors: {
            mentions_1h: factor("social_attention", "mentions_1h", 2, 46),
            unique_authors: factor("social_attention", "unique_authors", 2, 46),
            watched_mentions: factor("social_attention", "watched_mentions", 1, 50)
          },
          data_health: "ready"
        },
        social_quality: {
          score: 58,
          facts: {
            mentions: 2,
            independent_authors: 2,
            duplicate_text_share: 0,
            informative_post_count: 2
          },
          factors: {
            mentions: factor("social_quality", "mentions", 2, 36),
            independent_authors: factor("social_quality", "independent_authors", 2, 46)
          },
          data_health: "ready"
        },
        social_semantics: {
          score: 84,
          facts: { impact_mean: 0.85, novelty_mean: 0.6, confidence_mean: 0.9, direction_counts: { bullish: 1 } },
          factors: { impact_mean: factor("social_semantics", "impact_mean", 0.85, 85) },
          data_health: "ready"
        },
        market_quality: {
          score: 75,
          facts: {
            market_status: "fresh",
            volume_24h_usd: 10_482_890.08,
            native_market_id: "ZEC-USDT",
            target_market_type: "cex"
          },
          factors: {
            market_status: factor("market_quality", "market_status", "fresh", 100),
            volume_24h_usd: factor("market_quality", "volume_24h_usd", 10_482_890.08, 100)
          },
          data_health: "partial"
        },
        timing: {
          score: 99,
          facts: {
            social_signal_start_ms: 1_778_423_360_921,
            price_change_since_social_pct: 0.00131,
            price_change_before_social_pct: 0.001396
          },
          factors: {
            price_change_since_social_pct: factor("timing", "price_change_since_social_pct", 0.00131, 99)
          },
          data_health: "ready"
        }
      },
      hard_gates: {
        eligible_for_high_alert: true,
        blocked_reasons: []
      },
      composite: {
        rank_score: 78,
        recommended_decision: "high_alert",
        family_scores: {
          timing: 99,
          identity: 100,
          market_quality: 75,
          social_quality: 58,
          social_attention: 55,
          social_semantics: 84
        }
      },
      provenance: {
        source_event_ids: ["event-1", "event-2"],
        computed_at_ms: 1_778_426_470_167
      }
    },
    decision: "high_alert",
    data_health: { factor_snapshot: "ready", market: "partial", identity: "ready" },
    source_event_ids: ["event-1", "event-2"]
  } as unknown as AssetFlowRow;
}

function factor(family: string, key: string, rawValue: unknown, score: number) {
  return {
    family,
    key,
    raw_value: rawValue,
    score,
    confidence: 0.95,
    data_health: "ready",
    source_refs: [],
    risk_flags: [],
    hard_gate: null
  };
}
