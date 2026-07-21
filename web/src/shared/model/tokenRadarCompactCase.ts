import {
  compactNumber,
  formatRelativeTime,
  formatSignedPercent,
  formatUsdCompact,
} from "@lib/format";
import type { NarrativeAdmission, TokenFlowItem } from "@lib/types";

import { buildTokenCaseView, marketMeta } from "./tokenCase";

export type TokenRadarCompactCase = ReturnType<typeof buildTokenRadarCompactCase>;

export function buildTokenRadarCompactCase(item: TokenFlowItem) {
  const tokenCase = buildTokenCaseView(item);
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
    admission: {
      detail: admissionDetail(item.narrative_admission),
      tone: admissionTone(item.narrative_admission),
      value: admissionTitle(item.narrative_admission),
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

function admissionTitle(admission: NarrativeAdmission | null | undefined): string {
  if (!admission) return "Admission missing";
  if (admission.currentness.display_status === "unsupported_window") {
    return "Admission unsupported";
  }
  if (admission.currentness.display_status === "out_of_frontier") {
    return "Out of current frontier";
  }
  const labels: Record<string, string> = {
    admitted: "Admitted",
    missing: "Not admitted",
    suppressed: "Suppressed",
    unsupported_window: "Admission unsupported",
  };
  return labels[admission.status] ?? admission.status.replaceAll("_", " ");
}

function admissionDetail(admission: NarrativeAdmission | null | undefined): string {
  if (!admission) return "no current admission";
  const { independent_authors: authors, source_mentions: mentions } = admission.coverage;
  return `${compactNumber(mentions)} posts · ${compactNumber(authors)} authors`;
}

function admissionTone(admission: NarrativeAdmission | null | undefined): string {
  if (admission?.status === "admitted" && admission.currentness.display_status === "current") {
    return "health";
  }
  if (
    admission?.status === "suppressed" ||
    admission?.currentness.display_status === "out_of_frontier"
  ) {
    return "warn";
  }
  return "info";
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
