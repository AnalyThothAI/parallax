import type { MacroModuleView } from "@lib/types";

import { type MacroModuleId, macroRouteLabel } from "./macroRoutes";

export function macroModuleTitle(moduleId: MacroModuleId, module?: MacroModuleView): string {
  return stringValue(module?.snapshot.title) ?? macroRouteLabel(moduleId);
}

export function macroAsOfLabel(module?: MacroModuleView): string {
  const asof = stringValue(module?.snapshot.asof_date);
  return asof ? `As of ${asof}` : "As of unavailable";
}

export function macroStatusLabel(module?: MacroModuleView): string {
  return stringValue(module?.snapshot.status) ?? "unknown";
}

export function formatMacroScalar(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (value === null || value === undefined) {
    return "n/a";
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

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
