import { SignalLabInspector } from "@features/signal-lab";
import type { SignalPulseItem } from "@lib/types";
import { cleanup, render, screen } from "@testing-library/react";
import { marketContextFixture, marketObservationFixture } from "@tests/fixtures/marketFixtures";
import { axe } from "jest-axe";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("SignalLabInspector", () => {
  it("shows a venue link for the selected parsed token", async () => {
    const { container } = renderWithRouter(
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
              schema_version: "token_factor_snapshot_v3_social_attention",
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
                social_heat: {
                  raw_score: 62,
                  score: 62,
                  weight: 0.35,
                  data_health: "ready",
                  facts: {},
                  factors: {},
                },
                social_propagation: {
                  raw_score: 58,
                  score: 58,
                  weight: 0.3,
                  data_health: "ready",
                  facts: {},
                  factors: {},
                },
                semantic_catalyst: {
                  raw_score: 55,
                  score: 55,
                  weight: 0.25,
                  data_health: "ready",
                  facts: {},
                  factors: {},
                },
                timing_risk: {
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
                  social_heat: 62,
                  social_propagation: 58,
                  semantic_catalyst: 55,
                  timing_risk: 50,
                },
              },
              provenance: { source_event_ids: ["event-1"], computed_at_ms: 1_700_000_000_000 },
            },
            decision: {
              route: "meme",
              recommendation: "watchlist",
              confidence: 0.62,
              abstain_reason: null,
              stage_count: 3,
              summary_zh: "summary",
              invalidation_conditions: [],
              residual_risks: [],
              evidence_event_ids: ["event-1"],
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
      screen.getByRole("region", { name: "Signal Pulse case $CANCERHAWK" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Agent memo")).toBeInTheDocument();
    expect(screen.getByText("Fact ledger")).toBeInTheDocument();
    expect(screen.getByText("Source events")).toBeInTheDocument();
    expect(screen.getByText("Debug facts")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open pulse case on GMGN" })).toHaveAttribute(
      "href",
      "https://gmgn.ai/base/token/0x920738cbe6ddf7399187ffcf85c4b19154123be4",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("rejects malformed Signal Pulse factor snapshots before rendering raw JSON", () => {
    const item = signalPulseItem();
    item.factor_snapshot.families = {
      ...item.factor_snapshot.families,
      market_quality: { facts: { market_status: "fresh" }, factors: {} },
    } as unknown as SignalPulseItem["factor_snapshot"]["families"];

    expect(() => renderWithRouter(<SignalLabInspector item={item} />)).toThrow(
      /families\.market_quality/,
    );
    expect(screen.queryByText("factor_snapshot")).not.toBeInTheDocument();
  });

  it("requires factor_snapshot composite recommended_decision", () => {
    const item = signalPulseItem();
    delete (
      item.factor_snapshot.composite as Partial<SignalPulseItem["factor_snapshot"]["composite"]>
    ).recommended_decision;

    expect(() => renderWithRouter(<SignalLabInspector item={item} />)).toThrow(
      /composite\.recommended_decision/,
    );
  });
});

function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

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
      schema_version: "token_factor_snapshot_v3_social_attention",
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
        social_heat: {
          raw_score: 62,
          score: 62,
          weight: 0.35,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        social_propagation: {
          raw_score: 58,
          score: 58,
          weight: 0.3,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        semantic_catalyst: {
          raw_score: 55,
          score: 55,
          weight: 0.25,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        timing_risk: {
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
          social_heat: 62,
          social_propagation: 58,
          semantic_catalyst: 55,
          timing_risk: 50,
        },
      },
      provenance: { source_event_ids: ["event-1"], computed_at_ms: 1_700_000_000_000 },
    },
    decision: {
      route: "meme",
      recommendation: "watchlist",
      confidence: 0.62,
      abstain_reason: null,
      stage_count: 3,
      summary_zh: "summary",
      invalidation_conditions: [],
      residual_risks: [],
      evidence_event_ids: ["event-1"],
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
  return marketContextFixture({
    event_anchor: marketObservationFixture({
      source: "event_anchor",
      provider: "okx",
      price_usd: 0.42,
      price_quote: null,
      quote_symbol: "USD",
      price_basis: "usd",
      observed_at_ms: 1_700_000_000_000,
      received_at_ms: 1_700_000_000_000,
    }),
    decision_latest: marketObservationFixture({
      source: "decision_latest",
      provider: "okx",
      price_usd: 0.42,
      price_quote: null,
      quote_symbol: "USD",
      price_basis: "usd",
      observed_at_ms: 1_700_000_000_000,
      received_at_ms: 1_700_000_000_000,
    }),
  });
}
