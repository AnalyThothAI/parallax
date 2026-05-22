import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";

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
  const rows = Array.isArray(table.rows) ? table.rows : [];
  const columnIds = orderedColumnIds(rows);
  return {
    columns: columnIds.map((id) => ({ id, label: labelFromKey(id) })),
    rows: rows.map((row, rowIndex) => ({
      id: rowId(row, rowIndex),
      raw: row,
      cells: Object.fromEntries(
        columnIds.map((columnId) => [columnId, buildMacroTableCell(row[columnId])]),
      ),
    })),
    tableId: table.table_id,
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

export function formatMacroTableValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (Array.isArray(value)) {
    return value.map(formatMacroTableValue).join(", ");
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function buildMacroTableCell(value: unknown): MacroTableCellModel {
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
  return {
    displayValue: formatMacroTableValue(value),
    isNumeric: false,
    rawValue: scalar,
    sortValue: scalar,
  };
}

function orderedColumnIds(rows: MacroSemanticRecord[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key);
      }
    }
  }
  return [...seen];
}

function rowId(row: MacroSemanticRecord, rowIndex: number): string {
  const stable =
    stringValue(row.concept_key) ??
    stringValue(row.symbol) ??
    stringValue(row.label) ??
    stringValue(row.id);
  return stable ? `${stable}:${rowIndex}` : `row:${rowIndex}`;
}

function labelFromKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
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
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(value);
}
