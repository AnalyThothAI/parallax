import { screen, waitFor, within } from "@testing-library/react";
import {
  macroCorrelationFixture,
  macroModuleFixture,
  macroOverviewModuleFixture,
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
        if (path === "/api/macro/modules/overview") {
          return ok(
            macroOverviewModuleFixture({
              snapshot: {
                ...macroOverviewModuleFixture().snapshot,
                module_id: "overview",
                route_path: "/macro",
                title: "总览",
                section: "overview",
              },
            }),
          );
        }
        if (path === "/api/macro/modules/assets/equities") {
          return ok(macroModuleFixture());
        }
        if (path === "/api/macro/series") {
          const conceptKeys = String(options?.params?.concept_keys ?? "asset:spx").split(",");
          return ok(macroSeriesFixture(conceptKeys));
        }
        if (path === "/api/macro/assets/correlation") return ok(macroCorrelationFixture());
        return baseGetApi(path, options);
      };
    });
  });

  it("renders macro inside the cockpit shell and marks the sidebar item active", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "宏观" })).not.toBeInTheDocument();
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
  }, 10_000);

  it("keeps macro cold loads scoped to macro and lightweight shell data", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/overview", {
        token: "secret",
      }),
    );

    const requestedPaths = apiMock.readApi.mock.calls.map(([path]) => path);
    expect(requestedPaths).not.toContain("/api/recent");
    expect(requestedPaths).not.toContain("/api/token-radar");
    expect(requestedPaths).not.toContain("/api/stocks-radar");
    expect(requestedPaths).not.toContain("/api/news");
    expect(requestedPaths).not.toContain("/api/signal-lab/pulse");
    expect(requestedPaths).not.toContain("/api/notifications");
  });

  it("exposes the desktop brand once in the shell", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
    expect(screen.getAllByText("gmgn.intel")).toHaveLength(1);
  });

  it("opens a routed backend macro module", async () => {
    renderAppRoute("/macro/assets/equities");

    expect(await screen.findByRole("heading", { name: "美股风险" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "宏观" })).not.toBeInTheDocument();
    expect(screen.getByText("美股风险：等待小盘确认")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "美股模块页面" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "市场板" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "传导链" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块证据" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据来源" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块数据健康" })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/assets/equities", {
        token: "secret",
      }),
    );
  });

  it("renders an unsupported state for unknown macro routes", async () => {
    renderAppRoute("/macro/not-real");

    expect(await screen.findByRole("status", { name: "不支持的宏观页面" })).toHaveTextContent(
      "不支持的宏观页面",
    );
    expect(apiMock.readApi).not.toHaveBeenCalledWith("/api/macro/modules/overview", {
      token: "secret",
    });
  });

  it("opens the macro asset correlation detail route", async () => {
    renderAppRoute("/macro/assets/correlation");

    expect(await screen.findByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
    expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-page-kind", "matrix");
    expect(screen.getByRole("navigation", { name: "宏观面包屑" })).toHaveTextContent(
      "宏观/大类资产/相关性",
    );
    expect(await screen.findByRole("table", { name: "60d 资产相关性矩阵" })).toBeInTheDocument();
    expect(await screen.findByText("SPY / QQQ")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "secret",
      }),
    );
  });

  it.each([
    [390, 844],
    [834, 1194],
  ])("keeps the macro route shell readable at %ipx", async (width, height) => {
    setViewport(width, height);

    renderAppRoute("/macro/assets/equities");

    expect(await screen.findByRole("heading", { name: "美股风险" })).toBeInTheDocument();
    expect(screen.getByLabelText("宏观工作台")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "宏观主模块" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "宏观模块" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "宏观" })).not.toBeInTheDocument();
    expect(document.querySelector(".live-task-nav")).not.toBeInTheDocument();
  });
});

function setViewport(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
  window.dispatchEvent(new Event("resize"));
}
