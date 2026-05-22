import type { MacroSemanticRecord } from "@lib/types";
import { useMemo } from "react";

import { buildMacroHeatmapMatrix } from "../../model/macroChartModel";
import "./macroCharts.css";

export function MacroHeatmap({
  caption,
  rows,
}: {
  caption: string;
  rows: MacroSemanticRecord[];
}) {
  const matrix = useMemo(() => buildMacroHeatmapMatrix(rows), [rows]);
  if (matrix.rows.length === 0) {
    return (
      <div aria-label={`${caption} state`} className="macro-chart-state-panel" role="status">
        heatmap_rows_missing
      </div>
    );
  }
  return (
    <div className="macro-heatmap-wrap">
      <table aria-label={caption} className="macro-heatmap-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col" />
            {matrix.columns.map((column) => (
              <th key={column.key} scope="col">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              {row.cells.map((cell) => (
                <td data-value={cell.rawValue ?? ""} key={cell.columnKey}>
                  {cell.label}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
