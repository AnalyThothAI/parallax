// @responsive-spec
import { expect, test, type Page } from "@playwright/test";
import { expectNoUnhandledApiRequests } from "@tests/e2e/support/layoutAssertions";
import {
  expectHiddenMacroLabelsAbsent,
  expectMacroTableFramesBounded,
  expectNoMacroBodyOverflow,
  expectNoMacroLabelFragmentation,
  MACRO_AUDIT_VIEWPORTS,
} from "@tests/e2e/support/macroLayoutAudit";
import { installMockApi } from "@tests/e2e/support/mockApi";

const PRODUCT_ROUTES = [
  "/macro",
  "/macro/assets",
  "/macro/assets/equities",
  "/macro/assets/bonds",
  "/macro/assets/commodities",
  "/macro/assets/fx",
  "/macro/assets/crypto",
  "/macro/rates/fed-funds",
  "/macro/rates/yield-curve",
  "/macro/rates/real-rates",
  "/macro/liquidity/rrp-tga",
  "/macro/economy/gdp",
  "/macro/economy/employment",
  "/macro/economy/inflation",
  "/macro/volatility/vix",
  "/macro/credit/stress",
];

const HARD_DELETED_CATEGORY_ROUTES = [
  "/macro/assets/correlation",
  "/macro/rates",
  "/macro/liquidity",
  "/macro/economy",
  "/macro/volatility",
  "/macro/credit",
];

const RATES_PRIMARY_RAW_TEXT_PATTERN =
  /macro_module_view_v3|\b(?:rates|fed|liquidity|inflation):[a-z0-9_:-]+\b|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*_missing\b|\{|\}/;

test.describe("macro responsive audit", () => {
  test("macro product routes satisfy responsive layout contract", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-1366",
      "runs its own viewport matrix inside one project",
    );
    test.slow();
    const consoleErrors: string[] = [];

    page.on("console", (message) => {
      const text = message.text();
      if (
        message.type() === "error" &&
        !isMockWebSocketHandshakeError(text) &&
        !isExpectedMacroNotFoundDuringHardDeleteAudit(text, page.url())
      ) {
        consoleErrors.push(text);
      }
    });
    page.on("pageerror", (error) => {
      if (!isExpectedMacroNotFoundDuringHardDeleteAudit(error.message, page.url())) {
        consoleErrors.push(error.message);
      }
    });

    await installMockApi(page);

    for (const viewport of MACRO_AUDIT_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      for (const route of PRODUCT_ROUTES) {
        await page.goto(route);
        await expect(page.getByLabel("宏观工作台")).toBeVisible();
        await expectRatesWorkbenchHierarchy(page);
        await expectNoMacroBodyOverflow(page);
        await expectNoMacroLabelFragmentation(page);
        await expectMacroTableFramesBounded(page);
        await expectHiddenMacroLabelsAbsent(page);
        await expectNoUnhandledApiRequests(page);
      }

      for (const route of HARD_DELETED_CATEGORY_ROUTES) {
        await page.goto(route);
        await expect(page.getByRole("alert")).toContainText("404 Not Found");
        await expect(page.getByLabel("宏观工作台")).toHaveCount(0);
        await expectNoUnhandledApiRequests(page);
      }
    }

    expect(consoleErrors).toEqual([]);
  });
});

async function expectRatesWorkbenchHierarchy(page: Page) {
  const path = new URL(page.url()).pathname;
  if (!path.startsWith("/macro/rates/")) return;

  await expect(page.getByLabel("利率页导航")).toBeVisible();
  await expect(page.getByLabel("利率简报")).toBeVisible();
  await expect(page.getByLabel("利率主图")).toBeVisible();
  await expect(page.getByLabel("数据诊断")).toBeVisible();
  await expect(page.getByText("图表序列加载中")).toHaveCount(0);

  const order = await page.evaluate(() => {
    const labels = ["利率简报", "关键事实", "利率主图", "决策支持", "利率明细", "数据诊断"];
    const regions = Array.from(document.querySelectorAll<HTMLElement>("[aria-label]"));
    return labels.map((label) =>
      regions.findIndex((element) => element.getAttribute("aria-label") === label),
    );
  });

  expect(order).not.toContain(-1);
  expect(order).toEqual([...order].sort((left, right) => left - right));

  const primaryText = await page.evaluate(() => {
    const root = document.querySelector<HTMLElement>(".macro-page-scaffold");
    const diagnostics = root?.querySelector<HTMLElement>('[aria-label="数据诊断"]');
    if (!root || !diagnostics) return document.body.innerText;

    const parts: string[] = [];
    for (const child of Array.from(root.children)) {
      if (child.contains(diagnostics)) break;
      parts.push((child as HTMLElement).innerText ?? child.textContent ?? "");
    }
    return parts.join("\n");
  });

  expect(primaryText).not.toMatch(RATES_PRIMARY_RAW_TEXT_PATTERN);
}

function isMockWebSocketHandshakeError(text: string): boolean {
  return /WebSocket connection to 'ws:\/\/(?:127\.0\.0\.1|localhost):\d+\/ws' failed/.test(text);
}

function isExpectedMacroNotFoundDuringHardDeleteAudit(text: string, pageUrl: string): boolean {
  return (
    text.includes("404 Not Found") &&
    HARD_DELETED_CATEGORY_ROUTES.includes(new URL(pageUrl).pathname)
  );
}
