import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";

import {
  ASSET_GROUPS,
  type AssetDiagnosticsSummary,
  type AssetMarketGroup,
  type AssetMarketRow,
  type MacroDailyBrief,
  type MacroDailyBriefBlock,
  type MacroDailyBriefQuality,
} from "./macroAssetOverviewTypes";
import type { MacroDataHealthBucket } from "./macroModulePresentation";
import { buildMacroTableModel, type MacroTableRowModel } from "./macroTableColumns";

export type {
  AssetDiagnosticsSummary,
  AssetMarketGroup,
  AssetMarketRow,
  MacroDailyBrief,
  MacroDailyBriefBlock,
} from "./macroAssetOverviewTypes";

export function buildAssetMarketGroups(table: MacroModuleTable): AssetMarketGroup[] {
  const model = buildMacroTableModel(table);
  return ASSET_GROUPS.map((group) => ({
    key: group.key,
    route: group.route,
    rows: model.rows.filter((row) => group.match(rowKey(row))).map(assetMarketRow),
    title: group.title,
  }));
}

export function buildAssetDiagnosticsSummary({
  buckets,
  moduleStatus,
  provenance,
}: {
  buckets: MacroDataHealthBucket[];
  moduleStatus: string;
  provenance: MacroSemanticRecord;
}): AssetDiagnosticsSummary {
  return {
    gapCount: buckets.reduce(
      (count, bucket) => count + bucket.items.length + (bucket.referenceCount ?? 0),
      0,
    ),
    moduleStatus,
    sourceCount: sourceRows(provenance),
  };
}

export function normalizeDailyBrief(value: unknown): MacroDailyBrief | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const blocks = Array.isArray(record.blocks)
    ? record.blocks.flatMap((block) => normalizeDailyBriefBlock(block))
    : [];
  return {
    blocks,
    dataQuality: normalizeDailyBriefQuality(record.data_quality),
    headline: String(record.headline ?? "今日判断暂不可用"),
    status: String(record.status ?? "unknown"),
  };
}

function assetMarketRow(row: MacroTableRowModel): AssetMarketRow {
  return {
    delta: dayDelta(row),
    deltaTone: deltaTone(row),
    id: row.id,
    latest: cell(row, "latest"),
    name: cell(row, "indicator"),
    quality: qualityLabel(row),
    symbol: assetSymbol(row),
  };
}

function normalizeDailyBriefBlock(value: unknown): MacroDailyBriefBlock[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  const id = String(record.id ?? "").trim();
  const title = String(record.title ?? "").trim();
  const body = String(record.body ?? "").trim();
  if (!id || !title || !body) return [];
  return [
    {
      body,
      id,
      stance: String(record.stance ?? "neutral"),
      title,
    },
  ];
}

function normalizeDailyBriefQuality(value: unknown): MacroDailyBriefQuality | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  return {
    gapCount: numberValue(record.gap_count),
    historyCoverageRatio: numberValue(record.history_coverage_ratio),
    latestCoverageRatio: numberValue(record.latest_coverage_ratio),
    status: String(record.status ?? "unknown"),
  };
}

function rowKey(row: MacroTableRowModel): string {
  return String(row.raw.row_id ?? row.raw.concept_key ?? row.id ?? "").toLowerCase();
}

function cell(row: MacroTableRowModel, columnId: string): string {
  return row.cells[columnId]?.displayValue ?? "暂无";
}

function assetSymbol(row: MacroTableRowModel): string {
  const symbol = row.cells.symbol?.displayValue;
  if (symbol && symbol !== "暂无") return symbol;
  const rawSymbol = stringValue(row.raw.symbol) ?? stringValue(row.raw.ticker);
  if (rawSymbol) return rawSymbol;
  const key = rowKey(row);
  const suffix = key.split(":").at(-1);
  return suffix ? suffix.toUpperCase() : "暂无";
}

function dayDelta(row: MacroTableRowModel): string {
  const oneDay = row.cells.delta_1d?.displayValue;
  if (oneDay && oneDay !== "暂无") return oneDay;
  return row.cells.delta_20d?.displayValue ?? "暂无";
}

function qualityLabel(row: MacroTableRowModel): string {
  const quality = row.cells.quality?.displayValue;
  const source = row.cells.source?.displayValue;
  if (quality && quality !== "暂无" && source && source !== "暂无" && quality !== source) {
    return `${quality} · ${source}`;
  }
  if (quality && quality !== "暂无") return quality;
  if (source && source !== "暂无") return source;
  return "待确认";
}

function deltaTone(row: MacroTableRowModel): "up" | "down" | "flat" {
  const value = row.cells.delta_1d?.sortValue ?? row.cells.delta_20d?.sortValue;
  if (typeof value !== "number") return "flat";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

function sourceRows(provenance: MacroSemanticRecord): number {
  const rows = provenance.rows;
  return Array.isArray(rows) ? rows.length : 0;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}
