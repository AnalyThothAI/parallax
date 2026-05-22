import type { MacroModuleChart, MacroModuleTable } from "@lib/types";

export function chartConceptKeys(chart: MacroModuleChart): string[] {
  return (chart.series ?? [])
    .map((series) => (typeof series.concept_key === "string" ? series.concept_key : ""))
    .filter(Boolean);
}

export function tableCaption(table: MacroModuleTable): string {
  return TITLE_BY_ID[table.table_id] ?? labelFromIdentifier(table.table_id);
}

export function emptyChart(chartId: string): MacroModuleChart {
  return { chart_id: chartId, series: [], status: "missing" };
}

export function emptyTable(tableId: string): MacroModuleTable {
  return { table_id: tableId, rows: [], status: "missing" };
}

const TITLE_BY_ID: Record<string, string> = {
  cex_perp_board: "CEX 永续看板",
  crypto_proxy_performance: "加密资产代理表现",
  equity_proxy_performance: "美股代理表现",
  equity_proxy_snapshot: "美股代理快照",
  macro_regime: "宏观状态",
  panel_scorecard: "宏观状态面板",
  source_metadata: "数据源元信息",
  yield_curve: "收益率曲线",
  yield_curve_snapshot: "收益率曲线快照",
};

function labelFromIdentifier(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => WORD_LABELS[part] ?? part)
    .join(" ");
}

const WORD_LABELS: Record<string, string> = {
  asset: "资产",
  assets: "资产",
  board: "看板",
  cex: "CEX",
  chart: "图表",
  credit: "信用",
  curve: "曲线",
  derivatives: "衍生品",
  fed: "美联储",
  fx: "外汇",
  liquidity: "流动性",
  macro: "宏观",
  performance: "表现",
  perp: "永续",
  proxy: "代理",
  rates: "利率",
  real: "实际",
  snapshot: "快照",
  source: "数据源",
  table: "表格",
  volatility: "波动率",
  yield: "收益率",
};
