import type {
  MacroModuleChart,
  MacroSemanticRecord,
  MacroSeriesData,
  MacroSeriesPayload,
  MacroSeriesPoint,
} from "@lib/types";

export type RatesCorridorSeriesKey =
  | "target_lower"
  | "target_upper"
  | "effr"
  | "iorb"
  | "sofr"
  | "sofr_30d";
export type RatesCorridorPoint = { time: string; value: number };
export type RatesCorridorSeries = {
  key: RatesCorridorSeriesKey;
  label: string;
  unit: string | null;
  latest: number | null;
  points: RatesCorridorPoint[];
};
export type RatesCorridorModel = {
  lower: RatesCorridorSeries | null;
  upper: RatesCorridorSeries | null;
  lines: RatesCorridorSeries[];
  missingLabels: string[];
};

const CORRIDOR_SERIES_BY_CONCEPT: Record<string, RatesCorridorSeriesKey> = {
  "fed:target_lower": "target_lower",
  "fed:target_upper": "target_upper",
  "fed:effr": "effr",
  "fed:iorb": "iorb",
  "liquidity:sofr": "sofr",
  "fed:sofr_30d": "sofr_30d",
};

const CORRIDOR_LABELS: Record<RatesCorridorSeriesKey, string> = {
  target_lower: "目标下限",
  target_upper: "目标上限",
  effr: "EFFR",
  iorb: "IORB",
  sofr: "SOFR",
  sofr_30d: "SOFR 30D",
};

const CORRIDOR_LINE_ORDER: RatesCorridorSeriesKey[] = ["effr", "iorb", "sofr", "sofr_30d"];
const REQUIRED_CORRIDOR_KEYS: RatesCorridorSeriesKey[] = [
  "target_lower",
  "target_upper",
  ...CORRIDOR_LINE_ORDER,
];

export function buildRatesCorridorModel(
  chart: MacroModuleChart,
  seriesData?: MacroSeriesData | null,
): RatesCorridorModel {
  const seriesByKey = new Map<RatesCorridorSeriesKey, RatesCorridorSeries>();
  for (const series of chartSeries(chart)) {
    const concept = stringValue(series.concept_key);
    const key = concept ? CORRIDOR_SERIES_BY_CONCEPT[concept] : undefined;
    if (!concept || !key || seriesByKey.has(key)) {
      continue;
    }
    seriesByKey.set(key, buildCorridorSeries(key, series, seriesData?.series[concept]));
  }

  const missingLabels = uniqueLabels([
    ...REQUIRED_CORRIDOR_KEYS.filter((key) => !isRenderable(seriesByKey.get(key))).map(
      (key) => CORRIDOR_LABELS[key],
    ),
    ...(chart.missing_concept_keys ?? []).map(
      (concept) => CORRIDOR_LABELS[CORRIDOR_SERIES_BY_CONCEPT[concept]] ?? concept,
    ),
  ]);

  return {
    lower: renderableSeries(seriesByKey.get("target_lower")),
    upper: renderableSeries(seriesByKey.get("target_upper")),
    lines: CORRIDOR_LINE_ORDER.map((key) => renderableSeries(seriesByKey.get(key))).filter(
      (series): series is RatesCorridorSeries => Boolean(series),
    ),
    missingLabels,
  };
}

function buildCorridorSeries(
  key: RatesCorridorSeriesKey,
  series: MacroSemanticRecord,
  payload?: MacroSeriesPayload,
): RatesCorridorSeries {
  const payloadPoints = normalizeSeriesPoints(payload?.points ?? []);
  const inlinePoints =
    payloadPoints.length > 0 ? [] : normalizeSeriesPoints(inlineSeriesPoints(series));
  const latest = latestSeriesValue(series, payload, payloadPoints, inlinePoints);
  const points =
    payloadPoints.length > 0
      ? payloadPoints
      : inlinePoints.length > 0
        ? inlinePoints
        : latest === null
          ? []
          : [{ time: snapshotTime(series, payload), value: latest }];
  return {
    key,
    label: CORRIDOR_LABELS[key],
    unit: stringValue(series.unit) ?? stringValue(payload?.unit),
    latest: points.at(-1)?.value ?? latest,
    points,
  };
}

function latestSeriesValue(
  series: MacroSemanticRecord,
  payload: MacroSeriesPayload | undefined,
  payloadPoints: RatesCorridorPoint[],
  inlinePoints: RatesCorridorPoint[],
): number | null {
  return (
    payloadPoints.at(-1)?.value ??
    inlinePoints.at(-1)?.value ??
    numericValue(series.latest) ??
    numericValue(series.latest_value) ??
    numericValue(series.value) ??
    numericValue(payload?.latest_value)
  );
}

function normalizeSeriesPoints(points: MacroSeriesPoint[]): RatesCorridorPoint[] {
  return points
    .map((point) => {
      const time = stringValue(point.observed_at);
      const value = numericValue(point.value);
      return time && value !== null ? { time, value } : null;
    })
    .filter((point): point is RatesCorridorPoint => Boolean(point))
    .sort((left, right) => left.time.localeCompare(right.time));
}

function inlineSeriesPoints(series: MacroSemanticRecord): MacroSeriesPoint[] {
  return Array.isArray(series.points) ? (series.points as MacroSeriesPoint[]) : [];
}

function chartSeries(chart: MacroModuleChart): MacroSemanticRecord[] {
  return Array.isArray(chart.series) ? chart.series : [];
}

function renderableSeries(series: RatesCorridorSeries | undefined): RatesCorridorSeries | null {
  return isRenderable(series) ? series : null;
}

function isRenderable(series: RatesCorridorSeries | undefined): series is RatesCorridorSeries {
  return Boolean(series && series.points.length > 0);
}

function snapshotTime(series: MacroSemanticRecord, payload?: MacroSeriesPayload): string {
  return (
    stringValue(series.observed_at) ??
    stringValue(payload?.latest_observed_at) ??
    stringValue(series.latest_observed_at) ??
    "snapshot"
  );
}

function uniqueLabels(labels: string[]): string[] {
  return [...new Set(labels.filter((label) => label.trim()))];
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.replace(/%$/, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
