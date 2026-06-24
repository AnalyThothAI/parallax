import { screen, waitFor, within } from "@testing-library/react";
import {
  macroAssetsModuleFixture,
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
        if (path === "/api/macro/modules/assets") {
          return ok(macroAssetsModuleFixture());
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
    expect(screen.getByRole("region", { name: "美股风险模块页面" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块简报" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "主市场证据" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "驱动与反证" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "市场板" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "模块证据" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "数据来源" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "模块数据健康" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/assets/equities", {
        token: "secret",
      }),
    );
  });

  it("surfaces missing module titles instead of falling back to route labels", async () => {
    const baseGetApi = apiMock.getApiImpl;
    apiMock.getApiImpl = async (path, options) => {
      if (path === "/api/macro/modules/assets/equities") {
        return ok(
          macroModuleFixture({
            snapshot: {
              ...macroModuleFixture().snapshot,
              title: "",
            },
          }),
        );
      }
      return baseGetApi(path, options);
    };

    renderAppRoute("/macro/assets/equities");

    expect(await screen.findByRole("alert")).toHaveTextContent("macro_module_title_missing");
    expect(screen.queryByRole("heading", { name: "美股" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "美股风险" })).not.toBeInTheDocument();
  });

  it("omits macro shell eyebrow copy when backend section metadata is absent", async () => {
    const baseGetApi = apiMock.getApiImpl;
    apiMock.getApiImpl = async (path, options) => {
      if (path === "/api/macro/modules/assets/equities") {
        return ok(
          macroModuleFixture({
            snapshot: {
              ...macroModuleFixture().snapshot,
              section: null,
            },
          }),
        );
      }
      return baseGetApi(path, options);
    };

    renderAppRoute("/macro/assets/equities");

    expect(await screen.findByRole("heading", { name: "美股风险" })).toBeInTheDocument();
    expect(screen.queryByText("宏观工作台")).not.toBeInTheDocument();
  });

  it("opens the asset landing module without redirecting to equities", async () => {
    renderAppRoute("/macro/assets");

    expect(await screen.findByRole("heading", { name: "大类资产" })).toBeInTheDocument();
    expect(screen.queryByText("Assets")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "核心资产行情" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "今日判断" })).toBeInTheDocument();
    expect(screen.getByText("风险资产偏震荡")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "相关性详情" })).not.toBeInTheDocument();
    expect(screen.getByText("矩阵").closest("details")).not.toHaveAttribute("open");
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/assets", {
        token: "secret",
      }),
    );
    expect(apiMock.readApi).not.toHaveBeenCalledWith("/api/macro/modules/assets/equities", {
      token: "secret",
    });
  });

  it("hard-deletes unknown macro routes into the route error surface", async () => {
    renderAppRoute("/macro/not-real");

    expect(await screen.findByRole("alert")).toHaveTextContent("404 Not Found");
    expect(screen.queryByRole("status", { name: "不支持的宏观页面" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "宏观模块" })).not.toBeInTheDocument();
    expect(apiMock.readApi).not.toHaveBeenCalledWith("/api/macro/modules/overview", {
      token: "secret",
    });
  });

  it.each([
    "/macro/rates",
    "/macro/liquidity",
    "/macro/economy",
    "/macro/volatility",
    "/macro/credit",
  ])("hard-deletes macro category alias route %s", async (route) => {
    renderAppRoute(route);

    expect(await screen.findByRole("alert")).toHaveTextContent("404 Not Found");
    expect(screen.queryByRole("navigation", { name: "宏观模块" })).not.toBeInTheDocument();
    expect(apiMock.readApi).not.toHaveBeenCalledWith("/api/macro/modules/overview", {
      token: "secret",
    });
  });

  it("hard-deletes the standalone asset correlation page into the route error surface", async () => {
    renderAppRoute("/macro/assets/correlation");

    expect(await screen.findByRole("alert")).toHaveTextContent("404 Not Found");
    expect(screen.queryByRole("heading", { name: "资产相关性" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("宏观工作台")).not.toBeInTheDocument();
    expect(apiMock.readApi).not.toHaveBeenCalledWith("/api/macro/assets/correlation", {
      params: { window: "60d" },
      token: "secret",
    });
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
    const moduleNavigation = screen.getByRole("navigation", { name: "宏观模块" });
    expect(within(moduleNavigation).getByRole("link", { name: "大类资产" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(moduleNavigation).getByRole("link", { name: "利率" })).toHaveAttribute(
      "href",
      "/macro/rates/fed-funds",
    );
    expect(screen.queryByRole("heading", { name: "宏观" })).not.toBeInTheDocument();
    expect(document.querySelector(".live-task-nav")).not.toBeInTheDocument();
  });
});

function setViewport(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
  window.dispatchEvent(new Event("resize"));
}
