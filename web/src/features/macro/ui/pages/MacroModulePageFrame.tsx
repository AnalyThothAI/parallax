import type {
  MacroDataHealth,
  MacroModuleChart,
  MacroModuleTile,
  MacroModuleView,
  MacroSemanticRecord,
  MacroTransmissionNode,
} from "@lib/types";
import {
  Activity,
  BarChart3,
  Database,
  GitBranch,
  ListChecks,
  ShieldAlert,
  Table2,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

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
  gapLabel,
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
  const extraTables = module.tables.slice(1);
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
  const hasSupportingTable = showSupportingTable && Boolean(supportingTable.rows?.length);

  return (
    <section className="macro-page-layout" aria-label={`${moduleLabel}模块页面`}>
      <section className="macro-page-kpi-strip" aria-label="关键指标">
        {module.tiles.length > 0 ? (
          module.tiles.map((tile, index) => (
            <KpiTile tile={tile} key={tile.concept_key ?? tile.label ?? index} />
          ))
        ) : (
          <PageState label="module_tiles_missing" />
        )}
      </section>

      <section
        className="macro-page-panel macro-page-panel-primary macro-page-market-board"
        aria-label="市场板"
        data-has-table={hasSupportingTable ? "true" : "false"}
      >
        <SectionHead icon={BarChart3} meta={chartStatusLabel(primaryChart)} title="市场板" />
        <div className="macro-page-chart-table-grid">
          <div className="macro-page-chart-slot">
            <PrimaryChart
              chart={primaryChart}
              moduleId={moduleId}
              seriesData={seriesQuery.data}
              seriesLoading={shouldFetchSeries && seriesQuery.isLoading}
            />
          </div>
          {showSupportingTable ? (
            <div className="macro-page-table-slot">
              <div className="macro-page-table-title">
                <Table2 aria-hidden="true" />
                <span>{tableCaption(supportingTable)}</span>
              </div>
              <MacroDataTable caption={tableCaption(supportingTable)} table={supportingTable} />
            </div>
          ) : null}
        </div>
      </section>

      <section
        className="macro-page-panel macro-page-panel-current macro-page-decision"
        aria-label="模块判断"
      >
        <SectionHead icon={Activity} meta={macroStatusLabel(module)} title="模块判断" />
        <p className="macro-page-summary">{macroReadSummary(module)}</p>
        <ReadDetails record={currentRead} />
        <RelatedRoutes routes={module.related_routes} />
      </section>

      <section className="macro-page-panel macro-page-transmission" aria-label="传导链">
        <SectionHead icon={GitBranch} meta={moduleLabel} title="传导链" />
        <TransmissionMap nodes={module.transmission} />
      </section>

      <section
        className="macro-page-panel macro-page-evidence-panel"
        aria-label="模块证据"
      >
        <SectionHead icon={ListChecks} meta={`${String(evidenceCount)} 条`} title="模块证据" />
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

      {extraTables.length > 0 ? (
        <section className="macro-page-panel macro-page-extra-tables" aria-label="数据可用性与代理说明">
          <SectionHead icon={Table2} meta={String(extraTables.length)} title="数据可用性 / 代理说明" />
          <div className="macro-page-extra-table-grid">
            {extraTables.map((table) => (
              <MacroDataTable
                caption={tableCaption(table)}
                key={String(table.id ?? tableCaption(table))}
                table={table}
              />
            ))}
          </div>
        </section>
      ) : null}

      <section className="macro-page-quality-grid">
        <section className="macro-page-panel macro-page-source-panel" aria-label="数据来源">
          <SectionHead icon={Database} meta={module.snapshot.projection_version} title="数据来源" />
          <MacroSourceTable caption="数据源" source={module.provenance} />
        </section>

        <section className="macro-page-panel macro-page-gap-panel" aria-label="模块数据健康">
          <SectionHead
            icon={ShieldAlert}
            meta={module.data_health.summary_label ?? module.data_health.summary_status}
            title="模块数据健康"
          />
          <DataHealthBuckets dataHealth={module.data_health} scope="leaf" />
        </section>
      </section>
    </section>
  );
}

export function MacroOverviewPageFrame({
  module,
  moduleId,
  pageLabel,
  token,
}: MacroModulePageProps & {
  pageLabel: string;
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
  const currentRead = readRecord(module);
  const evidenceGroups = groupedEvidence(module);
  const evidenceCount = evidenceGroups.reduce((count, group) => count + group.items.length, 0);

  return (
    <section className="macro-page-layout" aria-label={`${pageLabel}模块页面`}>
      <section
        className="macro-page-panel macro-page-panel-current macro-page-overview-read"
        aria-label="宏观总览"
      >
        <SectionHead icon={Activity} meta={macroStatusLabel(module)} title="宏观总览" />
        <p className="macro-page-summary">{macroReadSummary(module)}</p>
        <ReadDetails record={currentRead} />
        {module.tiles.length > 0 ? (
          <div className="macro-page-kpi-strip macro-page-overview-kpis">
            {module.tiles.map((tile, index) => (
              <KpiTile tile={tile} key={tile.concept_key ?? tile.label ?? index} />
            ))}
          </div>
        ) : null}
      </section>

      <section
        className="macro-page-panel macro-page-panel-primary macro-page-market-board"
        aria-label="核心驱动"
        data-has-table={supportingTable.rows?.length ? "true" : "false"}
      >
        <SectionHead icon={BarChart3} meta={`${String(evidenceCount)} 条`} title="核心驱动" />
        <div className="macro-page-chart-table-grid">
          <div className="macro-page-chart-slot">
            <PrimaryChart
              chart={primaryChart}
              moduleId={moduleId}
              seriesData={seriesQuery.data}
              seriesLoading={shouldFetchSeries && seriesQuery.isLoading}
            />
          </div>
          {supportingTable.rows?.length ? (
            <div className="macro-page-table-slot">
              <div className="macro-page-table-title">
                <Table2 aria-hidden="true" />
                <span>{tableCaption(supportingTable)}</span>
              </div>
              <MacroDataTable caption={tableCaption(supportingTable)} table={supportingTable} />
            </div>
          ) : null}
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

      <section className="macro-page-panel macro-page-transmission" aria-label="全局传导链">
        <SectionHead icon={GitBranch} meta={pageLabel} title="全局传导链" />
        <TransmissionMap nodes={module.transmission} />
      </section>

      <section className="macro-page-panel macro-page-gap-panel" aria-label="数据健康">
        <SectionHead
          icon={ShieldAlert}
          meta={module.data_health.summary_label ?? module.data_health.summary_status}
          title="数据健康"
        />
        <DataHealthBuckets dataHealth={module.data_health} scope="overview" />
      </section>
    </section>
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
    <div className="macro-page-kpi" data-quality={stringValue(tile.quality) ?? undefined}>
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

function SectionHead({
  icon: Icon,
  meta,
  title,
}: {
  icon: LucideIcon;
  meta?: unknown;
  title: string;
}) {
  return (
    <div className="macro-page-section-head">
      <h3>
        <Icon aria-hidden="true" />
        {title}
      </h3>
      {hasMacroValue(meta) ? <span>{formatMacroScalar(meta)}</span> : null}
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

function TransmissionMap({ nodes }: { nodes: MacroTransmissionNode[] }) {
  return (
    <ol className="macro-page-transmission-map">
      {nodes.length > 0 ? (
        nodes.map((node, index) => (
          <li className="macro-page-transmission-node" key={`${node.label ?? "node"}:${index}`}>
            <span>{formatMacroScalar(node.label ?? node.kind ?? "传导节点")}</span>
            <b>{formatMacroScalar(node.value ?? node.status_label ?? node.status)}</b>
          </li>
        ))
      ) : (
        <li className="macro-page-transmission-node">
          <span>传导链</span>
          <b>暂无</b>
        </li>
      )}
    </ol>
  );
}

function RelatedRoutes({ routes }: { routes: MacroModuleView["related_routes"] }) {
  if (routes.length === 0) {
    return null;
  }
  return (
    <div className="macro-page-related-routes" aria-label="相关页面">
      {routes.slice(0, 4).map((route) => (
        <Link key={`${route.href}:${route.label}`} to={route.href}>
          {route.label}
        </Link>
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
  return module.module_read;
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
  const items = module.module_evidence[key];
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

function DataHealthBuckets({
  dataHealth,
  scope,
}: {
  dataHealth: MacroDataHealth;
  scope: "leaf" | "overview";
}) {
  const buckets = dataHealthBuckets(dataHealth, scope);
  const hasItems = buckets.some(
    (bucket) => bucket.items.length > 0 || (bucket.referenceCount ?? 0) > 0,
  );
  if (!hasItems) {
    return <PageState label="module_data_health_clear" />;
  }
  return (
    <div className="macro-page-health-buckets">
      {buckets.map((bucket) => (
        <section className="macro-page-health-bucket" key={bucket.key}>
          <div className="macro-page-health-bucket-head">
            <h4>{bucket.label}</h4>
            <span>{bucket.referenceCount ?? bucket.items.length}</span>
          </div>
          {bucket.referenceCount ? (
            <p className="macro-page-health-reference">总览级缺口，仅供参考</p>
          ) : bucket.items.length > 0 ? (
            <div className="macro-page-chip-list">
              {bucket.items.map((gap, index) => (
                <span className="macro-page-chip" key={`${bucket.key}:${index}:${gap}`}>
                  {gap}
                </span>
              ))}
            </div>
          ) : (
            <div className="macro-page-evidence-empty">暂无</div>
          )}
        </section>
      ))}
    </div>
  );
}

function dataHealthBuckets(
  dataHealth: MacroDataHealth,
  scope: "leaf" | "overview",
): Array<{
  items: string[];
  key: string;
  label: string;
  referenceCount?: number;
}> {
  return [
    {
      key: "module_gaps",
      label: "模块缺口",
      items: dataHealth.module_gaps.map(gapLabel).filter((label) => label !== "数据缺口待确认"),
    },
    {
      key: "chart_gaps",
      label: "图表缺口",
      items: dataHealth.chart_gaps.map(gapLabel).filter((label) => label !== "数据缺口待确认"),
    },
    {
      key: "global_gaps",
      label: scope === "leaf" ? "全局缺口（总览级参考）" : "全局缺口",
      items:
        scope === "overview"
          ? dataHealth.global_gaps
              .map(gapLabel)
              .filter((label) => label !== "数据缺口待确认")
          : [],
      referenceCount: scope === "leaf" ? dataHealth.global_gaps.length : undefined,
    },
    {
      key: "future_integration_gaps",
      label: "未来集成缺口",
      items: dataHealth.future_integration_gaps
        .map(gapLabel)
        .filter((label) => label !== "数据缺口待确认"),
    },
  ];
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
  module_data_health_clear: "暂无数据缺口",
  module_evidence_missing: "暂无模块证据",
  module_tiles_missing: "暂无关键指标",
  related_routes_missing: "暂无相关页面",
};

const READ_FIELDS = [
  { key: "regime_label", label: "宏观状态" },
  { key: "regime", label: "宏观状态" },
  { key: "confidence_label", label: "规则覆盖" },
  { key: "crypto_read", label: "加密影响" },
  { key: "token_impact", label: "代币影响" },
  { key: "data_note", label: "数据说明" },
  { key: "methodology_note", label: "方法说明" },
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
