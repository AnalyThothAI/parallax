import { expect, test } from "@playwright/test";
import { installMockApi } from "@tests/e2e/support/mockApi";

test("topbar gives status chips priority over search width", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 720 });
  await installMockApi(page);
  await page.goto("/");

  await expect(page.locator(".top-stats")).toBeVisible();
  await expect(page.locator(".searchbar")).toBeVisible();

  const layout = await page.evaluate(() => {
    const box = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing ${selector}`);
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        centerY: rect.top + rect.height / 2,
        width: rect.width,
      };
    };

    const chips = Array.from(document.querySelectorAll<HTMLElement>(".top-stats span")).map(
      (chip) => ({
        text: chip.textContent?.trim() ?? "",
        width: chip.getBoundingClientRect().width,
        scrollWidth: chip.scrollWidth,
      }),
    );

    return {
      topbar: box(".topbar"),
      search: box(".searchbar"),
      stats: box(".top-stats"),
      chips,
    };
  });

  expect(layout.search.width).toBeLessThanOrEqual(250);
  expect(layout.stats.width).toBeGreaterThan(layout.search.width * 2);
  expect(layout.stats.right).toBeLessThanOrEqual(layout.search.left);
  expect(Math.abs(layout.stats.centerY - layout.search.centerY)).toBeLessThanOrEqual(1);
  expect(layout.stats.bottom).toBeLessThanOrEqual(layout.topbar.bottom);
  expect(layout.chips).toHaveLength(5);
  for (const chip of layout.chips) {
    expect(chip.width, chip.text).toBeGreaterThanOrEqual(chip.scrollWidth - 1);
  }
});
