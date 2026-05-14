import { expect, test } from "@playwright/test";
import { installMockApi } from "@tests/e2e/support/mockApi";

test("notification click navigates into Signal Pulse context", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await page.getByRole("button", { name: "notifications" }).click();
  await expect(page.getByRole("button", { name: /open BNB pulse/i })).toBeVisible();
  await page.getByRole("button", { name: /open BNB pulse/i }).click();

  await expect(page).toHaveURL(/\/signal-lab\?q=BNB/);
  await expect(
    page.getByText("Review agent memos by candidate stage, gate, source, and next action."),
  ).toBeVisible();
});
