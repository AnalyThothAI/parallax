import type { MacroModuleChart, MacroModuleTable } from "@lib/types";

export function chartConceptKeys(chart: MacroModuleChart): string[] {
  return (chart.series ?? [])
    .map((series) => (typeof series.concept_key === "string" ? series.concept_key : ""))
    .filter(Boolean);
}

export function tableCaption(table: MacroModuleTable): string | null {
  const id = tableIdentifier(table);
  if (!id) {
    return null;
  }
  return stringValue(table.title);
}

export function chartCaption(chart: MacroModuleChart): string | null {
  const id = chartIdentifier(chart);
  if (!id) {
    return null;
  }
  return stringValue(chart.title);
}

export function chartIdentifier(chart: MacroModuleChart): string | null {
  return stringValue(chart.id);
}

export function tableIdentifier(table: MacroModuleTable): string | null {
  return stringValue(table.id);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
