import type { NewsRow, NewsSignalSummary, NewsTokenLane } from "@shared/model/newsIntel";

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
    ? "score --"
    : [signal.grade, String(signal.score)].filter(Boolean).join(" · ");

export const tokenImpactLabel = (
  lane: Pick<NewsTokenLane, "provider_score" | "provider_grade">,
): string =>
  lane.provider_score == null
    ? "score --"
    : [String(lane.provider_score), lane.provider_grade].filter(Boolean).join(" ");

export const tokenImpactCompactLabel = (
  lane: Pick<NewsTokenLane, "provider_score" | "provider_grade">,
): string =>
  lane.provider_score == null
    ? "--"
    : [String(lane.provider_score), lane.provider_grade].filter(Boolean).join(" ");

export const tokenImpactTone = (lane: Pick<NewsTokenLane, "provider_signal">): string =>
  lane.provider_signal === "long"
    ? "is-long"
    : lane.provider_signal === "short"
      ? "is-short"
      : "is-neutral";

export const tokenMarketLabel = (
  lane: Pick<NewsTokenLane, "market_type" | "resolution_status" | "lane">,
): string => lane.market_type?.toUpperCase() || lane.resolution_status || lane.lane || "token";

export const newsDisplayTokenLanes = (
  row: Pick<NewsRow, "token_lanes" | "token_impacts">,
): NewsTokenLane[] => {
  const lanes = row.token_lanes ?? [];
  const impacts = row.token_impacts ?? [];
  if (!impacts.length) return lanes;

  const impactsBySymbol = new Map(
    impacts
      .filter((impact) => impact.symbol)
      .map((impact) => [String(impact.symbol).toUpperCase(), impact]),
  );
  const seen = new Set<string>();
  const merged = lanes.map((lane) => {
    const symbol = lane.symbol ? String(lane.symbol).toUpperCase() : "";
    const impact = symbol ? impactsBySymbol.get(symbol) : undefined;
    if (symbol) seen.add(symbol);
    return impact ? { ...lane, ...impact } : lane;
  });

  for (const impact of impacts) {
    const symbol = impact.symbol ? String(impact.symbol).toUpperCase() : "";
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    merged.push({
      ...impact,
      lane: impact.lane || "provider",
      resolution_status: impact.resolution_status || "provider",
    });
  }
  return merged;
};
