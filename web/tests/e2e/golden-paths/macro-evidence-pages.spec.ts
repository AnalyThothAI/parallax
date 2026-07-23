import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoNestedHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

const riskLanes = [
  "美国股票风险暴露",
  "长期美债风险暴露",
  "信用风险暴露",
  "美元风险暴露",
  "黄金风险暴露",
  "原油风险暴露",
  "加密资产风险暴露",
  "市场波动率风险暴露",
] as const;

const drilldowns = [
  ["/macro/cross-asset", "跨资产确认", "风险资产、久期、信用与美元"],
  ["/macro/rates-inflation", "利率与通胀", "名义利率、实际利率与通胀补偿"],
  ["/macro/growth-labor", "增长与就业", "领先与滞后增长信号"],
  ["/macro/liquidity-funding", "流动性与资金", "资产负债表、准备金与融资价格"],
  ["/macro/credit", "信用周期雷达", "总量利差、评级尾部与金融条件"],
] as const;

test("renders the fixed eight-lane decision map with evidence collapsed by default", async ({
  page,
}) => {
  await installMockApi(page);
  await page.goto("/macro");

  await expect(page.getByRole("heading", { level: 1, name: "跨资产风险地图" })).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "宏观分析维度" }).getByRole("link"),
  ).toHaveCount(6);
  await expect(page.getByRole("heading", { name: "每日 AI 宏观研判" })).toBeVisible();
  await expect(page.getByText("SPY 未来方向")).toBeVisible();
  await expect(page.getByText("已复核")).toBeVisible();
  await expect(page.locator(".macro-risk-lane")).toHaveCount(8);
  for (const lane of riskLanes) {
    await expect(page.getByRole("article", { name: lane })).toBeVisible();
  }
  await expect(page.getByText("当前主导冲击：实际利率收紧。", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "五个交易日内的关键变化" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "最近官方催化" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "核心失效条件" })).toBeVisible();

  const audit = page.locator(".macro-audit-drawer");
  await expect(audit).not.toHaveAttribute("open", "");
  await expect(page.getByRole("heading", { name: "完整证据与溯源" })).toBeHidden();
  await audit.locator("summary").click();
  await expect(audit).toHaveAttribute("open", "");
  await expect(page.getByText("macro_decision_v2")).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整证据与溯源" })).toBeVisible();

  await expect(page.locator("main")).not.toContainText(/买入|卖出|仓位|持仓|目标价/);
  await expectNoDocumentHorizontalOverflow(page);
  await expectNoNestedHorizontalOverflow(page, [
    ".macro-workbench",
    ".macro-daily-analysis",
    ".macro-risk-lanes",
    ".macro-overview-action-band",
    ".macro-audit-body",
  ]);
  await expectNoUnhandledApiRequests(page);
});

test("renders all five domain drilldowns with separate-unit charts and concise judgment bands", async ({
  page,
}) => {
  await installMockApi(page);

  for (const [path, title, seriesTitle] of drilldowns) {
    await page.goto(path);

    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "宏观分析维度" }).getByRole("link"),
    ).toHaveCount(6);
    for (const heading of ["主要驱动", "确认", "反证", "失效条件"]) {
      await expect(page.getByRole("heading", { exact: true, name: heading })).toBeVisible();
    }
    await expect(page.getByRole("heading", { exact: true, name: seriesTitle })).toBeVisible();
    await expect(page.getByRole("group", { name: "图表窗口" })).toBeVisible();
    await expect(page.locator(".macro-series-figure")).toHaveCount(4);
    await expect(page.locator(".macro-audit-drawer")).not.toHaveAttribute("open", "");

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoNestedHorizontalOverflow(page, [
      ".macro-workbench",
      ".macro-judgment-band",
      ".macro-series-grid",
      ".macro-decision-grid",
    ]);
  }

  await expectNoUnhandledApiRequests(page);
});

test("keeps rates curve labels and credit stage-direction evidence visible", async ({ page }) => {
  await installMockApi(page);

  await page.goto("/macro/rates-inflation");
  await expect(page.getByRole("heading", { name: "收益率曲线：水平与变化分开" })).toBeVisible();
  await expect(page.getByText("当前曲线水平")).toBeVisible();
  await expect(page.getByText("20 个交易日曲线变化")).toBeVisible();
  await expect(page.getByText("美国国债期限溢价").first()).toBeVisible();

  await page.goto("/macro/credit");
  await expect(page.getByRole("heading", { name: "信用状态：阶段与方向分开" })).toBeVisible();
  await expect(page.getByText("低评级尾部承压", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("稳定", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("CCC–BB 尾部信用利差").first()).toBeVisible();
  await expect(page.getByText("tail_stress", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("stable", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("derived:credit_ccc_minus_bb_oas").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "6. 金融条件与信用流动性" })).toBeVisible();

  await expectNoDocumentHorizontalOverflow(page);
  await expectNoUnhandledApiRequests(page);
});

test("does not route retired macro paths through a fallback", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/macro/overview");

  await expect(page.getByRole("alert")).toContainText("404 Not Found");
  await expect(page.getByRole("navigation", { name: "宏观分析维度" })).toHaveCount(0);
  await expectNoUnhandledApiRequests(page);
});
