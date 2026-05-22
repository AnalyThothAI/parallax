import { expect, test, type Page } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoNestedHorizontalOverflow,
  expectNoUnhandledApiRequests,
  expectScrollableToLastMeaningfulElement,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test.beforeEach(({}, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile-"), "mobile-only layout contract");
});

test("mobile shell exposes sidebar route nav and task nav without route reloads", async ({
  page,
}) => {
  await installMockApi(page);
  await page.goto("/");

  const sidebarTrigger = page.getByRole("button", { name: "Toggle Sidebar" });
  await expect(sidebarTrigger).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeHidden();

  await sidebarTrigger.click();
  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
  await expect(primaryNavigation).toBeVisible();
  await expect(primaryNavigation.getByRole("link", { name: "Token Radar" })).toBeVisible();
  await expect(primaryNavigation.getByRole("link", { name: "Stocks" })).toBeVisible();
  await expect(primaryNavigation.getByRole("link", { name: "宏观" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(primaryNavigation).toBeHidden();

  const liveTaskNav = page.locator(".live-task-nav");
  await expect(liveTaskNav).toBeVisible();
  const radarButton = liveTaskNav.getByRole("button", { name: "Radar" });
  const tapeButton = liveTaskNav.getByRole("button", { name: "Tape" });
  const labButton = liveTaskNav.getByRole("button", { name: "Lab" });
  await expect(radarButton).toBeVisible();
  await expect(tapeButton).toBeVisible();
  await expect(labButton).toBeVisible();

  await expectNoDocumentHorizontalOverflow(page);
  await expectNoNestedHorizontalOverflow(page, [".topbar", ".live-task-nav"]);
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

test("mobile radar list remains reachable above the task nav without overlap", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/?window=24h&scope=matched");

  await expect(page.getByRole("button", { name: "Toggle Sidebar" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeHidden();
  await expect(page.locator(".live-task-nav")).toBeVisible();
  await expect(page.locator(".token-radar-row")).toHaveCount(8);

  const layout = await page.evaluate(() => {
    const center = document.querySelector<HTMLElement>(".center-column");
    const livePage = document.querySelector<HTMLElement>(".live-page");
    const radarPanel = document.querySelector<HTMLElement>(".radar-panel");
    const tokenTable = document.querySelector<HTMLElement>(".token-radar-table");
    const liveTaskNav = document.querySelector<HTMLElement>(".live-task-nav");
    const firstRow = document.querySelector<HTMLElement>(".token-radar-row");
    const navRect = liveTaskNav?.getBoundingClientRect();
    const firstRowRect = firstRow?.getBoundingClientRect();
    return {
      centerMaxScroll: center ? center.scrollHeight - center.clientHeight : null,
      livePageGridRows: livePage ? getComputedStyle(livePage).gridTemplateRows : null,
      liveTaskNavPosition: liveTaskNav ? getComputedStyle(liveTaskNav).position : null,
      tokenTableMaxScroll: tokenTable ? tokenTable.scrollHeight - tokenTable.clientHeight : null,
      radarPanelOverflowY: radarPanel ? getComputedStyle(radarPanel).overflowY : null,
      firstRowOverlapsTaskNav:
        firstRowRect && navRect ? firstRowRect.bottom > navRect.top + 1 : null,
    };
  });

  expect(layout.centerMaxScroll).toBe(0);
  expect(layout.tokenTableMaxScroll).toBeGreaterThan(0);
  expect(layout.livePageGridRows).not.toContain("405px");
  expect(layout.liveTaskNavPosition).toBe("static");
  expect(layout.radarPanelOverflowY).toBe("hidden");
  expect(layout.firstRowOverlapsTaskNav).toBe(false);

  await expectScrollableToLastMeaningfulElement(
    page,
    ".token-radar-table",
    ".token-radar-row:last-of-type",
  );
  await expectNoDocumentHorizontalOverflow(page);
  await expectNoNestedHorizontalOverflow(page, [".topbar", ".token-radar-row"]);
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
