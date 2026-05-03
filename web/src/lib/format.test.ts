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
        identity: { identity_key: "symbol:PEPE", identity_status: "unresolved_symbol", symbol: "PEPE" },
        market: { market_status: "missing", price_change_status: "missing_market" },
        flow: { window: "5m", mentions: 1, watched_mentions: 1, previous_mentions: 0, mention_delta: 1, stream_dominance: 1, baseline_status: "insufficient_history", baseline_sample_count: 0 },
        sources: { unique_authors: 1, watched_authors: 1, top_author_share: 1, source_quality_score: 1, source_quality_reasons: [] },
        fresh: { is_new_token: true, is_first_seen_by_watched: true },
        signal: { decision: "discard", score: 1, reasons: [], risks: [] },
        evidence: []
      })
    ).toBe("$PEPE");
  });
});
