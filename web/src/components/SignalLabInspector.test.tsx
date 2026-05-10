import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SignalPulseItem } from "../api/types";
import { SignalLabInspector } from "./SignalLabInspector";

afterEach(() => cleanup());

describe("SignalLabInspector", () => {
  it("shows a venue link for the selected parsed token", () => {
    render(
      <SignalLabInspector
        item={{
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
          summary_zh: "summary",
          why_now_zh: "why now",
          evidence_event_ids: [],
          source_event_ids: [],
          factor_snapshot: {
            schema_version: "token_factor_snapshot_v1",
            subject: {
              target_type: "Asset",
              target_id: "asset:eip155:8453:erc20:0x920738cbe6ddf7399187ffcf85c4b19154123be4",
              symbol: "CANCERHAWK",
              chain: "eip155:8453",
              address: "0x920738cbe6ddf7399187ffcf85c4b19154123be4"
            },
            families: {},
            hard_gates: { eligible_for_high_alert: false, blocked_reasons: ["liquidity_below_high_alert_floor"] },
            composite: { rank_score: 62, recommended_decision: "watch" }
          },
          agent_recommendation: {
            schema_version: "pulse_recommendation_v1",
            recommendation: "watch",
            summary_zh: "summary",
            primary_reasons: [],
            upgrade_conditions: [],
            invalidation_conditions: [],
            residual_risks: []
          },
          gate: { pulse_status: "token_watch", candidate_score: 62, score_band: "watch", blocked_reasons: ["liquidity_below_high_alert_floor"] },
          fact_card: { liquidity_usd: 10_000, mentions_1h: 2, unique_authors: 2 },
          created_at_ms: 1_700_000_000_000,
          updated_at_ms: 1_700_000_000_000,
          playbooks: []
        } satisfies SignalPulseItem}
      />
    );

    expect(screen.getByRole("link", { name: "Open selected Signal Pulse token on GMGN" })).toHaveAttribute(
      "href",
      "https://gmgn.ai/base/token/0x920738cbe6ddf7399187ffcf85c4b19154123be4"
    );
  });
});
