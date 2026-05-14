import { SignalLabPulse } from "@features/signal-lab";
import type { SignalPulseItem } from "@lib/types";
import { cleanup, render, screen } from "@testing-library/react";
import { marketContextFixture, marketObservationFixture } from "@tests/fixtures/marketFixtures";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());

describe("SignalLabPulse", () => {
  it("renders structural skeleton rows while loading", () => {
    renderWithRouter(
      <SignalLabPulse isLoading data={undefined} onOpenLab={vi.fn()} onSelect={vi.fn()} />,
    );

    const skeleton = screen.getByLabelText("loading signal pulse");
    expect(skeleton.querySelectorAll(".skeleton-row")).toHaveLength(5);
    expect(screen.queryByText("loading signal pulse")).not.toBeInTheDocument();
  });

  it("shows every pulse item with the Signal Pulse row budget", () => {
    const items = Array.from({ length: 7 }, (_, index) => pulseItem(index));

    renderWithRouter(
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
    expect(screen.getAllByText("trade candidate").length).toBeGreaterThan(0);
    expect(screen.getByText("recommendation 6")).toBeInTheDocument();
    expect(screen.getAllByText("watchlist").length).toBeGreaterThan(0);
    expect(screen.getByText(/mentions 7/)).toBeInTheDocument();
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Liquidity $75K").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/authors 3/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Search Intel/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open TOKEN6 on OKX" })).toHaveAttribute(
      "href",
      "https://www.okx.com/trade-spot/token6-usdt",
    );
    expect(screen.queryByText(["Direct", "token"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Topic", "heat"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["low", "signal"].join("_"))).not.toBeInTheDocument();
    expect(screen.queryByText(["NO", "TRADE"].join("_"))).not.toBeInTheDocument();
  });

  it("renders rows from the factor snapshot contract without legacy fields", () => {
    renderWithRouter(
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

    expect(screen.getByRole("button", { name: "open pulse case $TOKEN0" })).toBeInTheDocument();
    expect(screen.getByText("recommendation 0")).toBeInTheDocument();
    expect(screen.queryByText("radar_score_json")).not.toBeInTheDocument();
    expect(screen.queryByText("market_context_json")).not.toBeInTheDocument();
  });
});

function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

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
      schema_version: "token_factor_snapshot_v3_social_attention",
      subject: {
        target_type: "CexToken",
        target_id: `asset:cex:okx:TOKEN${index}-USDT`,
        symbol: `TOKEN${index}`,
        pricefeed_id: `pricefeed:cex:okx:spot:TOKEN${index}-USDT`,
      },
      market: signalPulseMarketFixture(),
      gates: {
        eligible_for_high_alert: true,
        max_decision: "high_alert",
        blocked_reasons: [],
        risk_reasons: [],
      },
      data_health: { identity: "ready", market: "ready", social: "ready", alpha: "ready" },
      families: {
        social_heat: {
          raw_score: 81,
          score: 81,
          weight: 0.35,
          data_health: "ready",
          facts: { mentions_1h: index + 1, watched_mentions: 1 },
          factors: {},
        },
        social_propagation: {
          raw_score: 70,
          score: 70,
          weight: 0.3,
          data_health: "ready",
          facts: { independent_authors: 3 },
          factors: {},
        },
        semantic_catalyst: {
          raw_score: 68,
          score: 68,
          weight: 0.25,
          data_health: "ready",
          facts: {
            impact_mean: 0.68,
            novelty_mean: 0.7,
            confidence_mean: 0.8,
            direction_counts: { bullish: 1 },
          },
          factors: {},
        },
        timing_risk: {
          raw_score: 64,
          score: 64,
          weight: 0.1,
          data_health: "ready",
          facts: { price_change_since_social_pct: 0.02, price_change_before_social_pct: 0.01 },
          factors: {},
        },
      },
      normalization: {
        status: "ready",
        cohort: { window: "24h" },
        factor_ranks: {},
        alpha_rank: index + 1,
        cohort_size: 7,
      },
      composite: {
        rank_score: 82,
        recommended_decision: "watch",
        family_scores: {
          social_heat: 81,
          social_propagation: 70,
          semantic_catalyst: 68,
          timing_risk: 64,
        },
      },
      provenance: {
        source_event_ids: [`source-${index}`],
        computed_at_ms: 1_700_000_000_000 + index,
      },
    },
    decision: {
      route: "meme",
      recommendation: "watchlist",
      confidence: 0.72,
      abstain_reason: null,
      stage_count: 3,
      summary_zh: `recommendation ${index}`,
      invalidation_conditions: [],
      residual_risks: ["liquidity can thin quickly"],
      evidence_event_ids: [`source-${index}`],
    },
    gate: {
      pulse_status: "trade_candidate",
      candidate_score: 82,
      score_band: "A",
      eligible_for_high_alert: true,
      blocked_reasons: [],
    },
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
      blocked_reasons: [],
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

function signalPulseMarketFixture() {
  return marketContextFixture({
    event_anchor: marketObservationFixture({
      source: "event_anchor",
      provider: "okx",
      price_usd: 1.23,
      price_quote: 1.23,
      quote_symbol: "USDT",
      price_basis: "quote_as_usd",
      observed_at_ms: 1_700_000_000_000,
      received_at_ms: 1_700_000_000_000,
    }),
    decision_latest: marketObservationFixture({
      source: "decision_latest",
      provider: "okx",
      price_usd: 1.23,
      price_quote: 1.23,
      quote_symbol: "USDT",
      price_basis: "quote_as_usd",
      observed_at_ms: 1_700_000_000_000,
      received_at_ms: 1_700_000_000_000,
    }),
  });
}
