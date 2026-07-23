import type { components } from "@lib/types/openapi";

export type MacroOverviewData = components["schemas"]["MacroOverviewData"];
export type MacroCrossAssetData = components["schemas"]["MacroCrossAssetData"];
export type MacroRatesInflationData = components["schemas"]["MacroRatesInflationData"];
export type MacroGrowthLaborData = components["schemas"]["MacroGrowthLaborData"];
export type MacroLiquidityFundingData = components["schemas"]["MacroLiquidityFundingData"];
export type MacroCreditData = components["schemas"]["MacroCreditData"];
export type MacroEvidenceData = components["schemas"]["MacroEvidenceData"];
export type MacroDecisionItemData = components["schemas"]["MacroDecisionItemData"];
export type MacroRuleHitData = components["schemas"]["MacroRuleHitData"];
export type MacroMetricData = components["schemas"]["MacroMetricData"];
export type MacroSeriesData = components["schemas"]["MacroSeriesData"];
export type MacroUnavailableEvidenceData = components["schemas"]["MacroUnavailableEvidenceData"];
export type DailyMacroJudgmentReadData = components["schemas"]["DailyMacroJudgmentReadData"];

export type MacroPageCommonData = Pick<
  MacroOverviewData,
  | "conclusion"
  | "confirmations"
  | "contradictions"
  | "drivers"
  | "evidence"
  | "evidence_refs"
  | "freshness"
  | "horizon"
  | "snapshot"
  | "unavailable_evidence"
  | "upgrade_invalidation"
>;
