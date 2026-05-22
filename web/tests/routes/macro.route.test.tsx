import { screen, waitFor, within } from "@testing-library/react";
import {
  legacyMacroFixture,
  macroCorrelationFixture,
  macroModuleFixture,
  macroSeriesFixture,
} from "@tests/fixtures/macroFixture";
import { ok } from "@tests/msw/fixtures";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

const chartMocks = vi.hoisted(() => {
  const lineSeries = { setData: vi.fn() };
  const chartApi = {
    addSeries: vi.fn(() => lineSeries),
    applyOptions: vi.fn(),
    remove: vi.fn(),
    resize: vi.fn(),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  };
  return {
    chartApi,
    createChart: vi.fn(() => chartApi),
    lineSeries,
  };
});

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  LineSeries: "LineSeries",
  createChart: chartMocks.createChart,
}));

describe("macro route", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mockLiveRadarRoute(mock);
      const baseGetApi = mock.getApiImpl;
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro") return ok(legacyMacroFixture());
        if (path === "/api/macro/modules/overview") {
          return ok(
            macroModuleFixture({
              snapshot: {
                ...macroModuleFixture().snapshot,
                module_id: "overview",
                route_path: "/macro",
                title: "Overview",
                section: "overview",
              },
            }),
          );
        }
        if (path === "/api/macro/modules/assets/equities") return ok(macroModuleFixture());
        if (path === "/api/macro/series") {
          const conceptKeys = String(options?.params?.concept_keys ?? "asset:spx").split(",");
          return ok(macroSeriesFixture(conceptKeys));
        }
        if (path === "/api/macro/assets/correlation") return ok(macroCorrelationFixture());
        return baseGetApi(path, options);
      };
    });
  });

  it(
    "renders macro inside the cockpit shell and marks the sidebar item active",
    async () => {
      renderAppRoute("/macro");

      expect(await screen.findByRole("heading", { name: "宏观" })).toBeInTheDocument();
      expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
      const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
      const macroLink = within(navigation).getByRole("link", { name: "宏观" });
      expect(macroLink).toHaveAttribute("data-active", "true");
      expect(macroLink).not.toHaveAttribute("aria-current");
      expect(within(navigation).getByRole("link", { name: "总览" })).toHaveAttribute(
        "aria-current",
        "page",
      );
      await waitFor(() =>
        expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/overview", {
          token: "secret",
        }),
      );
    },
    10_000,
  );

  it("opens a routed backend macro module", async () => {
    renderAppRoute("/macro/assets/equities");

    expect(await screen.findByRole("heading", { name: "宏观" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "美股" })).toBeInTheDocument();
    expect(screen.getByText("Backend says equity leadership is constructive.")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/assets/equities", {
        token: "secret",
      }),
    );
  });

  it("normalizes unknown module routes back to the macro overview", async () => {
    renderAppRoute("/macro/assets/unknown");

    expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/overview", {
        token: "secret",
      }),
    );
  });

  it("opens the macro asset correlation detail route", async () => {
    renderAppRoute("/macro/assets/correlation");

    expect(await screen.findByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
    expect(await screen.findByText("SPY / QQQ")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "secret",
      }),
    );
  });
});
