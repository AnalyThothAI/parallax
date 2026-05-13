import { describe, expect, it } from "vitest";

import type { AssetFlowRow } from "../api/types";

import { tokenRadarRowToTokenItem } from "./tokenRadar";

const PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933";

const legacySnapshotVersion = (version: string) =>
  ["token", "factor", "snapshot", version].join("_");
const legacySnapshotV2Alpha = () =>
  ["token", "factor", "snapshot", "v2", "alpha", "gated"].join("_");
const legacyGateKey = () => ["hard", "gates"].join("_");

describe("token radar factor snapshot mapper", () => {
  it("rejects legacy v1 factor snapshots", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot!,
      schema_version: legacySnapshotVersion("v1"),
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.schema_version/,
    );
  });

  it("rejects v2 alpha-gated factor snapshots", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot!,
      schema_version: legacySnapshotV2Alpha(),
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.schema_version/,
    );
  });

  it("rejects v2 snapshots with legacy gate blocks", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot!,
      [legacyGateKey()]: { eligible_for_high_alert: true, blocked_reasons: [] },
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      new RegExp(`factor_snapshot\\.${legacyGateKey()}`),
    );
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
    expect(item.market.market_status).toBe("live");
    expect(item.market.snapshot_received_at_ms).toBe(1_778_426_440_000);
  });

  it("preserves token profile facts from asset flow rows", () => {
    const profile = {
      status: "ready",
      provider: "gmgn",
      observed_at_ms: 1_778_426_440_000,
      identity: {
        symbol: "ZEC",
        name: "Zcash",
        logo_url: "https://cdn.example.test/zec.png",
        banner_url: null,
        description: "Privacy coin profile facts.",
      },
      links: {
        website_url: "https://z.cash",
        twitter_url: "https://x.com/zcash",
        twitter_username: "zcash",
        telegram_url: null,
        gmgn_url: "https://gmgn.ai/cex/ZEC",
        geckoterminal_url: null,
      },
      source: {
        provider: "gmgn",
        raw_available: true,
        last_error: null,
      },
    };
    const row = productionFactorSnapshotRow() as AssetFlowRow & { profile: typeof profile };
    row.profile = profile;

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect((item as { profile?: unknown }).profile).toEqual(profile);
  });

  it("normalizes CEX venue identity from pricefeed-only production rows", () => {
    const row = productionFactorSnapshotRow();
    delete row.target!.native_market_id;
    delete row.target!.feed_type;
    row.factor_snapshot!.subject = {
      ...row.factor_snapshot!.subject,
      pricefeed_id: "pricefeed:cex:okx:swap:ZEC-USDT-SWAP",
    };
    row.live_market = {
      ...row.live_market,
      provider: "okx_cex",
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.identity.exchange).toBe("okx");
    expect(item.identity.inst_id).toBe("ZEC-USDT-SWAP");
    expect(item.identity.inst_type).toBe("SWAP");
  });

  it("rejects rows missing anchor_price even when factor snapshot market contains price", () => {
    const row = productionFactorSnapshotRow() as Partial<AssetFlowRow> &
      Pick<AssetFlowRow, "factor_snapshot">;
    delete row.anchor_price;
    row.factor_snapshot!.market = {
      ...(row.factor_snapshot!.market ?? {}),
      price_usd: 999,
      market_cap_usd: 999_000_000,
    };

    expect(() => tokenRadarRowToTokenItem(row as AssetFlowRow, "1h", "all")).toThrow(
      /anchor_price/,
    );
  });

  it("does not read live price from factor snapshot market facts", () => {
    const row = productionFactorSnapshotRow();
    row.live_market = {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      status: "live",
      price_usd: 0.104,
      price_basis: "usd",
      market_cap_usd: 51_000_000,
      liquidity_usd: null,
      holders: null,
      volume_24h_usd: null,
      observed_at_ms: 1_778_426_440_000,
      received_at_ms: 1_778_426_440_000,
      age_ms: 30_000,
      provider: "okx_cex",
    };
    row.factor_snapshot!.market = {
      ...(row.factor_snapshot!.market ?? {}),
      price_usd: 999,
      market_cap_usd: 999_000_000,
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.price).toBe(0.104);
    expect(item.market.market_cap).toBeNull();
    expect(item.market.market_status).toBe("live");
    expect(item.market.snapshot_age_ms).toBe(30_000);
  });

  it("keeps usable market cap for chain asset rows", () => {
    const row = productionChainAssetRow();

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.identity.target_type).toBe("Asset");
    expect(item.market.price).toBe(0.104);
    expect(item.market.market_cap).toBe(51_000_000);
    expect(item.market.market_cap_status).toBe("live");
  });

  it("uses anchored GMGN market metadata for chain asset rows when live stream is missing", () => {
    const row = productionChainAssetRow();
    row.live_market = {
      ...row.live_market,
      status: "missing",
      price_usd: null,
      price_quote: null,
      market_cap_usd: null,
      liquidity_usd: null,
      holders: null,
      volume_24h_usd: null,
      provider: null,
      observed_at_ms: null,
      received_at_ms: null,
      age_ms: null,
    };
    row.factor_snapshot!.market = {
      ...row.factor_snapshot!.market,
      provider: "gmgn_dex_quote",
      market_cap_usd: 33_000_000,
      liquidity_usd: 1_800_000,
      holders: 22_000,
      volume_24h_usd: 9_100_000,
    };
    row.anchor_price = {
      ...row.anchor_price,
      provider: "gmgn_dex_quote",
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.price).toBe(0.1);
    expect(item.market.provider).toBe("gmgn_dex_quote");
    expect(item.market.market_cap).toBe(33_000_000);
    expect(item.market.liquidity).toBe(1_800_000);
    expect(item.market.holder_count).toBe(22_000);
    expect(item.market.volume_24h).toBe(9_100_000);
    expect(item.tradeability.market_cap_present).toBe(true);
    expect(item.tradeability.liquidity_present).toBe(true);
  });

  it("does not read market display deltas from timing facts", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot!.families.timing_risk.facts = {
      ...(row.factor_snapshot!.families.timing_risk.facts ?? {}),
      price_change_since_social_pct: 9.99,
      price_change_before_social_pct: 8.88,
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.price_change_since_social_pct).toBeCloseTo((35.42 - 34) / 34);
    expect(item.market.price_change_before_social_pct).toBeNull();
    expect(item.timing.price_change_since_social_pct).toBeCloseTo((35.42 - 34) / 34);
    expect(item.timing.price_change_before_social_pct).toBeNull();
    expect(item.market.price_change_status).toBe("ready");
  });

  it("derives tradeability market freshness from data_health.market only", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot!.data_health.market = "missing";
    row.live_market = {
      ...row.live_market,
      status: "live",
      price_usd: 35.42,
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.tradeability.market_fresh).toBe(false);
    expect(item.tradeability.contributions).toContainEqual({
      feature: "data_health.market",
      value: 0,
      reason: "missing",
    });
  });

  it("derives UI market status from live_market without falling back to factor snapshot market", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot!.market = {
      ...row.factor_snapshot!.market,
      market_status: "anchored",
    };
    row.live_market = {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      status: "stale",
      price_usd: 35.42,
      price_basis: "usd",
      observed_at_ms: 1_778_426_440_000,
      received_at_ms: 1_778_426_440_000,
      age_ms: 86_400_000,
      provider: "okx_cex",
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
    anchor_price: {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      status: "ready",
      price_usd: 34,
      price_quote: 34,
      quote_symbol: "USDT",
      price_basis: "quote_as_usd",
      provider: "okx",
      anchor_observed_at_ms: 1_778_423_360_921,
      event_received_at_ms: 1_778_423_360_921,
      anchor_lag_ms: 0,
    },
    live_market: {
      target_type: "CexToken",
      target_id: "cex_token:ZEC",
      status: "live",
      price_usd: 35.42,
      price_quote: 35.42,
      quote_symbol: "USDT",
      price_basis: "quote_as_usd",
      market_cap_usd: null,
      liquidity_usd: null,
      holders: null,
      volume_24h_usd: 10_482_890.08,
      observed_at_ms: 1_778_426_440_000,
      received_at_ms: 1_778_426_440_000,
      age_ms: 30_000,
      provider: "okx_cex",
    },
    resolution: {},
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v3_social_attention",
      subject: {
        target_type: "CexToken",
        target_id: "cex_token:ZEC",
        symbol: "ZEC",
        chain: null,
        address: null,
      },
      market: {
        market_status: "anchored",
        price_change_status: "live_not_persisted",
        provider: "okx",
        anchor_price_usd: 34,
        anchor_price_quote: 34,
        anchor_quote_symbol: "USDT",
        anchor_price_basis: "quote_as_usd",
        anchor_observed_at_ms: 1_778_423_360_921,
        social_signal_start_ms: 1_778_423_360_921,
        anchor_lag_ms: 0,
        event_price_readiness: { status: "ready" },
      },
      gates: {
        eligible_for_high_alert: true,
        max_decision: "high_alert",
        blocked_reasons: [],
        risk_reasons: [],
      },
      data_health: { identity: "ready", market: "ready", social: "ready", alpha: "ready" },
      families: {
        social_heat: {
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
            mentions_1h: factor("social_heat", "mentions_1h", 2, 46),
            unique_authors: factor("social_heat", "unique_authors", 2, 46),
            watched_mentions: factor("social_heat", "watched_mentions", 1, 50),
          },
          data_health: "ready",
        },
        social_propagation: {
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
            mentions: factor("social_propagation", "mentions", 2, 36),
            independent_authors: factor("social_propagation", "independent_authors", 2, 46),
          },
          data_health: "ready",
        },
        semantic_catalyst: {
          raw_score: 84,
          score: 84,
          weight: 0.25,
          facts: {
            impact_mean: 0.85,
            novelty_mean: 0.6,
            confidence_mean: 0.9,
            direction_counts: { bullish: 1 },
          },
          factors: { impact_mean: factor("semantic_catalyst", "impact_mean", 0.85, 85) },
          data_health: "ready",
        },
        timing_risk: {
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
              "timing_risk",
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
          timing_risk: 99,
          social_propagation: 58,
          social_heat: 55,
          semantic_catalyst: 84,
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

function productionChainAssetRow(): AssetFlowRow {
  const row = productionFactorSnapshotRow();
  row.intent = {
    intent_id: "intent-pepe",
    display_symbol: "PEPE",
    display_name: null,
    evidence: [],
  };
  row.target = {
    target_type: "Asset",
    target_id: `asset:eip155:1:erc20:${PEPE}`,
    symbol: "PEPE",
    chain_id: "eip155:1",
    address: PEPE,
  };
  row.anchor_price = {
    ...row.anchor_price,
    target_type: "Asset",
    target_id: `asset:eip155:1:erc20:${PEPE}`,
    price_usd: 0.1,
    price_quote: null,
    quote_symbol: "USD",
    price_basis: "usd",
  };
  row.live_market = {
    target_type: "Asset",
    target_id: `asset:eip155:1:erc20:${PEPE}`,
    status: "live",
    price_usd: 0.104,
    price_quote: null,
    quote_symbol: "USD",
    price_basis: "usd",
    market_cap_usd: 51_000_000,
    liquidity_usd: 5_000_000,
    holders: 12_000,
    volume_24h_usd: 1_200_000,
    observed_at_ms: 1_778_426_440_000,
    received_at_ms: 1_778_426_440_000,
    age_ms: 30_000,
    provider: "okx_dex",
  };
  row.factor_snapshot!.subject = {
    target_type: "Asset",
    target_id: `asset:eip155:1:erc20:${PEPE}`,
    symbol: "PEPE",
    chain: "eip155:1",
    address: PEPE,
  };
  return row;
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
