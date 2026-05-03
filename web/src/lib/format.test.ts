import { describe, expect, it } from "vitest";
import { compactNumber, eventHandle, formatPercentShare, formatRelativeTime, tokenLabel } from "./format";

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

  it("normalizes event handles and token labels", () => {
    expect(eventHandle({ event_id: "1", author: { handle: "@Toly" } })).toBe("toly");
    expect(
      tokenLabel({
        identity: { identity_key: "symbol:PEPE", identity_status: "unresolved_symbol", symbol: "PEPE" },
        social: { window: "5m", mention_count: 1, watched_mention_count: 1, unique_author_count: 1, market_mindshare: 1, watched_mindshare: 1 },
        baseline: { baseline_status: "insufficient_history", sample_count: 0 },
        anomaly: { score: 1, reasons: [] },
        market: { market_status: "missing", market_confirmed: false },
        confidence: { score: 1, coverage: "public_stream", coverage_boundary: "public stream", identity_status: "unresolved_symbol", market_status: "missing", baseline_status: "insufficient_history", reasons: [] },
        evidence: []
      })
    ).toBe("$PEPE");
  });
});
