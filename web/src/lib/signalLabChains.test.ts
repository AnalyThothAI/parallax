import { describe, expect, it } from "vitest";
import type { SignalLabChain } from "../api/types";
import { chainDisplayTitle, chainScore, chainStatusText } from "./signalLabChains";

describe("Signal Lab chain presentation", () => {
  it("does not render no-trade frozen snapshots as a misleading 0 percent signal", () => {
    const chain = signalChain({
      score: 0,
      snapshot: {
        snapshot_id: "snapshot-test",
        source_event_id: "event-test",
        seed_id: "seed-test",
        asset: "BNB",
        decision_time_ms: 1_000,
        horizon: "6h",
        combined_score: 0,
        shadow_signal: "NO_TRADE",
        policy_signal: "NO_TRADE",
        event_clusters: [],
        market_state: {},
        versions: {
          config_version: "config",
          prompt_version: "prompt",
          schema_version: "schema",
          scoring_version: "scoring",
          weight_version: "weight",
          policy_version: "policy",
          risk_version: "risk",
          baseline_version: "baseline"
        },
        outcome_status: "pending",
        credit_status: "none",
        risks: []
      }
    });

    expect(chainScore(chain)).toBe("NO TRADE");
  });

  it("surfaces terminal market-data blockers instead of generic pending copy", () => {
    const chain = signalChain({
      outcome_status: "missing_market",
      credit_status: "none"
    });

    expect(chainStatusText(chain)).toBe("missing market · no credit");
  });

  it("uses resolved seed symbol as the display label when the persisted asset is a token id", () => {
    const chain = signalChain({
      asset: "token:eth:0x0000000000000000000000000000000000000b0b",
      horizon: "6h",
      seed: {
        seed_id: "seed-test",
        extraction_id: "extraction-test",
        event_id: "event-test",
        author_handle: "toly",
        received_at_ms: 1_000,
        event_type: "meme_phrase_seed",
        subject: "BNB",
        anchor_terms: [],
        token_uptake_count: 1,
        top_linked_symbols: ["BNB"],
        seed_status: "snapshot_ready",
        risks: []
      }
    });

    expect(chainDisplayTitle(chain)).toBe("BNB · 6h");
  });
});

function signalChain(overrides: Partial<SignalLabChain>): SignalLabChain {
  return {
    chain_id: "snapshot:test",
    stage: "frozen",
    received_at_ms: 1_000,
    updated_at_ms: 1_000,
    asset: "BNB",
    horizon: "6h",
    source: "toly",
    event_type: "meme_phrase_seed",
    title: "BNB · 6h",
    summary: "summary",
    score: 0.42,
    outcome_status: "pending",
    credit_status: "none",
    risks: [],
    evidence_chips: [],
    lineage: {},
    social_event: null,
    seed: null,
    snapshot: null,
    outcome: null,
    credits: [],
    ...overrides
  };
}
