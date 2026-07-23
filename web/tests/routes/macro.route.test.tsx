import { screen, waitFor, within } from "@testing-library/react";
import {
  macroCreditFixture,
  macroCrossAssetFixture,
  macroGrowthLaborFixture,
  macroLiquidityFundingFixture,
  macroOverviewFixture,
  macroRatesInflationFixture,
  macroSeriesFixture,
} from "@tests/fixtures/macroFixture";
import { ok } from "@tests/msw/fixtures";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

const PAGES = [
  ["/macro", "/api/macro/overview", "宏观证据总览"],
  ["/macro/cross-asset", "/api/macro/cross-asset", "跨资产确认"],
  ["/macro/rates-inflation", "/api/macro/rates-inflation", "利率与通胀"],
  ["/macro/growth-labor", "/api/macro/growth-labor", "增长与就业"],
  ["/macro/liquidity-funding", "/api/macro/liquidity-funding", "流动性与资金"],
  ["/macro/credit", "/api/macro/credit", "信用周期雷达"],
] as const;

describe("macro evidence routes", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mockLiveRadarRoute(mock);
      const baseGetApi = mock.getApiImpl;
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro/overview") return ok(macroOverviewFixture());
        if (path === "/api/macro/cross-asset") return ok(macroCrossAssetFixture());
        if (path === "/api/macro/rates-inflation") return ok(macroRatesInflationFixture());
        if (path === "/api/macro/growth-labor") return ok(macroGrowthLaborFixture());
        if (path === "/api/macro/liquidity-funding") {
          return ok(macroLiquidityFundingFixture());
        }
        if (path === "/api/macro/credit") return ok(macroCreditFixture());
        if (path === "/api/macro/series") {
          const conceptKeys = String(options?.params?.concept_keys ?? "rates:dgs10").split(",");
          return ok(macroSeriesFixture(conceptKeys));
        }
        return baseGetApi(path, options);
      };
    });
  });

  it.each(PAGES)(
    "renders %s from its one strict endpoint",
    async (route, endpoint, title) => {
      renderAppRoute(route);

      expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
      const pageNavigation = screen.getByRole("navigation", { name: "宏观页面" });
      expect(within(pageNavigation).getAllByRole("link")).toHaveLength(6);
      const activeLink = within(pageNavigation)
        .getAllByRole("link")
        .find((link) => link.getAttribute("aria-current") === "page");
      expect(activeLink).toBeDefined();
      expect(screen.getByText("投影版本")).toBeInTheDocument();
      expect(screen.getAllByText("macro_evidence_v1").length).toBeGreaterThan(0);
      expect(screen.getByText("市场截止")).toBeInTheDocument();
      expect(screen.getAllByText("2026-07-22").length).toBeGreaterThan(0);
      expect(screen.getByRole("heading", { name: "驱动" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "确认" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "反证" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "升级 / 失效" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "实际规则命中" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "完整证据与溯源" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "未评估能力" })).toBeInTheDocument();
      expect(screen.getAllByText("未评估 · 不计分").length).toBeGreaterThan(0);
      expect(screen.queryByText("未命名规则或状态")).not.toBeInTheDocument();
      expect(screen.queryByText("未命名宏观证据")).not.toBeInTheDocument();
      await waitFor(() =>
        expect(apiMock.readApi).toHaveBeenCalledWith(endpoint, { token: "secret" }),
      );
    },
    15_000,
  );

  it("renders official seven-day catalysts with time, timezone, status and source", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { name: "官方催化日历" })).toBeInTheDocument();
    expect(screen.getByText("2026-07-23 · 08:30 · America/New_York")).toBeInTheDocument();
    expect(screen.getByText("2026-07-29 · 14:00 · America/New_York")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Federal Reserve" })).toHaveAttribute(
      "href",
      "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    );
    expect(screen.queryByText(/consensus|forecast|surprise/i)).not.toBeInTheDocument();
  });

  it("separates curve level from curve move and exposes the policy corridor", async () => {
    renderAppRoute("/macro/rates-inflation");

    expect(
      await screen.findByRole("heading", { name: "收益率曲线：水平与变化分开" }),
    ).toBeInTheDocument();
    expect(screen.getByText("当前曲线水平")).toBeInTheDocument();
    expect(screen.getByText("20 个交易日曲线变化")).toBeInTheDocument();
    expect(screen.getAllByText("upward_sloping").length).toBeGreaterThan(0);
    expect(screen.getAllByText("熊市趋陡").length).toBeGreaterThan(0);
    expect(screen.getAllByText("bear_steepener").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "政策与资金走廊" })).toBeInTheDocument();
    expect(screen.getAllByText("美国国债期限溢价").length).toBeGreaterThan(0);
    expect(screen.getAllByText("treasury_term_premium").length).toBeGreaterThan(0);
  });

  it("shows all six credit layers and keeps stage separate from direction", async () => {
    renderAppRoute("/macro/credit");

    expect(
      await screen.findByRole("heading", { name: "信用状态：阶段与方向分开" }),
    ).toBeInTheDocument();
    expect(screen.getByText("阶段")).toBeInTheDocument();
    expect(screen.getByText("方向")).toBeInTheDocument();
    expect(screen.getAllByText("低评级尾部承压").length).toBeGreaterThan(0);
    expect(screen.getAllByText("稳定").length).toBeGreaterThan(0);
    expect(screen.getAllByText("tail_stress").length).toBeGreaterThan(0);
    expect(screen.getAllByText("stable").length).toBeGreaterThan(0);
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
    expect(screen.getAllByText("投资级公司债 OAS").length).toBeGreaterThan(0);
    expect(screen.getAllByText("credit:ig_oas").length).toBeGreaterThan(0);
    expect(screen.getAllByText("derived:credit_ccc_minus_bb_oas").length).toBeGreaterThan(0);
    expect(screen.getAllByText("820").length).toBeGreaterThan(0);
    expect(screen.getAllByText("credit:nfci").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-0.55").length).toBeGreaterThan(0);
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
    expect(screen.queryByRole("navigation", { name: "宏观页面" })).not.toBeInTheDocument();
    expect(apiMock.readApi.mock.calls.some(([path]) => String(path).startsWith("/api/macro"))).toBe(
      false,
    );
  });
});
