import type { MacroModuleChart, MacroModuleTable, MacroSeriesData } from "@lib/types";

import {
  buildMacroNormalizedReturnModel,
  buildMacroTimeSeriesModel,
  buildMacroYieldCurveModel,
} from "../../model/macroChartModel";
import {
  chartCaption,
  chartIdentifier,
  tableCaption,
  tableIdentifier,
} from "../../model/macroModulePageModel";
import { formatMacroScalar } from "../../model/macroPageViewModel";
import type { MacroModuleId } from "../../model/macroRoutes";
import { MacroNormalizedReturnChart } from "../charts/MacroNormalizedReturnChart";
import { MacroTimeSeriesChart } from "../charts/MacroTimeSeriesChart";
import { MacroYieldCurveChart } from "../charts/MacroYieldCurveChart";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroDataTable } from "../tables/MacroDataTable";

import "./macroPages.css";

export function MacroMarketBoard({
  ariaLabel,
  chart,
  moduleId,
  seriesData,
  seriesLoading,
  supportingTable,
  supportingTables = [],
  title,
}: {
  ariaLabel?: string;
  chart: MacroModuleChart;
  moduleId: MacroModuleId;
  seriesData?: MacroSeriesData | null;
  seriesLoading?: boolean;
  supportingTable: MacroModuleTable | null;
  supportingTables?: MacroModuleTable[];
  title?: string;
}) {
  const tables = [supportingTable, ...supportingTables].filter(renderableTable);
  const hasChartEvidence = hasRenderablePrimaryChart({
    chart,
    moduleId,
    seriesData,
    seriesLoading,
  });

  if (!title || (!hasChartEvidence && tables.length === 0)) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel={ariaLabel ?? title}
      meta={chartStatusLabel(chart)}
      span="full"
      title={title}
    >
      {hasChartEvidence ? (
        <MacroPrimaryChart
          chart={chart}
          moduleId={moduleId}
          seriesData={seriesData}
          seriesLoading={seriesLoading}
        />
      ) : null}
      {tables.map((table) => (
        <TableBlock key={String(table.id)} table={table} />
      ))}
    </MacroPanel>
  );
}

function renderableTable(table: MacroModuleTable | null | undefined): table is MacroModuleTable {
  return Boolean(
    table && tableIdentifier(table) && tableCaption(table) && (table.rows?.length ?? 0) > 0,
  );
}

function TableBlock({ table }: { table: MacroModuleTable }) {
  const caption = tableCaption(table);
  if (!caption) {
    return null;
  }
  return (
    <>
      <MacroDataTable caption={caption} table={table} />
      <TableSourceNote source={table.source} />
    </>
  );
}

function TableSourceNote({ source }: { source: MacroModuleTable["source"] }) {
  const note = source?.notes ?? null;
  if (!note) {
    return null;
  }
  const label = formatMacroScalar(note);
  return label ? <p className="macro-table-source-note">{label}</p> : null;
}

export function MacroPrimaryChart({
  chart,
  moduleId,
  seriesData,
  seriesLoading,
}: {
  chart: MacroModuleChart;
  moduleId: MacroModuleId;
  seriesData?: MacroSeriesData | null;
  seriesLoading?: boolean;
}) {
  const title = chartCaption(chart);
  const chartId = chartIdentifier(chart);
  if (!title || !chartId) {
    return null;
  }
  if (isYieldCurveChart(chart) || moduleId === "rates/yield-curve") {
    return <MacroYieldCurveChart chart={chart} title={title} />;
  }
  if (seriesLoading) {
    return (
      <div aria-label={`${title}加载状态`} className="macro-chart-loading-state" role="status">
        图表序列加载中
      </div>
    );
  }
  if (moduleId.startsWith("assets") || chartId.includes("performance")) {
    return <MacroNormalizedReturnChart chart={chart} seriesData={seriesData} title={title} />;
  }
  return <MacroTimeSeriesChart chart={chart} seriesData={seriesData} title={title} />;
}

function isYieldCurveChart(chart: MacroModuleChart): boolean {
  return Boolean(chartIdentifier(chart)?.includes("curve"));
}

function hasRenderablePrimaryChart({
  chart,
  moduleId,
  seriesData,
  seriesLoading,
}: {
  chart: MacroModuleChart;
  moduleId: MacroModuleId;
  seriesData?: MacroSeriesData | null;
  seriesLoading?: boolean;
}): boolean {
  if (isYieldCurveChart(chart) || moduleId === "rates/yield-curve") {
    if (!chartIdentifier(chart)) {
      return false;
    }
    return buildMacroYieldCurveModel(chart).points.length > 0;
  }
  if (seriesLoading) {
    return buildMacroTimeSeriesModel(chart).series.length > 0;
  }
  const chartId = chartIdentifier(chart);
  if (!chartId) {
    return false;
  }
  const model =
    moduleId.startsWith("assets") || chartId.includes("performance")
      ? buildMacroNormalizedReturnModel(chart, seriesData)
      : buildMacroTimeSeriesModel(chart, seriesData);
  return model.series.some((series) => series.points.length >= model.minPoints);
}

function chartStatusLabel(chart: MacroModuleChart): string | null {
  return typeof chart.status_label === "string" && chart.status_label.trim()
    ? chart.status_label
    : null;
}
