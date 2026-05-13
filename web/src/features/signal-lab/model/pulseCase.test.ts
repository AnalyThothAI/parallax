import type { SignalPulseItem } from "@lib/types";
import { describe, expect, it } from "vitest";

import { marketContextFixture, marketObservationFixture } from "../../../test/marketFixtures";

import { buildPulseCaseView } from "./pulseCase";

describe("buildPulseCaseView", () => {
  it("maps a Signal Pulse candidate into a memo-first case view", () => {
    const view = buildPulseCaseView(signalPulseFixture());

    expect(view.candidateId).toBe("pulse-1");
    expect(view.subject.title).toBe("$HAWK");
    expect(view.subject.subtitle).toBe("base · 0x920738...123be4");
    expect(view.stage.value).toBe("token watch");
    expect(view.stage.source).toBe("deterministic");
    expect(view.gate.value).toBe("watch");
    expect(view.gate.detail).toContain("liquidity below high alert floor");
    expect(view.agentMemo.recommendation.value).toBe("research");
    expect(view.agentMemo.summary).toBe("社区在放大，但流动性还需要确认。");
    expect(view.agentMemo.reasons).toEqual(["social_heat.mentions_1h: mentions expanding"]);
    expect(view.agentMemo.risks).toEqual(["timing_risk.price: chase risk"]);
    expect(view.factLedger.map((fact) => fact.label)).toEqual([
      "Market cap",
      "Liquidity",
      "Holders",
      "Volume 24h",
      "Community",
      "Data health",
      "Alpha rank",
    ]);
    expect(view.factLedger[0]).toMatchObject({
      source: "market",
      value: "$2.5M",
    });
    expect(view.factLedger[4]).toMatchObject({
      source: "social",
      value: "9 posts · 4 authors",
    });
    expect(view.sourceEvents).toEqual([
      {
        body: "Candidate source event",
        id: "source-1",
        meta: "source_event_ids",
        title: "source-1",
        tone: "info",
      },
      {
        body: "Agent evidence event",
        id: "evidence-1",
        meta: "evidence_event_ids",
        title: "evidence-1",
        tone: "health",
      },
    ]);
    expect(view.actions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          href: "/search?q=%24HAWK&window=24h&scope=all",
          kind: "search",
          label: "Search Intel",
        }),
        expect.objectContaining({ kind: "venue", label: "GMGN" }),
      ]),
    );
    expect(view.debugFacts.map((fact) => fact.label)).toContain("factor_snapshot");
  });
});

function signalPulseFixture(): SignalPulseItem {
  return {
    candidate_id: "pulse-1",
    candidate_type: "token_target",
    subject_key: "HAWK",
    target_type: "Asset",
    target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
    symbol: "HAWK",
    window: "1h",
    scope: "all",
    pulse_status: "token_watch",
    verdict: "token_watch",
    social_phase: "ignition",
    narrative_type: "direct_token",
    candidate_score: 62,
    score_band: "watch",
    evidence_event_ids: ["evidence-1"],
    source_event_ids: ["source-1"],
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v3_social_attention",
      subject: {
        target_type: "Asset",
        target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
        symbol: "HAWK",
        chain: "base",
        address: "0x920738cbe6ddf7399187ffcf85c4b19154123be4",
      },
      market: marketContextFixture({
        event_anchor: marketObservationFixture({
          source: "event_anchor",
          market_cap_usd: 2_500_000,
          liquidity_usd: 65_000,
          holders: 1_240,
          volume_24h_usd: 440_000,
        }),
        decision_latest: marketObservationFixture({
          source: "decision_latest",
          market_cap_usd: 2_500_000,
          liquidity_usd: 65_000,
          holders: 1_240,
          volume_24h_usd: 440_000,
        }),
      }),
      gates: {
        eligible_for_high_alert: false,
        max_decision: "watch",
        blocked_reasons: ["liquidity_below_high_alert_floor"],
        risk_reasons: ["thin_author_set"],
      },
      data_health: {
        identity: "ready",
        market: "ready",
        social: "ready",
        alpha: "ready",
      },
      families: {
        social_heat: {
          raw_score: 62,
          score: 62,
          weight: 0.35,
          data_health: "ready",
          facts: { mentions_1h: 9, watched_mentions: 2 },
          factors: {},
        },
        social_propagation: {
          raw_score: 58,
          score: 58,
          weight: 0.3,
          data_health: "ready",
          facts: { independent_authors: 4 },
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
          data_health: "ready",
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
      provenance: { source_event_ids: ["source-1"], computed_at_ms: 1_700_000_000_000 },
    },
    agent_recommendation: {
      schema_version: "pulse_recommendation_v1",
      recommendation: "research",
      summary_zh: "社区在放大，但流动性还需要确认。",
      primary_reasons: [
        { factor_key: "social_heat.mentions_1h", explanation_zh: "mentions expanding" },
      ],
      upgrade_conditions: [
        {
          factor_key: "fact_card.liquidity_usd",
          operator: ">=",
          value: 100_000,
          description_zh: "needs more liquidity",
        },
      ],
      invalidation_conditions: [],
      residual_risks: [{ factor_key: "timing_risk.price", description_zh: "chase risk" }],
      confidence: 0.74,
    },
    gate: {
      pulse_status: "token_watch",
      candidate_score: 62,
      score_band: "watch",
      blocked_reasons: ["liquidity_below_high_alert_floor"],
    },
    fact_card: {
      market_cap_usd: 2_500_000,
      liquidity_usd: 65_000,
      holders: 1_240,
      volume_24h_usd: 440_000,
      mentions_1h: 9,
      unique_authors: 4,
      watched_mentions: 2,
      market_status: "ready",
    },
    agent_run_id: "run-1",
    pulse_version: "pulse-v1",
    gate_version: "gate-v1",
    prompt_version: "prompt-v1",
    schema_version: "schema-v1",
    created_at_ms: 1_700_000_000_000,
    updated_at_ms: 1_700_000_000_000,
    playbooks: [],
  };
}
