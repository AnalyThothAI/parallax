import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";

export function strongestCorrelationPairs(
  data: MacroAssetCorrelationData | null,
  direction: "positive" | "negative",
): MacroAssetCorrelationPair[] {
  if (!data) {
    return [];
  }
  const pairs = data.pairs.filter(
    (pair) =>
      pair.available &&
      typeof pair.correlation === "number" &&
      (direction === "positive" ? pair.correlation >= 0 : pair.correlation < 0),
  );

  return pairs
    .sort((left, right) =>
      direction === "positive"
        ? Number(right.correlation) - Number(left.correlation)
        : Number(left.correlation) - Number(right.correlation),
    )
    .slice(0, 8);
}

export function assetTitleByKey(data: MacroAssetCorrelationData | null): Record<string, string> {
  return data
    ? Object.fromEntries(data.assets.map((asset) => [asset.concept_key, asset.title]))
    : {};
}

export function assetLabel(conceptKey: string, titleByKey: Record<string, string>): string | null {
  return titleByKey[conceptKey] ?? null;
}

export function correlationTone(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "gap";
  }
  if (value >= 0.55) {
    return "constructive";
  }
  if (value <= -0.35) {
    return "stress";
  }
  return "neutral";
}

export function matrixCorrelationLabel(value: number | null | undefined): string | null {
  if (typeof value !== "number") {
    return null;
  }
  return value.toFixed(2);
}

export function signedCorrelationLabel(value: number | null | undefined): string | null {
  if (typeof value !== "number") {
    return null;
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}
