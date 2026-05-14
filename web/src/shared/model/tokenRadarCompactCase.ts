import { compactNumber, formatReason, formatRisk, formatSignedPercent } from "@lib/format";
import type { TokenFlowItem } from "@lib/types";

import { buildTokenCaseView, marketMeta } from "./tokenCase";

export type TokenRadarCompactCase = ReturnType<typeof buildTokenRadarCompactCase>;

export function buildTokenRadarCompactCase(item: TokenFlowItem) {
  const tokenCase = buildTokenCaseView(item);
  const risk = compactRisk(item);
  const marketMove = compactMarketMove(item);

  return {
    externalLinks: compactExternalLinks(item, tokenCase.actions),
    label: tokenCase.label,
    logoUrl: item.profile?.identity?.logo_url ?? null,
    markTone: tokenCase.decision.tone,
    market: {
      ...tokenCase.market,
      detail: marketMeta(item, "-"),
    },
    marketMove,
    narrative: {
      detail: compactWhyNowDetail(item, risk),
      tone: risk ? "risk" : tokenCase.narrative.tone,
      value: compactWhyNowTitle(item),
    },
    score: tokenCase.score,
    searchTitle: tokenCase.actions.searchLabel,
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

function compactWhyNowTitle(item: TokenFlowItem): string {
  return `${phaseLabel(item.propagation.phase)} · ${compactNumber(
    item.discussion_quality.informative_post_count,
  )} 条有效讨论`;
}

function compactWhyNowDetail(item: TokenFlowItem, risk: string | null): string {
  if (risk) {
    return `风险：${risk}`;
  }
  if (item.flow.watched_mentions > 0) {
    return `关注源 ${compactNumber(item.flow.watched_mentions)} 次确认`;
  }
  const reason =
    item.discussion_quality.reasons[0] ??
    item.propagation.reasons[0] ??
    item.social_heat.reasons[0];
  return reason ? `催化：${formatReason(reason)}` : "暂无关注源确认";
}

function phaseLabel(phase: string): string {
  const labels: Record<string, string> = {
    concentration: "集中期",
    expansion: "扩散中",
    fade: "降温中",
    ignition: "点火中",
    seed: "种子中",
  };
  return labels[phase] ?? phase.replaceAll("_", " ");
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
