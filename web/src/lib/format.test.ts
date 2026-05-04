import { describe, expect, it } from "vitest";
import { compactNumber, eventHandle, formatPercentShare, formatRelativeTime, formatSignedPercent, formatUsdCompact, tokenLabel } from "./format";

describe("format helpers", () => {
  it("compacts large numbers for dense cockpit cells", () => {
    expect(compactNumber(1250)).toBe("1.3K");
    expect(compactNumber(1_250_000)).toBe("1.3M");
  });

  it("formats relative milliseconds without locale noise", () => {
    expect(formatRelativeTime(1_000, 31_000)).toBe("30s");
    expect(formatRelativeTime(1_000, 181_000)).toBe("3m");
  });

  it("formats normalized mindshare as a compact percent", () => {
    expect(formatPercentShare(0.5)).toBe("50%");
    expect(formatPercentShare(0.0123)).toBe("1.2%");
  });

  it("formats market cap and signed price changes for radar cells", () => {
    expect(formatUsdCompact(15_200)).toBe("$15K");
    expect(formatSignedPercent(0.124)).toBe("+12%");
    expect(formatSignedPercent(-0.084)).toBe("-8.4%");
    expect(formatSignedPercent(null)).toBe("-");
  });

  it("normalizes event handles and token labels", () => {
    expect(eventHandle({ event_id: "1", author: { handle: "@Toly" } })).toBe("toly");
    expect(
      tokenLabel({
        identity: {
          identity_key: "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933",
          identity_status: "resolved_ca",
          token_id: "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933",
          chain: "eth",
          address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
          symbol: "PEPE"
        },
        market: { market_status: "fresh", price_change_status: "insufficient_history" },
        flow: { window: "5m", mentions: 1, watched_mentions: 1, previous_mentions: 0, mention_delta: 1, stream_dominance: 1, baseline_status: "insufficient_history", baseline_sample_count: 0 },
        baseline: { baseline_status: "insufficient_history", sample_count: 0, zero_slot_count: 0, ewma_mean: null, ewma_stddev: null, simple_mean: null, z_score: null, new_burst_score: 1 },
        diffusion: { score: 80, status: "thin", independent_authors: 1, effective_authors: 1, top_author_share: 1, duplicate_text_share: 0, repeated_cluster_count: 0, shill_author_count: 0, reasons: [], risks: ["thin_author_set"] },
        watch: { status: "direct_watch", direct_mentions: 1, direct_authors: 1, seed_link_count: 0, top_seed: null, reasons: ["watched_direct_mention"], risks: [] },
        fresh: { is_new_local_evidence: true, is_first_seen_by_watched: true },
        signal: {
          score_version: "token_signal_v1",
          decision: "watch",
          score: 1,
          reasons: [],
          risks: [],
          contributions: [],
          risk_caps: []
        },
        evidence_highlight_best: null,
        evidence_highlights: [],
        evidence_total_count: 0,
        posts_query: {
          token_id: "token:eth:0x6982508145454Ce325dDbE47a25d4ec3d2311933",
          chain: "eth",
          address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
          window: "5m",
          scope: "all"
        }
      })
    ).toBe("$PEPE");
  });
});
