import { formatTokenPriceUsd } from "@lib/format";

import type { TokenCasePostEvent, TokenCaseTone } from "./tokenCaseViewModel";

export type TokenPostEventMarketInput = {
  priceUsd?: number | null;
  status?: string | null;
  provider?: string | null;
  observationKind?: string | null;
  providerPrefix?: string | null;
  fallbackProvider?: string;
  livePriceUsd?: number | null;
};

export function buildTokenPostEventMarket({
  fallbackProvider = "market tick",
  livePriceUsd,
  observationKind,
  priceUsd,
  provider,
  providerPrefix,
  status,
}: TokenPostEventMarketInput): TokenCasePostEvent["market"] {
  const eventPrice = numberValue(priceUsd);
  const normalizedStatus = cleanText(status);
  if (
    eventPrice === null ||
    (normalizedStatus !== "ready" && normalizedStatus !== "live" && normalizedStatus !== "stale")
  ) {
    return null;
  }
  const deltaPct =
    livePriceUsd !== null && livePriceUsd !== undefined && eventPrice > 0
      ? ((livePriceUsd - eventPrice) / eventPrice) * 100
      : null;
  const providerLabel = [
    cleanText(providerPrefix),
    cleanText(provider) ?? cleanText(observationKind) ?? normalizedStatus ?? fallbackProvider,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" · ");
  return {
    eventPriceLabel: formatTokenPriceUsd(eventPrice),
    liveDeltaLabel: deltaPct === null ? null : `${formatSignedPercent(deltaPct)} vs live`,
    providerLabel,
    tone: normalizedStatus === "stale" ? "warn" : marketDeltaTone(deltaPct),
  };
}

export function tokenPricePill(
  priceUsd: number | null | undefined,
  status?: string | null,
): { label: string; tone: TokenCaseTone } | null {
  const price = numberValue(priceUsd);
  const normalizedStatus = cleanText(status);
  if (
    price === null ||
    (normalizedStatus !== "ready" && normalizedStatus !== "live" && normalizedStatus !== "stale")
  ) {
    return null;
  }
  return {
    label: formatTokenPriceUsd(price),
    tone: normalizedStatus === "stale" ? "warn" : "info",
  };
}

export function relativeTimeLabel(timestampMs: number, now = Date.now()): string {
  const minutes = Math.max(0, Math.round((now - timestampMs) / 60_000));
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  return `${Math.round(minutes / 60)}h ago`;
}

export function normalizeTokenSymbol(value: string | null | undefined): string | null {
  const text = value?.replace(/^\$+/, "").trim();
  return text ? text.toUpperCase() : null;
}

export function cleanText(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

export function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatSignedPercent(value: number): string {
  if (!Number.isFinite(value)) return "-";
  const normalized = Math.abs(value) < 0.005 ? 0 : value;
  const sign = normalized > 0 ? "+" : "";
  return `${sign}${normalized.toFixed(2)}%`;
}

function marketDeltaTone(value: number | null): TokenCaseTone {
  if (value === null || Math.abs(value) < 0.01) return "neutral";
  return value > 0 ? "health" : "risk";
}
