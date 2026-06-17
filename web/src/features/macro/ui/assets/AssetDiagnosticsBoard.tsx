import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";
import { useMemo } from "react";

import type { AssetDiagnosticsSummary } from "../../model/macroAssetOverviewModel";
import { tableCaption } from "../../model/macroModulePageModel";
import type {
  MacroDataHealthBucket,
  MacroDataHealthBucketItem,
} from "../../model/macroModulePresentation";
import { buildMacroTableModel, type MacroTableRowModel } from "../../model/macroTableColumns";
import { MacroSourceTable } from "../tables/MacroSourceTable";
import { MacroTableFrame } from "../tables/MacroTableFrame";

import "./macroAssetOverview.css";

export function AssetDiagnosticsBoard({
  availabilityTable,
  buckets,
  provenance,
  summary,
}: {
  availabilityTable?: MacroModuleTable;
  buckets: MacroDataHealthBucket[];
  provenance: MacroSemanticRecord;
  summary: AssetDiagnosticsSummary;
}) {
  return (
    <div className="macro-assets-diagnostics">
      <dl className="macro-assets-diagnostics-summary">
        {summary.moduleStatus ? <SummaryItem label="状态" value={summary.moduleStatus} /> : null}
        <SummaryItem label="来源" value={String(summary.sourceCount)} />
        <SummaryItem label="缺口" value={String(summary.gapCount)} />
      </dl>
      <GapSection buckets={buckets} gapCount={summary.gapCount} />
      {summary.sourceCount > 0 ? (
        <details className="macro-assets-diagnostics-section">
          <summary>来源</summary>
          <MacroSourceTable caption="数据源" source={provenance} />
        </details>
      ) : null}
      {availabilityTable ? <AvailabilitySection table={availabilityTable} /> : null}
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function GapSection({ buckets, gapCount }: { buckets: MacroDataHealthBucket[]; gapCount: number }) {
  const visibleBuckets = buckets.filter(
    (bucket) => bucket.items.length > 0 || (bucket.referenceCount ?? 0) > 0,
  );
  if (gapCount <= 0 || visibleBuckets.length === 0) {
    return null;
  }
  return (
    <details className="macro-assets-diagnostics-section">
      <summary>缺口 {gapCount}</summary>
      <div className="macro-assets-health-buckets">
        {visibleBuckets.map((bucket) => (
          <div className="macro-assets-health-bucket" key={bucket.key}>
            <div className="macro-assets-health-bucket-head">
              <h4>{bucket.label}</h4>
              <span>{bucket.referenceCount ?? bucket.items.length}</span>
            </div>
            {bucket.referenceCount ? (
              <p className="macro-assets-health-reference">总览级缺口</p>
            ) : bucket.items.length > 0 ? (
              <GapList bucket={bucket} />
            ) : null}
          </div>
        ))}
      </div>
    </details>
  );
}

function GapList({ bucket }: { bucket: MacroDataHealthBucket }) {
  return (
    <ul className="macro-assets-health-gap-list">
      {bucket.items.map((item) => (
        <li data-severity={item.severity ?? undefined} key={`${bucket.key}:${item.key}`}>
          <b>{item.label}</b>
          {gapMeta(item) ? <span>{gapMeta(item)}</span> : null}
          {item.detail ? <small>{item.detail}</small> : null}
        </li>
      ))}
    </ul>
  );
}

function gapMeta(item: MacroDataHealthBucketItem): string | null {
  return [severityLabel(item.severity), scopeLabel(item.scope)].filter(Boolean).join(" · ") || null;
}

function severityLabel(severity: string | null): string | null {
  return (
    {
      critical: "严重",
      error: "错误",
      info: "提示",
      warning: "警告",
    }[severity ?? ""] ?? null
  );
}

function scopeLabel(scope: string | null): string | null {
  return (
    {
      chart_blocker: "图表阻断",
      global_reference: "总览参考",
      module_blocker: "模块阻断",
      module_reference: "模块参考",
    }[scope ?? ""] ?? null
  );
}

function AvailabilitySection({ table }: { table: MacroModuleTable }) {
  const model = useMemo(() => buildMacroTableModel(table), [table]);
  const rows = useMemo(() => availabilityRows(model.rows), [model.rows]);
  if (rows.length === 0) {
    return null;
  }
  return (
    <details className="macro-assets-diagnostics-section">
      <summary>覆盖</summary>
      <CompactAvailabilityTable rows={rows} table={table} />
    </details>
  );
}

type AvailabilityRow = {
  coverage: string | null;
  item: string;
  latest: string | null;
  notes: string | null;
  rowId: string;
  status: string | null;
};

function CompactAvailabilityTable({
  rows,
  table,
}: {
  rows: AvailabilityRow[];
  table: MacroModuleTable;
}) {
  const caption = tableCaption(table);
  if (!caption) {
    return null;
  }
  return (
    <MacroTableFrame caption={caption} minWidth={760} stickyFirstColumn>
      <table className="macro-assets-availability-table" aria-label={caption}>
        <caption>{caption}</caption>
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
            <tr key={row.rowId}>
              <th scope="row">{row.item}</th>
              <td>{row.status}</td>
              <td>{row.latest}</td>
              <td>{row.coverage}</td>
              <td>{row.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MacroTableFrame>
  );
}

function availabilityRows(rows: MacroTableRowModel[]): AvailabilityRow[] {
  return rows
    .map((row) => {
      const item = displayCell(row, "item");
      const status = displayCell(row, "status");
      const latest = displayCell(row, "latest");
      const coverage = displayCell(row, "coverage");
      const notes = displayCell(row, "notes");
      if (!item || ![status, latest, coverage, notes].some(Boolean)) {
        return null;
      }
      return {
        coverage,
        item,
        latest,
        notes,
        rowId: row.id,
        status,
      };
    })
    .filter((row): row is AvailabilityRow => Boolean(row))
    .slice(0, 12);
}

function displayCell(row: MacroTableRowModel, columnId: string): string | null {
  const value = row.cells[columnId]?.displayValue;
  if (!value || value === "暂无") {
    return null;
  }
  return value;
}
