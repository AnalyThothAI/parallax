import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";

export function strongestCorrelationPairs(
  data: MacroAssetCorrelationData | null,
  direction: "positive" | "negative",
): MacroAssetCorrelationPair[] {
  const pairs =
    data?.pairs.filter(
      (pair) =>
        pair.available &&
        typeof pair.correlation === "number" &&
        (direction === "positive" ? pair.correlation >= 0 : pair.correlation < 0),
    ) ?? [];

  return pairs
    .sort((left, right) =>
      direction === "positive"
        ? Number(right.correlation) - Number(left.correlation)
        : Number(left.correlation) - Number(right.correlation),
    )
    .slice(0, 8);
}

export function assetTitleByKey(data: MacroAssetCorrelationData | null): Record<string, string> {
  return Object.fromEntries((data?.assets ?? []).map((asset) => [asset.concept_key, asset.title]));
}

export function assetLabel(conceptKey: string, titleByKey: Record<string, string>): string {
  return titleByKey[conceptKey] ?? "资产";
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? (looksInternalSource(source) ? "数据源" : source);
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

export function matrixCorrelationLabel(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(2);
}

export function signedCorrelationLabel(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

export function correlationGapLabel(
  gap: MacroAssetCorrelationData["data_gaps"][number],
  titleByKey: Record<string, string>,
): string {
  if (gap.label) {
    return gap.label;
  }
  const prefix = CORRELATION_GAP_LABELS[gap.code] ?? "相关性样本不足";
  if (gap.left || gap.right) {
    return `${prefix}：${gap.left ? (titleByKey[gap.left] ?? "资产") : "资产"} / ${
      gap.right ? (titleByKey[gap.right] ?? "资产") : "资产"
    }`;
  }
  if (gap.concept_key) {
    return `${prefix}：${titleByKey[gap.concept_key] ?? "资产"}`;
  }
  return prefix;
}

const CORRELATION_GAP_LABELS: Record<string, string> = {
  insufficient_history: "历史样本不足",
  insufficient_overlap: "重叠样本不足",
  missing_observations: "观测缺失",
};

const SOURCE_LABELS: Record<string, string> = {
  fred: "FRED",
  nyfed: "NY Fed",
  yahoo: "Yahoo",
};

function looksInternalSource(value: string): boolean {
  return /^[a-z][a-z0-9_:.-]*$/.test(value);
}
