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

export type NewsAgentReviewBadge = {
  label: string;
  tone: "is-ready" | "is-waiting" | "is-blocked" | "is-failed";
};

export const newsAgentReviewBadge = (
  row: Pick<NewsRow, "agent_brief" | "agent_brief_status" | "agent_status" | "signal">,
): NewsAgentReviewBadge => {
  const eligibility = row.signal.alert_eligibility;
  const status = String(
    eligibility?.agent_status ?? row.agent_brief?.status ?? row.agent_status ?? row.agent_brief_status ?? "pending",
  ).toLowerCase();

  if (eligibility?.external_push_ready === true) {
    return { label: "AGENT READY", tone: "is-ready" };
  }
  if (status === "ready") {
    return { label: "AGENT HOLD", tone: "is-blocked" };
  }
  if (status === "insufficient") {
    return { label: "AGENT INSUFF", tone: "is-blocked" };
  }
  if (status === "failed") {
    return { label: "AGENT FAILED", tone: "is-failed" };
  }
  if (status === "disabled") {
    return { label: "AGENT OFF", tone: "is-failed" };
  }
  if (status === "stale") {
    return { label: "AGENT STALE", tone: "is-waiting" };
  }
  return { label: "AGENT WAIT", tone: "is-waiting" };
};

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
