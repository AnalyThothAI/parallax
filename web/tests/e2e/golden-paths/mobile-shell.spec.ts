import { expect, test, type Page } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test.beforeEach(({}, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile-"), "mobile-only layout contract");
});

test("mobile shell exposes task nav without desktop rail or route reloads", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await expect(page.locator(".desktop-side-rail")).toBeHidden();

  const mobileTaskNav = page.locator(".mobile-task-nav");
  await expect(mobileTaskNav).toBeVisible();
  const radarButton = mobileTaskNav.getByRole("button", { name: "Radar" });
  const tapeButton = mobileTaskNav.getByRole("button", { name: "Tape" });
  const labButton = mobileTaskNav.getByRole("button", { name: "Lab" });
  await expect(radarButton).toBeVisible();
  await expect(tapeButton).toBeVisible();
  await expect(labButton).toBeVisible();

  await expectNoDocumentHorizontalOverflow(page);
  await expectActiveMobileTask(page, "radar");

  await page.evaluate(() => {
    window.__routeBackSentinel = "mobile-task-switch";
  });

  await tapeButton.click();
  await expect(tapeButton).toHaveAttribute("aria-current", "page");
  await expect(radarButton).not.toHaveAttribute("aria-current", "page");
  await expectActiveMobileTask(page, "tape");
  await expect(page).toHaveURL(/\/$/);
  expect(await page.evaluate(() => window.__routeBackSentinel)).toBe("mobile-task-switch");

  await labButton.click();
  await expect(labButton).toHaveAttribute("aria-current", "page");
  await expect(tapeButton).not.toHaveAttribute("aria-current", "page");
  await expectActiveMobileTask(page, "lab");
  await expect(page).toHaveURL(/\/$/);
  expect(await page.evaluate(() => window.__routeBackSentinel)).toBe("mobile-task-switch");

  await page.getByLabel("global search").fill("test-token");
  await page.getByRole("button", { name: "检索" }).click();
  await expect(page).toHaveURL(/\/search\?q=test-token/);
  await expectNoUnhandledApiRequests(page);
});

async function expectActiveMobileTask(page: Page, activePanel: string) {
  await expect(page.locator(`[data-mobile-task-panel="${activePanel}"]`)).toBeVisible();
  for (const inactivePanel of ["radar", "tape", "lab"].filter((panel) => panel !== activePanel)) {
    await expect(page.locator(`[data-mobile-task-panel="${inactivePanel}"]`)).toBeHidden();
  }
}

declare global {
  interface Window {
    __routeBackSentinel?: string;
  }
}
