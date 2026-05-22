import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
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

  it("shows sidebar badges for primary market destinations", async () => {
    setupAppRouteTest((apiMock) => {
      mockLiveRadarRoute(apiMock);
      const baseGetApi = apiMock.getApiImpl;
      apiMock.getApiImpl = async (path, options) => {
        if (path === "/api/stocks-radar") {
          return ok({
            rows: [{ target: { symbol: "AAPL" } }, { target: { symbol: "RKLB" } }],
            health: { returned_count: 2, quote_ready_count: 1, quote_unavailable_count: 1 },
          });
        }
        if (path === "/api/news") {
          return ok({
            items: [
              {
                row_id: "news-1",
                news_item_id: "news-1",
                lifecycle_status: "processed",
                headline: "First item",
              },
              {
                row_id: "news-2",
                news_item_id: "news-2",
                lifecycle_status: "processed",
                headline: "Second item",
              },
            ],
            next_cursor: "next-page",
          });
        }
        return baseGetApi(path, options);
      };
    });
    renderAppRoute("/");

    const navigation = await screen.findByRole("navigation", { name: "Primary navigation" });

    await waitFor(() => {
      expect(within(navigation).getByRole("link", { name: /Token Radar/i })).toBeInTheDocument();
      expect(within(navigation).getByRole("link", { name: /Stocks/i })).toBeInTheDocument();
      expect(within(navigation).getByText("2")).toBeInTheDocument();
      expect(within(navigation).getByRole("link", { name: /News/i })).toBeInTheDocument();
      expect(within(navigation).getByText("2+")).toBeInTheDocument();
    });
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
