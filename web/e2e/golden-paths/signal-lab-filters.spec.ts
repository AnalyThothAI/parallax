import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("cold Signal Lab load preserves filters and opens pulse detail", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/signal-lab?window=4h&scope=matched&q=BNB");

  await expect(
    page.getByText("Review Signal Pulse agent candidates by status, source, and query."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "open Signal Pulse BNB" })).toBeVisible();
  await expect(page).toHaveURL(/window=4h/);
  await expect(page).toHaveURL(/scope=matched/);
  await expect(page).toHaveURL(/q=BNB/);

  await page.getByRole("button", { name: "open Signal Pulse BNB" }).click();
  await expect(page).toHaveURL(/\/signal-lab\/pulse\/pulse-bnb/);
  await expect(page.getByText("selected Signal Pulse")).toBeVisible();
});
