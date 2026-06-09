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
  detail?: string | null;
  tone: "is-ready" | "is-waiting" | "is-blocked" | "is-failed";
  title: string;
};

export const newsAgentReviewBadge = (
  row: Pick<NewsRow, "agent_brief" | "agent_brief_status" | "agent_status" | "signal">,
): NewsAgentReviewBadge => {
  const eligibility = row.signal.alert_eligibility;
  const agentSignal =
    row.signal.agent_signal && typeof row.signal.agent_signal === "object"
      ? row.signal.agent_signal
      : {};
  const status = String(
    row.agent_brief?.status ??
      eligibility?.agent_status ??
      row.agent_status ??
      row.agent_brief_status ??
      "pending",
  ).toLowerCase();
  const decisionClass = String(
    row.agent_brief?.decision_class ??
      eligibility?.decision_class ??
      agentSignal.decision_class ??
      "",
  ).toLowerCase();
  const reason =
    eligibility?.external_push_block_reason ?? eligibility?.agent_admission_reason ?? null;
  const badge = (
    label: string,
    tone: NewsAgentReviewBadge["tone"],
    detail: string | null = reason,
  ): NewsAgentReviewBadge => ({
    label,
    detail,
    tone,
    title: [label, detail].filter(Boolean).join(" · "),
  });

  if (eligibility?.external_push_ready === true) {
    return badge("AGENT READY", "is-ready", null);
  }
  if (status === "ready") {
    if (decisionClass === "driver" || decisionClass === "watch") {
      return badge("AGENT READY", "is-ready", null);
    }
    if (decisionClass === "context") {
      return badge("AGENT CONTEXT", "is-waiting", reason);
    }
    return badge("AGENT HOLD", "is-blocked", reason);
  }
  if (status === "insufficient") {
    return badge("AGENT INSUFF", "is-blocked");
  }
  if (status === "not_required" || status === "skipped") {
    return badge("AGENT SKIP", "is-blocked");
  }
  if (status === "failed") {
    return badge("AGENT FAILED", "is-failed", reason);
  }
  if (status === "disabled") {
    return badge("AGENT OFF", "is-failed", reason);
  }
  if (status === "stale") {
    return badge("AGENT STALE", "is-waiting", reason);
  }
  return badge("AGENT WAIT", "is-waiting", reason);
};

export const tokenMarketLabel = (
  lane: Pick<NewsTokenLane, "market_type" | "resolution_status" | "lane">,
): string => lane.market_type?.toUpperCase() || lane.resolution_status || lane.lane || "token";

export const newsDisplayTokenLanes = (
  row: Pick<NewsRow, "token_lanes" | "token_impacts">,
): NewsTokenLane[] => {
  return row.token_lanes ?? [];
};
