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
          market_context_json: {},
          thesis_json: {},
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
