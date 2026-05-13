import type { MarketContext, MarketObservationSnapshot, TokenMarketBlock } from "../api/types";

export function marketObservationFixture(
  overrides: Partial<MarketObservationSnapshot> = {},
): MarketObservationSnapshot {
  return {
    target_type: "Asset",
    target_id: "asset:test",
    source: "event_anchor",
    provider: "okx",
    pricefeed_id: "pricefeed:test",
    price_usd: 1,
    price_quote: 1,
    quote_symbol: "USD",
    price_basis: "usd",
    market_cap_usd: 1_000_000,
    liquidity_usd: 100_000,
    holders: 1_000,
    volume_24h_usd: 250_000,
    open_interest_usd: null,
    observed_at_ms: 1_700_000_000_000,
    received_at_ms: 1_700_000_000_000,
    raw_payload_hash: null,
    ...overrides,
  };
}

export function marketContextFixture(overrides: Partial<MarketContext> = {}): MarketContext {
  const eventAnchor =
    overrides.event_anchor === undefined
      ? marketObservationFixture({ source: "event_anchor" })
      : overrides.event_anchor;
  const decisionLatest =
    overrides.decision_latest === undefined
      ? marketObservationFixture({ source: "decision_latest" })
      : overrides.decision_latest;
  return {
    event_anchor: eventAnchor,
    decision_latest: decisionLatest,
    readiness: {
      anchor_status: eventAnchor ? "ready" : "missing",
      latest_status: decisionLatest ? "live" : "missing",
      dex_floor_status: decisionLatest ? "ready" : "missing_fields",
      missing_fields: decisionLatest ? [] : ["holders", "liquidity_usd", "market_cap_usd"],
      stale_fields: [],
      ...overrides.readiness,
    },
  };
}

export function tokenMarketBlockFixture(
  overrides: Partial<TokenMarketBlock> = {},
): TokenMarketBlock {
  const context = marketContextFixture({
    event_anchor: overrides.event_anchor,
    decision_latest: overrides.decision_latest,
    readiness: overrides.readiness,
  });
  const latest = context.decision_latest;
  const anchor = context.event_anchor;
  return {
    ...context,
    market_status: "fresh",
    price: latest?.price_usd ?? anchor?.price_usd ?? null,
    price_status: latest ? "live" : "missing",
    market_cap: latest?.market_cap_usd ?? null,
    market_cap_status: latest?.market_cap_usd == null ? "missing" : "ready",
    liquidity: latest?.liquidity_usd ?? null,
    liquidity_status: latest?.liquidity_usd == null ? "missing" : "ready",
    pool_status: latest ? "ready" : "missing",
    holder_count: latest?.holders ?? null,
    holder_count_status: latest?.holders == null ? "missing" : "ready",
    volume_24h: latest?.volume_24h_usd ?? null,
    volume_24h_status: latest?.volume_24h_usd == null ? "missing" : "ready",
    provider: latest?.provider ?? anchor?.provider ?? null,
    snapshot_age_ms: 0,
    snapshot_received_at_ms: latest?.received_at_ms ?? anchor?.received_at_ms ?? null,
    social_signal_start_ms: anchor?.observed_at_ms ?? null,
    reference_ms: latest?.observed_at_ms ?? anchor?.observed_at_ms ?? null,
    price_at_social_start: anchor?.price_usd ?? null,
    price_at_reference: latest?.price_usd ?? null,
    price_change_since_social_pct: null,
    price_before_social_start: null,
    price_change_before_social_pct: null,
    market_observation_status: context.readiness.anchor_status === "ready" ? "ready" : "pending",
    price_change_status: latest && anchor ? "ready" : "pending_observation",
    ...overrides,
  };
}
