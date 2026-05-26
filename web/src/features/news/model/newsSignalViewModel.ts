import type { NewsSignalSummary, NewsTokenLane } from "@shared/model/newsIntel";

export const newsSignalLabel = (
  signal: Pick<NewsSignalSummary, "direction"> & Partial<NewsSignalSummary>,
): string =>
  signal.label_zh ??
  (signal.direction === "bullish" ? "利好" : signal.direction === "bearish" ? "利空" : "中性");

export const newsSignalTone = (signal: Pick<NewsSignalSummary, "direction">): string =>
  signal.direction === "bullish"
    ? "is-long"
    : signal.direction === "bearish"
      ? "is-short"
      : "is-neutral";

export const newsSignalScoreLabel = (signal: Pick<NewsSignalSummary, "score" | "grade">): string =>
  signal.score == null
    ? "partial"
    : [signal.grade, String(signal.score)].filter(Boolean).join(" · ");

export const tokenImpactLabel = (
  lane: Pick<NewsTokenLane, "provider_score" | "provider_grade">,
): string =>
  lane.provider_score == null
    ? "impact pending"
    : [String(lane.provider_score), lane.provider_grade].filter(Boolean).join(" ");

export const tokenImpactTone = (lane: Pick<NewsTokenLane, "provider_signal">): string =>
  lane.provider_signal === "long"
    ? "is-long"
    : lane.provider_signal === "short"
      ? "is-short"
      : "is-neutral";
