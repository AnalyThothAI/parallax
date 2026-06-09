import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";
import { useMemo } from "react";

import type { AssetDiagnosticsSummary } from "../../model/macroAssetOverviewModel";
import { tableCaption } from "../../model/macroModulePageModel";
import type { MacroDataHealthBucket } from "../../model/macroModulePresentation";
import { buildMacroTableModel } from "../../model/macroTableColumns";
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
        <SummaryItem label="状态" value={summary.moduleStatus} />
        <SummaryItem label="来源" value={String(summary.sourceCount)} />
        <SummaryItem label="缺口" value={String(summary.gapCount)} />
      </dl>
      <GapSection buckets={buckets} gapCount={summary.gapCount} />
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

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function GapSection({
  buckets,
  gapCount,
}: {
  buckets: MacroDataHealthBucket[];
  gapCount: number;
}) {
  return (
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
              <th scope="row">{row.cells.item?.displayValue ?? "暂无"}</th>
              <td>{row.cells.status?.displayValue ?? "暂无"}</td>
              <td>{row.cells.latest?.displayValue ?? "暂无"}</td>
              <td>{row.cells.coverage?.displayValue ?? "暂无"}</td>
              <td>{row.cells.notes?.displayValue ?? "暂无"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MacroTableFrame>
  );
}
