import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoNestedHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

const pages = [
  ["/macro", "宏观证据总览", "官方催化：下一次 BEA 国内生产总值发布"],
  ["/macro/cross-asset", "跨资产确认", "债券 ETF 折溢价"],
  ["/macro/rates-inflation", "利率与通胀", "美国国债期限溢价"],
  ["/macro/growth-labor", "增长与就业", "市场一致预期"],
  ["/macro/liquidity-funding", "流动性与资金", "交易商库存"],
  ["/macro/credit", "信用周期雷达", "TRACE 公司债逐笔成交与流动性"],
] as const;

test("renders all six evidence pages without document overflow", async ({ page }) => {
  await installMockApi(page);

  for (const [path, title, unavailableCapability] of pages) {
    await page.goto(path);

    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "宏观页面" }).getByRole("link")).toHaveCount(
      6,
    );
    await expect(page.getByRole("heading", { exact: true, name: "驱动" })).toBeVisible();
    await expect(page.getByRole("heading", { exact: true, name: "确认" })).toBeVisible();
    await expect(page.getByRole("heading", { exact: true, name: "反证" })).toBeVisible();
    await expect(page.getByRole("heading", { exact: true, name: "升级 / 失效" })).toBeVisible();
    await expect(page.getByRole("heading", { exact: true, name: "完整证据与溯源" })).toBeVisible();
    await expect(page.getByRole("heading", { exact: true, name: "未评估能力" })).toBeVisible();
    await expect(page.getByText("macro_evidence_v1")).toBeVisible();
    await expect(page.getByText(unavailableCapability).first()).toBeVisible();

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoNestedHorizontalOverflow(page, [
      ".macro-evidence-page",
      ".macro-evidence-header",
      ".macro-snapshot-meta",
      ".macro-decision-grid",
      ".macro-evidence-card",
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
  await expect(page.getByRole("navigation", { name: "宏观页面" })).toHaveCount(0);
  await expectNoUnhandledApiRequests(page);
});
