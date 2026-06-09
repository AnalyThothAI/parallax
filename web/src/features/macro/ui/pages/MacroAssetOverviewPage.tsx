import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { useMacroAssetCorrelationQuery } from "../../api/useMacroAssetCorrelationQuery";
import {
  assetTitleByKey,
  strongestCorrelationPairs,
} from "../../model/macroCorrelationModel";
import { tableCaption } from "../../model/macroModulePageModel";
import {
  buildMacroDataHealthBuckets,
  macroReadSummary,
  primarySupportingTable,
  type MacroDataHealthBucket,
} from "../../model/macroModulePresentation";
import { macroStatusLabel } from "../../model/macroPageViewModel";
import { buildMacroTableModel, type MacroTableRowModel } from "../../model/macroTableColumns";
import {
  MacroCorrelationMatrixTable,
  MacroCorrelationPairList,
} from "../correlation/MacroCorrelationTables";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroSourceTable } from "../tables/MacroSourceTable";
import { MacroTableFrame } from "../tables/MacroTableFrame";

import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import "./macroPages.css";

type MacroDailyBriefBlock = {
  id: string;
  title: string;
  stance: string;
  body: string;
};

type MacroDailyBrief = {
  headline: string;
  status: string;
  blocks: MacroDailyBriefBlock[];
  dataQuality?: MacroDailyBriefQuality;
};

export function MacroAssetOverviewPage({ module, token }: MacroModulePageProps) {
  const supportingTable = primarySupportingTable(module);
  const dailyBrief = normalizeDailyBrief(module.daily_brief);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");
  const correlationQuery = useMacroAssetCorrelationQuery({ token, window: "60d" });
  const correlationData = correlationQuery.data ?? null;
  const titleByKey = useMemo(() => assetTitleByKey(correlationData), [correlationData]);
  const positivePairs = useMemo(
    () => strongestCorrelationPairs(correlationData, "positive").slice(0, 3),
    [correlationData],
  );
  const negativePairs = useMemo(
    () => strongestCorrelationPairs(correlationData, "negative").slice(0, 3),
    [correlationData],
  );
  const availabilityTable = module.tables.find((table) => table.id === "availability_proxy_notes");

  return (
    <MacroPageScaffold label="大类资产模块页面" pageKind="leaf">
      <MacroPanel
        ariaLabel="市场仪表盘"
        className="macro-assets-dashboard-panel"
        meta={`${module.snapshot.asof_label ?? macroStatusLabel(module)} · ${
          supportingTable.rows?.length ?? 0
        } 项`}
        span="full"
        title="市场仪表盘"
      >
        <AssetGroupBoard table={supportingTable} />
      </MacroPanel>
      <MacroPanel
        ariaLabel="今日判断"
        className="macro-assets-judgment-panel"
        meta={dailyBrief?.status ?? macroStatusLabel(module)}
        span="full"
        title="今日判断"
      >
        <DailyBriefContent brief={dailyBrief} fallback={macroReadSummary(module)} />
      </MacroPanel>
      <MacroPanel
        ariaLabel="60日相关性"
        className="macro-assets-correlation-panel"
        meta={correlationMeta(correlationData, correlationQuery.isFetching)}
        span="major"
        title="60日相关性"
      >
        {correlationQuery.isLoading ? (
          <div className="macro-assets-inline-state">相关性加载中</div>
        ) : correlationQuery.isError ? (
          <div className="macro-assets-inline-state">
            相关性暂不可用：{errorLabel(correlationQuery.error)}
          </div>
        ) : correlationData ? (
          <div className="macro-assets-correlation-layout">
            <MacroCorrelationMatrixTable
              className="macro-assets-correlation-matrix"
              data={correlationData}
              label="60日资产相关性矩阵"
              minWidth={560}
              titleByKey={titleByKey}
            />
            <div className="macro-assets-correlation-pairs">
              <div className="macro-assets-pair-group">
                <h4>正相关</h4>
                <MacroCorrelationPairList
                  emptyLabel="暂无"
                  pairs={positivePairs}
                  titleByKey={titleByKey}
                  variant="summary"
                />
              </div>
              <div className="macro-assets-pair-group">
                <h4>负相关</h4>
                <MacroCorrelationPairList
                  emptyLabel="暂无"
                  pairs={negativePairs}
                  titleByKey={titleByKey}
                  variant="summary"
                />
              </div>
              <Link className="macro-assets-detail-link" to="/macro/assets/correlation">
                打开相关性详情
              </Link>
            </div>
          </div>
        ) : (
          <div className="macro-assets-inline-state">暂无相关性样本</div>
        )}
      </MacroPanel>
      <MacroPanel
        ariaLabel="数据诊断"
        className="macro-assets-diagnostics-panel"
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
        span="minor"
        title="数据诊断"
      >
        <DataDiagnostics
          availabilityTable={availabilityTable}
          buckets={dataHealthBuckets}
          moduleStatus={macroStatusLabel(module)}
          provenance={module.provenance}
        />
      </MacroPanel>
    </MacroPageScaffold>
  );
}

type AssetGroup = {
  key: string;
  route: string;
  rows: MacroTableRowModel[];
  title: string;
};

const ASSET_GROUPS: Array<{
  key: string;
  route: string;
  title: string;
  match: (rowKey: string) => boolean;
}> = [
  {
    key: "equities",
    title: "美股",
    route: "/macro/assets/equities",
    match: (key) =>
      ["asset:spx", "asset:spy", "asset:qqq", "asset:ndx", "asset:dji", "asset:iwm", "asset:rut"]
        .includes(key),
  },
  {
    key: "bonds",
    title: "债券",
    route: "/macro/assets/bonds",
    match: (key) =>
      key.startsWith("bond:") || ["asset:tlt", "asset:ief", "asset:hyg", "asset:lqd"].includes(key),
  },
  {
    key: "commodities",
    title: "商品",
    route: "/macro/assets/commodities",
    match: (key) => key.startsWith("commodity:"),
  },
  {
    key: "fx",
    title: "外汇",
    route: "/macro/assets/fx",
    match: (key) => key.startsWith("fx:"),
  },
  {
    key: "crypto",
    title: "加密货币",
    route: "/macro/assets/crypto",
    match: (key) => key.startsWith("crypto:"),
  },
];

function AssetGroupBoard({ table }: { table: MacroModuleTable }) {
  const model = useMemo(() => buildMacroTableModel(table), [table]);
  const groups = useMemo(() => assetGroups(model.rows), [model.rows]);
  if (groups.length === 0) {
    return <p className="macro-table-source-note">大类资产快照暂无可展示行。</p>;
  }
  return (
    <div className="macro-assets-market-board">
      {groups.map((group) => (
        <article className="macro-assets-group" key={group.key}>
          <div className="macro-assets-group-head">
            <h4>{group.title}</h4>
            <Link to={group.route}>查看{group.title}详情</Link>
          </div>
          <MacroTableFrame caption={group.title} minWidth={540} stickyFirstColumn>
            <table aria-label={group.title} className="macro-assets-market-table">
              <caption>{group.title}</caption>
              <thead>
                <tr>
                  <th scope="col">代码</th>
                  <th scope="col">名称</th>
                  <th scope="col">最新</th>
                  <th scope="col">日涨跌幅</th>
                  <th scope="col">日期</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((row) => (
                  <tr key={row.id}>
                    <th scope="row">{assetSymbol(row)}</th>
                    <td>{cell(row, "indicator")}</td>
                    <td>{cell(row, "latest")}</td>
                    <td data-tone={deltaTone(row)}>{dayDelta(row)}</td>
                    <td>{observedAt(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </MacroTableFrame>
        </article>
      ))}
    </div>
  );
}

function DailyBriefContent({
  brief,
  fallback,
}: {
  brief: MacroDailyBrief | null;
  fallback: string;
}) {
  return (
    <div className="macro-daily-brief">
      <strong>{brief?.headline ?? fallback}</strong>
      {brief?.blocks.length ? (
        <div className="macro-daily-brief-grid">
          {brief.blocks.map((block) => (
            <article className="macro-daily-brief-block" key={block.id}>
              <span>{block.stance}</span>
              <b>{block.title}</b>
              <p>{block.body}</p>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DataDiagnostics({
  availabilityTable,
  buckets,
  moduleStatus,
  provenance,
}: {
  availabilityTable?: MacroModuleTable;
  buckets: MacroDataHealthBucket[];
  moduleStatus: string;
  provenance: MacroSemanticRecord;
}) {
  const sourceCount = sourceRows(provenance);
  const gapCount = buckets.reduce(
    (count, bucket) => count + bucket.items.length + (bucket.referenceCount ?? 0),
    0,
  );
  return (
    <div className="macro-assets-diagnostics">
      <dl className="macro-assets-diagnostics-summary">
        <div>
          <dt>状态</dt>
          <dd>{moduleStatus}</dd>
        </div>
        <div>
          <dt>来源</dt>
          <dd>{sourceCount}</dd>
        </div>
        <div>
          <dt>缺口</dt>
          <dd>{gapCount}</dd>
        </div>
      </dl>
      <div className="macro-assets-diagnostics-section">
        <h4>缺口</h4>
        {gapCount > 0 ? (
          <div className="macro-health-buckets">
            {buckets.map((bucket) => (
              <div className="macro-health-bucket" key={bucket.key}>
                <div className="macro-health-bucket-head">
                  <h4>{bucket.label}</h4>
                  <span>{bucket.referenceCount ?? bucket.items.length}</span>
                </div>
                {bucket.referenceCount ? (
                  <p className="macro-health-reference">总览级缺口，仅供参考</p>
                ) : bucket.items.length > 0 ? (
                  <div className="macro-health-chip-list">
                    {bucket.items.map((item, index) => (
                      <span className="macro-health-chip" key={`${bucket.key}:${index}:${item}`}>
                        {item}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="macro-health-empty">暂无</div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="macro-health-empty" role="status">
            暂无数据缺口
          </div>
        )}
      </div>
      <div className="macro-assets-diagnostics-section">
        <h4>来源</h4>
        <MacroSourceTable caption="数据源" source={provenance} />
      </div>
      {availabilityTable ? (
        <div className="macro-assets-diagnostics-section">
          <h4>覆盖</h4>
          <CompactAvailabilityTable table={availabilityTable} />
        </div>
      ) : null}
    </div>
  );
}

function CompactAvailabilityTable({ table }: { table: MacroModuleTable }) {
  const model = useMemo(() => buildMacroTableModel(table), [table]);
  const rows = model.rows.slice(0, 12);
  if (rows.length === 0) {
    return <p className="macro-table-source-note">暂无覆盖明细。</p>;
  }
  return (
    <MacroTableFrame caption={tableCaption(table)} minWidth={760} stickyFirstColumn>
      <table className="macro-assets-availability-table" aria-label={tableCaption(table)}>
        <caption>{tableCaption(table)}</caption>
        <thead>
          <tr>
            <th scope="col">项目</th>
            <th scope="col">状态</th>
            <th scope="col">最新观测</th>
            <th scope="col">历史覆盖</th>
            <th scope="col">说明</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <th scope="row">{cell(row, "item")}</th>
              <td>{cell(row, "status")}</td>
              <td>{cell(row, "latest")}</td>
              <td>{cell(row, "coverage")}</td>
              <td>{cell(row, "notes")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MacroTableFrame>
  );
}

function normalizeDailyBrief(value: unknown): MacroDailyBrief | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const blocks = Array.isArray(record.blocks)
    ? record.blocks.flatMap((block) => normalizeDailyBriefBlock(block))
    : [];
  return {
    headline: String(record.headline ?? "今日判断暂不可用"),
    status: String(record.status ?? "unknown"),
    blocks,
    dataQuality: normalizeDailyBriefQuality(record.data_quality),
  };
}

function normalizeDailyBriefBlock(value: unknown): MacroDailyBriefBlock[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  const id = String(record.id ?? "").trim();
  const title = String(record.title ?? "").trim();
  const body = String(record.body ?? "").trim();
  if (!id || !title || !body) return [];
  return [
    {
      id,
      title,
      body,
      stance: String(record.stance ?? "neutral"),
    },
  ];
}

function normalizeDailyBriefQuality(value: unknown): MacroDailyBriefQuality | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  return {
    status: String(record.status ?? "unknown"),
    gapCount: numberValue(record.gap_count),
    historyCoverageRatio: numberValue(record.history_coverage_ratio),
    latestCoverageRatio: numberValue(record.latest_coverage_ratio),
  };
}

function assetGroups(rows: MacroTableRowModel[]): AssetGroup[] {
  return ASSET_GROUPS.map((group) => ({
    key: group.key,
    route: group.route,
    rows: rows.filter((row) => group.match(rowKey(row))),
    title: group.title,
  })).filter((group) => group.rows.length > 0);
}

function rowKey(row: MacroTableRowModel): string {
  return String(row.raw.row_id ?? row.raw.concept_key ?? row.id ?? "").toLowerCase();
}

function cell(row: MacroTableRowModel, columnId: string): string {
  return row.cells[columnId]?.displayValue ?? "暂无";
}

function assetSymbol(row: MacroTableRowModel): string {
  const symbol = row.cells.symbol?.displayValue;
  if (symbol && symbol !== "暂无") return symbol;
  const rawSymbol = stringValue(row.raw.symbol) ?? stringValue(row.raw.ticker);
  if (rawSymbol) return rawSymbol;
  const key = rowKey(row);
  const suffix = key.split(":").at(-1);
  return suffix ? suffix.toUpperCase() : "暂无";
}

function dayDelta(row: MacroTableRowModel): string {
  const oneDay = row.cells.delta_1d?.displayValue;
  if (oneDay && oneDay !== "暂无") return oneDay;
  return row.cells.delta_20d?.displayValue ?? "暂无";
}

function observedAt(row: MacroTableRowModel): string {
  const observed = row.cells.observed_at?.displayValue;
  if (observed && observed !== "暂无") return observed;
  const latestObserved = row.cells.latest_observed_at?.displayValue;
  if (latestObserved && latestObserved !== "暂无") return latestObserved;
  return (
    stringValue(row.raw.observed_at) ??
    stringValue(row.raw.latest_observed_at) ??
    stringValue(row.raw.asof_date) ??
    "暂无"
  );
}

function deltaTone(row: MacroTableRowModel): "up" | "down" | "flat" {
  const value = row.cells.delta_1d?.sortValue ?? row.cells.delta_20d?.sortValue;
  if (typeof value !== "number") return "flat";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

function correlationMeta(data: unknown, isFetching: boolean): string {
  if (isFetching) return "更新中";
  if (!data || typeof data !== "object") return "暂无";
  const record = data as { asof_date?: string | null; window?: string };
  return record.asof_date ? `截至 ${record.asof_date}` : (record.window ?? "相关性");
}

function errorLabel(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "请求失败";
}

function sourceRows(provenance: MacroSemanticRecord): number {
  const rows = provenance.rows;
  return Array.isArray(rows) ? rows.length : 0;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

type MacroDailyBriefQuality = {
  gapCount?: number;
  historyCoverageRatio?: number;
  latestCoverageRatio?: number;
  status: string;
};
