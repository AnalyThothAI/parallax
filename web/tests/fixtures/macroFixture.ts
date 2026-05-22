import type {
  MacroAssetCorrelationData,
  MacroData,
  MacroModuleView,
  MacroSeriesData,
} from "@lib/types";

export function macroModuleFixture(
  overrides: Partial<MacroModuleView> = {},
): MacroModuleView {
  return {
    snapshot: {
      module_id: "assets/equities",
      route_path: "/macro/assets/equities",
      title: "Equities",
      section: "assets",
      projection_version: "macro_module_view_v1",
      status: "partial",
      asof_date: "2026-05-20",
      source_snapshot_id: "macro-view:macro_regime_v3:1779000000000",
      source_projection_version: "macro_regime_v3",
      computed_at_ms: 1_779_000_000_000,
    },
    tiles: [
      {
        concept_key: "asset:spx",
        label: "asset:spx",
        latest: 5312.4,
        unit: "index",
        freshness_days: 1,
      },
    ],
    charts: [
      {
        chart_id: "equity_proxy_performance",
        status: "partial",
        missing_concept_keys: ["asset:iwm"],
        series: [{ concept_key: "asset:spx", latest: 5312.4, unit: "index" }],
      },
    ],
    tables: [
      {
        table_id: "equity_proxy_snapshot",
        status: "partial",
        missing_concept_keys: ["asset:iwm"],
        rows: [{ concept_key: "asset:spx", latest: 5312.4, unit: "index" }],
      },
    ],
    current_read: {
      regime: "risk_on",
      current_regime: "risk_on",
      summary: "Backend says equity leadership is constructive.",
      trade_map: { expression: "SPX leadership" },
    },
    signals: [
      {
        code: "watch_breadth",
        description: "Breadth confirmation is still missing.",
      },
    ],
    provenance: {
      latest_import_run: {
        status: "partial",
        reason_codes: ["equity_breadth_missing"],
      },
      source_coverage: {
        observed_concept_count: 7,
        required_concept_count: 8,
      },
      observation_sources: ["fred", "yahoo"],
      degradation: {
        status: "partial",
        reason_codes: ["equity_breadth_missing"],
      },
    },
    data_gaps: ["equity_breadth_missing"],
    related_routes: ["/macro/assets", "/macro/volatility"],
    ...overrides,
  };
}

export function legacyMacroFixture(): MacroData {
  return {
    snapshot: {
      snapshot_id: "macro-view:macro_regime_v3:1779000000000",
      projection_version: "macro_regime_v3",
      asof_date: "2026-05-20",
      status: "partial",
      regime: "funding_stress",
      overall_score: 7.25,
      computed_at_ms: 1_779_000_000_000,
    },
    panels: {},
    indicators: {},
    triggers: [],
    data_gaps: [],
    source_coverage: { observed_concept_count: 10, required_concept_count: 10, coverage_ratio: 1 },
    features: {},
    chain: {},
    scenario: {},
    scorecard: {},
  };
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
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "rates/yield-curve",
      route_path: "/macro/rates/yield-curve",
      section: "rates",
      title: "Yield Curve",
    },
    tiles: [
      { concept_key: "rates:dgs2", label: "2Y", latest: 3.8, unit: "percent" },
      { concept_key: "rates:dgs10", label: "10Y", latest: 4.2, unit: "percent" },
    ],
    charts: [
      {
        chart_id: "yield_curve",
        status: "ok",
        series: [
          { concept_key: "rates:dgs10", latest: 4.2, unit: "percent" },
          { concept_key: "rates:dgs2", latest: 3.8, unit: "percent" },
          { concept_key: "rates:dgs30", latest: 4.7, unit: "percent" },
          { concept_key: "rates:dgs5", latest: 4.0, unit: "percent" },
        ],
      },
    ],
    tables: [
      {
        table_id: "yield_curve_snapshot",
        status: "ok",
        rows: [
          { concept_key: "rates:dgs2", latest: 3.8, unit: "percent" },
          { concept_key: "rates:dgs10", latest: 4.2, unit: "percent" },
        ],
      },
    ],
    data_gaps: [],
  });
}

export function macroCryptoDerivativesModuleFixture(): MacroModuleView {
  return macroModuleFixture({
    snapshot: {
      ...macroModuleFixture().snapshot,
      module_id: "assets/crypto-derivatives",
      route_path: "/macro/assets/crypto-derivatives",
      section: "assets",
      title: "Crypto Derivatives",
    },
    tiles: [{ concept_key: "crypto:btc", label: "BTC", latest: 110_000, unit: "usd" }],
    charts: [
      {
        chart_id: "crypto_proxy_performance",
        status: "ok",
        series: [{ concept_key: "crypto:btc", latest: 110_000, unit: "usd" }],
      },
    ],
    tables: [
      {
        table_id: "cex_perp_board",
        status: "ok",
        source: {
          status: "degraded",
          coinglass_status: "partial",
          degraded_reasons: ["coinglass_partial"],
        },
        rows: [
          {
            symbol: "BTC",
            open_interest_usd: 12_500_000_000,
            funding_rate: "0.0001",
          },
          {
            symbol: "ETH",
            open_interest_usd: 8_300_000_000,
            funding_rate: "-0.0002",
          },
        ],
      },
    ],
    data_gaps: ["basis_missing", "crypto_options_missing", "etf_flows_missing"],
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
