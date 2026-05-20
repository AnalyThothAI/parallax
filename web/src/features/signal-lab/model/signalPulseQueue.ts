import { formatRelativeTime, shortAddress } from "@lib/format";
import type { SignalPulseItem } from "@lib/types";

export type SignalPulseQueueTone = "alert" | "health" | "neutral" | "risk" | "warn";

export type SignalPulseQueueChip = {
  label: string;
  tone: SignalPulseQueueTone;
};

export type SignalPulseQueueItemView = {
  candidateId: string;
  key: string;
  meta: string;
  score: {
    caption: string;
    value: string;
  };
  summary: string;
  symbol: string;
  timeIso?: string;
  timeLabel: string;
  title: string;
  tone: "default" | "risk";
  chips: SignalPulseQueueChip[];
  verdict: {
    confidenceLabel: string;
    label: string;
  };
};

export function buildSignalPulseQueueItem(item: SignalPulseItem): SignalPulseQueueItemView {
  const subject = item.factor_snapshot.subject;
  const symbol = formatSymbol(subject.symbol ?? item.symbol ?? item.subject_key);
  const mentions = intFact(item, "mentions_1h");
  const authors = intFact(item, "unique_authors");
  const watchedMentions = intFact(item, "watched_mentions");
  const topAuthorShare = numberFact(
    item.factor_snapshot.families.social_propagation.facts.top_author_share,
  );
  const liquidity = numberFact(
    item.factor_snapshot.market.decision_latest?.liquidity_usd ?? item.fact_card.liquidity_usd,
  );
  const latestStatus = item.factor_snapshot.market.readiness.latest_status ?? "";
  const marketIsStale = latestStatus === "stale";
  const title = buildTitle({ item, liquidity, marketIsStale, topAuthorShare });
  const chips = buildChips({
    authors,
    item,
    marketIsStale,
    mentions,
    topAuthorShare,
    watchedMentions,
  });
  return {
    candidateId: item.candidate_id,
    key: item.candidate_id || item.target_id || item.subject_key,
    meta: buildMeta(item),
    score: {
      caption: "热度分",
      value: String(Math.round(scoreValue(item))),
    },
    summary: item.decision.summary_zh || "Agent 暂无摘要。",
    symbol,
    timeIso: formatTimeIso(item.updated_at_ms),
    timeLabel: formatTimeLabel(item.updated_at_ms),
    title,
    tone: hasHardRisk({ liquidity, marketIsStale, topAuthorShare }) ? "risk" : "default",
    chips,
    verdict: {
      confidenceLabel: confidenceLabel(item.decision.confidence),
      label: recommendationLabel(item.decision.recommendation),
    },
  };
}

function formatTimeLabel(value: number | null | undefined): string {
  return hasValidTimestamp(value) ? `${formatRelativeTime(value)}前` : "时间未知";
}

function formatTimeIso(value: number | null | undefined): string | undefined {
  return hasValidTimestamp(value) ? new Date(value).toISOString() : undefined;
}

function hasValidTimestamp(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function buildTitle({
  item,
  liquidity,
  marketIsStale,
  topAuthorShare,
}: {
  item: SignalPulseItem;
  liquidity: number | null;
  marketIsStale: boolean;
  topAuthorShare: number | null;
}): string {
  const lowLiquidity = liquidity != null && liquidity < 50_000;
  const concentrated = topAuthorShare != null && topAuthorShare >= 0.5;
  if (lowLiquidity && concentrated) {
    return "热度很高，但流动性极浅且作者集中";
  }
  if (concentrated) {
    return "社交热度强，但疑似少数账号主导";
  }
  if (marketIsStale) {
    return "社交热度上升，但市场数据需要核验";
  }
  if (item.decision.recommendation === "watchlist") {
    return "Agent 建议先观察，不是直接交易结论";
  }
  if ((item.decision.confidence ?? 0) < 0.5 && scoreValue(item) >= 80) {
    return "高热度信号，但 Agent 信心偏低";
  }
  return "Agent 留下的候选信号";
}

function buildChips({
  authors,
  item,
  marketIsStale,
  mentions,
  topAuthorShare,
  watchedMentions,
}: {
  authors: number | null;
  item: SignalPulseItem;
  marketIsStale: boolean;
  mentions: number | null;
  topAuthorShare: number | null;
  watchedMentions: number | null;
}): SignalPulseQueueChip[] {
  const chips: SignalPulseQueueChip[] = [];
  const watchedOnly =
    mentions != null && mentions > 0 && watchedMentions != null && watchedMentions >= mentions;
  if (item.scope === "matched") {
    chips.push({ label: "关注匹配", tone: "alert" });
  }
  const displayStatus = item.display_status ?? "";
  if (displayStatus.startsWith("hidden_")) {
    chips.push({ label: hiddenDisplayLabel(displayStatus), tone: "risk" });
  }
  if (watchedOnly) {
    chips.push({ label: "仅关注源", tone: "alert" });
  }
  if (authors != null) {
    chips.push({
      label: `独立作者 ${authors}`,
      tone: authors <= 1 ? "warn" : "health",
    });
  }
  if (topAuthorShare != null && topAuthorShare >= 0.3) {
    chips.push({
      label: `头部${Math.round(topAuthorShare * 100)}%`,
      tone: topAuthorShare >= 0.5 ? "risk" : "warn",
    });
  }
  if (mentions != null) {
    chips.push({ label: `提及 ${mentions} / 1h`, tone: "warn" });
  }
  if (marketIsStale) {
    chips.push({ label: "市场过期", tone: "risk" });
  } else if (!item.factor_snapshot.market.event_anchor) {
    chips.push({ label: "锚点缺失", tone: "risk" });
  }
  return chips.slice(0, 4);
}

function hiddenDisplayLabel(value: string): string {
  return value.replace(/^hidden_/, "隐藏 ").replaceAll("_", " ");
}

function buildMeta(item: SignalPulseItem): string {
  const subject = item.factor_snapshot.subject;
  const values = [
    subject.chain?.toUpperCase(),
    subject.target_market_type?.toUpperCase(),
    shortAddress(subject.address ?? subject.target_id ?? item.target_id ?? null),
  ].filter((value): value is string => Boolean(value && value !== "-"));
  return values.join(" · ");
}

function formatSymbol(value: string | null | undefined): string {
  const clean = (value ?? "").trim();
  return clean ? `$${clean.replace(/^\$+/, "")}` : "$UNKNOWN";
}

function recommendationLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    high_conviction: "高确信",
    trade_candidate: "候选",
    watchlist: "观察",
    ignore: "忽略",
    abstain: "放弃",
  };
  return labels[value ?? ""] ?? (value ? value.replaceAll("_", " ") : "-");
}

function confidenceLabel(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "conf -";
  }
  return `conf ${value.toFixed(2)}`;
}

function scoreValue(item: SignalPulseItem): number {
  const score = item.candidate_score ?? item.factor_snapshot.composite.rank_score ?? 0;
  return Number.isFinite(score) ? Number(score) : 0;
}

function intFact(
  item: SignalPulseItem,
  key: "mentions_1h" | "unique_authors" | "watched_mentions",
): number | null {
  const fromCard = numberFact(item.fact_card[key]);
  if (fromCard != null) {
    return Math.round(fromCard);
  }
  const fromHeat = numberFact(item.factor_snapshot.families.social_heat.facts[key]);
  if (fromHeat != null) {
    return Math.round(fromHeat);
  }
  if (key === "unique_authors") {
    const independent = numberFact(
      item.factor_snapshot.families.social_propagation.facts.independent_authors,
    );
    return independent == null ? null : Math.round(independent);
  }
  return null;
}

function numberFact(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function hasHardRisk({
  liquidity,
  marketIsStale,
  topAuthorShare,
}: {
  liquidity: number | null;
  marketIsStale: boolean;
  topAuthorShare: number | null;
}): boolean {
  return Boolean(
    marketIsStale ||
    (topAuthorShare != null && topAuthorShare >= 0.5) ||
    (liquidity != null && liquidity < 50_000),
  );
}
