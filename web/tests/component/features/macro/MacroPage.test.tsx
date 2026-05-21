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
    expect(await screen.findAllByText("funding_stress")).toHaveLength(2);
    expect(screen.getByText("Liquidity")).toBeInTheDocument();
    expect(screen.getByText("SOFR minus IORB")).toBeInTheDocument();
    expect(screen.getByText("sofr_above_iorb")).toBeInTheDocument();
    expect(screen.getByText("missing:fred:SP500")).toBeInTheDocument();
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
      source_coverage: { observed_series_count: 0 },
    };

    renderWithProviders(<MacroPage token="test-token" />);

    expect(await screen.findByText("Macro pending")).toBeInTheDocument();
    expect(screen.getByText("macro_view_snapshot_missing")).toBeInTheDocument();
  });
});

function populatedMacro(): MacroData {
  return {
    snapshot: {
      snapshot_id: "macro-view:macro_regime_v1:1779000000000",
      projection_version: "macro_regime_v1",
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
        series_keys: ["nyfed:SOFR", "fred:IORB"],
      },
    },
    triggers: [{ code: "sofr_above_iorb", description: "SOFR is above IORB", value: 15 }],
    data_gaps: ["missing:fred:SP500"],
    source_coverage: {
      observed_series_count: 10,
      required_series_count: 10,
      coverage_ratio: 1,
      latest_observed_at: "2026-05-20",
    },
  };
}
