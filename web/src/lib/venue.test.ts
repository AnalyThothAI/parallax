import { describe, expect, it } from "vitest";

import type { SignalPulseItem, TokenFlowItem } from "../api/types";

import { signalPulseVenueActions, tokenVenueAction } from "./venue";

describe("venue links", () => {
  it("opens OKX spot instruments for CEX assets", () => {
    expect(
      tokenVenueAction(
        token({ venueType: "cex", exchange: "okx", instId: "BTC-USDT", instType: "SPOT" }),
      ),
    ).toEqual({
      label: "OKX",
      url: "https://www.okx.com/trade-spot/btc-usdt",
    });
  });

  it("opens OKX swap instruments for CEX perpetuals", () => {
    expect(
      tokenVenueAction(
        token({ venueType: "cex", exchange: "okx", instId: "TAO-USDT-SWAP", instType: "SWAP" }),
      ),
    ).toEqual({
      label: "OKX",
      url: "https://www.okx.com/trade-swap/tao-usdt-swap",
    });
  });

  it("keeps GMGN links for DEX assets", () => {
    expect(
      tokenVenueAction(
        token({
          venueType: "dex",
          chain: "solana",
          address: "So11111111111111111111111111111111111111112",
        }),
      ),
    ).toEqual({
      label: "GMGN",
      url: "https://gmgn.ai/sol/token/So11111111111111111111111111111111111111112",
    });
  });

  it("opens Signal Pulse DEX targets on GMGN", () => {
    expect(
      signalPulseVenueActions(
        pulse({
          targetType: "Asset",
          targetId: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
        }),
      ),
    ).toEqual([
      {
        label: "GMGN",
        url: "https://gmgn.ai/base/token/0x920738cbe6ddf7399187ffcf85c4b19154123be4",
      },
    ]);
  });

  it("opens Signal Pulse CEX targets on the exact OKX pricefeed instrument", () => {
    expect(
      signalPulseVenueActions(
        pulse({
          targetType: "CexToken",
          targetId: "cex_token:SOL",
          symbol: "SOL",
          marketContext: { pricefeed_id: "pricefeed:cex:okx:spot:SOL-USDT" },
        }),
      ),
    ).toEqual([
      {
        label: "OKX",
        url: "https://www.okx.com/trade-spot/sol-usdt",
      },
    ]);
  });
});

function token(options: {
  venueType: "cex" | "dex";
  exchange?: string | null;
  instId?: string | null;
  instType?: string | null;
  chain?: string | null;
  address?: string | null;
}): TokenFlowItem {
  return {
    identity: {
      identity_key: "asset:test",
      identity_status: "resolved",
      venue_type: options.venueType,
      exchange: options.exchange ?? null,
      inst_id: options.instId ?? null,
      inst_type: options.instType ?? null,
      chain: options.chain ?? null,
      address: options.address ?? null,
      symbol: "BTC",
    },
    market: { market_status: "missing", price_change_status: "missing_market" },
    flow: {
      window: "1h",
      mentions: 1,
      watched_mentions: 0,
      previous_mentions: 0,
      mention_delta: 1,
      baseline_status: "insufficient_history",
      baseline_sample_count: 0,
    },
    social_heat: scoreBlock(),
    discussion_quality: scoreBlock(),
    propagation: {
      ...scoreBlock(),
      independent_authors: 1,
      effective_authors: 1,
      new_authors: 1,
      top_author_share: 1,
      duplicate_text_share: 0,
      author_entropy: 0,
      reproduction_rate: null,
      phase: "seed",
      top_authors: [],
    },
    tradeability: {
      ...scoreBlock(),
      identity_tradeable: true,
      market_fresh: false,
      market_cap_present: false,
      liquidity_present: false,
      pool_present: options.venueType === "dex",
      hard_risks: [],
    },
    timing: {
      ...scoreBlock(),
      status: "market_unavailable",
      social_signal_start_ms: null,
      price_change_since_social_pct: null,
      price_change_before_social_pct: null,
      market_observation_status: "provider_not_found",
      chase_risk: false,
    },
    opportunity: {
      ...scoreBlock(),
      decision: "watch",
      decision_priority: 2,
      hard_risks: [],
      components: { heat: 0, quality: 0, propagation: 0, tradeability: 0, timing: 0 },
    },
    watch: { status: "public_only", direct_mentions: 0, direct_authors: 0 },
    evidence_total_count: 0,
    posts_query: { window: "1h", scope: "all", range: "current_window" },
    timeline_query: { window: "1h", scope: "all" },
  } as unknown as TokenFlowItem;
}

function scoreBlock() {
  return {
    score: 0,
    score_version: "test",
    reasons: [],
    risks: [],
    contributions: [],
    risk_caps: [],
  };
}

function pulse(options: {
  targetType: "Asset" | "CexToken";
  targetId: string;
  symbol?: string | null;
  marketContext?: Record<string, unknown>;
}): SignalPulseItem {
  return {
    candidate_id: "pulse-1",
    candidate_type: "token_target",
    subject_key: options.symbol ?? "token",
    target_type: options.targetType,
    target_id: options.targetId,
    symbol: options.symbol ?? "TOKEN",
    window: "1h",
    scope: "all",
    pulse_status: "token_watch",
    bull_case_zh: [],
    bear_case_zh: [],
    confirmation_triggers_zh: [],
    invalidation_triggers_zh: [],
    top_risks: [],
    gate_reasons: [],
    risk_reasons: [],
    evidence_event_ids: [],
    source_event_ids: [],
    radar_score_json: {},
    market_context_json: options.marketContext ?? {},
    thesis_json: {},
    created_at_ms: 1,
    updated_at_ms: 1,
    playbooks: [],
  } as SignalPulseItem;
}
