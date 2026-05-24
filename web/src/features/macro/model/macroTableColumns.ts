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
  const columns = columnModels(table);
  return {
    columns,
    rows: rows.map((row, rowIndex) => ({
      id: rowId(row, rowIndex),
      raw: row,
      cells: Object.fromEntries(
        columns.map((column) => [column.id, buildMacroTableCell(tableCell(row, column.id))]),
      ),
    })),
    tableId: tableId(table),
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
    return "暂无";
  }
  if (Array.isArray(value)) {
    return value.map(formatMacroTableValue).join(", ");
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "string") {
    return VALUE_LABELS[value] ?? value;
  }
  const display = displayValue(value);
  if (display !== null) {
    return display;
  }
  return "暂无";
}

function buildMacroTableCell(value: unknown): MacroTableCellModel {
  if (isDisplayCell(value)) {
    const sortValue = scalarValue(value.sort_value);
    const rawValue = sortValue ?? scalarValue(value.display_value);
    return {
      displayValue: formatMacroTableValue(value.display_value),
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
  return {
    displayValue: formatMacroTableValue(value),
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

function rowId(row: MacroSemanticRecord, rowIndex: number): string {
  const stable =
    stringValue(row.row_id) ??
    stringValue(row.concept_key) ??
    stringValue(row.symbol) ??
    stringValue(row.label) ??
    stringValue(row.id);
  return stable ? `${stable}:${rowIndex}` : `row:${rowIndex}`;
}

function tableCell(row: MacroSemanticRecord, columnId: string): unknown {
  const cells = row.cells;
  if (cells && typeof cells === "object" && !Array.isArray(cells)) {
    return (cells as Record<string, unknown>)[columnId];
  }
  return undefined;
}

function tableId(table: MacroModuleTable): string {
  return stringValue(table.id) ?? "unknown_table";
}

function displayValue(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  return (
    stringValue(record.display_value) ??
    stringValue(record.label) ??
    stringValue(record.title) ??
    null
  );
}

function isDisplayCell(
  value: unknown,
): value is { display_value?: unknown; sort_value?: unknown } {
  return Boolean(value && typeof value === "object" && !Array.isArray(value) && "display_value" in value);
}

const VALUE_LABELS: Record<string, string> = {
  degraded: "降级",
  missing: "缺失",
  ok: "正常",
  partial: "部分可用",
  unavailable: "不可用",
  unknown: "未知",
};

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
