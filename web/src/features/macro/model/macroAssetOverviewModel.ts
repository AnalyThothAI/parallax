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

export function buildAssetMarketGroups(table: MacroModuleTable | null): AssetMarketGroup[] {
  if (!table) {
    return [];
  }
  const model = buildMacroTableModel(table);
  return ASSET_GROUPS.map((group) => {
    const rows = model.rows
      .filter((row) => group.match(rowKey(row)))
      .flatMap((row) => {
        const assetRow = assetMarketRow(row);
        return assetRow ? [assetRow] : [];
      });
    return {
      key: group.key,
      route: group.route,
      rows,
      title: group.title,
    };
  }).filter((group) => group.rows.length > 0);
}

export function buildAssetDiagnosticsSummary({
  buckets,
  moduleStatus,
  provenance,
}: {
  buckets: MacroDataHealthBucket[];
  moduleStatus: string | null;
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
  const headline = stringValue(record.headline);
  const status = stringValue(record.status);
  if (!headline || !status) {
    return null;
  }
  const blocks = Array.isArray(record.blocks)
    ? record.blocks.flatMap((block) => normalizeDailyBriefBlock(block))
    : [];
  return {
    blocks,
    dataQuality: normalizeDailyBriefQuality(record.data_quality),
    headline,
    status,
  };
}

function assetMarketRow(row: MacroTableRowModel): AssetMarketRow | null {
  const latest = displayCell(row, "latest");
  const name = displayCell(row, "indicator");
  const symbol = assetSymbol(row);
  if (!latest || !name || !symbol) {
    return null;
  }
  return {
    asOf: asOfLabel(row),
    delta: dayDelta(row),
    deltaTone: deltaTone(row),
    id: row.id,
    latest,
    name,
    quality: qualityLabel(row),
    symbol,
  };
}

function normalizeDailyBriefBlock(value: unknown): MacroDailyBriefBlock[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  const id = String(record.id ?? "").trim();
  const title = String(record.title ?? "").trim();
  const body = String(record.body ?? "").trim();
  const stance = stringValue(record.stance);
  if (!id || !title || !body || !stance) return [];
  return [
    {
      body,
      id,
      stance,
      title,
    },
  ];
}

function normalizeDailyBriefQuality(value: unknown): MacroDailyBriefQuality | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const status = stringValue(record.status);
  if (!status) {
    return undefined;
  }
  return {
    gapCount: numberValue(record.gap_count),
    historyCoverageRatio: numberValue(record.history_coverage_ratio),
    latestCoverageRatio: numberValue(record.latest_coverage_ratio),
    status,
  };
}

function rowKey(row: MacroTableRowModel): string {
  return String(row.raw.row_id ?? row.raw.concept_key ?? row.id ?? "").toLowerCase();
}

function displayCell(row: MacroTableRowModel, columnId: string): string | null {
  const value = row.cells[columnId]?.displayValue;
  if (!value || value === "暂无") {
    return null;
  }
  return value;
}

function assetSymbol(row: MacroTableRowModel): string | null {
  const symbol = row.cells.symbol?.displayValue;
  if (symbol && symbol !== "暂无") return symbol;
  const rawSymbol = stringValue(row.raw.symbol) ?? stringValue(row.raw.ticker);
  if (rawSymbol) return rawSymbol;
  return null;
}

function dayDelta(row: MacroTableRowModel): string | null {
  return displayCell(row, "delta_1d") ?? displayCell(row, "delta_20d");
}

function asOfLabel(row: MacroTableRowModel): string | null {
  return (
    firstDisplayCell(row, ["observed_at", "latest_observed_at", "date", "asof_date"]) ??
    stringValue(row.raw.latest_observed_at) ??
    stringValue(row.raw.observed_at) ??
    stringValue(row.raw.date)
  );
}

function firstDisplayCell(row: MacroTableRowModel, columnIds: string[]): string | null {
  for (const columnId of columnIds) {
    const value = row.cells[columnId]?.displayValue;
    if (value && value !== "暂无") return value;
  }
  return null;
}

function qualityLabel(row: MacroTableRowModel): string | null {
  const quality = row.cells.quality?.displayValue;
  const source = row.cells.source?.displayValue;
  if (quality && quality !== "暂无" && source && source !== "暂无" && quality !== source) {
    return `${quality} · ${source}`;
  }
  if (quality && quality !== "暂无") return quality;
  if (source && source !== "暂无") return source;
  return null;
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
