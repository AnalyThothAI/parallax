import type { MacroSectionBoard, MacroSemanticRecord } from "@lib/types";
import { Link } from "react-router-dom";

import { formatMacroScalar } from "../../model/macroPageViewModel";
import { macroRouteLabel } from "../../model/macroRoutes";
import { MacroMetricStrip } from "../primitives/MacroMetricStrip";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroTableFrame } from "../tables/MacroTableFrame";

import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import "./macroPages.css";

export function MacroModuleIndexPage({ module, moduleId }: MacroModulePageProps) {
  const boards = module.section_boards;
  const label = macroRouteLabel(moduleId);
  const tableCaption = `${label}模块目录`;

  return (
    <MacroPageScaffold label={`${label}模块索引`} pageKind="index">
      <MacroMetricStrip
        ariaLabel="模块索引状态"
        density="compact"
        metrics={moduleIndexMetrics(boards)}
      />
      <MacroPanel ariaLabel="模块目录" span="full" title={`${label}模块目录`}>
        {boards.length > 0 ? (
          <MacroTableFrame caption={tableCaption} minWidth={720} stickyFirstColumn>
            <table aria-label={tableCaption} className="macro-module-index-table">
              <caption>{tableCaption}</caption>
              <thead>
                <tr>
                  <th scope="col">模块</th>
                  <th scope="col">状态</th>
                  <th scope="col">核心代理</th>
                  <th scope="col">当前读数</th>
                  <th scope="col">入口</th>
                </tr>
              </thead>
              <tbody>
                {boards.map((board) => (
                  <ModuleIndexRow board={board} key={board.id} />
                ))}
              </tbody>
            </table>
          </MacroTableFrame>
        ) : (
          <div className="macro-module-index-empty" role="status">
            暂无模块目录
          </div>
        )}
      </MacroPanel>
    </MacroPageScaffold>
  );
}

function moduleIndexMetrics(boards: MacroSectionBoard[]) {
  const partialCount = boards.filter((board) => statusKey(board) === "partial").length;
  const missingCount = boards.filter((board) =>
    ["missing", "unknown"].includes(statusKey(board)),
  ).length;
  const readyCount = boards.filter((board) => ["ok", "ready"].includes(statusKey(board))).length;
  return [
    metric("coverage", "覆盖", `${boards.length} 个模块`),
    metric("ready", "可用", `${readyCount} 个可用`),
    metric("partial", "待确认", `${partialCount} 个待确认`),
    metric("missing", "待接入", `${missingCount} 个待接入`),
  ];
}

function metric(key: string, label: string, value: string) {
  return {
    key,
    label,
    observedAtLabel: null,
    quality: null,
    qualityLabel: null,
    shortLabel: label,
    unitLabel: null,
    value,
  };
}

function ModuleIndexRow({ board }: { board: MacroSectionBoard }) {
  return (
    <tr>
      <th scope="row">
        <span className="macro-module-index-module">{board.title}</span>
      </th>
      <td>
        <span className="macro-module-index-status" data-status={statusKey(board)}>
          {boardStatusLabel(board)}
        </span>
      </td>
      <td>{boardProxy(board)}</td>
      <td>{boardRead(board)}</td>
      <td>
        <Link className="macro-module-index-link" to={board.href}>
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
