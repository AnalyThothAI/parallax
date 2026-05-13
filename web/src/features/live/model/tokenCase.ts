import {
  compactNumber,
  formatDecision,
  formatPercentShare,
  formatRisk,
  formatScore,
  formatSignedPercent,
  formatTokenPriceUsd,
  formatUsdCompact,
  shortAddress,
  tokenKey,
  tokenLabel,
} from "@lib/format";
import type { Decision, TokenFlowItem, TokenProfileBlock } from "@lib/types";
import { tokenVenueAction } from "@lib/venue";
import type {
  ObsidianSource,
  ObsidianStringField,
  ObsidianTone,
} from "@shared/ui/obsidianLanguage";

import { isDexMarket } from "../../../domain/tokenTarget";

export type TokenCaseTone = ObsidianTone;

export type TokenCaseSource = ObsidianSource;

export type TokenCaseField = ObsidianStringField;

export type TokenCaseAction = {
  searchHref: string;
  searchLabel: string;
  venueHref?: string;
  venueLabel?: string;
};

export type TokenCaseView = {
  actions: TokenCaseAction;
  community: TokenCaseField;
  decision: TokenCaseField;
  evidence: string[];
  identity: TokenCaseField;
  key: string;
  label: string;
  market: TokenCaseField;
  narrative: TokenCaseField;
  official: TokenCaseField;
  score: string;
  subtitle: string;
};

const DECISION_TONES: Record<Decision, TokenCaseTone> = {
  discard: "risk",
  driver: "opportunity",
  investigate: "info",
  watch: "neutral",
};

export function buildTokenCaseView(item: TokenFlowItem): TokenCaseView {
  const label = tokenLabel(item);
  const venueAction = tokenVenueAction(item);
  const identityDetail = identitySubtitle(item);
  const official = officialField(item.profile);
  const marketDetail = marketMeta(item, marketDelta(item));
  const evidence = item.opportunity.reasons.map(compactLabel);

  return {
    actions: {
      searchHref: searchHref(item),
      searchLabel: "Search Intel",
      venueHref: venueAction?.url,
      venueLabel: venueAction?.label,
    },
    community: {
      detail: communityDetail(item),
      label: "Community",
      source: "social",
      tone:
        item.watch.direct_mentions > 0 || item.social_heat.watched_share > 0 ? "health" : "neutral",
      value: `${compactNumber(item.flow.mentions)} posts · ${compactNumber(
        item.propagation.independent_authors,
      )} authors`,
    },
    decision: {
      detail: decisionDetail(item),
      label: "Decision",
      source: "deterministic",
      tone: DECISION_TONES[item.opportunity.decision],
      value: formatDecision(item.opportunity.decision),
    },
    evidence,
    identity: {
      detail: identityDetail,
      label: "Identity",
      source: "deterministic",
      tone: item.identity.target_id ? "info" : "neutral",
      value: label,
    },
    key: tokenKey(item),
    label,
    market: {
      detail: marketDetail,
      label: "Market",
      source: "market",
      tone: marketTone(item),
      value: marketPrimary(item),
    },
    narrative: {
      detail: narrativeDetail(item),
      label: "Narrative",
      source: "deterministic",
      tone: narrativeTone(item),
      value: `${compactLabel(item.propagation.phase)} · ${qualityLabel(item)}`,
    },
    official,
    score: formatScore(item.opportunity.score),
    subtitle: identityDetail,
  };
}

export function identitySubtitle(item: TokenFlowItem): string {
  if (item.identity.venue_type === "cex") {
    return (
      [item.identity.exchange?.toUpperCase(), item.identity.inst_id].filter(Boolean).join(" · ") ||
      "CEX"
    );
  }
  if (item.identity.address) {
    return `${item.identity.chain ?? "unknown"} · ${shortAddress(item.identity.address)}`;
  }
  if (item.identity.target_type && item.identity.target_id) {
    return item.identity.chain ? `${item.identity.chain} · resolved target` : "resolved target";
  }
  const reason = item.identity.resolution_reasons?.[0] ?? item.identity.identity_status;
  const candidateText = item.identity.candidate_count
    ? ` · ${compactNumber(item.identity.candidate_count)} candidates`
    : "";
  const discoveryText = item.identity.discovery_status
    ? ` · ${compactLabel(item.identity.discovery_status)}`
    : "";
  return `symbol-only · ${formatRisk(reason)}${candidateText}${discoveryText}`;
}

export function marketPrimary(item: TokenFlowItem): string {
  if (isDexMarket(item)) {
    return item.market.market_cap !== null && item.market.market_cap !== undefined
      ? formatUsdCompact(item.market.market_cap)
      : "-";
  }
  if (item.market.market_cap !== null && item.market.market_cap !== undefined) {
    return formatUsdCompact(item.market.market_cap);
  }
  if (item.market.price !== null && item.market.price !== undefined) {
    return formatTokenPriceUsd(item.market.price);
  }
  return "-";
}

export function marketMeta(item: TokenFlowItem, delta: string): string {
  const details = marketFreshnessDetails(item);
  const parts = [
    marketDeltaLabel(delta),
    marketStatusLabel(item.market.market_status),
    ...details,
  ].filter((part): part is string => Boolean(part));
  return parts.join(" · ") || "market data unavailable";
}

export function timingMeta(item: TokenFlowItem): string {
  if (item.timing.status === "market_pending") {
    return "market observation pending";
  }
  if (item.timing.status === "market_unavailable") {
    return formatRisk(
      item.timing.market_observation_status ??
        item.market.market_observation_status ??
        item.timing.risks[0],
    );
  }
  if (item.timing.chase_risk || item.timing.status === "chase_risk") {
    return `${formatSignedPercent(
      item.timing.price_change_before_social_pct ?? item.market.price_change_before_social_pct,
    )} before social`;
  }
  const risk = item.timing.risks[0] ?? item.timing.reasons[0];
  if (risk) {
    return formatRisk(risk);
  }
  const change =
    item.timing.price_change_since_social_pct ?? item.market.price_change_since_social_pct;
  if (change !== null && change !== undefined) {
    return `${formatSignedPercent(change)} since social`;
  }
  if (
    item.market.price_change_status &&
    item.market.price_change_status !== "ready" &&
    item.market.price_change_status !== "insufficient_history" &&
    item.market.price_change_status !== "live_not_persisted"
  ) {
    return formatRisk(item.market.price_change_status);
  }
  return marketStatusLabel(item.market.market_status) ?? "";
}

function officialField(profile?: TokenProfileBlock | null): TokenCaseField {
  const status = cleanText(profile?.status)?.toLowerCase() ?? "unavailable";
  const source = profile?.source ?? {};
  const provider = cleanText(profile?.provider) ?? cleanText(source.provider);

  if (!profile || status !== "ready") {
    return {
      detail: [`profile ${status}`, provider].filter(Boolean).join(" · "),
      label: "Official",
      source: "official",
      tone: "neutral",
      value: "Official profile unavailable",
    };
  }

  const identity = profile.identity ?? {};
  const links = profile.links ?? {};
  const website = hostLabel(links.website_url);
  const twitter = cleanText(links.twitter_username)?.replace(/^@+/, "");
  const description = cleanText(identity.description);
  const linkDetail = [
    website,
    twitter ? `@${twitter}` : null,
    provider,
    description ? "description ready" : null,
  ].filter(Boolean);

  return {
    detail: linkDetail.join(" · ") || "profile ready",
    label: "Official",
    source: "official",
    tone: "info",
    value: cleanText(identity.name) ?? cleanText(identity.symbol) ?? "Official profile ready",
  };
}

function communityDetail(item: TokenFlowItem): string {
  const topAuthors = item.propagation.top_authors
    .map((author) => author.handle?.replace(/^@+/, ""))
    .filter((handle): handle is string => Boolean(handle))
    .slice(0, 2)
    .map((handle) => `@${handle}`);
  const watched = item.watch.direct_mentions || item.discussion_quality.watched_source_count;
  return [
    `watched ${compactNumber(watched)}`,
    `top share ${formatPercentShare(item.propagation.top_author_share)}`,
    topAuthors.length ? `lead ${topAuthors.join(", ")}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function narrativeDetail(item: TokenFlowItem): string {
  const reason = item.discussion_quality.reasons[0] ?? item.propagation.reasons[0];
  const risk = item.discussion_quality.risks[0] ?? item.propagation.risks[0];
  return [
    reason ? compactLabel(reason) : null,
    risk ? formatRisk(risk) : null,
    `${compactNumber(item.discussion_quality.informative_post_count)} informative`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function decisionDetail(item: TokenFlowItem): string {
  const reasons = item.opportunity.reasons.slice(0, 2).map(compactLabel);
  const risks = item.opportunity.risks.slice(0, 2).map(formatRisk);
  return [
    `score ${formatScore(item.opportunity.score)}`,
    ...reasons,
    ...risks.map((risk) => `risk ${risk}`),
  ].join(" · ");
}

function marketDelta(item: TokenFlowItem): string {
  return formatSignedPercent(
    item.market.price_change_since_social_pct ?? item.market.price_change_since_first_snapshot_pct,
  );
}

function marketDeltaLabel(delta: string): string | null {
  return delta === "-" ? null : delta;
}

function marketStatusLabel(marketStatus: string): string | null {
  if (marketStatus === "live") {
    return "live";
  }
  if (marketStatus === "anchored" || marketStatus === "fresh" || marketStatus === "ready") {
    return null;
  }
  return compactLabel(marketStatus);
}

function marketFreshnessDetails(item: TokenFlowItem): string[] {
  const marketStatus = item.market.market_status;
  const details: string[] = [];
  if (!isDexMarket(item) && shouldShowFieldStatus(item.market.price_status, marketStatus)) {
    details.push(`price ${compactLabel(item.market.price_status)}`);
  }
  if (
    isDexMarket(item) &&
    (item.market.market_cap === null || item.market.market_cap === undefined) &&
    item.market.market_cap_status
  ) {
    details.push(`cap ${compactLabel(item.market.market_cap_status)}`);
  }
  if (
    item.market.market_cap !== null &&
    item.market.market_cap !== undefined &&
    shouldShowFieldStatus(item.market.market_cap_status, marketStatus)
  ) {
    details.push(`cap ${compactLabel(item.market.market_cap_status)}`);
  }
  if (
    item.market.liquidity !== null &&
    item.market.liquidity !== undefined &&
    shouldShowFieldStatus(item.market.liquidity_status, marketStatus)
  ) {
    details.push(`liq ${compactLabel(item.market.liquidity_status)}`);
  }
  return details;
}

function shouldShowFieldStatus(
  fieldStatus: string | null | undefined,
  marketStatus: string,
): boolean {
  if (!fieldStatus) {
    return false;
  }
  if (fieldStatus === marketStatus) {
    return false;
  }
  if (fieldStatus === "ready" || fieldStatus === "fresh" || fieldStatus === "live") {
    return false;
  }
  if (marketStatus === "missing" && fieldStatus === "missing") {
    return false;
  }
  return true;
}

function marketTone(item: TokenFlowItem): TokenCaseTone {
  if (item.market.market_status === "missing") {
    return "risk";
  }
  if (item.market.market_status === "partial" || item.market.market_status === "stale") {
    return "info";
  }
  return "health";
}

function narrativeTone(item: TokenFlowItem): TokenCaseTone {
  if (item.discussion_quality.score >= 70 && item.propagation.independent_authors >= 3) {
    return "opportunity";
  }
  if (item.discussion_quality.risks.length || item.propagation.risks.length) {
    return "risk";
  }
  return "neutral";
}

function searchHref(item: TokenFlowItem): string {
  const query =
    item.identity.symbol ??
    item.identity.address ??
    item.identity.target_id ??
    item.identity.identity_key;
  return `/search?q=${encodeURIComponent(query)}`;
}

function hostLabel(value?: string | null): string | null {
  const text = cleanText(value);
  if (!text) {
    return null;
  }
  try {
    return new URL(text).hostname.replace(/^www\./, "");
  } catch {
    return text.replace(/^https?:\/\//, "").replace(/^www\./, "");
  }
}

function cleanText(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function compactLabel(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "-";
}

function qualityLabel(item: TokenFlowItem): string {
  const reason = item.discussion_quality.reasons[0] ?? item.discussion_quality.risks[0] ?? "";
  const labels: Record<string, string> = {
    catalyst: "catalyst",
    duplicate_text_cluster: "repeat",
    informative_discussion: "informative",
    low_duplicate_share: "low dup",
    low_information_posts: "meme only",
    repeated_text_cluster: "repeat",
    resolved_direct_evidence: "CA direct",
    seed_linked: "seed+CA",
  };
  return labels[reason] ?? compactLabel(reason);
}
