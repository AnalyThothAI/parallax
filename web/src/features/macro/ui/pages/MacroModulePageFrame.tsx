import type {
  MacroModuleChart,
  MacroModuleTile,
  MacroModuleView,
  MacroSemanticRecord,
} from "@lib/types";

import { useMacroSeriesQuery } from "../../api/useMacroSeriesQuery";
import {
  chartCaption,
  chartConceptKeys,
  chartIdentifier,
  emptyTable,
  tableCaption,
} from "../../model/macroModulePageModel";
import {
  formatMacroScalar,
  macroStatusLabel,
} from "../../model/macroPageViewModel";
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
  const primaryChart = module.primary_chart;
  const supportingTable = module.tables[0] ?? emptyTable(`${moduleId}_supporting_table`);
  const seriesConceptKeys = chartConceptKeys(primaryChart);
  const shouldFetchSeries = seriesConceptKeys.length > 0 && !isYieldCurveChart(primaryChart);
  const seriesQuery = useMacroSeriesQuery({
    conceptKeys: shouldFetchSeries ? seriesConceptKeys : [],
    token,
    window: "60d",
  });
  const moduleLabel = pageLabel || macroRouteLabel(moduleId);
  const currentRead = readRecord(module);
  const evidenceGroups = groupedEvidence(module);
  const evidenceCount = evidenceGroups.reduce((count, group) => count + group.items.length, 0);

  return (
    <div className="macro-page-layout" aria-label={`${moduleLabel}模块页面`}>
      <section className="macro-page-panel macro-page-panel-current" aria-label="当前解读">
        <div className="macro-page-section-head">
          <h3>当前解读</h3>
          <span>{macroStatusLabel(module)}</span>
        </div>
        <p className="macro-page-summary">{macroReadSummary(module)}</p>
        <ReadDetails record={currentRead} />
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
          <span>{chartStatusLabel(primaryChart)}</span>
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
          <span>{String(evidenceCount)}</span>
        </div>
        {evidenceCount > 0 ? (
          <div className="macro-page-evidence-grid">
            {evidenceGroups.map((group) => (
              <EvidenceGroup group={group} key={group.key} />
            ))}
          </div>
        ) : (
          <PageState label="module_evidence_missing" />
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
            {module.data_gaps.map((gap, index) => (
              <span className="macro-page-chip" key={`${index}:${formatMacroScalar(gap)}`}>
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
  const title = chartCaption(chart);
  const chartId = chartIdentifier(chart);
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
  if (moduleId.startsWith("assets") || chartId.includes("performance")) {
    return <MacroNormalizedReturnChart chart={chart} seriesData={seriesData} title={title} />;
  }
  return <MacroTimeSeriesChart chart={chart} seriesData={seriesData} title={title} />;
}

function isYieldCurveChart(chart: MacroModuleChart): boolean {
  return chartIdentifier(chart).includes("curve");
}

function chartStatusLabel(chart: MacroModuleChart): string {
  const statusLabel = stringValue(chart.status_label);
  if (statusLabel) {
    return statusLabel;
  }
  return formatMacroScalar(chart.status ?? "unknown");
}

function KpiTile({ tile }: { tile: MacroModuleTile }) {
  const title = stringValue(tile.label) ?? stringValue(tile.short_label) ?? "未命名指标";
  const eyebrow =
    stringValue(tile.short_label) ??
    stringValue(tile.source_label) ??
    stringValue(tile.quality_label) ??
    "关键指标";
  const value = tile.display_value ?? tile.value;
  const unitLabel = stringValue(tile.unit_label);
  const footer =
    stringValue(tile.observed_at_label) ??
    stringValue(tile.quality_label) ??
    stringValue(tile.delta_label);
  return (
    <div className="macro-page-kpi">
      <span>
        <small>{eyebrow}</small>
        <b>{title}</b>
      </span>
      <strong>
        {formatMacroScalar(value)}
        {unitLabel ? <em>{unitLabel}</em> : null}
      </strong>
      {footer ? <small>{footer}</small> : null}
    </div>
  );
}

function ReadDetails({ record }: { record: MacroSemanticRecord }) {
  const entries = READ_FIELDS.map((field) => ({
    key: field.key,
    label: field.label,
    value: record[field.key],
  })).filter((entry) => hasMacroValue(entry.value));
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="macro-page-semantic-list">
      {entries.map(({ key, label, value }) => (
        <div className="macro-page-semantic-row" key={key}>
          <span>{label}</span>
          <b>{formatMacroScalar(value)}</b>
        </div>
      ))}
    </div>
  );
}

function macroReadSummary(module: MacroModuleView): string {
  const read = readRecord(module);
  if (hasMacroValue(read.headline)) {
    return formatMacroScalar(read.headline);
  }
  if (hasMacroValue(read.summary)) {
    return formatMacroScalar(read.summary);
  }
  if (hasMacroValue(read.regime_label)) {
    return formatMacroScalar(read.regime_label);
  }
  return formatMacroScalar(module.snapshot.status);
}

function readRecord(module: MacroModuleView): MacroSemanticRecord {
  return module.read;
}

function groupedEvidence(module: MacroModuleView): EvidenceGroupModel[] {
  return EVIDENCE_GROUPS.map((group) => ({
    ...group,
    items: evidenceItemsForGroup(module, group.key),
  }));
}

function evidenceItemsForGroup(
  module: MacroModuleView,
  key: string,
): Array<{ detail: string; label: string }> {
  const items = module.evidence[key];
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) =>
      item && typeof item === "object"
        ? {
            label: formatMacroScalar((item as MacroSemanticRecord).label),
            detail: formatMacroScalar((item as MacroSemanticRecord).description),
          }
        : null,
    )
    .filter((item): item is { detail: string; label: string } =>
      Boolean(item && item.label !== "暂无"),
    );
}

function EvidenceGroup({ group }: { group: EvidenceGroupModel }) {
  return (
    <section aria-label={group.label} className="macro-page-evidence-group" role="group">
      <div className="macro-page-evidence-group-head">
        <h4>{group.label}</h4>
        <span>{group.items.length}</span>
      </div>
      {group.items.length > 0 ? (
        <div className="macro-page-signal-list">
          {group.items.map((signal, index) => (
            <article className="macro-page-signal" key={`${signal.label}:${index}`}>
              <b>{signal.label}</b>
              <span>{signal.detail}</span>
            </article>
          ))}
        </div>
      ) : (
        <div className="macro-page-evidence-empty">暂无</div>
      )}
    </section>
  );
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

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

const PAGE_STATE_LABELS: Record<string, string> = {
  module_data_gaps_clear: "暂无数据缺口",
  module_evidence_missing: "暂无证据",
  module_tiles_missing: "暂无关键指标",
  related_routes_missing: "暂无相关页面",
};

const READ_FIELDS = [
  { key: "regime_label", label: "宏观状态" },
  { key: "regime", label: "宏观状态" },
  { key: "confidence_label", label: "置信度" },
  { key: "crypto_read", label: "加密影响" },
  { key: "token_impact", label: "代币影响" },
] as const;

type EvidenceGroupModel = {
  items: Array<{ detail: string; label: string }>;
  key: string;
  label: string;
};

const EVIDENCE_GROUPS = [
  { key: "confirmations", label: "确认" },
  { key: "contradictions", label: "反证" },
  { key: "watch_triggers", label: "观察触发" },
  { key: "invalidations", label: "失效条件" },
] as const;
