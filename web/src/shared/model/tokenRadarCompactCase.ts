import {
  compactNumber,
  formatRelativeTime,
  formatRisk,
  formatSignedPercent,
  formatUsdCompact,
} from "@lib/format";
import type { NarrativeStatus, TokenDiscussionDigest, TokenFlowItem } from "@lib/types";

import { narrativeGapLabel } from "./narrativeDataGaps";
import { buildTokenCaseView, marketMeta } from "./tokenCase";

export type TokenRadarCompactCase = ReturnType<typeof buildTokenRadarCompactCase>;

export function buildTokenRadarCompactCase(item: TokenFlowItem) {
  const tokenCase = buildTokenCaseView(item);
  const risk = compactRisk(item);
  const marketMove = compactMarketMove(item);

  return {
    externalLinks: compactExternalLinks(item, tokenCase.actions),
    label: tokenCase.label,
    listed: compactListedAt(item),
    logoUrl: cleanText(item.profile?.identity?.logo_url),
    markTone: tokenCase.decision.tone,
    market: {
      ...tokenCase.market,
      detail: compactMarketDetail(item),
      stats: compactMarketStats(item),
    },
    marketMove,
    narrative: {
      detail: compactWhyNowDetail(item),
      tone: compactWhyNowTone(item.discussion_digest, risk, tokenCase.narrative.tone),
      value: compactWhyNowTitle(item),
    },
    score: tokenCase.score,
    socialDetail: `关注源 ${compactNumber(item.flow.watched_mentions)} · 较前窗 ${signedCompactNumber(
      item.flow.mention_delta,
    )}`,
    socialFact: `${compactNumber(item.flow.mentions)} 帖 · ${compactNumber(
      item.propagation.independent_authors,
    )} 作者`,
    subtitle: tokenCase.subtitle,
  };
}

type CompactExternalLink = {
  href: string;
  label: string;
  tone: "official" | "venue";
};

type TokenCaseAction = ReturnType<typeof buildTokenCaseView>["actions"];

function compactExternalLinks(
  item: TokenFlowItem,
  actions: TokenCaseAction,
): CompactExternalLink[] {
  const links = item.profile?.links ?? {};
  return [
    link("官网", cleanText(links.website_url), "official"),
    link("X", cleanText(links.twitter_url) ?? twitterHref(links.twitter_username), "official"),
    link(actions.venueLabel ?? "", actions.venueHref ?? null, "venue"),
  ].filter((item): item is CompactExternalLink => Boolean(item));
}

function link(
  label: string,
  href: string | null,
  tone: CompactExternalLink["tone"],
): CompactExternalLink | null {
  if (!label || !href) {
    return null;
  }
  return { href, label, tone };
}

function compactRisk(item: TokenFlowItem): string | null {
  const risk =
    item.tradeability.risks[0] ??
    item.timing.risks[0] ??
    item.discussion_quality.risks[0] ??
    item.propagation.risks[0] ??
    item.opportunity.risks[0];
  return risk ? formatRisk(risk) : null;
}

function compactMarketMove(item: TokenFlowItem): {
  direction: "down" | "flat" | "up";
  value: string;
} {
  const change =
    item.market.price_change_since_social_pct ??
    item.market.price_change_since_first_snapshot_pct ??
    item.timing.price_change_since_social_pct;
  return {
    direction:
      change === null || change === undefined
        ? "flat"
        : change > 0
          ? "up"
          : change < 0
            ? "down"
            : "flat",
    value: formatSignedPercent(change),
  };
}

function compactMarketDetail(item: TokenFlowItem): string {
  const stats = compactMarketStats(item);
  return stats.length
    ? stats.map((stat) => `${stat.label} ${stat.value}`).join(" · ")
    : marketMeta(item, "-");
}

type CompactMarketStat = {
  key: "holders" | "liq" | "vol";
  label: string;
  status: string;
  tone: "holders" | "liquidity" | "volume";
  value: string;
};

function compactMarketStats(item: TokenFlowItem): CompactMarketStat[] {
  return [
    marketStat("liq", "liq", item.market.liquidity, item.market.liquidity_status, "liquidity"),
    marketStat("vol", "vol", item.market.volume_24h, item.market.volume_24h_status, "volume"),
    marketStat(
      "holders",
      "holders",
      item.market.holder_count,
      item.market.holder_count_status,
      "holders",
    ),
  ].filter((stat): stat is CompactMarketStat => Boolean(stat));
}

function marketStat(
  key: CompactMarketStat["key"],
  label: CompactMarketStat["label"],
  value: number | null | undefined,
  status: string | null | undefined,
  tone: CompactMarketStat["tone"],
): CompactMarketStat | null {
  if (value === null || value === undefined) {
    return null;
  }
  const formatted = key === "holders" ? compactNumber(value) : formatUsdCompact(value);
  return {
    key,
    label,
    status: statusLabel(status, label),
    tone,
    value: formatted,
  };
}

function compactListedAt(item: TokenFlowItem): {
  detail: string;
  timestampMs: number | null;
  value: string;
} {
  const listedAtMs =
    item.radar?.listed_at_ms ?? item.radar?.computed_at_ms ?? item.flow.window_end_ms ?? null;
  return {
    detail: item.radar?.rank ? `#${item.radar.rank}` : "rank -",
    timestampMs: listedAtMs,
    value: listedAtMs ? `${formatRelativeTime(listedAtMs)}前` : "-",
  };
}

function compactWhyNowTitle(item: TokenFlowItem): string {
  const digest = item.discussion_digest;
  if (!digest) {
    return narrativeStatusTitle("semantic_unavailable");
  }
  const currentness = digest.currentness;
  const displayStatus = currentness.display_status;
  if (displayStatus === "unsupported_window") {
    return "5m 实时信号";
  }
  if (displayStatus === "not_ready" || displayStatus === "out_of_frontier") {
    return firstGapLabel(digest) ?? currentnessTitle(displayStatus);
  }
  if (digest.status !== "ready") {
    return firstGapLabel(digest) ?? narrativeStatusTitle(digest.status);
  }
  const title = cleanText(digest.dominant_narrative?.title) ?? "叙事已读取";
  if (displayStatus === "updating") {
    return `${title} · 更新中 +${compactNumber(currentness.delta_source_event_count ?? 0)}`;
  }
  if (displayStatus === "stale") {
    return `${title} · 上一版`;
  }
  const stance = topMixLabel(digest.stance_mix);
  return stance ? `${title} · ${stance}` : title;
}

function compactWhyNowDetail(item: TokenFlowItem): string {
  const digest = item.discussion_digest;
  if (!digest) {
    return "discussion digest missing";
  }
  const displayStatus = digest.currentness.display_status;
  const gap = firstGapLabel(digest);
  if (displayStatus === "unsupported_window") {
    return "5m 实时信号";
  }
  if (displayStatus === "not_ready" || displayStatus === "out_of_frontier") {
    return gap ?? currentnessTitle(displayStatus);
  }
  if (digest.status !== "ready") {
    return gap ?? narrativeStatusTitle(digest.status);
  }
  const summary = cleanText(digest.dominant_narrative?.summary_zh) ?? gap ?? "ready";
  const details = [summary, coverageLabel(digest), pulseOverlayLabel(item)].filter(Boolean);
  return details.join(" · ");
}

function compactWhyNowTone(
  digest: TokenDiscussionDigest | null | undefined,
  risk: string | null,
  fallbackTone: string,
): string {
  const displayStatus = digest?.currentness.display_status;
  if (displayStatus === "updating") {
    return "info";
  }
  if (displayStatus === "stale" || displayStatus === "out_of_frontier") {
    return "warn";
  }
  if (displayStatus === "not_ready" || displayStatus === "unsupported_window") {
    return risk ? "risk" : "info";
  }
  if (digest?.status === "ready") {
    return fallbackTone;
  }
  if (digest?.status === "insufficient" || digest?.status === "semantic_unavailable" || risk) {
    return "risk";
  }
  return "info";
}

function narrativeStatusTitle(status: NarrativeStatus): string {
  const labels: Record<string, string> = {
    insufficient: "叙事样本不足",
    pending: "叙事分析中",
    semantic_unavailable: "叙事分析暂不可用",
    stale: "叙事待刷新",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function currentnessTitle(status: string): string {
  const labels: Record<string, string> = {
    current: "叙事已更新",
    not_ready: "叙事待生成",
    out_of_frontier: "不在当前雷达前沿",
    stale: "上一版",
    unsupported_window: "5m 实时信号",
    updating: "叙事更新中",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function firstGapLabel(digest: TokenDiscussionDigest): string | null {
  return narrativeGapLabel(digest.data_gaps.find(Boolean));
}

function topMixLabel(mix: TokenDiscussionDigest["stance_mix"]): string | null {
  const top = Object.entries(mix ?? {})
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => Number(right[1]) - Number(left[1]))[0];
  if (!top) {
    return null;
  }
  const [label, value] = top;
  return `${label} ${Math.round(Number(value) * 100)}%`;
}

function coverageLabel(digest: TokenDiscussionDigest): string | null {
  const coverage = digest.coverage?.semantic_coverage;
  return typeof coverage === "number" && Number.isFinite(coverage)
    ? `coverage ${Math.round(coverage * 100)}%`
    : null;
}

function pulseOverlayLabel(item: TokenFlowItem): string | null {
  const pulse = item.pulse_overlay;
  if (!pulse || pulse.status !== "ready") {
    return null;
  }
  const summary = cleanText(pulse.verdict) ?? cleanText(pulse.recommendation) ?? pulse.pulse_status;
  return summary ? `Pulse ${summary}` : "Pulse ready";
}

function signedCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  if (value > 0) {
    return `+${compactNumber(value)}`;
  }
  if (value < 0) {
    return `-${compactNumber(Math.abs(value))}`;
  }
  return "0";
}

function twitterHref(value?: string | null): string | null {
  const username = cleanText(value)?.replace(/^@+/, "");
  return username ? `https://x.com/${encodeURIComponent(username)}` : null;
}

function cleanText(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function statusLabel(value?: string | null, readyLabel = "live"): string {
  if (!value || value === "live" || value === "ready" || value === "fresh") {
    return readyLabel;
  }
  return value.replaceAll("_", " ");
}
