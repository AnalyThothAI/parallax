import type {
  MacroLiveEvidenceReadData,
  MacroLiveMetricData,
  MacroLiveReadViewId,
  MacroLiveViewData,
  MacroLiveViewId,
  MacroResearchReadData,
} from "@features/macro";

export function macroResearchFixture(
  state: MacroResearchReadData["state"] = "current",
): MacroResearchReadData {
  const hasPublication = state === "current" || state === "historical";
  const hasRun = state === "generating" || state === "failed";
  return {
    state,
    requested_session_date: state === "historical" ? "2026-07-22" : "2026-07-23",
    current_session_date: "2026-07-23",
    publication: hasPublication
      ? {
          schema_version: "macro_research_artifact_v2",
          session_date: state === "historical" ? "2026-07-22" : "2026-07-23",
          market_cutoff_ms: 1_774_200_000_000,
          title: "宏观研究：增长与实际利率的拉锯",
          executive_summary: "增长放缓与实际利率高位并存，风险资产缺少单边确认。",
          sections: [
            {
              section_id: "mechanism",
              title: "核心机制",
              body_markdown: "实际利率维持高位，信用尚未确认系统性收紧。",
              citation_ids: ["M001"],
            },
            {
              section_id: "counterevidence",
              title: "关键反证",
              body_markdown: "信用利差尚未确认增长冲击已扩散到融资条件。",
              citation_ids: ["M002"],
            },
          ],
          evidence_gaps: [
            {
              gap_id: "term-premium-history",
              summary: "期限溢价历史窗口不足",
              details: "无法可靠区分供给冲击与增长预期。",
              citation_ids: [],
            },
          ],
          citations: [
            {
              citation_id: "M001",
              source_type: "macro_observation",
              source_ref: "macro:rates:dgs10:2026-07-23",
              source_label: "U.S. Treasury 10Y",
              observed_at: "2026-07-23",
              published_at_ms: null,
              available_at_ms: 1_774_199_000_000,
              source_url: "https://fred.stlouisfed.org/series/DGS10",
              lineage: { concept_key: "rates:dgs10" },
            },
            {
              citation_id: "M002",
              source_type: "macro_observation",
              source_ref: "macro:credit:hy_oas:2026-07-23",
              source_label: "ICE BofA High Yield OAS",
              observed_at: "2026-07-23",
              published_at_ms: null,
              available_at_ms: 1_774_199_000_000,
              source_url: null,
              lineage: { concept_key: "credit:hy_oas" },
            },
          ],
          reviewer_notes: ["反证已覆盖，但期限溢价仍应标为缺口。"],
          audit: {
            model: "provider-model",
            planning_used: true,
            subagents_used: ["skeptic"],
          },
          published_at_ms: 1_774_202_000_000,
        }
      : null,
    run: hasRun
      ? {
          session_date: "2026-07-23",
          status: state === "generating" ? "running" : "failed",
          attempt_count: 1,
          max_attempts: 3,
          last_error: state === "failed" ? "provider_timeout" : null,
          updated_at_ms: 1_774_201_900_000,
        }
      : null,
  };
}

const LIVE_READ_AT_MS = 1_774_300_000_000;

export function macroLiveEvidenceFixture(
  viewId: MacroLiveReadViewId = "dashboard",
): MacroLiveEvidenceReadData {
  const viewIds: MacroLiveViewId[] =
    viewId === "dashboard"
      ? [
          "overview",
          "rates-inflation",
          "growth-labor",
          "liquidity-funding",
          "credit",
          "cross-asset",
        ]
      : [viewId];
  return {
    schema_version: "macro_live_evidence_v1",
    view_id: viewId,
    window: "90d",
    read_at_ms: LIVE_READ_AT_MS,
    views: viewIds.map(liveView),
    unclassified:
      viewId === "dashboard"
        ? [
            liveMetric({
              concept_key: "macro:new_fact",
              page_id: null,
              section_id: "unclassified",
              section_label: "未分类事实",
              display_label: "macro:new_fact",
              series_key: "fixture:new",
            }),
          ]
        : [],
    research: {
      state: "current",
      session_date: "2026-07-23",
      market_cutoff_ms: 1_774_200_000_000,
      title: "宏观研究：增长与实际利率的拉锯",
      executive_summary: "增长放缓与实际利率高位并存，风险资产缺少单边确认。",
      evidence_gap_summaries: ["期限溢价历史窗口不足"],
      href: "/macro/research",
    },
  };
}

function liveView(viewId: MacroLiveViewId): MacroLiveViewData {
  const meta: Record<MacroLiveViewId, [string, string, string]> = {
    overview: ["总览与官方催化", "已知官方催化日历。", "event:fomc_decision_next"],
    "rates-inflation": ["利率与通胀", "名义曲线、实际利率与通胀。", "rates:dgs10"],
    "growth-labor": ["增长与就业", "增长、消费与就业事实。", "labor:initial_claims"],
    "liquidity-funding": ["流动性与资金", "资产负债表与资金市场。", "liquidity:fed_assets"],
    credit: ["信用", "信用利差与融资条件。", "credit:hy_oas"],
    "cross-asset": ["跨资产", "资产价格、收益与波动率。", "asset:spy"],
  };
  const [title, description, conceptKey] = meta[viewId];
  const primary = liveMetric({
    concept_key: conceptKey,
    page_id: viewId,
    section_id: viewId === "cross-asset" ? "asset_returns" : "summary",
    section_label: viewId === "cross-asset" ? "资产价格与收益" : "核心数据",
    display_label: {
      overview: "下一次 FOMC 利率决议",
      "rates-inflation": "美国 10 年期国债收益率",
      "growth-labor": "首次申请失业救济人数",
      "liquidity-funding": "美联储总资产",
      credit: "高收益公司债 OAS",
      "cross-asset": "标普 500 ETF（SPY）",
    }[viewId],
    unit: viewId === "credit" ? "basis_points" : viewId === "growth-labor" ? "number" : "percent",
  });
  const metrics =
    viewId === "overview"
      ? [primary]
      : [
          primary,
          liveMetric({
            concept_key: `${conceptKey}:missing`,
            page_id: viewId,
            section_id: "secondary",
            section_label: "补充数据",
            display_label: "尚无观测的补充指标",
            availability: "missing",
            value_numeric: null,
            observed_at: null,
            source_timestamp: null,
            received_at_ms: null,
            source_name: null,
            series_key: null,
            data_quality: null,
            history: [],
            calculation: null,
          }),
        ];
  return {
    view_id: viewId,
    title,
    description,
    metrics,
    total_metric_count: metrics.length,
    available_count: metrics.filter((metric) => metric.availability === "available").length,
    latest_observed_at: "2026-07-23",
    max_received_at_ms: LIVE_READ_AT_MS - 10_000,
  };
}

function liveMetric(overrides: Partial<MacroLiveMetricData> = {}): MacroLiveMetricData {
  return {
    concept_key: "rates:dgs10",
    page_id: "rates-inflation",
    section_id: "nominal_curve",
    section_label: "名义收益率曲线",
    display_label: "美国 10 年期国债收益率",
    display_order: 1,
    summary: true,
    kind: "material",
    availability: "available",
    value_numeric: 4.22,
    unit: "percent",
    frequency: "daily",
    observed_at: "2026-07-23",
    source_timestamp: "2026-07-23T16:00:00-04:00",
    received_at_ms: LIVE_READ_AT_MS - 10_000,
    source_name: "fixture",
    series_key: "fred:DGS10",
    source_priority: 100,
    data_quality: "ok",
    source_url: "https://fred.stlouisfed.org/series/DGS10",
    history: [
      {
        observed_at: "2026-07-21",
        value_numeric: 4.1,
        source_timestamp: "2026-07-21",
        received_at_ms: LIVE_READ_AT_MS - 180_000,
        source_name: "fixture",
        series_key: "fred:DGS10",
        source_priority: 100,
        frequency: "daily",
        data_quality: "ok",
        source_url: "https://fred.stlouisfed.org/series/DGS10",
      },
      {
        observed_at: "2026-07-23",
        value_numeric: 4.22,
        source_timestamp: "2026-07-23T16:00:00-04:00",
        received_at_ms: LIVE_READ_AT_MS - 10_000,
        source_name: "fixture",
        series_key: "fred:DGS10",
        source_priority: 100,
        frequency: "daily",
        data_quality: "ok",
        source_url: "https://fred.stlouisfed.org/series/DGS10",
      },
    ],
    calculation: {
      formula_id: "window_difference_v1",
      formula: "latest - first",
      operands: ["rates:dgs10"],
      window: "90d",
      sample_size: 2,
      result: 0.12,
      unit: "percent",
    },
    ...overrides,
  };
}
