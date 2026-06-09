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
  "/macro/assets/crypto-derivatives",
  "/macro/assets/correlation",
  "/macro/rates/fed-funds",
  "/macro/rates/yield-curve",
  "/macro/rates/real-rates",
  "/macro/rates/expectations",
  "/macro/liquidity/transmission-chain",
  "/macro/liquidity/fed-balance-sheet",
  "/macro/liquidity/operations",
  "/macro/liquidity/rrp-tga",
  "/macro/liquidity/reserves",
  "/macro/liquidity/global-dollar",
  "/macro/liquidity/subsurface",
  "/macro/economy/gdp",
  "/macro/economy/employment",
  "/macro/economy/inflation",
  "/macro/economy/consumer",
  "/macro/volatility/vix",
  "/macro/credit/stress",
];

const PARENT_ALIAS_ROUTES = [
  { route: "/macro/rates", target: /\/macro\/rates\/fed-funds$/ },
  { route: "/macro/fed", target: /\/macro\/fed\/statements$/ },
  { route: "/macro/liquidity", target: /\/macro\/liquidity\/transmission-chain$/ },
  { route: "/macro/economy", target: /\/macro\/economy\/gdp$/ },
  { route: "/macro/volatility", target: /\/macro\/volatility\/dashboard$/ },
  { route: "/macro/credit", target: /\/macro\/credit\/cds$/ },
];

const HIDDEN_DIRECT_ROUTES = [
  "/macro/rates/auctions",
  "/macro/fed/statements",
  "/macro/fed/speeches",
  "/macro/volatility/dashboard",
  "/macro/credit/cds",
];

const RATES_PRIMARY_RAW_TEXT_PATTERN =
  /macro_module_view_v3|source_snapshot_id|\b(?:rates|fed|liquidity|inflation):[a-z0-9_:-]+\b|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*_missing\b|\{|\}/;

test.describe("macro responsive audit", () => {
  test("macro product and hidden-supported routes satisfy responsive layout contract", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop-1366",
      "runs its own viewport matrix inside one project",
    );
    test.slow();
    const consoleErrors: string[] = [];

    page.on("console", (message) => {
      const text = message.text();
      if (message.type() === "error" && !isMockWebSocketHandshakeError(text)) {
        consoleErrors.push(text);
      }
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await installMockApi(page);

    for (const viewport of MACRO_AUDIT_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      for (const route of [...PRODUCT_ROUTES, ...HIDDEN_DIRECT_ROUTES]) {
        await page.goto(route);
        await expect(page.getByLabel("宏观工作台")).toBeVisible();
        await expectRatesWorkbenchHierarchy(page);
        await expectNoMacroBodyOverflow(page);
        await expectNoMacroLabelFragmentation(page);
        await expectMacroTableFramesBounded(page);
        await expectHiddenMacroLabelsAbsent(page);
        await expectNoUnhandledApiRequests(page);
      }

      for (const { route, target } of PARENT_ALIAS_ROUTES) {
        await page.goto(route);
        await expect(page).toHaveURL(target);
        await expect(page.getByLabel("宏观工作台")).toBeVisible();
        await expectRatesWorkbenchHierarchy(page);
        await expectNoMacroBodyOverflow(page);
        await expectNoMacroLabelFragmentation(page);
        await expectMacroTableFramesBounded(page);
        await expectHiddenMacroLabelsAbsent(page);
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
