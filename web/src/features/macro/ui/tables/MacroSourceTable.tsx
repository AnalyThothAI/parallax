import type { MacroSemanticRecord } from "@lib/types";

import { MacroTableFrame } from "./MacroTableFrame";
import "./macroTables.css";

type SourceColumnKey = "source" | "latest" | "quality" | "count" | "notes";

type SourceCell = {
  displayValue: string;
};

type SourceRow = {
  cells: Partial<Record<SourceColumnKey, SourceCell>>;
  id: string;
};

const SOURCE_COLUMNS: { key: SourceColumnKey; label: string }[] = [
  { key: "source", label: "来源" },
  { key: "latest", label: "最新观测" },
  { key: "quality", label: "新鲜度/质量/状态" },
  { key: "count", label: "指标数" },
  { key: "notes", label: "备注" },
];

export function MacroSourceTable({
  caption,
  source,
}: {
  caption: string;
  source: MacroSemanticRecord;
}) {
  const rows = sourceRows(source);
  if (rows.length === 0) {
    return null;
  }
  const columns = sourceColumns(rows);
  return (
    <MacroTableFrame caption={caption} minWidth={420} stickyFirstColumn>
      <table aria-label={caption} className="macro-data-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {columns.map((column) => (
                <td key={column.key}>{row.cells[column.key]?.displayValue ?? null}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </MacroTableFrame>
  );
}

function sourceRows(source: MacroSemanticRecord): SourceRow[] {
  const rows = Array.isArray(source.rows) ? source.rows : [];
  return rows
    .map((row) => (isRecord(row) ? sourceRow(row) : null))
    .filter((row): row is SourceRow => Boolean(row));
}

function sourceRow(row: MacroSemanticRecord): SourceRow | null {
  const id = stringValue(row.row_id);
  const source = sourceLabel(row);
  if (!id || !source) {
    return null;
  }
  const quality = qualityLabel(row);
  const latest = stringValue(row.latest_observed_at);
  const count = numberValue(row.concept_count);
  const notes = notesLabel(row);
  const cells: SourceRow["cells"] = {
    source: sourceCell(source),
  };
  if (latest) {
    cells.latest = sourceCell(latest);
  }
  if (quality) {
    cells.quality = sourceCell(quality);
  }
  if (count !== null) {
    cells.count = sourceCell(String(count));
  }
  if (notes) {
    cells.notes = sourceCell(notes);
  }
  if (!hasAuditCells(cells)) {
    return null;
  }
  return {
    id,
    cells,
  };
}

function sourceColumns(rows: SourceRow[]): typeof SOURCE_COLUMNS {
  return SOURCE_COLUMNS.filter(
    (column) => column.key === "source" || rows.some((row) => Boolean(row.cells[column.key])),
  );
}

function hasAuditCells(cells: SourceRow["cells"]): boolean {
  return SOURCE_COLUMNS.some((column) => column.key !== "source" && Boolean(cells[column.key]));
}

function sourceCell(displayValue: string) {
  return { displayValue };
}

function sourceLabel(row: MacroSemanticRecord): string | null {
  const raw = stringValue(row.source_label);
  if (!raw) {
    return null;
  }
  return looksInternalCode(raw) ? null : raw;
}

function statusLabel(row: MacroSemanticRecord): string | null {
  return stringValue(row.status_label);
}

function qualityLabel(row: MacroSemanticRecord): string | null {
  const freshness = stringValue(row.freshness_label);
  const quality = stringValue(row.quality_label);
  const status = statusLabel(row);
  return [freshness, quality, status].filter(Boolean).join(" / ") || null;
}

function notesLabel(row: MacroSemanticRecord): string | null {
  const notes = stringValue(row.notes);
  if (notes) {
    return displayText(notes);
  }
  return null;
}

function isRecord(value: unknown): value is MacroSemanticRecord {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function displayText(value: string | null): string | null {
  if (!value) {
    return null;
  }
  return looksInternalCode(value) ? null : value;
}

function looksInternalCode(value: string): boolean {
  return /^[a-z][a-z0-9_:.-]*$/.test(value);
}
