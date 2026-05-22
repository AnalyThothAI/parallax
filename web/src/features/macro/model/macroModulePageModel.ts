import type { MacroModuleChart, MacroModuleTable } from "@lib/types";

export function chartConceptKeys(chart: MacroModuleChart): string[] {
  return (chart.series ?? [])
    .map((series) => (typeof series.concept_key === "string" ? series.concept_key : ""))
    .filter(Boolean);
}

export function tableCaption(table: MacroModuleTable): string {
  return table.table_id
    .split("_")
    .filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

export function emptyChart(chartId: string): MacroModuleChart {
  return { chart_id: chartId, series: [], status: "missing" };
}

export function emptyTable(tableId: string): MacroModuleTable {
  return { table_id: tableId, rows: [], status: "missing" };
}
