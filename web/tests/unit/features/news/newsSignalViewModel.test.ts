import {
  newsDisplayTokenLanes,
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenImpactCompactLabel,
  tokenImpactLabel,
  tokenImpactTone,
  tokenMarketLabel,
} from "@features/news/model/newsSignalViewModel";
import { describe, expect, it } from "vitest";

describe("newsSignalViewModel", () => {
  it("labels provider bullish, bearish, and neutral signals in Chinese", () => {
    expect(newsSignalLabel({ source: "provider", status: "ready", direction: "bullish" })).toBe(
      "利好",
    );
    expect(newsSignalLabel({ source: "provider", status: "ready", direction: "bearish" })).toBe(
      "利空",
    );
    expect(newsSignalLabel({ source: "provider", status: "partial", direction: "neutral" })).toBe(
      "中性",
    );
  });

  it("formats total scores only for the signal pill", () => {
    expect(newsSignalScoreLabel({ score: 82, grade: "A" })).toBe("A · 82");
    expect(newsSignalScoreLabel({ score: null, grade: null })).toBe("score --");
  });

  it("uses token impact labels for per-token chip scores", () => {
    expect(tokenImpactLabel({ provider_score: 82, provider_grade: "A" })).toBe("82 A");
    expect(tokenImpactCompactLabel({ provider_score: 82, provider_grade: "A" })).toBe("82 A");
    expect(tokenImpactLabel({ provider_score: null, provider_grade: null })).toBe("score --");
    expect(tokenImpactCompactLabel({ provider_score: null, provider_grade: null })).toBe("--");
    expect(
      tokenMarketLabel({ market_type: "cex", resolution_status: "resolved", lane: "resolved" }),
    ).toBe("CEX");
  });

  it("maps signal and token impact tones to compact CSS modifiers", () => {
    expect(newsSignalTone({ direction: "bullish" })).toBe("is-long");
    expect(newsSignalTone({ direction: "bearish" })).toBe("is-short");
    expect(tokenImpactTone({ provider_signal: "long" })).toBe("is-long");
    expect(tokenImpactTone({ provider_signal: "short" })).toBe("is-short");
  });

  it("merges provider token impacts onto resolved token lanes for display only", () => {
    const lanes = newsDisplayTokenLanes({
      token_lanes: [{ lane: "resolved", symbol: "BTC", target_id: "token:btc" }],
      token_impacts: [
        { lane: "provider", symbol: "BTC", provider_score: 91, provider_grade: "A" },
        { lane: "provider", symbol: "SOL", provider_score: 70, provider_grade: "B" },
      ],
    });

    expect(lanes).toMatchObject([
      { symbol: "BTC", target_id: "token:btc", provider_score: 91, provider_grade: "A" },
      { symbol: "SOL", provider_score: 70, provider_grade: "B" },
    ]);
  });
});
