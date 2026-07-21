import { expect, test } from "@playwright/test";
import { installMockApi } from "@tests/e2e/support/mockApi";

test("notification click navigates to the retained token search", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await page.getByRole("button", { name: "notifications" }).click();
  await expect(page.getByRole("button", { name: /open BNB watched-account alert/i })).toBeVisible();
  await page.getByRole("button", { name: /open BNB watched-account alert/i }).click();

  await page.waitForURL((url) => url.pathname === "/search" && url.searchParams.get("q") === "BNB");
  await expect(page.getByRole("heading", { name: "Search Intel" })).toBeVisible();
});
