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
        return baseGetApi(path, options);
      };
    });
  });

  it("renders Macro inside the cockpit shell and marks the rail item active", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "Macro" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Macro/i })).toHaveClass("active");
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro", {
        token: "secret",
      }),
    );
  });
});

function macroFixture(): MacroData {
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
    },
    indicators: {},
    triggers: [],
    data_gaps: [],
    source_coverage: { observed_series_count: 10, required_series_count: 10, coverage_ratio: 1 },
  };
}
