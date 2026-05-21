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
    const labels = within(controls)
      .getAllByRole("button")
      .map((button) => button.textContent);

    expect(labels.slice(0, 6)).toEqual(["All", "SOL", "ETH", "BASE", "BSC", "CEX"]);
    expect(labels.slice(6, 10)).toEqual(["5m", "1h", "4h", "24h"]);
  });

  it("shows counts for every view rail destination", async () => {
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

    const markets = await screen.findByRole("heading", { name: "markets" });
    const viewButtons = within(markets.closest("section") as HTMLElement).getAllByRole("button");

    await waitFor(() => {
      expect(viewButtons.map((button) => button.textContent)).toEqual([
        "1Radar0",
        "2Stocks2",
        "3News2+",
        "MMacro",
      ]);
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
