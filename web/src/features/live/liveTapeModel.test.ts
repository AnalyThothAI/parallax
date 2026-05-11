import { describe, expect, it } from "vitest";

import type { LivePayload, TokenFlowItem } from "../../api/types";

import { buildLiveSignalTapeItems, tapeItemId, tokenTapeReason } from "./liveTapeModel";

describe("liveTapeModel", () => {
  it("promotes live events to token tape rows when resolution target matches", () => {
    const token = tokenItem({ targetId: "asset:sol", symbol: "SOL" });
    const event = liveEvent({
      eventId: "evt-1",
      text: "SOL volume is waking up",
      token_resolutions: [{ target_id: "asset:sol" }],
    });

    const rows = buildLiveSignalTapeItems({ liveItems: [event], tokenItems: [token] });

    expect(rows[0].kind).toBe("token");
    expect(rows[0].score).toBe(72);
    expect(tapeItemId(rows[0])).toBe("evt-1");
    expect(rows).toHaveLength(2);
  });

  it("keeps ambiguous cashtag-only events as event rows", () => {
    const rows = buildLiveSignalTapeItems({
      liveItems: [liveEvent({ eventId: "evt-1", cashtags: ["SOL"] })],
      tokenItems: [
        tokenItem({ targetId: "asset:sol-1", symbol: "SOL" }),
        tokenItem({ targetId: "asset:sol-2", symbol: "SOL" }),
      ],
    });

    expect(rows[0].kind).toBe("event");
    expect(tapeItemId(rows[0])).toBe("evt-1");
  });

  it("uses the first explicit token reason and normalizes it for display", () => {
    expect(tokenTapeReason(tokenItem({ reasons: ["new_burst_from_watched_accounts"] }))).toBe(
      "new burst from watched accounts",
    );
  });
});

function liveEvent({
  cashtags = [],
  eventId,
  text = "",
  token_resolutions = [],
}: {
  cashtags?: string[];
  eventId: string;
  text?: string;
  token_resolutions?: LivePayload["token_resolutions"];
}): LivePayload {
  return {
    type: "event",
    event: {
      event_id: eventId,
      author_handle: "toly",
      received_at_ms: 1_700_000_000_000,
      text_clean: text,
      cashtags,
    },
    entities: [],
    alerts: [],
    token_resolutions,
  };
}

function tokenItem({
  reasons = [],
  symbol = "SOL",
  targetId = "asset:sol",
}: {
  reasons?: string[];
  symbol?: string;
  targetId?: string;
}): TokenFlowItem {
  return {
    identity: {
      identity_key: targetId,
      target_id: targetId,
      chain: "solana",
      address: targetId.replace("asset:", ""),
      symbol,
    },
    flow: {
      window: "1h",
      window_end_ms: 1_700_000_000_000,
      mentions: 9,
      watched_mentions: 3,
      previous_mentions: 1,
      mention_delta: 8,
      stream_dominance: 0.3,
      baseline_status: "ready",
      baseline_sample_count: 30,
    },
    social_heat: {
      score: 68,
      score_version: "token_factor_snapshot_v2_alpha_gated:social_heat",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      window: "1h",
      mentions: 9,
      mentions_5m: 2,
      mentions_1h: 9,
      mentions_4h: 12,
      mentions_24h: 20,
      weighted_mentions: 10,
      previous_mentions: 1,
      mention_delta: 8,
      stream_share: 0.3,
      watched_share: 0.5,
      status: "rising",
    },
    propagation: {
      score: 61,
      score_version: "token_factor_snapshot_v2_alpha_gated:propagation",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      independent_authors: 4,
      effective_authors: 4,
      new_authors: 2,
      top_author_share: 0.25,
      duplicate_text_share: 0,
      author_entropy: 1,
      phase: "ignition",
      top_authors: [],
    },
    timing: {
      score: 55,
      score_version: "token_factor_snapshot_v2_alpha_gated:timing",
      status: "neutral",
      chase_risk: false,
      reasons: [],
      risks: [],
    },
    opportunity: {
      score: 72,
      score_version: "token_factor_snapshot_v2_alpha_gated:composite",
      decision: "watch",
      reasons,
      risks: [],
      contributions: [],
      risk_caps: [],
      components: {
        heat: 68,
        quality: 50,
        propagation: 61,
        timing: 55,
      },
    },
  } as unknown as TokenFlowItem;
}
