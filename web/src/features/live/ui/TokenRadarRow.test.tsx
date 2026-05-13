import type { TokenFlowItem } from "@lib/types";
import { cleanup, render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TokenRadarRow } from "./TokenRadarRow";

afterEach(() => cleanup());

describe("TokenRadarRow", () => {
  it("does not render unresolved intent ids as address-like token subtitles", () => {
    render(
      <TokenRadarRow
        item={unresolvedSymbolOnly()}
        selected={false}
        onOpenSearch={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("$SLOP")).toBeInTheDocument();
    expect(
      screen.getByText("symbol-only · 候选价格过期 · 2 candidates · found:2"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/8ff41158.*e70faa/i)).not.toBeInTheDocument();
  });

  it("renders DEX market cap as the primary market value", async () => {
    const { container } = render(
      <TokenRadarRow
        item={mixedFreshnessToken()}
        selected={false}
        onOpenSearch={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    const row = screen.getByRole("button", { name: "Select token case $TROLL" });
    const searchButton = screen.getByRole("button", { name: "Open Search Intel for $TROLL" });
    const venueLink = screen.getByRole("link", { name: "Open $TROLL on GMGN" });
    expect(searchButton).toBeInTheDocument();
    expect(venueLink.parentElement?.children[0]).toBe(venueLink);
    expect(venueLink.parentElement?.children[1]).toBe(searchButton);
    expect(within(row).getByText("Identity")).toBeInTheDocument();
    expect(within(row).getByText("Official")).toBeInTheDocument();
    expect(within(row).getByText("Community")).toBeInTheDocument();
    expect(within(row).getByText("Narrative")).toBeInTheDocument();
    expect(within(row).getByText("Decision")).toBeInTheDocument();
    const market = row.querySelector('[data-radar-metric="market"]') as HTMLElement;
    expect(market).toHaveTextContent("$51M");
    expect(market).toHaveTextContent("partial");
    expect(market).toHaveTextContent("cap stale");
    expect(market).not.toHaveTextContent("- fresh");
    expect(market).not.toHaveTextContent("$0.104");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("does not fall back to token price for DEX rows without market cap", () => {
    const item = mixedFreshnessToken();
    render(
      <TokenRadarRow
        item={{
          ...item,
          market: {
            ...item.market,
            market_cap: null,
            market_cap_status: "missing",
          },
        }}
        selected={false}
        onOpenSearch={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    const row = screen.getByRole("button", { name: "Select token case $TROLL" });
    const market = row.querySelector('[data-radar-metric="market"]') as HTMLElement;
    expect(market).toHaveTextContent("-");
    expect(market).toHaveTextContent("cap missing");
    expect(market).not.toHaveTextContent("$0.104");
  });

  it("suppresses anchored readiness noise from compact radar cells", () => {
    const item = mixedFreshnessToken();
    render(
      <TokenRadarRow
        item={{
          ...item,
          market: {
            ...item.market,
            market_status: "anchored",
            price_status: "ready",
            market_cap: 236_000,
            market_cap_status: "live",
            liquidity: 9_000,
            liquidity_status: "live",
            price_change_since_social_pct: null,
            price_change_since_first_snapshot_pct: null,
            price_change_status: "live_not_persisted",
          },
        }}
        selected={false}
        onOpenSearch={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    const row = screen.getByRole("button", { name: "Select token case $TROLL" });
    const market = row.querySelector('[data-radar-metric="market"]') as HTMLElement;
    expect(market).toHaveTextContent("$236K");
    expect(market).not.toHaveTextContent("anchored");
    expect(market).not.toHaveTextContent("price ready");
    expect(market).not.toHaveTextContent("cap live");
    expect(market).not.toHaveTextContent("liq live");
    expect(row.querySelector('[data-radar-metric="timing"]')).not.toBeInTheDocument();
    expect(row).not.toHaveTextContent("live not persisted");
  });
});

function mixedFreshnessToken(): TokenFlowItem {
  const item = unresolvedSymbolOnly();
  return {
    ...item,
    identity: {
      ...item.identity,
      identity_key: "asset:dex:eth:0x1111111111111111111111111111111111111111",
      identity_status: "EXACT",
      target_type: "Asset",
      target_id: "asset:dex:eth:0x1111111111111111111111111111111111111111",
      asset_id: "asset:dex:eth:0x1111111111111111111111111111111111111111",
      asset_type: "Asset",
      venue_type: "dex",
      exchange: "gmgn",
      chain: "eth",
      address: "0x1111111111111111111111111111111111111111",
      symbol: "TROLL",
      resolution_reasons: [],
    },
    market: {
      event_anchor: null,
      decision_latest: {
        target_type: "Asset",
        target_id: "asset:dex:eth:0x1111111111111111111111111111111111111111",
        source: "decision_latest",
        price_usd: 0.104,
        market_cap_usd: 51_000_000,
        liquidity_usd: 3_000_000,
        holders: 52_000,
        observed_at_ms: 1_778_426_440_000,
        received_at_ms: 1_778_426_440_000,
        provider: "okx_dex_price",
      },
      readiness: {
        anchor_status: "ready",
        latest_status: "live",
        dex_floor_status: "ready",
        missing_fields: [],
        stale_fields: [],
      },
      market_status: "partial",
      price: 0.104,
      price_status: "fresh",
      market_cap: 51_000_000,
      market_cap_status: "stale",
      liquidity: 3_000_000,
      liquidity_status: "stale",
      holder_count: 52_000,
      holder_count_status: "stale",
      pool_status: "missing",
      snapshot_age_ms: 30_000,
      snapshot_received_at_ms: 1_778_426_440_000,
      provider: "okx_dex_price",
      price_change_status: "insufficient_history",
    },
    timing: {
      ...item.timing,
      status: "neutral",
      risks: [],
      market_observation_status: "partial",
    },
  };
}

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
    market: {
      event_anchor: null,
      decision_latest: null,
      readiness: {
        anchor_status: "missing",
        latest_status: "missing",
        dex_floor_status: "not_applicable",
        missing_fields: [],
        stale_fields: [],
      },
      market_status: "missing",
      price_change_status: "missing",
    },
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
      score_version: "token_factor_snapshot_v3_social_attention:social_heat",
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
      score_version: "token_factor_snapshot_v3_social_attention:discussion_quality",
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
      score_version: "token_factor_snapshot_v3_social_attention:propagation",
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
      score_version: "token_factor_snapshot_v3_social_attention:gates",
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
      score_version: "token_factor_snapshot_v3_social_attention:timing",
      score: 0,
      status: "market_unavailable",
      chase_risk: false,
      reasons: [],
      risks: ["no_resolved_target"],
      market_observation_status: "no_resolved_target",
    },
    opportunity: {
      score_version: "token_factor_snapshot_v3_social_attention:composite",
      score: 44,
      decision: "investigate",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      components: { heat: 44, quality: 43, propagation: 50, timing: 0 },
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
