import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";

import { requireMacroArray } from "./macroCurrentContract";

export type MacroTableSortDirection = "asc" | "desc";

export type MacroTableColumnModel = {
  id: string;
  label: string;
};

export type MacroTableCellModel = {
  displayValue: string;
  isNumeric: boolean;
  rawValue: number | string | boolean | null;
  sortValue: number | string | boolean | null;
};

export type MacroTableRowModel = {
  cells: Record<string, MacroTableCellModel | undefined>;
  id: string;
  raw: MacroSemanticRecord;
};

export type MacroTableModel = {
  columns: MacroTableColumnModel[];
  rows: MacroTableRowModel[];
  tableId: string;
};

export function buildMacroTableModel(table: MacroModuleTable): MacroTableModel {
  const id = tableId(table);
  if (!id) {
    return { columns: [], rows: [], tableId: "" };
  }
  const rows = requireMacroArray<MacroSemanticRecord>(table.rows, `tables.${id}.rows`);
  const candidateColumns = columnModels(table);
  const candidateRows = rows.reduce<MacroTableRowModel[]>((accumulator, row) => {
    const id = rowId(row);
    if (!id) {
      return accumulator;
    }
    const cells = Object.fromEntries(
      candidateColumns
        .map((column) => {
          const cell = buildMacroTableCell(tableCell(row, column.id));
          return cell ? ([column.id, cell] as const) : null;
        })
        .filter((entry): entry is readonly [string, MacroTableCellModel] => entry !== null),
    );
    if (Object.keys(cells).length > 0) {
      accumulator.push({ id, raw: row, cells });
    }
    return accumulator;
  }, []);
  const columns = candidateColumns.filter((column) =>
    candidateRows.some((row) => Boolean(row.cells[column.id])),
  );
  return {
    columns,
    rows: candidateRows,
    tableId: id,
  };
}

export function sortMacroTableRows(
  rows: MacroTableRowModel[],
  columnId: string,
  direction: MacroTableSortDirection,
): MacroTableRowModel[] {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const leftValue = left.cells[columnId]?.sortValue ?? null;
    const rightValue = right.cells[columnId]?.sortValue ?? null;
    if (isMissingSortValue(leftValue)) {
      return isMissingSortValue(rightValue) ? 0 : 1;
    }
    if (isMissingSortValue(rightValue)) {
      return -1;
    }
    return compareMacroTableSortValues(leftValue, rightValue) * multiplier;
  });
}

export function compareMacroTableSortValues(left: unknown, right: unknown): number {
  if (left === null || left === undefined) {
    return right === null || right === undefined ? 0 : 1;
  }
  if (right === null || right === undefined) {
    return -1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left).localeCompare(String(right));
}

export function formatMacroTableValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (Array.isArray(value)) {
    const labels = value.map(formatMacroTableValue).filter((item): item is string => Boolean(item));
    return labels.length > 0 ? labels.join(", ") : null;
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "string") {
    const text = value.trim();
    return text;
  }
  const display = displayValue(value);
  if (display !== null) {
    return display;
  }
  return null;
}

function buildMacroTableCell(value: unknown): MacroTableCellModel | null {
  if (isDisplayCell(value)) {
    const displayValue = formatMacroTableValue(value.display_value);
    if (!displayValue) {
      return null;
    }
    const sortValue = scalarValue(value.sort_value);
    const rawValue = sortValue;
    return {
      displayValue,
      isNumeric: typeof sortValue === "number",
      rawValue,
      sortValue,
    };
  }
  const numeric = numericValue(value);
  if (numeric !== null) {
    return {
      displayValue: formatNumber(numeric),
      isNumeric: true,
      rawValue: numeric,
      sortValue: numeric,
    };
  }
  const scalar = scalarValue(value);
  const displayValue = formatMacroTableValue(value);
  if (!displayValue) {
    return null;
  }
  return {
    displayValue,
    isNumeric: false,
    rawValue: scalar,
    sortValue: scalar,
  };
}

function columnModels(table: MacroModuleTable): MacroTableColumnModel[] {
  const columns = Array.isArray(table.columns) ? table.columns : [];
  return columns
    .map((column) => {
      if (!column || typeof column !== "object") {
        return null;
      }
      const record = column as Record<string, unknown>;
      const id = stringValue(record.key);
      const label = stringValue(record.label);
      if (!id || !label) {
        return null;
      }
      return { id, label };
    })
    .filter((column): column is MacroTableColumnModel => Boolean(column));
}

function rowId(row: MacroSemanticRecord): string | null {
  return stringValue(row.row_id);
}

function tableCell(row: MacroSemanticRecord, columnId: string): unknown {
  const cells = row.cells;
  if (cells && typeof cells === "object" && !Array.isArray(cells)) {
    return (cells as Record<string, unknown>)[columnId];
  }
  return undefined;
}

function tableId(table: MacroModuleTable): string | null {
  return stringValue(table.id);
}

function displayValue(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  return stringValue(record.display_value);
}

function isDisplayCell(value: unknown): value is { display_value?: unknown; sort_value?: unknown } {
  return Boolean(
    value && typeof value === "object" && !Array.isArray(value) && "display_value" in value,
  );
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function scalarValue(value: unknown): number | string | boolean | null {
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  return null;
}

function isMissingSortValue(value: unknown): boolean {
  return value === null || value === undefined;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function formatNumber(value: number): string {
  const maximumFractionDigits = Math.abs(value) > 0 && Math.abs(value) < 1 ? 6 : 2;
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(value);
}
