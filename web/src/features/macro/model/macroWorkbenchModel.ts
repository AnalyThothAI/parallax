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
  judgementReview: MacroDecisionJudgementReview | null;
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

export type MacroDecisionJudgementReview = {
  itemCountLabel: string | null;
  key: string;
  label: string;
  rows: MacroDecisionConsoleItem[];
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
  confirms: string | null;
  history: string[];
  holding: string[];
  invalidates: string | null;
  key: string;
  label: string;
  legs: string[];
  portfolio: string[];
  trust: string[];
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
    asOfLabel: stringValue(module.snapshot.asof_label) ?? stringValue(module.snapshot.asof_date),
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
    judgementReview: judgementReviewItem(objectValue(consolePayload?.judgement_review)),
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
    consoleModel.judgementReview !== null ||
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

function decisionItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.code);
  const label = stringValue(item.label) ?? signalLabel(stringValue(item.code));
  const detail = formattedScalarValue(stringValue(item.evidence_label) ?? item.description);
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
    sectionLabel(stringValue(item.node) ?? stringValue(item.kind)),
    stringValue(item.severity_label) ?? severityLabel(stringValue(item.severity)),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function qualityItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.code);
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.description);
  if (!key || !label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: severityLabel(stringValue(item.severity)),
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
    asOf: stringValue(item.observed_at) ?? stringValue(item.observed_at_label),
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
  const label = stringValue(item.label) ?? signalLabel(key);
  const detail = formattedScalarValue(item.description);
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

function judgementReviewItem(
  item: MacroSemanticRecord | null,
): MacroDecisionJudgementReview | null {
  if (!item) {
    return null;
  }
  const key = stringValue(item.key);
  const label = stringValue(item.label);
  if (!key || !label) {
    return null;
  }
  const rows = recordList(item.rows)
    .map((row) => judgementReviewRow(row))
    .filter((row): row is MacroDecisionConsoleItem => row !== null)
    .slice(0, 4);
  if (rows.length === 0) {
    return null;
  }
  return {
    itemCountLabel: stringValue(item.item_count_label),
    key,
    label,
    rows,
  };
}

function judgementReviewRow(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.key);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = judgementReviewDetail(item);
  if (!label || !detail) {
    return null;
  }
  return {
    detail,
    key,
    label,
    meta: stringValue(item.reliability_summary),
  };
}

function judgementReviewDetail(item: MacroSemanticRecord): string | null {
  const rows = recordList(item.windows)
    .map(judgementReviewWindowDetail)
    .filter((detail): detail is string => detail !== null);
  return rows.length > 0 ? rows.join(" / ") : null;
}

function judgementReviewWindowDetail(item: MacroSemanticRecord): string | null {
  const label = stringValue(item.label);
  const status = stringValue(item.status_label);
  const winRate = stringValue(item.win_rate_label);
  const pnl = numberValue(item.pnl_usd);
  const averageReturn = numberValue(item.average_signed_return_pct);
  if (!label || !status || !winRate || pnl === null || averageReturn === null) {
    return null;
  }
  return `${label} ${status} · ${winRate} · P&L ${formatSignedUsd(
    pnl,
  )} · 均值 ${formatSignedPercent(averageReturn)}`;
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
    stringValue(item.source) ?? eventKindLabel(stringValue(item.kind)),
    stringValue(item.category_label),
    stringValue(item.impact_label),
    stringValue(item.window),
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
  const key = stringValue(item.key) ?? stringValue(item.code);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = stringValue(item.description);
  if (!label || !detail) {
    return null;
  }
  const detailLabel = formatMacroScalar(detail);
  if (!detailLabel) {
    return null;
  }
  return {
    detail: detailLabel,
    key,
    label,
    meta: futureCatalystMeta(item),
    sourceUrl: stringValue(item.source_url),
  };
}

function futureCatalystMeta(item: MacroSemanticRecord): string | null {
  const parts = [
    stringValue(item.window_label) ?? stringValue(item.window),
    stringValue(item.severity_label) ?? severityLabel(stringValue(item.severity)),
    stringValue(item.source) ?? eventKindLabel(stringValue(item.kind)),
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
  if (!label && !symbol) {
    return null;
  }
  return {
    action: stringValue(item.action),
    key,
    label: label ?? symbol ?? key,
    symbol,
  };
}

function watchlistRuleItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {
  const key = stringValue(item.key) ?? stringValue(item.code);
  if (!key) {
    return null;
  }
  const label = stringValue(item.label);
  const detail = formattedScalarValue(item.description);
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
    stringValue(item.kind_label) ?? watchlistKindLabel(stringValue(item.kind)),
    stringValue(item.window),
    stringValue(item.severity_label) ?? severityLabel(stringValue(item.severity)),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function watchlistKindLabel(kind: string | null): string | null {
  const labels: Record<string, string> = {
    invalidation: "失效",
    quality: "质量",
    watch: "触发",
  };
  return labels[kind ?? ""] ?? null;
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
  const meta = [stringValue(item.probability_label), stringValue(item.time_window)].filter(
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
    stringValue(item.time_window),
    severityLabel(stringValue(item.severity)),
    stringValue(item.meta) ?? sectionLabel(stringValue(item.node)),
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : null;
}

function tradeMapItem(item: MacroSemanticRecord): MacroDecisionTradeMapItem | null {
  const expression = stringValue(item.expression);
  if (!expression) {
    return null;
  }
  const label = stringValue(item.label) ?? tradeExpressionLabel(expression);
  if (!label) {
    return null;
  }
  return {
    checklist: tradeMapChecklist(item),
    confirms: codeList(item.confirms_on),
    history: tradeMapHistory(item),
    holding: tradeMapHolding(item),
    invalidates: codeList(item.invalidates_on),
    key: expression,
    label,
    legs: recordList(item.legs)
      .map(tradeLegLabel)
      .filter((leg): leg is string => Boolean(leg)),
    portfolio: tradeMapPortfolio(item),
    trust: tradeMapTrust(item),
    window: stringValue(item.time_window),
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

function tradeMapHistory(item: MacroSemanticRecord): string[] {
  const review = objectValue(item.historical_review);
  if (!review) {
    return [];
  }
  const label = stringValue(review.label);
  if (!label) {
    return [];
  }
  const header = [
    label,
    stringValue(review.win_rate_label) ? `胜率 ${stringValue(review.win_rate_label)}` : null,
    percentPart("均值", numberValue(review.average_return_pct)),
    percentPart("最大逆风", numberValue(review.max_adverse_excursion_pct)),
  ].filter((part): part is string => Boolean(part));
  const rows = recordList(review.rows)
    .map(tradeMapHistoryRow)
    .filter((row): row is string => Boolean(row))
    .slice(0, 5);
  return [header.join(" · "), ...rows].filter((line) => line.length > 0);
}

function tradeMapHistoryRow(item: MacroSemanticRecord): string | null {
  const asset = stringValue(item.asset);
  const label = stringValue(item.label);
  const returnPct = numberValue(item.return_pct);
  if (!asset || !label || returnPct === null) {
    return null;
  }
  return `${asset} ${label} ${formatSignedPercent(returnPct)} ${outcomeLabel(
    stringValue(item.outcome),
  )}`;
}

function tradeMapPortfolio(item: MacroSemanticRecord): string[] {
  const review = objectValue(item.portfolio_review);
  if (!review) {
    return [];
  }
  const label = stringValue(review.label);
  if (!label) {
    return [];
  }
  const summary = stringValue(review.summary);
  if (!summary) {
    return [];
  }
  const risk = stringValue(review.risk_temperature);
  return [`${label} · ${summary}${risk ? ` · 风险温度 ${risk}` : ""}`];
}

function tradeMapChecklist(item: MacroSemanticRecord): string[] {
  return recordList(item.action_checklist)
    .map((entry) => {
      const kindLabel = checklistKindLabel(stringValue(entry.kind));
      if (!kindLabel) {
        return null;
      }
      const label = stringValue(entry.label);
      const description = stringValue(entry.description);
      if (!label || !description) {
        return null;
      }
      return `${kindLabel} · ${label} · ${description}`;
    })
    .filter((line): line is string => Boolean(line));
}

function tradeMapTrust(item: MacroSemanticRecord): string[] {
  const trust = objectValue(item.historical_trust);
  const summary = stringValue(trust?.summary);
  return summary ? [summary] : [];
}

function tradeMapHolding(item: MacroSemanticRecord): string[] {
  const review = objectValue(item.holding_period_review);
  return recordList(review?.rows)
    .map((row) => {
      const label = stringValue(row.label);
      const status = stringValue(row.status_label);
      const winRate = stringValue(row.win_rate_label);
      const pnl = numberValue(row.pnl_usd);
      const averageReturn = numberValue(row.average_signed_return_pct);
      if (!label || !status || !winRate || pnl === null || averageReturn === null) {
        return null;
      }
      return `${label} ${status} · ${winRate} · P&L ${formatSignedUsd(
        pnl,
      )} · 均值 ${formatSignedPercent(averageReturn)}`;
    })
    .filter((line): line is string => Boolean(line));
}

function checklistKindLabel(kind: string | null): string | null {
  return CHECKLIST_KIND_LABELS[kind ?? ""] ?? null;
}

function percentPart(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatSignedPercent(value)}`;
}

function outcomeLabel(value: string | null): string {
  return value === "hit" ? "命中" : "未中";
}

function formatSignedPercent(value: number): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function formatSignedUsd(value: number): string {
  const rounded = Math.round(value);
  const prefix = rounded > 0 ? "+" : rounded < 0 ? "-" : "";
  return `${prefix}$${Math.abs(rounded).toLocaleString("en-US")}`;
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

function codeList(value: unknown): string | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const labels = value
    .map((item) => signalLabel(stringValue(item)))
    .filter((label): label is string => Boolean(label));
  return labels.length > 0 ? labels.join(" / ") : null;
}

function signalLabel(code: string | null): string | null {
  if (!code) return null;
  if (/[\u3400-\u9fff]/u.test(code)) return code;
  return SIGNAL_LABELS[code] ?? null;
}

function sectionLabel(value: string | null): string | null {
  if (!value) return null;
  if (/[\u3400-\u9fff]/u.test(value)) return value;
  return (
    {
      credit: "信用",
      cross_asset: "跨资产确认",
      fed_corridor: "政策走廊",
      funding: "资金面",
      liquidity: "流动性",
      macro: "宏观",
      positioning: "仓位拥挤度",
      rates: "利率",
      trigger: "触发",
      volatility: "波动率",
    }[value] ?? null
  );
}

function severityLabel(value: string | null): string | null {
  if (!value) return null;
  return (
    {
      error: "阻断",
      high: "高",
      info: "提示",
      low: "低",
      medium: "中",
      warning: "警告",
    }[value] ?? null
  );
}

function tradeExpressionLabel(expression: string | null): string | null {
  if (!expression) return null;
  if (/[\u3400-\u9fff]/u.test(expression)) return expression;
  return TRADE_EXPRESSION_LABELS[expression] ?? null;
}

function eventKindLabel(kind: string | null): string | null {
  if (!kind) return null;
  return (
    {
      auction_calendar: "国债拍卖日历",
      auction_result: "拍卖结果",
      calendar: "官方日历",
      event: "事件",
      fed_text: "Fed 文本",
    }[kind] ?? null
  );
}

const BRIEF_FIELDS = [
  { key: "regime_label", label: "状态" },
  { key: "regime", label: "状态" },
  { key: "confidence_label", label: "规则覆盖" },
  { key: "crypto_read", label: "加密影响" },
  { key: "token_impact", label: "代币影响" },
] as const;

const SIGNAL_LABELS: Record<string, string> = {
  breakevens_accelerate: "通胀补偿加速",
  credit_spreads_benign: "信用利差仍温和",
  credit_spreads_normalize: "信用利差正常化",
  credit_stress: "信用压力",
  deep_curve_inversion: "曲线深度倒挂",
  fed_corridor_pressure: "政策走廊压力",
  higher_real_rates: "实际利率上行",
  hyg_underperforms_lqd: "HYG 跑输 LQD",
  hy_oas_distress: "高收益债利差进入困境区",
  hy_oas_stress: "高收益债利差压力",
  hy_oas_tightens: "HY OAS 收窄",
  hy_oas_widening: "HY OAS 走阔",
  hy_oas_widening_5d: "HY OAS 5日走阔",
  liquidity_easing: "流动性宽松",
  liquidity_impulse_fades: "流动性脉冲减弱",
  liquidity_impulse_persists: "流动性脉冲延续",
  liquidity_tightens: "流动性转紧",
  liquidity_tightening: "流动性收紧",
  macro_core_coverage_recovers: "宏观核心覆盖恢复",
  macro_regime_breakout: "宏观状态突破",
  real_yield_breakout: "实际利率突破",
  real_yield_recedes: "实际利率回落",
  repo_pressure_persists_3d: "回购压力延续 3 日",
  repo_corridor_pressure: "回购走廊压力",
  risk_asset_confirmation_missing: "风险资产确认缺失",
  risk_assets_confirm_risk_on: "风险资产确认 risk-on",
  rrp_buffer_low: "RRP 缓冲偏低",
  sofr_above_iorb: "SOFR 高于 IORB",
  sofr_iorb_normalizes: "SOFR/IORB 回归正常",
  ten_year_yield_reverses: "10Y 收益率反转",
  term_premium_pressure: "期限溢价压力",
  tga_high: "TGA 偏高",
  vix_elevated: "VIX 偏高",
  vix_breaks_30: "VIX 突破 30",
  vix_reprices_higher: "VIX 重新上行",
  vix_returns_to_carry: "VIX 回到 carry 区间",
  volatility_panic: "波动率恐慌",
  volatility_stress: "波动率压力",
  volatility_unconcerned: "波动率未确认压力",
};

const TRADE_EXPRESSION_LABELS: Record<string, string> = {
  credit_beta_underweight: "低配信用 beta",
  duration_pressure_quality_over_growth: "久期承压 / 质量优于成长",
  risk_down_credit_sensitive: "风险降档 / 信用敏感",
  risk_on_liquidity_beta: "流动性 risk-on beta",
};

const CHECKLIST_KIND_LABELS: Record<string, string> = {
  confirm: "确认",
  invalidate: "失效",
  position_review: "纸面仓位",
};

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
