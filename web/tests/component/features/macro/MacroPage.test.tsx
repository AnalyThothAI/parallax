import { MacroPage } from "@features/macro";
import type { MacroData } from "@lib/types";
import { screen, waitFor } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { apiMock, setupAppRouteTest } from "@tests/routes/routeTestSetup";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let macroData: MacroData;

describe("MacroPage", () => {
  beforeEach(() => {
    macroData = populatedMacro();
    setupAppRouteTest((mock) => {
      mock.getApiImpl = async (path) => {
        if (path === "/api/macro") return ok(macroData);
        throw new Error(`unexpected path ${path}`);
      };
    });
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders the persisted macro regime snapshot from the API", async () => {
    renderWithProviders(<MacroPage token="test-token" />);

    expect(await screen.findByRole("heading", { name: "Macro" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Market Read" })).toBeInTheDocument();
    expect(await screen.findByText("funding_stress · 72% confidence · 1w")).toBeInTheDocument();
    expect(await screen.findByText("10/70 observed")).toBeInTheDocument();
    expect((await screen.findAllByText("funding_stress")).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "宏观传导链" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "情景与交易地图" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "验证矩阵" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "数据覆盖" })).toBeInTheDocument();
    expect(screen.getAllByText("Onshore Funding").length).toBeGreaterThan(0);
    expect(screen.getByText("Fed Corridor")).toBeInTheDocument();
    expect(screen.getByText("repo_pressure_persists_3d")).toBeInTheDocument();
    expect(screen.getByText("volatility_carry")).toBeInTheDocument();
    expect(screen.getByText("risk_down_credit_sensitive")).toBeInTheDocument();
    expect(screen.getByText("SOFR minus IORB")).toBeInTheDocument();
    expect(screen.getAllByText("sofr_above_iorb").length).toBeGreaterThan(0);
    expect(screen.getByText("missing:asset:spx")).toBeInTheDocument();
    expect(screen.getAllByText("10Y Treasury").length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro", { token: "test-token" }),
    );
  });

  it("renders an explicit data gap when no worker snapshot exists", async () => {
    macroData = {
      snapshot: null,
      panels: {},
      indicators: {},
      triggers: [],
      data_gaps: ["macro_view_snapshot_missing"],
      source_coverage: { observed_concept_count: 0 },
      features: {},
      chain: {},
      scenario: {},
      scorecard: {},
    };

    renderWithProviders(<MacroPage token="test-token" />);

    expect(await screen.findByText("Macro pending")).toBeInTheDocument();
    expect(screen.getByText("macro_view_snapshot_missing")).toBeInTheDocument();
  });
});

function populatedMacro(): MacroData {
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
    panels: {
      liquidity: {
        score: 9,
        regime: "funding_stress",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
      rates: {
        score: 7,
        regime: "term_premium_pressure",
        evidence: ["10y=4.70"],
        data_gaps: [],
      },
    },
    indicators: {
      sofr_iorb_spread_bps: {
        label: "SOFR minus IORB",
        value: 15,
        unit: "bps",
        observed_at: "2026-05-20",
        sources: ["nyfed", "fred"],
        concept_keys: ["liquidity:sofr", "fed:iorb"],
      },
    },
    triggers: [{ code: "sofr_above_iorb", description: "SOFR is above IORB", value: 15 }],
    data_gaps: ["missing:asset:spx"],
    source_coverage: {
      observed_concept_count: 10,
      required_concept_count: 10,
      coverage_ratio: 1,
      latest_observed_at: "2026-05-20",
    },
    features: {
      "rates:dgs10": {
        latest: { value: 4.7, observed_at: "2026-05-20", unit: "percent" },
        freshness_days: 1,
        delta: { "5d": 0.1, "20d": 0.35, "60d": null },
        zscore: { lookback: 252, value: 1.4 },
        percentile: { lookback: 252, value: 0.82 },
        data_gaps: [],
      },
    },
    chain: {
      liquidity: {
        score: 8,
        regime: "funding_stress",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
      fed_corridor: {
        score: 7,
        regime: "corridor_pressure",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
      volatility: {
        score: 3,
        regime: "carry",
        evidence: ["vix=16.0"],
        data_gaps: [],
      },
    },
    scenario: {
      current_regime: "funding_stress",
      confidence: 0.72,
      time_window: "1w",
      confirmations: [
        {
          code: "sofr_above_iorb",
          description: "SOFR is above IORB",
          indicator_keys: ["sofr_iorb_spread_bps"],
          value: 15,
        },
      ],
      contradictions: [{ code: "volatility_carry", node: "volatility" }],
      watch_triggers: [
        {
          code: "repo_pressure_persists_3d",
          description: "SOFR remains above IORB across multiple observations.",
        },
      ],
      invalidations: [
        {
          code: "sofr_iorb_normalizes",
          description: "SOFR trades back below or in line with IORB.",
        },
      ],
      trade_map: [
        {
          expression: "risk_down_credit_sensitive",
          time_window: "1w",
          confirms_on: ["sofr_above_iorb", "hy_oas_widening_5d", "vix_breaks_30"],
          invalidates_on: ["sofr_iorb_normalizes", "hy_oas_tightens", "vix_returns_to_carry"],
        },
      ],
    },
    scorecard: {
      projection_version: "macro_regime_v3",
      overall_score: 7.25,
      chain_average: 6,
      observed_concept_count: 10,
      required_concept_count: 70,
      coverage_ratio: 0.14,
      data_gap_count: 1,
      chain_regimes: {
        liquidity: "funding_stress",
        fed_corridor: "corridor_pressure",
        volatility: "carry",
      },
    },
  };
}
