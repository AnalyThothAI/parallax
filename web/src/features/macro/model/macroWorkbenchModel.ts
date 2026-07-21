import type { MacroModuleView, MacroSemanticRecord } from "@lib/types";

import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  macroReadSummary,
  type MacroDataHealthBucket,
  type MacroEvidenceGroup,
} from "./macroModulePresentation";
import { formatMacroScalar, macroStatusLabel } from "./macroPageViewModel";

export type MacroWorkbenchBrief = {
  asOfLabel: string | null;
  rows: MacroWorkbenchBriefRow[];
  statusLabel: string | null;
  summary: string | null;
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

export type MacroStructuredAnalysis = {
  key: string;
  label: string;
  rows: MacroStructuredAnalysisRow[];
};

export type MacroStructuredAnalysisRow = {
  evidence: string[];
  fact: string;
  invalidation: string;
  key: string;
  label: string;
  regimeLabel: string | null;
  trade: string;
};

export type MacroMarketEventFlow = {
  key: string;
  label: string;
  rows: MacroMarketEventFlowItem[];
};

export type MacroMarketEventFlowItem = {
  categoryLabel: string | null;
  date: string;
  detail: string;
  impactLabel: string | null;
  key: string;
  label: string;
  meta: string | null;
  severityLabel: string | null;
  sourceUrl: string | null;
  watch: string;
};

export type MacroDecisionConsole = {
  confirmations: MacroDecisionConsoleItem[];
  contradictions: MacroDecisionConsoleItem[];
  dataCredibility: MacroDecisionDataCredibility | null;
  futureCatalysts: MacroDecisionFutureCatalystItem[];
  liquidityPressure: MacroDecisionLiquidityPressureItem | null;
  qualityBlockers: MacroDecisionConsoleItem[];
  scenarioCases: MacroDecisionScenarioCaseItem[];
  topChanges: MacroDecisionConsoleItem[];
  tradeMap: MacroDecisionTradeMapItem[];
  watchlistAlerts: MacroDecisionWatchlistAlerts | null;
};

export type MacroDecisionConsoleItem = {
  detail: string;
  key: string;
  label: string;
  meta: string | null;
};

export type MacroDecisionFutureCatalystItem = MacroDecisionConsoleItem & {
  sourceUrl: string | null;
};

export type MacroDecisionWatchlistAlerts = {
  assets: MacroDecisionWatchlistAsset[];
  key: string;
  label: string;
  rules: MacroDecisionConsoleItem[];
};

export type MacroDecisionWatchlistAsset = {
  action: string | null;
  key: string;
  label: string;
  symbol: string | null;
};

export type MacroDecisionDataCredibility = {
  issueLabel: string | null;
  key: string;
  label: string;
  rows: MacroDecisionDataCredibilityRow[];
};

export type MacroDecisionDataCredibilityRow = {
  asOf: string | null;
  key: string;
  label: string;
  qualityLabel: string | null;
  source: string | null;
  value: string;
};

export type MacroDecisionLiquidityPressureItem = {
  detail: string;
  drivers: string[];
  implication: string | null;
  invalidation: string | null;
  key: string;
  label: string;
  meta: string | null;
};

export type MacroDecisionScenarioCaseItem = {
  detail: string;
  entry: string;
  invalidation: string;
  key: string;
  label: string;
  meta: string | null;
  stop: string;
  trade: string;
};

export type MacroDecisionTradeMapItem = {
  checklist: string[];
  key: string;
  label: string;
  legs: string[];
  window: string | null;
};

export type MacroSignalDiagnostics = {
  headline: string;
  implications: string[];
  invalidations: string[];
  label: string;
  rows: MacroSignalDiagnosticsRow[];
  summary: string | null;
};

export type MacroSignalDiagnosticsRow = {
  key: string;
  label: string;
  statusLabel: string | null;
  value: string;
};

export type MacroAssetDiagnostics = MacroSignalDiagnostics;
export type MacroAssetDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroAssetClassDiagnostics = MacroSignalDiagnostics;
export type MacroAssetClassDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroCreditDiagnostics = MacroSignalDiagnostics;
export type MacroCreditDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroEmploymentDiagnostics = MacroSignalDiagnostics;
export type MacroEmploymentDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroGrowthDiagnostics = MacroSignalDiagnostics;
export type MacroGrowthDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroVolatilityDiagnostics = MacroSignalDiagnostics;
export type MacroVolatilityDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroLiquidityDiagnostics = MacroSignalDiagnostics;
export type MacroLiquidityDiagnosticsRow = MacroSignalDiagnosticsRow;
export type MacroInflationDiagnostics = MacroSignalDiagnostics;
export type MacroInflationDiagnosticsRow = MacroSignalDiagnosticsRow;

export function buildMacroWorkbenchBrief(module: MacroModuleView): MacroWorkbenchBrief {
  const rows = BRIEF_FIELDS.flatMap((field): MacroWorkbenchBriefRow[] => {
    const rawValue = module.module_read[field.key];
    if (!hasMacroValue(rawValue)) {
      return [];
    }
    const value = formatMacroScalar(rawValue);
    return value ? [{ key: field.key, label: field.label, value }] : [];
  });

  return {
    asOfLabel: stringValue(module.snapshot.asof_label),
    rows: compactBriefRows(rows),
    statusLabel: macroStatusLabel(module),
    summary: macroReadSummary(module),
  };
}

export function hasMacroWorkbenchBrief(brief: MacroWorkbenchBrief): boolean {
  return Boolean(brief.summary || brief.rows.length > 0);
}

export function buildMacroWorkbenchDiagnostics(
  module: MacroModuleView,
  scope: "leaf" | "overview",
): MacroWorkbenchDiagnostics {
  const sourceCount = sourceRows(module.provenance).length;
  return {
    buckets: buildMacroDataHealthBuckets(module.data_health, scope),
    sourceCount,
    sourceMeta: `${sourceCount} 个来源`,
    statusLabel: stringValue(module.data_health.summary_label),
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

export function hasMacroWorkbenchDrivers(drivers: MacroWorkbenchDrivers): boolean {
  return drivers.evidenceCount > 0 || drivers.transmissionCount > 0;
}

export function buildMacroStructuredAnalysis(
  module: MacroModuleView,
): MacroStructuredAnalysis | null {
  const payload = objectValue(module.module_read.structured_analysis);
  if (!payload) {
    return null;
  }
  const key = stringValue(payload.key);
  const label = stringValue(payload.label);
  if (!key || !label) {
    return null;
  }
  const rows = recordList(payload.rows)
    .map((row) => structuredAnalysisRow(row))
    .filter((row): row is MacroStructuredAnalysisRow => row !== null);
  if (rows.length === 0) {
    return null;
  }
  return {
    key,
    label,
    rows,
  };
}

export function buildMacroMarketEventFlow(module: MacroModuleView): MacroMarketEventFlow | null {
  const payload = objectValue(module.module_read.market_event_flow);
  if (!payload) {
    return null;
  }
  const key = stringValue(payload.key);
  const label = stringValue(payload.label);
  if (!key || !label) {
    return null;
  }
  const rows = recordList(payload.rows)
    .map((row) => marketEventFlowItem(row))
    .filter((row): row is MacroMarketEventFlowItem => row !== null);
  if (rows.length === 0) {
    return null;
  }
  return {
    key,
    label,
    rows,
  };
}

export function buildMacroDecisionConsole(module: MacroModuleView): MacroDecisionConsole {
  const consolePayload = objectValue(module.module_read.decision_console);
  return {
    confirmations: evidenceList(module.module_evidence.confirmations)
      .map((item) => evidenceItem(item))
      .filter((item): item is MacroDecisionConsoleItem => item !== null)
      .slice(0, 3),
    contradictions: evidenceList(module.module_evidence.contradictions)
      .map((item) => evidenceItem(item))
      .filter((item): item is MacroDecisionConsoleItem => item !== null)
      .slice(0, 3),
    dataCredibility: dataCredibilityItem(objectValue(consolePayload?.data_credibility)),
    futureCatalysts: futureCatalystItems(objectValue(consolePayload?.future_catalysts)),
    liquidityPressure: liquidityPressureItem(objectValue(consolePayload?.liquidity_pressure)),
    topChanges: recordList(consolePayload?.top_changes)
      .map((item) => decisionItem(item))
      .filter((item): item is MacroDecisionConsoleItem => item !== null)
      .slice(0, 3),
    qualityBlockers: recordList(consolePayload?.quality_blockers)
      .map((item) => qualityItem(item))
      .filter((item): item is MacroDecisionConsoleItem => item !== null)
      .slice(0, 3),
    scenarioCases: recordList(consolePayload?.scenario_cases)
      .map((item) => scenarioCaseItem(item))
      .filter((item): item is MacroDecisionScenarioCaseItem => item !== null)
      .slice(0, 3),
    tradeMap: recordList(consolePayload?.trade_map)
      .map((item) => tradeMapItem(item))
      .filter((item): item is MacroDecisionTradeMapItem => item !== null)
      .slice(0, 2),
    watchlistAlerts: watchlistAlertsItem(objectValue(consolePayload?.watchlist_alerts)),
  };
}

export function buildMacroAssetDiagnostics(module: MacroModuleView): MacroAssetDiagnostics | null {
  return buildSignalDiagnostics(module, "asset_diagnostics", assetDiagnosticsRow);
}

export function buildMacroAssetClassDiagnostics(
  module: MacroModuleView,
): MacroAssetClassDiagnostics | null {
  return buildSignalDiagnostics(module, "asset_class_diagnostics", assetDiagnosticsRow);
}

export function buildMacroCreditDiagnostics(
  module: MacroModuleView,
): MacroCreditDiagnostics | null {
  return buildSignalDiagnostics(module, "credit_diagnostics", creditDiagnosticsRow);
}

export function buildMacroEmploymentDiagnostics(
  module: MacroModuleView,
): MacroEmploymentDiagnostics | null {
  return buildSignalDiagnostics(module, "employment_diagnostics", employmentDiagnosticsRow);
}

export function buildMacroGrowthDiagnostics(
  module: MacroModuleView,
): MacroGrowthDiagnostics | null {
  return buildSignalDiagnostics(module, "growth_diagnostics", growthDiagnosticsRow);
}

export function buildMacroVolatilityDiagnostics(
  module: MacroModuleView,
): MacroVolatilityDiagnostics | null {
  return buildSignalDiagnostics(module, "volatility_diagnostics", volatilityDiagnosticsRow);
}

export function buildMacroLiquidityDiagnostics(
  module: MacroModuleView,
): MacroLiquidityDiagnostics | null {
  return buildSignalDiagnostics(module, "liquidity_diagnostics", liquidityDiagnosticsRow);
}

export function buildMacroInflationDiagnostics(
  module: MacroModuleView,
): MacroInflationDiagnostics | null {
  return buildSignalDiagnostics(module, "inflation_diagnostics", inflationDiagnosticsRow);
}

function buildSignalDiagnostics(
  module: MacroModuleView,
  payloadKey: string,
  rowBuilder: (row: MacroSemanticRecord) => MacroSignalDiagnosticsRow | null,
): MacroSignalDiagnostics | null {
  const payload = objectValue(module.module_read[payloadKey]);
  if (!payload) {
    return null;
  }
  const label = stringValue(payload.label);
  if (!label) {
    return null;
  }
  const rows = recordList(payload.rows)
    .map((row) => rowBuilder(row))
    .filter((row): row is MacroSignalDiagnosticsRow => row !== null);
  const summary = stringValue(payload.summary);
  if (!summary && rows.length === 0) {
    return null;
  }
  const regimeLabel = stringValue(payload.regime_label);
  return {
    headline: regimeLabel ? `${label} · ${regimeLabel}` : label,
    implications: stringList(payload.implications),
    invalidations: stringList(payload.invalidations),
    label,
    rows,
    summary,
  };
}

export function hasMacroDecisionConsole(consoleModel: MacroDecisionConsole): boolean {
  return (
    consoleModel.confirmations.length > 0 ||
    consoleModel.contradictions.length > 0 ||
    consoleModel.dataCredibility !== null ||
    consoleModel.futureCatalysts.length > 0 ||
    consoleModel.liquidityPressure !== null ||
    consoleModel.scenarioCases.length > 0 ||
    consoleModel.topChanges.length > 0 ||
    consoleModel.qualityBlockers.length > 0 ||
    consoleModel.tradeMap.length > 0 ||
    consoleModel.watchlistAlerts !== null
  );
}

function structuredAnalysisRow(item: MacroSemanticRecord): MacroStructuredAnalysisRow | null {
  const key = stringValue(item.key);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const fact = stringValue(item.fact);
  const trade = stringValue(item.trade);
  const invalidation = stringValue(item.invalidation);
  const evidence = stringList(item.evidence);
  if (!label || !fact || !trade || !invalidation || evidence.length === 0) {
    return null;
  }
  const factLabel = formatMacroScalar(fact);
  const tradeLabel = formatMacroScalar(trade);
  const invalidationLabel = formatMacroScalar(invalidation);
  if (!factLabel || !tradeLabel || !invalidationLabel) {
    return null;
  }
  return {
    evidence,
    fact: factLabel,
    invalidation: invalidationLabel,
    key,
    label,
    regimeLabel: stringValue(item.regime_label),
    trade: tradeLabel,
  };
}

function assetDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = assetDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function assetDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const currentBn = numberValue(item.current_bn);
  if (currentBn !== null) {
    const parts = [
      formatUsdBillions(currentBn),
      creditPctChange("1w", numberValue(item.change_1w_pct)),
      creditPctChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const oneWeekPct = numberValue(item.change_1w_pct);
  const oneMonthPct = numberValue(item.change_1m_pct);
  if (oneWeekPct !== null || oneMonthPct !== null) {
    const parts = [creditPctChange("1w", oneWeekPct), creditPctChange("1m", oneMonthPct)].filter(
      (part): part is string => Boolean(part),
    );
    return parts.length > 0 ? parts.join(" · ") : null;
  }
  const currentIndex = numberValue(item.current_index);
  if (currentIndex !== null) {
    const parts = [
      formatCompactNumber(currentIndex),
      volatilityIndexChange("1w", numberValue(item.change_1w_index)),
      volatilityIndexChange("1m", numberValue(item.change_1m_index)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentBp = numberValue(item.current_bp);
  if (currentBp !== null) {
    const parts = [
      formatBp(currentBp),
      creditBpChange("1w", numberValue(item.change_1w_bp)),
      creditBpChange("1m", numberValue(item.change_1m_bp)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentK = numberValue(item.current_k);
  if (currentK !== null) {
    const parts = [
      formatThousands(currentK),
      employmentKChange("1w", numberValue(item.change_1w_k)),
      employmentKChange("1m", numberValue(item.change_1m_k)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function volatilityDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = volatilityDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function volatilityDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const currentIndex = numberValue(item.current_index);
  if (currentIndex !== null) {
    const parts = [
      formatCompactNumber(currentIndex),
      volatilityIndexChange("1w", numberValue(item.change_1w_index)),
      volatilityIndexChange("1m", numberValue(item.change_1m_index)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentPoints = numberValue(item.current_points);
  if (currentPoints !== null) {
    const parts = [
      `${formatCompactNumber(currentPoints)}pts`,
      volatilityPointsChange("1w", numberValue(item.change_1w_points)),
      volatilityPointsChange("1m", numberValue(item.change_1m_points)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentRatio = numberValue(item.current_ratio);
  if (currentRatio !== null) {
    const parts = [
      `${formatRatio(currentRatio)}x`,
      creditPctChange("1w", numberValue(item.change_1w_pct)),
      creditPctChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function volatilityIndexChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedCompactNumber(value)}`;
}

function volatilityPointsChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedCompactNumber(value)}pts`;
}

function creditDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = creditDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function liquidityDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = liquidityDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function liquidityDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const currentBp = numberValue(item.current_bp);
  if (currentBp !== null) {
    const parts = [
      formatBp(currentBp),
      creditBpChange("1w", numberValue(item.change_1w_bp)),
      creditBpChange("1m", numberValue(item.change_1m_bp)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentBn = numberValue(item.current_bn);
  if (currentBn !== null) {
    const parts = [
      formatUsdBillions(currentBn),
      liquidityBnChange("1w", numberValue(item.change_1w_bn)),
      liquidityBnChange("1m", numberValue(item.change_1m_bn)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentTrillion = numberValue(item.current_trillion);
  if (currentTrillion !== null) {
    const parts = [
      formatUsdTrillions(currentTrillion),
      liquidityBnChange("1w", numberValue(item.change_1w_bn)),
      liquidityBnChange("1m", numberValue(item.change_1m_bn)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function employmentDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = employmentDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function employmentDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const currentYoyPct = numberValue(item.current_yoy_pct);
  if (currentYoyPct !== null) {
    const parts = [
      `${formatCompactNumber(currentYoyPct)}% y/y`,
      inflationPctPointChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentPct = numberValue(item.current_pct);
  if (currentPct !== null) {
    const parts = [
      `${formatCompactNumber(currentPct)}%`,
      inflationPctPointChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentK = numberValue(item.current_k);
  if (currentK !== null) {
    const parts = [
      formatThousands(currentK),
      employmentKChange("1w", numberValue(item.change_1w_k)),
      employmentKChange("1m", numberValue(item.change_1m_k)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentM = numberValue(item.current_m);
  if (currentM !== null) {
    const parts = [
      formatMillions(currentM),
      employmentMChange("1m", numberValue(item.change_1m_m)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function growthDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = growthDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function growthDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const currentYoyPct = numberValue(item.current_yoy_pct);
  if (currentYoyPct !== null) {
    const parts = [
      `${formatCompactNumber(currentYoyPct)}% y/y`,
      inflationPctPointChange("1q", numberValue(item.change_1q_pct)),
      inflationPctPointChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentPct = numberValue(item.current_pct);
  if (currentPct !== null) {
    const parts = [
      `${formatCompactNumber(currentPct)}% SAAR`,
      inflationPctPointChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentM = numberValue(item.current_m);
  if (currentM !== null) {
    const parts = [
      formatMillions(currentM),
      employmentKChange("1m", numberValue(item.change_1m_k)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function inflationDiagnosticsRow(item: MacroSemanticRecord): MacroSignalDiagnosticsRow | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const value = inflationDiagnosticsValue(item);
  if (!key || !label || !value) {
    return null;
  }
  return {
    key,
    label,
    statusLabel: stringValue(item.status_label),
    value,
  };
}

function inflationDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const currentYoyPct = numberValue(item.current_yoy_pct);
  if (currentYoyPct !== null) {
    const parts = [
      `${formatCompactNumber(currentYoyPct)}% y/y`,
      inflationPctPointChange("1m", numberValue(item.change_1m_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentPct = numberValue(item.current_pct);
  if (currentPct !== null) {
    const parts = [
      `${formatCompactNumber(currentPct)}%`,
      creditBpChange("1w", numberValue(item.change_1w_bp)),
      creditBpChange("1m", numberValue(item.change_1m_bp)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function creditDiagnosticsValue(item: MacroSemanticRecord): string | null {
  const relativeOneWeekPct = numberValue(item.relative_1w_pct);
  if (relativeOneWeekPct !== null) {
    const hygOneWeekPct = numberValue(item.hyg_1w_pct);
    const lqdOneWeekPct = numberValue(item.lqd_1w_pct);
    if (hygOneWeekPct === null || lqdOneWeekPct === null) {
      return null;
    }
    return [
      `HYG 1w ${formatSignedCompactNumber(hygOneWeekPct)}%`,
      `LQD 1w ${formatSignedCompactNumber(lqdOneWeekPct)}%`,
      `相对 ${formatSignedCompactNumber(relativeOneWeekPct)}%`,
    ].join(" · ");
  }
  const currentBp = numberValue(item.current_bp);
  if (currentBp !== null) {
    const parts = [
      formatBp(currentBp),
      creditBpChange("1w", numberValue(item.change_1w_bp)),
      creditBpChange("1m", numberValue(item.change_1m_bp)),
      creditBpChange("3m", numberValue(item.change_3m_bp)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentPct = numberValue(item.current_pct);
  if (currentPct !== null) {
    const parts = [
      `${formatCompactNumber(currentPct)}%`,
      creditPctChange("1q", numberValue(item.change_1q_pct)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  const currentIndex = numberValue(item.current_index);
  if (currentIndex !== null) {
    const parts = [
      formatCompactNumber(currentIndex),
      volatilityIndexChange("1w", numberValue(item.change_1w_index)),
      volatilityIndexChange("1m", numberValue(item.change_1m_index)),
      volatilityIndexChange("3m", numberValue(item.change_3m_index)),
    ].filter((part): part is string => Boolean(part));
    return parts.join(" · ");
  }
  return null;
}

function creditBpChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedBp(value)}`;
}

function creditPctChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedCompactNumber(value)}%`;
}

function formatBp(value: number): string {
  return `${formatCompactNumber(value)}bp`;
}

function formatSignedBp(value: number): string {
  return `${formatSignedCompactNumber(value)}bp`;
}

function inflationPctPointChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedCompactNumber(value)}pp`;
}

function liquidityBnChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedUsdBillions(value)}`;
}

function employmentKChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedThousands(value)}`;
}

function employmentMChange(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedMillions(value)}`;
}

function formatThousands(value: number): string {
  return `${formatCompactNumber(value)}k`;
}

function formatSignedThousands(value: number): string {
  return `${formatSignedCompactNumber(value)}k`;
}

function formatMillions(value: number): string {
  return `${formatCompactNumber(value)}M`;
}

function formatSignedMillions(value: number): string {
  return `${formatSignedCompactNumber(value)}M`;
}

function formatUsdBillions(value: number): string {
  return `$${formatCompactNumber(value)}B`;
}

function formatSignedUsdBillions(value: number): string {
  const prefix = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${prefix}$${formatCompactNumber(Math.abs(value))}B`;
}

function formatUsdTrillions(value: number): string {
  const body = value.toFixed(2).replace(/\.00$/, "");
  return `$${body}T`;
}

function hasMacroValue(value: unknown): boolean {
  if (typeof value === "number") {
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

function decisionItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.code);
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.evidence_label);
  if (!key || !label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: decisionItemMeta(item),
  };
}

function decisionItemMeta(item: MacroSemanticRecord): string | null {
  const parts = [
    stringValue(item.change_label),
    stringValue(item.value_label),
    stringValue(item.source_label),
    stringValue(item.observed_at),
    stringValue(item.severity_label),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function qualityItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.code);
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.evidence_label);
  if (!key || !label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: stringValue(item.severity_label),
  };
}

function dataCredibilityItem(
  item: MacroSemanticRecord | null,
): MacroDecisionDataCredibility | null {
  if (!item) {
    return null;
  }
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  if (!key || !label) {
    return null;
  }
  const rows = recordList(item.rows)
    .map((row) => dataCredibilityRow(row))
    .filter((row): row is MacroDecisionDataCredibilityRow => row !== null)
    .slice(0, 8);
  if (rows.length === 0) {
    return null;
  }
  return {
    issueLabel: stringValue(item.issue_label),
    key,
    label,
    rows,
  };
}

function dataCredibilityRow(item: MacroSemanticRecord): MacroDecisionDataCredibilityRow | null {
  const key = stringValue(item.concept_key);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const value = dataCredibilityValue(item);
  if (!label || !value) {
    return null;
  }
  return {
    asOf: stringValue(item.observed_at_label),
    key,
    label,
    qualityLabel: stringValue(item.quality_label),
    source: stringValue(item.source_label),
    value,
  };
}

function dataCredibilityValue(item: MacroSemanticRecord): string | null {
  const displayValue = stringValue(item.display_value);
  if (!displayValue) {
    return null;
  }
  const unitLabel = stringValue(item.unit_label);
  return [displayValue, unitLabel].filter((part): part is string => Boolean(part)).join(" ");
}

function evidenceItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.code);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.evidence_label);
  if (!label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: evidenceMeta(item),
  };
}

function liquidityPressureItem(
  item: MacroSemanticRecord | null,
): MacroDecisionLiquidityPressureItem | null {
  if (!item) {
    return null;
  }
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  if (!key || !label) {
    return null;
  }
  const detail = stringValue(item.summary);
  if (!detail) {
    return null;
  }
  const detailLabel = formatMacroScalar(detail);
  if (!detailLabel) {
    return null;
  }
  return {
    detail: detailLabel,
    drivers: recordList(item.drivers)
      .map((driver) => liquidityPressureDriver(driver))
      .filter((driver): driver is string => driver !== null)
      .slice(0, 3),
    implication: stringValue(item.implication),
    invalidation: stringValue(item.invalidation),
    key,
    label,
    meta: liquidityPressureMeta(item),
  };
}

function liquidityPressureDriver(item: MacroSemanticRecord): string | null {
  const row = liquidityDiagnosticsRow(item);
  if (!row) {
    return null;
  }
  return [row.label, row.value, row.statusLabel]
    .filter((part): part is string => Boolean(part))
    .join(" · ");
}

function liquidityPressureMeta(item: MacroSemanticRecord): string | null {
  const parts = [stringValue(item.score_label), stringValue(item.regime_label)].filter(
    (part): part is string => Boolean(part),
  );
  return parts.length > 0 ? parts.join(" · ") : null;
}

function marketEventFlowItem(item: MacroSemanticRecord): MacroMarketEventFlowItem | null {
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  const date = stringValue(item.date);
  const detail = stringValue(item.detail);
  const watch = stringValue(item.watch);
  if (!key || !label || !date || !detail || !watch) {
    return null;
  }
  const detailLabel = formatMacroScalar(detail);
  const watchLabel = formatMacroScalar(watch);
  if (!detailLabel || !watchLabel) {
    return null;
  }
  return {
    categoryLabel: stringValue(item.category_label),
    date,
    detail: detailLabel,
    impactLabel: stringValue(item.impact_label),
    key,
    label,
    meta: marketEventFlowMeta(item),
    severityLabel: stringValue(item.severity_label),
    sourceUrl: stringValue(item.source_url),
    watch: watchLabel,
  };
}

function marketEventFlowMeta(item: MacroSemanticRecord): string | null {
  const parts = [
    stringValue(item.source),
    stringValue(item.category_label),
    stringValue(item.impact_label),
    stringValue(item.window_label),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function futureCatalystItems(item: MacroSemanticRecord | null): MacroDecisionFutureCatalystItem[] {
  if (!item) {
    return [];
  }
  return recordList(item.rows)
    .map((row) => futureCatalystItem(row))
    .filter((row): row is MacroDecisionFutureCatalystItem => row !== null)
    .slice(0, 6);
}

function futureCatalystItem(item: MacroSemanticRecord): MacroDecisionFutureCatalystItem | null {
  const key = stringValue(item.key);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.detail);
  if (!label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: futureCatalystMeta(item),
    sourceUrl: stringValue(item.source_url),
  };
}

function futureCatalystMeta(item: MacroSemanticRecord): string | null {
  const parts = [
    stringValue(item.window_label),
    stringValue(item.severity_label),
    stringValue(item.source),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function watchlistAlertsItem(
  item: MacroSemanticRecord | null,
): MacroDecisionWatchlistAlerts | null {
  if (!item) {
    return null;
  }
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  if (!key || !label) {
    return null;
  }
  const assets = recordList(item.assets)
    .map((asset) => watchlistAssetItem(asset))
    .filter((asset): asset is MacroDecisionWatchlistAsset => asset !== null)
    .slice(0, 8);
  const rules = recordList(item.rules)
    .map((rule) => watchlistRuleItem(rule))
    .filter((rule): rule is MacroDecisionConsoleItem => rule !== null)
    .slice(0, 8);
  if (assets.length === 0 && rules.length === 0) {
    return null;
  }
  return {
    assets,
    key,
    label,
    rules,
  };
}

function watchlistAssetItem(item: MacroSemanticRecord): MacroDecisionWatchlistAsset | null {
  const key = stringValue(item.key);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const symbol = stringValue(item.symbol);
  if (!label) {
    return null;
  }
  return {
    action: stringValue(item.action),
    key,
    label,
    symbol,
  };
}

function watchlistRuleItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.key);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.detail);
  if (!label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: watchlistRuleMeta(item),
  };
}

function watchlistRuleMeta(item: MacroSemanticRecord): string | null {
  const parts = [
    stringValue(item.kind_label),
    stringValue(item.window_label),
    stringValue(item.severity_label),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function scenarioCaseItem(item: MacroSemanticRecord): MacroDecisionScenarioCaseItem | null {
  const key = stringValue(item.case);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = stringValue(item.thesis);
  const trade = stringValue(item.trade);
  const entry = stringValue(item.entry_condition);
  const stop = stringValue(item.stop);
  const invalidation = stringValue(item.invalidation);
  if (!label || !detail || !trade || !entry || !stop || !invalidation) {
    return null;
  }
  const meta = [stringValue(item.probability_label), stringValue(item.time_window_label)].filter(
    (part): part is string => Boolean(part),
  );
  return {
    detail,
    entry: `入场：${entry}`,
    invalidation: `失效：${invalidation}`,
    key,
    label,
    meta: meta.length > 0 ? meta.join(" · ") : null,
    stop: `止损：${stop}`,
    trade: `交易：${trade}`,
  };
}

function evidenceMeta(item: MacroSemanticRecord): string | null {
  const parts = [
    stringValue(item.time_window_label),
    stringValue(item.severity_label),
    stringValue(item.meta),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function tradeMapItem(item: MacroSemanticRecord): MacroDecisionTradeMapItem | null {
  const expression = stringValue(item.expression);
  if (!expression) {
    return null;
  }
  const label = stringValue(item.label);
  if (!label) {
    return null;
  }
  return {
    checklist: tradeMapChecklist(item),
    key: expression,
    label,
    legs: recordList(item.legs)
      .map(tradeLegLabel)
      .filter((leg): leg is string => Boolean(leg)),
    window: stringValue(item.time_window_label),
  };
}

function tradeLegLabel(item: MacroSemanticRecord): string | null {
  const label = stringValue(item.label);
  const action = stringValue(item.action);
  if (!label || !action) {
    return null;
  }
  const symbol = stringValue(item.symbol);
  return symbol ? `${symbol} · ${label} · ${action}` : `${label} · ${action}`;
}

function tradeMapChecklist(item: MacroSemanticRecord): string[] {
  return recordList(item.action_checklist)
    .map((entry) => {
      const kindLabel = stringValue(entry.kind_label);
      const label = stringValue(entry.label);
      const description = stringValue(entry.description);
      if (!kindLabel || !label || !description) {
        return null;
      }
      return `${kindLabel} · ${label} · ${description}`;
    })
    .filter((line): line is string => Boolean(line));
}

function formatCompactNumber(value: number): string {
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function formatSignedCompactNumber(value: number): string {
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  const prefix = rounded > 0 ? "+" : "";
  const body = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${prefix}${body}`;
}

function formatRatio(value: number): string {
  return value.toFixed(2);
}

function objectValue(value: unknown): MacroSemanticRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as MacroSemanticRecord)
    : null;
}

function recordList(value: unknown): MacroSemanticRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is MacroSemanticRecord =>
        Boolean(item && typeof item === "object" && !Array.isArray(item)),
      )
    : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .map((item) => stringValue(item))
        .filter((item): item is string => Boolean(item))
        .slice(0, 4)
    : [];
}

function evidenceList(value: unknown): MacroSemanticRecord[] {
  return recordList(value);
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

function formattedScalarValue(value: unknown): string | null {
  return formatMacroScalar(value);
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

const BRIEF_FIELDS = [
  { key: "regime_label", label: "状态" },
  { key: "confidence_label", label: "规则覆盖" },
  { key: "crypto_read", label: "加密影响" },
  { key: "token_impact", label: "代币影响" },
] as const;

function compactBriefRows(rows: MacroWorkbenchBriefRow[]): MacroWorkbenchBriefRow[] {
  const seen = new Set<string>();
  return rows
    .filter((row) => {
      const signature = `${row.label}:${row.value}`;
      if (seen.has(signature)) {
        return false;
      }
      seen.add(signature);
      return true;
    })
    .slice(0, 3);
}
