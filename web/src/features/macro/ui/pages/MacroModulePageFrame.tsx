import type {
  MacroModuleChart,
  MacroModuleTile,
  MacroModuleView,
  MacroSemanticRecord,
} from "@lib/types";

import { useMacroSeriesQuery } from "../../api/useMacroSeriesQuery";
import {
  chartConceptKeys,
  emptyChart,
  emptyTable,
  tableCaption,
} from "../../model/macroModulePageModel";
import { formatMacroScalar, macroFieldLabel } from "../../model/macroPageViewModel";
import { macroRouteLabel, type MacroModuleId } from "../../model/macroRoutes";
import { MacroNormalizedReturnChart } from "../charts/MacroNormalizedReturnChart";
import { MacroTimeSeriesChart } from "../charts/MacroTimeSeriesChart";
import { MacroYieldCurveChart } from "../charts/MacroYieldCurveChart";
import { MacroDataTable } from "../tables/MacroDataTable";
import { MacroSourceTable } from "../tables/MacroSourceTable";
import "./macroPages.css";

export type MacroModulePageProps = {
  module: MacroModuleView;
  moduleId: MacroModuleId;
  token: string;
};

export function MacroModulePageFrame({
  module,
  moduleId,
  pageLabel,
  showSupportingTable = true,
  token,
}: MacroModulePageProps & {
  pageLabel: string;
  showSupportingTable?: boolean;
}) {
  const primaryChart = module.charts[0] ?? emptyChart(`${moduleId}_primary_chart`);
  const supportingTable = module.tables[0] ?? emptyTable(`${moduleId}_supporting_table`);
  const seriesConceptKeys = chartConceptKeys(primaryChart);
  const shouldFetchSeries = seriesConceptKeys.length > 0 && !isYieldCurveChart(primaryChart);
  const seriesQuery = useMacroSeriesQuery({
    conceptKeys: shouldFetchSeries ? seriesConceptKeys : [],
    token,
    window: "60d",
  });
  const moduleLabel = pageLabel || macroRouteLabel(moduleId);
  const currentReadSummary = macroReadSummary(module);

  return (
    <div className="macro-page-layout" aria-label={`${moduleLabel}模块页面`}>
      <section className="macro-page-panel macro-page-panel-current" aria-label="当前解读">
        <div className="macro-page-section-head">
          <h3>当前解读</h3>
          <span>{formatMacroScalar(module.snapshot.status)}</span>
        </div>
        <p className="macro-page-summary">{currentReadSummary}</p>
        <SemanticList record={module.current_read} excludeKeys={["summary"]} />
      </section>

      <section className="macro-page-kpi-strip" aria-label="关键指标">
        {module.tiles.length > 0 ? (
          module.tiles.map((tile, index) => (
            <KpiTile tile={tile} key={tile.concept_key ?? tile.label ?? index} />
          ))
        ) : (
          <PageState label="module_tiles_missing" />
        )}
      </section>

      <section className="macro-page-panel macro-page-panel-primary" aria-label="核心图表">
        <div className="macro-page-section-head">
          <h3>核心图表</h3>
          <span>{formatMacroScalar(primaryChart.status ?? primaryChart.chart_id)}</span>
        </div>
        <PrimaryChart
          chart={primaryChart}
          moduleId={moduleId}
          seriesData={seriesQuery.data}
          seriesLoading={shouldFetchSeries && seriesQuery.isLoading}
        />
      </section>

      {showSupportingTable ? (
        <section className="macro-page-panel" aria-label="支撑表格">
          <MacroDataTable caption={tableCaption(supportingTable)} table={supportingTable} />
        </section>
      ) : null}

      <section className="macro-page-panel" aria-label="证据板">
        <div className="macro-page-section-head">
          <h3>证据板</h3>
          <span>{String(module.signals.length)}</span>
        </div>
        {module.signals.length > 0 ? (
          <div className="macro-page-signal-list">
            {module.signals.map((signal, index) => (
              <article className="macro-page-signal" key={signal.code ?? index}>
                <b>{formatMacroScalar(signal.code ?? "signal")}</b>
                <span>{formatMacroScalar(signal.description)}</span>
              </article>
            ))}
          </div>
        ) : (
          <PageState label="module_signals_missing" />
        )}
      </section>

      <section className="macro-page-panel" aria-label="数据源">
        <MacroSourceTable caption="数据源" source={module.provenance} />
      </section>

      <section className="macro-page-panel" aria-label="数据缺口">
        <div className="macro-page-section-head">
          <h3>数据缺口</h3>
          <span>{String(module.data_gaps.length)}</span>
        </div>
        {module.data_gaps.length > 0 ? (
          <div className="macro-page-chip-list">
            {module.data_gaps.map((gap) => (
              <span className="macro-page-chip" key={formatMacroScalar(gap)}>
                {formatMacroScalar(gap)}
              </span>
            ))}
          </div>
        ) : (
          <PageState label="module_data_gaps_clear" />
        )}
      </section>
    </div>
  );
}

function PrimaryChart({
  chart,
  moduleId,
  seriesData,
  seriesLoading,
}: {
  chart: MacroModuleChart;
  moduleId: MacroModuleId;
  seriesData?: Parameters<typeof MacroTimeSeriesChart>[0]["seriesData"];
  seriesLoading?: boolean;
}) {
  const title = tableCaption({ table_id: chart.chart_id });
  if (isYieldCurveChart(chart) || moduleId === "rates/yield-curve") {
    return <MacroYieldCurveChart chart={chart} title={title} />;
  }
  if (seriesLoading) {
    return (
      <div aria-label={`${title}加载状态`} className="macro-page-chart-loading" role="status">
        图表序列加载中
      </div>
    );
  }
  if (moduleId.startsWith("assets") || chart.chart_id.includes("performance")) {
    return <MacroNormalizedReturnChart chart={chart} seriesData={seriesData} title={title} />;
  }
  return <MacroTimeSeriesChart chart={chart} seriesData={seriesData} title={title} />;
}

function isYieldCurveChart(chart: MacroModuleChart): boolean {
  return chart.chart_id.includes("yield_curve");
}

function KpiTile({ tile }: { tile: MacroModuleTile }) {
  return (
    <div className="macro-page-kpi">
      <span>
        <small>{formatMacroScalar(tile.concept_key ?? tile.label)}</small>
        <b>{formatMacroScalar(tile.label ?? tile.concept_key)}</b>
      </span>
      <strong>
        {formatMacroScalar(tile.latest)}
        {tile.unit ? <em>{tile.unit}</em> : null}
      </strong>
    </div>
  );
}

function SemanticList({
  excludeKeys = [],
  record,
}: {
  excludeKeys?: string[];
  record: MacroSemanticRecord;
}) {
  const entries = Object.entries(record)
    .filter(([key, value]) => !excludeKeys.includes(key) && hasMacroValue(value))
    .slice(0, 6);
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="macro-page-semantic-list">
      {entries.map(([key, value]) => (
        <div className="macro-page-semantic-row" key={key}>
          <span>{macroFieldLabel(key)}</span>
          <b>{formatMacroScalar(value)}</b>
        </div>
      ))}
    </div>
  );
}

function macroReadSummary(module: MacroModuleView): string {
  if (hasMacroValue(module.current_read.summary)) {
    return formatMacroScalar(module.current_read.summary);
  }
  if (hasMacroValue(module.current_read.current_regime)) {
    return formatMacroScalar(module.current_read.current_regime);
  }
  if (hasMacroValue(module.current_read.regime)) {
    return formatMacroScalar(module.current_read.regime);
  }
  return formatMacroScalar(module.snapshot.status);
}

function hasMacroValue(value: unknown): boolean {
  if (typeof value === "number" || typeof value === "boolean") {
    return true;
  }
  if (typeof value === "string") {
    return value.trim().length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (value && typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return false;
}

function PageState({ label }: { label: string }) {
  return (
    <div className="macro-page-state" role="status">
      {PAGE_STATE_LABELS[label] ?? label}
    </div>
  );
}

const PAGE_STATE_LABELS: Record<string, string> = {
  module_data_gaps_clear: "暂无数据缺口",
  module_signals_missing: "暂无证据信号",
  module_tiles_missing: "暂无关键指标",
  related_routes_missing: "暂无相关页面",
};
