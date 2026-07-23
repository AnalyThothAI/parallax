import { expect, test } from "@playwright/test";
import { installMockApi } from "@tests/e2e/support/mockApi";

test("topbar search submits to Search Intel route", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await page.getByLabel("global search").fill("PEPE ignition");
  await page.getByLabel("global search").press("Enter");

  await expect(page).toHaveURL(/\/search\?q=PEPE\+ignition/);
  const searchRegion = page.getByRole("region", { name: "Search Intel" });
  await expect(searchRegion.getByRole("heading", { name: "Search Intel" })).toBeVisible();
  await expect(searchRegion.getByText("PEPE ignition", { exact: true })).toBeVisible();
});
