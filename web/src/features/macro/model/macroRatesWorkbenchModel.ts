import type { MacroModuleTable, MacroModuleView, MacroSemanticRecord } from "@lib/types";

import { chartCaption } from "./macroModulePageModel";
import { formatMacroScalar, macroAsOfLabel, macroStatusLabel } from "./macroPageViewModel";

export const RATES_MODULE_IDS = [
  "rates/fed-funds",
  "rates/yield-curve",
  "rates/real-rates",
] as const;

export type RatesModuleId = (typeof RATES_MODULE_IDS)[number];
export type RatesReadiness = "ready" | "partial" | "stale" | "missing";

export type RatesFact = {
  key: string;
  label: string;
  value: string;
  observedAtLabel: string | null;
  sourceLabel: string | null;
  statusLabel: string | null;
  interpretation: string | null;
};

export type RatesGapSummary = {
  key: string;
  label: string;
  severity: "info" | "warning" | "critical";
};

export type RatesDecisionGroup = {
  key: "confirmations" | "contradictions" | "watch_triggers" | "invalidations";
  label: string;
  items: Array<{ label: string; detail: string | null }>;
};

export type RatesDetailTable = {
  role: "primary" | "diagnostic";
  table: MacroModuleTable;
};

export type RatesCurveDiagnosticRow = {
  key: string;
  label: string;
  value: string;
  statusLabel: string | null;
};

export type RatesCurveHistoryPoint = {
  key: string;
  label: string;
  value: number;
};

export type RatesCurveHistorySeries = {
  key: string;
  label: string;
  latest: string;
  range: string;
  points: RatesCurveHistoryPoint[];
};

export type RatesCurveTenorComparisonRow = {
  key: string;
  label: string;
  value: string;
  change: string;
  residual: string | null;
  driverLabel: string | null;
};

export type RatesCurveDiagnostics = {
  headline: string;
  summary: string;
  rows: RatesCurveDiagnosticRow[];
  spreadHistories: RatesCurveHistorySeries[];
  tenorComparison: RatesCurveTenorComparisonRow[];
  implications: string[];
  invalidations: string[];
};

export type RatesPolicyDiagnosticRow = {
  key: string;
  label: string;
  value: string;
  statusLabel: string | null;
};

export type RatesPolicyDiagnostics = {
  headline: string;
  summary: string;
  rows: RatesPolicyDiagnosticRow[];
  implications: string[];
  invalidations: string[];
};

export type RatesRealRateDiagnosticRow = {
  key: string;
  label: string;
  value: string;
  statusLabel: string | null;
};

export type RatesRealRateDiagnostics = {
  headline: string;
  summary: string;
  realYieldRows: RatesRealRateDiagnosticRow[];
  inflationRows: RatesRealRateDiagnosticRow[];
  implications: string[];
  invalidations: string[];
};

export type RatesWorkbenchView = {
  moduleId: RatesModuleId;
  title: string;
  question: string;
  readiness: RatesReadiness;
  readinessLabel: string;
  marketHeadline: string | null;
  asOfLabel: string | null;
  facts: RatesFact[];
  missingPrimaryItems: string[];
  proxyNote: string | null;
  chartTitle: string | null;
  chartNote: string | null;
  curveDiagnostics: RatesCurveDiagnostics | null;
  policyDiagnostics: RatesPolicyDiagnostics | null;
  realRateDiagnostics: RatesRealRateDiagnostics | null;
  decisionGroups: RatesDecisionGroup[];
  detailTables: RatesDetailTable[];
  diagnostics: {
    coverage: RatesGapSummary[];
    sourceMeta: string | null;
    moduleHealthLabel: string | null;
    globalGapReferenceCount: number;
  };
};

const RATES_PAGE_COPY: Record<RatesModuleId, { title: string; question: string }> = {
  "rates/fed-funds": {
    title: "联邦基金与走廊",
    question: "政策走廊是否稳定，隔夜融资是否溢出目标区间？",
  },
  "rates/yield-curve": {
    title: "收益率曲线",
    question: "曲线是在交易衰退压力，还是期限溢价？",
  },
  "rates/real-rates": {
    title: "实际利率",
    question: "实际利率是在压制估值，还是通胀补偿主导？",
  },
};

const DECISION_GROUPS = [
  { key: "confirmations", label: "确认" },
  { key: "contradictions", label: "反证" },
  { key: "watch_triggers", label: "观察触发" },
  { key: "invalidations", label: "失效条件" },
] as const;

const CONCEPT_LABELS: Record<string, string> = {
  "fed:target_lower": "目标下限",
  "fed:target_upper": "目标上限",
  "fed:effr": "EFFR",
  "fed:effr_volume": "EFFR 成交量",
  "fed:iorb": "IORB",
  "fed:obfr": "OBFR",
  "fed:obfr_volume": "OBFR 成交量",
  "fed:sofr_30d": "SOFR 30D",
  "liquidity:sofr": "SOFR",
  "rates:dgs2": "2年期美债收益率",
  "rates:dgs5": "5年期美债收益率",
  "rates:dgs10": "10年期美债收益率",
  "rates:dgs30": "30年期美债收益率",
  "rates:real_5y": "5年期实际利率",
  "rates:real_10y": "10年期实际利率",
  "inflation:breakeven_10y": "10年期通胀补偿",
};

const GAP_LABELS: Record<string, string> = {
  "insufficient_history:60d": "历史样本不足：无法计算 60 日变化",
  sofr_30d_missing: "SOFR 30D 尚未入库",
};

export function isRatesModuleId(moduleId: string): moduleId is RatesModuleId {
  return (RATES_MODULE_IDS as readonly string[]).includes(moduleId);
}

export function buildRatesWorkbenchView(
  module: MacroModuleView,
  moduleId: RatesModuleId,
): RatesWorkbenchView {
  const readiness = readinessFromModule(module);
  const readHeadline = readableText(module.module_read.headline);
  const marketHeadline = sanitizeOptionalText(readHeadline);

  return {
    moduleId,
    title: ratesTitle(module, moduleId),
    question: ratesQuestion(module, moduleId),
    readiness,
    readinessLabel: readinessLabel(readiness),
    marketHeadline,
    asOfLabel: macroAsOfLabel(module),
    facts: module.tiles.map(buildRatesFact).filter((fact): fact is RatesFact => fact !== null),
    missingPrimaryItems: missingPrimaryItems(module),
    proxyNote: null,
    chartTitle: sanitizeOptionalText(chartCaption(module.primary_chart)),
    chartNote: chartNote(module),
    curveDiagnostics: buildCurveDiagnostics(module.module_read.curve_diagnostics),
    policyDiagnostics: buildPolicyDiagnostics(module.module_read.policy_diagnostics),
    realRateDiagnostics: buildRealRateDiagnostics(module.module_read.real_rate_diagnostics),
    decisionGroups: decisionGroups(module.module_evidence),
    detailTables: detailTables(module, moduleId),
    diagnostics: {
      coverage: gapSummaries(module),
      sourceMeta: sourceMeta(module.provenance),
      moduleHealthLabel: sanitizeOptionalText(
        stringValue(module.data_health.summary_label) ?? macroStatusLabel(module),
      ),
      globalGapReferenceCount: module.data_health.global_gaps.length,
    },
  };
}

function buildPolicyDiagnostics(value: unknown): RatesPolicyDiagnostics | null {
  const diagnostics = objectValue(value);
  if (!diagnostics) {
    return null;
  }
  const rows = recordList(diagnostics.rows)
    .map(buildPolicyDiagnosticRow)
    .filter((row): row is RatesPolicyDiagnosticRow => Boolean(row));
  const summary = sanitizeOptionalText(diagnostics.summary);
  const label = sanitizeOptionalText(diagnostics.label);
  if (!label || !summary || rows.length === 0) {
    return null;
  }
  const regimeLabel = sanitizeOptionalText(diagnostics.regime_label);
  return {
    headline: regimeLabel ? `${label} · ${regimeLabel}` : label,
    summary,
    rows,
    implications: stringList(diagnostics.implications).map(sanitizePrimaryText),
    invalidations: stringList(diagnostics.invalidations).map(sanitizePrimaryText),
  };
}

function buildPolicyDiagnosticRow(row: MacroSemanticRecord): RatesPolicyDiagnosticRow | null {
  const value = policyDiagnosticValue(row);
  const key = stringValue(row.key);
  const label = stringValue(row.label);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label: sanitizePrimaryText(label),
    value,
    statusLabel: sanitizeOptionalText(row.status_label),
  };
}

function policyDiagnosticValue(row: MacroSemanticRecord): string | null {
  const lowerPct = numberValue(row.lower_pct);
  const upperPct = numberValue(row.upper_pct);
  const widthBp = numberValue(row.width_bp);
  if (lowerPct !== null && upperPct !== null && widthBp !== null) {
    return `${formatPercent(lowerPct)}-${formatPercent(upperPct)} · 宽度 ${formatBp(widthBp)}`;
  }
  const currentPct = numberValue(row.current_pct);
  if (currentPct !== null) {
    const parts = [formatPercent(currentPct)];
    const distanceToUpperBp = numberValue(row.distance_to_upper_bp);
    if (distanceToUpperBp !== null) {
      parts.push(`距上限 ${formatSignedBp(distanceToUpperBp)}`);
    }
    const change1wBp = numberValue(row.change_1w_bp);
    if (change1wBp !== null) {
      parts.push(`1w ${formatSignedBp(change1wBp)}`);
    }
    return parts.join(" · ");
  }
  const currentBp = numberValue(row.current_bp);
  if (currentBp !== null) {
    const parts = [formatBp(currentBp)];
    const change1wBp = numberValue(row.change_1w_bp);
    if (change1wBp !== null) {
      parts.push(`1w ${formatSignedBp(change1wBp)}`);
    }
    return parts.join(" · ");
  }
  const currentBn = numberValue(row.current_bn);
  if (currentBn !== null) {
    const parts = [formatUsdBillions(currentBn)];
    const change1wBn = numberValue(row.change_1w_bn);
    if (change1wBn !== null) {
      parts.push(`1w ${formatSignedUsdBillions(change1wBn)}`);
    }
    return parts.join(" · ");
  }
  return null;
}

function buildCurveDiagnostics(value: unknown): RatesCurveDiagnostics | null {
  const diagnostics = objectValue(value);
  if (!diagnostics) {
    return null;
  }
  const rows = recordList(diagnostics.rows)
    .map(buildCurveDiagnosticRow)
    .filter((row): row is RatesCurveDiagnosticRow => Boolean(row));
  const summary = sanitizeOptionalText(diagnostics.summary);
  const label = sanitizeOptionalText(diagnostics.label);
  if (!label || !summary || rows.length === 0) {
    return null;
  }
  const shapeLabel = sanitizeOptionalText(diagnostics.shape_label);
  return {
    headline: shapeLabel ? `${label} · ${shapeLabel}` : label,
    summary,
    rows,
    spreadHistories: recordList(diagnostics.spread_history)
      .map(buildCurveHistorySeries)
      .filter((series): series is RatesCurveHistorySeries => Boolean(series)),
    tenorComparison: recordList(diagnostics.tenor_comparison)
      .map(buildCurveTenorComparisonRow)
      .filter((row): row is RatesCurveTenorComparisonRow => Boolean(row)),
    implications: stringList(diagnostics.implications).map(sanitizePrimaryText),
    invalidations: stringList(diagnostics.invalidations).map(sanitizePrimaryText),
  };
}

function buildCurveDiagnosticRow(row: MacroSemanticRecord): RatesCurveDiagnosticRow | null {
  const currentBp = numberValue(row.current_bp);
  const key = stringValue(row.key);
  const label = stringValue(row.label);
  if (!key || !label || currentBp === null) {
    return null;
  }
  const changes: Array<[string, unknown]> = [
    ["1w", row.change_1w_bp],
    ["1m", row.change_1m_bp],
    ["3m", row.change_3m_bp],
  ];
  const parts = [
    formatBp(currentBp),
    ...changes.flatMap(([label, value]) => {
      const changeBp = numberValue(value);
      return changeBp === null ? [] : `${label} ${formatSignedBp(changeBp)}`;
    }),
  ];
  return {
    key,
    label: sanitizePrimaryText(label),
    value: parts.join(" · "),
    statusLabel: sanitizeOptionalText(row.status_label),
  };
}

function buildCurveHistorySeries(series: MacroSemanticRecord): RatesCurveHistorySeries | null {
  const key = stringValue(series.key);
  const label = stringValue(series.label);
  if (!key || !label) {
    return null;
  }
  const points = recordList(series.points)
    .map((point) => {
      const value = numberValue(point.value_bp);
      const observedAt = stringValue(point.observed_at);
      if (value === null || !observedAt) {
        return null;
      }
      return {
        key: `${key}:${observedAt}`,
        label: `${observedAt}：${formatBp(value)}`,
        value,
      };
    })
    .filter((point): point is RatesCurveHistoryPoint => Boolean(point));
  if (points.length === 0) {
    return null;
  }
  const latestValue = numberValue(series.latest_bp) ?? points[points.length - 1]?.value;
  const minValue = numberValue(series.min_bp) ?? Math.min(...points.map((point) => point.value));
  const maxValue = numberValue(series.max_bp) ?? Math.max(...points.map((point) => point.value));
  if (latestValue === undefined) {
    return null;
  }
  return {
    key,
    label: sanitizePrimaryText(label),
    latest: formatBp(latestValue),
    range: `${formatBp(minValue)} 至 ${formatBp(maxValue)}`,
    points,
  };
}

function buildCurveTenorComparisonRow(
  row: MacroSemanticRecord,
): RatesCurveTenorComparisonRow | null {
  const nominalPct = numberValue(row.nominal_pct);
  const realPct = numberValue(row.real_pct);
  const breakevenPct = numberValue(row.breakeven_pct);
  const key = stringValue(row.key);
  const label = stringValue(row.label);
  if (!key || !label || nominalPct === null || realPct === null || breakevenPct === null) {
    return null;
  }
  const nominalChange = numberValue(row.nominal_change_1w_bp);
  const realChange = numberValue(row.real_change_1w_bp);
  const breakevenChange = numberValue(row.breakeven_change_1w_bp);
  return {
    key,
    label: sanitizePrimaryText(label),
    value: [
      `名义 ${formatPercent(nominalPct)}`,
      `实际 ${formatPercent(realPct)}`,
      `通胀补偿 ${formatPercent(breakevenPct)}`,
    ].join(" · "),
    change: [
      "1w：",
      [
        ["名义", nominalChange],
        ["实际", realChange],
        ["通胀补偿", breakevenChange],
      ]
        .flatMap(([label, value]) =>
          typeof value === "number" ? `${label} ${formatSignedBp(value)}` : [],
        )
        .join(" · "),
    ].join(""),
    residual:
      numberValue(row.residual_bp) === null
        ? null
        : `残差 ${formatBp(numberValue(row.residual_bp) ?? 0)}`,
    driverLabel: sanitizeOptionalText(row.driver_label),
  };
}

function buildRealRateDiagnostics(value: unknown): RatesRealRateDiagnostics | null {
  const diagnostics = objectValue(value);
  if (!diagnostics) {
    return null;
  }
  const realYieldRows = recordList(diagnostics.real_yield_rows)
    .map(buildRealRateDiagnosticRow)
    .filter((row): row is RatesRealRateDiagnosticRow => Boolean(row));
  const inflationRows = recordList(diagnostics.inflation_rows)
    .map(buildRealRateDiagnosticRow)
    .filter((row): row is RatesRealRateDiagnosticRow => Boolean(row));
  const summary = sanitizeOptionalText(diagnostics.summary);
  const label = sanitizeOptionalText(diagnostics.label);
  if (!label || !summary || realYieldRows.length === 0) {
    return null;
  }
  const regimeLabel = sanitizeOptionalText(diagnostics.regime_label);
  return {
    headline: regimeLabel ? `${label} · ${regimeLabel}` : label,
    summary,
    realYieldRows,
    inflationRows,
    implications: stringList(diagnostics.implications).map(sanitizePrimaryText),
    invalidations: stringList(diagnostics.invalidations).map(sanitizePrimaryText),
  };
}

function buildRealRateDiagnosticRow(row: MacroSemanticRecord): RatesRealRateDiagnosticRow | null {
  const currentPct = numberValue(row.current_pct);
  const key = stringValue(row.key);
  const label = stringValue(row.label);
  if (!key || !label || currentPct === null) {
    return null;
  }
  const changes: Array<[string, unknown]> = [
    ["1w", row.change_1w_bp],
    ["1m", row.change_1m_bp],
    ["3m", row.change_3m_bp],
  ];
  const parts = [
    formatPercent(currentPct),
    ...changes.flatMap(([label, value]) => {
      const changeBp = numberValue(value);
      return changeBp === null ? [] : `${label} ${formatSignedBp(changeBp)}`;
    }),
  ];
  return {
    key,
    label: sanitizePrimaryText(label),
    value: parts.join(" · "),
    statusLabel: sanitizeOptionalText(row.status_label),
  };
}

export function humanizeRatesConceptKey(conceptKey: string): string | null {
  return CONCEPT_LABELS[conceptKey] ?? null;
}

function buildRatesFact(tile: MacroModuleView["tiles"][number]): RatesFact | null {
  const key = stringValue(tile.concept_key);
  const label = sanitizeOptionalText(tile.label);
  const value = sanitizeOptionalText(formatMacroScalar(tile.display_value ?? tile.value));
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    value,
    observedAtLabel: sanitizeOptionalText(tile.observed_at_label ?? tile.observed_at),
    sourceLabel: sanitizeOptionalText(tile.source_label),
    statusLabel: sanitizeOptionalText(tile.quality_label ?? tile.quality),
    interpretation: sanitizeOptionalText(tile.description ?? tile.delta_label),
  };
}

function ratesTitle(module: MacroModuleView, moduleId: RatesModuleId): string {
  const snapshotTitle = readableText(module.snapshot.title);
  if (!snapshotTitle || isGenericRatesCopy(snapshotTitle)) {
    return RATES_PAGE_COPY[moduleId].title;
  }
  return sanitizePrimaryText(snapshotTitle);
}

function ratesQuestion(module: MacroModuleView, moduleId: RatesModuleId): string {
  const snapshotQuestion = readableText(module.snapshot.question);
  if (!snapshotQuestion || isGenericRatesCopy(snapshotQuestion)) {
    return RATES_PAGE_COPY[moduleId].question;
  }
  return sanitizePrimaryText(snapshotQuestion);
}

function isGenericRatesCopy(value: string): boolean {
  return (
    /^(macro|rates?|宏观|利率|模块|总览)$/i.test(value.trim()) || /资产|asset|crypto/i.test(value)
  );
}

function readinessFromModule(module: MacroModuleView): RatesReadiness {
  const status =
    stringValue(module.data_health.summary_status) ?? stringValue(module.snapshot.status);
  if (status === "ok" || status === "ready") {
    return "ready";
  }
  if (status === "stale") {
    return "stale";
  }
  if (status === "missing" || status === "unavailable") {
    return "missing";
  }
  return "partial";
}

function readinessLabel(readiness: RatesReadiness): string {
  const labels: Record<RatesReadiness, string> = {
    ready: "可用",
    partial: "部分可用",
    stale: "已过期",
    missing: "缺失",
  };
  return labels[readiness];
}

function missingPrimaryItems(module: MacroModuleView): string[] {
  const gapLabels = allGaps(module).flatMap((gap) => {
    const label = explicitGapLabel(gap);
    return label ? [label] : [];
  });
  const missingConceptLabels = [
    ...(module.primary_chart.missing_concept_keys ?? []).flatMap((conceptKey) => {
      const label = humanizeRatesConceptKey(conceptKey);
      return label ? [label] : [];
    }),
    ...module.tables
      .flatMap((table) => table.missing_concept_keys ?? [])
      .flatMap((conceptKey) => {
        const label = humanizeRatesConceptKey(conceptKey);
        return label ? [label] : [];
      }),
  ];
  return uniqueStrings([...gapLabels, ...missingConceptLabels].map(sanitizePrimaryText));
}

function chartNote(module: MacroModuleView): string | null {
  return sanitizeOptionalText(module.primary_chart.subtitle ?? module.primary_chart.status_label);
}

function decisionGroups(evidence: MacroModuleView["module_evidence"]): RatesDecisionGroup[] {
  return DECISION_GROUPS.map((group) => ({
    key: group.key,
    label: group.label,
    items: evidenceItems(evidence[group.key]),
  }));
}

function evidenceItems(
  items: MacroSemanticRecord[] | undefined,
): Array<{ label: string; detail: string | null }> {
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => {
      const label = readableText(item.label);
      if (!label) {
        return null;
      }
      return {
        label: sanitizePrimaryText(label),
        detail: sanitizeOptionalText(item.description),
      };
    })
    .filter((item): item is { label: string; detail: string | null } => Boolean(item));
}

function detailTables(module: MacroModuleView, _moduleId: RatesModuleId): RatesDetailTable[] {
  return module.tables.map((table, index) => ({
    role: index === 0 ? "primary" : "diagnostic",
    table,
  }));
}

function gapSummaries(module: MacroModuleView): RatesGapSummary[] {
  return allGaps(module)
    .map(gapSummary)
    .filter((summary): summary is RatesGapSummary => summary !== null);
}

function gapSummary(gap: MacroSemanticRecord): RatesGapSummary | null {
  const key = stringValue(gap.code);
  const label = explicitGapLabel(gap);
  if (!key || !label) {
    return null;
  }
  return {
    key,
    label: sanitizePrimaryText(label),
    severity: gapSeverity(gap.severity),
  };
}

function explicitGapLabel(gap: MacroSemanticRecord): string | null {
  return readableText(gap.label) ?? readableText(gap.display_value) ?? null;
}

function gapSeverity(value: unknown): RatesGapSummary["severity"] {
  return value === "critical" || value === "warning" ? value : "info";
}

function allGaps(module: MacroModuleView): MacroSemanticRecord[] {
  return [...module.data_health.module_gaps, ...module.data_health.chart_gaps];
}

function sourceMeta(provenance: MacroSemanticRecord): string | null {
  const rows = Array.isArray(provenance.rows) ? (provenance.rows as MacroSemanticRecord[]) : [];
  const labels = rows
    .map((row) =>
      [row.source_label, row.status_label].map(sanitizeOptionalText).filter(Boolean).join("："),
    )
    .filter(Boolean);
  return labels.length > 0 ? labels.join("；") : null;
}

function sanitizeOptionalText(value: unknown): string | null {
  const text = readableText(value);
  if (!text) {
    return null;
  }
  const sanitized = sanitizePrimaryText(text);
  return sanitized || null;
}

function sanitizePrimaryText(value: string): string {
  let text = value;
  for (const [code, label] of Object.entries(GAP_LABELS)) {
    text = text.replaceAll(code, label);
  }
  return text
    .replace(/\b[a-z]+:[\w.-]+\b/gi, (concept) => humanizeRatesConceptKey(concept) ?? "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function readableText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function objectValue(value: unknown): MacroSemanticRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as MacroSemanticRecord)
    : null;
}

function recordList(value: unknown): MacroSemanticRecord[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is MacroSemanticRecord =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map(sanitizeOptionalText).filter((item): item is string => Boolean(item))
    : [];
}

function formatBp(value: number): string {
  return `${formatCompactNumber(value)}bp`;
}

function formatPercent(value: number): string {
  return `${formatDecimal(value, 2)}%`;
}

function formatSignedBp(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCompactNumber(value)}bp`;
}

function formatUsdBillions(value: number): string {
  return `$${formatCompactNumber(value)}B`;
}

function formatSignedUsdBillions(value: number): string {
  if (value < 0) {
    return `-$${formatCompactNumber(Math.abs(value))}B`;
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}$${formatCompactNumber(value)}B`;
}

function formatCompactNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  if (Object.is(rounded, -0)) {
    return "0";
  }
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function formatDecimal(value: number, precision: number): string {
  const rounded = Number(value.toFixed(precision));
  if (Object.is(rounded, -0)) {
    return "0";
  }
  return Number.isInteger(rounded)
    ? String(rounded)
    : rounded.toFixed(precision).replace(/0+$/, "").replace(/\.$/, "");
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}
