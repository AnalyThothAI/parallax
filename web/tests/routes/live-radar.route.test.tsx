import { cleanup, screen } from "@testing-library/react";
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

    expect(await screen.findByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
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
              targets: [],
              attention: [],
              projection: {
                status: "pending",
                version: "token-radar-route-fixture",
                source: "route_test",
                reason: "projection_window_running",
                row_count: 0,
                source_rows: 3,
              },
            },
          };
        }
        return baseGetApi(path, options);
      };
    });
    renderAppRoute("/");

    expect(await screen.findByLabelText("loading token radar")).toBeInTheDocument();
    expect(screen.queryByText("当前窗口暂无可交易 token 热度")).not.toBeInTheDocument();
  });
});
