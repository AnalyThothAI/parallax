import { cleanup, screen, within } from "@testing-library/react";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setupAppRouteTest } from "./routeTestSetup";

describe("live radar route", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    setupAppRouteTest();
  });

  it("renders Token Radar as the default route", async () => {
    renderAppRoute("/");

    await screen.findByLabelText("token radar scan controls");
    expect(await screen.findByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
  });

  it("keeps the chain selector to the left of the radar window controls", async () => {
    renderAppRoute("/");

    const controls = await screen.findByLabelText("token radar scan controls");
    const chainLabels = within(controls)
      .getAllByRole("button")
      .map((button) => button.textContent);
    const windowGroup = within(controls).getByLabelText("radar window");
    const windowLabels = within(windowGroup)
      .getAllByRole("radio")
      .map((radio) => radio.textContent);

    expect(chainLabels.slice(0, 6)).toEqual(["All", "SOL", "ETH", "BASE", "BSC", "CEX"]);
    expect(windowLabels).toEqual(["5m", "1h", "4h", "24h"]);
    expect(
      within(controls).getByRole("button", { name: "CEX" }).compareDocumentPosition(windowGroup) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps primary navigation free of server-backed badges", async () => {
    renderAppRoute("/");

    const navigation = await screen.findByRole("navigation", { name: "Primary navigation" });

    expect(within(navigation).getByRole("link", { name: /^Radar$/i })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: /Stocks/i })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: /News/i })).toBeInTheDocument();
    expect(within(navigation).queryByText("2")).not.toBeInTheDocument();
    expect(within(navigation).queryByText("2+")).not.toBeInTheDocument();
  });

  it("treats pending projection coverage as loading instead of empty data", async () => {
    setupAppRouteTest((apiMock) => {
      mockLiveRadarRoute(apiMock);
      const baseGetApi = apiMock.getApiImpl;
      apiMock.getApiImpl = async (path, options) => {
        if (path === "/api/token-radar") {
          return {
            ok: true,
            data: {
              window: "1h",
              scope: "all",
              venue: "all",
              targets: [],
              attention: [],
              projection: {
                status: "pending",
                version: "token-radar-route-fixture",
                source: "token_radar_current_rows",
                venue: "all",
                reason: "projection_window_running",
                latest_attempt_status: "running",
                row_count: 0,
                source_rows: 3,
                source_max_received_at_ms: 0,
                source_frontier_ms: null,
                computed_at_ms: null,
                error: null,
                anchor_coverage: { status: "pending", ready: 0, missing: 0, total: 0 },
                quality_status: "insufficient",
                degraded_reasons: ["projection_window_running"],
                unresolved: {
                  identity_missing_count: 0,
                  nil_count: 0,
                  ambiguous_count: 0,
                  sample_symbols: [],
                },
              },
            },
          };
        }
        return baseGetApi(path, options);
      };
    });
    renderAppRoute("/");

    await screen.findByLabelText("token radar scan controls");
    expect(await screen.findByLabelText("loading token radar")).toBeInTheDocument();
    expect(screen.queryByText("当前窗口暂无可交易 token 热度")).not.toBeInTheDocument();
  });
});
