import type { MacroModuleView, MacroSemanticRecord } from "@lib/types";

import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  macroReadSummary,
  type MacroDataHealthBucket,
  type MacroEvidenceGroup,
} from "./macroModulePresentation";
import { formatMacroScalar } from "./macroPageViewModel";

export type MacroWorkbenchBrief = {
  asOfLabel: string | null;
  rows: MacroWorkbenchBriefRow[];
  statusLabel: string | null;
  summary: string;
};

export type MacroWorkbenchBriefRow = {
  key: string;
  label: string;
  value: string;
};

export type MacroWorkbenchDiagnostics = {
  buckets: MacroDataHealthBucket[];
  sourceCount: number;
  sourceMeta: string;
  statusLabel: string | null;
};

export type MacroWorkbenchDrivers = {
  evidenceCount: number;
  evidenceGroups: MacroEvidenceGroup[];
  transmissionCount: number;
};

export function buildMacroWorkbenchBrief(module: MacroModuleView): MacroWorkbenchBrief {
  return {
    asOfLabel: stringValue(module.snapshot.asof_label) ?? stringValue(module.snapshot.asof_date),
    rows: BRIEF_FIELDS.map((field) => ({
      key: field.key,
      label: field.label,
      value: module.module_read[field.key],
    }))
      .filter((row) => hasMacroValue(row.value))
      .map((row) => ({
        ...row,
        value: formatMacroScalar(row.value),
      })),
    statusLabel: stringValue(module.snapshot.status_label) ?? stringValue(module.snapshot.status),
    summary: macroReadSummary(module),
  };
}

export function buildMacroWorkbenchDiagnostics(
  module: MacroModuleView,
  scope: "leaf" | "overview",
): MacroWorkbenchDiagnostics {
  const sourceCount = sourceRows(module.provenance).length;
  return {
    buckets: buildMacroDataHealthBuckets(module.data_health, scope),
    sourceCount,
    sourceMeta: sourceCount > 0 ? `${sourceCount} 个来源` : "来源待接入",
    statusLabel: stringValue(module.data_health.summary_label) ?? stringValue(module.data_health.summary_status),
  };
}

export function buildMacroWorkbenchDrivers(module: MacroModuleView): MacroWorkbenchDrivers {
  const evidenceGroups = buildMacroEvidenceGroups(module.module_evidence);
  return {
    evidenceCount: evidenceGroups.reduce((count, group) => count + group.items.length, 0),
    evidenceGroups,
    transmissionCount: module.transmission.length,
  };
}

function hasMacroValue(value: unknown): boolean {
  if (typeof value === "number" || typeof value === "boolean") {
    return true;
  }
  if (typeof value === "string") {
    return value.trim().length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return Boolean(value && typeof value === "object" && Object.keys(value).length > 0);
}

function sourceRows(source: MacroSemanticRecord): MacroSemanticRecord[] {
  return Array.isArray(source.rows)
    ? source.rows.filter((row): row is MacroSemanticRecord =>
        Boolean(row && typeof row === "object" && !Array.isArray(row)),
      )
    : [];
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

const BRIEF_FIELDS = [
  { key: "regime_label", label: "状态" },
  { key: "regime", label: "状态" },
  { key: "confidence_label", label: "规则覆盖" },
  { key: "crypto_read", label: "加密影响" },
  { key: "token_impact", label: "代币影响" },
  { key: "data_note", label: "数据说明" },
  { key: "methodology_note", label: "方法说明" },
] as const;
