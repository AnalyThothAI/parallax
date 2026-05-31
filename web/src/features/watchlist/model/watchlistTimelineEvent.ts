import type { WatchlistTimelineItem } from "@lib/types";
import type { TokenCasePostEvent, TokenCaseTone } from "@shared/model/tokenCaseViewModel";
import {
  buildTokenPostEventMarket,
  cleanText,
  normalizeTokenSymbol,
  relativeTimeLabel,
  tokenPricePill,
} from "@shared/model/tokenPostEvent";

type TokenResolution = NonNullable<WatchlistTimelineItem["token_resolutions"]>[number];

export function buildWatchlistTimelineEvent(item: WatchlistTimelineItem): TokenCasePostEvent {
  const resolution = primaryResolution(item.token_resolutions);
  const price = resolution?.price;
  const sourceText = cleanText(item.text_clean);
  const text = sourceText ?? "(empty source event)";
  const tokenSymbols = uniqueStrings([resolutionSymbol(resolution), ...(item.cashtags ?? [])]);

  return {
    id: item.event_id,
    handle: cleanText(item.author_handle),
    text,
    sourceText: null,
    detailsLabel: null,
    url: cleanText(item.canonical_url),
    timestampMs: item.received_at_ms ?? null,
    timeLabel: item.received_at_ms ? relativeTimeLabel(item.received_at_ms) : null,
    phase: "source",
    role: cleanText(item.action),
    isWatched: true,
    pills: watchlistPills({ item, price, resolution, tokenSymbols }),
    market: buildTokenPostEventMarket({
      fallbackProvider: "mention price",
      observationKind: price?.observation_kind,
      priceUsd: price?.price_usd,
      provider: price?.provider,
      status: price?.status,
    }),
    quality: {
      score: null,
      scoreLabel: "source event",
      reasons: [],
      contributions: [],
    },
  };
}

function watchlistPills({
  item,
  price,
  resolution,
  tokenSymbols,
}: {
  item: WatchlistTimelineItem;
  price: TokenResolution["price"] | undefined;
  resolution: TokenResolution | null;
  tokenSymbols: string[];
}): TokenCasePostEvent["pills"] {
  const pricePill = tokenPricePill(price?.price_usd, price?.status);
  return uniquePills([
    { label: "source", tone: "health" },
    ...tokenSymbols.map((symbol) => ({ label: `$${symbol}`, tone: "opportunity" as const })),
    pricePill,
    resolution?.resolution_status
      ? { label: resolution.resolution_status.replaceAll("_", " "), tone: "info" as const }
      : null,
    ...(item.hashtags ?? []).map((value) => ({
      label: `#${value.replace(/^#+/, "")}`,
      tone: "neutral" as const,
    })),
  ]).slice(0, 8);
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
