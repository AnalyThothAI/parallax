import { describe, expect, it } from "vitest";

import type { AssetFlowRow, MarketContext } from "../api/types";

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
      ...row.factor_snapshot,
      schema_version: legacySnapshotVersion("v1"),
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.schema_version/,
    );
  });

  it("rejects v2 alpha-gated factor snapshots", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot,
      schema_version: legacySnapshotV2Alpha(),
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.schema_version/,
    );
  });

  it("rejects snapshots with legacy gate blocks", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot = {
      ...row.factor_snapshot,
      [legacyGateKey()]: { eligible_for_high_alert: true, blocked_reasons: [] },
    } as unknown as AssetFlowRow["factor_snapshot"];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      new RegExp(`factor_snapshot\\.${legacyGateKey()}`),
    );
  });

  it("requires composite recommended_decision instead of falling back to row decision", () => {
    const row = productionFactorSnapshotRow();
    delete (row.factor_snapshot.composite as Record<string, unknown>).recommended_decision;
    (row as unknown as Record<string, unknown>).decision = "high_alert";

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.composite\.recommended_decision/,
    );
  });

  it("rejects snapshots with empty provenance source_event_ids", () => {
    const row = productionFactorSnapshotRow();
    row.factor_snapshot.provenance.source_event_ids = [];

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(
      /factor_snapshot\.provenance\.source_event_ids/,
    );
  });

  it("maps production hard-cut rows from factor_snapshot and market roles", () => {
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
    expect(item.market.event_anchor?.price_usd).toBe(34);
    expect(item.market.decision_latest?.price_usd).toBe(35.42);
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
    row.factor_snapshot.subject = {
      ...row.factor_snapshot.subject,
      pricefeed_id: "pricefeed:cex:okx:swap:ZEC-USDT-SWAP",
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.identity.exchange).toBe("okx");
    expect(item.identity.inst_id).toBe("ZEC-USDT-SWAP");
    expect(item.identity.inst_type).toBe("SWAP");
  });

  it("rejects rows missing material market context", () => {
    const row = productionFactorSnapshotRow() as Partial<AssetFlowRow> &
      Pick<AssetFlowRow, "factor_snapshot">;
    delete row.market;

    expect(() => tokenRadarRowToTokenItem(row as AssetFlowRow, "1h", "all")).toThrow(/market/);
  });

  it("keeps usable market cap for chain asset rows", () => {
    const row = productionChainAssetRow();

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.identity.target_type).toBe("Asset");
    expect(item.market.price).toBe(0.104);
    expect(item.market.market_cap).toBe(51_000_000);
    expect(item.market.market_cap_status).toBe("live");
  });

  it("uses event_anchor market metadata for chain asset rows when decision_latest is missing", () => {
    const row = productionChainAssetRow();
    row.market = {
      event_anchor: {
        ...row.market.event_anchor!,
        provider: "gmgn_dex_quote",
        price_usd: 0.1,
        market_cap_usd: 33_000_000,
        liquidity_usd: 1_800_000,
        holders: 22_000,
        volume_24h_usd: 9_100_000,
      },
      decision_latest: null,
      readiness: {
        ...row.market.readiness,
        latest_status: "missing",
      },
    };
    row.factor_snapshot.market = row.market;

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
    row.factor_snapshot.families.timing_risk.facts = {
      ...row.factor_snapshot.families.timing_risk.facts,
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
    row.factor_snapshot.data_health.market = "missing";

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.tradeability.market_fresh).toBe(false);
    expect(item.tradeability.contributions).toContainEqual({
      feature: "data_health.market",
      value: 0,
      reason: "missing",
    });
  });

  it("derives UI market status from decision_latest readiness", () => {
    const row = productionFactorSnapshotRow();
    row.market = {
      ...row.market,
      readiness: {
        ...row.market.readiness,
        latest_status: "stale",
        stale_fields: ["decision_latest"],
      },
      decision_latest: {
        ...row.market.decision_latest!,
        observed_at_ms: 1_778_340_040_000,
      },
    };
    row.factor_snapshot.market = row.market;

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.market_status).toBe("stale");
    expect(item.market.price_status).toBe("stale");
  });
});

function productionFactorSnapshotRow(): AssetFlowRow {
  const market = marketContext({
    targetType: "CexToken",
    targetId: "cex_token:ZEC",
    provider: "okx",
    latestProvider: "okx_cex",
    anchorPrice: 34,
    latestPrice: 35.42,
    quoteSymbol: "USDT",
    priceBasis: "quote_as_usd",
    latestVolume24h: 10_482_890.08,
  });
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
      mentions_window: 2,
      latest_seen_ms: 1_778_425_132_800,
      unique_authors: 2,
      watched_mentions: 1,
      previous_mentions: 0,
      mention_delta: 2,
      mention_delta_pct: null,
      z_score: null,
      z_ewma: null,
      robust_z: null,
      new_burst_score: null,
      stream_share: 0,
      baseline_version: "test",
      baseline_status: "ready",
      baseline_sample_count: 1,
      baseline_nonzero_sample_count: 1,
      zero_slot_count: 0,
    },
    market,
    resolution: { status: "EXACT" },
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v3_social_attention",
      subject: {
        target_type: "CexToken",
        target_id: "cex_token:ZEC",
        symbol: "ZEC",
        chain: null,
        address: null,
      },
      market,
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
        status: "ranked",
        cohort_status: "ready",
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
  };
}

function productionChainAssetRow(): AssetFlowRow {
  const row = productionFactorSnapshotRow();
  const targetId = `asset:eip155:1:erc20:${PEPE}`;
  row.intent = {
    intent_id: "intent-pepe",
    display_symbol: "PEPE",
    display_name: null,
    evidence: [],
  };
  row.target = {
    target_type: "Asset",
    target_id: targetId,
    symbol: "PEPE",
    chain_id: "eip155:1",
    address: PEPE,
  };
  row.market = marketContext({
    targetType: "Asset",
    targetId,
    provider: "gmgn_dex_quote",
    latestProvider: "okx_dex",
    anchorPrice: 0.1,
    latestPrice: 0.104,
    quoteSymbol: "USD",
    priceBasis: "usd",
    latestMarketCap: 51_000_000,
    latestLiquidity: 5_000_000,
    latestHolders: 12_000,
    latestVolume24h: 1_200_000,
  });
  row.factor_snapshot.subject = {
    target_type: "Asset",
    target_id: targetId,
    symbol: "PEPE",
    chain: "eip155:1",
    address: PEPE,
  };
  row.factor_snapshot.market = row.market;
  return row;
}

function marketContext({
  targetType,
  targetId,
  provider,
  latestProvider,
  anchorPrice,
  latestPrice,
  quoteSymbol,
  priceBasis,
  latestMarketCap = null,
  latestLiquidity = null,
  latestHolders = null,
  latestVolume24h = null,
}: {
  targetType: string;
  targetId: string;
  provider: string;
  latestProvider: string;
  anchorPrice: number;
  latestPrice: number;
  quoteSymbol: string;
  priceBasis: string;
  latestMarketCap?: number | null;
  latestLiquidity?: number | null;
  latestHolders?: number | null;
  latestVolume24h?: number | null;
}): MarketContext {
  return {
    event_anchor: {
      target_type: targetType,
      target_id: targetId,
      observed_at_ms: 1_778_423_360_921,
      received_at_ms: 1_778_423_360_921,
      source: "event_anchor",
      provider,
      pricefeed_id: "pf-test",
      price_usd: anchorPrice,
      price_quote: anchorPrice,
      quote_symbol: quoteSymbol,
      price_basis: priceBasis,
      market_cap_usd: null,
      liquidity_usd: null,
      holders: null,
      volume_24h_usd: null,
      open_interest_usd: null,
      raw_payload_hash: null,
    },
    decision_latest: {
      target_type: targetType,
      target_id: targetId,
      observed_at_ms: 1_778_426_440_000,
      received_at_ms: 1_778_426_440_000,
      source: "decision_latest",
      provider: latestProvider,
      pricefeed_id: "pf-test",
      price_usd: latestPrice,
      price_quote: latestPrice,
      quote_symbol: quoteSymbol,
      price_basis: priceBasis,
      market_cap_usd: latestMarketCap,
      liquidity_usd: latestLiquidity,
      holders: latestHolders,
      volume_24h_usd: latestVolume24h,
      open_interest_usd: null,
      raw_payload_hash: null,
    },
    readiness: {
      anchor_status: "ready",
      latest_status: "live",
      dex_floor_status: latestMarketCap === null ? "not_applicable" : "ready",
      missing_fields: [],
      stale_fields: [],
    },
  };
}

function factor(family: string, key: string, rawValue: unknown, score: number) {
  return {
    family,
    key,
    raw_value: rawValue,
    score,
    data_health: "ready",
    reasons: [],
    risk_flags: [],
  };
}
