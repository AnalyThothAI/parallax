import type {
  MacroDataHealth,
  MacroModuleTable,
  MacroModuleTile,
  MacroModuleView,
  MacroSemanticRecord,
} from "@lib/types";

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
  items: Array<{ detail: string; key: string; label: string }>;
  key: string;
  label: string;
};

export type MacroDataHealthBucket = {
  items: MacroDataHealthBucketItem[];
  key: string;
  label: string;
  referenceCount?: number;
};

export type MacroDataHealthBucketItem = {
  detail: string | null;
  key: string;
  label: string;
  scope: string | null;
  severity: string | null;
};

const EVIDENCE_GROUPS = [
  { key: "confirmations", label: "确认" },
  { key: "contradictions", label: "反证" },
  { key: "watch_triggers", label: "观察触发" },
  { key: "invalidations", label: "失效条件" },
] as const;

type EvidenceGroupKey = (typeof EVIDENCE_GROUPS)[number]["key"];

export function buildMacroMetrics({ tiles }: { tiles: MacroModuleTile[] }): MacroMetricDisplay[] {
  return tiles
    .map((tile) => metricDisplay(tile))
    .filter((metric): metric is MacroMetricDisplay => metric !== null);
}

export function primarySupportingTable(module: MacroModuleView): MacroModuleTable | null {
  return module.tables[0] ?? null;
}

export function extraTables(module: MacroModuleView): MacroModuleTable[] {
  return module.tables.slice(1);
}

export function macroReadSummary(module: MacroModuleView): string | null {
  const read = module.module_read;
  for (const value of [read.headline, read.summary]) {
    const summary = summaryValue(value);
    if (summary) {
      return summary;
    }
  }
  return null;
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
      items: gapItems(dataHealth.module_gaps ?? []),
    },
    {
      key: "chart_gaps",
      label: "图表缺口",
      items: gapItems(dataHealth.chart_gaps ?? []),
    },
    {
      key: "global_gaps",
      label: scope === "leaf" ? "全局缺口（总览级参考）" : "全局缺口",
      items: scope === "overview" ? gapItems(dataHealth.global_gaps ?? []) : [],
      referenceCount: scope === "leaf" ? (dataHealth.global_gaps ?? []).length : undefined,
    },
  ];
}

function gapItems(gaps: unknown[]): MacroDataHealthBucketItem[] {
  return gaps
    .map((gap) => gapItem(gap))
    .filter((item): item is MacroDataHealthBucketItem => item !== null);
}

function gapItem(gap: unknown): MacroDataHealthBucketItem | null {
  if (!gap || typeof gap !== "object" || Array.isArray(gap)) {
    return null;
  }
  const record = gap as Record<string, unknown>;
  const key = stringValue(record.code);
  const label = gapLabel(record);
  if (!key || !label) {
    return null;
  }
  return {
    detail: stringValue(record.remediation_hint),
    key,
    label,
    scope: stringValue(record.scope),
    severity: stringValue(record.severity),
  };
}

function evidenceItemsForGroup(
  evidence: MacroModuleView["module_evidence"],
  key: EvidenceGroupKey,
): Array<{ detail: string; key: string; label: string }> {
  const items = evidence[key];
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => (item && typeof item === "object" ? evidenceItem(item) : null))
    .filter((item): item is { detail: string; key: string; label: string } => item !== null);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function summaryValue(value: unknown): string | null {
  return formattedScalarValue(value);
}

function metricDisplay(tile: MacroModuleTile): MacroMetricDisplay | null {
  const key = stringValue(tile.concept_key);
  const label = stringValue(tile.label);
  const value = formattedScalarValue(tile.display_value);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    observedAtLabel: stringValue(tile.observed_at_label),
    quality: stringValue(tile.quality),
    qualityLabel: stringValue(tile.quality_label),
    shortLabel: stringValue(tile.short_label),
    unitLabel: stringValue(tile.unit_label),
    value,
  };
}

function evidenceItem(
  item: MacroSemanticRecord,
): { detail: string; key: string; label: string } | null {
  const key = stringValue(item.code);
  const label = formattedScalarValue(item.label);
  const detail = formattedScalarValue(item.evidence_label);
  if (!key || !label || !detail) {
    return null;
  }
  return { detail, key, label };
}

function formattedScalarValue(value: unknown): string | null {
  return formatMacroScalar(value);
}
