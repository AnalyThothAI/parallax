import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test.beforeEach(({}, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("tablet-"), "tablet-only shell contract");
});

test("tablet shell keeps top-level route navigation in the sidebar drawer", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await expect(page.locator(".live-task-nav")).toBeHidden();

  const sidebarTrigger = page.getByRole("button", { name: "Toggle Sidebar" });
  await expect(sidebarTrigger).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeHidden();

  await sidebarTrigger.click();
  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
  await expect(primaryNavigation).toBeVisible();
  await expect(primaryNavigation.getByRole("link", { name: "Token Radar" })).toBeVisible();

  await primaryNavigation.getByRole("link", { name: "Stocks" }).click();
  await expect(page).toHaveURL(/\/stocks(?:\?|$)/);
  await expect(primaryNavigation).toBeHidden();
  await expect(page.getByRole("region", { name: "US stocks radar" })).toBeVisible();
  await expectNoDocumentHorizontalOverflow(page);
  await expectNoUnhandledApiRequests(page);
});
