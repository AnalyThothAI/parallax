import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test.describe("macro terminal navigation hardening", () => {
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

    await expect(page.getByRole("region", { name: "市场板" })).toBeVisible();
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
    await expect(primaryNavigation.getByRole("link", { name: "美股" })).toBeVisible();
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
    await expect(page.getByRole("region", { name: "市场仪表盘" })).toBeVisible();
    await expect(page.getByRole("region", { name: "今日判断" })).toBeVisible();

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });

  test("macro terminal unsupported routes show the unsupported state instead of overview", async ({
    page,
  }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("desktop-"), "desktop unsupported route contract");

    await installMockApi(page);
    await page.goto("/macro/not-real");

    await expect(page.getByRole("status", { name: "不支持的宏观页面" })).toBeVisible();
    await expect(page.getByText("/macro/not-real")).toBeVisible();
    await expect(page.getByRole("heading", { name: "总览" })).toHaveCount(0);

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });
});
