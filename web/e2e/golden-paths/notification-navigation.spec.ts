import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("notification click navigates into Signal Lab context", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await page.getByRole("button", { name: "notifications" }).click();
  await expect(page.getByRole("button", { name: /open BNB pulse/i })).toBeVisible();
  await page.getByRole("button", { name: /open BNB pulse/i }).click();

  await expect(page).toHaveURL(/\/signal-lab\?q=BNB/);
  await expect(
    page.getByText("Review Signal Pulse agent candidates by status, source, and query."),
  ).toBeVisible();
});
