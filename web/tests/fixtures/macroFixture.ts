import type {
  MacroAssetCorrelationData,
  MacroModuleChart,
  MacroModuleTable,
  MacroModuleView,
  MacroSeriesData,
} from "@lib/types";

const NOW_MS = 1_779_000_000_000;

export function macroModuleFixture(
  overrides: Partial<MacroModuleView> = {},
): MacroModuleView {
  const primaryChart = equityChart();
  const tables = [equityTable()];
  return {
    snapshot: {
      module_id: "assets/equities",
      route_path: "/macro/assets/equities",
      title: "美股风险",
      subtitle: "SPX/QQQ/IWM 领导力与风险偏好确认",
      question: "美股风险偏好是否足以确认加密 beta？",
      section: "assets",
      projection_version: "macro_module_view_v3",
      status: "partial",
      status_label: "部分可用",
      asof_date: "2026-05-20",
      asof_label: "截至 2026-05-20",
      source_snapshot_id: "macro-view:macro_regime_v4:1779000000000",
      source_projection_version: "macro_regime_v4",
      computed_at_ms: NOW_MS,
    },
    tiles: [
      {
        concept_key: "asset:spx",
        label: "标普500",
        short_label: "SPX",
        description: "美国大盘风险偏好代理",
        value: 5312.4,
        display_value: "5,312.40",
        unit: "index",
        unit_label: "点",
        delta_label: "20日变化不可用",
        source_label: "Yahoo",
        observed_at: "2026-05-20",
        observed_at_label: "观测于 2026-05-20",
        quality: "partial",
        quality_label: "历史不足",
        score_participation: false,
        history_points: 1,
      },
    ],
    primary_chart: primaryChart,
    tables,
    module_read: {
      headline: "美股风险：等待小盘确认",
      regime_label: "风险偏好部分可用",
      confidence_label: "低置信度",
      crypto_read: "美股代理有最新值，但历史样本不足，不能确认加密 beta。",
      token_impact: "高 beta 山寨暴露等待更多历史确认。",
    },
    module_evidence: {
      confirmations: [{ label: "SPX 最新值可用", description: "Yahoo 最新观测存在" }],
      contradictions: [{ label: "IWM 样本不足", description: "小盘确认不足" }],
      watch_triggers: [{ label: "60日历史补齐", description: "核心代理达到最小样本" }],
      invalidations: [{ label: "SPX 跌破趋势", description: "风险偏好走弱" }],
    },
    transmission: [
      {
        kind: "flow",
        label: "美股 beta",
        status: "partial",
        status_label: "部分可用",
        value: "等待小盘确认",
      },
    ],
    data_health: {
      summary_status: "partial",
      summary_label: "模块数据部分可用",
      module_gaps: [
        {
          code: "insufficient_history:60d",
          label: "历史样本不足：无法计算 60 日变化",
          severity: "warning",
          owner: "macro_history_import",
          score_impact: "excluded",
          remediation_hint: "回填 60 日宏观历史后重新投影。",
        },
      ],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
    provenance: {
      rows: [
        {
          source: "Yahoo",
          status: "partial",
          status_label: "部分可用",
          latest_observed_at: "2026-05-20",
          concept_count: 1,
          score_participation: false,
          notes: "历史样本不足",
        },
      ],
    },
    related_routes: [
      { href: "/macro/assets", label: "大类资产" },
      { href: "/macro/volatility", label: "波动率" },
    ],
    section_boards: [],
    ...overrides,
  };
}

export function macroOverviewModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "overview",
      route_path: "/macro",
      section: "overview",
      title: "宏观总览",
      subtitle: "跨资产状态与关键缺口",
      question: "宏观环境是否支持风险资产扩张？",
      status: "partial",
      status_label: "全局数据部分可用",
    },
    tiles: [
      {
        concept_key: "macro:regime",
        label: "宏观状态",
        value: "partial_risk_on",
        display_value: "风险偏好部分确认",
        quality: "partial",
        quality_label: "部分可用",
      },
    ],
    module_read: {
      headline: "总览：风险偏好等待利率与流动性确认",
      regime_label: "风险偏好部分确认",
      confidence_label: "中低置信度",
      crypto_read: "加密 beta 需要美元流动性配合。",
    },
    module_evidence: {
      confirmations: [{ label: "美股代理可用", description: "SPX/QQQ 最新观测存在" }],
      contradictions: [],
      watch_triggers: [{ label: "收益率曲线更新", description: "等待利率模块补齐" }],
      invalidations: [],
    },
    transmission: [],
    data_health: {
      summary_status: "partial",
      summary_label: "全局数据部分可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [{ code: "macro_global_history_partial", label: "部分全局历史待回填" }],
      future_integration_gaps: [
        { code: "macro_forward_calendar_missing", label: "未来宏观日历待接入" },
      ],
    },
    section_boards: [],
  });
}

export function macroAssetsModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "assets",
      route_path: "/macro/assets",
      section: "assets",
      title: "大类资产",
      subtitle: "跨资产风险偏好入口",
      question: "哪些资产正在确认宏观风险偏好？",
    },
    module_read: {
      headline: "大类资产：美股与加密代理等待更多确认",
      regime_label: "资产信号部分可用",
      confidence_label: "低置信度",
    },
    module_evidence: {
      confirmations: [{ label: "美股代理有最新值" }],
      contradictions: [],
      watch_triggers: [{ label: "相关性样本补齐" }],
      invalidations: [],
    },
    transmission: [],
    data_health: {
      summary_status: "partial",
      summary_label: "资产模块部分可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
    section_boards: [
      {
        id: "asset-classes",
        title: "资产分区",
        href: "/macro/assets",
        status: "partial",
        status_label: "部分可用",
        rows: [
          {
            id: "assets-equities",
            title: "美股",
            href: "/macro/assets/equities",
            status: "partial",
            status_label: "历史不足",
          },
          {
            id: "assets-correlation",
            title: "相关性",
            href: "/macro/assets/correlation",
            status: "partial",
            status_label: "样本构建中",
          },
        ],
      },
    ],
  });
}

export function macroSeriesFixture(conceptKeys = ["asset:spx"]): MacroSeriesData {
  return {
    window: "60d",
    data_gaps: [],
    series: Object.fromEntries(
      conceptKeys.map((conceptKey) => [
        conceptKey,
        {
          concept_key: conceptKey,
          status: "ok",
          unit: "index",
          points: [
            { observed_at: "2026-05-18", value: 100, source_name: "fixture" },
            { observed_at: "2026-05-19", value: 110, source_name: "fixture" },
          ],
        },
      ]),
    ),
  };
}

export function macroYieldCurveModuleFixture(): MacroModuleView {
  const primaryChart: MacroModuleChart = {
    id: "yield_curve",
    title: "收益率曲线",
    subtitle: "2Y/5Y/10Y/30Y 曲线形态",
    kind: "yield_curve",
    status: "ok",
    status_label: "可用",
    min_points: 2,
    series: [
      { concept_key: "rates:dgs10", label: "10年期美债收益率", short_label: "10Y", latest: 4.2, unit: "percent" },
      { concept_key: "rates:dgs2", label: "2年期美债收益率", short_label: "2Y", latest: 3.8, unit: "percent" },
      { concept_key: "rates:dgs30", label: "30年期美债收益率", short_label: "30Y", latest: 4.7, unit: "percent" },
      { concept_key: "rates:dgs5", label: "5年期美债收益率", short_label: "5Y", latest: 4.0, unit: "percent" },
    ],
  };
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "rates/yield-curve",
      route_path: "/macro/rates/yield-curve",
      section: "rates",
      title: "收益率曲线",
      subtitle: "期限结构与估值压力",
      question: "曲线是否继续压制风险资产估值？",
    },
    tiles: [
      { concept_key: "rates:dgs2", label: "2年期美债收益率", short_label: "2Y", value: 3.8, display_value: "3.80", unit: "percent", unit_label: "%" },
      { concept_key: "rates:dgs10", label: "10年期美债收益率", short_label: "10Y", value: 4.2, display_value: "4.20", unit: "percent", unit_label: "%" },
    ],
    primary_chart: primaryChart,
    tables: [ratesTable()],
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
  });
}

export function macroCryptoDerivativesModuleFixture(): MacroModuleView {
  const primaryChart: MacroModuleChart = {
    id: "crypto_proxy_performance",
    title: "加密资产代理表现",
    subtitle: "BTC/ETH 宏观 beta",
    kind: "line",
    status: "ok",
    status_label: "可用",
    min_points: 2,
    series: [{ concept_key: "crypto:btc", label: "BTC", latest: 110_000, unit: "usd", point_count: 60 }],
  };
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "assets/crypto-derivatives",
      route_path: "/macro/assets/crypto-derivatives",
      section: "assets",
      title: "加密衍生品",
      subtitle: "CEX OI、资金费率与成交",
      question: "衍生品杠杆是否确认风险偏好？",
    },
    tiles: [{ concept_key: "crypto:btc", label: "BTC", value: 110_000, display_value: "110,000.00", unit: "usd", unit_label: "美元" }],
    primary_chart: primaryChart,
    tables: [cexTable()],
    data_health: {
      summary_status: "partial",
      summary_label: "衍生品集成部分可用",
      module_gaps: [
        { code: "basis_missing", label: "基差数据缺失", severity: "info" },
        { code: "crypto_options_missing", label: "加密期权数据缺失", severity: "info" },
        { code: "etf_flows_missing", label: "ETF 资金流缺失", severity: "info" },
      ],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
  });
}

export function macroCorrelationFixture(): MacroAssetCorrelationData {
  return {
    window: "60d",
    asof_date: "2026-05-20",
    assets: [
      {
        concept_key: "asset:spy",
        title: "SPY",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
      {
        concept_key: "asset:qqq",
        title: "QQQ",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
    ],
    matrix: [
      {
        concept_key: "asset:spy",
        correlations: { "asset:spy": 1, "asset:qqq": 0.92 },
      },
      {
        concept_key: "asset:qqq",
        correlations: { "asset:spy": 0.92, "asset:qqq": 1 },
      },
    ],
    pairs: [
      {
        left: "asset:spy",
        right: "asset:qqq",
        correlation: 0.92,
        sample_size: 58,
        start_date: "2026-02-24",
        end_date: "2026-05-20",
        available: true,
        reason: null,
      },
    ],
    data_gaps: [],
  };
}

function equityChart(): MacroModuleChart {
  return {
    id: "equity_proxy_performance",
    title: "美股代理表现",
    subtitle: "SPX/QQQ/IWM 60 日归一化表现",
    kind: "line",
    status: "insufficient_history",
    status_label: "历史样本不足",
    min_points: 2,
    missing_concept_keys: ["asset:iwm"],
    series: [
      {
        concept_key: "asset:spx",
        label: "标普500",
        short_label: "SPX",
        latest: 5312.4,
        unit: "index",
        point_count: 1,
        status: "insufficient_history",
        status_label: "历史样本不足",
      },
    ],
  };
}

function equityTable(): MacroModuleTable {
  return {
    id: "equity_proxy_snapshot",
    title: "美股代理快照",
    status: "partial",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "delta_20d", label: "20日变化" },
      { key: "quality", label: "质量" },
      { key: "source", label: "来源" },
    ],
    rows: [
      {
        row_id: "asset:spx",
        row_quality: "partial",
        source_state: { label: "Yahoo", status: "partial" },
        cells: {
          indicator: { display_value: "标普500", sort_value: "SPX" },
          latest: { display_value: "5,312.40", sort_value: 5312.4 },
          delta_20d: { display_value: "历史不足", sort_value: null },
          quality: { display_value: "历史不足", sort_value: "partial" },
          source: { display_value: "Yahoo", sort_value: "Yahoo" },
        },
      },
    ],
  };
}

function ratesTable(): MacroModuleTable {
  return {
    id: "yield_curve_snapshot",
    title: "收益率曲线快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      {
        row_id: "rates:dgs2",
        cells: {
          indicator: { display_value: "2年期美债收益率", sort_value: "2Y" },
          latest: { display_value: "3.80", sort_value: 3.8 },
          quality: { display_value: "可用", sort_value: "ok" },
        },
      },
      {
        row_id: "rates:dgs10",
        cells: {
          indicator: { display_value: "10年期美债收益率", sort_value: "10Y" },
          latest: { display_value: "4.20", sort_value: 4.2 },
          quality: { display_value: "可用", sort_value: "ok" },
        },
      },
    ],
  };
}

function cexTable(): MacroModuleTable {
  return {
    id: "cex_perp_board",
    title: "CEX 永续看板",
    status: "partial",
    source: {
      name: "CEX OI Radar",
      status: "partial",
      status_label: "部分可用",
      notes: "Coinglass 数据不完整",
    },
    columns: [
      { key: "symbol", label: "合约" },
      { key: "open_interest", label: "未平仓" },
      { key: "funding", label: "资金费率" },
      { key: "volume_24h", label: "24h 成交" },
      { key: "score", label: "分数" },
    ],
    rows: [
      {
        row_id: "BTCUSDT",
        row_quality: "partial",
        source_state: { label: "CEX OI Radar", status: "partial" },
        cells: {
          symbol: { display_value: "BTC", sort_value: "BTC" },
          open_interest: { display_value: "12.50B", sort_value: 12_500_000_000 },
          funding: { display_value: "0.0100%", sort_value: 0.0001 },
          volume_24h: { display_value: "31.00B", sort_value: 31_000_000_000 },
          score: { display_value: "91.20", sort_value: 91.2 },
        },
      },
      {
        row_id: "ETHUSDT",
        row_quality: "partial",
        source_state: { label: "CEX OI Radar", status: "partial" },
        cells: {
          symbol: { display_value: "ETH", sort_value: "ETH" },
          open_interest: { display_value: "8.30B", sort_value: 8_300_000_000 },
          funding: { display_value: "-0.0200%", sort_value: -0.0002 },
          volume_24h: { display_value: "18.00B", sort_value: 18_000_000_000 },
          score: { display_value: "80.40", sort_value: 80.4 },
        },
      },
    ],
  };
}
