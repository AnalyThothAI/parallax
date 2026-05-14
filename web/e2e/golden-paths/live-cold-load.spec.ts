import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("cold live load renders radar, tape, and URL-owned filters", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installMockApi(page);
  await page.goto("/");

  const radarRow = page.getByRole("article", { name: "Token Radar item $UPEG" });
  await expect(radarRow).toBeVisible();
  await expect(radarRow.getByRole("button", { name: "Open token item $UPEG" })).toBeVisible();
  await expect(radarRow.getByText("4 帖 · 3 作者")).toBeVisible();
  await expect(radarRow.getByText("扩散中 · 4 条有效讨论")).toBeVisible();
  await expect(radarRow.locator(".market-move.up", { hasText: "+12%" })).toBeVisible();
  await expect(radarRow.getByRole("link", { name: "GMGN" })).toBeVisible();
  await expect(radarRow.getByText("profile")).toHaveCount(0);
  await expect(radarRow.getByText("unverified")).toHaveCount(0);
  await expect(page.getByText("$UPEG watched account evidence")).toBeVisible();
  await expect(page.getByRole("button", { name: "1h" })).toHaveClass(/active/);
  await expect(page.getByRole("button", { name: "all stream" })).toHaveClass(/active/);
  await expect(page).toHaveURL(/\/$/);

  const shellBox = await page.locator(".cockpit-shell").boundingBox();
  expect(shellBox).not.toBeNull();
  expect(Math.round(shellBox?.x ?? -1)).toBe(0);
  expect(Math.round(shellBox?.y ?? -1)).toBe(0);
  expect(Math.round(shellBox?.width ?? 0)).toBe(1920);
  expect(Math.round(shellBox?.height ?? 0)).toBe(1080);

  const rowBox = await radarRow.boundingBox();
  expect(rowBox).not.toBeNull();
  expect(Math.round(rowBox?.height ?? 0)).toBeLessThanOrEqual(100);
  expect(Math.round(rowBox?.height ?? 0)).toBeGreaterThanOrEqual(76);

  await expect(page.locator(".detail-task-panel")).toHaveCount(0);
  await expect(page.locator(".detail-drawer")).toHaveCount(0);
});
