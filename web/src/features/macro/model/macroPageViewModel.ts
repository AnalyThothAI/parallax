import type { MacroModuleView } from "@lib/types";

import { type MacroModuleId, macroRouteLabel } from "./macroRoutes";

export type MacroFreshnessAlertModel = {
  detail: string;
  items: string[];
  title: string;
};

export function macroModuleTitle(moduleId: MacroModuleId, module?: MacroModuleView): string {
  return stringValue(module?.snapshot.title) || macroRouteLabel(moduleId) || "总览";
}

export function macroAsOfLabel(module?: MacroModuleView): string | null {
  return stringValue(module?.snapshot.asof_label) ?? dateAsOfLabel(module?.snapshot.asof_date);
}

export function macroStatusLabel(module?: MacroModuleView): string | null {
  const label = stringValue(module?.snapshot.status_label);
  if (label) {
    return label;
  }
  return knownStatusLabel(stringValue(module?.snapshot.status));
}

export function macroFreshnessAlert(module?: MacroModuleView): MacroFreshnessAlertModel | null {
  const snapshotStatus = stringValue(module?.snapshot.status)?.toLowerCase() ?? null;
  const healthStatus = stringValue(module?.data_health?.summary_status)?.toLowerCase() ?? null;
  const wholePageStale = snapshotStatus === "stale" || healthStatus === "stale";
  const staleGaps = (
    wholePageStale ? dataHealthGaps(module) : blockingDataHealthGaps(module)
  ).filter(isStaleGap);
  if (!wholePageStale && staleGaps.length === 0) {
    return null;
  }
  const asOfLabel = macroAsOfLabel(module);
  const items = uniqueLabels(staleGaps.map(staleGapLabel)).slice(0, 3);
  if (wholePageStale) {
    return {
      detail: `${asOfPrefix(asOfLabel)}宏观快照整体处于滞后状态，请先确认同步与投影状态。`,
      items,
      title: "宏观数据滞后",
    };
  }
  return {
    detail: `${asOfPrefix(asOfLabel)}页面已使用最新可用观测，少数指标仍有新鲜度缺口。`,
    items,
    title: "部分宏观序列滞后",
  };
}

export function formatMacroScalar(value: unknown): string | null {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "string" && value.trim()) {
    const text = value.trim();
    return text === "暂无" ? null : scalarLabel(text);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (value === null || value === undefined) {
    return null;
  }
  if (Array.isArray(value)) {
    const labels = value.map(formatMacroScalar).filter((item): item is string => Boolean(item));
    return labels.length > 0 ? labels.join(", ") : null;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return formatMacroScalar(record.display_value ?? record.label ?? record.title);
  }
  return null;
}

export function gapLabel(gap: unknown): string | null {
  if (gap && typeof gap === "object" && !Array.isArray(gap)) {
    const record = gap as Record<string, unknown>;
    return (
      stringValue(record.display_value) ?? stringValue(record.label) ?? stringValue(record.title)
    );
  }
  return null;
}

export function macroFieldLabel(key: string): string {
  if (isCanonicalConceptKey(key)) {
    return "指标";
  }
  return FIELD_LABELS[key] ?? key;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function dataHealthGaps(module?: MacroModuleView): unknown[] {
  const dataHealth = module?.data_health;
  if (!dataHealth) {
    return [];
  }
  return [
    ...(dataHealth.module_gaps ?? []),
    ...(dataHealth.chart_gaps ?? []),
    ...(dataHealth.global_gaps ?? []),
  ];
}

function blockingDataHealthGaps(module?: MacroModuleView): unknown[] {
  const dataHealth = module?.data_health;
  if (!dataHealth) {
    return [];
  }
  return [...(dataHealth.module_gaps ?? []), ...(dataHealth.chart_gaps ?? [])];
}

function isStaleGap(gap: unknown): boolean {
  if (!gap || typeof gap !== "object" || Array.isArray(gap)) {
    return false;
  }
  const record = gap as Record<string, unknown>;
  const code = stringValue(record.code)?.toLowerCase() ?? "";
  const label = stringValue(record.label) ?? "";
  return code.startsWith("stale_latest") || code.startsWith("stale_") || label.includes("滞后");
}

function staleGapLabel(gap: unknown): string | null {
  return gapLabel(gap);
}

function uniqueLabels(labels: Array<string | null>): string[] {
  return [...new Set(labels.filter((label): label is string => Boolean(label)))];
}

function dateAsOfLabel(value: unknown): string | null {
  const asof = stringValue(value);
  return asof ? `截至 ${asof}` : null;
}

function asOfPrefix(asOfLabel: string | null): string {
  return asOfLabel ? `${asOfLabel}；` : "";
}

function isCanonicalConceptKey(key: string): boolean {
  return /^[a-z]+:[\w.-]+$/i.test(key);
}

const STATUS_LABELS: Record<string, string> = {
  degraded: "降级",
  insufficient_history: "历史样本不足",
  missing: "缺失",
  ok: "正常",
  partial: "部分可用",
  unavailable: "不可用",
};

function knownStatusLabel(value: string | null): string | null {
  if (!value || value === "unknown") {
    return null;
  }
  return STATUS_LABELS[value] ?? null;
}

function scalarLabel(value: string): string | null {
  if (value === "unknown") {
    return null;
  }
  return STATUS_LABELS[value] ?? value;
}

const FIELD_LABELS: Record<string, string> = {
  confidence_label: "置信度",
  current_regime: "当前状态",
  crypto_read: "加密影响",
  expression: "表达方式",
  regime: "宏观状态",
  regime_label: "宏观状态",
  token_impact: "代币影响",
  trade_map: "交易映射",
};
