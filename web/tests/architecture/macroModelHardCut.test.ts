import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const webRoot = process.cwd();
const macroRoot = join(webRoot, "src/features/macro");
const macroWorkbenchModel = join(macroRoot, "model/macroWorkbenchModel.ts");
const macroRatesWorkbenchModel = join(macroRoot, "model/macroRatesWorkbenchModel.ts");
const macroPageViewModel = join(macroRoot, "model/macroPageViewModel.ts");
const macroModulePresentation = join(macroRoot, "model/macroModulePresentation.ts");
const macroTableColumns = join(macroRoot, "model/macroTableColumns.ts");
const macroChartModel = join(macroRoot, "model/macroChartModel.ts");
const macroRatesChartModel = join(macroRoot, "model/macroRatesChartModel.ts");
const macroAssetOverviewModel = join(macroRoot, "model/macroAssetOverviewModel.ts");
const macroCorrelationModel = join(macroRoot, "model/macroCorrelationModel.ts");
const macroRoutesModel = join(macroRoot, "model/macroRoutes.ts");
const macroWorkbenchRoute = join(macroRoot, "MacroWorkbenchRoute.tsx");
const macroMarketBoard = join(macroRoot, "ui/pages/MacroMarketBoard.tsx");
const macroOverviewModulePage = join(macroRoot, "ui/pages/MacroOverviewModulePage.tsx");
const macroAssetOverviewPage = join(macroRoot, "ui/pages/MacroAssetOverviewPage.tsx");
const macroDiagnosticsPanel = join(macroRoot, "ui/workbench/MacroDiagnosticsPanel.tsx");
const macroTimeSeriesChart = join(macroRoot, "ui/charts/MacroTimeSeriesChart.tsx");
const macroCorrelationTables = join(macroRoot, "ui/correlation/MacroCorrelationTables.tsx");
const macroMarketEventFlowPanel = join(macroRoot, "ui/workbench/MacroMarketEventFlowPanel.tsx");
const ratesDiagnosticsPanel = join(macroRoot, "ui/rates/RatesDiagnosticsPanel.tsx");
const ratesMarketRead = join(macroRoot, "ui/rates/RatesMarketRead.tsx");
const ratesPrimaryVisual = join(macroRoot, "ui/rates/RatesPrimaryVisual.tsx");
const ratesWorkbenchCss = join(macroRoot, "ui/rates/macroRatesWorkbench.css");
const assetDiagnosticsBoard = join(macroRoot, "ui/assets/AssetDiagnosticsBoard.tsx");
const assetDailyBrief = join(macroRoot, "ui/assets/AssetDailyBrief.tsx");
const macroLeafModulePage = join(macroRoot, "ui/pages/MacroLeafModulePage.tsx");
const macroSourceTable = join(macroRoot, "ui/tables/MacroSourceTable.tsx");
const macroShell = join(macroRoot, "ui/shell/MacroShell.tsx");
const frontendContracts = join(webRoot, "src/lib/types/frontend-contracts.ts");

const collectSourceFiles = (directory: string): string[] =>
  readdirSync(directory)
    .flatMap((entry) => {
      const path = join(directory, entry);
      const stats = statSync(path);

      if (stats.isDirectory()) {
        return collectSourceFiles(path);
      }

      if (stats.isFile() && (path.endsWith(".ts") || path.endsWith(".tsx"))) {
        return [path];
      }

      return [];
    })
    .sort();

const retiredIdentityFallbackTokens = [
  "`metric:${index}`",
  "`fact:${index}`",
  "`gap:${index}`",
  "`${bucketKey}:${index}`",
  "`row:${rowIndex}`",
  "`row:${index}`",
  "`${stable}:${rowIndex}`",
  'titleByKey[conceptKey] ?? "资产"',
  "`policy-row:${index}`",
  "`curve-row:${index}`",
  "`curve-history:${seriesIndex}`",
  "`tenor:${index}`",
  "`${groupKey}:${index}`",
  "`政策读数 ${index + 1}`",
  "`曲线 ${index + 1}`",
  "`利差历史 ${seriesIndex + 1}`",
  "`期限 ${index + 1}`",
  "`实际利率读数 ${index + 1}`",
  "`点 ${pointIndex + 1}`",
  'conceptKey.split(":")',
  "code.split(/[:_]+/)",
  "`${source}:${index}`",
  'String(chart.status ?? "unknown")',
  'stringValue(value) ?? "unknown"',
  'String(record.headline ?? "今日判断暂不可用")',
  'String(record.status ?? "unknown")',
  'String(record.stance ?? "neutral")',
  'text === "unknown"',
  'value === "unknown"',
  'key.split(":").at(-1)',
  'data-severity={item.severity ?? "unknown"}',
  "gapCodeLabel(",
  "GAP_CODE_TERMS",
  "最新宏观观测滞后",
  ".split(/[:_]+/u)",
  'diagnostics.statusLabel ?? "正常"',
  "module.data_health.summary_label ?? module.data_health.summary_status",
  "view.diagnostics.sourceMeta ?? `${sourceCount} 个来源`",
  "stringValue(module.snapshot.status_label) ?? stringValue(module.snapshot.status)",
  "stringValue(module.data_health.summary_label) ??\n      stringValue(module.data_health.summary_status)",
  "TITLE_BY_ID",
  "labelFromIdentifier",
  "WORD_LABELS",
  '.split("_")',
  "node.label ?? node.kind",
  "node.value ?? node.status_label ?? node.status",
  '`${node.label ?? node.kind ?? "node"}:${index}`',
  "`${group.key}:${item.label}:${index}`",
  "String(table.id ?? index)",
  'return explicit ?? "ok";',
  "`${tenorYears}Y`",
  'stringValue(diagnostics.label) ?? "政策走廊诊断"',
  'stringValue(diagnostics.label) ?? "曲线诊断"',
  'stringValue(diagnostics.label) ?? "实际利率诊断"',
  "readHeadline ?? `${ratesTitle(module, moduleId)}：${readinessLabel(readiness)}`",
  "neutralFallbackExplanation(",
  "marketExplanation:",
  "fallback={readSummary}",
  "textValue(brief?.headline) ?? fallback",
  "label ?? `${data.window} 资产相关性矩阵`",
  "meta ?? `${drivers.evidenceCount} 条证据`",
  "fallbackAsOf",
  "存在降级原因",
  'displayText(reason, "存在降级原因")',
  "CORRIDOR_LABELS[CORRIDOR_SERIES_BY_CONCEPT[concept]] ?? concept",
  "stringValue(row.label) ??",
  "stringValue(row.source) ??",
  "stringValue(row.name)",
  "label ?? symbol ?? key",
  '? value : "info"',
  "row.raw.row_id ?? row.raw.concept_key ?? row.id",
  "stringValue(module.data_health.summary_status) ?? stringValue(module.snapshot.status)",
  "stringValue(module.data_health.summary_label) ?? macroStatusLabel(module)",
  "snapshotTime(",
  'return "insufficient_history";',
];

const retiredTradeMapCodeListTokens = [
  "confirms_on",
  "invalidates_on",
  "confirms: codeList(",
  "invalidates: codeList(",
];

const retiredScenarioSignalDisplayTokens = ["signalLabel(", "SIGNAL_LABELS"];
const retiredTradeMapExpressionLabelTokens = ["tradeExpressionLabel(", "TRADE_EXPRESSION_LABELS"];
const retiredChecklistKindLabelTokens = ["checklistKindLabel(", "CHECKLIST_KIND_LABELS"];
const retiredEventKindSourceLabelTokens = ["eventKindLabel("];
const retiredWatchlistKindLabelTokens = ["watchlistKindLabel("];
const retiredSeverityLabelTokens = ["severityLabel("];
const retiredSectionLabelTokens = ["sectionLabel("];
const retiredTradeMapOutcomeLabelTokens = ["outcomeLabel("];
const retiredWatchlistAssetSymbolLabelFallbackTokens = ["const displayLabel = label ?? symbol"];
const retiredWorkbenchBriefRawRegimeFallbackTokens = ['{ key: "regime", label: "状态" }'];
const retiredDecisionConsoleCodeIdentityFallbackTokens = [
  "stringValue(item.key) ?? stringValue(item.code)",
];
const retiredRatesConceptLabelTokens = ["CONCEPT_LABELS", "humanizeRatesConceptKey("];
const retiredRatesGapLabelTokens = ["GAP_LABELS"];
const retiredRatesReadinessLabelTokens = [
  "function readinessLabel(",
  "readinessLabel(readiness)",
  "labels: Record<RatesReadiness",
];
const retiredRatesFactQualityFallbackTokens = ["tile.quality_label ?? tile.quality"];
const retiredRatesFactObservedAtFallbackTokens = ["tile.observed_at_label ?? tile.observed_at"];
const retiredRatesFactValueFallbackTokens = ["formatMacroScalar(tile.display_value ?? tile.value)"];
const retiredRatesFactInterpretationFallbackTokens = ["tile.description ?? tile.delta_label"];
const retiredRatesDecisionDescriptionFallbackTokens = [
  "detail: sanitizeOptionalText(item.description)",
];
const retiredRatesChartNoteStatusFallbackTokens = [
  "module.primary_chart.subtitle ?? module.primary_chart.status_label",
];
const retiredMacroPageStatusLabelTokens = ["STATUS_LABELS", "knownStatusLabel(", "scalarLabel("];
const retiredMacroFieldKeyLabelFallbackTokens = ["FIELD_LABELS[key] ?? key"];
const retiredMacroFieldKeyLabelMapTokens = ["const FIELD_LABELS", "macroFieldLabel("];
const retiredSourceTableStatusLabelTokens = ["const STATUS_LABELS", "STATUS_LABELS[status]"];
const retiredSourceTableProviderLabelTokens = ["SOURCE_LABELS", "SOURCE_LABELS[raw]"];
const retiredSourceTableScoreParticipationLabelTokens = [
  "scoreParticipationLabel(",
  'return "参与计分";',
  'return "计分排除";',
];
const retiredSourceTableObservedTimestampFallbackTokens = [
  "observedAtLabel(row.observed_at_ms)",
  "function observedAtLabel(",
];
const retiredSourceTableMessageFallbackTokens = [
  "stringValue(row.notes) ?? stringValue(row.message)",
];
const retiredSourceTableDegradedReasonsNotesFallbackTokens = [
  "row.degraded_reasons",
  "const degradedReasons = Array.isArray(row.degraded_reasons)",
];
const retiredTableScalarStatusLabelTokens = ["VALUE_LABELS", "VALUE_LABELS[text]"];
const retiredMacroTableObjectDisplayFallbackTokens = [
  "stringValue(record.display_value) ??\n    stringValue(record.label) ??\n    stringValue(record.title)",
];
const retiredMacroTableDisplayCellRawValueFallbackTokens = [
  "const rawValue = sortValue ?? scalarValue(value.display_value)",
];
const retiredGenericObjectScalarDisplayFallbackTokens = [
  "formatMacroScalar(record.display_value ?? record.label ?? record.title)",
];
const retiredMacroScalarBooleanLabelTokens = ['typeof value === "boolean"', 'value ? "是" : "否"'];
const retiredGapTitleDisplayFallbackTokens = [
  "stringValue(record.display_value) ?? stringValue(record.label) ?? stringValue(record.title)",
];
const retiredGapDisplayValueLabelFallbackTokens = [
  "return stringValue(record.display_value) ?? stringValue(record.label)",
];
const retiredMacroModuleTitleRouteLabelFallbackTokens = [
  "stringValue(module?.snapshot.title) || macroRouteLabel(moduleId)",
];
const retiredMacroLeafPageRouteLabelMetadataTokens = ["macroRouteLabel(moduleId)"];
const retiredMacroOverviewStaticPageMetadataTokens = ['label="总览模块页面"', 'meta="总览"'];
const retiredMacroAssetStaticPageMetadataTokens = ['label="大类资产模块页面"'];
const retiredMacroSnapshotAsOfDateFallbackTokens = [
  "dateAsOfLabel(",
  "module.snapshot.asof_label) ?? stringValue(module.snapshot.asof_date)",
];
const retiredMacroFreshnessLabelInferenceTokens = ['label.includes("滞后")'];
const retiredDataCredibilityObservedAtFallbackTokens = [
  "stringValue(item.observed_at) ?? stringValue(item.observed_at_label)",
];
const retiredFutureCatalystWindowFallbackTokens = [
  "stringValue(item.window_label) ?? stringValue(item.window)",
];
const retiredFutureCatalystDescriptionFallbackTokens = [
  "function futureCatalystItem(item: MacroSemanticRecord): MacroDecisionFutureCatalystItem | null {\n  const key = stringValue(item.key);\n  if (!key) {\n    return null;\n  }\n  const label = stringValue(item.label);\n  const detail = stringValue(item.description);",
];
const retiredWatchlistRuleWindowFallbackTokens = [
  "stringValue(item.kind_label),\n    stringValue(item.window),\n    stringValue(item.severity_label),",
];
const retiredWatchlistRuleDescriptionFallbackTokens = [
  "function watchlistRuleItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {\n  const key = stringValue(item.key);\n  if (!key) {\n    return null;\n  }\n  const label = stringValue(item.label);\n  const detail = formattedScalarValue(item.description);",
];
const retiredDecisionConsoleTimeWindowFallbackTokens = [
  "stringValue(item.probability_label), stringValue(item.time_window)",
  "stringValue(item.time_window),\n    stringValue(item.severity_label),",
  "window: stringValue(item.time_window)",
];
const retiredMarketEventFlowWindowFallbackTokens = [
  "stringValue(item.source),\n    stringValue(item.category_label),\n    stringValue(item.impact_label),\n    stringValue(item.window),",
];
const retiredMetricTileRawValueFallbackTokens = [
  "formattedScalarValue(tile.display_value ?? tile.value)",
];
const retiredMetricTileObservedAtFallbackTokens = [
  "stringValue(tile.observed_at_label) ??\n      stringValue(tile.quality_label) ??\n      stringValue(tile.delta_label)",
];
const retiredDataHealthGapDescriptionFallbackTokens = [
  "stringValue(record.remediation_hint) ??\n      stringValue(record.detail) ??\n      stringValue(record.description)",
];
const retiredDataHealthGapDetailFallbackTokens = [
  "detail: stringValue(record.remediation_hint) ?? stringValue(record.detail)",
];
const retiredModuleEvidenceDescriptionFallbackTokens = [
  "const detail = formattedScalarValue(item.description);",
];
const retiredModuleEvidenceKeyIdentityFallbackTokens = [
  "const key = stringValue(item.code) ?? stringValue(item.key)",
];
const retiredModuleReadRegimeSummaryFallbackTokens = [
  "[read.headline, read.summary, read.regime_label]",
];
const retiredAssetOverviewRawMetaFallbackTokens = [
  "textValue(module.snapshot.asof_date) ?? textValue(module.snapshot.asof_label)",
  "record.asof_date ?",
  'record.window ?? "相关性"',
];
const retiredMarketBoardChartStatusFallbackTokens = ["chart.status_label ??", "chart.status ==="];
const retiredMarketBoardSourceDescriptionFallbackTokens = [
  "source?.notes ?? source?.description ?? null",
];
const retiredMarketBoardTitleDefaultTokens = ['title = "市场板"'];
const retiredMacroChartSeriesTitleFallbackTokens = [
  "stringValue(record.label) ?? stringValue(record.short_label) ?? stringValue(record.title)",
];
const retiredMacroChartPayloadMetadataFallbackTokens = [
  "statusLabel: stringValue(series.status_label) ?? stringValue(payload?.status_label)",
  "unit: stringValue(series.unit ?? payload?.unit)",
  "return stringValue(series.status) ?? stringValue(payload?.status);",
];
const retiredMacroChartPayloadPointCountFallbackTokens = [
  "integerValue(series.point_count) ?? normalizedPoints.length",
];
const retiredMacroChartLegacyLatestValueFallbackTokens = [
  "numericValue(series.latest_value)",
  "numericValue(series.value)",
];
const retiredMacroChartInlinePointsFallbackTokens = [
  "normalizeSeriesPoints(inlineSeriesPoints(series))",
  "function inlineSeriesPoints(",
  "latestInlinePointValue(series)",
];
const retiredRatesChartInlinePointsFallbackTokens = [
  "normalizeSeriesPoints(inlineSeriesPoints(series))",
  "inlinePoints.at(-1)?.value",
  "function inlineSeriesPoints(",
];
const retiredRatesChartPayloadMetadataFallbackTokens = [
  "unit: stringValue(series.unit) ?? stringValue(payload?.unit)",
  "numericValue(series.latest_value)",
  "numericValue(series.value)",
  "numericValue(payload?.latest_value)",
];
const retiredRatesCorridorSeriesLabelFallbackTokens = ["label: CORRIDOR_LABELS[key]"];
const retiredRatesCorridorPlaceholderTokens = ['return "n/a";'];
const retiredDecisionEvidenceDescriptionFallbackTokens = [
  "formattedScalarValue(stringValue(item.evidence_label) ?? item.description)",
  "function evidenceItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {\n  const key = stringValue(item.code);\n  if (!key) {\n    return null;\n  }\n  const label = stringValue(item.label);\n  const detail = formattedScalarValue(item.description);",
];
const retiredDecisionQualityDescriptionFallbackTokens = [
  "function qualityItem(item: MacroSemanticRecord): MacroDecisionConsoleItem | null {\n  const key = stringValue(item.code);\n  const label = stringValue(item.label);\n  const detail = formattedScalarValue(item.description);",
  "const detail = formattedScalarValue(item.description);\n  if (!key || !label || !detail) {\n    return null;\n  }\n  return {\n    detail,\n    key,\n    label,\n    meta: stringValue(item.severity_label)",
];
const retiredDecisionEvidenceMetaFallbackTokens = [
  "stringValue(item.meta) ?? stringValue(item.node_label)",
];
const retiredDecisionTopChangeNodeMetaTokens = [
  "stringValue(item.node_label),\n    stringValue(item.severity_label)",
];
const retiredRatesDiagnosticsLabelTokens = ["function severityLabel(", "function scopeLabel("];
const retiredRatesGapDisplayValueLabelFallbackTokens = [
  "readableText(gap.label) ?? readableText(gap.display_value)",
];
const retiredRatesCurveHistorySummaryFallbackTokens = [
  "numberValue(series.latest_bp) ?? points[points.length - 1]?.value",
  "numberValue(series.min_bp) ?? Math.min(...points.map((point) => point.value))",
  "numberValue(series.max_bp) ?? Math.max(...points.map((point) => point.value))",
];
const retiredMacroDiagnosticsLabelTokens = [
  "function gapMeta(",
  "function severityLabel(",
  "function scopeLabel(",
];
const retiredMacroChartStatePlaceholderTokens = ['"历史样本不足"'];
const retiredMacroChartSeriesStateFallbackTokens = [
  'model.series.find((series) => series.status === "insufficient_history")?.statusLabel',
];
const retiredMacroChartLegendPlaceholderTokens = ['? "n/a"', "model.series.map((series)"];
const retiredMacroHeatmapSurfaceTokens = [
  "MacroHeatmap",
  "buildMacroHeatmapMatrix",
  "MacroHeatmapMatrix",
  "macro-heatmap",
];
const retiredMacroCorrelationPlaceholderTokens = ['return "-"', '?? "-"', " 至 "];
const retiredMacroMarketEventFlowFallbackTokens = ["row.meta ?? row.date"];
const retiredAssetDiagnosticsLabelTokens = [
  "function gapMeta(",
  "function severityLabel(",
  "function scopeLabel(",
];
const retiredAssetDailyBriefStanceLabelTokens = ["stanceLabel(", "normalized.includes("];
const retiredAssetDailyBriefQualityFallbackTokens = ['"样本不足"'];
const retiredAssetDailyBriefBlockCoercionTokens = [
  'String(record.id ?? "")',
  'String(record.title ?? "")',
  'String(record.body ?? "")',
];
const retiredMacroPlaceholderValueTokens = ['"暂无"', 'value === "暂无"', 'text === "暂无"'];
const retiredAssetRawFieldFallbackTokens = [
  "row.raw.symbol",
  "row.raw.ticker",
  "row.raw.latest_observed_at",
  "row.raw.observed_at",
  "row.raw.date",
];
const retiredAssetMarketDeltaFallbackTokens = [
  'return displayCell(row, "delta_1d") ?? displayCell(row, "delta_20d")',
  "row.cells.delta_1d?.sortValue ?? row.cells.delta_20d?.sortValue",
];
const retiredAssetMarketGenericDateFallbackTokens = [
  'return firstDisplayCell(row, ["observed_at", "latest_observed_at", "date", "asof_date"])',
];
const retiredAssetMarketTwentyDayHeaderTokens = ['<th scope="col">20日变化</th>'];
const retiredAssetMarketSourceQualityFallbackTokens = [
  "const source = row.cells.source?.displayValue;",
  "return `${quality} · ${source}`;",
  'if (source && source !== "暂无") return source;',
];
const retiredMacroRouteDescriptorDefaultTokens = [
  'pageKind: descriptor?.pageKind ?? "overview"',
  'productTier: descriptor?.productTier ?? "primary"',
];
const retiredMacroShellHeaderQuestionTokens = [
  "question?: string | null;",
  "question: module.snapshot.question ?? module.snapshot.subtitle ?? null",
  "question: module.snapshot.question ?? null",
  "question: null,",
];
const retiredMacroShellEyebrowFallbackTokens = [
  'eyebrow: module.snapshot.section ?? "宏观工作台"',
  'eyebrow: "Assets"',
  'eyebrow: "利率工作台"',
];
const retiredRatesScaffoldLabelFallbackTokens = ["`${view.title}利率工作台`"];
const retiredRatesPrimaryChartMetaFallbackTokens = ["meta={view.chartNote ?? view.readinessLabel}"];
const retiredRatesMarketReadEyebrowTokens = ["macro-rates-eyebrow", "{view.title ? <p"];
const retiredRatesProxyNoteTokens = ["proxyNote", "macro-rates-proxy-note"];
const retiredMacroDiagnosticsHeaderMetaFallbackTokens = [
  "meta={diagnostics.statusLabel ?? diagnostics.sourceMeta}",
];
const retiredRatesWorkbenchQuestionTokens = [
  "question: string;",
  "question: ratesQuestion(module, moduleId)",
  "function ratesQuestion(",
  "RATES_PAGE_COPY[moduleId].question",
  'question: "政策走廊是否稳定',
  'question: "曲线是在交易',
  'question: "实际利率是在压制',
];
const retiredRatesWorkbenchTitleFallbackTokens = [
  "RATES_PAGE_COPY",
  "function ratesTitle(module: MacroModuleView, moduleId: RatesModuleId)",
  'title: "联邦基金与走廊"',
  'title: "收益率曲线"',
  'title: "实际利率"',
];

describe("macro model hard cut", () => {
  it("does not restore frontend synthetic identity or asset label fallbacks", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredIdentityFallbackTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore macro trade-map code-list display contracts", () => {
    const offenders = [...collectSourceFiles(macroRoot), frontendContracts].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredTradeMapCodeListTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend scenario signal code-label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredScenarioSignalDisplayTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend trade-map expression label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredTradeMapExpressionLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend checklist kind label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredChecklistKindLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend event-kind source label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredEventKindSourceLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend watchlist kind label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredWatchlistKindLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore watchlist asset symbol label fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredWatchlistAssetSymbolLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore workbench brief raw regime fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredWorkbenchBriefRawRegimeFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore decision-console code identity fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDecisionConsoleCodeIdentityFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend workbench severity label maps", () => {
    const offenders = [macroWorkbenchModel].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredSeverityLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend workbench section label maps", () => {
    const offenders = [macroWorkbenchModel].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredSectionLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend trade-map outcome label maps", () => {
    const offenders = [macroWorkbenchModel].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredTradeMapOutcomeLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates concept label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesConceptLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates gap label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesGapLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates readiness label maps", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesReadinessLabelTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates fact quality code fallbacks", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesFactQualityFallbackTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates fact observed-date fallbacks", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesFactObservedAtFallbackTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates fact raw value fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesFactValueFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend rates fact delta-label interpretation fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesFactInterpretationFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates decision description detail fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesDecisionDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates chart status-label note fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesChartNoteStatusFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates gap display-value label fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesGapDisplayValueLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates curve history summary fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesCurveHistorySummaryFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro page status code label maps", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredMacroPageStatusLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro field-key display fallbacks", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredMacroFieldKeyLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore frontend macro field-key label maps", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredMacroFieldKeyLabelMapTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore source table status code label maps", () => {
    const source = readFileSync(macroSourceTable, "utf8");
    const offenders = retiredSourceTableStatusLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroSourceTable)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore source table provider code label maps", () => {
    const source = readFileSync(macroSourceTable, "utf8");
    const offenders = retiredSourceTableProviderLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroSourceTable)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore source table score-participation boolean label maps", () => {
    const source = readFileSync(macroSourceTable, "utf8");
    const offenders = retiredSourceTableScoreParticipationLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroSourceTable)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore source table observed-timestamp display fallbacks", () => {
    const source = readFileSync(macroSourceTable, "utf8");
    const offenders = retiredSourceTableObservedTimestampFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroSourceTable)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore source table message-as-notes fallbacks", () => {
    const source = readFileSync(macroSourceTable, "utf8");
    const offenders = retiredSourceTableMessageFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroSourceTable)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore source table degraded-reasons-as-notes fallbacks", () => {
    const source = readFileSync(macroSourceTable, "utf8");
    const offenders = retiredSourceTableDegradedReasonsNotesFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroSourceTable)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore table scalar status code label maps", () => {
    const source = readFileSync(macroTableColumns, "utf8");
    const offenders = retiredTableScalarStatusLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroTableColumns)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro table object label or title display fallbacks", () => {
    const source = readFileSync(macroTableColumns, "utf8");
    const offenders = retiredMacroTableObjectDisplayFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroTableColumns)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro table display-cell raw-value fallbacks", () => {
    const source = readFileSync(macroTableColumns, "utf8");
    const offenders = retiredMacroTableDisplayCellRawValueFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroTableColumns)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore generic macro object scalar label or title fallbacks", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredGenericObjectScalarDisplayFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro scalar boolean label maps", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredMacroScalarBooleanLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore data-health gap title display fallbacks", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredGapTitleDisplayFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore data-health gap display-value label fallbacks", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredGapDisplayValueLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro module-title route-label fallbacks", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredMacroModuleTitleRouteLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro leaf page route-label metadata fallbacks", () => {
    const source = readFileSync(macroLeafModulePage, "utf8");
    const offenders = retiredMacroLeafPageRouteLabelMetadataTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroLeafModulePage)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro overview static page metadata fallbacks", () => {
    const source = readFileSync(macroOverviewModulePage, "utf8");
    const offenders = retiredMacroOverviewStaticPageMetadataTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroOverviewModulePage)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro assets static page metadata fallbacks", () => {
    const source = readFileSync(macroAssetOverviewPage, "utf8");
    const offenders = retiredMacroAssetStaticPageMetadataTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewPage)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro snapshot as-of date display fallbacks", () => {
    const offenders = [macroPageViewModel, macroWorkbenchModel].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredMacroSnapshotAsOfDateFallbackTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore macro freshness inference from display labels", () => {
    const source = readFileSync(macroPageViewModel, "utf8");
    const offenders = retiredMacroFreshnessLabelInferenceTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroPageViewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore data credibility observed-date display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDataCredibilityObservedAtFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore future catalyst raw window display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredFutureCatalystWindowFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore future catalyst description display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredFutureCatalystDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore watchlist rule raw window display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredWatchlistRuleWindowFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore watchlist rule description display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredWatchlistRuleDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore decision-console raw time-window display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDecisionConsoleTimeWindowFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore market event flow raw window display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredMarketEventFlowWindowFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore metric tile raw value display fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredMetricTileRawValueFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore metric tile quality or delta observed-at fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredMetricTileObservedAtFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore data-health gap description detail fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredDataHealthGapDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore data-health gap generic detail remediation fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredDataHealthGapDetailFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore module evidence description detail fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredModuleEvidenceDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore module evidence key identity fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredModuleEvidenceKeyIdentityFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore module regime-label read-summary fallbacks", () => {
    const source = readFileSync(macroModulePresentation, "utf8");
    const offenders = retiredModuleReadRegimeSummaryFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroModulePresentation)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset overview raw date or window meta fallbacks", () => {
    const source = readFileSync(macroAssetOverviewPage, "utf8");
    const offenders = retiredAssetOverviewRawMetaFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewPage)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore market-board chart status fallback labels", () => {
    const source = readFileSync(macroMarketBoard, "utf8");
    const offenders = retiredMarketBoardChartStatusFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroMarketBoard)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore market-board source description note fallbacks", () => {
    const source = readFileSync(macroMarketBoard, "utf8");
    const offenders = retiredMarketBoardSourceDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroMarketBoard)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore market-board default title fallbacks", () => {
    const source = readFileSync(macroMarketBoard, "utf8");
    const offenders = retiredMarketBoardTitleDefaultTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroMarketBoard)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart series title label fallbacks", () => {
    const source = readFileSync(macroChartModel, "utf8");
    const offenders = retiredMacroChartSeriesTitleFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart payload metadata display fallbacks", () => {
    const source = readFileSync(macroChartModel, "utf8");
    const offenders = retiredMacroChartPayloadMetadataFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart payload point-count fallbacks", () => {
    const source = readFileSync(macroChartModel, "utf8");
    const offenders = retiredMacroChartPayloadPointCountFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart legacy latest-value fallbacks", () => {
    const source = readFileSync(macroChartModel, "utf8");
    const offenders = retiredMacroChartLegacyLatestValueFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart v2 inline point fallbacks", () => {
    const source = readFileSync(macroChartModel, "utf8");
    const offenders = retiredMacroChartInlinePointsFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates corridor v2 inline point fallbacks", () => {
    const source = readFileSync(macroRatesChartModel, "utf8");
    const offenders = retiredRatesChartInlinePointsFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates corridor payload metadata fallbacks", () => {
    const source = readFileSync(macroRatesChartModel, "utf8");
    const offenders = retiredRatesChartPayloadMetadataFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates corridor local series-label fallbacks", () => {
    const source = readFileSync(macroRatesChartModel, "utf8");
    const offenders = retiredRatesCorridorSeriesLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesChartModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates corridor legend placeholder values", () => {
    const source = readFileSync(join(macroRoot, "ui/rates/RatesCorridorChart.tsx"), "utf8");
    const offenders = retiredRatesCorridorPlaceholderTokens
      .filter((token) => source.includes(token))
      .map((token) => `src/features/macro/ui/rates/RatesCorridorChart.tsx contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore decision evidence description display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDecisionEvidenceDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore decision quality-blocker description display fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDecisionQualityDescriptionFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore decision evidence node-label meta fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDecisionEvidenceMetaFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore decision top-change section-label meta fallbacks", () => {
    const source = readFileSync(macroWorkbenchModel, "utf8");
    const offenders = retiredDecisionTopChangeNodeMetaTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates diagnostics severity or scope label maps", () => {
    const source = readFileSync(ratesDiagnosticsPanel, "utf8");
    const offenders = retiredRatesDiagnosticsLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, ratesDiagnosticsPanel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro diagnostics severity or scope label maps", () => {
    const source = readFileSync(macroDiagnosticsPanel, "utf8");
    const offenders = retiredMacroDiagnosticsLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroDiagnosticsPanel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart state placeholder labels", () => {
    const source = readFileSync(macroTimeSeriesChart, "utf8");
    const offenders = retiredMacroChartStatePlaceholderTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroTimeSeriesChart)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart series-status state fallbacks", () => {
    const source = readFileSync(macroTimeSeriesChart, "utf8");
    const offenders = retiredMacroChartSeriesStateFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroTimeSeriesChart)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro chart legend placeholder or hidden-series rows", () => {
    const source = readFileSync(macroTimeSeriesChart, "utf8");
    const offenders = retiredMacroChartLegendPlaceholderTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroTimeSeriesChart)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore the orphan macro heatmap surface", () => {
    const files = [...collectSourceFiles(macroRoot), join(macroRoot, "ui/charts/macroCharts.css")];
    const offenders = files.flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredMacroHeatmapSurfaceTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore macro correlation placeholder labels", () => {
    const offenders = [macroCorrelationModel, macroCorrelationTables].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredMacroCorrelationPlaceholderTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore macro market-event date meta fallbacks", () => {
    const source = readFileSync(macroMarketEventFlowPanel, "utf8");
    const offenders = retiredMacroMarketEventFlowFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroMarketEventFlowPanel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset daily-brief stance code label maps", () => {
    const source = readFileSync(assetDailyBrief, "utf8");
    const offenders = retiredAssetDailyBriefStanceLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, assetDailyBrief)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset daily-brief quality placeholder fallbacks", () => {
    const source = readFileSync(assetDailyBrief, "utf8");
    const offenders = retiredAssetDailyBriefQualityFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, assetDailyBrief)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset daily-brief block display-field coercion", () => {
    const source = readFileSync(macroAssetOverviewModel, "utf8");
    const offenders = retiredAssetDailyBriefBlockCoercionTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro placeholder string value handling", () => {
    const offenders = collectSourceFiles(macroRoot).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredMacroPlaceholderValueTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore asset market raw-field display fallbacks", () => {
    const source = readFileSync(macroAssetOverviewModel, "utf8");
    const offenders = retiredAssetRawFieldFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset market 20-day delta as daily-change fallback", () => {
    const source = readFileSync(macroAssetOverviewModel, "utf8");
    const offenders = retiredAssetMarketDeltaFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset market generic date display fallbacks", () => {
    const source = readFileSync(macroAssetOverviewModel, "utf8");
    const offenders = retiredAssetMarketGenericDateFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset market 20-day table headers for daily deltas", () => {
    const source = readFileSync(macroAssetOverviewPage, "utf8");
    const assetMarketDashboard = join(macroRoot, "ui/assets/AssetMarketDashboard.tsx");
    const dashboardSource = readFileSync(assetMarketDashboard, "utf8");
    const offenders = retiredAssetMarketTwentyDayHeaderTokens
      .filter((token) => source.includes(token) || dashboardSource.includes(token))
      .map((token) => `${relative(webRoot, assetMarketDashboard)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset market source-as-quality fallbacks", () => {
    const source = readFileSync(macroAssetOverviewModel, "utf8");
    const offenders = retiredAssetMarketSourceQualityFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroAssetOverviewModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore macro route descriptor default fallbacks", () => {
    const source = readFileSync(macroRoutesModel, "utf8");
    const offenders = retiredMacroRouteDescriptorDefaultTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRoutesModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore unused macro shell header question wiring", () => {
    const sources = [macroShell, macroWorkbenchRoute];
    const offenders = sources.flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredMacroShellHeaderQuestionTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore macro shell eyebrow fallback copy", () => {
    const source = readFileSync(macroWorkbenchRoute, "utf8");
    const offenders = retiredMacroShellEyebrowFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroWorkbenchRoute)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates workbench scaffold label copy", () => {
    const macroRatesModulePage = join(macroRoot, "ui/rates/MacroRatesModulePage.tsx");
    const source = readFileSync(macroRatesModulePage, "utf8");
    const offenders = retiredRatesScaffoldLabelFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesModulePage)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates primary-chart readiness meta fallbacks", () => {
    const source = readFileSync(ratesPrimaryVisual, "utf8");
    const offenders = retiredRatesPrimaryChartMetaFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, ratesPrimaryVisual)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates market-read module-title eyebrow copy", () => {
    const offenders = [ratesMarketRead, ratesWorkbenchCss].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesMarketReadEyebrowTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore rates proxy-note compatibility display", () => {
    const offenders = [
      macroRatesWorkbenchModel,
      ratesMarketRead,
      ratesPrimaryVisual,
      ratesWorkbenchCss,
    ].flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return retiredRatesProxyNoteTokens
        .filter((token) => source.includes(token))
        .map((token) => `${relative(webRoot, path)} contains ${token}`);
    });

    expect(offenders).toEqual([]);
  });

  it("does not restore macro diagnostics source-count header meta fallbacks", () => {
    const source = readFileSync(macroDiagnosticsPanel, "utf8");
    const offenders = retiredMacroDiagnosticsHeaderMetaFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroDiagnosticsPanel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore unused rates workbench question wiring", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesWorkbenchQuestionTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore rates workbench title page-copy fallbacks", () => {
    const source = readFileSync(macroRatesWorkbenchModel, "utf8");
    const offenders = retiredRatesWorkbenchTitleFallbackTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, macroRatesWorkbenchModel)} contains ${token}`);

    expect(offenders).toEqual([]);
  });

  it("does not restore asset diagnostics severity or scope label maps", () => {
    const source = readFileSync(assetDiagnosticsBoard, "utf8");
    const offenders = retiredAssetDiagnosticsLabelTokens
      .filter((token) => source.includes(token))
      .map((token) => `${relative(webRoot, assetDiagnosticsBoard)} contains ${token}`);

    expect(offenders).toEqual([]);
  });
});
