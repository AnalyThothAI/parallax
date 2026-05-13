import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("topbar search submits to Search Intel route", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await page.getByLabel("global search").fill("PEPE ignition");
  await page.getByRole("button", { name: "检索" }).click();

  await expect(page).toHaveURL(/\/search\?q=PEPE\+ignition/);
  await expect(page.getByRole("heading", { name: "Search Intel" })).toBeVisible();
  await expect(
    page.getByLabel("Search Intel controls").getByText("PEPE ignition", { exact: true }),
  ).toBeVisible();
});
