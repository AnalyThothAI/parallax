import type { MacroModuleChart, MacroModuleTable, MacroSeriesData } from "@lib/types";

import { chartCaption, chartIdentifier, tableCaption } from "../../model/macroModulePageModel";
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
  title = "市场板",
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
  const tables = [supportingTable, ...supportingTables].filter((table): table is MacroModuleTable =>
    Boolean(table && (table.rows?.length ?? 0) > 0),
  );

  return (
    <MacroPanel
      ariaLabel={ariaLabel ?? title}
      meta={chartStatusLabel(chart)}
      span="full"
      title={title}
    >
      <MacroPrimaryChart
        chart={chart}
        moduleId={moduleId}
        seriesData={seriesData}
        seriesLoading={seriesLoading}
      />
      {tables.map((table) => (
        <TableBlock key={String(table.id ?? tableCaption(table))} table={table} />
      ))}
    </MacroPanel>
  );
}

function TableBlock({ table }: { table: MacroModuleTable }) {
  return (
    <>
      <MacroDataTable caption={tableCaption(table)} table={table} />
      <TableSourceNote source={table.source} />
    </>
  );
}

function TableSourceNote({ source }: { source: MacroModuleTable["source"] }) {
  const note = source?.notes ?? source?.description ?? null;
  if (!note) {
    return null;
  }
  return <p className="macro-table-source-note">{formatMacroScalar(note)}</p>;
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
  return chartIdentifier(chart).includes("curve");
}

function chartStatusLabel(chart: MacroModuleChart): string {
  return chart.status_label ?? String(chart.status ?? "unknown");
}
