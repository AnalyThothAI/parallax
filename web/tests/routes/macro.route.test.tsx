import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import {
  dailyMacroJudgmentFixture,
  macroCreditFixture,
  macroCrossAssetFixture,
  macroGrowthLaborFixture,
  macroLiquidityFundingFixture,
  macroOverviewFixture,
  macroOverviewInsufficientFixture,
  macroOverviewLocalDegradationFixture,
  macroOverviewNoShockFixture,
  macroRatesInflationFixture,
  macroSeriesFixture,
} from "@tests/fixtures/macroFixture";
import { ok } from "@tests/msw/fixtures";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

const PAGES = [
  ["/macro", "/api/macro/overview", "跨资产风险地图"],
  ["/macro/cross-asset", "/api/macro/cross-asset", "跨资产确认"],
  ["/macro/rates-inflation", "/api/macro/rates-inflation", "利率与通胀"],
  ["/macro/growth-labor", "/api/macro/growth-labor", "增长与就业"],
  ["/macro/liquidity-funding", "/api/macro/liquidity-funding", "流动性与资金"],
  ["/macro/credit", "/api/macro/credit", "信用周期雷达"],
] as const;

describe("macro decision workbench routes", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    configureMacroApi(macroOverviewFixture());
  });

  it.each(PAGES)("renders %s from its strict page endpoint", async (route, endpoint, title) => {
    renderAppRoute(route);

    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "宏观分析维度" });
    expect(within(navigation).getAllByRole("link")).toHaveLength(6);
    expect(
      within(navigation)
        .getAllByRole("link")
        .some((link) => link.getAttribute("aria-current") === "page"),
    ).toBe(true);
    expect(screen.getByText("审计与证据")).toBeInTheDocument();
    if (route === "/macro") {
      expect(screen.getByRole("heading", { name: "八类风险暴露" })).toBeInTheDocument();
    } else {
      expect(screen.getByText("主要驱动")).toBeInTheDocument();
      expect(screen.getByText("失效条件")).toBeInTheDocument();
    }
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith(endpoint, { token: "secret" }),
    );
  });

  it("renders the fixed risk map and persisted daily AI judgment", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "每日 AI 宏观研判" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "八类风险暴露" })).toBeInTheDocument();
    for (const lane of [
      "美国股票",
      "长期美债",
      "信用",
      "美元",
      "黄金",
      "原油",
      "加密资产",
      "市场波动率",
    ]) {
      expect(screen.getByRole("article", { name: `${lane}风险暴露` })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "五个交易日内的关键变化" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "最近官方催化" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "核心失效条件" })).toBeInTheDocument();
    expect(
      apiMock.readApi.mock.calls.filter(([path]) => path === "/api/macro/overview"),
    ).toHaveLength(1);
    expect(
      apiMock.readApi.mock.calls.filter(([path]) => path === "/api/macro/daily-judgment"),
    ).toHaveLength(1);
    expect(
      apiMock.readApi.mock.calls.filter(
        ([path]) =>
          path.startsWith("/api/macro/") &&
          path !== "/api/macro/overview" &&
          path !== "/api/macro/daily-judgment",
      ),
    ).toHaveLength(0);
    expect(screen.getByText(/跨资产信号分化/)).toBeVisible();
    expect(screen.getAllByText("不判断")).toHaveLength(2);
    expect(screen.getByText("政策与实际利率")).toBeVisible();
    expect(screen.getByText("已复核")).toBeVisible();
    expect(document.body.textContent).not.toMatch(
      /买入|卖出|仓位|position size|allocation|target price/i,
    );
  });

  it.each([
    [macroOverviewNoShockFixture(), "无单一主导冲击"],
    [macroOverviewInsufficientFixture(), "证据不足"],
  ] as const)("keeps %s as a distinct shock state", async (fixture, label) => {
    configureMacroApi(fixture);
    renderAppRoute("/macro");

    expect(await screen.findByText(label, { selector: ".macro-shock-summary span" })).toBeVisible();
  });

  it("keeps a critical gap local to the affected lane", async () => {
    configureMacroApi(macroOverviewLocalDegradationFixture());
    renderAppRoute("/macro");

    const oil = await screen.findByRole("article", { name: "原油风险暴露" });
    expect(within(oil).getByText(/局部证据缺口/)).toBeVisible();
    expect(
      within(screen.getByRole("article", { name: "美国股票风险暴露" })).queryByText(/局部证据缺口/),
    ).toBeNull();
  });

  it("keeps an unpublished daily judgment explicit without hiding the risk map", async () => {
    const pending = dailyMacroJudgmentFixture();
    configureMacroApi(macroOverviewFixture(), {
      ...pending,
      publication: null,
      state: "pending",
      target_job: pending.target_job
        ? {
            ...pending.target_job,
            status: "pending",
          }
        : null,
    });
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "每日 AI 宏观研判" })).toBeInTheDocument();
    expect(screen.getByText("今日研判等待生成")).toBeVisible();
    expect(screen.getByText(/页面不会临时调用模型/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "八类风险暴露" })).toBeVisible();
  });

  it("keeps audit metadata collapsed until explicitly opened", async () => {
    renderAppRoute("/macro");

    await screen.findByRole("heading", { name: "八类风险暴露" });
    const details = document.querySelector("details.macro-audit-drawer");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("审计与证据"));
    expect(details).toHaveAttribute("open");
    expect(screen.getByText("macro_decision_v2")).toBeVisible();
    expect(screen.getByRole("heading", { name: "完整证据与溯源" })).toBeVisible();
  });

  it("renders the nearest catalyst in local and official time", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "最近官方催化" })).toBeInTheDocument();
    expect(screen.getByText(/官方时间 2026-07-23 08:30/)).toBeVisible();
    expect(screen.getByRole("link", { name: "U.S. Department of Labor" })).toHaveAttribute(
      "href",
      "https://www.dol.gov/ui/data.pdf",
    );
  });

  it("separates curve level from curve move and exposes the policy corridor", async () => {
    renderAppRoute("/macro/rates-inflation");

    expect(
      await screen.findByRole("heading", { name: "收益率曲线：水平与变化分开" }),
    ).toBeInTheDocument();
    expect(screen.getByText("当前曲线水平")).toBeInTheDocument();
    expect(screen.getByText("20 个交易日曲线变化")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "政策与资金走廊" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "名义利率、实际利率与通胀补偿" }),
    ).toBeInTheDocument();
  });

  it("shows all six credit layers and keeps stage separate from direction", async () => {
    renderAppRoute("/macro/credit");

    expect(
      await screen.findByRole("heading", { name: "信用状态：阶段与方向分开" }),
    ).toBeInTheDocument();
    expect(screen.getByText("阶段")).toBeInTheDocument();
    expect(screen.getByText("方向")).toBeInTheDocument();
    for (const layer of [
      "1. 总量信用利差",
      "2. 评级尾部",
      "3. 企业有效融资成本",
      "4. 信贷供给",
      "5. 已实现贷款损伤",
      "6. 金融条件与信用流动性",
    ]) {
      expect(screen.getByRole("heading", { name: layer })).toBeInTheDocument();
    }
  });

  it.each([
    "/macro/overview",
    "/macro/not-real",
    "/macro/assets",
    "/macro/assets/correlation",
    "/macro/rates",
    "/macro/rates/fed-funds",
    "/macro/liquidity",
    "/macro/economy",
    "/macro/volatility",
  ])("returns an ordinary not-found surface for retired route %s", async (route) => {
    renderAppRoute(route);

    expect(await screen.findByRole("alert")).toHaveTextContent("404 Not Found");
    expect(screen.queryByRole("navigation", { name: "宏观分析维度" })).not.toBeInTheDocument();
    expect(apiMock.readApi.mock.calls.some(([path]) => path.startsWith("/api/macro"))).toBe(false);
  });
});

function configureMacroApi(
  overview: ReturnType<typeof macroOverviewFixture>,
  dailyJudgment = dailyMacroJudgmentFixture(),
) {
  setupAppRouteTest((mock) => {
    mockLiveRadarRoute(mock);
    const baseGetApi = mock.getApiImpl;
    mock.getApiImpl = async (path, options) => {
      if (path === "/api/macro/overview") return ok(overview);
      if (path === "/api/macro/daily-judgment") return ok(dailyJudgment);
      if (path === "/api/macro/cross-asset") return ok(macroCrossAssetFixture());
      if (path === "/api/macro/rates-inflation") return ok(macroRatesInflationFixture());
      if (path === "/api/macro/growth-labor") return ok(macroGrowthLaborFixture());
      if (path === "/api/macro/liquidity-funding") return ok(macroLiquidityFundingFixture());
      if (path === "/api/macro/credit") return ok(macroCreditFixture());
      if (path === "/api/macro/series") {
        const conceptKeys = String(options?.params?.concept_keys ?? "rates:dgs10").split(",");
        return ok(macroSeriesFixture(conceptKeys));
      }
      return baseGetApi(path, options);
    };
  });
}
