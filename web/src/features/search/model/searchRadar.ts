import { formatScore, formatTokenPriceUsd, formatUsdCompact } from "@lib/format";
import type { SearchTokenResult } from "@lib/types";

export type SearchMetricTone = "positive" | "warning" | "negative";

export type SearchRadarSummary = {
  dataHealthEntries: Array<{ label: string; value: string }>;
  dataHealthLine: string;
  decision: string;
  familyScores: Array<{ label: string; value: string }>;
  gateLine: string;
  marketHealth: string;
  marketVenue: string;
  primaryMarketDetail: string;
  primaryMarketLabel: string;
  primaryMarketTone: SearchMetricTone;
  primaryMarketValue: string;
  radarStatusLabel: string;
  rankScore: number | null;
  scoreSummary: Array<{ label: string; value: string }>;
};

export function buildSearchRadarSummary(result: SearchTokenResult): SearchRadarSummary {
  const radar = asRecord(result.radar_item);
  const radarTarget = asRecord(radar.target);
  const score = asRecord(radar.score);
  const snapshot = asRecord(radar.factor_snapshot);
  const composite = asRecord(snapshot.composite);
  const gates = asRecord(snapshot.gates);
  const dataHealth = nonEmptyRecord(radar.data_health) ?? asRecord(snapshot.data_health);
  const familyScores = nonEmptyRecord(score.family_scores) ?? asRecord(composite.family_scores);
  const market = asRecord(radar.market);
  const eventAnchor = asRecord(market.event_anchor);
  const decisionLatest = asRecord(market.decision_latest);
  const readiness = asRecord(market.readiness);
  const marketOverlay = asRecord(result.market_overlay);
  const firstBucketPrice = result.timeline.buckets.find((bucket) => bucket.price?.price_usd)?.price;
  const candleClose = latestCandleClose(marketOverlay.candles);
  const isDexMarket =
    result.target.target_type === "Asset" || stringValue(radarTarget.target_type) === "Asset";
  const latestMarketCap = numberValue(decisionLatest.market_cap_usd);
  const anchoredMarketCap = numberValue(eventAnchor.market_cap_usd);
  const marketCap = latestMarketCap ?? anchoredMarketCap;
  const marketCapStatus =
    latestMarketCap !== null
      ? stringValue(readiness.latest_status)
      : anchoredMarketCap !== null
        ? "anchored"
        : "missing";
  const price =
    candleClose ??
    numberValue(decisionLatest.price_usd) ??
    numberValue(eventAnchor.price_usd) ??
    numberValue(firstBucketPrice?.price_usd);
  const priceStatus =
    stringValue(marketOverlay.candle_status) === "ready"
      ? "ohlc ready"
      : stringValue(readiness.latest_status) !== "-"
        ? stringValue(readiness.latest_status)
        : stringValue(readiness.anchor_status);
  const provider = stringValue(
    decisionLatest.provider ?? eventAnchor.provider ?? marketOverlay.provider,
  );
  const primaryMarketLabel = isDexMarket ? "market cap" : "price";
  const primaryMarketValue = isDexMarket
    ? marketCap === null
      ? "-"
      : formatUsdCompact(marketCap)
    : price === null
      ? "-"
      : formatTokenPriceUsd(price);
  const primaryMarketDetail = isDexMarket
    ? marketCap === null
      ? `${priceStatus} · cap missing`
      : `${marketCapStatus} · ${provider}`
    : priceStatus !== "-"
      ? `${priceStatus} · ${provider}`
      : "message anchor only";
  const marketHealth =
    stringValue(marketOverlay.candle_status) === "ready"
      ? "ready"
      : stringValue(dataHealth.market) !== "-"
        ? stringValue(dataHealth.market)
        : priceStatus;
  const decision = stringValue(score.recommended_decision ?? composite.recommended_decision);
  const rankScore = numberValue(score.rank_score ?? composite.rank_score);
  const gate = stringValue(gates.max_decision);
  const dataHealthEntries = Object.entries(dataHealth).map(([label, value]) => ({
    label,
    value: stringValue(value),
  }));

  return {
    dataHealthEntries,
    dataHealthLine:
      dataHealthEntries
        .slice(0, 3)
        .map((entry) => `${entry.label}:${entry.value}`)
        .join(" · ") || "not ranked",
    decision,
    familyScores: Object.entries(familyScores)
      .slice(0, 6)
      .map(([label, value]) => ({
        label: label.replaceAll("_", " "),
        value: formatScore(numberValue(value)),
      })),
    gateLine: gate !== "-" ? `gate ${gate}` : "gate unavailable",
    marketHealth,
    marketVenue: stringValue(
      marketOverlay.native_market_id ??
        marketOverlay.chain_id ??
        marketOverlay.provider ??
        marketOverlay.pricefeed_id,
    ),
    primaryMarketDetail,
    primaryMarketLabel,
    primaryMarketTone: isDexMarket
      ? marketCap === null
        ? "warning"
        : "positive"
      : price
        ? "positive"
        : "warning",
    primaryMarketValue,
    radarStatusLabel: result.radar_item ? "radar row" : "not in current radar",
    rankScore,
    scoreSummary: [
      { label: "rank", value: formatScore(rankScore) },
      { label: "decision", value: decision },
      { label: "gate", value: gate },
    ],
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function nonEmptyRecord(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value);
  return Object.keys(record).length ? record : null;
}

function latestCandleClose(value: unknown): number | null {
  if (!Array.isArray(value)) {
    return null;
  }
  for (let index = value.length - 1; index >= 0; index -= 1) {
    const close = numberValue(asRecord(value[index]).close);
    if (close !== null) {
      return close;
    }
  }
  return null;
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
