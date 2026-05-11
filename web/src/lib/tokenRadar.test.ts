import { describe, expect, it } from "vitest";

import type { AssetFlowRow } from "../api/types";

import { tokenRadarRowToTokenItem } from "./tokenRadar";

describe("token radar factor snapshot mapper", () => {
  it("rejects legacy v1 factor snapshots", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot!,
      schema_version: "token_factor_snapshot_v1",
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.schema_version/,
    );
  });

  it("rejects v2 snapshots with legacy hard_gates", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot!,
      hard_gates: { eligible_for_high_alert: true, blocked_reasons: [] },
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(/factor_snapshot\.hard_gates/);
  });

  it("requires composite recommended_decision instead of falling back to row decision", () => {
    const row = productionFactorSnapshotRow();
    delete (row.factor_snapshot!.composite as Record<string, unknown>).recommended_decision;
    (row as unknown as Record<string, unknown>).decision = "high_alert";

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.composite\.recommended_decision/,
    );
  });

  it("rejects v2 snapshots with empty provenance source_event_ids", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot!.provenance.source_event_ids = [];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.provenance\.source_event_ids/,
    );
  });

  it("maps production hard-cut rows from factor_snapshot instead of legacy score fields", () => {
    const item = tokenRadarRowToTokenItem(productionFactorSnapshotRow(), "1h", "all");

    expect(item.identity.symbol).toBe("ZEC");
    expect(item.identity.target_type).toBe("CexToken");
    expect(item.flow.mentions).toBe(2);
    expect(item.social_heat.score).toBe(55);
    expect(item.discussion_quality.score).toBe(84);
    expect(item.propagation.score).toBe(58);
    expect(item.tradeability.market_fresh).toBe(true);
    expect(item.opportunity.score).toBe(78);
    expect(item.opportunity.decision).toBe("driver");
    expect(item.evidence_total_count).toBe(2);
    expect(item.market.price).toBe(35.42);
    expect(item.market.market_status).toBe("fresh");
    expect(item.market.snapshot_received_at_ms).toBe(1_778_426_440_000);
  });

  it("rejects rows missing current_market even when factor snapshot facts contain price", () => {
    const row = productionFactorSnapshotRow() as Partial<AssetFlowRow> &
      Pick<AssetFlowRow, "factor_snapshot">;
    delete row.current_market;
    row.factor_snapshot!.families.timing_response.facts = {
      ...(row.factor_snapshot!.families.timing_response.facts ?? {}),
      price_usd: 999,
      market_cap_usd: 999_000_000,
    };

    expect(() => tokenRadarRowToTokenItem(row as AssetFlowRow, "1h", "all")).toThrow(
      /current_market/,
    );
  });

  it("does not read live price from factor snapshot market facts", () => {
    const row = productionFactorSnapshotRow();
    row.current_market = {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      market_status: "partial",
      fields: {
        price_usd: {
          value: 0.104,
          status: "fresh",
          observed_at_ms: 1_778_426_440_000,
          age_ms: 30_000,
          provider: "okx_cex",
        },
        market_cap_usd: {
          value: 51_000_000,
          status: "stale",
          observed_at_ms: 1_778_340_070_000,
          age_ms: 86_400_000,
          provider: "okx_cex_metadata",
        },
      },
    };
    row.factor_snapshot!.families.timing_response.facts = {
      ...(row.factor_snapshot!.families.timing_response.facts ?? {}),
      price_usd: 999,
      market_cap_usd: 999_000_000,
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.price).toBe(0.104);
    expect(item.market.market_cap).toBe(51_000_000);
    expect(item.market.market_status).toBe("partial");
    expect(item.market.snapshot_age_ms).toBe(30_000);
  });

  it("does not read market display deltas from timing facts", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot!.families.timing_response.facts = {
      ...(row.factor_snapshot!.families.timing_response.facts ?? {}),
      price_change_since_social_pct: 9.99,
      price_change_before_social_pct: 8.88,
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.price_change_since_social_pct).toBeNull();
    expect(item.market.price_change_before_social_pct).toBeNull();
    expect(item.timing.price_change_since_social_pct).toBeNull();
    expect(item.timing.price_change_before_social_pct).toBeNull();
    expect(item.market.price_change_status).toBe("insufficient_history");
  });

  it("derives tradeability market freshness from data_health.market only", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot!.data_health.market = "missing";
    row.current_market = {
      ...row.current_market,
      market_status: "fresh",
      fields: {
        ...row.current_market.fields,
        price_usd: {
          value: 35.42,
          status: "fresh",
          observed_at_ms: 1_778_426_440_000,
          age_ms: 30_000,
          provider: "okx_cex",
        },
      },
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.tradeability.market_fresh).toBe(false);
    expect(item.tradeability.contributions).toContainEqual({
      feature: "data_health.market",
      value: 0,
      reason: "missing",
    });
  });

  it("derives UI market status from field facts without falling back to top-level current_market status", () => {
    const row = productionFactorSnapshotRow();
    row.current_market = {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      market_status: "fresh",
      fields: {
        price_usd: {
          value: 35.42,
          status: "stale",
          observed_at_ms: 1_778_426_440_000,
          age_ms: 86_400_000,
          provider: "okx_cex",
        },
        market_cap_usd: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
        liquidity_usd: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
        holders: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
        volume_24h_usd: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
      },
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.market_status).toBe("stale");
    expect(item.market.price_status).toBe("stale");
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
      feed_type: "SPOT",
    },
    attention: {
      mentions_1h: 2,
      mentions_4h: 6,
      mentions_5m: 0,
      mentions_24h: 12,
      latest_seen_ms: 1_778_425_132_800,
      unique_authors: 2,
      watched_mentions: 1,
    },
    current_market: {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      market_status: "fresh",
      fields: {
        price_usd: {
          value: 35.42,
          status: "fresh",
          observed_at_ms: 1_778_426_440_000,
          age_ms: 30_000,
          provider: "okx_cex",
        },
        volume_24h_usd: {
          value: 10_482_890.08,
          status: "fresh",
          observed_at_ms: 1_778_426_440_000,
          age_ms: 30_000,
          provider: "okx_cex",
        },
        market_cap_usd: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
        liquidity_usd: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
        holders: {
          value: null,
          status: "unsupported",
          observed_at_ms: null,
          age_ms: null,
          provider: "okx_cex",
        },
      },
    },
    resolution: {},
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v2_alpha_gated",
      subject: {
        target_type: "CexToken",
        target_id: "cex_token:ZEC",
        symbol: "ZEC",
        chain: null,
        address: null,
      },
      gates: {
        eligible_for_high_alert: true,
        max_decision: "high_alert",
        blocked_reasons: [],
        risk_reasons: [],
      },
      data_health: { identity: "ready", market: "ready", social: "ready", alpha: "ready" },
      families: {
        attention_heat: {
          raw_score: 55,
          score: 55,
          weight: 0.35,
          facts: {
            mentions_5m: 0,
            mentions_1h: 2,
            mentions_4h: 6,
            mentions_24h: 12,
            unique_authors: 2,
            watched_mentions: 1,
            latest_seen_ms: 1_778_425_132_800,
          },
          factors: {
            mentions_1h: factor("attention_heat", "mentions_1h", 2, 46),
            unique_authors: factor("attention_heat", "unique_authors", 2, 46),
            watched_mentions: factor("attention_heat", "watched_mentions", 1, 50),
          },
          data_health: "ready",
        },
        diffusion_quality: {
          raw_score: 58,
          score: 58,
          weight: 0.3,
          facts: {
            mentions: 2,
            independent_authors: 2,
            duplicate_text_share: 0,
            informative_post_count: 2,
          },
          factors: {
            mentions: factor("diffusion_quality", "mentions", 2, 36),
            independent_authors: factor("diffusion_quality", "independent_authors", 2, 46),
          },
          data_health: "ready",
        },
        semantic_quality: {
          raw_score: 84,
          score: 84,
          weight: 0.25,
          facts: {
            impact_mean: 0.85,
            novelty_mean: 0.6,
            confidence_mean: 0.9,
            direction_counts: { bullish: 1 },
          },
          factors: { impact_mean: factor("semantic_quality", "impact_mean", 0.85, 85) },
          data_health: "ready",
        },
        timing_response: {
          raw_score: 99,
          score: 99,
          weight: 0.1,
          facts: {
            social_signal_start_ms: 1_778_423_360_921,
            price_change_since_social_pct: 0.00131,
            price_change_before_social_pct: 0.001396,
          },
          factors: {
            price_change_since_social_pct: factor(
              "timing_response",
              "price_change_since_social_pct",
              0.00131,
              99,
            ),
          },
          data_health: "ready",
        },
      },
      normalization: {
        status: "ready",
        cohort: { window: "1h" },
        factor_ranks: {},
        alpha_rank: 3,
        cohort_size: 42,
      },
      composite: {
        rank_score: 78,
        recommended_decision: "high_alert",
        family_scores: {
          timing_response: 99,
          diffusion_quality: 58,
          attention_heat: 55,
          semantic_quality: 84,
        },
      },
      provenance: {
        source_event_ids: ["event-1", "event-2"],
        computed_at_ms: 1_778_426_470_167,
      },
    },
    data_health: { factor_snapshot: "ready", market: "partial", identity: "ready" },
    source_event_ids: ["event-1", "event-2"],
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
  };
}
