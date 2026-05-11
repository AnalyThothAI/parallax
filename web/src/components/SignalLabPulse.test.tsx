import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SignalPulseItem } from "../api/types";

import { SignalLabPulse } from "./SignalLabPulse";

afterEach(() => cleanup());

describe("SignalLabPulse", () => {
  it("renders structural skeleton rows while loading", () => {
    render(<SignalLabPulse isLoading data={undefined} onOpenLab={vi.fn()} onSelect={vi.fn()} />);

    const skeleton = screen.getByLabelText("loading signal pulse");
    expect(skeleton.querySelectorAll(".skeleton-row")).toHaveLength(5);
    expect(screen.queryByText("loading signal pulse")).not.toBeInTheDocument();
  });

  it("shows every pulse item with the Signal Pulse row budget", () => {
    const items = Array.from({ length: 7 }, (_, index) => pulseItem(index));

    render(
      <SignalLabPulse
        data={{
          query: { window: "24h", scope: "all" },
          health: {
            pulse_ready: true,
            agent_worker_running: true,
            candidate_count: 7,
            blocked_low_information_count: 0,
            dead_job_count: 0,
            market_ready_rate: 1,
            settlement_coverage: 1,
          },
          items,
          summary: {
            trade_candidate: 7,
            token_watch: 0,
            theme_watch: 0,
            risk_rejected_high_info: 0,
            blocked_low_information: 0,
          },
          returned_count: 7,
          has_more: false,
          next_cursor: null,
        }}
        onOpenLab={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /TOKEN6/ })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(7);
    expect(screen.getAllByText("trade").length).toBeGreaterThan(0);
    expect(screen.getByText("recommendation 6")).toBeInTheDocument();
    expect(screen.getByText(/mentions 7/)).toBeInTheDocument();
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("liq $75K").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/authors 3/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open TOKEN6 on OKX" })).toHaveAttribute(
      "href",
      "https://www.okx.com/trade-spot/token6-usdt",
    );
    expect(screen.queryByText(["Direct", "token"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Topic", "heat"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["low", "signal"].join("_"))).not.toBeInTheDocument();
    expect(screen.queryByText(["NO", "TRADE"].join("_"))).not.toBeInTheDocument();
  });

<<<<<<< HEAD
  it("keeps sparse pulse rows renderable while backend jobs are catching up", () => {
    const sparse = {
      ...pulseItem(0),
      top_risks: undefined,
      confirmation_triggers_zh: undefined,
      invalidation_triggers_zh: undefined,
    } as unknown as SignalPulseItem;

=======
  it("renders rows from the factor snapshot contract without legacy fields", () => {
>>>>>>> origin/main
    render(
      <SignalLabPulse
        data={{
          query: { window: "24h", scope: "all" },
          health: {
            pulse_ready: true,
            agent_worker_running: true,
            candidate_count: 1,
            blocked_low_information_count: 0,
            dead_job_count: 0,
            market_ready_rate: 1,
            settlement_coverage: null,
          },
          items: [pulseItem(0)],
          summary: {
            trade_candidate: 1,
            token_watch: 0,
            theme_watch: 0,
            risk_rejected_high_info: 0,
            blocked_low_information: 0,
          },
          returned_count: 1,
          has_more: false,
          next_cursor: null,
        }}
        onOpenLab={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "open Signal Pulse TOKEN0" })).toBeInTheDocument();
    expect(screen.getByText("recommendation 0")).toBeInTheDocument();
    expect(screen.queryByText("radar_score_json")).not.toBeInTheDocument();
    expect(screen.queryByText("market_context_json")).not.toBeInTheDocument();
  });
});

function pulseItem(index: number): SignalPulseItem {
  return {
    candidate_id: `candidate-${index}`,
    candidate_type: "token",
    subject_key: `token:TOKEN${index}`,
    target_type: "CexToken",
    target_id: `asset:cex:TOKEN${index}`,
    symbol: `TOKEN${index}`,
    window: "24h",
    scope: "all",
    pulse_status: "trade_candidate",
    verdict: "candidate",
    social_phase: "ignition",
    narrative_type: "token",
    candidate_score: 82,
    score_band: "A",
    evidence_event_ids: [`evidence-${index}`],
    source_event_ids: [`source-${index}`],
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v1",
      subject: {
        target_type: "CexToken",
        target_id: `asset:cex:okx:TOKEN${index}-USDT`,
        symbol: `TOKEN${index}`
      },
      families: {
        market_quality: {
          score: 76,
          data_health: "ready",
          facts: {
            native_market_id: `pricefeed:cex:okx:spot:TOKEN${index}-USDT`,
            liquidity_usd: 75_000,
            market_cap_usd: 2_500_000,
            holders: 1200,
            volume_24h_usd: 430_000
          },
          factors: {}
        },
        social_attention: {
          score: 81,
          data_health: "ready",
          facts: { mentions_1h: index + 1, watched_mentions: 1 },
          factors: {}
        },
        social_quality: {
          score: 70,
          data_health: "ready",
          facts: { independent_authors: 3 },
          factors: {}
        }
      },
      hard_gates: { eligible_for_high_alert: true, blocked_reasons: [] },
      composite: { rank_score: 82, recommended_decision: "watch" }
    },
    agent_recommendation: {
      schema_version: "pulse_recommendation_v1",
      recommendation: "watch",
      summary_zh: `recommendation ${index}`,
      primary_reasons: [{ factor_key: "social_attention.mentions_1h", explanation_zh: "mentions expanding" }],
      upgrade_conditions: [],
      invalidation_conditions: [],
      residual_risks: [{ factor_key: "market_quality.liquidity_usd", description_zh: "liquidity can thin quickly" }]
    },
    gate: { pulse_status: "trade_candidate", candidate_score: 82, score_band: "A", eligible_for_high_alert: true, blocked_reasons: [] },
    fact_card: {
      market_cap_usd: 2_500_000,
      liquidity_usd: 75_000,
      holders: 1200,
      volume_24h_usd: 430_000,
      market_status: "ready",
      mentions_1h: index + 1,
      unique_authors: 3,
      watched_mentions: 1,
      eligible_for_high_alert: true,
      blocked_reasons: []
    },
    agent_run_id: "run-1",
    pulse_version: "pulse-v10",
    gate_version: "gate-v10",
    prompt_version: "prompt-v10",
    schema_version: "signal-pulse-v1",
    created_at_ms: 1_700_000_000_000 + index,
    updated_at_ms: 1_700_000_000_000 + index,
    playbooks: [],
  };
}
