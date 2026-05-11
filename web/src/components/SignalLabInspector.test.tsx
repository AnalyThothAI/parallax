import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { SignalPulseItem } from "../api/types";

import { SignalLabInspector } from "./SignalLabInspector";

afterEach(() => cleanup());

describe("SignalLabInspector", () => {
  it("shows a venue link for the selected parsed token", () => {
    render(
      <SignalLabInspector
        item={
          {
            candidate_id: "pulse-1",
            candidate_type: "token_target",
            subject_key: "CANCERHAWK",
            target_type: "Asset",
            target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
            symbol: "CANCERHAWK",
            window: "1h",
            scope: "all",
            pulse_status: "token_watch",
            verdict: "token_watch",
            social_phase: "ignition",
            narrative_type: "direct_token",
            candidate_score: 62,
            score_band: "watch",
            evidence_event_ids: [],
            source_event_ids: [],
            factor_snapshot: {
              schema_version: "token_factor_snapshot_v2_alpha_gated",
              subject: {
                target_type: "Asset",
                target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
                symbol: "CANCERHAWK",
                chain: "eip155:8453",
                address: "0x920738cbe6ddf7399187ffcf85c4b19154123be4",
              },
              market: signalPulseMarketFixture(),
              gates: {
                eligible_for_high_alert: false,
                max_decision: "watch",
                blocked_reasons: ["liquidity_below_high_alert_floor"],
                risk_reasons: ["thin_author_set"],
              },
              data_health: {
                identity: "ready",
                market: "partial",
                social: "ready",
                alpha: "ready",
              },
              families: {
                attention_heat: {
                  raw_score: 62,
                  score: 62,
                  weight: 0.35,
                  data_health: "ready",
                  facts: {},
                  factors: {},
                },
                diffusion_quality: {
                  raw_score: 58,
                  score: 58,
                  weight: 0.3,
                  data_health: "ready",
                  facts: {},
                  factors: {},
                },
                semantic_quality: {
                  raw_score: 55,
                  score: 55,
                  weight: 0.25,
                  data_health: "ready",
                  facts: {},
                  factors: {},
                },
                timing_response: {
                  raw_score: 50,
                  score: 50,
                  weight: 0.1,
                  data_health: "partial",
                  facts: {},
                  factors: {},
                },
              },
              normalization: {
                status: "ready",
                cohort: {},
                factor_ranks: {},
                alpha_rank: 8,
                cohort_size: 50,
              },
              composite: {
                rank_score: 62,
                recommended_decision: "watch",
                family_scores: {
                  attention_heat: 62,
                  diffusion_quality: 58,
                  semantic_quality: 55,
                  timing_response: 50,
                },
              },
              provenance: { source_event_ids: ["event-1"], computed_at_ms: 1_700_000_000_000 },
            },
            agent_recommendation: {
              schema_version: "pulse_recommendation_v1",
              recommendation: "watch",
              summary_zh: "summary",
              primary_reasons: [],
              upgrade_conditions: [],
              invalidation_conditions: [],
              residual_risks: [],
            },
            gate: {
              pulse_status: "token_watch",
              candidate_score: 62,
              score_band: "watch",
              blocked_reasons: ["liquidity_below_high_alert_floor"],
            },
            fact_card: { liquidity_usd: 10_000, mentions_1h: 2, unique_authors: 2 },
            created_at_ms: 1_700_000_000_000,
            updated_at_ms: 1_700_000_000_000,
            playbooks: [],
          } satisfies SignalPulseItem
        }
      />,
    );

    expect(
      screen.getByRole("link", { name: "Open selected Signal Pulse token on GMGN" }),
    ).toHaveAttribute(
      "href",
      "https://gmgn.ai/base/token/0x920738cbe6ddf7399187ffcf85c4b19154123be4",
    );
  });

  it("rejects malformed Signal Pulse factor snapshots before rendering raw JSON", () => {
    const item = signalPulseItem();
    item.factor_snapshot.families = {
      ...item.factor_snapshot.families,
      market_quality: { facts: { market_status: "fresh" }, factors: {} },
    } as unknown as SignalPulseItem["factor_snapshot"]["families"];

    expect(() => render(<SignalLabInspector item={item} />)).toThrow(/families\.market_quality/);
    expect(screen.queryByText("factor_snapshot")).not.toBeInTheDocument();
  });

  it("requires factor_snapshot composite recommended_decision", () => {
    const item = signalPulseItem();
    delete (
      item.factor_snapshot.composite as Partial<SignalPulseItem["factor_snapshot"]["composite"]>
    ).recommended_decision;

    expect(() => render(<SignalLabInspector item={item} />)).toThrow(
      /composite\.recommended_decision/,
    );
  });
});

function signalPulseItem(): SignalPulseItem {
  return {
    candidate_id: "pulse-1",
    candidate_type: "token_target",
    subject_key: "CANCERHAWK",
    target_type: "Asset",
    target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
    symbol: "CANCERHAWK",
    window: "1h",
    scope: "all",
    pulse_status: "token_watch",
    verdict: "token_watch",
    social_phase: "ignition",
    narrative_type: "direct_token",
    candidate_score: 62,
    score_band: "watch",
    evidence_event_ids: [],
    source_event_ids: [],
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v2_alpha_gated",
      subject: {
        target_type: "Asset",
        target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
        symbol: "CANCERHAWK",
        chain: "eip155:8453",
        address: "0x920738cbe6ddf7399187ffcf85c4b19154123be4",
      },
      market: signalPulseMarketFixture(),
      gates: {
        eligible_for_high_alert: false,
        max_decision: "watch",
        blocked_reasons: ["liquidity_below_high_alert_floor"],
        risk_reasons: ["thin_author_set"],
      },
      data_health: { identity: "ready", market: "partial", social: "ready", alpha: "ready" },
      families: {
        attention_heat: {
          raw_score: 62,
          score: 62,
          weight: 0.35,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        diffusion_quality: {
          raw_score: 58,
          score: 58,
          weight: 0.3,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        semantic_quality: {
          raw_score: 55,
          score: 55,
          weight: 0.25,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        timing_response: {
          raw_score: 50,
          score: 50,
          weight: 0.1,
          data_health: "partial",
          facts: {},
          factors: {},
        },
      },
      normalization: {
        status: "ready",
        cohort: {},
        factor_ranks: {},
        alpha_rank: 8,
        cohort_size: 50,
      },
      composite: {
        rank_score: 62,
        recommended_decision: "watch",
        family_scores: {
          attention_heat: 62,
          diffusion_quality: 58,
          semantic_quality: 55,
          timing_response: 50,
        },
      },
      provenance: { source_event_ids: ["event-1"], computed_at_ms: 1_700_000_000_000 },
    },
    agent_recommendation: {
      schema_version: "pulse_recommendation_v1",
      recommendation: "watch",
      summary_zh: "summary",
      primary_reasons: [],
      upgrade_conditions: [],
      invalidation_conditions: [],
      residual_risks: [],
    },
    gate: {
      pulse_status: "token_watch",
      candidate_score: 62,
      score_band: "watch",
      blocked_reasons: ["liquidity_below_high_alert_floor"],
    },
    fact_card: { liquidity_usd: 10_000, mentions_1h: 2, unique_authors: 2 },
    created_at_ms: 1_700_000_000_000,
    updated_at_ms: 1_700_000_000_000,
    playbooks: [],
  };
}

function signalPulseMarketFixture() {
  return {
    market_status: "anchored",
    price_change_status: "live_not_persisted",
    provider: "okx",
    anchor_price_usd: 0.42,
    anchor_price_quote: null,
    anchor_quote_symbol: "USD",
    anchor_price_basis: "usd",
    anchor_observed_at_ms: 1_700_000_000_000,
    social_signal_start_ms: 1_700_000_000_000,
    anchor_lag_ms: 0,
    event_price_readiness: { status: "ready" },
  };
}
