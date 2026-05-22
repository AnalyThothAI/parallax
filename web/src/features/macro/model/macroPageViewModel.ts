import type { MacroModuleView } from "@lib/types";

import { type MacroModuleId, macroRouteLabel } from "./macroRoutes";

export function macroModuleTitle(moduleId: MacroModuleId, module?: MacroModuleView): string {
  const routeLabel = macroRouteLabel(moduleId);
  return routeLabel || stringValue(module?.snapshot.title) || "总览";
}

export function macroAsOfLabel(module?: MacroModuleView): string {
  const asof = stringValue(module?.snapshot.asof_date);
  return asof ? `截至 ${asof}` : "暂无日期";
}

export function macroStatusLabel(module?: MacroModuleView): string {
  return statusLabel(stringValue(module?.snapshot.status));
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
  return JSON.stringify(value);
}

export function gapLabel(gap: unknown): string {
  if (typeof gap === "string") {
    return gap;
  }
  if (gap && typeof gap === "object" && "code" in gap) {
    return formatMacroScalar((gap as { code?: unknown }).code);
  }
  return formatMacroScalar(gap);
}

export function macroFieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function statusLabel(value: string | null): string {
  if (!value) {
    return "未知";
  }
  const labels: Record<string, string> = {
    degraded: "降级",
    missing: "缺失",
    ok: "正常",
    partial: "部分可用",
    unavailable: "不可用",
    unknown: "未知",
  };
  return labels[value] ?? value;
}

const FIELD_LABELS: Record<string, string> = {
  current_regime: "当前状态",
  expression: "表达方式",
  regime: "宏观状态",
  trade_map: "交易映射",
};
