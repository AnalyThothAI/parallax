import type {
  MacroAssetCorrelationData,
  MacroAssetCorrelationPair,
  MacroModuleTable,
} from "@lib/types";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { useMacroAssetCorrelationQuery } from "../../api/useMacroAssetCorrelationQuery";
import {
  assetLabel,
  assetTitleByKey,
  correlationTone,
  matrixCorrelationLabel,
  signedCorrelationLabel,
  strongestCorrelationPairs,
} from "../../model/macroCorrelationModel";
import { tableCaption } from "../../model/macroModulePageModel";
import {
  buildMacroDataHealthBuckets,
  buildMacroMetrics,
  macroReadSummary,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroStatusLabel } from "../../model/macroPageViewModel";
import { buildMacroTableModel, type MacroTableRowModel } from "../../model/macroTableColumns";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroMetricStrip } from "../primitives/MacroMetricStrip";
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
  const metrics = buildMacroMetrics({ tiles: module.tiles }).slice(0, 8);
  const supportingTable = primarySupportingTable(module);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");
  const dailyBrief = normalizeDailyBrief(module.daily_brief);
  const correlationQuery = useMacroAssetCorrelationQuery({ token, window: "60d" });
  const availabilityTable = module.tables.find((table) => table.id === "availability_proxy_notes");

  return (
    <MacroPageScaffold label="大类资产模块页面" pageKind="leaf">
      <section className="macro-assets-lede" aria-label="大类资产今日判断">
        <div className="macro-assets-lede-copy">
          <span>{module.snapshot.asof_label ?? macroStatusLabel(module)}</span>
          <strong>{dailyBrief?.headline ?? macroReadSummary(module)}</strong>
          <p>{readableText(module.module_read.data_note) ?? macroReadSummary(module)}</p>
        </div>
        <dl className="macro-assets-status-grid" aria-label="大类资产数据状态">
          <div>
            <dt>状态</dt>
            <dd>{macroStatusLabel(module)}</dd>
          </div>
          <div>
            <dt>资产</dt>
            <dd>{supportingTable.rows?.length ?? 0}</dd>
          </div>
          <div>
            <dt>覆盖</dt>
            <dd>{coverageLabel(dailyBrief)}</dd>
          </div>
        </dl>
      </section>
      <MacroMetricStrip
        ariaLabel="关键指标"
        density="compact"
        metrics={metrics}
      />
      <MacroPanel
        ariaLabel="跨资产快照"
        className="macro-assets-board-panel"
        meta={`${module.snapshot.asof_label ?? "最新"} · ${supportingTable.rows?.length ?? 0} 项`}
        span="full"
        title="跨资产快照"
      >
        <AssetGroupBoard table={supportingTable} />
      </MacroPanel>
      <MacroPanel
        ariaLabel="资产相关性"
        className="macro-assets-correlation-panel"
        meta={correlationMeta(correlationQuery.data ?? null, correlationQuery.isFetching)}
        span="major"
        title="60日相关性"
      >
        <CorrelationPreview
          data={correlationQuery.data ?? null}
          error={correlationQuery.error}
          isError={correlationQuery.isError}
          isLoading={correlationQuery.isLoading}
        />
      </MacroPanel>
      <MacroPanel
        ariaLabel="交叉分析"
        className="macro-assets-brief-panel"
        meta={dailyBrief?.status ?? "missing"}
        span="minor"
        title="交叉分析"
      >
        <DailyBriefContent brief={dailyBrief} />
      </MacroPanel>
      <MacroPanel
        ariaLabel="数据来源"
        meta={sourceMeta(module.provenance)}
        span="half"
        title="数据来源"
      >
        <MacroSourceTable caption="数据源" source={module.provenance} />
      </MacroPanel>
      <MacroDataHealthPanel
        buckets={dataHealthBuckets}
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
      />
      {availabilityTable ? (
        <MacroPanel
          ariaLabel="数据覆盖"
          className="macro-assets-availability-panel"
          meta={`${availabilityTable.rows?.length ?? 0} 项`}
          span="full"
          title={tableCaption(availabilityTable)}
        >
          <CompactAvailabilityTable table={availabilityTable} />
        </MacroPanel>
      ) : null}
      {supportingTable.rows?.length ? null : (
        <MacroPanel ariaLabel="大类资产快照" span="full" title={tableCaption(supportingTable)}>
          <p className="macro-table-source-note">大类资产快照暂无可展示行。</p>
        </MacroPanel>
      )}
    </MacroPageScaffold>
  );
}

type AssetGroup = {
  key: string;
  title: string;
  route: string;
  rows: MacroTableRowModel[];
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
    match: (rowKey) => ["asset:spx", "asset:ndx", "asset:dji", "asset:rut"].includes(rowKey),
  },
  {
    key: "bonds",
    title: "债券",
    route: "/macro/assets/bonds",
    match: (rowKey) => ["asset:tlt", "asset:hyg", "asset:lqd"].includes(rowKey),
  },
  {
    key: "commodities",
    title: "商品",
    route: "/macro/assets/commodities",
    match: (rowKey) => rowKey.startsWith("commodity:"),
  },
  {
    key: "fx",
    title: "外汇",
    route: "/macro/assets/fx",
    match: (rowKey) => rowKey.startsWith("fx:"),
  },
  {
    key: "crypto",
    title: "加密货币",
    route: "/macro/assets/crypto",
    match: (rowKey) => rowKey.startsWith("crypto:"),
  },
];

function AssetGroupBoard({ table }: { table: MacroModuleTable }) {
  const model = useMemo(() => buildMacroTableModel(table), [table]);
  const groups = useMemo(() => assetGroups(model.rows), [model.rows]);
  if (groups.length === 0) {
    return <p className="macro-table-source-note">大类资产快照暂无可展示行。</p>;
  }
  return (
    <div className="macro-assets-group-board">
      {groups.map((group) => (
        <section className="macro-assets-group" key={group.key} aria-label={group.title}>
          <div className="macro-assets-group-head">
            <h4>{group.title}</h4>
            <Link to={group.route}>查看详情</Link>
          </div>
          <table className="macro-assets-mini-table">
            <thead>
              <tr>
                <th scope="col">名称</th>
                <th scope="col">最新</th>
                <th scope="col">20日</th>
                <th scope="col">来源</th>
              </tr>
            </thead>
            <tbody>
              {group.rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{cell(row, "indicator")}</th>
                  <td>{cell(row, "latest")}</td>
                  <td data-tone={deltaTone(row)}>{cell(row, "delta_20d")}</td>
                  <td>{cell(row, "source")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

function CorrelationPreview({
  data,
  error,
  isError,
  isLoading,
}: {
  data: MacroAssetCorrelationData | null;
  error: unknown;
  isError: boolean;
  isLoading: boolean;
}) {
  const titleByKey = useMemo(() => assetTitleByKey(data), [data]);
  const positivePairs = useMemo(() => strongestCorrelationPairs(data, "positive").slice(0, 3), [data]);
  const negativePairs = useMemo(() => strongestCorrelationPairs(data, "negative").slice(0, 3), [data]);

  if (isLoading) {
    return <div className="macro-assets-inline-state">相关性加载中</div>;
  }
  if (isError) {
    return <div className="macro-assets-inline-state">相关性暂不可用：{errorLabel(error)}</div>;
  }
  if (!data || data.assets.length === 0) {
    return <div className="macro-assets-inline-state">暂无相关性样本</div>;
  }
  return (
    <div className="macro-assets-correlation-layout">
      <MacroTableFrame caption="60日资产相关性矩阵" minWidth={560} stickyFirstColumn>
        <table aria-label="60日资产相关性矩阵" className="macro-matrix-table macro-assets-correlation-matrix">
          <caption>60日资产相关性矩阵</caption>
          <thead>
            <tr>
              <th scope="col">资产</th>
              {data.assets.map((asset) => (
                <th key={asset.concept_key} scope="col">
                  {asset.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.matrix.map((row) => (
              <tr key={row.concept_key}>
                <th scope="row">{assetLabel(row.concept_key, titleByKey)}</th>
                {data.assets.map((asset) => {
                  const value = row.correlations[asset.concept_key];
                  return (
                    <td data-tone={correlationTone(value)} key={asset.concept_key}>
                      {matrixCorrelationLabel(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </MacroTableFrame>
      <div className="macro-assets-pair-columns">
        <CorrelationPairs label="正相关" pairs={positivePairs} titleByKey={titleByKey} />
        <CorrelationPairs label="负相关" pairs={negativePairs} titleByKey={titleByKey} />
        <Link className="macro-assets-detail-link" to="/macro/assets/correlation">
          打开相关性详情
        </Link>
      </div>
    </div>
  );
}

function CorrelationPairs({
  label,
  pairs,
  titleByKey,
}: {
  label: string;
  pairs: MacroAssetCorrelationPair[];
  titleByKey: Record<string, string>;
}) {
  return (
    <div className="macro-assets-pair-list">
      <h4>{label}</h4>
      {pairs.length ? (
        <ul>
          {pairs.map((pair) => (
            <li key={`${pair.left}:${pair.right}`}>
              <span>
                {assetLabel(pair.left, titleByKey)} / {assetLabel(pair.right, titleByKey)}
              </span>
              <b data-tone={correlationTone(pair.correlation)}>{signedCorrelationLabel(pair.correlation)}</b>
            </li>
          ))}
        </ul>
      ) : (
        <span>暂无</span>
      )}
    </div>
  );
}

function DailyBriefContent({ brief }: { brief: MacroDailyBrief | null }) {
  return (
    <div className="macro-daily-brief">
      <strong>{brief?.headline ?? "今日判断暂不可用"}</strong>
      <div className="macro-daily-brief-grid">
        {(brief?.blocks ?? []).map((block) => (
          <article className="macro-daily-brief-block" key={block.id}>
            <span>{block.stance}</span>
            <b>{block.title}</b>
            <p>{block.body}</p>
          </article>
        ))}
      </div>
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
    title: group.title,
    rows: rows.filter((row) => group.match(rowKey(row))),
  })).filter((group) => group.rows.length > 0);
}

function rowKey(row: MacroTableRowModel): string {
  return String(row.raw.row_id ?? row.raw.concept_key ?? row.id ?? "");
}

function cell(row: MacroTableRowModel, columnId: string): string {
  return row.cells[columnId]?.displayValue ?? "暂无";
}

function deltaTone(row: MacroTableRowModel): "up" | "down" | "flat" {
  const value = row.cells.delta_20d?.sortValue;
  if (typeof value !== "number") return "flat";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

function coverageLabel(brief: MacroDailyBrief | null): string {
  const quality = brief?.dataQuality;
  if (!quality) return "未知";
  const ratio = quality.historyCoverageRatio;
  if (typeof ratio === "number") {
    return `${Math.round(ratio * 100)}%`;
  }
  return quality.status;
}

function correlationMeta(data: MacroAssetCorrelationData | null, isFetching: boolean): string {
  if (isFetching) return "更新中";
  if (!data) return "暂无";
  return data.asof_date ? `截至 ${data.asof_date}` : data.window;
}

function errorLabel(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "请求失败";
}

function readableText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function sourceMeta(provenance: unknown): string {
  if (!provenance || typeof provenance !== "object") return "来源";
  const rows = (provenance as { rows?: unknown }).rows;
  if (!Array.isArray(rows)) return "来源";
  return `${rows.length} 个来源`;
}

type MacroDailyBriefQuality = {
  gapCount?: number;
  historyCoverageRatio?: number;
  latestCoverageRatio?: number;
  status: string;
};
