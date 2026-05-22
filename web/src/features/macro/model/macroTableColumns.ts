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
  if (COLUMN_LABELS[key]) {
    return COLUMN_LABELS[key];
  }
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => WORD_LABELS[part] ?? part)
    .join(" ");
}

const COLUMN_LABELS: Record<string, string> = {
  basis: "基差",
  code: "代码",
  concept_key: "指标",
  degraded_reasons: "降级原因",
  field: "字段",
  funding_rate: "资金费率",
  id: "ID",
  label: "名称",
  latest: "最新值",
  open_interest_usd: "未平仓量(美元)",
  reason: "原因",
  status: "状态",
  symbol: "标的",
  unit: "单位",
  value: "值",
};

const WORD_LABELS: Record<string, string> = {
  asset: "资产",
  assets: "资产",
  chain: "链路",
  coinglass: "Coinglass",
  count: "数量",
  credit: "信用",
  curve: "曲线",
  days: "天数",
  fed: "美联储",
  flow: "流量",
  flows: "资金流",
  fx: "外汇",
  liquidity: "流动性",
  observed: "观测",
  percent: "百分比",
  rate: "利率",
  rates: "利率",
  real: "实际",
  return: "回报",
  returns: "回报",
  score: "分数",
  source: "数据源",
  sources: "数据源",
  transmission: "传导",
  usd: "美元",
  volatility: "波动率",
  yield: "收益率",
};

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
