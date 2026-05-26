import { expect, test } from "@playwright/test";
import { expectNoUnhandledApiRequests } from "@tests/e2e/support/layoutAssertions";
import {
  expectHiddenMacroLabelsAbsent,
  expectMacroTableFramesBounded,
  expectNoMacroBodyOverflow,
  expectNoMacroMetricFragmentation,
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
  "/macro/rates",
  "/macro/rates/fed-funds",
  "/macro/rates/yield-curve",
  "/macro/rates/real-rates",
  "/macro/rates/expectations",
  "/macro/fed",
  "/macro/liquidity",
  "/macro/liquidity/transmission-chain",
  "/macro/liquidity/fed-balance-sheet",
  "/macro/liquidity/operations",
  "/macro/liquidity/rrp-tga",
  "/macro/liquidity/reserves",
  "/macro/liquidity/global-dollar",
  "/macro/liquidity/subsurface",
  "/macro/economy",
  "/macro/economy/gdp",
  "/macro/economy/employment",
  "/macro/economy/inflation",
  "/macro/economy/consumer",
  "/macro/volatility",
  "/macro/volatility/vix",
  "/macro/credit",
  "/macro/credit/stress",
];

const HIDDEN_DIRECT_ROUTES = [
  "/macro/rates/auctions",
  "/macro/fed/statements",
  "/macro/fed/speeches",
  "/macro/volatility/dashboard",
  "/macro/credit/cds",
];

test.describe("macro responsive audit", () => {
  test("macro product and hidden-supported routes satisfy responsive layout contract", async ({
    page,
  }) => {
    test.slow();
    const consoleErrors: string[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await installMockApi(page);

    for (const viewport of MACRO_AUDIT_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      for (const route of [...PRODUCT_ROUTES, ...HIDDEN_DIRECT_ROUTES]) {
        await page.goto(route);
        await expect(page.getByLabel("宏观工作台")).toBeVisible();
        await expectNoMacroBodyOverflow(page);
        await expectNoMacroMetricFragmentation(page);
        await expectMacroTableFramesBounded(page);
        await expectHiddenMacroLabelsAbsent(page);
        await expectNoUnhandledApiRequests(page);
      }
    }

    expect(consoleErrors).toEqual([]);
  });
});
