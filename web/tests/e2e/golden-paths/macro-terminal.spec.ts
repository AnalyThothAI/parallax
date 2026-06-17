import { expect, test, type Page } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

const CORE_PAGE_CONTRACTS = [
  {
    route: "/macro",
    regions: ["宏观简报", "跨域市场板", "传导链", "数据诊断"],
    visibleText: "总览：风险偏好等待利率与流动性确认",
  },
  {
    route: "/macro/assets",
    regions: ["核心资产行情", "今日判断", "数据诊断", "60日相关性"],
    visibleText: "风险资产偏震荡",
  },
  {
    route: "/macro/rates/fed-funds",
    regions: ["利率简报", "关键事实", "利率主图", "决策支持", "利率明细", "数据诊断"],
    visibleText: "联邦基金走廊：隔夜利率保持在目标区间内",
  },
] as const;

const HARD_DELETED_MACRO_ROUTES = [
  "/macro/assets/crypto-derivatives",
  "/macro/rates/auctions",
  "/macro/rates/expectations",
  "/macro/fed/statements",
  "/macro/fed/speeches",
  "/macro/liquidity/global-dollar",
  "/macro/liquidity/reserves",
  "/macro/liquidity/subsurface",
  "/macro/liquidity/transmission-chain",
  "/macro/liquidity/operations",
  "/macro/economy/consumer",
  "/macro/volatility/dashboard",
  "/macro/credit/cds",
] as const;

test.describe("macro terminal navigation hardening", () => {
  test("macro core pages keep the workbench grammar across target viewports", async ({ page }) => {
    await installMockApi(page);

    for (const contract of CORE_PAGE_CONTRACTS) {
      await page.goto(contract.route);

      await expect(page.getByLabel("宏观工作台")).toBeVisible();
      await expect(page.getByText(contract.visibleText)).toBeVisible();
      await expectRegionsInOrder(page, [...contract.regions]);
      await expect(page.getByRole("navigation", { name: "宏观模块" })).toBeVisible();
      await expectNoDocumentHorizontalOverflow(page);
      await expectNoUnhandledApiRequests(page);
    }
  });

  test("desktop macro terminal renders equities with shell module navigation", async ({
    page,
  }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("desktop-"), "desktop-only macro terminal check");

    await installMockApi(page);
    await page.goto("/macro/assets/equities");

    const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primaryNavigation).toBeVisible();
    const moduleNavigation = page.getByRole("navigation", { name: "宏观模块" });
    await expect(moduleNavigation).toBeVisible();
    await expect(moduleNavigation.getByRole("link", { name: "大类资产" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(moduleNavigation.getByRole("link", { name: "利率" })).toBeVisible();

    await expect(primaryNavigation.getByRole("link", { name: "宏观" })).toBeVisible();
    await expect(primaryNavigation.getByRole("link", { name: "大类资产" })).toBeVisible();

    await expect(page.getByRole("region", { name: "主市场证据" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "美股风险" })).toBeVisible();
    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });

  test("mobile macro terminal drawer exposes nested asset links without legacy tabs", async ({
    page,
  }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("mobile-"), "mobile-only macro terminal drawer");

    await installMockApi(page);
    await page.goto("/macro/assets/equities");

    const sidebarTrigger = page.getByRole("button", { name: "Toggle Sidebar" });
    await expect(sidebarTrigger).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeHidden();

    await sidebarTrigger.click();
    const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primaryNavigation).toBeVisible();
    await expect(primaryNavigation.getByRole("link", { name: "宏观" })).toBeVisible();
    await expect(primaryNavigation.getByRole("link", { name: "大类资产" })).toBeVisible();
    await primaryNavigation.getByRole("button", { name: "展开大类资产" }).click();
    await expect(primaryNavigation.getByRole("link", { name: "美股" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(primaryNavigation).toBeHidden();
    await expect(page.getByRole("navigation", { name: "宏观模块" })).toBeVisible();

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });

  test("macro terminal asset parent opens the asset landing module", async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("desktop-"), "desktop asset landing contract");

    await installMockApi(page);
    await page.goto("/macro/assets");

    await expect(page).toHaveURL(/\/macro\/assets$/);
    await expect(page.getByRole("heading", { name: "大类资产" })).toBeVisible();
    await expect(page.getByRole("region", { name: "今日判断" })).toBeVisible();
    await expect(page.getByRole("region", { name: "核心资产行情" })).toBeVisible();

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });

  test("macro terminal hard-deleted routes go to the route error surface", async ({
    page,
  }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("desktop-"), "desktop deleted-route contract");

    await installMockApi(page);

    for (const route of ["/macro/not-real", ...HARD_DELETED_MACRO_ROUTES]) {
      await page.goto(route);

      await expect(page.getByRole("alert")).toContainText("404 Not Found");
      await expect(page.getByRole("status", { name: "不支持的宏观页面" })).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "总览" })).toHaveCount(0);
      await expect(page.getByRole("navigation", { name: "宏观模块" })).toHaveCount(0);

      await expectNoDocumentHorizontalOverflow(page);
      await expectNoUnhandledApiRequests(page);
    }
  });
});

async function expectRegionsInOrder(page: Page, regionNames: string[]) {
  const indexes = await page.evaluate((labels) => {
    const regions = Array.from(document.querySelectorAll<HTMLElement>("[aria-label]"));
    return labels.map((label) =>
      regions.findIndex((element) => element.getAttribute("aria-label") === label),
    );
  }, regionNames);

  expect(indexes, regionNames.join(" -> ")).not.toContain(-1);
  expect(indexes, regionNames.join(" -> ")).toEqual(
    [...indexes].sort((left, right) => left - right),
  );
}
