import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SignalPulseItem } from "../api/types";
import { SignalLabPulse } from "./SignalLabPulse";

afterEach(() => cleanup());

describe("SignalLabPulse", () => {
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
            settlement_coverage: 1
          },
          items,
          summary: {
            trade_candidate: 7,
            token_watch: 0,
            theme_watch: 0,
            risk_rejected_high_info: 0,
            blocked_low_information: 0
          },
          returned_count: 7,
          has_more: false,
          next_cursor: null
        }}
        onOpenLab={vi.fn()}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /TOKEN6/ })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(7);
    expect(screen.getAllByText("trade").length).toBeGreaterThan(0);
    expect(screen.getByText("why now 6")).toBeInTheDocument();
    expect(screen.getAllByText("ignition").length).toBeGreaterThan(0);
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("liquidity thin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("confirm: volume confirms").length).toBeGreaterThan(0);
    expect(screen.getAllByText("invalidate: author concentration fades").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open TOKEN6 on OKX" })).toHaveAttribute(
      "href",
      "https://www.okx.com/trade-spot/token6-usdt"
    );
    expect(screen.queryByText(["Direct", "token"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Topic", "heat"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["low", "signal"].join("_"))).not.toBeInTheDocument();
    expect(screen.queryByText(["NO", "TRADE"].join("_"))).not.toBeInTheDocument();
  });

  it("keeps sparse pulse rows renderable while backend jobs are catching up", () => {
    const sparse = { ...pulseItem(0), top_risks: undefined, confirmation_triggers_zh: undefined, invalidation_triggers_zh: undefined } as unknown as SignalPulseItem;

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
            settlement_coverage: null
          },
          items: [sparse],
          summary: {
            trade_candidate: 1,
            token_watch: 0,
            theme_watch: 0,
            risk_rejected_high_info: 0,
            blocked_low_information: 0
          },
          returned_count: 1,
          has_more: false,
          next_cursor: null
        }}
        onOpenLab={vi.fn()}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "open Signal Pulse TOKEN0" })).toBeInTheDocument();
    expect(screen.getByText("why now 0")).toBeInTheDocument();
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
    summary_zh: `summary ${index}`,
    why_now_zh: `why now ${index}`,
    bull_case_zh: ["watched account led"],
    bear_case_zh: ["crowded"],
    confirmation_triggers_zh: ["volume confirms"],
    invalidation_triggers_zh: ["author concentration fades"],
    top_risks: ["liquidity thin"],
    gate_reasons: [],
    risk_reasons: [],
    evidence_event_ids: [`evidence-${index}`],
    source_event_ids: [`source-${index}`],
    radar_score_json: { score: 82 },
    market_context_json: { market: "ready" },
    thesis_json: { setup: "momentum" },
    agent_run_id: "run-1",
    pulse_version: "pulse-v10",
    gate_version: "gate-v10",
    prompt_version: "prompt-v10",
    schema_version: "signal-pulse-v1",
    created_at_ms: 1_700_000_000_000 + index,
    updated_at_ms: 1_700_000_000_000 + index,
    playbooks: []
  };
}
