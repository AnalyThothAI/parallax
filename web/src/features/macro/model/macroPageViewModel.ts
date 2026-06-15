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

export function macroAsOfLabel(module?: MacroModuleView): string {
  return stringValue(module?.snapshot.asof_label) ?? dateAsOfLabel(module?.snapshot.asof_date);
}

export function macroStatusLabel(module?: MacroModuleView): string {
  const label = stringValue(module?.snapshot.status_label);
  if (label) {
    return label;
  }
  return statusLabel(stringValue(module?.snapshot.status));
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
      detail: `${asOfLabel}；宏观快照整体处于滞后状态，请先确认同步与投影状态。`,
      items,
      title: "宏观数据滞后",
    };
  }
  return {
    detail: `${asOfLabel}；页面已使用最新可用观测，少数指标仍有新鲜度缺口。`,
    items,
    title: "部分宏观序列滞后",
  };
}

export function formatMacroScalar(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "string" && value.trim()) {
    return statusLabel(value);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (value === null || value === undefined) {
    return "暂无";
  }
  if (Array.isArray(value)) {
    return (
      value
        .map(formatMacroScalar)
        .filter((item) => item !== "暂无")
        .join(", ") || "暂无"
    );
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return (
      stringValue(record.display_value) ??
      stringValue(record.label) ??
      stringValue(record.title) ??
      "暂无"
    );
  }
  return "暂无";
}

export function gapLabel(gap: unknown): string {
  if (gap && typeof gap === "object" && !Array.isArray(gap)) {
    const record = gap as Record<string, unknown>;
    return (
      stringValue(record.display_value) ??
      stringValue(record.label) ??
      stringValue(record.title) ??
      "数据缺口待确认"
    );
  }
  return "数据缺口待确认";
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
    ...(dataHealth.future_integration_gaps ?? []),
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

function staleGapLabel(gap: unknown): string {
  const label = gapLabel(gap);
  return label === "数据缺口待确认" ? "最新宏观观测滞后" : label;
}

function uniqueLabels(labels: string[]): string[] {
  return [...new Set(labels.filter((label) => label && label !== "数据缺口待确认"))];
}

function dateAsOfLabel(value: unknown): string {
  const asof = stringValue(value);
  return asof ? `截至 ${asof}` : "暂无日期";
}

function isCanonicalConceptKey(key: string): boolean {
  return /^[a-z]+:[\w.-]+$/i.test(key);
}

function statusLabel(value: string | null): string {
  if (!value) {
    return "未知";
  }
  const labels: Record<string, string> = {
    degraded: "降级",
    insufficient_history: "历史样本不足",
    missing: "缺失",
    ok: "正常",
    partial: "部分可用",
    unavailable: "不可用",
    unknown: "未知",
  };
  return labels[value] ?? value;
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
