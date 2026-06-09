import { expect, type Page } from "@playwright/test";

export const MACRO_AUDIT_VIEWPORTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "mobile-430", width: 430, height: 932 },
  { name: "tablet-834", width: 834, height: 1194 },
  { name: "compact-1096", width: 1096, height: 690 },
  { name: "desktop-1366", width: 1366, height: 720 },
  { name: "desktop-1920", width: 1920, height: 1080 },
] as const;

export async function expectNoMacroBodyOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }));

  expect(metrics.document, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.width + 1);
  expect(metrics.body, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.width + 1);
}

export async function expectNoMacroLabelFragmentation(page: Page) {
  const failures = await page.evaluate(() => {
    const watched = /^(SPX|VIX|CPI|SOFR|DXY|HY OAS|Payrolls|Claims)$/;

    return Array.from(
      document.querySelectorAll<HTMLElement>(
        ".macro-data-table th, .macro-assets-market-table th, .macro-workbench-brief-row dd",
      ),
    )
      .filter((element) => watched.test(element.textContent?.trim() ?? ""))
      .flatMap((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const fragmented =
          element.getClientRects().length > 1 ||
          style.overflowWrap === "anywhere" ||
          style.wordBreak === "break-all";

        return fragmented
          ? [
              {
                text: element.textContent?.trim(),
                height: rect.height,
                rects: element.getClientRects().length,
              },
            ]
          : [];
      });
  });

  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}

export async function expectHiddenMacroLabelsAbsent(page: Page) {
  const hidden = ["拍卖", "FOMC 声明", "美联储讲话", "Dashboard", "CDS 代理"];
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  const navIsVisible = await nav.isVisible().catch(() => false);

  if (!navIsVisible) {
    const sidebarTrigger = page.getByRole("button", { name: "Toggle Sidebar" });
    await expect(sidebarTrigger, "mobile/tablet macro nav drawer trigger").toBeVisible();
    await sidebarTrigger.click();
    await expect(nav).toBeVisible();
  }

  for (const label of hidden) {
    await expect(nav.getByRole("link", { name: label })).toHaveCount(0);
  }

  if (!navIsVisible) {
    await page.keyboard.press("Escape");
    await expect(nav).toBeHidden();
  }
}

export async function expectMacroTableFramesBounded(page: Page) {
  const failures = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>(".macro-table-frame-scroller")).flatMap(
      (frame, index) => {
        const rect = frame.getBoundingClientRect();
        const leaks = rect.width > window.innerWidth + 1;
        const labelled = Boolean(frame.getAttribute("aria-label"));

        return leaks || !labelled
          ? [{ index, width: rect.width, windowWidth: window.innerWidth, labelled }]
          : [];
      },
    ),
  );

  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}
