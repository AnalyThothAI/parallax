import type { MacroSectionBoard, MacroSemanticRecord } from "@lib/types";
import { Link } from "react-router-dom";

import { formatMacroScalar } from "../../model/macroPageViewModel";

import type { MacroModulePageProps } from "./MacroModulePageFrame";
import "./macroPages.css";

export function MacroAssetsLandingPage({ module }: MacroModulePageProps) {
  return (
    <section aria-label="大类资产索引" className="macro-assets-index">
      {module.section_boards.length > 0 ? (
        module.section_boards.map((board) => <AssetIndexBoard board={board} key={board.id} />)
      ) : (
        <div className="macro-assets-index-empty" role="status">
          暂无资产索引
        </div>
      )}
    </section>
  );
}

function AssetIndexBoard({ board }: { board: MacroSectionBoard }) {
  const headingId = `macro-assets-index-${board.id}`;
  return (
    <section aria-labelledby={headingId} className="macro-assets-index-board">
      <div className="macro-assets-index-board-head">
        <h2 id={headingId}>{board.title}</h2>
        <span>{boardStatusLabel(board)}</span>
      </div>
      <CompactRows rows={board.rows} />
      <Link className="macro-assets-index-link" to={board.href}>
        查看{board.title}
      </Link>
    </section>
  );
}

function CompactRows({ rows }: { rows: MacroSemanticRecord[] }) {
  if (rows.length === 0) {
    return <div className="macro-assets-index-row-empty">暂无索引行</div>;
  }
  return (
    <dl className="macro-assets-index-rows">
      {rows.map((row, index) => (
        <div className="macro-assets-index-row" key={rowKey(row, index)}>
          <dt>{rowLabel(row)}</dt>
          <dd>{rowValue(row)}</dd>
        </div>
      ))}
    </dl>
  );
}

function boardStatusLabel(board: MacroSectionBoard): string {
  if (hasText(board.status_label)) {
    return board.status_label;
  }
  return formatMacroScalar(board.status ?? "unknown");
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

function rowKey(row: MacroSemanticRecord, index: number): string {
  return `${String(row.id ?? row.label ?? row.title ?? "row")}:${index}`;
}

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}
