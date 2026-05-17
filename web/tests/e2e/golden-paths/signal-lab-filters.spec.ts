import { expect, test } from "@playwright/test";
import { installMockApi } from "@tests/e2e/support/mockApi";

test("cold Signal Pulse load preserves filters and opens pulse detail", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/signal-lab?window=4h&scope=matched&q=BNB");

  await expect(page.getByRole("heading", { name: "Signal Pulse" })).toBeVisible();
  await expect(page.getByRole("button", { name: "查看 $BNB 详情" })).toBeVisible();
  await expect(page).toHaveURL(/window=4h/);
  await expect(page).toHaveURL(/scope=matched/);
  await expect(page).toHaveURL(/q=BNB/);

  await page.getByRole("button", { name: "查看 $BNB 详情" }).click();
  await expect(page).toHaveURL(/\/signal-lab\/pulse\/pulse-bnb/);
  await expect(page.getByRole("heading", { name: "$BNB" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "AGENT 推理栏" })).toBeVisible();
  const decisionSurface = page.getByRole("region", { name: "v2 decision surface" });
  await expect(decisionSurface).toBeVisible();
  await expect(decisionSurface).toContainText("KOL 扩散");
  await expect(decisionSurface).toContainText("Bull · strong");
  await expect(decisionSurface).toContainText("Bear · weak");
  await expect(decisionSurface).toContainText("监控窗口 · 30m");
  await expect(decisionSurface.getByRole("link", { name: "event-upeg-1" })).toHaveAttribute(
    "href",
    "https://x.com/upeg/status/1",
  );
  await expect(page.getByRole("region", { name: "source events" })).toContainText(
    "$UPEG watched account evidence",
  );
});
