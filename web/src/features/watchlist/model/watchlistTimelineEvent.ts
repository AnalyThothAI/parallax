import type { WatchlistSocialEvent, WatchlistTimelineItem } from "@lib/types";
import type { TokenCasePostEvent, TokenCaseTone } from "@shared/model/tokenCaseViewModel";
import {
  buildTokenPostEventMarket,
  cleanText,
  normalizeTokenSymbol,
  numberValue,
  relativeTimeLabel,
  tokenPricePill,
} from "@shared/model/tokenPostEvent";

type TokenResolution = NonNullable<WatchlistTimelineItem["token_resolutions"]>[number];

export function buildWatchlistTimelineEvent(item: WatchlistTimelineItem): TokenCasePostEvent {
  const social = item.social_event;
  const resolution = primaryResolution(item.token_resolutions);
  const price = resolution?.price;
  const summary = cleanText(social?.summary_zh);
  const sourceText = cleanText(item.text_clean);
  const text = summary ?? sourceText ?? "(empty source event)";
  const confidence = numberValue(social?.confidence);
  const tokenSymbols = uniqueStrings([
    resolutionSymbol(resolution),
    ...termsFromRecords(social?.token_candidates, "symbol"),
    ...(item.cashtags ?? []),
  ]);

  return {
    id: item.event_id,
    handle: cleanText(item.author_handle),
    text,
    sourceText: summary ? sourceText : null,
    detailsLabel: summary ? "Original" : null,
    url: cleanText(item.canonical_url),
    timestampMs: item.received_at_ms ?? null,
    timeLabel: item.received_at_ms ? relativeTimeLabel(item.received_at_ms) : null,
    phase: summary ? "signal" : "source",
    role: cleanText(social?.event_type) ?? cleanText(item.action),
    isWatched: true,
    pills: watchlistPills({ item, price, resolution, social, tokenSymbols }),
    market: buildTokenPostEventMarket({
      fallbackProvider: "mention price",
      observationKind: price?.observation_kind,
      priceUsd: price?.price_usd,
      provider: price?.provider,
      status: price?.status,
    }),
    quality: {
      score: confidence,
      scoreLabel:
        confidence === null ? "confidence -" : `confidence ${Math.round(confidence * 100)}%`,
      reasons: social?.semantic_risks ?? [],
      contributions: socialContributions(social),
    },
  };
}

function watchlistPills({
  item,
  price,
  resolution,
  social,
  tokenSymbols,
}: {
  item: WatchlistTimelineItem;
  price: TokenResolution["price"] | undefined;
  resolution: TokenResolution | null;
  social: WatchlistSocialEvent | null | undefined;
  tokenSymbols: string[];
}): TokenCasePostEvent["pills"] {
  const pricePill = tokenPricePill(price?.price_usd, price?.status);
  return uniquePills([
    {
      label: social?.summary_zh ? "signal" : "source",
      tone: social?.summary_zh ? "opportunity" : "health",
    },
    ...tokenSymbols.map((symbol) => ({ label: `$${symbol}`, tone: "opportunity" as const })),
    pricePill,
    resolution?.resolution_status
      ? { label: resolution.resolution_status.replaceAll("_", " "), tone: "info" as const }
      : null,
    social?.subject ? { label: social.subject, tone: "info" as const } : null,
    social?.direction_hint ? { label: social.direction_hint, tone: "neutral" as const } : null,
    ...(item.hashtags ?? []).map((value) => ({
      label: `#${value.replace(/^#+/, "")}`,
      tone: "neutral" as const,
    })),
  ]).slice(0, 8);
}

function socialContributions(
  social: WatchlistSocialEvent | null | undefined,
): TokenCasePostEvent["quality"]["contributions"] {
  if (!social) {
    return [];
  }
  const rows: TokenCasePostEvent["quality"]["contributions"] = [];
  if (social.impact_hint != null) {
    rows.push({
      label: "impact",
      value: formatHint(social.impact_hint),
      reason: "LLM social-event impact hint",
    });
  }
  if (social.semantic_novelty_hint != null) {
    rows.push({
      label: "novelty",
      value: formatHint(social.semantic_novelty_hint),
      reason: "LLM novelty hint",
    });
  }
  if (social.attention_mechanism) {
    rows.push({
      label: "attention",
      value: social.attention_mechanism,
      reason: "Detected attention mechanism",
    });
  }
  return rows;
}

function primaryResolution(
  resolutions: WatchlistTimelineItem["token_resolutions"],
): TokenResolution | null {
  return (
    (resolutions ?? []).find((resolution) => resolution.price?.price_usd != null) ??
    (resolutions ?? [])[0] ??
    null
  );
}

function resolutionSymbol(resolution: TokenResolution | null): string | null {
  return normalizeTokenSymbol(resolution?.symbol) ?? cexSymbolFromTargetId(resolution);
}

function cexSymbolFromTargetId(resolution: TokenResolution | null): string | null {
  if (resolution?.target_type !== "CexToken") {
    return null;
  }
  return normalizeTokenSymbol(resolution.target_id?.split(":").pop());
}

function uniquePills(
  values: Array<{ label: string; tone: TokenCaseTone } | null | undefined>,
): TokenCasePostEvent["pills"] {
  const seen = new Set<string>();
  const pills: TokenCasePostEvent["pills"] = [];
  for (const value of values) {
    if (!value || seen.has(value.label)) {
      continue;
    }
    seen.add(value.label);
    pills.push(value);
  }
  return pills;
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    const normalized = normalizeTokenSymbol(value);
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    out.push(normalized);
  }
  return out;
}

function termsFromRecords(
  records: Array<Record<string, unknown>> | undefined,
  key: string,
): string[] {
  return [
    ...new Set(
      (records ?? [])
        .map((item) => {
          const value = item[key];
          return typeof value === "string" ? value : "";
        })
        .filter(Boolean),
    ),
  ];
}

function formatHint(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}
