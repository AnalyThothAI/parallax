import type { MacroData } from "@lib/types";
import { screen, waitFor } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("macro route", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mockLiveRadarRoute(mock);
      const baseGetApi = mock.getApiImpl;
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro") return ok(macroFixture());
        if (path === "/api/macro/assets/correlation") return ok(correlationFixture());
        return baseGetApi(path, options);
      };
    });
  });

  it("renders Macro inside the cockpit shell and marks the sidebar item active", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "Macro" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Macro/i })).toHaveAttribute("aria-current", "page");
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro", {
        token: "secret",
      }),
    );
  });

  it("opens a routed macro module and secondary page", async () => {
    renderAppRoute("/macro/assets/macro-beta");

    expect(await screen.findByRole("heading", { name: "Macro" })).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Inflation And Dollar Beta" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "商品/美元" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("opens the macro asset correlation detail route", async () => {
    renderAppRoute("/macro/assets/correlation");

    expect(await screen.findByRole("heading", { name: "Asset Correlation" })).toBeInTheDocument();
    expect(await screen.findByText("SPY / QQQ")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "secret",
      }),
    );
  });
});

function macroFixture(): MacroData {
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
    },
    indicators: {},
    triggers: [],
    data_gaps: [],
    source_coverage: { observed_concept_count: 10, required_concept_count: 10, coverage_ratio: 1 },
    features: {},
    chain: {
      liquidity: {
        score: 8,
        regime: "funding_stress",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
    },
    scenario: {
      current_regime: "funding_stress",
      confidence: 0.72,
      time_window: "1w",
      confirmations: [],
      contradictions: [],
      watch_triggers: [],
      invalidations: [],
      trade_map: [],
    },
    scorecard: {
      projection_version: "macro_regime_v3",
      observed_concept_count: 10,
      required_concept_count: 10,
      coverage_ratio: 1,
    },
  };
}

function correlationFixture() {
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
