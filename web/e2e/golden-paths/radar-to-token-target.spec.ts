import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

const targetId = "asset:dex:eth:0x6982508145454ce325ddbe47a25d4ec3d2311933";

test("token target route renders the radar target audit surface", async ({ page }) => {
  await installMockApi(page);
  await page.goto(`/token/Asset/${encodeURIComponent(targetId)}`);

  await expect(page.getByRole("heading", { name: "$UPEG" })).toBeVisible();
  await expect(page.getByText("score audit")).toBeVisible();
  await expect(
    page.getByRole("article").filter({ hasText: "$UPEG watched account evidence" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/token\/Asset\/asset%3Adex%3Aeth/);
});
