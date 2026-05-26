import type { MacroModuleChart, MacroSeriesData } from "@lib/types";

import { useMacroSeriesQuery } from "../../api/useMacroSeriesQuery";
import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  buildMacroMetrics,
  extraTables,
  macroReadSummary,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import {
  chartCaption,
  chartConceptKeys,
  chartIdentifier,
  tableCaption,
} from "../../model/macroModulePageModel";
import { formatMacroScalar, macroStatusLabel } from "../../model/macroPageViewModel";
import { macroRouteLabel, type MacroModuleId } from "../../model/macroRoutes";
import { MacroNormalizedReturnChart } from "../charts/MacroNormalizedReturnChart";
import { MacroTimeSeriesChart } from "../charts/MacroTimeSeriesChart";
import { MacroYieldCurveChart } from "../charts/MacroYieldCurveChart";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroEvidencePanel } from "../primitives/MacroEvidencePanel";
import { MacroMetricStrip } from "../primitives/MacroMetricStrip";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroReadPanel } from "../primitives/MacroReadPanel";
import { MacroTransmissionPanel } from "../primitives/MacroTransmissionPanel";
import { MacroDataTable } from "../tables/MacroDataTable";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import "./macroPages.css";

export function MacroLeafModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const metrics = buildMacroMetrics({ tiles: module.tiles });
  const supportingTable = primarySupportingTable(module);
  const remainingTables = extraTables(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });
  const evidenceGroups = buildMacroEvidenceGroups(module.module_evidence);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");

  return (
    <MacroPageScaffold label={`${macroRouteLabel(moduleId)}模块页面`} pageKind="leaf">
      <MacroMetricStrip
        ariaLabel="关键指标"
        density={metrics.length > 4 ? "compact" : "card"}
        metrics={metrics}
      />
      <MacroMarketBoard
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
      />
      {remainingTables.length > 0 ? (
        <MacroPanel
          ariaLabel="数据可用性与代理说明"
          meta={String(remainingTables.length)}
          span="full"
          title="数据可用性 / 代理说明"
        >
          {remainingTables.map((table) => (
            <MacroDataTable
              caption={tableCaption(table)}
              key={String(table.id ?? tableCaption(table))}
              table={table}
            />
          ))}
        </MacroPanel>
      ) : null}
      <MacroReadPanel
        meta={macroStatusLabel(module)}
        read={module.module_read}
        summary={macroReadSummary(module)}
      />
      <MacroTransmissionPanel meta={macroRouteLabel(moduleId)} nodes={module.transmission} />
      <MacroEvidencePanel groups={evidenceGroups} />
      <MacroPanel
        ariaLabel="数据来源"
        meta={module.snapshot.projection_version}
        span="half"
        title="数据来源"
      >
        <MacroSourceTable caption="数据源" source={module.provenance} />
      </MacroPanel>
      <MacroDataHealthPanel
        buckets={dataHealthBuckets}
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
      />
    </MacroPageScaffold>
  );
}

export function MacroMarketBoard({
  ariaLabel,
  chart,
  moduleId,
  seriesData,
  seriesLoading,
  supportingTable,
  title = "市场板",
}: {
  ariaLabel?: string;
  chart: MacroModuleChart;
  moduleId: MacroModuleId;
  seriesData?: MacroSeriesData | null;
  seriesLoading?: boolean;
  supportingTable: ReturnType<typeof primarySupportingTable> | null;
  title?: string;
}) {
  return (
    <MacroPanel
      ariaLabel={ariaLabel ?? title}
      meta={chartStatusLabel(chart)}
      span="full"
      title={title}
    >
      <PrimaryChart
        chart={chart}
        moduleId={moduleId}
        seriesData={seriesData}
        seriesLoading={seriesLoading}
      />
      {supportingTable ? (
        <>
          <MacroDataTable caption={tableCaption(supportingTable)} table={supportingTable} />
          <TableSourceNote source={supportingTable.source} />
        </>
      ) : null}
    </MacroPanel>
  );
}

function TableSourceNote({
  source,
}: {
  source: ReturnType<typeof primarySupportingTable>["source"];
}) {
  const note = source?.notes ?? source?.description ?? null;
  if (!note) {
    return null;
  }
  return <p className="macro-table-source-note">{formatMacroScalar(note)}</p>;
}

export function useMacroPrimarySeries({
  chart,
  token,
}: {
  chart: MacroModuleChart;
  token: string;
}) {
  const seriesConceptKeys = chartConceptKeys(chart);
  const shouldFetchSeries = seriesConceptKeys.length > 0 && !isYieldCurveChart(chart);
  return useMacroSeriesQuery({
    conceptKeys: shouldFetchSeries ? seriesConceptKeys : [],
    token,
    window: "60d",
  });
}

function PrimaryChart({
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
