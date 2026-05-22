import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test.describe("desktop sidebar navigation", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("desktop-"), "desktop-only sidebar contract");
  });

  test("shows dense primary navigation and a clickable rail toggle", async ({ page }) => {
    await installMockApi(page);
    await page.goto("/");

    const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primaryNavigation).toBeVisible();

    for (const routeName of [
      "Token Radar",
      "Stocks",
      "News",
      "宏观",
      "Watchlist",
      "Signal Lab",
      "Ops",
    ]) {
      await expect(primaryNavigation.getByRole("link", { name: routeName })).toBeVisible();
    }

    const sidebarRoot = page.locator('[data-slot="sidebar"]');
    const railToggle = page.locator('[data-sidebar="rail"]');
    await expect(railToggle).toBeVisible();
    await railToggle.click();
    await expect(sidebarRoot).toHaveAttribute("data-state", "collapsed");
    await expect(railToggle).toBeVisible();
    await railToggle.click();
    await expect(sidebarRoot).toHaveAttribute("data-state", "expanded");

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });
});

test.describe("mobile sidebar navigation", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("mobile-"), "mobile-only sidebar contract");
  });

  test("opens the route drawer and closes it after navigation", async ({ page }) => {
    await installMockApi(page);
    await page.goto("/");

    const sidebarTrigger = page.getByRole("button", { name: "Toggle Sidebar" });
    await expect(sidebarTrigger).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeHidden();

    await sidebarTrigger.click();
    const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primaryNavigation).toBeVisible();
    await expect(primaryNavigation.getByRole("link", { name: "Token Radar" })).toBeVisible();
    await expect(primaryNavigation.getByRole("link", { name: "News" })).toBeVisible();

    await primaryNavigation.getByRole("link", { name: "News" }).click();
    await expect(page).toHaveURL(/\/news(?:\?|$)/);
    await expect(primaryNavigation).toBeHidden();

    await expectNoDocumentHorizontalOverflow(page);
    await expectNoUnhandledApiRequests(page);
  });
});
