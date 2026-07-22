import type {
  MacroModuleChart,
  MacroSemanticRecord,
  MacroSeriesData,
  MacroSeriesPayload,
  MacroSeriesPoint,
} from "@lib/types";

import { requireMacroArray, requireMacroFiniteNumber } from "./macroCurrentContract";

export type MacroChartPoint = {
  dataQuality: string | null;
  sourceName: string | null;
  time: string;
  value: number;
};

export type MacroChartSeriesModel = {
  conceptKey: string;
  label: string;
  latest: number | null;
  pointCount: number | null;
  points: MacroChartPoint[];
  status: string | null;
  statusLabel: string | null;
  unit: string | null;
};

export type MacroTimeSeriesModel = {
  chartId: string;
  minPoints: number;
  status: string | null;
  statusLabel: string | null;
  series: MacroChartSeriesModel[];
};

export type MacroYieldCurvePoint = {
  conceptKey: string;
  label: string;
  tenorYears: number;
  unit: string | null;
  value: number;
};

export type MacroYieldCurveModel = {
  chartId: string;
  points: MacroYieldCurvePoint[];
};

const CANONICAL_CONCEPT_PREFIXES = new Set([
  "asset",
  "commodity",
  "consumer",
  "credit",
  "crypto",
  "economy",
  "fed",
  "fx",
  "inflation",
  "labor",
  "liquidity",
  "rates",
  "vol",
]);

const TENOR_YEARS_BY_CONCEPT: Record<string, number> = {
  "rates:dgs1mo": 1 / 12,
  "rates:dgs3mo": 0.25,
  "rates:dgs6mo": 0.5,
  "rates:dgs1": 1,
  "rates:dgs2": 2,
  "rates:dgs3": 3,
  "rates:dgs5": 5,
  "rates:dgs7": 7,
  "rates:dgs10": 10,
  "rates:dgs20": 20,
  "rates:dgs30": 30,
};

export const MACRO_MIN_CHART_POINTS = 2;

export function buildMacroTimeSeriesModel(
  chart: MacroModuleChart,
  seriesData?: MacroSeriesData | null,
): MacroTimeSeriesModel {
  const id = chartId(chart);
  if (!id) {
    return {
      chartId: "",
      minPoints: chartMinPoints(chart),
      status: statusValue(chart.status),
      statusLabel: stringValue(chart.status_label),
      series: [],
    };
  }
  const chartSeries = requireMacroArray<MacroSemanticRecord>(chart.series, "primary_chart.series");
  return {
    chartId: id,
    minPoints: chartMinPoints(chart),
    status: statusValue(chart.status),
    statusLabel: stringValue(chart.status_label),
    series: chartSeries
      .map((series) =>
        buildSeriesModel(series, chartMinPoints(chart), seriesData?.series[conceptKey(series)]),
      )
      .filter((series): series is MacroChartSeriesModel => Boolean(series)),
  };
}

export function buildMacroNormalizedReturnModel(
  chart: MacroModuleChart,
  seriesData?: MacroSeriesData | null,
): MacroTimeSeriesModel {
  const model = buildMacroTimeSeriesModel(chart, seriesData);
  return {
    chartId: model.chartId,
    minPoints: model.minPoints,
    status: model.status,
    statusLabel: model.statusLabel,
    series: model.series.map((series) => ({
      ...series,
      points: normalizeReturnPoints(series.points),
      unit: "return_percent",
    })),
  };
}

export function buildMacroYieldCurveModel(chart: MacroModuleChart): MacroYieldCurveModel {
  const id = chartId(chart);
  if (!id) {
    return { chartId: "", points: [] };
  }
  const chartSeries = requireMacroArray<MacroSemanticRecord>(chart.series, "primary_chart.series");
  const points = chartSeries
    .map((series) => {
      const key = conceptKey(series);
      const tenorYears = TENOR_YEARS_BY_CONCEPT[key];
      const label = displayLabel(series);
      const value = latestSeriesNumericValue(series);
      if (!tenorYears || !label || value === null) {
        return null;
      }
      return {
        conceptKey: key,
        label,
        tenorYears,
        unit: stringValue(series.unit),
        value,
      };
    })
    .filter((point): point is MacroYieldCurvePoint => Boolean(point))
    .sort((left, right) => left.tenorYears - right.tenorYears);
  return { chartId: id, points };
}

export function formatMacroChartValue(value: number, unit?: string | null): string {
  const formatted =
    Math.abs(value) > 0 && Math.abs(value) < 1 ? trimNumber(value, 6) : trimNumber(value, 2);
  return unit === "return_percent" || unit === "percent" ? `${formatted}%` : formatted;
}

function buildSeriesModel(
  series: MacroSemanticRecord,
  minPoints: number,
  payload?: MacroSeriesPayload,
): MacroChartSeriesModel | null {
  const key = conceptKey(series);
  if (!isCanonicalMacroConceptKey(key)) {
    return null;
  }
  const label = displayLabel(series);
  if (!label) {
    return null;
  }
  const normalizedPoints = normalizeSeriesPoints(
    payload
      ? requireMacroArray<MacroSeriesPoint>(payload.points, `series_data.series.${key}.points`)
      : [],
  );
  const pointCount = integerValue(series.point_count);
  const status = seriesStatus(series);
  return {
    conceptKey: key,
    label,
    latest: numericValue(series.latest),
    pointCount,
    points: normalizedPoints.length >= minPoints ? normalizedPoints : [],
    status,
    statusLabel: stringValue(series.status_label),
    unit: stringValue(series.unit),
  };
}

function normalizeSeriesPoints(points: MacroSeriesPoint[]): MacroChartPoint[] {
  return points
    .map((point) => {
      const time = stringValue(point.observed_at);
      const value = numericValue(point.value);
      if (!time || value === null) {
        return null;
      }
      return {
        time,
        value,
        sourceName: stringValue(point.source_name),
        dataQuality: stringValue(point.data_quality),
      };
    })
    .filter((point): point is MacroChartPoint => Boolean(point))
    .sort((left, right) => left.time.localeCompare(right.time));
}

function latestSeriesNumericValue(series: MacroSemanticRecord): number | null {
  return numericValue(series.latest);
}

function normalizeReturnPoints(points: MacroChartPoint[]): MacroChartPoint[] {
  const base = points.find((point) => point.value !== 0)?.value;
  if (!base) {
    return [];
  }
  return points.map((point) => ({
    ...point,
    value: roundForDisplay(((point.value - base) / base) * 100),
  }));
}

function conceptKey(series: MacroSemanticRecord): string {
  return stringValue(series.concept_key) ?? "";
}

function chartId(chart: MacroModuleChart): string | null {
  return stringValue(chart.id);
}

function chartMinPoints(chart: MacroModuleChart): number {
  const minPoints = requireMacroFiniteNumber(chart.min_points, "primary_chart.min_points");
  if (!Number.isInteger(minPoints) || minPoints < MACRO_MIN_CHART_POINTS) {
    throw new Error("macro_current_contract:primary_chart.min_points");
  }
  return minPoints;
}

function displayLabel(record: MacroSemanticRecord): string | null {
  return stringValue(record.label) ?? stringValue(record.short_label);
}

function statusValue(value: unknown): string | null {
  return stringValue(value);
}

function seriesStatus(series: MacroSemanticRecord): string | null {
  return stringValue(series.status);
}

function isCanonicalMacroConceptKey(key: string): boolean {
  const [prefix, suffix] = key.split(":");
  return Boolean(prefix && suffix && CANONICAL_CONCEPT_PREFIXES.has(prefix));
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function integerValue(value: unknown): number | null {
  const numeric = numericValue(value);
  return numeric === null ? null : Math.trunc(numeric);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function roundForDisplay(value: number): number {
  return Number(value.toFixed(4));
}

function trimNumber(value: number, maximumFractionDigits: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
    useGrouping: false,
  }).format(value);
}
