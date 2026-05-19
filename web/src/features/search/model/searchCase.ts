import {
  compactNumber,
  formatPercentShare,
  formatTokenPriceUsd,
  formatUsdCompact,
  shortAddress,
} from "@lib/format";
import type { SearchInspectData, SearchTargetCandidate, SearchTokenResult } from "@lib/types";
import { narrativeGapLabel } from "@shared/model/narrativeDataGaps";
import type {
  ObsidianSource,
  ObsidianStringField,
  ObsidianTone,
} from "@shared/ui/obsidianLanguage";

export type SearchCaseTone = ObsidianTone;

export type SearchCaseSource = ObsidianSource;

export type SearchCaseFact = ObsidianStringField;

export type SearchCaseView = {
  community: SearchCaseFact;
  evidence: SearchCaseFact;
  official: SearchCaseFact;
  market: SearchCaseFact;
  narrative: SearchCaseFact;
  resolver: SearchCaseFact;
  resultKind: SearchInspectData["query"]["result_kind"];
  subtitle: string;
  title: string;
};

export function buildSearchCaseView(data: SearchInspectData): SearchCaseView {
  if (data.query.result_kind === "token_result" && data.token_result) {
    return tokenSearchCase(data, data.token_result);
  }
  if (data.query.result_kind === "ambiguous_result" && data.ambiguous_result) {
    return {
      community: {
        detail: "topic evidence retained until a target is selected",
        label: "Community",
        source: "social",
        tone: data.ambiguous_result.summary.posts ? "health" : "neutral",
        value: `${compactNumber(data.ambiguous_result.summary.posts)} posts · ${compactNumber(
          data.ambiguous_result.summary.authors,
        )} authors`,
      },
      evidence: evidenceFact(data.ambiguous_result.items.length),
      official: {
        detail: `${data.ambiguous_result.candidates.length} resolver candidates`,
        label: "Official",
        source: "deterministic",
        tone: "neutral",
        value: "No single official target",
      },
      market: unavailableMarket(),
      narrative: agentNarrative(data.ambiguous_result.agent_brief.project_summary.one_liner),
      resolver: resolverFact(data),
      resultKind: data.query.result_kind,
      subtitle: "Ambiguous query; no silent token selection.",
      title: data.query.q,
    };
  }
  if (data.query.result_kind === "topic_result" && data.topic_result) {
    return {
      community: {
        detail: "topic evidence only",
        label: "Community",
        source: "social",
        tone: data.topic_result.summary.posts ? "health" : "neutral",
        value: `${compactNumber(data.topic_result.summary.posts)} posts · ${compactNumber(
          data.topic_result.summary.authors,
        )} authors`,
      },
      evidence: evidenceFact(data.topic_result.items.length),
      official: {
        detail: "topic result",
        label: "Official",
        source: "deterministic",
        tone: "neutral",
        value: "No token profile",
      },
      market: unavailableMarket(),
      narrative: agentNarrative(data.topic_result.agent_brief.project_summary.one_liner),
      resolver: resolverFact(data),
      resultKind: data.query.result_kind,
      subtitle: "Topic result; not resolved to one token.",
      title: data.query.q,
    };
  }
  return {
    community: emptyFact("Community", "social"),
    evidence: evidenceFact(0),
    official: emptyFact("Official", "official"),
    market: unavailableMarket(),
    narrative: emptyFact("Narrative", "agent"),
    resolver: resolverFact(data),
    resultKind: data.query.result_kind,
    subtitle: "No result available.",
    title: data.query.q || "Search case",
  };
}

function tokenSearchCase(data: SearchInspectData, result: SearchTokenResult): SearchCaseView {
  const profile = result.profile;
  const target = result.target;
  const officialName =
    cleanText(profile?.identity?.name) ??
    cleanText(profile?.identity?.symbol) ??
    (target.symbol ? `$${target.symbol}` : "Official profile unavailable");
  const officialDetail = [
    cleanText(profile?.identity?.description) ? "description ready" : null,
    hostLabel(profile?.links?.website_url),
    cleanText(profile?.provider),
  ]
    .filter(Boolean)
    .join(" · ");

  return {
    community: {
      detail: `watched ${compactNumber(result.timeline.summary.watched_posts ?? 0)} · top ${formatPercentShare(
        result.timeline.summary.top_author_share,
      )}`,
      label: "Community",
      source: "social",
      tone: result.timeline.summary.watched_posts ? "health" : "neutral",
      value: `${compactNumber(result.timeline.summary.posts)} posts · ${compactNumber(
        result.timeline.summary.authors,
      )} authors`,
    },
    evidence: evidenceFact(result.posts.returned_count),
    official: {
      detail: officialDetail || (profile?.status ? `profile ${profile.status}` : "profile missing"),
      label: "Official",
      source: "official",
      tone: profile?.status === "ready" ? "info" : "neutral",
      value: officialName,
    },
    market: marketFact(result),
    narrative: tokenDigestNarrative(result),
    resolver: resolverFact(data),
    resultKind: data.query.result_kind,
    subtitle: identityLine(target, searchMarketCandles(result)),
    title: target.symbol ? `$${target.symbol}` : shortTarget(target.target_id),
  };
}

function marketFact(result: SearchTokenResult): SearchCaseFact {
  const marketLive = asRecord(result.market_live);
  const marketCap = numberValue(marketLive.market_cap_usd);
  const price = numberValue(marketLive.price_usd);
  const provider = stringValue(marketLive.provider);
  const isDex = result.target.target_type === "Asset";
  return {
    detail: provider === "-" ? "market source unavailable" : provider,
    label: "Market",
    source: "market",
    tone: marketCap !== null || price !== null ? "health" : "neutral",
    value: isDex
      ? marketCap === null
        ? "-"
        : formatUsdCompact(marketCap)
      : formatTokenPriceUsd(price),
  };
}

function searchMarketCandles(result: SearchTokenResult): Record<string, unknown> {
  return asRecord(result.timeline.market_candles);
}

function resolverFact(data: SearchInspectData): SearchCaseFact {
  return {
    detail: data.resolver.reasons.join(" · ") || "no resolver reasons",
    label: "Resolver",
    source: "deterministic",
    tone: data.resolver.confidence >= 0.8 ? "health" : "info",
    value: `${Math.round(data.resolver.confidence * 100)}%`,
  };
}

function agentNarrative(value?: string | null): SearchCaseFact {
  return {
    detail: "agent memo boundary",
    label: "Narrative",
    source: "agent",
    tone: "agent",
    value: cleanText(value) ?? "Agent memo unavailable",
  };
}

function tokenDigestNarrative(result: SearchTokenResult): SearchCaseFact {
  const digest = result.discussion_digest;
  const dominant = digest.dominant_narrative;
  const coverage = digest.coverage?.semantic_coverage;
  const coverageDetail =
    typeof coverage === "number" && Number.isFinite(coverage)
      ? `${Math.round(coverage * 100)}% semantic coverage`
      : digest.status.replaceAll("_", " ");
  return {
    detail: cleanText(dominant?.summary_zh) ?? narrativeGapLabel(digest.data_gaps[0]) ?? coverageDetail,
    label: "Narrative",
    source: "social",
    tone: digest.status === "ready" ? "health" : "info",
    value: cleanText(dominant?.title) ?? digestStatusLabel(digest.status),
  };
}

function digestStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    insufficient: "Narrative insufficient",
    pending: "Narrative pending",
    ready: "Narrative ready",
    semantic_unavailable: "Narrative unavailable",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function evidenceFact(count: number): SearchCaseFact {
  return {
    detail: "source events in current result",
    label: "Evidence",
    source: "social",
    tone: count ? "health" : "neutral",
    value: `${compactNumber(count)} events`,
  };
}

function unavailableMarket(): SearchCaseFact {
  return {
    detail: "not a single token market case",
    label: "Market",
    source: "market",
    tone: "neutral",
    value: "Unavailable",
  };
}

function emptyFact(label: string, source: SearchCaseSource): SearchCaseFact {
  return {
    detail: "unavailable",
    label,
    source,
    tone: "neutral",
    value: "Unavailable",
  };
}

function identityLine(candidate: SearchTargetCandidate, marketCandles: Record<string, unknown>) {
  const chain = candidate.chain_id ?? stringValue(marketCandles.chain_id);
  const address = candidate.address ?? stringValue(marketCandles.address);
  const nativeMarket = stringValue(marketCandles.native_market_id);
  if (candidate.target_type === "CexToken" && nativeMarket !== "-") {
    return `${nativeMarket} · ${candidate.target_id}`;
  }
  if (address && address !== "-") {
    return `${chain || "chain"} · ${shortAddress(address)}`;
  }
  return candidate.target_id;
}

function shortTarget(value: string) {
  return value.length > 28 ? `${value.slice(0, 14)}...${value.slice(-8)}` : value;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "-";
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
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
