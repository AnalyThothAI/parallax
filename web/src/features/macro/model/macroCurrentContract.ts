import type {
  MacroAssetCorrelationData,
  MacroAssetCorrelationWindow,
  MacroModuleView,
  MacroSeriesData,
} from "@lib/types";

type JsonRecord = Record<string, unknown>;

const CORRELATION_WINDOWS = new Set<MacroAssetCorrelationWindow>(["20d", "60d", "120d"]);
const EVIDENCE_GROUPS = [
  "confirmations",
  "contradictions",
  "watch_triggers",
  "invalidations",
] as const;

export function requireMacroModuleView(value: unknown): MacroModuleView {
  const module = requireMacroRecord(value, "module");
  requireAllowedKeys(
    module,
    [
      "snapshot",
      "tiles",
      "primary_chart",
      "tables",
      "module_read",
      "module_evidence",
      "transmission",
      "data_health",
      "provenance",
      "related_routes",
      "daily_brief",
    ],
    [
      "snapshot",
      "tiles",
      "primary_chart",
      "tables",
      "module_read",
      "module_evidence",
      "transmission",
      "data_health",
      "provenance",
      "related_routes",
    ],
    "module",
  );
  const snapshot = requireMacroRecord(module.snapshot, "snapshot");
  requireString(snapshot.module_id, "snapshot.module_id");
  requireString(snapshot.route_path, "snapshot.route_path");
  requireString(snapshot.title, "snapshot.title");
  for (const key of [
    "subtitle",
    "question",
    "section",
    "projection_version",
    "status",
    "status_label",
    "asof_date",
    "asof_label",
    "computed_at_label",
    "source_projection_version",
  ]) {
    requireNullableString(snapshot[key], `snapshot.${key}`);
  }
  requireFiniteNumber(snapshot.computed_at_ms, "snapshot.computed_at_ms");

  requireRecordArray(module.tiles, "tiles");
  validatePrimaryChart(module.primary_chart);
  for (const [index, tableValue] of requireRecordArray(module.tables, "tables").entries()) {
    const path = `tables.${index}`;
    requireString(tableValue.id, `${path}.id`);
    requireString(tableValue.title, `${path}.title`);
    requireString(tableValue.status, `${path}.status`);
    requireRecordArray(tableValue.rows, `${path}.rows`);
    if (Object.hasOwn(tableValue, "columns")) {
      requireRecordArray(tableValue.columns, `${path}.columns`);
    }
    if (Object.hasOwn(tableValue, "missing_concept_keys")) {
      requireStringArray(tableValue.missing_concept_keys, `${path}.missing_concept_keys`);
    }
  }
  requireMacroRecord(module.module_read, "module_read");

  const evidence = requireMacroRecord(module.module_evidence, "module_evidence");
  for (const group of EVIDENCE_GROUPS) {
    requireRecordArray(evidence[group], `module_evidence.${group}`);
  }

  requireRecordArray(module.transmission, "transmission");
  validateDataHealth(module.data_health);
  const provenance = requireMacroRecord(module.provenance, "provenance");
  requireRecordArray(provenance.rows, "provenance.rows");
  for (const [index, routeValue] of requireRecordArray(
    module.related_routes,
    "related_routes",
  ).entries()) {
    requireString(routeValue.href, `related_routes.${index}.href`);
    requireString(routeValue.label, `related_routes.${index}.label`);
  }
  if (Object.hasOwn(module, "daily_brief") && module.daily_brief !== null) {
    requireMacroRecord(module.daily_brief, "daily_brief");
  }
  return module as MacroModuleView;
}

export function requireMacroSeriesData(value: unknown): MacroSeriesData {
  const data = requireMacroRecord(value, "series_data");
  requireExactKeys(data, ["window", "series", "data_gaps"], "series_data");
  requireString(data.window, "series_data.window");
  const series = requireMacroRecord(data.series, "series_data.series");
  requireMacroArray(data.data_gaps, "series_data.data_gaps");

  for (const [conceptKey, payloadValue] of Object.entries(series)) {
    const path = `series_data.series.${conceptKey}`;
    const payload = requireMacroRecord(payloadValue, path);
    requireExactKeys(
      payload,
      [
        "concept_key",
        "status",
        "unit",
        "sources",
        "latest_observed_at",
        "data_quality",
        "points",
        "data_gaps",
      ],
      path,
    );
    if (requireString(payload.concept_key, `${path}.concept_key`) !== conceptKey) {
      fail(`${path}.concept_key`);
    }
    requireString(payload.status, `${path}.status`);
    requireNullableString(payload.unit, `${path}.unit`);
    requireStringArray(payload.sources, `${path}.sources`);
    requireNullableString(payload.latest_observed_at, `${path}.latest_observed_at`);
    requireString(payload.data_quality, `${path}.data_quality`);
    validateSeriesPoints(payload.points, `${path}.points`);
    requireMacroArray(payload.data_gaps, `${path}.data_gaps`);
  }
  return data as MacroSeriesData;
}

export function requireMacroAssetCorrelationData(value: unknown): MacroAssetCorrelationData {
  const data = requireMacroRecord(value, "correlation_data");
  requireExactKeys(
    data,
    ["window", "assets", "matrix", "pairs", "data_gaps", "asof_date"],
    "correlation_data",
  );
  const window = requireString(data.window, "correlation_data.window");
  if (!CORRELATION_WINDOWS.has(window as MacroAssetCorrelationWindow)) {
    fail("correlation_data.window");
  }
  requireNullableString(data.asof_date, "correlation_data.asof_date");

  for (const [index, assetValue] of requireRecordArray(
    data.assets,
    "correlation_data.assets",
  ).entries()) {
    const path = `correlation_data.assets.${index}`;
    requireExactKeys(
      assetValue,
      [
        "concept_key",
        "title",
        "observations_count",
        "return_count",
        "start_date",
        "end_date",
        "latest_observed_at",
        "sources",
      ],
      path,
    );
    requireString(assetValue.concept_key, `${path}.concept_key`);
    requireString(assetValue.title, `${path}.title`);
    requireFiniteNumber(assetValue.observations_count, `${path}.observations_count`);
    requireFiniteNumber(assetValue.return_count, `${path}.return_count`);
    requireNullableString(assetValue.start_date, `${path}.start_date`);
    requireNullableString(assetValue.end_date, `${path}.end_date`);
    requireNullableString(assetValue.latest_observed_at, `${path}.latest_observed_at`);
    requireStringArray(assetValue.sources, `${path}.sources`);
  }

  for (const [index, rowValue] of requireRecordArray(
    data.matrix,
    "correlation_data.matrix",
  ).entries()) {
    const path = `correlation_data.matrix.${index}`;
    requireExactKeys(rowValue, ["concept_key", "correlations"], path);
    requireString(rowValue.concept_key, `${path}.concept_key`);
    const correlations = requireMacroRecord(rowValue.correlations, `${path}.correlations`);
    for (const [key, correlation] of Object.entries(correlations)) {
      requireNullableFiniteNumber(correlation, `${path}.correlations.${key}`);
    }
  }

  for (const [index, pairValue] of requireRecordArray(
    data.pairs,
    "correlation_data.pairs",
  ).entries()) {
    const path = `correlation_data.pairs.${index}`;
    requireExactKeys(
      pairValue,
      [
        "left",
        "right",
        "correlation",
        "sample_size",
        "start_date",
        "end_date",
        "available",
        "reason",
      ],
      path,
    );
    requireString(pairValue.left, `${path}.left`);
    requireString(pairValue.right, `${path}.right`);
    requireNullableFiniteNumber(pairValue.correlation, `${path}.correlation`);
    requireFiniteNumber(pairValue.sample_size, `${path}.sample_size`);
    requireNullableString(pairValue.start_date, `${path}.start_date`);
    requireNullableString(pairValue.end_date, `${path}.end_date`);
    requireBoolean(pairValue.available, `${path}.available`);
    requireNullableString(pairValue.reason, `${path}.reason`);
  }

  for (const [index, gapValue] of requireRecordArray(
    data.data_gaps,
    "correlation_data.data_gaps",
  ).entries()) {
    requireString(gapValue.code, `correlation_data.data_gaps.${index}.code`);
  }
  return data as MacroAssetCorrelationData;
}

export function requireMacroArray<T = unknown>(value: unknown, path: string): T[] {
  if (!Array.isArray(value)) {
    fail(path);
  }
  return value as T[];
}

export function requireMacroRecord(value: unknown, path: string): JsonRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(path);
  }
  return value as JsonRecord;
}

export function requireMacroFiniteNumber(value: unknown, path: string): number {
  return requireFiniteNumber(value, path);
}

function validatePrimaryChart(value: unknown): void {
  const chart = requireMacroRecord(value, "primary_chart");
  requireString(chart.id, "primary_chart.id");
  requireString(chart.kind, "primary_chart.kind");
  requireString(chart.title, "primary_chart.title");
  requireString(chart.subtitle, "primary_chart.subtitle");
  requireString(chart.status, "primary_chart.status");
  requireString(chart.status_label, "primary_chart.status_label");
  const minPoints = requireFiniteNumber(chart.min_points, "primary_chart.min_points");
  if (!Number.isInteger(minPoints) || minPoints < 2) {
    fail("primary_chart.min_points");
  }
  requireStringArray(chart.missing_concept_keys, "primary_chart.missing_concept_keys");
  for (const [index, seriesValue] of requireRecordArray(
    chart.series,
    "primary_chart.series",
  ).entries()) {
    const path = `primary_chart.series.${index}`;
    requireString(seriesValue.concept_key, `${path}.concept_key`);
    requireString(seriesValue.label, `${path}.label`);
    requireString(seriesValue.unit_label, `${path}.unit_label`);
    validateEmbeddedPoints(seriesValue.points, `${path}.points`);
  }
}

function validateDataHealth(value: unknown): void {
  const health = requireMacroRecord(value, "data_health");
  requireString(health.summary_status, "data_health.summary_status");
  requireString(health.summary_label, "data_health.summary_label");
  requireRecordArray(health.module_gaps, "data_health.module_gaps");
  requireRecordArray(health.chart_gaps, "data_health.chart_gaps");
  requireRecordArray(health.global_gaps, "data_health.global_gaps");
}

function validateEmbeddedPoints(value: unknown, path: string): void {
  for (const [index, pointValue] of requireRecordArray(value, path).entries()) {
    requireNullableString(pointValue.observed_at, `${path}.${index}.observed_at`);
    requireNullableFiniteNumber(pointValue.value, `${path}.${index}.value`);
  }
}

function validateSeriesPoints(value: unknown, path: string): void {
  for (const [index, pointValue] of requireRecordArray(value, path).entries()) {
    requireNullableString(pointValue.observed_at, `${path}.${index}.observed_at`);
    requireNullableFiniteNumber(pointValue.value, `${path}.${index}.value`);
    requireNullableString(pointValue.source_name, `${path}.${index}.source_name`);
    requireString(pointValue.data_quality, `${path}.${index}.data_quality`);
  }
}

function requireRecordArray(value: unknown, path: string): JsonRecord[] {
  return requireMacroArray(value, path).map((item, index) =>
    requireMacroRecord(item, `${path}.${index}`),
  );
}

function requireStringArray(value: unknown, path: string): string[] {
  return requireMacroArray(value, path).map((item, index) =>
    requireString(item, `${path}.${index}`),
  );
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string") {
    fail(path);
  }
  return value;
}

function requireNullableString(value: unknown, path: string): string | null {
  if (value !== null && typeof value !== "string") {
    fail(path);
  }
  return value;
}

function requireFiniteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(path);
  }
  return value;
}

function requireNullableFiniteNumber(value: unknown, path: string): number | null {
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
    fail(path);
  }
  return value;
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    fail(path);
  }
  return value;
}

function requireExactKeys(value: JsonRecord, keys: readonly string[], path: string): void {
  requireAllowedKeys(value, keys, keys, path);
}

function requireAllowedKeys(
  value: JsonRecord,
  allowedKeys: readonly string[],
  requiredKeys: readonly string[],
  path: string,
): void {
  const actual = Object.keys(value);
  const unknown = actual.find((key) => !allowedKeys.includes(key));
  if (unknown) fail(`${path}.${unknown}`);
  const missing = requiredKeys.find((key) => !Object.hasOwn(value, key));
  if (missing) fail(`${path}.${missing}`);
}

function fail(path: string): never {
  throw new Error(`macro_current_contract:${path}`);
}
