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
      asset_class_diagnostics: {
        label: "美股风险诊断",
        regime: "equity_risk_off",
        regime_label: "美股降温",
        summary: "美股风险偏好走弱：大盘和成长承压，小盘/高 beta 未确认，风险资产需要降档。",
        rows: [
          {
            key: "spx",
            label: "SPX",
            change_1w_pct: -3.85,
            change_1m_pct: 0,
            status: "risk_off",
            status_label: "风险降温",
          },
          {
            key: "ndx",
            label: "NDX",
            change_1w_pct: -4.55,
            change_1m_pct: 5,
            status: "risk_off",
            status_label: "风险降温",
          },
          {
            key: "sp500_positioning",
            label: "CFTC S&P 净投机",
            current_k: -120,
            change_1w_k: -60,
            change_1m_k: -100,
            status: "positioning_defensive",
            status_label: "仓位防守",
          },
        ],
        implications: ["美股降温：降低股票、加密 beta 和高收益信用暴露，等待小盘和成长股修复。"],
        invalidations: ["若 SPX/NDX 1w 转正且 RUT/IWM 不再跑输，美股降温读法降级。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "spx_latest_available",
          label: "SPX 最新值可用",
          description: "Yahoo 最新观测存在",
          evidence_label: "Yahoo 最新观测存在",
        },
      ],
      contradictions: [
        {
          code: "iwm_sample_insufficient",
          label: "IWM 样本不足",
          description: "小盘确认不足",
          evidence_label: "小盘确认不足",
        },
      ],
      watch_triggers: [
        {
          code: "core_history_backfill_60d",
          label: "60日历史补齐",
          description: "核心代理达到最小样本",
          evidence_label: "核心代理达到最小样本",
          time_window: "24h",
          severity: "high",
          severity_label: "高",
        },
      ],
      invalidations: [
        {
          code: "spx_breaks_trend",
          label: "SPX 跌破趋势",
          description: "风险偏好走弱",
          evidence_label: "风险偏好走弱",
        },
      ],
    },
    transmission: [
      {
        key: "flow:yahoo",
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
    },
    provenance: {
      rows: [
        {
          row_id: "source:Yahoo_Finance",
          source_label: "Yahoo Finance",
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
      { href: "/macro/volatility/vix", label: "波动率" },
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
      decision_console: {
        top_changes: [
          {
            code: "sofr_above_iorb",
            label: "SOFR 高于 IORB",
            description: "隔夜资金价格重新接近政策走廊压力区。",
            change_label: "SOFR-IORB +7bp",
            value_label: "最新 7bp",
            observed_at: "2026-05-20",
            source_label: "NY Fed / Federal Reserve",
            severity: "high",
            severity_label: "高",
            evidence_label:
              "SOFR-IORB +7bp · 最新 7bp · source=NY Fed / Federal Reserve · as-of=2026-05-20",
            node: "funding",
            node_label: "资金面",
            kind: "trigger",
          },
          {
            code: "hy_oas_stress",
            label: "高收益债利差压力",
            description: "信用 beta 对风险偏好给出反证。",
            evidence_label: "信用 beta 对风险偏好给出反证。",
            node: "credit",
            node_label: "信用压力",
            kind: "trigger",
          },
        ],
        quality_blockers: [
          {
            code: "missing_asset_spy",
            label: "缺少当前数据：SPY",
            description: "检查对应 provider 导入与最新观测。",
            evidence_label: "检查对应 provider 导入与最新观测。",
            severity: "error",
            severity_label: "阻断",
          },
        ],
        data_credibility: {
          key: "data_credibility",
          label: "数据可信度层",
          issue_count: 2,
          issue_label: "2 issue(s)",
          rows: [
            {
              concept_key: "asset:spx",
              label: "SPX",
              display_value: "5312.40",
              unit_label: "点",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "FRED",
              quality: "ok",
              quality_label: "可用",
            },
            {
              concept_key: "fx:dxy",
              label: "DXY",
              display_value: "104.20",
              unit_label: "点",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "FRED",
              quality: "ok",
              quality_label: "可用",
            },
            {
              concept_key: "crypto:btc",
              label: "BTC",
              display_value: "110000.00",
              unit_label: "美元",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "Yahoo",
              quality: "ok",
              quality_label: "可用",
            },
            {
              concept_key: "commodity:wti_futures",
              label: "CL=F",
              display_value: "72.40",
              unit_label: "美元",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "Yahoo",
              quality: "ok",
              quality_label: "可用",
            },
            {
              concept_key: "rates:dgs10",
              label: "10Y",
              display_value: "4.70",
              unit_label: "%",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "FRED",
              quality: "ok",
              quality_label: "可用",
            },
            {
              concept_key: "vol:vix",
              label: "VIX",
              display_value: "17.20",
              unit_label: "点",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "FRED",
              quality: "ok",
              quality_label: "可用",
            },
            {
              concept_key: "credit:hy_oas",
              label: "HY OAS",
              display_value: "2.80",
              unit_label: "%",
              observed_at: "2026-05-17",
              observed_at_label: "2026-05-17",
              source_label: "FRED",
              quality: "stale",
              quality_label: "过期",
            },
            {
              concept_key: "liquidity:on_rrp",
              label: "ON RRP",
              display_value: "127.00",
              unit_label: "百万美元",
              observed_at: "2026-05-20",
              observed_at_label: "2026-05-20",
              source_label: "FRED",
              quality: "degraded",
              quality_label: "降级",
            },
          ],
        },
        trade_map: [
          {
            expression: "risk_down_credit_sensitive",
            label: "风险降档 / 信用敏感",
            time_window: "1w",
            time_window_label: "1周",
            action_checklist: [
              {
                kind: "confirm",
                kind_label: "确认",
                label: "SOFR 高于 IORB",
                description: "观察 SOFR 高于 IORB 是否继续确认。",
              },
              {
                kind: "confirm",
                kind_label: "确认",
                label: "HY OAS 5日走阔",
                description: "观察 HY OAS 5日走阔 是否继续确认。",
              },
              {
                kind: "invalidate",
                kind_label: "失效",
                label: "SOFR 回到 IORB 附近",
                description: "若 SOFR 回到 IORB 附近，则撤销该映射。",
              },
            ],
            legs: [
              {
                asset: "cash_short_bills",
                label: "现金/短债",
                symbol: "BIL",
                action: "做多/防守",
              },
              {
                asset: "nasdaq",
                label: "纳斯达克",
                symbol: "QQQ",
                action: "回避/做空代理",
              },
              {
                asset: "high_yield_credit",
                label: "高收益信用",
                symbol: "HYG",
                action: "低配",
              },
            ],
          },
        ],
        liquidity_pressure: {
          key: "liquidity_pressure",
          label: "流动性压力",
          score: 7.0,
          score_label: "7.0/10",
          regime: "corridor_drain",
          regime_label: "走廊抽水",
          summary: "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
          drivers: [
            {
              key: "sofr_iorb",
              label: "SOFR-IORB 走廊压力",
              current_bp: 7,
              change_1w_bp: 6,
              change_1m_bp: 11,
              status: "corridor_pressure",
              status_label: "走廊压力",
            },
            {
              key: "net_liquidity",
              label: "净流动性",
              current_trillion: 5.78,
              change_1w_bn: -60,
              change_1m_bn: -120,
              status: "net_drain",
              status_label: "净抽水",
            },
            {
              key: "tga",
              label: "TGA 财政现金",
              current_bn: 760,
              change_1w_bn: 70,
              change_1m_bn: 160,
              status: "treasury_drain",
              status_label: "财政抽水",
            },
          ],
          implication: "流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。",
          invalidation: "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
        },
        future_catalysts: {
          label: "未来 24/72h 催化剂",
          rows: [
            {
              key: "watch:real_yield_breakout",
              label: "实际利率突破",
              detail: "10Y real yield keeps rising.",
              window: "24h",
              window_label: "24h",
              severity: "high",
              severity_label: "高",
              source: "情景触发",
              kind: "watch_trigger",
            },
            {
              key: "event:official_calendar:fomc_decision_next",
              label: "FOMC 决议",
              detail: "2026-06-17 · 还有 1 天 · 14:00 ET",
              window: "24h",
              window_label: "24h",
              severity: "high",
              severity_label: "高",
              source: "官方日历",
              source_url: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
              kind: "calendar",
            },
            {
              key: "watch:hy_oas_distress",
              label: "高收益债利差进入困境区",
              detail: "HY OAS crosses distress thresholds.",
              window: "72h",
              window_label: "72h",
              severity: "medium",
              severity_label: "中",
              source: "情景触发",
              kind: "watch_trigger",
            },
          ],
        },
        watchlist_alerts: {
          key: "watchlist_alerts",
          label: "Watchlist 与触发提醒",
          assets: [
            { key: "BIL", symbol: "BIL", label: "现金/短债", action: "做多/防守" },
            { key: "QQQ", symbol: "QQQ", label: "纳斯达克", action: "回避/做空代理" },
            { key: "HYG", symbol: "HYG", label: "高收益信用", action: "低配" },
          ],
          rules: [
            {
              key: "watch:real_yield_breakout",
              label: "实际利率突破",
              detail: "10Y real yield keeps rising.",
              kind: "watch",
              kind_label: "触发",
              window: "24h",
              window_label: "24h",
              severity: "high",
              severity_label: "高",
            },
            {
              key: "invalidation:ten_year_yield_reverses",
              label: "10年期收益率回落",
              detail: "10Y yield loses pressure.",
              kind: "invalidation",
              kind_label: "失效",
            },
            {
              key: "quality:missing_asset_spy",
              label: "缺少当前数据：SPY",
              detail: "检查对应 provider 导入与最新观测。",
              kind: "quality",
              kind_label: "质量",
              severity: "error",
              severity_label: "阻断",
            },
          ],
        },
        scenario_cases: [
          {
            case: "base",
            label: "基准情景",
            probability: 0.5,
            probability_label: "50%",
            time_window: "未来 2 周",
            time_window_label: "未来 2 周",
            thesis: "资金压力维持，信用 beta 继续承压，风险资产反弹先按减仓处理。",
            trade: "防守：做多/持有 BIL，低配 QQQ 与 HYG。",
            entry_condition: "SOFR-IORB 仍为正且 HY OAS 5日继续走阔。",
            stop: "SOFR 回到 IORB 附近且 HY OAS 明显收窄。",
            invalidation: "若 VIX 回到 carry 区且信用利差同步收窄，资金压力情景降级。",
          },
          {
            case: "downside",
            label: "悲观情景",
            probability: 0.25,
            probability_label: "25%",
            time_window: "未来 2 周",
            time_window_label: "未来 2 周",
            thesis: "资金压力传导到信用与波动率，风险资产进入去杠杆。",
            trade: "提高现金/短债，继续低配 HYG 与 QQQ，可用 VIX 上行作为保护确认。",
            entry_condition: "HY OAS 进入困境区或 VIX 突破 30。",
            stop: "信用利差收窄且 VIX 回落到 20 以下。",
            invalidation: "若净流动性转正且信用利差未扩张，悲观情景降级。",
          },
        ],
      },
      market_event_flow: {
        key: "market_event_flow",
        label: "市场事件流",
        rows: [
          {
            key: "news:news-row-1",
            label: "中东震荡下，日本追加预算预期升温",
            date: "2026-06-10",
            detail: "油价与美元走强，风险资产低开。",
            source: "bloomberg.com",
            source_url: "https://news.google.com/articles/macro-1",
            kind: "news",
            window: "recent",
            window_label: "近期",
            severity: "low",
            severity_label: "低",
            category: "macro_policy",
            category_label: "美联储",
            impact: "mainline_context",
            impact_label: "不改主线",
            watch: "SPX · 美元 · 美联储",
          },
          {
            key: "official_calendar:fomc_decision_next",
            label: "FOMC 决议",
            date: "2026-06-17",
            detail: "2026-06-17 · 还有 1 天 · 14:00 ET",
            source: "官方日历",
            source_url: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            kind: "calendar",
            window: "0-3d",
            window_label: "0-3天",
            severity: "high",
            severity_label: "高",
            category: "policy",
            category_label: "政策",
            impact: "policy_path",
            impact_label: "政策路径",
            watch: "利率路径和流动性定价。",
          },
          {
            key: "treasury_auction:2y_next_auction_days",
            label: "2Y 国债拍卖日历",
            date: "2026-06-23",
            detail: "2026-06-23 · 还有 7 天 · 2026-06-18 公告 · 2026-06-30 交割",
            source: "US Treasury",
            source_url: "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
            kind: "auction_calendar",
            window: "4-7d",
            window_label: "4-7天",
            severity: "medium",
            severity_label: "中",
            category: "treasury_supply",
            category_label: "国债供给",
            impact: "settlement_watch",
            impact_label: "拍卖/交割",
            watch: "关注拍卖需求、公告规模和交割日资金占用。",
          },
          {
            key: "treasury_auction:10y_bid_to_cover",
            label: "10Y 国债拍卖 Bid/Cover",
            date: "2026-06-10",
            detail: "2026-06-10 · 2.52 · CUSIP 91282CQQ9",
            source: "US Treasury",
            source_url:
              "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
            kind: "auction_result",
            window: "recent",
            window_label: "近期",
            severity: "medium",
            severity_label: "中",
            category: "treasury_supply",
            category_label: "国债供给",
            impact: "auction_result",
            impact_label: "拍卖结果",
            watch: "拍卖结果作为国债需求和期限溢价压力证据。",
          },
          {
            key: "official_fed_text:speech_latest",
            label: "Fed 官员讲话",
            date: "2026-05-08",
            detail: "2026-05-08 · Waller, Update On Federal Reserve Bank Operations",
            source: "Federal Reserve",
            source_url: "https://www.federalreserve.gov/newsevents/speech/waller20260508a.htm",
            kind: "fed_text",
            window: "recent",
            window_label: "近期",
            severity: "medium",
            severity_label: "中",
            category: "policy",
            category_label: "政策",
            impact: "fed_communication",
            impact_label: "Fed 沟通",
            watch: "跟踪措辞、投票分歧和政策路径信号。",
          },
        ],
      },
      structured_analysis: {
        key: "structured_analysis",
        label: "跨域判断链",
        rows: [
          {
            key: "market_thesis",
            label: "市场主线",
            regime_label: "期限溢价压力",
            fact: "市场主线：长端利率维持压力。",
            evidence: [
              "实际利率上行 · 10Y real yield broke higher",
              "RRP 缓冲偏低 · ON RRP buffer is below 300bn USD",
              "Trade Map · 久期承压 / 质量优于成长",
            ],
            trade: "低配 TLT。",
            invalidation: "实际利率压力消退。",
          },
          {
            key: "fed_communication",
            label: "美联储沟通",
            regime_label: "讲话",
            fact: "Fed 沟通：2026-05-08 · Waller, Update On Federal Reserve Bank Operations",
            evidence: [
              "Fed 官员讲话 · Federal Reserve · Waller",
              "Fed 沟通 · 跟踪措辞、投票分歧和政策路径信号。",
            ],
            trade: "利率路径和流动性定价需跟随 Fed 沟通重新校准。",
            invalidation: "若后续 FOMC 声明、纪要或讲话与当前政策路径反向，Fed 沟通读法降级。",
          },
          {
            key: "assets",
            label: "大类资产",
            regime_label: "滞胀冲击",
            fact: "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。",
            evidence: [
              "SPX · 1w -2.8% · 1m -3.7% · 风险降温",
              "TLT · 1w -4.5% · 1m -6.7% · 久期承压",
              "DXY · 1w +1.5% · 1m +3.5% · 美元走强",
            ],
            trade: "滞胀冲击：降低权益/加密 beta，保留美元、能源或现金防守表达。",
            invalidation: "若 SPX/BTC 修复且 DXY、WTI、VIX 同步回落，滞胀冲击读法降级。",
          },
          {
            key: "rates",
            label: "利率曲线",
            regime_label: "熊陡",
            fact: "曲线熊陡：10Y 上行且 2s10s 走陡，期限溢价压力压制久期资产。",
            evidence: ["2s10s · 50bp · 走陡", "3m10y · 0bp · 走陡", "5s30s · 50bp · 走陡"],
            trade: "期限溢价压力：优先防守长久期成长、长债和高 beta。",
            invalidation: "若 10Y 回落且 2s10s 重新走平，曲线压力降级。",
          },
          {
            key: "policy",
            label: "美联储",
            regime_label: "鹰派定价",
            fact: "Fed 定价偏鹰：终端利率和降息预期未给风险资产提供宽松确认。",
            evidence: [
              "联邦基金有效利率 · 5.33% · 政策约束",
              "期货隐含降息 · 1 次 · 宽松不足",
              "Fed 官员讲话 · Federal Reserve · Waller",
            ],
            trade: "Fed 偏鹰：降低长久期成长和高 beta 多头置信度。",
            invalidation: "若点阵图或官员沟通转向更快降息路径，鹰派定价读法降级。",
          },
          {
            key: "liquidity",
            label: "流动性",
            regime_label: "走廊抽水",
            fact: "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
            evidence: [
              "SOFR-IORB 走廊压力 · 7bp · 走廊压力",
              "SOFR-TGCR 深度压力 · 9bp · Repo 深度压力",
              "SOFR 成交量 · $3023B · 成交放大",
            ],
            trade: "流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。",
            invalidation: "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
          },
          {
            key: "growth",
            label: "经济增长",
            regime_label: "增长降温",
            fact: "增长降温：实际 GDP、工业生产和消费动能同步放缓，盈利预期需要降级。",
            evidence: [
              "实际 GDP · 1.9% y/y · 增长降温",
              "工业生产 · 1.5% SAAR · 动能放缓",
              "实际 PCE · -1.5% y/y · 需求走弱",
            ],
            trade: "增长降温：降低周期、高 beta 和盈利弹性资产暴露。",
            invalidation: "若实际 PCE 与工业生产同比回升且住房开工 1m 转正，增长降温读法降级。",
          },
          {
            key: "employment",
            label: "就业",
            regime_label: "就业降温",
            fact: "就业降温：失业率与初请上行、非农动能放缓，增长风险压过软着陆叙事。",
            evidence: [
              "失业率 · 4.3% · 就业降温",
              "非农新增 · 80k · 动能放缓",
              "初请失业金 · 260k · 走弱",
            ],
            trade: "就业降温：降低盈利周期和高 beta 置信度，降息交易需等待通胀配合。",
            invalidation: "若非农新增重新高于 180k 且初请 1m 回落超过 20k，就业降温读法降级。",
          },
          {
            key: "inflation",
            label: "通胀",
            regime_label: "通胀再加速",
            fact: "通胀再加速：CPI/Core CPI 同比重新上行且通胀补偿走阔，降息交易需要降级。",
            evidence: [
              "核心 CPI · 5.7% y/y · 再加速",
              "CPI · 5.3% y/y · 再加速",
              "10Y Breakeven · 2.6% · 补偿走阔",
            ],
            trade: "通胀再加速：降低降息受益、长久期成长和高 beta 反弹置信度。",
            invalidation: "若核心 CPI 同比回落且 10Y 通胀补偿 1m 收窄超过 10bp，再加速读法降级。",
          },
          {
            key: "volatility",
            label: "波动率",
            regime_label: "期限 Contango",
            fact: "波动率处于 Contango：VIX 回落且远期仍有溢价，短期风险偏 carry。",
            evidence: [
              "VIX · 16.9 · Carry",
              "VIX3M-VIX · 6.9pts · Contango",
              "VVIX · 88 · 波动率风险可控",
            ],
            trade: "波动率 carry：风险资产可维持暴露，但不追杠杆，等待 VIX3M-VIX 收窄确认。",
            invalidation: "若 VIX3M-VIX 转负或 VIX 单周上行超过 5 点，carry 读法失效。",
          },
          {
            key: "credit",
            label: "信用市场",
            regime_label: "尾部走阔",
            fact: "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。",
            evidence: [
              "HY OAS · 440bp · 走阔",
              "IG OAS · 125bp · 走阔",
              "CCC-HY 尾部 · 510bp · 尾部恶化",
            ],
            trade: "信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。",
            invalidation: "若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。",
          },
        ],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "equity_proxies_available",
          label: "美股代理可用",
          description: "SPX/QQQ 最新观测存在",
          evidence_label: "SPX/QQQ 最新观测存在",
        },
      ],
      contradictions: [
        {
          code: "iwm_sample_insufficient",
          label: "IWM 样本不足",
          description: "小盘确认不足",
          evidence_label: "小盘确认不足",
        },
      ],
      watch_triggers: [
        {
          code: "core_history_backfill_60d",
          label: "60日历史补齐",
          description: "核心代理达到最小样本",
          evidence_label: "核心代理达到最小样本",
          time_window: "24h",
          severity: "high",
          severity_label: "高",
        },
      ],
      invalidations: [
        {
          code: "spx_breaks_trend",
          label: "SPX 跌破趋势",
          description: "风险偏好走弱",
          evidence_label: "风险偏好走弱",
        },
      ],
    },
    transmission: [],
    data_health: {
      summary_status: "partial",
      summary_label: "全局数据部分可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [
        {
          code: "macro_global_history_partial",
          label: "全局历史样本不足",
          remediation_hint: "需要补充全局宏观历史后再生成总览投影。",
          severity: "warning",
        },
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
      asset_diagnostics: {
        label: "跨资产诊断",
        regime: "stagflation_shock",
        regime_label: "滞胀冲击",
        summary: "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。",
        rows: [
          {
            key: "spx",
            label: "SPX",
            change_1w_pct: -3.06,
            change_1m_pct: -5,
            status: "risk_off",
            status_label: "风险降温",
          },
          {
            key: "tlt",
            label: "TLT",
            change_1w_pct: -2.02,
            change_1m_pct: -3,
            status: "duration_pressure",
            status_label: "久期承压",
          },
          {
            key: "dxy",
            label: "DXY",
            change_1w_pct: 0.98,
            change_1m_pct: 3,
            status: "dollar_up",
            status_label: "美元走强",
          },
          {
            key: "wti",
            label: "WTI",
            change_1w_pct: 7.32,
            change_1m_pct: 10,
            status: "energy_up",
            status_label: "能源上行",
          },
        ],
        implications: ["滞胀冲击：降低权益/加密 beta，保留美元、能源或现金防守表达。"],
        invalidations: ["若 SPX/BTC 修复且 DXY、WTI、VIX 同步回落，滞胀冲击读法降级。"],
      },
    },
    daily_brief: {
      brief_key: "assets_today",
      projection_version: "macro_daily_brief_v1",
      brief_date: "2026-05-20",
      asof_date: "2026-05-20",
      status: "partial",
      headline: "今日判断：风险资产偏震荡",
      data_quality: {
        status: "partial",
        gap_count: 7,
        latest_coverage_ratio: 1,
        history_coverage_ratio: 0.84,
      },
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
    related_routes: [{ href: "/macro/assets/equities", label: "美股" }],
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
    module_read: {
      headline: "收益率曲线：熊陡",
      regime_label: "熊陡",
      confidence_label: "模块覆盖 5/13",
      data_note: "收益率曲线以 2s10s、3m10y 与 5s30s 的当前形态和 1w/1m/3m 变化为核心读法。",
      curve_diagnostics: {
        label: "曲线诊断",
        shape: "bear_steepening",
        shape_label: "熊陡",
        summary: "曲线熊陡：10Y 上行且 2s10s 走陡，期限溢价压力压制久期资产。",
        rows: [
          {
            key: "2s10s",
            label: "2s10s",
            current_bp: 40,
            change_1w_bp: 10,
            change_1m_bp: 10,
            change_3m_bp: 10,
            status: "steepening",
            status_label: "走陡",
          },
          {
            key: "3m10y",
            label: "3m10y",
            current_bp: -10,
            change_1w_bp: 25,
            change_1m_bp: 40,
            change_3m_bp: 60,
            status: "less_inverted",
            status_label: "倒挂缓和",
          },
          {
            key: "5s30s",
            label: "5s30s",
            current_bp: 70,
            change_1w_bp: 5,
            change_1m_bp: 0,
            change_3m_bp: 0,
            status: "steepening",
            status_label: "走陡",
          },
        ],
        spread_history: [
          {
            key: "2s10s",
            label: "2s10s",
            unit: "bp",
            points: [
              { observed_at: "2026-02-19", value_bp: 30 },
              { observed_at: "2026-04-20", value_bp: 30 },
              { observed_at: "2026-05-13", value_bp: 30 },
              { observed_at: "2026-05-20", value_bp: 40 },
            ],
            min_bp: 30,
            max_bp: 40,
            latest_bp: 40,
          },
          {
            key: "3m10y",
            label: "3m10y",
            unit: "bp",
            points: [
              { observed_at: "2026-02-19", value_bp: -70 },
              { observed_at: "2026-04-20", value_bp: -50 },
              { observed_at: "2026-05-13", value_bp: -35 },
              { observed_at: "2026-05-20", value_bp: -10 },
            ],
            min_bp: -70,
            max_bp: -10,
            latest_bp: -10,
          },
        ],
        tenor_comparison: [
          {
            key: "5y",
            label: "5Y",
            nominal_pct: 4,
            real_pct: 2.1,
            breakeven_pct: 1.9,
            nominal_change_1w_bp: 10,
            real_change_1w_bp: 15,
            breakeven_change_1w_bp: -5,
            residual_bp: 0,
            driver: "real_rate",
            driver_label: "实际利率驱动",
          },
          {
            key: "10y",
            label: "10Y",
            nominal_pct: 4.2,
            real_pct: 1.95,
            breakeven_pct: 2.15,
            nominal_change_1w_bp: 20,
            real_change_1w_bp: 15,
            breakeven_change_1w_bp: -5,
            residual_bp: 10,
            driver: "real_rate",
            driver_label: "实际利率驱动",
          },
        ],
        implications: ["期限溢价压力：优先防守长久期成长、长债和高 beta。"],
        invalidations: ["若 10Y 回落且 2s10s 重新走平，曲线压力降级。"],
      },
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
    },
  });
}

export function macroCreditStressModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "credit/stress",
      route_path: "/macro/credit/stress",
      section: "credit",
      title: "信用压力分解",
      subtitle: "IG/HY OAS、CCC 尾部与银行信贷收紧",
      question: "信用市场是在确认风险偏好，还是提示尾部压力？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      creditTile("credit:hy_oas", "HY OAS", "4.20%", "FRED"),
      creditTile("credit:ig_oas", "IG OAS", "1.20%", "FRED"),
      creditTile("credit:hy_ccc_oas", "CCC OAS", "9.50%", "FRED"),
      creditTile("credit:nfci", "NFCI", "-0.10", "FRED"),
      creditTile("credit:sloos_ci_large_tightening", "SLOOS 大中型收紧", "30%", "Federal Reserve"),
    ],
    primary_chart: {
      id: "credit_stress_stack",
      title: "信用压力栈",
      subtitle: "IG/HY/CCC OAS 与银行信贷收紧",
      kind: "line",
      status: "ok",
      status_label: "可用",
      min_points: 2,
      series: [
        { concept_key: "credit:hy_oas", label: "HY OAS", latest: 4.2, unit: "percent" },
        { concept_key: "credit:ig_oas", label: "IG OAS", latest: 1.2, unit: "percent" },
        { concept_key: "credit:hy_ccc_oas", label: "CCC OAS", latest: 9.5, unit: "percent" },
        {
          concept_key: "credit:sloos_ci_large_tightening",
          label: "SLOOS 大中型收紧",
          latest: 30,
          unit: "percent",
        },
      ],
    },
    tables: [creditStressTable()],
    module_read: {
      headline: "信用压力分解：尾部走阔",
      regime_label: "尾部走阔",
      confidence_label: "模块覆盖 4/24",
      data_note: "信用压力以 HY/IG OAS、CCC-HY 尾部和 SLOOS 收紧为核心读法。",
      credit_diagnostics: {
        label: "信用压力诊断",
        regime: "tail_widening",
        regime_label: "尾部走阔",
        summary: "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。",
        rows: [
          {
            key: "hy_oas",
            label: "HY OAS",
            current_bp: 420,
            change_1w_bp: 30,
            change_1m_bp: 50,
            change_3m_bp: 70,
            status: "widening",
            status_label: "走阔",
          },
          {
            key: "ig_oas",
            label: "IG OAS",
            current_bp: 120,
            change_1w_bp: 10,
            change_1m_bp: 15,
            change_3m_bp: 20,
            status: "widening",
            status_label: "走阔",
          },
          {
            key: "ccc_hy_tail",
            label: "CCC-HY 尾部",
            current_bp: 530,
            change_1w_bp: 90,
            change_1m_bp: 100,
            change_3m_bp: 160,
            status: "tail_widening",
            status_label: "尾部恶化",
          },
          {
            key: "hyg_lqd_relative",
            label: "HYG/LQD 信用 ETF",
            hyg_1w_pct: -1.27,
            lqd_1w_pct: 0.93,
            relative_1w_pct: -2.19,
            hyg_1m_pct: 0,
            lqd_1m_pct: 1.87,
            relative_1m_pct: -1.87,
            status: "etf_pressure",
            status_label: "HYG跑输",
          },
          {
            key: "nfci",
            label: "NFCI 金融条件",
            current_index: -0.1,
            change_1w_index: 0.2,
            change_1m_index: 0.3,
            change_3m_index: 0.5,
            adjusted_index: -0.3,
            status: "conditions_tightening",
            status_label: "金融条件收紧",
          },
          {
            key: "sloos_ci_large_tightening",
            label: "SLOOS 大中型收紧",
            current_pct: 30,
            change_1q_pct: 12,
            status: "tightening",
            status_label: "银行收紧",
          },
        ],
        implications: ["信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。"],
        invalidations: ["若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "hy_oas_widening",
          label: "HY OAS 走阔",
          description: "高收益信用利差短期上行",
          evidence_label: "高收益信用利差短期上行",
        },
      ],
      contradictions: [
        {
          code: "ig_oas_mild_pressure",
          label: "IG 压力较温和",
          description: "投资级利差尚未进入压力区",
          evidence_label: "投资级利差尚未进入压力区",
        },
      ],
      watch_triggers: [
        {
          code: "ccc_hy_tail_widens",
          label: "CCC-HY 尾部继续走阔",
          description: "低质量信用扩散压力",
          evidence_label: "低质量信用扩散压力",
        },
      ],
      invalidations: [
        {
          code: "hy_oas_narrows",
          label: "HY OAS 收窄",
          description: "信用压力读法降级",
          evidence_label: "信用压力读法降级",
        },
      ],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
    },
  });
}

export function macroVolatilityVixModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "volatility/vix",
      route_path: "/macro/volatility/vix",
      section: "volatility",
      title: "VIX 结构",
      subtitle: "VIX、VIX1D、VIX9D、VIX3M、VVIX/SKEW 与 VIX 期货 ETF 代理",
      question: "波动率期限结构是在 carry，还是进入倒挂压力？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      volatilityTile("vol:vix", "VIX", "16.90", "FRED"),
      volatilityTile("vol:vix1d", "VIX1D", "17.30", "Cboe"),
      volatilityTile("vol:vix9d", "VIX9D", "18.00", "Cboe"),
      volatilityTile("vol:vix3m", "VIX3M", "23.80", "FRED"),
      volatilityTile("vol:vvix", "VVIX", "88.00", "Cboe"),
      volatilityTile("vol:skew", "SKEW", "143.80", "Cboe"),
      volatilityTile("asset:vixy", "VIXY", "18.00", "Yahoo Finance"),
      volatilityTile("asset:vixm", "VIXM", "29.00", "Yahoo Finance"),
    ],
    primary_chart: {
      id: "vix_term_proxy",
      title: "VIX 期限代理",
      subtitle: "VIX、VIX1D、VIX9D、VIX3M、VIXY 与 VIXM",
      kind: "line",
      status: "ok",
      status_label: "可用",
      min_points: 2,
      series: [
        { concept_key: "vol:vix", label: "VIX", latest: 16.9, unit: "index" },
        { concept_key: "vol:vix1d", label: "VIX1D", latest: 17.3, unit: "index" },
        { concept_key: "vol:vix9d", label: "VIX9D", latest: 18, unit: "index" },
        { concept_key: "vol:vix3m", label: "VIX3M", latest: 23.8, unit: "index" },
        { concept_key: "asset:vixy", label: "VIXY", latest: 18, unit: "usd" },
        { concept_key: "asset:vixm", label: "VIXM", latest: 29, unit: "usd" },
      ],
    },
    tables: [volatilityVixTable()],
    module_read: {
      headline: "VIX 结构：期限 Contango",
      regime_label: "期限 Contango",
      confidence_label: "模块覆盖 7/11",
      data_note:
        "波动率以 VIX 现货、VIX1D-VIX、VIX9D-VIX、VIX3M-VIX、VIXY/VIXM 和跨资产波动率为核心读法。",
      volatility_diagnostics: {
        label: "波动率诊断",
        regime: "carry_contango",
        regime_label: "期限 Contango",
        summary: "波动率处于 Contango：VIX 回落且远期仍有溢价，短期风险偏 carry。",
        rows: [
          {
            key: "vix_spot",
            label: "VIX 现货",
            current_index: 16.9,
            change_1w_index: -2.1,
            change_1m_index: -4.1,
            status: "normal",
            status_label: "正常",
          },
          {
            key: "vix1d_vix",
            label: "VIX1D-VIX 当日溢价",
            current_points: 0.4,
            change_1w_points: 1.4,
            change_1m_points: 1.4,
            status: "normal",
            status_label: "正常",
          },
          {
            key: "vix9d_vix",
            label: "VIX9D-VIX 近端溢价",
            current_points: 1.1,
            change_1w_points: 1.6,
            change_1m_points: 2.1,
            status: "normal",
            status_label: "正常",
          },
          {
            key: "vix3m_vix",
            label: "VIX3M-VIX 期限溢价",
            current_points: 6.9,
            change_1w_points: 1.7,
            change_1m_points: 2.9,
            status: "contango",
            status_label: "Contango",
          },
          {
            key: "vvix",
            label: "VVIX 波动率凸性",
            current_index: 88,
            change_1w_index: 2,
            change_1m_index: 4,
            status: "normal",
            status_label: "正常",
          },
          {
            key: "skew",
            label: "SKEW 尾部风险",
            current_index: 143.8,
            change_1w_index: 2.8,
            change_1m_index: 5.8,
            status: "tail_premium",
            status_label: "尾部溢价",
          },
          {
            key: "vixy_vixm",
            label: "VIXY/VIXM 前端压力",
            current_ratio: 0.62,
            change_1w_pct: -6.67,
            change_1m_pct: -6.67,
            status: "front_relief",
            status_label: "前端回落",
          },
          {
            key: "vxn",
            label: "VXN 纳指波动率",
            current_index: 20.5,
            change_1w_index: -1.5,
            change_1m_index: -4.5,
            status: "elevated",
            status_label: "偏高",
          },
        ],
        implications: ["波动率 carry：风险资产可维持暴露，但不追杠杆，等待 VIX3M-VIX 收窄确认。"],
        invalidations: ["若 VIX3M-VIX 转负或 VIX 单周上行超过 5 点，carry 读法失效。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "vix_term_structure_contango",
          label: "VIX 期限结构 Contango",
          description: "VIX3M 高于 VIX",
          evidence_label: "VIX3M 高于 VIX",
        },
      ],
      contradictions: [
        {
          code: "vxn_still_elevated",
          label: "纳指波动率仍偏高",
          description: "VXN 仍高于 20",
          evidence_label: "VXN 仍高于 20",
        },
      ],
      watch_triggers: [
        {
          code: "vix3m_vix_turns_negative",
          label: "VIX3M-VIX 转负",
          description: "期限结构转入 backwardation",
          evidence_label: "期限结构转入 backwardation",
        },
      ],
      invalidations: [
        {
          code: "vix_weekly_rises",
          label: "VIX 单周上行",
          description: "短端波动率重新定价",
          evidence_label: "短端波动率重新定价",
        },
      ],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
    },
  });
}

export function macroLiquidityRrpTgaModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "liquidity/rrp-tga",
      route_path: "/macro/liquidity/rrp-tga",
      section: "liquidity",
      title: "RRP / TGA",
      subtitle: "财政现金、逆回购与净流动性代理",
      question: "TGA 与 RRP 是否正在吸收市场流动性？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      liquidityTile("liquidity:sofr", "SOFR", "4.47%", "Federal Reserve Bank of New York"),
      liquidityTile("fed:iorb", "IORB", "4.40%", "Federal Reserve"),
      liquidityTile("liquidity:on_rrp", "ON RRP", "$760B", "FRED"),
      liquidityTile("liquidity:tga", "TGA", "$760B", "U.S. Treasury"),
    ],
    primary_chart: {
      id: "rrp_tga_stack",
      title: "RRP / TGA 栈",
      subtitle: "RRP、TGA 与美联储总资产",
      kind: "line",
      status: "ok",
      status_label: "可用",
      min_points: 2,
      series: [
        { concept_key: "liquidity:on_rrp", label: "ON RRP", latest: 760000, unit: "million_usd" },
        { concept_key: "liquidity:tga", label: "TGA", latest: 760000, unit: "million_usd" },
        {
          concept_key: "liquidity:fed_assets",
          label: "美联储总资产",
          latest: 7300000,
          unit: "million_usd",
        },
      ],
    },
    tables: [liquidityRrpTgaTable()],
    module_read: {
      headline: "RRP / TGA：走廊抽水",
      regime_label: "走廊抽水",
      confidence_label: "模块覆盖 5/5",
      data_note: "流动性以 SOFR-IORB、RRP 缓冲、TGA 和净流动性为核心读法。",
      liquidity_diagnostics: {
        label: "流动性诊断",
        regime: "corridor_drain",
        regime_label: "走廊抽水",
        summary: "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
        rows: [
          {
            key: "sofr_iorb",
            label: "SOFR-IORB 走廊压力",
            current_bp: 7,
            change_1w_bp: 6,
            change_1m_bp: 11,
            status: "corridor_pressure",
            status_label: "走廊压力",
          },
          {
            key: "sofr_tgcr",
            label: "SOFR-TGCR 深度压力",
            current_bp: 9,
            change_1w_bp: 5,
            change_1m_bp: 8,
            status: "repo_depth_pressure",
            status_label: "Repo 深度压力",
          },
          {
            key: "sofr_volume",
            label: "SOFR 成交量",
            current_bn: 3023,
            change_1w_bn: 173,
            change_1m_bn: 323,
            status: "volume_expansion",
            status_label: "成交放大",
          },
          {
            key: "on_rrp",
            label: "RRP 缓冲",
            current_bn: 760,
            change_1w_bn: -60,
            change_1m_bn: -140,
            status: "buffer_drawdown",
            status_label: "缓冲消耗",
          },
          {
            key: "tga",
            label: "TGA 财政现金",
            current_bn: 760,
            change_1w_bn: 70,
            change_1m_bn: 160,
            status: "treasury_drain",
            status_label: "财政抽水",
          },
          {
            key: "net_liquidity",
            label: "净流动性",
            current_trillion: 5.78,
            change_1w_bn: -60,
            change_1m_bn: -120,
            status: "net_drain",
            status_label: "净抽水",
          },
        ],
        implications: ["流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。"],
        invalidations: ["若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "tga_rising",
          label: "TGA 上升",
          description: "财政现金账户吸收系统流动性",
          evidence_label: "财政现金账户吸收系统流动性",
        },
      ],
      contradictions: [
        {
          code: "rrp_buffer_above_depletion_zone",
          label: "RRP 缓冲仍高于枯竭区",
          description: "隔夜逆回购余额仍可缓冲抽水",
          evidence_label: "隔夜逆回购余额仍可缓冲抽水",
        },
      ],
      watch_triggers: [
        {
          code: "sofr_iorb_widens",
          label: "SOFR-IORB 延续走阔",
          description: "回购压力继续向走廊扩散",
          evidence_label: "回购压力继续向走廊扩散",
        },
      ],
      invalidations: [
        {
          code: "net_liquidity_turns_positive",
          label: "净流动性转正",
          description: "抽水读法降级",
          evidence_label: "抽水读法降级",
        },
      ],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
    },
  });
}

export function macroInflationModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "economy/inflation",
      route_path: "/macro/economy/inflation",
      section: "economy",
      title: "通胀仪表盘",
      subtitle: "CPI、PPI、PCE、GDP 平减指数与通胀预期",
      question: "通胀是在继续降温，还是重新压制降息预期？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      inflationTile("inflation:cpi", "CPI", "318.00", "FRED"),
      inflationTile("inflation:core_cpi", "核心 CPI", "318.00", "FRED"),
      inflationTile("inflation:ppi", "PPI", "108.00", "FRED"),
      inflationTile("inflation:10y_breakeven", "10Y 通胀补偿", "2.55%", "FRED"),
    ],
    primary_chart: {
      id: "inflation_dashboard",
      title: "通胀仪表盘",
      subtitle: "CPI、PPI、PCE 与市场通胀补偿",
      kind: "line",
      status: "ok",
      status_label: "可用",
      min_points: 2,
      series: [
        { concept_key: "inflation:cpi", label: "CPI", latest: 318, unit: "index" },
        { concept_key: "inflation:core_cpi", label: "核心 CPI", latest: 318, unit: "index" },
        { concept_key: "inflation:ppi", label: "PPI", latest: 108, unit: "index" },
        {
          concept_key: "inflation:10y_breakeven",
          label: "10Y 通胀补偿",
          latest: 2.55,
          unit: "percent",
        },
      ],
    },
    tables: [inflationTable()],
    module_read: {
      headline: "通胀仪表盘：通胀再加速",
      regime_label: "通胀再加速",
      confidence_label: "模块覆盖 4/10",
      data_note: "通胀以 CPI/Core CPI/PPI 同比和市场通胀补偿为核心读法。",
      inflation_diagnostics: {
        label: "通胀诊断",
        regime: "reaccelerating",
        regime_label: "通胀再加速",
        summary: "通胀再加速：CPI/Core CPI 同比重新上行且通胀补偿走阔，降息交易需要降级。",
        rows: [
          {
            key: "cpi_yoy",
            label: "CPI 同比",
            current_yoy_pct: 5.3,
            change_1m_pct: 1.3,
            status: "accelerating",
            status_label: "加速",
          },
          {
            key: "core_cpi_yoy",
            label: "核心 CPI 同比",
            current_yoy_pct: 5.65,
            change_1m_pct: 1.32,
            status: "accelerating",
            status_label: "加速",
          },
          {
            key: "ppi_yoy",
            label: "PPI 同比",
            current_yoy_pct: 6.93,
            change_1m_pct: 0.93,
            status: "pipeline_pressure",
            status_label: "上游压力",
          },
          {
            key: "breakeven_10y",
            label: "10Y 通胀补偿",
            current_pct: 2.55,
            change_1w_bp: 10,
            change_1m_bp: 25,
            status: "expectation_pressure",
            status_label: "预期升温",
          },
        ],
        implications: ["通胀再加速：降低降息受益、长久期成长和高 beta 反弹置信度。"],
        invalidations: ["若核心 CPI 同比回落且 10Y 通胀补偿 1m 收窄超过 10bp，再加速读法降级。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "core_cpi_accelerating",
          label: "核心 CPI 加速",
          description: "核心通胀同比重新上行",
          evidence_label: "核心通胀同比重新上行",
        },
      ],
      contradictions: [
        {
          code: "pce_release_pending",
          label: "PCE 发布窗口",
          description: "下一次 BEA PCE 发布会验证 CPI 再加速是否扩散到 PCE。",
          evidence_label: "下一次 BEA PCE 发布会验证 CPI 再加速是否扩散到 PCE。",
        },
      ],
      watch_triggers: [
        {
          code: "breakevens_keep_widening",
          label: "通胀补偿继续走阔",
          description: "市场预期可能压制降息交易",
          evidence_label: "市场预期可能压制降息交易",
        },
      ],
      invalidations: [
        {
          code: "core_cpi_cools",
          label: "核心 CPI 回落",
          description: "通胀再加速读法降级",
          evidence_label: "通胀再加速读法降级",
        },
      ],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
    },
  });
}

export function macroEmploymentModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "economy/employment",
      route_path: "/macro/economy/employment",
      section: "economy",
      title: "就业市场",
      subtitle: "失业率、非农、初请、职位空缺与工资",
      question: "就业是在缓慢降温，还是触发增长风险？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      employmentTile("labor:unemployment", "失业率", "4.30%", "FRED"),
      employmentTile("labor:payrolls", "非农就业", "158,300k", "FRED"),
      employmentTile("labor:initial_claims", "初请失业金", "260k", "FRED"),
      employmentTile("labor:job_openings", "职位空缺", "7.40M", "FRED"),
      employmentTile("labor:avg_hourly_earnings", "平均时薪", "$36.50", "FRED"),
    ],
    primary_chart: {
      id: "employment_dashboard",
      title: "就业市场走势",
      subtitle: "失业率、非农、初请、JOLTS 与工资",
      kind: "line",
      status: "ok",
      status_label: "可用",
      min_points: 2,
      series: [
        { concept_key: "labor:unemployment", label: "失业率", latest: 4.3, unit: "percent" },
        {
          concept_key: "labor:payrolls",
          label: "非农就业",
          latest: 158300,
          unit: "thousand_persons",
        },
        {
          concept_key: "labor:initial_claims",
          label: "初请失业金",
          latest: 260000,
          unit: "persons",
        },
        {
          concept_key: "labor:job_openings",
          label: "职位空缺",
          latest: 7400,
          unit: "thousand_persons",
        },
        {
          concept_key: "labor:avg_hourly_earnings",
          label: "平均时薪",
          latest: 36.5,
          unit: "usd_per_hour",
        },
      ],
    },
    tables: [employmentTable()],
    module_read: {
      headline: "就业市场：就业降温",
      regime_label: "就业降温",
      confidence_label: "模块覆盖 5/7",
      data_note: "就业以失业率、非农增量、初请、职位空缺和工资同比为核心读法。",
      employment_diagnostics: {
        label: "就业诊断",
        regime: "labor_cooling",
        regime_label: "就业降温",
        summary: "就业降温：失业率与初请上行、非农动能放缓，增长风险开始压过软着陆叙事。",
        rows: [
          {
            key: "unemployment_rate",
            label: "失业率",
            current_pct: 4.3,
            change_1m_pct: 0.3,
            status: "deteriorating",
            status_label: "走弱",
          },
          {
            key: "payroll_gain",
            label: "非农新增",
            current_k: 80,
            change_1m_k: -140,
            status: "slowing",
            status_label: "放缓",
          },
          {
            key: "initial_claims",
            label: "初请失业金",
            current_k: 260,
            change_1w_k: 4,
            change_1m_k: 30,
            status: "claims_rising",
            status_label: "初请上行",
          },
          {
            key: "job_openings",
            label: "职位空缺",
            current_m: 7.4,
            change_1m_m: -0.6,
            status: "demand_cooling",
            status_label: "需求降温",
          },
          {
            key: "wage_yoy",
            label: "平均时薪同比",
            current_yoy_pct: 3.69,
            change_1m_pct: -0.88,
            status: "wage_cooling",
            status_label: "工资降温",
          },
        ],
        implications: ["就业降温：降低盈利周期和高 beta 置信度，降息交易需等待通胀同步配合。"],
        invalidations: ["若非农新增重新高于 180k 且初请 1m 回落超过 20k，就业降温读法降级。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "initial_claims_rising",
          label: "初请上行",
          description: "劳动力市场边际走弱",
          evidence_label: "劳动力市场边际走弱",
        },
      ],
      contradictions: [
        {
          code: "wages_still_supported",
          label: "工资仍有支撑",
          description: "平均时薪同比尚未快速下行",
          evidence_label: "平均时薪同比尚未快速下行",
        },
      ],
      watch_triggers: [
        {
          code: "payrolls_below_100k",
          label: "非农继续低于 100k",
          description: "增长风险会进一步升温",
          evidence_label: "增长风险会进一步升温",
        },
      ],
      invalidations: [
        {
          code: "payrolls_reaccelerate",
          label: "非农重新加速",
          description: "就业降温读法降级",
          evidence_label: "就业降温读法降级",
        },
      ],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
    },
  });
}

export function macroGdpModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "economy/gdp",
      route_path: "/macro/economy/gdp",
      section: "economy",
      title: "GDP 增长",
      subtitle: "实际 GDP、消费与增长代理",
      question: "增长数据是否足够支撑风险资产盈利预期？",
      status: "ok",
      status_label: "可用",
    },
    tiles: [
      growthTile("economy:gdp_real", "实际 GDP", "$22.62T", "FRED"),
      growthTile("economy:gdp_nowcast", "GDPNow", "1.50%", "FRED"),
      growthTile("economy:industrial_production", "工业生产", "98.50", "FRED"),
      growthTile("economy:housing_starts", "住房开工", "1.25M", "FRED"),
      growthTile("consumer:pce_real", "实际 PCE", "101.50", "FRED"),
      growthTile("consumer:retail_sales", "零售销售", "101.00", "FRED"),
    ],
    primary_chart: {
      id: "real_gdp_history",
      title: "实际 GDP 历史",
      subtitle: "实际 GDP、工业生产、消费和零售",
      kind: "line",
      status: "ok",
      status_label: "可用",
      min_points: 2,
      series: [
        { concept_key: "economy:gdp_real", label: "实际 GDP", latest: 22620, unit: "billion_usd" },
        {
          concept_key: "economy:industrial_production",
          label: "工业生产",
          latest: 98.5,
          unit: "index",
        },
        {
          concept_key: "economy:housing_starts",
          label: "住房开工",
          latest: 1250,
          unit: "thousand_units",
        },
        { concept_key: "consumer:pce_real", label: "实际 PCE", latest: 101.5, unit: "index" },
        { concept_key: "consumer:retail_sales", label: "零售销售", latest: 101, unit: "index" },
      ],
    },
    tables: [growthTable()],
    module_read: {
      headline: "GDP 增长：增长降温",
      regime_label: "增长降温",
      confidence_label: "模块覆盖 5/10",
      data_note: "增长以实际 GDP、工业生产、地产开工、实际消费和零售为核心读法。",
      growth_diagnostics: {
        label: "增长诊断",
        regime: "growth_cooling",
        regime_label: "增长降温",
        summary: "增长降温：实际 GDP、工业生产和消费动能同步放缓，风险资产盈利预期需要降级。",
        rows: [
          {
            key: "real_gdp_yoy",
            label: "实际 GDP 同比",
            current_yoy_pct: 1.89,
            change_1q_pct: -0.84,
            status: "slowing",
            status_label: "放缓",
          },
          {
            key: "gdpnow_saar",
            label: "GDPNow",
            current_pct: 1.5,
            change_1m_pct: -1.7,
            status: "nowcast_cooling",
            status_label: "Nowcast 降温",
          },
          {
            key: "industrial_production_yoy",
            label: "工业生产同比",
            current_yoy_pct: -1.5,
            change_1m_pct: -2,
            status: "contracting",
            status_label: "收缩",
          },
          {
            key: "housing_starts",
            label: "住房开工",
            current_m: 1.25,
            change_1m_k: -150,
            status: "housing_drag",
            status_label: "地产拖累",
          },
          {
            key: "real_pce_yoy",
            label: "实际 PCE 同比",
            current_yoy_pct: 1.5,
            change_1m_pct: -1,
            status: "consumption_cooling",
            status_label: "消费降温",
          },
          {
            key: "retail_sales_yoy",
            label: "零售销售同比",
            current_yoy_pct: 1,
            change_1m_pct: -2,
            status: "demand_cooling",
            status_label: "需求降温",
          },
        ],
        implications: ["增长降温：降低盈利周期和高 beta 暴露，等待就业或消费重新确认。"],
        invalidations: ["若实际 PCE 与工业生产同比回升且住房开工 1m 转正，增长降温读法降级。"],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "industrial_production_weakening",
          label: "工业生产转弱",
          description: "生产端开始拖累增长动能",
          evidence_label: "生产端开始拖累增长动能",
        },
      ],
      contradictions: [
        {
          code: "employment_still_neutral",
          label: "就业仍中性",
          description: "劳动力市场尚未确认硬着陆",
          evidence_label: "劳动力市场尚未确认硬着陆",
        },
      ],
      watch_triggers: [
        {
          code: "real_pce_weakens",
          label: "实际 PCE 继续走弱",
          description: "消费放缓会压低盈利预期",
          evidence_label: "消费放缓会压低盈利预期",
        },
      ],
      invalidations: [
        {
          code: "housing_starts_turn_positive",
          label: "住房开工转正",
          description: "增长降温读法降级",
          evidence_label: "增长降温读法降级",
        },
      ],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "模块数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
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
    status_label: "SOFR 30D 缺失",
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
        status_label: "缺失",
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
      policy_diagnostics: {
        label: "政策走廊诊断",
        regime: "corridor_pressure",
        regime_label: "走廊压力",
        summary: "政策走廊承压：EFFR 高于目标上限且 SOFR 相对 EFFR 走阔，隔夜融资压力需要降杠杆。",
        rows: [
          {
            key: "target_range",
            label: "目标区间",
            lower_pct: 4.25,
            upper_pct: 4.5,
            width_bp: 25,
            status: "range_defined",
            status_label: "区间明确",
          },
          {
            key: "effr_vs_range",
            label: "EFFR 位置",
            current_pct: 4.55,
            distance_to_upper_bp: 5,
            change_1w_bp: 20,
            status: "above_upper",
            status_label: "高于上限",
          },
          {
            key: "effr_iorb_spread",
            label: "EFFR-IORB",
            current_bp: 15,
            change_1w_bp: 20,
            status: "corridor_pressure",
            status_label: "走廊压力",
          },
          {
            key: "sofr_effr_spread",
            label: "SOFR-EFFR",
            current_bp: 7,
            change_1w_bp: 6,
            status: "funding_pressure",
            status_label: "融资压力",
          },
          {
            key: "sofr_30d_effr_spread",
            label: "SOFR 30D-EFFR",
            current_bp: 2,
            change_1w_bp: 2,
            status: "stable",
            status_label: "稳定",
          },
          {
            key: "dff_effr_spread",
            label: "DFF-EFFR",
            current_bp: -1,
            change_1w_bp: 0,
            status: "stable",
            status_label: "稳定",
          },
          {
            key: "obfr_effr_spread",
            label: "OBFR-EFFR",
            current_bp: 8,
            change_1w_bp: 6,
            status: "broader_unsecured_pressure",
            status_label: "广义无担保压力",
          },
          {
            key: "effr_volume",
            label: "EFFR 成交量",
            current_bn: 102,
            change_1w_bn: -43,
            status: "thin_depth",
            status_label: "成交变薄",
          },
          {
            key: "obfr_volume",
            label: "OBFR 成交量",
            current_bn: 196,
            change_1w_bn: -14,
            status: "depth_ok",
            status_label: "深度稳定",
          },
        ],
        implications: ["走廊压力：降低融资敏感资产和杠杆多头，等待 EFFR 回到目标区间内。"],
        invalidations: [
          "若 EFFR 回落至目标上限下方且 SOFR-EFFR 收窄至 0bp 附近，走廊压力读法降级。",
        ],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "effr_inside_target_range",
          label: "EFFR 位于目标区间内",
          description: "隔夜政策利率未显示越界压力",
          evidence_label: "隔夜政策利率未显示越界压力",
        },
      ],
      contradictions: [],
      watch_triggers: [
        {
          code: "sofr_rises",
          label: "SOFR 上行",
          description: "若 SOFR 持续贴近区间上沿，需要关注融资压力",
          evidence_label: "若 SOFR 持续贴近区间上沿，需要关注融资压力",
        },
      ],
      invalidations: [
        {
          code: "effr_crosses_upper_bound",
          label: "EFFR 越过上限",
          description: "政策走廊稳定判断失效",
          evidence_label: "政策走廊稳定判断失效",
        },
      ],
    },
    data_health: {
      summary_status: "partial",
      summary_label: "走廊数据部分可用",
      module_gaps: [{ code: "sofr_30d_missing", label: "SOFR 30D 尚未入库", severity: "info" }],
      chart_gaps: [],
      global_gaps: [],
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
      real_rate_diagnostics: {
        label: "实际利率诊断",
        regime: "real_rate_pressure",
        regime_label: "实际利率压力",
        summary:
          "实际利率上行且通胀补偿未同步走阔：估值压力偏实际利率驱动，长久期与高 beta 需要降级。",
        real_yield_rows: [
          {
            key: "real_5y",
            label: "5Y Real",
            current_pct: 2.05,
            change_1w_bp: 20,
            change_1m_bp: 35,
            change_3m_bp: 45,
            status: "valuation_pressure",
            status_label: "估值压力",
          },
          {
            key: "real_10y",
            label: "10Y Real",
            current_pct: 2.1,
            change_1w_bp: 20,
            change_1m_bp: 30,
            change_3m_bp: 40,
            status: "valuation_pressure",
            status_label: "估值压力",
          },
        ],
        inflation_rows: [
          {
            key: "breakeven_10y",
            label: "10Y Breakeven",
            current_pct: 2.15,
            change_1w_bp: -5,
            change_1m_bp: -10,
            change_3m_bp: -5,
            status: "falling",
            status_label: "补偿回落",
          },
          {
            key: "forward_5y5y",
            label: "5Y5Y Forward",
            current_pct: 2.25,
            change_1w_bp: -5,
            change_1m_bp: -10,
            change_3m_bp: -15,
            status: "falling",
            status_label: "补偿回落",
          },
        ],
        implications: ["实际利率压力：降低长久期成长、长债和高 beta 反弹置信度。"],
        invalidations: [
          "若 10Y 实际利率单周回落超过 15bp，且 breakeven 不再回落，实际利率压力读法降级。",
        ],
      },
    },
    module_evidence: {
      confirmations: [
        {
          code: "tips_curve_available",
          label: "TIPS 曲线可用",
          description: "5年期和10年期实际利率最新值存在",
          evidence_label: "5年期和10年期实际利率最新值存在",
        },
      ],
      contradictions: [],
      watch_triggers: [
        {
          code: "real_rates_rise_fast",
          label: "实际利率快速上行",
          description: "估值压力需要重新评估",
          evidence_label: "估值压力需要重新评估",
        },
      ],
      invalidations: [],
    },
    data_health: {
      summary_status: "ok",
      summary_label: "实际利率数据可用",
      module_gaps: [],
      chart_gaps: [],
      global_gaps: [],
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
      { key: "symbol", label: "代码" },
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
          symbol: { display_value: "^GSPC", sort_value: "^GSPC" },
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

function creditTile(
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

function volatilityTile(
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
    unit: "index",
    unit_label: "点",
    source_label: sourceLabel,
    observed_at: "2026-05-20",
    observed_at_label: "观测于 2026-05-20",
    quality: "ok",
    quality_label: "可用",
  };
}

function liquidityTile(
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
    unit: "mixed",
    unit_label: "",
    source_label: sourceLabel,
    observed_at: "2026-05-20",
    observed_at_label: "观测于 2026-05-20",
    quality: "ok",
    quality_label: "可用",
  };
}

function inflationTile(
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
    unit: "mixed",
    unit_label: "",
    source_label: sourceLabel,
    observed_at: "2026-05-20",
    observed_at_label: "观测于 2026-05-20",
    quality: "ok",
    quality_label: "可用",
  };
}

function employmentTile(
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
    unit: "mixed",
    unit_label: "",
    source_label: sourceLabel,
    observed_at: "2026-05-20",
    observed_at_label: "观测于 2026-05-20",
    quality: "ok",
    quality_label: "可用",
  };
}

function growthTile(
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
    unit: "mixed",
    unit_label: "",
    source_label: sourceLabel,
    observed_at: "2026-05-20",
    observed_at_label: "观测于 2026-05-20",
    quality: "ok",
    quality_label: "可用",
  };
}

function creditStressTable(): MacroModuleTable {
  return {
    id: "credit_stress_table",
    title: "信用压力快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("credit:hy_oas", "HY OAS", "4.20%", "FRED", "可用"),
      ratesRow("credit:ig_oas", "IG OAS", "1.20%", "FRED", "可用"),
      ratesRow("credit:hy_ccc_oas", "CCC OAS", "9.50%", "FRED", "可用"),
      ratesRow("credit:nfci", "NFCI", "-0.10", "FRED", "可用"),
      ratesRow(
        "credit:sloos_ci_large_tightening",
        "SLOOS 大中型收紧",
        "30%",
        "Federal Reserve",
        "可用",
      ),
    ],
  };
}

function volatilityVixTable(): MacroModuleTable {
  return {
    id: "vix_term_proxy_table",
    title: "VIX 期限代理表",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("vol:vix", "VIX", "16.90", "FRED", "可用"),
      ratesRow("vol:vix1d", "VIX1D", "17.30", "Cboe", "可用"),
      ratesRow("vol:vix9d", "VIX9D", "18.00", "Cboe", "可用"),
      ratesRow("vol:vix3m", "VIX3M", "23.80", "FRED", "可用"),
      ratesRow("vol:vvix", "VVIX", "88.00", "Cboe", "可用"),
      ratesRow("vol:skew", "SKEW", "143.80", "Cboe", "可用"),
      ratesRow("asset:vixy", "VIXY", "18.00", "Yahoo Finance", "可用"),
      ratesRow("asset:vixm", "VIXM", "29.00", "Yahoo Finance", "可用"),
    ],
  };
}

function liquidityRrpTgaTable(): MacroModuleTable {
  return {
    id: "rrp_tga_table",
    title: "RRP / TGA 快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("liquidity:sofr", "SOFR", "4.47%", "Federal Reserve Bank of New York", "可用"),
      ratesRow("fed:iorb", "IORB", "4.40%", "Federal Reserve", "可用"),
      ratesRow("liquidity:on_rrp", "ON RRP", "$760B", "FRED", "可用"),
      ratesRow("liquidity:tga", "TGA", "$760B", "U.S. Treasury", "可用"),
    ],
  };
}

function inflationTable(): MacroModuleTable {
  return {
    id: "inflation_table",
    title: "通胀快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("inflation:cpi", "CPI", "318.00", "FRED", "可用"),
      ratesRow("inflation:core_cpi", "核心 CPI", "318.00", "FRED", "可用"),
      ratesRow("inflation:ppi", "PPI", "108.00", "FRED", "可用"),
      ratesRow("inflation:10y_breakeven", "10Y 通胀补偿", "2.55%", "FRED", "可用"),
    ],
  };
}

function employmentTable(): MacroModuleTable {
  return {
    id: "employment_table",
    title: "就业快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("labor:unemployment", "失业率", "4.30%", "FRED", "可用"),
      ratesRow("labor:payrolls", "非农就业", "158,300k", "FRED", "可用"),
      ratesRow("labor:initial_claims", "初请失业金", "260k", "FRED", "可用"),
      ratesRow("labor:job_openings", "职位空缺", "7.40M", "FRED", "可用"),
      ratesRow("labor:avg_hourly_earnings", "平均时薪", "$36.50", "FRED", "可用"),
    ],
  };
}

function growthTable(): MacroModuleTable {
  return {
    id: "real_gdp_table",
    title: "增长快照",
    status: "ok",
    columns: [
      { key: "indicator", label: "指标" },
      { key: "latest", label: "最新值" },
      { key: "source", label: "来源" },
      { key: "quality", label: "质量" },
    ],
    rows: [
      ratesRow("economy:gdp_real", "实际 GDP", "$22.62T", "FRED", "可用"),
      ratesRow("economy:gdp_nowcast", "GDPNow", "1.50%", "FRED", "可用"),
      ratesRow("economy:industrial_production", "工业生产", "98.50", "FRED", "可用"),
      ratesRow("economy:housing_starts", "住房开工", "1.25M", "FRED", "可用"),
      ratesRow("consumer:pce_real", "实际 PCE", "101.50", "FRED", "可用"),
      ratesRow("consumer:retail_sales", "零售销售", "101.00", "FRED", "可用"),
    ],
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
