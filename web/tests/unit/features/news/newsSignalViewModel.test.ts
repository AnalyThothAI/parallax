import {
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenImpactLabel,
  tokenImpactTone,
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
    expect(newsSignalScoreLabel({ score: null, grade: null })).toBe("partial");
  });

  it("uses token impact labels for per-token chip scores", () => {
    expect(tokenImpactLabel({ provider_score: 82, provider_grade: "A" })).toBe("82 A");
    expect(tokenImpactLabel({ provider_score: null, provider_grade: null })).toBe("impact pending");
  });

  it("maps signal and token impact tones to compact CSS modifiers", () => {
    expect(newsSignalTone({ direction: "bullish" })).toBe("is-long");
    expect(newsSignalTone({ direction: "bearish" })).toBe("is-short");
    expect(tokenImpactTone({ provider_signal: "long" })).toBe("is-long");
    expect(tokenImpactTone({ provider_signal: "short" })).toBe("is-short");
  });
});
