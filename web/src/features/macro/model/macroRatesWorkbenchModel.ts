import type { MacroModuleTable, MacroModuleView, MacroSemanticRecord } from "@lib/types";

import { chartCaption } from "./macroModulePageModel";
import { formatMacroScalar, macroAsOfLabel, macroStatusLabel } from "./macroPageViewModel";
import { type MacroModuleId } from "./macroRoutes";

export const RATES_MODULE_IDS = [
  "rates/fed-funds",
  "rates/yield-curve",
  "rates/auctions",
  "rates/real-rates",
  "rates/expectations",
] as const;

export type RatesModuleId = (typeof RATES_MODULE_IDS)[number];
export type RatesReadiness = "ready" | "partial" | "proxy" | "stale" | "missing";

export type RatesFact = {
  key: string;
  label: string;
  value: string;
  observedAtLabel: string;
  sourceLabel: string | null;
  statusLabel: string | null;
  interpretation: string | null;
};

export type RatesGapSummary = {
  key: string;
  label: string;
  severity: "info" | "warning" | "critical";
};

export type RatesDecisionGroup = {
  key: "confirmations" | "contradictions" | "watch_triggers" | "invalidations";
  label: string;
  items: Array<{ label: string; detail: string }>;
};

export type RatesDetailTable = {
  role: "primary" | "diagnostic";
  table: MacroModuleTable;
};

export type RatesWorkbenchView = {
  moduleId: RatesModuleId;
  title: string;
  question: string;
  readiness: RatesReadiness;
  readinessLabel: string;
  marketHeadline: string;
  marketExplanation: string;
  asOfLabel: string;
  facts: RatesFact[];
  missingPrimaryItems: string[];
  proxyNote: string | null;
  chartTitle: string;
  chartNote: string | null;
  decisionGroups: RatesDecisionGroup[];
  detailTables: RatesDetailTable[];
  diagnostics: {
    coverage: RatesGapSummary[];
    sourceMeta: string | null;
    moduleHealthLabel: string;
    globalGapReferenceCount: number;
  };
};

const RATES_PAGE_COPY: Record<
  RatesModuleId,
  { title: string; question: string; proxyHeadline?: string }
> = {
  "rates/fed-funds": {
    title: "联邦基金与走廊",
    question: "政策走廊是否稳定，隔夜融资是否溢出目标区间？",
  },
  "rates/yield-curve": {
    title: "收益率曲线",
    question: "曲线是在交易衰退压力，还是期限溢价？",
  },
  "rates/auctions": {
    title: "国债拍卖",
    question: "拍卖供给压力是否体现在曲线和长端收益率上？",
    proxyHeadline: "当前为拍卖代理页面：官方拍卖日历和结果尚未入库。",
  },
  "rates/real-rates": {
    title: "实际利率",
    question: "实际利率是在压制估值，还是通胀补偿主导？",
  },
  "rates/expectations": {
    title: "政策预期",
    question: "市场是否在重新定价降息、维持或加息路径？",
    proxyHeadline: "当前为政策路径代理页面，不能生成正式降息概率。",
  },
};

const DECISION_GROUPS = [
  { key: "confirmations", label: "确认" },
  { key: "contradictions", label: "反证" },
  { key: "watch_triggers", label: "观察触发" },
  { key: "invalidations", label: "失效条件" },
] as const;

const AUCTION_PROXY_GAPS = new Set([
  "treasury_auction_calendar_missing",
  "treasury_auction_results_missing",
]);
const EXPECTATIONS_PROXY_GAPS = new Set([
  "fed_funds_futures_missing",
  "fomc_probability_feed_missing",
]);

const CONCEPT_LABELS: Record<string, string> = {
  "fed:target_lower": "目标下限",
  "fed:target_upper": "目标上限",
  "fed:effr": "EFFR",
  "fed:iorb": "IORB",
  "fed:sofr_30d": "SOFR 30D",
  "liquidity:sofr": "SOFR",
  "rates:dgs2": "2年期美债收益率",
  "rates:dgs5": "5年期美债收益率",
  "rates:dgs10": "10年期美债收益率",
  "rates:dgs30": "30年期美债收益率",
  "rates:real_5y": "5年期实际利率",
  "rates:real_10y": "10年期实际利率",
  "inflation:breakeven_10y": "10年期通胀补偿",
  "fed:next_meeting_hold_probability": "下次会议维持概率",
  "fed:next_meeting_cut_probability": "下次会议降息概率",
  "treasury:bid_to_cover": "投标覆盖倍数",
  "treasury:next_auction_size": "下一场拍卖规模",
};

const GAP_LABELS: Record<string, string> = {
  "insufficient_history:60d": "历史样本不足：无法计算 60 日变化",
  fed_funds_futures_missing: "联邦基金期货数据尚未入库",
  fomc_probability_feed_missing: "FOMC 概率数据尚未入库",
  sofr_30d_missing: "SOFR 30D 尚未入库",
  treasury_auction_calendar_missing: "官方拍卖日历尚未入库",
  treasury_auction_results_missing: "官方拍卖结果尚未入库",
};

export function isRatesModuleId(moduleId: MacroModuleId): moduleId is RatesModuleId {
  return (RATES_MODULE_IDS as readonly string[]).includes(moduleId);
}

export function buildRatesWorkbenchView(
  module: MacroModuleView,
  moduleId: RatesModuleId,
): RatesWorkbenchView {
  const proxyHeadline = proxyHeadlineForModule(module, moduleId);
  const readiness = proxyHeadline ? "proxy" : readinessFromModule(module);
  const readHeadline = readableText(module.module_read.headline);
  const marketHeadline = sanitizePrimaryText(
    proxyHeadline ??
      readHeadline ??
      `${ratesTitle(module, moduleId)}：${readinessLabel(readiness)}`,
  );
  const marketExplanation = sanitizePrimaryText(
    readableText(module.module_read.crypto_read) ??
      readableText(module.module_read.token_impact) ??
      neutralFallbackExplanation(moduleId),
  );

  return {
    moduleId,
    title: ratesTitle(module, moduleId),
    question: ratesQuestion(module, moduleId),
    readiness,
    readinessLabel: readinessLabel(readiness),
    marketHeadline,
    marketExplanation,
    asOfLabel: sanitizePrimaryText(macroAsOfLabel(module)),
    facts: module.tiles.map(buildRatesFact),
    missingPrimaryItems: missingPrimaryItems(module),
    proxyNote: proxyHeadline ? sanitizePrimaryText(proxyHeadline) : null,
    chartTitle: sanitizePrimaryText(chartCaption(module.primary_chart)),
    chartNote: chartNote(module),
    decisionGroups: decisionGroups(module.module_evidence),
    detailTables: detailTables(module, moduleId, readiness),
    diagnostics: {
      coverage: gapSummaries(module),
      sourceMeta: sourceMeta(module.provenance),
      moduleHealthLabel: sanitizePrimaryText(
        stringValue(module.data_health.summary_label) ?? macroStatusLabel(module),
      ),
      globalGapReferenceCount: module.data_health.global_gaps.length,
    },
  };
}

export function humanizeRatesConceptKey(conceptKey: string): string {
  const mapped = CONCEPT_LABELS[conceptKey];
  if (mapped) {
    return mapped;
  }
  const [, rawName = conceptKey] = conceptKey.split(":");
  return rawName
    .split(/[_\-.]+/)
    .filter(Boolean)
    .map((part) => (part.length <= 4 ? part.toUpperCase() : part))
    .join(" ");
}

export function humanizeRatesGapCode(code: string): string {
  const mapped = GAP_LABELS[code];
  if (mapped) {
    return mapped;
  }
  return code
    .split(/[:_]+/)
    .filter(Boolean)
    .map((part) => (part.length <= 4 ? part.toUpperCase() : part))
    .join(" ");
}

function buildRatesFact(tile: MacroModuleView["tiles"][number], index: number): RatesFact {
  const key = stringValue(tile.concept_key) ?? stringValue(tile.label) ?? `fact:${index}`;
  return {
    key,
    label: sanitizePrimaryText(
      stringValue(tile.label) ?? stringValue(tile.short_label) ?? humanizeRatesConceptKey(key),
    ),
    value: sanitizePrimaryText(formatMacroScalar(tile.display_value ?? tile.value)),
    observedAtLabel: sanitizePrimaryText(
      stringValue(tile.observed_at_label) ?? stringValue(tile.observed_at) ?? "暂无日期",
    ),
    sourceLabel: sanitizeOptionalText(tile.source_label),
    statusLabel: sanitizeOptionalText(tile.quality_label ?? tile.quality),
    interpretation: sanitizeOptionalText(tile.description ?? tile.delta_label),
  };
}

function ratesTitle(module: MacroModuleView, moduleId: RatesModuleId): string {
  const snapshotTitle = readableText(module.snapshot.title);
  if (!snapshotTitle || isGenericRatesCopy(snapshotTitle)) {
    return RATES_PAGE_COPY[moduleId].title;
  }
  return sanitizePrimaryText(snapshotTitle);
}

function ratesQuestion(module: MacroModuleView, moduleId: RatesModuleId): string {
  const snapshotQuestion = readableText(module.snapshot.question);
  if (!snapshotQuestion || isGenericRatesCopy(snapshotQuestion)) {
    return RATES_PAGE_COPY[moduleId].question;
  }
  return sanitizePrimaryText(snapshotQuestion);
}

function isGenericRatesCopy(value: string): boolean {
  return (
    /^(macro|rates?|宏观|利率|模块|总览)$/i.test(value.trim()) || /资产|asset|crypto/i.test(value)
  );
}

function proxyHeadlineForModule(module: MacroModuleView, moduleId: RatesModuleId): string | null {
  const futureGapCodes = allGapCodes(module);
  if (
    moduleId === "rates/auctions" &&
    futureGapCodes.some((code) => AUCTION_PROXY_GAPS.has(code))
  ) {
    return RATES_PAGE_COPY[moduleId].proxyHeadline ?? null;
  }
  if (
    moduleId === "rates/expectations" &&
    futureGapCodes.some((code) => EXPECTATIONS_PROXY_GAPS.has(code))
  ) {
    return RATES_PAGE_COPY[moduleId].proxyHeadline ?? null;
  }
  return null;
}

function readinessFromModule(module: MacroModuleView): RatesReadiness {
  const status =
    stringValue(module.data_health.summary_status) ?? stringValue(module.snapshot.status);
  if (status === "ok" || status === "ready") {
    return "ready";
  }
  if (status === "stale") {
    return "stale";
  }
  if (status === "missing" || status === "unavailable") {
    return "missing";
  }
  return "partial";
}

function readinessLabel(readiness: RatesReadiness): string {
  const labels: Record<RatesReadiness, string> = {
    ready: "可用",
    partial: "部分可用",
    proxy: "代理页",
    stale: "已过期",
    missing: "缺失",
  };
  return labels[readiness];
}

function neutralFallbackExplanation(moduleId: RatesModuleId): string {
  return `${RATES_PAGE_COPY[moduleId].title}数据已整理，方向判断以后台解读文本为准。`;
}

function missingPrimaryItems(module: MacroModuleView): string[] {
  const gapLabels = allGaps(module).map((gap) => gapDisplayLabel(gap));
  const missingConceptLabels = [
    ...(module.primary_chart.missing_concept_keys ?? []).map(humanizeRatesConceptKey),
    ...module.tables
      .flatMap((table) => table.missing_concept_keys ?? [])
      .map(humanizeRatesConceptKey),
  ];
  return uniqueStrings([...gapLabels, ...missingConceptLabels].map(sanitizePrimaryText));
}

function chartNote(module: MacroModuleView): string | null {
  return sanitizeOptionalText(module.primary_chart.subtitle ?? module.primary_chart.status_label);
}

function decisionGroups(evidence: MacroModuleView["module_evidence"]): RatesDecisionGroup[] {
  return DECISION_GROUPS.map((group) => ({
    key: group.key,
    label: group.label,
    items: evidenceItems(evidence[group.key]),
  }));
}

function evidenceItems(
  items: MacroSemanticRecord[] | undefined,
): Array<{ label: string; detail: string }> {
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => {
      const label = readableText(item.label);
      if (!label) {
        return null;
      }
      return {
        label: sanitizePrimaryText(label),
        detail: sanitizePrimaryText(readableText(item.description) ?? "暂无"),
      };
    })
    .filter((item): item is { label: string; detail: string } => Boolean(item));
}

function detailTables(
  module: MacroModuleView,
  moduleId: RatesModuleId,
  readiness: RatesReadiness,
): RatesDetailTable[] {
  return orderedTables(module.tables, moduleId, readiness).map((table, index) => ({
    role: index === 0 ? "primary" : "diagnostic",
    table,
  }));
}

function orderedTables(
  tables: MacroModuleTable[],
  moduleId: RatesModuleId,
  readiness: RatesReadiness,
): MacroModuleTable[] {
  if (readiness === "proxy") {
    return tables;
  }
  if (moduleId === "rates/auctions") {
    return [...tables].sort(
      (left, right) => auctionTablePriority(left) - auctionTablePriority(right),
    );
  }
  if (moduleId === "rates/expectations") {
    return [...tables].sort(
      (left, right) => expectationsTablePriority(left) - expectationsTablePriority(right),
    );
  }
  return tables;
}

function auctionTablePriority(table: MacroModuleTable): number {
  const text = tableSearchText(table);
  if (/未来拍卖|拍卖日历|auction_calendar/.test(text)) {
    return 0;
  }
  if (/拍卖结果|auction_results/.test(text)) {
    return 1;
  }
  return text.includes("proxy") || text.includes("代理") ? 3 : 2;
}

function expectationsTablePriority(table: MacroModuleTable): number {
  const text = tableSearchText(table);
  if (/会议概率|meeting_probability|fomc/.test(text)) {
    return 0;
  }
  return text.includes("proxy") || text.includes("代理") ? 2 : 1;
}

function tableSearchText(table: MacroModuleTable): string {
  return `${table.id} ${stringValue(table.title) ?? ""}`.toLowerCase();
}

function gapSummaries(module: MacroModuleView): RatesGapSummary[] {
  return allGaps(module).map((gap, index) => ({
    key: stringValue(gap.code) ?? `gap:${index}`,
    label: sanitizePrimaryText(gapDisplayLabel(gap)),
    severity: gapSeverity(gap.severity),
  }));
}

function gapDisplayLabel(gap: MacroSemanticRecord): string {
  return (
    readableText(gap.label) ??
    readableText(gap.display_value) ??
    humanizeRatesGapCode(stringValue(gap.code) ?? "data_gap")
  );
}

function gapSeverity(value: unknown): RatesGapSummary["severity"] {
  return value === "critical" || value === "warning" ? value : "info";
}

function allGapCodes(module: MacroModuleView): string[] {
  return allGaps(module)
    .map((gap) => stringValue(gap.code))
    .filter((code): code is string => Boolean(code));
}

function allGaps(module: MacroModuleView): MacroSemanticRecord[] {
  return [
    ...module.data_health.module_gaps,
    ...module.data_health.chart_gaps,
    ...module.data_health.future_integration_gaps,
  ];
}

function sourceMeta(provenance: MacroSemanticRecord): string | null {
  const rows = Array.isArray(provenance.rows) ? (provenance.rows as MacroSemanticRecord[]) : [];
  const labels = rows
    .map((row) =>
      [row.source, row.status_label].map(sanitizeOptionalText).filter(Boolean).join("："),
    )
    .filter(Boolean);
  return labels.length > 0 ? labels.join("；") : null;
}

function sanitizeOptionalText(value: unknown): string | null {
  const text = readableText(value);
  return text ? sanitizePrimaryText(text) : null;
}

function sanitizePrimaryText(value: string): string {
  let text = value;
  for (const [code, label] of Object.entries(GAP_LABELS)) {
    text = text.replaceAll(code, label);
  }
  return text.replace(/\b[a-z]+:[\w.-]+\b/gi, (concept) => humanizeRatesConceptKey(concept));
}

function readableText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}
