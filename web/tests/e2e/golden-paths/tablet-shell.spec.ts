import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test.beforeEach(({}, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("tablet-"), "tablet-only shell contract");
});

test("tablet shell keeps top-level route navigation when the desktop rail is hidden", async ({
  page,
}) => {
  await installMockApi(page);
  await page.goto("/");

  await expect(page.locator(".desktop-side-rail")).toBeHidden();
  await expect(page.locator(".live-task-nav")).toBeHidden();

  const routeNav = page.locator(".mobile-route-nav");
  await expect(routeNav).toBeVisible();
  await expect(routeNav.getByRole("link", { name: "Radar" })).toBeVisible();

  await routeNav.getByRole("link", { name: "Stocks" }).click();
  await expect(page).toHaveURL(/\/stocks(?:\?|$)/);
  await expect(page.getByRole("region", { name: "US stocks radar" })).toBeVisible();
  await expectNoDocumentHorizontalOverflow(page);
  await expectNoUnhandledApiRequests(page);
});
