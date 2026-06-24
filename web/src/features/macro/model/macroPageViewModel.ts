import type { MacroModuleView } from "@lib/types";

export type MacroFreshnessAlertModel = {
  detail: string;
  items: string[];
  title: string;
};

export function macroModuleTitle(module?: MacroModuleView): string | null {
  return stringValue(module?.snapshot.title);
}

export function macroAsOfLabel(module?: MacroModuleView): string | null {
  return stringValue(module?.snapshot.asof_label);
}

export function macroStatusLabel(module?: MacroModuleView): string | null {
  return stringValue(module?.snapshot.status_label);
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
    return value.trim();
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
    return formatMacroScalar(record.display_value);
  }
  return null;
}

export function gapLabel(gap: unknown): string | null {
  if (gap && typeof gap === "object" && !Array.isArray(gap)) {
    const record = gap as Record<string, unknown>;
    return stringValue(record.label);
  }
  return null;
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
  return code.startsWith("stale_latest") || code.startsWith("stale_");
}

function staleGapLabel(gap: unknown): string | null {
  return gapLabel(gap);
}

function uniqueLabels(labels: Array<string | null>): string[] {
  return [...new Set(labels.filter((label): label is string => Boolean(label)))];
}

function asOfPrefix(asOfLabel: string | null): string {
  return asOfLabel ? `${asOfLabel}；` : "";
}
