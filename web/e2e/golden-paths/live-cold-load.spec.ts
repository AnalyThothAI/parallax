import { expect, test } from "@playwright/test";

import { installMockApi } from "../support/mockApi";

test("cold live load renders radar, tape, and URL-owned filters", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installMockApi(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Select token case $UPEG" })).toBeVisible();
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

  const detailBox = await page.locator(".detail-task-panel").boundingBox();
  const drawerBox = await page.locator(".detail-drawer").boundingBox();
  expect(detailBox).not.toBeNull();
  expect(drawerBox).not.toBeNull();
  expect(Math.round(detailBox?.width ?? 0)).toBeGreaterThanOrEqual(420);
  expect(Math.round(drawerBox?.height ?? 0)).toBeLessThanOrEqual(Math.round(detailBox?.height ?? 0));

  const selectedCase = page.locator(".selected-case-file");
  await expect(selectedCase).toHaveCSS("display", "grid");
  await expect(selectedCase).toHaveCSS("border-top-width", "1px");
});
