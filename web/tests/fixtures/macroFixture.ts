import type {
  MacroAssetCorrelationData,
  MacroModuleChart,
  MacroModuleTable,
  MacroModuleView,
  MacroSemanticRecord,
  MacroSeriesData,
} from "@lib/types";

const NOW_MS = 1_779_000_000_000;

export function macroModuleFixture(overrides: Partial<MacroModuleView> = {}): MacroModuleView {
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
        source_label: "Yahoo Finance",
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
        label: "Yahoo",
        status: "partial",
        status_label: "部分可用",
        value: "美股风险偏好",
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
      global_gaps: [{ code: "missing_srf", label: "缺少 SRF" }],
      future_integration_gaps: [],
    },
    provenance: {
      rows: [
        {
          source: "Yahoo Finance",
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
      { href: "/macro/volatility/dashboard", label: "波动率" },
    ],
    ...overrides,
  };
}

export function macroOverviewModuleFixture(
  overrides: Partial<MacroModuleView> = {},
): MacroModuleView {
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
    ...overrides,
  });
}

export function macroAssetsModuleFixture(
  overrides: Partial<MacroModuleView> = {},
): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "assets",
      route_path: "/macro/assets",
      section: "assets",
      title: "大类资产",
      subtitle: "股票、债券、商品、美元与加密资产总览",
      question: "今天跨资产链条是在支持 risk-on，还是提示防守？",
      status: "partial",
      status_label: "部分可用",
    },
    primary_chart: {
      ...equityChart(),
      id: "asset_cross_market_snapshot",
      title: "大类资产走势",
    },
    tables: [
      {
        ...equityTable(),
        id: "asset_group_snapshot",
        title: "大类资产快照",
      },
    ],
    module_read: {
      headline: "大类资产：风险资产偏震荡",
      regime_label: "部分可用",
      confidence_label: "模块覆盖 5/12",
      data_note: "只展示已入库事实和可用性说明。",
    },
    daily_brief: {
      brief_key: "assets_today",
      projection_version: "macro_daily_brief_v1",
      brief_date: "2026-05-20",
      asof_date: "2026-05-20",
      status: "partial",
      headline: "今日判断：风险资产偏震荡",
      blocks: [
        {
          id: "cross_correlation",
          title: "跨资产相关性",
          stance: "mixed",
          body: "SPX 与 BTC 同向，但 10Y 仍有压力。",
        },
        {
          id: "dollar_commodity",
          title: "美元与商品",
          stance: "commodity_supported",
          body: "DXY 回落，WTI 偏强。",
        },
        {
          id: "risk_appetite",
          title: "风险偏好",
          stance: "neutral",
          body: "风险偏好部分恢复，信用确认不足。",
        },
        {
          id: "outlook",
          title: "今日展望",
          stance: "watch_data_quality",
          body: "等待美元、10Y 与信用利差同向确认。",
        },
      ],
    },
    related_routes: [
      { href: "/macro/assets/equities", label: "美股" },
      { href: "/macro/assets/correlation", label: "相关性" },
    ],
    ...overrides,
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
      {
        concept_key: "rates:dgs10",
        label: "10年期美债收益率",
        short_label: "10Y",
        latest: 4.2,
        unit: "percent",
      },
      {
        concept_key: "rates:dgs2",
        label: "2年期美债收益率",
        short_label: "2Y",
        latest: 3.8,
        unit: "percent",
      },
      {
        concept_key: "rates:dgs30",
        label: "30年期美债收益率",
        short_label: "30Y",
        latest: 4.7,
        unit: "percent",
      },
      {
        concept_key: "rates:dgs5",
        label: "5年期美债收益率",
        short_label: "5Y",
        latest: 4.0,
        unit: "percent",
      },
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
      {
        concept_key: "rates:dgs2",
        label: "2年期美债收益率",
        short_label: "2Y",
        value: 3.8,
        display_value: "3.80",
        unit: "percent",
        unit_label: "%",
      },
      {
        concept_key: "rates:dgs10",
        label: "10年期美债收益率",
        short_label: "10Y",
        value: 4.2,
        display_value: "4.20",
        unit: "percent",
        unit_label: "%",
      },
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

export function macroFedFundsModuleFixture(): MacroModuleView {
  const primaryChart: MacroModuleChart = {
    id: "fed_funds_corridor",
    title: "政策利率走廊",
    subtitle: "目标区间、EFFR、IORB 与 SOFR",
    kind: "rates_corridor",
    status: "partial",
    status_label: "SOFR 30D 待接入",
    min_points: 1,
    missing_concept_keys: ["fed:sofr_30d"],
    series: [
      {
        concept_key: "fed:target_lower",
        label: "目标下限",
        latest: 4.25,
        unit: "percent",
        points: [
          { observed_at: "2026-05-19", value: 4.25 },
          { observed_at: "2026-05-20", value: 4.25 },
        ],
      },
      {
        concept_key: "fed:target_upper",
        label: "目标上限",
        latest: 4.5,
        unit: "percent",
        points: [
          { observed_at: "2026-05-19", value: 4.5 },
          { observed_at: "2026-05-20", value: 4.5 },
        ],
      },
      {
        concept_key: "fed:effr",
        label: "EFFR",
        latest: 4.33,
        unit: "percent",
        points: [
          { observed_at: "2026-05-19", value: 4.33 },
          { observed_at: "2026-05-20", value: 4.33 },
        ],
      },
      {
        concept_key: "fed:iorb",
        label: "IORB",
        latest: 4.4,
        unit: "percent",
      },
      {
        concept_key: "liquidity:sofr",
        label: "SOFR",
        latest: 4.31,
        unit: "percent",
        points: [
          { observed_at: "2026-05-19", value: 4.32 },
          { observed_at: "2026-05-20", value: 4.31 },
        ],
      },
      {
        concept_key: "fed:sofr_30d",
        label: "SOFR 30D",
        latest: null,
        unit: "percent",
        status: "missing",
        status_label: "待接入",
      },
    ],
  };
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "rates/fed-funds",
      route_path: "/macro/rates/fed-funds",
      section: "rates",
      title: "联邦基金与走廊",
      subtitle: "目标区间、有效联邦基金利率与隔夜融资",
      question: "政策走廊是否稳定，隔夜融资是否溢出目标区间？",
      status: "partial",
      status_label: "走廊数据部分可用",
    },
    tiles: [
      ratesTile("fed:target_lower", "目标下限", "4.25%", "Federal Reserve"),
      ratesTile("fed:target_upper", "目标上限", "4.50%", "Federal Reserve"),
      ratesTile("fed:effr", "EFFR", "4.33%", "Federal Reserve Bank of New York"),
      ratesTile("fed:iorb", "IORB", "4.40%", "Federal Reserve"),
      ratesTile("liquidity:sofr", "SOFR", "4.31%", "Federal Reserve Bank of New York"),
    ],
    primary_chart: primaryChart,
    tables: [fedFundsTable()],
    module_read: {
      headline: "联邦基金走廊：隔夜利率保持在目标区间内",
      regime_label: "走廊稳定",
      confidence_label: "中等置信度",
      crypto_read: "隔夜融资代理显示美元资金面暂未出现明显挤压。",
      token_impact: "加密风险资产需要继续观察 SOFR 与有效联邦基金利率的相对位置。",
    },
    module_evidence: {
      confirmations: [{ label: "EFFR 位于目标区间内", description: "隔夜政策利率未显示越界压力" }],
      contradictions: [],
      watch_triggers: [
        { label: "SOFR 上行", description: "若 SOFR 持续贴近区间上沿，需要关注融资压力" },
      ],
      invalidations: [{ label: "EFFR 越过上限", description: "政策走廊稳定判断失效" }],
    },
    data_health: {
      summary_status: "partial",
      summary_label: "走廊数据部分可用",
      module_gaps: [{ code: "sofr_30d_missing", label: "SOFR 30D 尚未入库", severity: "info" }],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
  });
}

export function macroAuctionsProxyModuleFixture(
  overrides: Partial<MacroModuleView> = {},
): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "rates/auctions",
      route_path: "/macro/rates/auctions",
      section: "rates",
      title: "国债拍卖",
      subtitle: "官方拍卖日历和结果接入前的代理视图",
      question: "拍卖供给压力是否体现在曲线和长端收益率上？",
      status: "partial",
      status_label: "代理数据",
    },
    tiles: [
      ratesTile("rates:dgs10", "10年期美债收益率", "4.20%", "U.S. Treasury"),
      ratesTile("rates:dgs30", "30年期美债收益率", "4.70%", "U.S. Treasury"),
    ],
    primary_chart: {
      id: "auction_proxy_yields",
      title: "拍卖代理：长端收益率",
      subtitle: "官方拍卖数据未接入时使用曲线代理",
      kind: "line",
      status: "partial",
      status_label: "代理数据",
      series: [
        { concept_key: "rates:dgs10", label: "10年期美债收益率", latest: 4.2, unit: "percent" },
        { concept_key: "rates:dgs30", label: "30年期美债收益率", latest: 4.7, unit: "percent" },
      ],
    },
    tables: [auctionProxyYieldTable()],
    module_read: {
      headline: "国债拍卖：官方日历和结果尚未入库",
      regime_label: "代理页",
      confidence_label: "低置信度",
      crypto_read: "长端收益率代理可用于观察供给压力，但不能替代官方拍卖结果。",
      token_impact: "加密风险资产仅获得中性背景信息，不能从代理数值推出方向结论。",
    },
    module_evidence: {
      confirmations: [
        { label: "长端收益率代理可用", description: "10年期与30年期收益率最新值存在" },
      ],
      contradictions: [
        { label: "官方拍卖结果缺失", description: "尾部利差与投标覆盖倍数尚未接入" },
      ],
      watch_triggers: [
        { label: "官方日历补齐", description: "接入未来拍卖安排后切换到正式拍卖页面" },
      ],
      invalidations: [],
    },
    data_health: {
      summary_status: "partial",
      summary_label: "拍卖代理数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [
        {
          code: "treasury_auction_calendar_missing",
          label: "官方拍卖日历尚未入库",
          severity: "warning",
        },
        {
          code: "treasury_auction_results_missing",
          label: "官方拍卖结果尚未入库",
          severity: "warning",
        },
      ],
    },
    ...overrides,
  });
}

export function macroAuctionsOfficialModuleFixture(): MacroModuleView {
  return macroAuctionsProxyModuleFixture({
    snapshot: {
      ...macroAuctionsProxyModuleFixture().snapshot,
      status: "ok",
      status_label: "官方数据可用",
    },
    tiles: [
      ratesTile("treasury:next_auction_size", "下一场拍卖规模", "420 亿美元", "U.S. Treasury"),
      ratesTile("treasury:bid_to_cover", "最近投标覆盖倍数", "2.42", "U.S. Treasury"),
    ],
    tables: [auctionCalendarTable(), auctionResultsTable(), auctionProxyYieldTable()],
    module_read: {
      headline: "国债拍卖：官方日历与最近结果可用",
      regime_label: "官方拍卖数据可用",
      confidence_label: "中等置信度",
      crypto_read: "拍卖供给压力可用官方日历和结果直接观察。",
      token_impact: "加密风险资产需要结合长端收益率反应确认融资冲击。",
    },
    data_health: {
      summary_status: "ok",
      summary_label: "官方拍卖数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
  });
}

export function macroRealRatesModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "rates/real-rates",
      route_path: "/macro/rates/real-rates",
      section: "rates",
      title: "实际利率",
      subtitle: "TIPS 实际收益率与通胀补偿",
      question: "实际利率是在压制估值，还是通胀补偿主导？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      ratesTile("rates:real_5y", "5年期实际利率", "1.78%", "U.S. Treasury"),
      ratesTile("rates:real_10y", "10年期实际利率", "1.94%", "U.S. Treasury"),
      ratesTile("inflation:breakeven_10y", "10年期通胀补偿", "2.26%", "FRED"),
    ],
    primary_chart: {
      id: "real_rates_snapshot",
      title: "实际利率与通胀补偿",
      kind: "line",
      status: "ok",
      status_label: "可用",
      series: [
        { concept_key: "rates:real_5y", label: "5年期实际利率", latest: 1.78, unit: "percent" },
        { concept_key: "rates:real_10y", label: "10年期实际利率", latest: 1.94, unit: "percent" },
        {
          concept_key: "inflation:breakeven_10y",
          label: "10年期通胀补偿",
          latest: 2.26,
          unit: "percent",
        },
      ],
    },
    tables: [realRatesTable()],
    module_read: {
      headline: "实际利率：估值压力仍需结合通胀补偿判断",
      regime_label: "实际利率可用",
      confidence_label: "中等置信度",
      crypto_read: "实际利率处于可观察状态，但方向判断依赖后台解读文本而非单点数值。",
      token_impact: "长久期代币需要关注实际利率与通胀补偿的组合变化。",
    },
    module_evidence: {
      confirmations: [{ label: "TIPS 曲线可用", description: "5年期和10年期实际利率最新值存在" }],
      contradictions: [],
      watch_triggers: [{ label: "实际利率快速上行", description: "估值压力需要重新评估" }],
      invalidations: [],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "实际利率数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [],
    },
  });
}

export function macroExpectationsProxyModuleFixture(
  overrides: Partial<MacroModuleView> = {},
): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "rates/expectations",
      route_path: "/macro/rates/expectations",
      section: "rates",
      title: "政策预期",
      subtitle: "期货概率接入前的代理视图",
      question: "市场是否在重新定价降息、维持或加息路径？",
      status: "partial",
      status_label: "代理数据",
    },
    tiles: [
      ratesTile("fed:target_upper", "目标上限", "4.50%", "Federal Reserve"),
      ratesTile("fed:effr", "EFFR", "4.33%", "Federal Reserve Bank of New York"),
    ],
    primary_chart: {
      id: "policy_path_proxy",
      title: "政策路径代理",
      subtitle: "正式会议概率接入前展示政策利率代理",
      kind: "line",
      status: "partial",
      status_label: "代理数据",
      series: [
        { concept_key: "fed:target_upper", label: "目标上限", latest: 4.5, unit: "percent" },
        { concept_key: "fed:effr", label: "EFFR", latest: 4.33, unit: "percent" },
      ],
    },
    tables: [policyProxyTable()],
    module_read: {
      headline: "政策预期：正式会议概率尚未入库",
      regime_label: "代理页",
      confidence_label: "低置信度",
      crypto_read: "政策利率代理只能说明当前走廊状态，不能生成正式降息概率。",
      token_impact: "加密风险资产等待联邦基金期货和会议概率数据确认政策路径。",
    },
    module_evidence: {
      confirmations: [{ label: "政策利率代理可用", description: "目标上限与 EFFR 最新值存在" }],
      contradictions: [{ label: "会议概率缺失", description: "正式 FOMC 概率源尚未接入" }],
      watch_triggers: [{ label: "会议概率接入", description: "接入后切换到正式政策路径页面" }],
      invalidations: [],
    },
    data_health: {
      summary_status: "partial",
      summary_label: "政策路径代理数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
      future_integration_gaps: [
        {
          code: "fed_funds_futures_missing",
          label: "联邦基金期货数据尚未入库",
          severity: "warning",
        },
        {
          code: "fomc_probability_feed_missing",
          label: "FOMC 概率数据尚未入库",
          severity: "warning",
        },
      ],
    },
    ...overrides,
  });
}

export function macroExpectationsOfficialModuleFixture(): MacroModuleView {
  return macroExpectationsProxyModuleFixture({
    snapshot: {
      ...macroExpectationsProxyModuleFixture().snapshot,
      status: "ok",
      status_label: "官方概率可用",
    },
    tiles: [
      ratesTile("fed:next_meeting_hold_probability", "下次会议维持概率", "61%", "CME FedWatch"),
      ratesTile("fed:next_meeting_cut_probability", "下次会议降息概率", "34%", "CME FedWatch"),
    ],
    tables: [meetingProbabilityTable(), policyProxyTable()],
    module_read: {
      headline: "政策预期：会议概率数据可用",
      regime_label: "会议概率可用",
      confidence_label: "中等置信度",
      crypto_read: "政策路径可以从会议概率表读取，方向判断仍以后台解读为准。",
      token_impact: "加密风险资产需要观察概率变化是否与利率曲线同步。",
    },
    data_health: {
      summary_status: "ok",
      summary_label: "政策预期数据可用",
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
    series: [
      { concept_key: "crypto:btc", label: "BTC", latest: 110_000, unit: "usd", point_count: 60 },
    ],
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
    tiles: [
      {
        concept_key: "crypto:btc",
        label: "BTC",
        value: 110_000,
        display_value: "110,000.00",
        unit: "usd",
        unit_label: "美元",
      },
    ],
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
        source_state: { label: "Yahoo Finance", status: "partial" },
        cells: {
          indicator: { display_value: "标普500", sort_value: "SPX" },
          latest: { display_value: "5,312.40", sort_value: 5312.4 },
          delta_20d: { display_value: "历史不足", sort_value: null },
          quality: { display_value: "历史不足", sort_value: "partial" },
          source: { display_value: "Yahoo Finance", sort_value: "Yahoo Finance" },
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

function ratesTile(
  conceptKey: string,
  label: string,
  displayValue: string,
  sourceLabel: string,
): MacroModuleView["tiles"][number] {
  return {
    concept_key: conceptKey,
    label,
    value: displayValue,
    display_value: displayValue,
    unit: "percent",
    unit_label: "%",
    source_label: sourceLabel,
    observed_at: "2026-05-20",
    observed_at_label: "观测于 2026-05-20",
    quality: "ok",
    quality_label: "可用",
  };
}

function fedFundsTable(): MacroModuleTable {
  return {
    id: "fed_funds_corridor_snapshot",
    title: "联邦基金走廊快照",
    status: "partial",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("fed:target_lower", "目标下限", "4.25%", "Federal Reserve", "可用"),
      ratesRow("fed:target_upper", "目标上限", "4.50%", "Federal Reserve", "可用"),
      ratesRow("fed:effr", "EFFR", "4.33%", "Federal Reserve Bank of New York", "可用"),
      ratesRow("fed:iorb", "IORB", "4.40%", "Federal Reserve", "可用"),
      ratesRow("liquidity:sofr", "SOFR", "4.31%", "Federal Reserve Bank of New York", "可用"),
    ],
  };
}

function auctionProxyYieldTable(): MacroModuleTable {
  return {
    id: "auction_proxy_yield_snapshot",
    title: "拍卖代理：长端收益率",
    status: "partial",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("rates:dgs10", "10年期美债收益率", "4.20%", "U.S. Treasury", "代理"),
      ratesRow("rates:dgs30", "30年期美债收益率", "4.70%", "U.S. Treasury", "代理"),
    ],
  };
}

function auctionCalendarTable(): MacroModuleTable {
  return {
    id: "treasury_auction_calendar",
    title: "未来拍卖日历",
    status: "ok",
    columns: [
      { key: "security", label: "品种" },
      { key: "auction_date", label: "拍卖日期" },
      { key: "amount", label: "规模" },
      { key: "settlement", label: "交割" },
    ],
    rows: [
      {
        row_id: "auction:2026-05-21:10y",
        cells: {
          security: { display_value: "10年期国债", sort_value: "10Y" },
          auction_date: { display_value: "2026-05-21", sort_value: "2026-05-21" },
          amount: { display_value: "420 亿美元", sort_value: 42_000_000_000 },
          settlement: { display_value: "2026-05-31", sort_value: "2026-05-31" },
        },
      },
    ],
  };
}

function auctionResultsTable(): MacroModuleTable {
  return {
    id: "treasury_auction_results",
    title: "最近拍卖结果",
    status: "ok",
    columns: [
      { key: "security", label: "品种" },
      { key: "tail", label: "尾部利差" },
      { key: "bid_to_cover", label: "投标覆盖倍数" },
      { key: "indirect", label: "间接投标" },
    ],
    rows: [
      {
        row_id: "auction-result:2026-05-14:30y",
        cells: {
          security: { display_value: "30年期国债", sort_value: "30Y" },
          tail: { display_value: "0.4 bp", sort_value: 0.4 },
          bid_to_cover: { display_value: "2.42", sort_value: 2.42 },
          indirect: { display_value: "68%", sort_value: 68 },
        },
      },
    ],
  };
}

function realRatesTable(): MacroModuleTable {
  return {
    id: "real_rates_snapshot",
    title: "实际利率快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("rates:real_5y", "5年期实际利率", "1.78%", "U.S. Treasury", "可用"),
      ratesRow("rates:real_10y", "10年期实际利率", "1.94%", "U.S. Treasury", "可用"),
      ratesRow("inflation:breakeven_10y", "10年期通胀补偿", "2.26%", "FRED", "可用"),
    ],
  };
}

function policyProxyTable(): MacroModuleTable {
  return {
    id: "policy_path_proxy_snapshot",
    title: "政策路径代理快照",
    status: "partial",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("fed:target_upper", "目标上限", "4.50%", "Federal Reserve", "代理"),
      ratesRow("fed:effr", "EFFR", "4.33%", "Federal Reserve Bank of New York", "代理"),
    ],
  };
}

function meetingProbabilityTable(): MacroModuleTable {
  return {
    id: "fomc_meeting_probability",
    title: "会议概率",
    status: "ok",
    columns: [
      { key: "meeting", label: "会议" },
      { key: "hold_probability", label: "维持概率" },
      { key: "cut_probability", label: "降息概率" },
      { key: "source", label: "来源" },
    ],
    rows: [
      {
        row_id: "fomc:2026-06",
        cells: {
          meeting: { display_value: "2026-06 FOMC", sort_value: "2026-06" },
          hold_probability: { display_value: "61%", sort_value: 61 },
          cut_probability: { display_value: "34%", sort_value: 34 },
          source: { display_value: "CME FedWatch", sort_value: "CME FedWatch" },
        },
      },
    ],
  };
}

function ratesRow(
  rowId: string,
  indicator: string,
  latest: string,
  source: string,
  quality: string,
): MacroSemanticRecord {
  return {
    row_id: rowId,
    cells: {
      indicator: { display_value: indicator, sort_value: indicator },
      latest: { display_value: latest, sort_value: latest },
      source: { display_value: source, sort_value: source },
      quality: { display_value: quality, sort_value: quality },
    },
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
