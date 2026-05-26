import type { MacroSectionBoard, MacroSemanticRecord } from "@lib/types";
import { Link } from "react-router-dom";

import { formatMacroScalar } from "../../model/macroPageViewModel";

import type { MacroModulePageProps } from "./MacroModulePageFrame";
import "./MacroAssetsLandingPage.css";

export function MacroAssetsLandingPage({ module }: MacroModulePageProps) {
  const boards = module.section_boards;
  return (
    <section aria-label="大类资产索引" className="macro-assets-index">
      {boards.length > 0 ? (
        <>
          <AssetIndexSummary boards={boards} />
          <div className="macro-assets-index-matrix-wrap">
            <table aria-label="大类资产矩阵" className="macro-assets-index-matrix">
              <thead>
                <tr>
                  <th scope="col">板块</th>
                  <th scope="col">状态</th>
                  <th scope="col">核心代理</th>
                  <th scope="col">当前读数</th>
                  <th scope="col">入口</th>
                </tr>
              </thead>
              <tbody>
                {boards.map((board) => (
                  <AssetIndexRow board={board} key={board.id} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="macro-assets-index-empty" role="status">
          暂无资产索引
        </div>
      )}
    </section>
  );
}

function AssetIndexSummary({ boards }: { boards: MacroSectionBoard[] }) {
  const partialCount = boards.filter((board) => statusKey(board) === "partial").length;
  const missingCount = boards.filter((board) =>
    ["missing", "unknown"].includes(statusKey(board)),
  ).length;
  const readyCount = boards.filter((board) => statusKey(board) === "ok").length;
  return (
    <div aria-label="资产索引状态" className="macro-assets-index-summary">
      <SummaryMetric label="覆盖" value={`${boards.length} 个板块`} />
      <SummaryMetric label="可用" value={`${readyCount} 个可用`} />
      <SummaryMetric label="待确认" value={`${partialCount} 个待确认`} />
      <SummaryMetric label="待接入" value={`${missingCount} 个待接入`} />
    </div>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="macro-assets-index-summary-item">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function AssetIndexRow({ board }: { board: MacroSectionBoard }) {
  return (
    <tr>
      <th scope="row">
        <span className="macro-assets-index-asset">{board.title}</span>
      </th>
      <td>
        <span className="macro-assets-index-status" data-status={statusKey(board)}>
          {boardStatusLabel(board)}
        </span>
      </td>
      <td>{boardProxy(board)}</td>
      <td>{boardRead(board)}</td>
      <td>
        <Link className="macro-assets-index-link" to={board.href}>
          查看{board.title}
        </Link>
      </td>
    </tr>
  );
}

function boardStatusLabel(board: MacroSectionBoard): string {
  if (hasText(board.status_label)) {
    return board.status_label;
  }
  return formatMacroScalar(board.status ?? "unknown");
}

function statusKey(board: MacroSectionBoard): string {
  return hasText(board.status) ? board.status : "unknown";
}

function boardProxy(board: MacroSectionBoard): string {
  const explicitProxy = rowValueByLabel(board.rows, "代理");
  if (explicitProxy) {
    return explicitProxy;
  }
  const proxyLabels = board.rows.map(rowShortLabel).filter(hasText);
  return compactList(proxyLabels, 4) ?? "等待代理";
}

function boardRead(board: MacroSectionBoard): string {
  const explicitRead =
    rowValueByLabel(board.rows, "状态") ??
    rowValueByLabel(board.rows, "读数") ??
    rowValueByLabel(board.rows, "判断");
  if (explicitRead) {
    return explicitRead;
  }

  const readings = board.rows
    .filter((row) => rowStatus(row) !== "missing")
    .map((row) => {
      const value = rowMetricValue(row);
      return value ? `${rowShortLabel(row)} ${value}` : null;
    })
    .filter(hasText);

  if (readings.length > 0) {
    return compactList(readings, 2) ?? "等待数据确认";
  }

  const missingCount = board.rows.filter((row) => rowStatus(row) === "missing").length;
  return missingCount > 0 ? `缺失 ${missingCount}/${board.rows.length}` : "等待数据确认";
}

function rowValueByLabel(rows: MacroSemanticRecord[], label: string): string | null {
  const row = rows.find((item) => rowLabel(item) === label);
  return row ? rowValue(row) : null;
}

function compactList(values: string[], limit: number): string | null {
  const visible = values.slice(0, limit);
  if (visible.length === 0) {
    return null;
  }
  const extraCount = values.length - visible.length;
  return extraCount > 0 ? `${visible.join(" / ")} / +${extraCount}` : visible.join(" / ");
}

function rowShortLabel(row: MacroSemanticRecord): string {
  if (hasText(row.short_label)) {
    return row.short_label;
  }
  if (hasText(row.label)) {
    return row.label;
  }
  if (hasText(row.title)) {
    return row.title;
  }
  if (hasText(row.concept_key)) {
    return row.concept_key.split(":").at(-1)?.toUpperCase() ?? row.concept_key;
  }
  return "代理";
}

function rowLabel(row: MacroSemanticRecord): string {
  if (hasText(row.label)) {
    return row.label;
  }
  if (hasText(row.title)) {
    return row.title;
  }
  return "指标";
}

function rowValue(row: MacroSemanticRecord): string {
  const value = row.display_value ?? row.value ?? row.status_label ?? row.status ?? row.description;
  return formatMacroScalar(value);
}

function rowMetricValue(row: MacroSemanticRecord): string | null {
  const value = row.display_value ?? row.value;
  const formatted = formatMacroScalar(value);
  return formatted === "暂无" ? null : formatted;
}

function rowStatus(row: MacroSemanticRecord): string {
  return hasText(row.status) ? row.status : "unknown";
}

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}
