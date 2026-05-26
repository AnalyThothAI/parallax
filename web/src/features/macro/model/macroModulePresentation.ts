import type {
  MacroDataHealth,
  MacroModuleTable,
  MacroModuleTile,
  MacroModuleView,
  MacroSemanticRecord,
} from "@lib/types";

import { emptyTable } from "./macroModulePageModel";
import { formatMacroScalar, gapLabel } from "./macroPageViewModel";

export type MacroMetricDisplay = {
  key: string;
  label: string;
  observedAtLabel: string | null;
  quality: string | null;
  qualityLabel: string | null;
  shortLabel: string | null;
  unitLabel: string | null;
  value: string;
};

export type MacroEvidenceGroup = {
  items: Array<{ detail: string; label: string }>;
  key: string;
  label: string;
};

export type MacroDataHealthBucket = {
  items: string[];
  key: string;
  label: string;
  referenceCount?: number;
};

const EVIDENCE_GROUPS = [
  { key: "confirmations", label: "确认" },
  { key: "contradictions", label: "反证" },
  { key: "watch_triggers", label: "观察触发" },
  { key: "invalidations", label: "失效条件" },
] as const;

type EvidenceGroupKey = (typeof EVIDENCE_GROUPS)[number]["key"];

export function buildMacroMetrics({ tiles }: { tiles: MacroModuleTile[] }): MacroMetricDisplay[] {
  return tiles.map((tile, index) => ({
    key: String(tile.concept_key ?? tile.label ?? `metric:${index}`),
    label: stringValue(tile.label) ?? stringValue(tile.short_label) ?? "未命名指标",
    observedAtLabel:
      stringValue(tile.observed_at_label) ??
      stringValue(tile.quality_label) ??
      stringValue(tile.delta_label),
    quality: stringValue(tile.quality),
    qualityLabel: stringValue(tile.quality_label),
    shortLabel:
      stringValue(tile.short_label) ??
      stringValue(tile.source_label) ??
      stringValue(tile.quality_label),
    unitLabel: stringValue(tile.unit_label),
    value: formatMacroScalar(tile.display_value ?? tile.value),
  }));
}

export function primarySupportingTable(module: MacroModuleView): MacroModuleTable {
  return module.tables[0] ?? emptyTable(`${module.snapshot.module_id ?? "macro"}_supporting_table`);
}

export function extraTables(module: MacroModuleView): MacroModuleTable[] {
  return module.tables.slice(1);
}

export function macroReadSummary(module: MacroModuleView): string {
  const read = module.module_read;
  return formatMacroScalar(
    read.headline || read.summary || read.regime_label || module.snapshot.status || "暂无",
  );
}

export function buildMacroEvidenceGroups(
  evidence: MacroModuleView["module_evidence"],
): MacroEvidenceGroup[] {
  return EVIDENCE_GROUPS.map((group) => ({
    ...group,
    items: evidenceItemsForGroup(evidence, group.key),
  }));
}

export function buildMacroDataHealthBuckets(
  dataHealth: MacroDataHealth,
  scope: "leaf" | "overview",
): MacroDataHealthBucket[] {
  return [
    {
      key: "module_gaps",
      label: "模块缺口",
      items: (dataHealth.module_gaps ?? [])
        .map(gapLabel)
        .filter((label) => label !== "数据缺口待确认"),
    },
    {
      key: "chart_gaps",
      label: "图表缺口",
      items: (dataHealth.chart_gaps ?? [])
        .map(gapLabel)
        .filter((label) => label !== "数据缺口待确认"),
    },
    {
      key: "global_gaps",
      label: scope === "leaf" ? "全局缺口（总览级参考）" : "全局缺口",
      items:
        scope === "overview"
          ? (dataHealth.global_gaps ?? [])
              .map(gapLabel)
              .filter((label) => label !== "数据缺口待确认")
          : [],
      referenceCount: scope === "leaf" ? (dataHealth.global_gaps ?? []).length : undefined,
    },
    {
      key: "future_integration_gaps",
      label: "未来集成缺口",
      items: (dataHealth.future_integration_gaps ?? [])
        .map(gapLabel)
        .filter((label) => label !== "数据缺口待确认"),
    },
  ];
}

function evidenceItemsForGroup(
  evidence: MacroModuleView["module_evidence"],
  key: EvidenceGroupKey,
): Array<{ detail: string; label: string }> {
  const items = evidence[key];
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) =>
      item && typeof item === "object"
        ? {
            detail: formatMacroScalar((item as MacroSemanticRecord).description),
            label: formatMacroScalar((item as MacroSemanticRecord).label),
          }
        : null,
    )
    .filter((item): item is { detail: string; label: string } =>
      Boolean(item && item.label !== "暂无"),
    );
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
