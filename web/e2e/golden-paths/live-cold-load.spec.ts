import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("cold live load renders radar, tape, and URL-owned filters", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "select token $UPEG" })).toBeVisible();
  await expect(page.getByText("$UPEG watched account evidence")).toBeVisible();
  await expect(page.getByRole("button", { name: "1h" })).toHaveClass(/active/);
  await expect(page.getByRole("button", { name: "all stream" })).toHaveClass(/active/);
  await expect(page).toHaveURL(/\/$/);
});
