import type { components } from "@lib/types/openapi";

type MacroOverviewData = components["schemas"]["MacroOverviewData"];
type MacroCrossAssetData = components["schemas"]["MacroCrossAssetData"];
type MacroRatesInflationData = components["schemas"]["MacroRatesInflationData"];
type MacroGrowthLaborData = components["schemas"]["MacroGrowthLaborData"];
type MacroLiquidityFundingData = components["schemas"]["MacroLiquidityFundingData"];
type MacroCreditData = components["schemas"]["MacroCreditData"];
type MacroEvidenceData = components["schemas"]["MacroEvidenceData"];
type MacroMetricData = components["schemas"]["MacroMetricData"];
type MacroSeriesData = components["schemas"]["MacroSeriesData"];
type DailyMacroJudgmentReadData = components["schemas"]["DailyMacroJudgmentReadData"];

const SNAPSHOT = {
  computed_at_ms: Date.parse("2026-07-23T02:00:00Z"),
  fact_watermark: "2026-07-22T21:00:00Z",
  market_cutoff: "2026-07-22",
  projection_version: "macro_decision_v2",
} as const;

const SAMPLE = {
  count: 60,
  end: "2026-07-22",
  start: "2026-04-29",
};

export function dailyMacroJudgmentFixture(): DailyMacroJudgmentReadData {
  const marketCutoffMs = Date.parse("2026-07-22T20:00:00Z");
  const evidencePackHash = "7".repeat(64);
  return {
    is_current: true,
    publication: {
      agent_audit: {
        analyst_submissions: 1,
        native_review_calls: 1,
      },
      compiler_version: "macro_evidence_pack_v1",
      evidence_pack: {
        evidence: [],
        exclusions: [],
        health: {
          global_reasons: [],
          local_reasons: ["overview_insufficient_evidence"],
          no_call_horizons: [5, 20],
          status: "degraded",
        },
        market_cutoff_ms: marketCutoffMs,
        pages: {},
        projection_version: "macro_decision_v2",
        schema_version: "macro_evidence_pack_v1",
        sealed_at_ms: marketCutoffMs + 60_000,
        selection_policy_version: "macro_point_in_time_v1",
        session_date: "2026-07-22",
        texts: [],
      },
      evidence_pack_hash: evidencePackHash,
      judgment: {
        audit_versions: {
          evidence_pack_hash: evidencePackHash,
          prompt_version: "daily_macro_spy_v1",
          schema_version: "daily_macro_judgment_v1",
          workflow_version: "daily_macro_deepagent_v1",
        },
        counterevidence: [
          {
            evidence_refs: ["overview:asset:spy"],
            statement: "SPY 与 BTC 的价格表现仍有支撑，不能形成单边风险结论。",
          },
          {
            evidence_refs: ["credit:hy_oas"],
            statement: "信用压力集中在尾部，整体利差尚未确认即时下行方向。",
          },
        ],
        data_health: "degraded",
        experimental_marker: "experimental_shadow_research",
        macro_state:
          "跨资产信号分化：SPY 与 BTC 偏强，但实际利率、尾部信用压力和波动率风险仍构成逆风。",
        market_cutoff_ms: marketCutoffMs,
        pressures: [
          {
            axis: "policy_real_rates",
            evidence_refs: ["rates:real_10y"],
            mechanism: "名义与实际利率维持高位，继续压制股票估值。",
            state: "elevated",
          },
          {
            axis: "credit",
            evidence_refs: ["credit:hy_oas"],
            mechanism: "高收益与 CCC 尾部利差压力抵消了股票价格的支撑。",
            state: "elevated",
          },
        ],
        session_date: "2026-07-22",
        spy_20d: {
          direction: "no_call",
          evidence_refs: ["overview:asset:spy", "credit:hy_oas"],
          horizon_sessions: 20,
          thesis: "关键页面降级且跨资产条件分化，20 个交易日没有可靠方向。",
        },
        spy_5d: {
          direction: "no_call",
          evidence_refs: ["overview:asset:spy", "rates:real_10y"],
          horizon_sessions: 5,
          thesis: "价格支撑与实际利率、信用压力相互抵消，5 个交易日暂不判断。",
        },
      },
      market_cutoff_ms: marketCutoffMs,
      memo_text: "# 每日宏观 SPY 研判",
      model_name: "openai/gpt-5.5",
      outcomes: [],
      prompt_version: "daily_macro_spy_v1",
      published_at_ms: marketCutoffMs + 120_000,
      renderer_version: "daily_macro_judgment_zh_v1",
      review: {
        disposition: "pass",
        issues: [],
      },
      schema_version: "daily_macro_judgment_v1",
      sealed_at_ms: marketCutoffMs + 60_000,
      selection_policy_version: "macro_point_in_time_v1",
      session_date: "2026-07-22",
      workflow_version: "daily_macro_deepagent_v1",
    },
    state: "current",
    target_job: {
      attempt_count: 1,
      due_at_ms: marketCutoffMs,
      last_error: null,
      market_cutoff_ms: marketCutoffMs,
      max_attempts: 3,
      reviewer_disposition: "pass",
      session_date: "2026-07-22",
      status: "published",
      updated_at_ms: marketCutoffMs + 120_000,
    },
    target_session_date: "2026-07-22",
  };
}

function evidence(
  conceptKey: string,
  value: number | null,
  overrides: Partial<MacroEvidenceData> = {},
): MacroEvidenceData {
  return {
    change: value === null ? null : 0.1,
    change_window: "20_sessions",
    claim_effect: "risk_asset_direction",
    concept_key: conceptKey,
    criticality: "optional",
    data_quality: value === null ? "missing" : "ok",
    derivation: null,
    frequency: "daily",
    freshness: {
      age_days: value === null ? null : 1,
      stale_after_days: 3,
      status: value === null ? "missing" : "fresh",
    },
    observed_at: value === null ? null : "2026-07-22",
    reason: value === null ? "missing_observation" : null,
    role: "context",
    sample: { ...SAMPLE },
    series_key: conceptKey,
    source_name: value === null ? null : "FRED",
    status: value === null ? "unavailable" : "available",
    unit: "percent",
    value,
    ...overrides,
  };
}

function metric(conceptKey: string, value: number, unit = "percent"): MacroMetricData {
  return {
    concept_key: conceptKey,
    derivation: null,
    reason: null,
    sample: { ...SAMPLE },
    status: "available",
    unit,
    value,
    window: "1_release",
  };
}

function common(
  judgment: string,
  evidenceItems: MacroEvidenceData[],
  {
    confirmationCode,
    invalidationCode,
    ruleId,
    unavailableCapability,
    upgradeCode,
  }: {
    confirmationCode: string;
    invalidationCode: string;
    ruleId: string;
    unavailableCapability: string;
    upgradeCode: string;
  },
) {
  return {
    conclusion: {
      judgment,
      rule_hits: [
        {
          evidence_refs: [evidenceItems[0]?.concept_key ?? "evidence:missing"],
          outcome: "trigger" as const,
          rule_id: ruleId,
        },
      ],
      rule_version: "macro_evidence_rules_v1",
      status: "supported" as const,
    },
    confirmations: [
      {
        code: confirmationCode,
        evidence_refs: evidenceItems.slice(1, 3).map((item) => item.concept_key),
      },
    ],
    contradictions: [],
    drivers: [
      {
        code: ruleId,
        evidence_refs: [evidenceItems[0]?.concept_key ?? "evidence:missing"],
      },
    ],
    evidence: evidenceItems,
    evidence_refs: evidenceItems.map((item) => item.concept_key),
    freshness: {
      critical_missing: [],
      critical_stale: [],
      optional_unavailable: [],
      status: "fresh" as const,
    },
    horizon: "1_4_weeks" as const,
    snapshot: { ...SNAPSHOT },
    unavailable_evidence: [
      {
        capability: unavailableCapability,
        reason: "source_not_ingested",
        status: "not_assessed" as const,
      },
    ],
    upgrade_invalidation: {
      invalidation: [
        {
          code: invalidationCode,
          evidence_refs: [evidenceItems[0]?.concept_key ?? "evidence:missing"],
        },
      ],
      upgrade: [
        {
          code: upgradeCode,
          evidence_refs: evidenceItems.slice(1, 3).map((item) => item.concept_key),
        },
      ],
    },
  };
}

export function macroOverviewFixture(): MacroOverviewData {
  const items = [
    evidence("rates:real_10y", 2.1, {
      change: 0.34,
      claim_effect: "real_rate_direction",
      criticality: "critical",
      role: "primary",
    }),
    evidence("rates:dgs10", 4.58, {
      change: 0.31,
      claim_effect: "long_rate_direction",
      role: "confirmation",
    }),
    evidence("asset:spy", 624.1, {
      change: -2.4,
      change_window: "20_sessions",
      claim_effect: "risk_asset_direction",
      role: "confirmation",
      unit: "price",
    }),
  ];
  return {
    ...common("policy_real_rates", items, {
      confirmationCode: "cross_asset_risk_off",
      invalidationCode: "primary_trigger_reversal",
      ruleId: "real_rate_up_20_sessions",
      unavailableCapability: "official_catalyst:event:bea_gdp_next",
      upgradeCode: "additional_cross_domain_confirmation",
    }),
    core_invalidation: {
      code: "dominant_shock_trigger_reverses",
      evidence_refs: ["rates:real_10y", "rates:dgs10", "asset:spy"],
    },
    key_changes: [
      {
        code: "us_equities_weakening",
        evidence_refs: ["asset:spy", "asset:qqq"],
        lane_id: "us_equities",
        rank: 1,
        summary: "美国股票：逆风，较五个已完成交易日前减弱。",
      },
      {
        code: "long_duration_treasuries_strengthening",
        evidence_refs: ["asset:tlt", "rates:dgs10"],
        lane_id: "long_duration_treasuries",
        rank: 2,
        summary: "长期美债：逆风，较五个已完成交易日前增强。",
      },
    ],
    nearest_catalyst: {
      concept_key: "event:bls_employment_next",
      event_at_ms: Date.parse("2026-07-23T12:30:00Z"),
      event_date: "2026-07-23",
      event_time: "08:30",
      evidence_ref: "event:bls_employment_next",
      release_status: "today",
      series_key: "labor:initial_claims",
      source_name: "U.S. Department of Labor",
      source_url: "https://www.dol.gov/ui/data.pdf",
      timezone: "America/New_York",
    },
    risk_lanes: [
      riskLane("us_equities", "headwind", "weakening", "high", "asset:spy", "asset:qqq"),
      riskLane(
        "long_duration_treasuries",
        "headwind",
        "strengthening",
        "high",
        "asset:tlt",
        "rates:dgs10",
      ),
      riskLane("credit", "neutral", "stable", "medium", "asset:hyg", "credit:hy_oas"),
      riskLane("usd", "tailwind", "strengthening", "high", "fx:dxy", "rates:dgs10"),
      riskLane("gold", "headwind", "stable", "low", "asset:gld", "rates:real_10y"),
      riskLane("oil", "neutral", "stable", "medium", "asset:uso", "inflation:10y_breakeven"),
      riskLane("crypto", "headwind", "weakening", "high", "crypto:btc", "crypto:eth"),
      riskLane("market_volatility", "tailwind", "strengthening", "high", "vol:vix", "vol:vix3m"),
    ],
    shock_summary: {
      candidate: "policy_real_rates",
      confidence: "high",
      confirmations: [{ code: "risk_off_confirmation", evidence_refs: ["asset:spy"] }],
      contradictions: [],
      drivers: [{ code: "real_rate_up_20_sessions", evidence_refs: ["rates:real_10y"] }],
      evidence_refs: ["rates:real_10y", "rates:dgs10", "asset:spy"],
      state: "dominant",
      summary: "当前主导冲击：实际利率收紧。",
      trend: "strengthening",
    },
    official_catalysts: [
      {
        concept_key: "event:bls_employment_next",
        event_at_ms: Date.parse("2026-07-23T12:30:00Z"),
        event_date: "2026-07-23",
        event_time: "08:30",
        evidence_ref: "event:bls_employment_next",
        release_status: "today",
        series_key: "labor:initial_claims",
        source_name: "U.S. Department of Labor",
        source_url: "https://www.dol.gov/ui/data.pdf",
        timezone: "America/New_York",
      },
      {
        concept_key: "event:fomc_decision_next",
        event_at_ms: Date.parse("2026-07-29T18:00:00Z"),
        event_date: "2026-07-29",
        event_time: "14:00",
        evidence_ref: "event:fomc_decision_next",
        release_status: "upcoming",
        series_key: "fed:fomc_calendar",
        source_name: "Federal Reserve",
        source_url: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        timezone: "America/New_York",
      },
    ],
    page_id: "overview",
  };
}

function riskLane(
  laneId: MacroOverviewData["risk_lanes"][number]["lane_id"],
  direction: MacroOverviewData["risk_lanes"][number]["direction"],
  trend: MacroOverviewData["risk_lanes"][number]["trend"],
  confidence: MacroOverviewData["risk_lanes"][number]["confidence"],
  anchor: string,
  confirmation: string,
): MacroOverviewData["risk_lanes"][number] {
  const laneLabels = {
    credit: "信用",
    crypto: "加密资产",
    gold: "黄金",
    long_duration_treasuries: "长期美债",
    market_volatility: "市场波动率",
    oil: "原油",
    usd: "美元",
    us_equities: "美国股票",
  } as const;
  const directionLabels = {
    headwind: "逆风",
    insufficient_evidence: "证据不足",
    neutral: "中性",
    tailwind: "顺风",
  } as const;
  const trendLabels = {
    insufficient_evidence: "缺少可比历史",
    stable: "基本不变",
    strengthening: "增强",
    weakening: "减弱",
  } as const;
  return {
    comparison_session: "2026-07-15",
    confidence,
    contradiction:
      confidence === "low"
        ? { code: `${laneId}_confirmation_conflicts`, evidence_refs: [confirmation] }
        : null,
    current_session: "2026-07-22",
    degradation_reason: null,
    direction,
    drivers: [{ code: `${laneId}_${direction}`, evidence_refs: [anchor] }],
    evidence_refs: [anchor, confirmation],
    invalidation: {
      code:
        direction === "neutral" ? `${laneId}_breaks_neutral_range` : `${laneId}_direction_reverses`,
      evidence_refs: [anchor, confirmation],
    },
    lane_id: laneId,
    sparkline_concept_key: anchor,
    summary: `${laneLabels[laneId]}：${directionLabels[direction]}，较五个已完成交易日前${trendLabels[trend]}。`,
    trend,
  };
}

export function macroOverviewNoShockFixture(): MacroOverviewData {
  const fixture = macroOverviewFixture();
  return {
    ...fixture,
    core_invalidation: {
      code: "cross_asset_consensus_emerges",
      evidence_refs: ["asset:spy", "asset:tlt", "asset:hyg"],
    },
    shock_summary: {
      candidate: null,
      confidence: "medium",
      confirmations: [],
      contradictions: [],
      drivers: [],
      evidence_refs: [],
      state: "no_dominant_shock",
      summary: "当前没有单一主导冲击，跨资产信号仍然分散。",
      trend: "stable",
    },
  };
}

export function macroOverviewInsufficientFixture(): MacroOverviewData {
  const fixture = macroOverviewFixture();
  return {
    ...fixture,
    core_invalidation: null,
    risk_lanes: fixture.risk_lanes.map((lane, index) =>
      index < 3
        ? lane
        : {
            ...lane,
            confidence: "insufficient_evidence",
            degradation_reason: "missing_at_cutoff",
            direction: "insufficient_evidence",
            drivers: [],
            invalidation: null,
            summary: `${lane.lane_id}：关键证据不足，暂不判断。`,
            trend: "insufficient_evidence",
          },
    ),
    shock_summary: {
      candidate: null,
      confidence: "insufficient_evidence",
      confirmations: [],
      contradictions: [],
      drivers: [],
      evidence_refs: [],
      state: "insufficient_evidence",
      summary: "关键证据不足，暂时无法判断主导冲击。",
      trend: "insufficient_evidence",
    },
  };
}

export function macroOverviewLocalDegradationFixture(): MacroOverviewData {
  const fixture = macroOverviewFixture();
  return {
    ...fixture,
    risk_lanes: fixture.risk_lanes.map((lane) =>
      lane.lane_id === "oil"
        ? {
            ...lane,
            confidence: "insufficient_evidence",
            degradation_reason: "comparison_insufficient_20_session_history",
            direction: "insufficient_evidence",
            drivers: [],
            invalidation: null,
            summary: "原油：关键证据不足，暂不判断。",
            trend: "insufficient_evidence",
          }
        : lane,
    ),
  };
}

export function macroCrossAssetFixture(): MacroCrossAssetData {
  const spy = evidence("asset:spy", 624.1, {
    change: -2.4,
    change_window: "20_sessions",
    claim_effect: "risk_asset_direction",
    criticality: "critical",
    role: "primary",
    unit: "price",
  });
  const btc = evidence("crypto:btc", 112_000, {
    change: -7.2,
    change_window: "20_sessions",
    claim_effect: "crypto_beta_direction",
    role: "confirmation",
    source_name: "Yahoo Finance",
    unit: "price",
  });
  const vix = evidence("vol:vix", 21.2, {
    change: 4.1,
    claim_effect: "equity_volatility_direction",
    role: "confirmation",
    unit: "index",
  });
  const items = [spy, btc, vix];
  const returnWindow = (value: number, window: "20_sessions" | "60_sessions") => ({
    derivation: {
      formula: "((last / first) - 1) * 100",
      inputs: [
        { observed_at: SAMPLE.start, value: 100 },
        { observed_at: SAMPLE.end, value: 100 + value },
      ],
      references: ["aligned_completed_sessions"],
    },
    reason: null,
    sample: { ...SAMPLE, count: window === "20_sessions" ? 21 : 60 },
    status: "available" as const,
    unit: "percent" as const,
    value,
    window,
  });
  return {
    ...common("risk_off_confirmation", items, {
      confirmationCode: "hyg_down",
      invalidationCode: "risk_asset_direction_reverses",
      ruleId: "spy_down",
      unavailableCapability: "etf_premium_discount",
      upgradeCode: "credit_and_volatility_confirm",
    }),
    asset_returns: [
      {
        concept_key: "asset:spy",
        evidence: spy,
        observed_at: "2026-07-22",
        reason: null,
        return_20: returnWindow(-2.4, "20_sessions"),
        return_60: returnWindow(4.8, "60_sessions"),
        series_key: "asset:spy",
        source_name: "Yahoo Finance",
        status: "available",
      },
      {
        concept_key: "crypto:btc",
        evidence: btc,
        observed_at: "2026-07-22",
        reason: null,
        return_20: returnWindow(-7.2, "20_sessions"),
        return_60: returnWindow(12.5, "60_sessions"),
        series_key: "crypto:btc",
        source_name: "Yahoo Finance",
        status: "available",
      },
    ],
    correlations_20: [
      {
        correlation: 0.61,
        left: "asset:spy",
        reason: null,
        right: "crypto:btc",
        sample: { count: 20, end: SAMPLE.end, start: "2026-06-24" },
        status: "available",
        window: "20_sessions",
      },
    ],
    correlations_60: [
      {
        correlation: 0.42,
        left: "asset:spy",
        reason: null,
        right: "crypto:btc",
        sample: { ...SAMPLE },
        status: "available",
        window: "60_sessions",
      },
    ],
    divergences: [
      {
        code: "equity_crypto_divergence",
        evidence_refs: ["asset:spy", "crypto:btc"],
      },
    ],
    page_id: "cross_asset",
    volatility: [vix],
  };
}

export function macroRatesInflationFixture(): MacroRatesInflationData {
  const dgs2 = evidence("rates:dgs2", 4.2, {
    change: 0.18,
    claim_effect: "curve_shape",
    criticality: "critical",
    role: "primary",
  });
  const dgs10 = evidence("rates:dgs10", 4.58, {
    change: 0.31,
    claim_effect: "long_rate_direction",
    criticality: "critical",
    role: "primary",
  });
  const slope = evidence("rates:10y2y", 0.38, {
    change: 0.13,
    claim_effect: "curve_shape",
    role: "confirmation",
    unit: "percentage_points",
  });
  const real = evidence("rates:real_10y", 2.1, {
    change: 0.34,
    claim_effect: "real_rate_direction",
    role: "confirmation",
  });
  const breakeven = evidence("inflation:10y_breakeven", 2.48, {
    change: -0.03,
    claim_effect: "inflation_compensation",
    role: "confirmation",
  });
  const sofr = evidence("liquidity:sofr", 4.37, {
    claim_effect: "funding_corridor",
    role: "context",
  });
  const iorb = evidence("fed:iorb", 4.4, {
    claim_effect: "policy_corridor",
    role: "context",
  });
  const spread = evidence("derived:sofr_minus_iorb_bps", -3, {
    change: 1,
    claim_effect: "funding_corridor",
    derivation: {
      formula: "(SOFR - IORB) * 100",
      inputs: [
        { concept_key: "liquidity:sofr", value: 4.37 },
        { concept_key: "fed:iorb", value: 4.4 },
      ],
      references: ["liquidity:sofr", "fed:iorb"],
    },
    freshness: { age_days: 0, stale_after_days: 3, status: "derived" },
    observed_at: "2026-07-22",
    source_name: "derived",
    unit: "basis_points",
  });
  const cpi = evidence("inflation:core_cpi", 3.1, {
    change: 0.2,
    change_window: "1_release",
    claim_effect: "consumer_inflation",
    frequency: "monthly",
    role: "confirmation",
  });
  const items = [dgs2, dgs10, slope, real, breakeven, sofr, iorb, spread, cpi];
  return {
    ...common("real_rate_tightening", items, {
      confirmationCode: "real_rate_up_20_sessions",
      invalidationCode: "rate_impulse_reverses",
      ruleId: "long_rate_up_20_sessions",
      unavailableCapability: "treasury_term_premium",
      upgradeCode: "real_and_nominal_rates_confirm",
    }),
    breakevens: [breakeven],
    curve_shape: {
      change_window: "20_sessions",
      evidence_refs: ["rates:dgs2", "rates:dgs10", "rates:10y2y"],
      level_classification: "upward_sloping",
      move_classification: "bear_steepener",
      rule_version: "macro_curve_shape_v1",
      status: "supported",
      ten_year_change: 0.31,
      two_year_change: 0.18,
    },
    curve_slopes: [slope],
    inflation_releases: [
      {
        evidence: cpi,
        release_change: metric("inflation:core_cpi", 0.2),
        year_over_year: metric("inflation:core_cpi", 3.1),
      },
    ],
    nominal_curve: [dgs2, dgs10],
    page_id: "rates_inflation",
    policy_funding_corridor: {
      evidence: [sofr, iorb],
      evidence_refs: ["liquidity:sofr", "fed:iorb", "derived:sofr_minus_iorb_bps"],
      spreads: [spread],
      state: "orderly",
      status: "supported",
    },
    real_yields: [real],
    term_premium: {
      capability: "treasury_term_premium",
      reason: "source_not_ingested",
      status: "not_assessed",
    },
  };
}

export function macroGrowthLaborFixture(): MacroGrowthLaborData {
  const claims = evidence("labor:initial_claims", 245_000, {
    change: 22_000,
    change_window: "4_releases",
    claim_effect: "labor_deterioration",
    criticality: "critical",
    frequency: "weekly",
    role: "primary",
    unit: "number",
  });
  const payrolls = evidence("labor:payrolls", 95_000, {
    change: -32_000,
    change_window: "1_release",
    claim_effect: "labor_growth",
    criticality: "critical",
    frequency: "monthly",
    role: "confirmation",
    unit: "thousands_persons",
  });
  const unemployment = evidence("labor:unemployment", 4.3, {
    change: 0.2,
    change_window: "1_release",
    claim_effect: "labor_slack",
    frequency: "monthly",
    role: "confirmation",
  });
  const gdp = evidence("economy:gdp_real", 0.8, {
    change: -1.1,
    change_window: "1_release",
    claim_effect: "real_growth",
    criticality: "critical",
    frequency: "quarterly",
    role: "confirmation",
    unit: "billions_chained_usd",
  });
  const items = [claims, payrolls, unemployment, gdp];
  return {
    ...common("growth_labor_cooling", items, {
      confirmationCode: "unemployment_rate_up",
      invalidationCode: "labor_growth_reaccelerates",
      ruleId: "claims_up_four_releases",
      unavailableCapability: "consensus_forecasts",
      upgradeCode: "leading_and_lagging_confirm",
    }),
    growth_lagging: [gdp],
    growth_leading: [claims],
    growth_metrics: [
      metric("labor:initial_claims", 22_000, "number"),
      metric("economy:gdp_real", 0.8, "percent_saar"),
    ],
    labor_lagging: [unemployment],
    labor_leading: [claims, payrolls],
    page_id: "growth_labor",
  };
}

export function macroLiquidityFundingFixture(): MacroLiquidityFundingData {
  const fedAssets = evidence("liquidity:fed_assets", 6_600_000, {
    change: -45_000,
    change_window: "4_releases",
    claim_effect: "central_bank_balance_sheet",
    criticality: "critical",
    frequency: "weekly",
    role: "primary",
    unit: "millions_usd",
  });
  const reserves = evidence("liquidity:reserve_balances", 3_200_000, {
    change: -30_000,
    change_window: "4_releases",
    claim_effect: "reserve_balance",
    frequency: "weekly",
    role: "confirmation",
    unit: "millions_usd",
  });
  const rrp = evidence("liquidity:on_rrp", 91_000, {
    change: -7_000,
    claim_effect: "reverse_repo_usage",
    role: "context",
    unit: "billions_usd",
  });
  const tga = evidence("liquidity:tga", 760_000, {
    change: 38_000,
    claim_effect: "treasury_cash",
    role: "context",
    unit: "millions_usd",
  });
  const net = evidence("derived:net_liquidity_accounting_proxy", 5_749_000, {
    change: -76_000,
    claim_effect: "accounting_proxy_context_only",
    derivation: {
      formula:
        "accounting proxy only: Fed assets - TGA - (RRP * 1000); no causal risk-asset inference",
      inputs: [
        {
          concept_key: "liquidity:fed_assets",
          source_unit: "millions_usd",
          value_millions_usd: 6_600_000,
        },
        {
          concept_key: "liquidity:on_rrp",
          source_unit: "billions_usd",
          value_millions_usd: 91_000_000,
        },
        {
          concept_key: "liquidity:tga",
          source_unit: "millions_usd",
          value_millions_usd: 760_000,
        },
      ],
      references: ["liquidity:fed_assets", "liquidity:on_rrp", "liquidity:tga"],
    },
    freshness: { age_days: 0, stale_after_days: 8, status: "derived" },
    observed_at: "2026-07-22",
    role: "context",
    source_name: "derived_accounting_proxy",
    unit: "millions_usd",
  });
  const sofr = evidence("liquidity:sofr", 4.53, {
    claim_effect: "funding_corridor",
    role: "primary",
  });
  const iorb = evidence("fed:iorb", 4.4, {
    claim_effect: "policy_corridor",
    role: "confirmation",
  });
  const sofrSpread = evidence("derived:sofr_minus_iorb_bps", 13, {
    claim_effect: "secured_funding",
    role: "confirmation",
    unit: "basis_points",
  });
  const effr = evidence("fed:effr", 4.33, {
    claim_effect: "policy_corridor",
    role: "context",
  });
  const items = [fedAssets, reserves, rrp, tga, net, sofr, iorb, sofrSpread, effr];
  return {
    ...common("secured_funding_pressure", items, {
      confirmationCode: "fed_assets_declining",
      invalidationCode: "funding_spreads_normalize",
      ruleId: "sofr_iorb_at_least_10bps",
      unavailableCapability: "dealer_inventory",
      upgradeCode: "secured_and_unsecured_confirm",
    }),
    central_bank_balance_sheet: [fedAssets],
    net_liquidity: net,
    page_id: "liquidity_funding",
    reserves: [reserves],
    reverse_repo: [rrp],
    secured_funding: {
      evidence: [sofr, iorb],
      spreads: [sofrSpread],
    },
    treasury_cash: [tga],
    unsecured_funding: {
      evidence: [effr],
      spreads: [],
    },
  };
}

export function macroCreditFixture(): MacroCreditData {
  const ig = evidence("credit:ig_oas", 78, {
    change: 1,
    claim_effect: "aggregate_credit_spread",
    criticality: "critical",
    role: "primary",
    unit: "basis_points",
  });
  const hy = evidence("credit:hy_oas", 269, {
    change: 3,
    claim_effect: "aggregate_credit_spread",
    criticality: "critical",
    role: "primary",
    unit: "basis_points",
  });
  const bb = evidence("credit:hy_bb_oas", 158, {
    change: 2,
    claim_effect: "high_yield_tail",
    role: "confirmation",
    unit: "basis_points",
  });
  const b = evidence("credit:hy_b_oas", 286, {
    change: 4,
    claim_effect: "high_yield_tail",
    role: "confirmation",
    unit: "basis_points",
  });
  const ccc = evidence("credit:hy_ccc_oas", 978, {
    change: 8,
    claim_effect: "high_yield_tail",
    criticality: "critical",
    role: "primary",
    unit: "basis_points",
  });
  const cccMinusBb = evidence("derived:credit_ccc_minus_bb_oas", 820, {
    change: 6,
    claim_effect: "rating_dispersion",
    derivation: {
      formula: "CCC OAS - BB OAS",
      inputs: [
        { concept_key: "credit:hy_ccc_oas", value: 978 },
        { concept_key: "credit:hy_bb_oas", value: 158 },
      ],
      references: ["credit:hy_ccc_oas", "credit:hy_bb_oas"],
    },
    freshness: { age_days: 0, stale_after_days: 3, status: "derived" },
    observed_at: "2026-07-22",
    role: "primary",
    source_name: "derived",
    unit: "basis_points",
  });
  const effectiveYield = evidence("credit:hy_yield", 7.02, {
    change: 0.05,
    claim_effect: "high_yield_cost",
    role: "context",
  });
  const sloos = evidence("credit:sloos_ci_large_tightening", 5.2, {
    change: -2,
    change_window: "1_release",
    claim_effect: "credit_supply",
    frequency: "quarterly",
    role: "context",
    unit: "percent",
  });
  const delinq = evidence("credit:business_delinquency", 1.6, {
    change: 0.1,
    change_window: "1_release",
    claim_effect: "realized_damage",
    frequency: "quarterly",
    role: "context",
  });
  const nfci = evidence("credit:nfci", -0.55, {
    change: -0.03,
    change_window: "4_releases",
    claim_effect: "financial_conditions",
    role: "confirmation",
    unit: "index",
  });
  const items = [ig, hy, bb, b, ccc, cccMinusBb, effectiveYield, sloos, delinq, nfci];
  return {
    ...common("tail_stress", items, {
      confirmationCode: "yields_up_spreads_wider",
      invalidationCode: "credit_spreads_reverse",
      ruleId: "credit_stage_tail_stress",
      unavailableCapability: "trace_transactions",
      upgradeCode: "aggregate_and_tail_confirm",
    }),
    aggregate_spreads: [ig, hy],
    credit_state: {
      direction: "stable",
      evidence_refs: ["credit:hy_oas", "credit:ig_oas", "credit:hy_ccc_oas", "credit:hy_bb_oas"],
      rule_version: "macro_credit_state_v1",
      stage: "tail_stress",
      status: "supported",
    },
    credit_supply: [sloos],
    effective_yields: [effectiveYield],
    financial_conditions_liquidity: [nfci],
    page_id: "credit",
    rating_tail: [bb, b, ccc, cccMinusBb],
    realized_damage: [delinq],
    treasury_spread_quadrant: {
      change_window: "20_sessions",
      evidence_refs: ["rates:dgs10", "credit:hy_oas"],
      quadrant: "yields_up_spreads_wider",
      rule_version: "macro_treasury_spread_quadrant_v1",
      spread_change: 3,
      status: "supported",
      yield_change: 0.31,
    },
  };
}

export function macroSeriesFixture(conceptKeys: string[]): MacroSeriesData {
  return {
    data_gaps: [],
    series: Object.fromEntries(
      conceptKeys.map((conceptKey) => [
        conceptKey,
        {
          concept_key: conceptKey,
          data_gaps: [],
          data_quality: "ok",
          latest_observed_at: "2026-07-22",
          points: [
            {
              data_quality: "ok",
              event_metadata: {},
              frequency: "daily",
              observed_at: "2026-07-22",
              series_key: conceptKey,
              source_name: "FRED",
              unit: "percent",
              value: 1,
            },
          ],
          sources: ["FRED"],
          status: "ok",
          unit: "percent",
        },
      ]),
    ),
    window: "60d",
  };
}
