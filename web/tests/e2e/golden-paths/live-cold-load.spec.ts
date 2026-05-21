import { expect, test } from "@playwright/test";
import { installMockApi } from "@tests/e2e/support/mockApi";

// @desktop-only-spec
test.beforeEach(({}, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("desktop-"), "desktop-only layout contract");
});

test("cold live load renders radar, tape, and URL-owned filters", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installMockApi(page);
  await page.goto("/");

  const radarRow = page.getByRole("article", { name: "Token Radar item $UPEG" });
  await expect(radarRow).toBeVisible();
  await expect(radarRow.getByRole("link", { name: "Open token item $UPEG" })).toBeVisible();
  await expect(radarRow.getByText("4 帖 · 3 作者")).toBeVisible();
  await expect(radarRow.locator('[data-case-section="why-now"]')).toContainText(
    "discussion digest missing",
  );
  await expect(radarRow.locator(".market-move.up", { hasText: "+12%" })).toBeVisible();
  await expect(radarRow.locator('[data-radar-metric="market"]')).toContainText("liq$250K");
  await expect(radarRow.locator('[data-radar-metric="market"]')).toContainText("vol$250K");
  await expect(radarRow.locator('[data-radar-metric="market"]')).toContainText("holders1K");
  await expect(radarRow.getByRole("link", { name: "GMGN" })).toBeVisible();
  await expect(radarRow.getByText("profile")).toHaveCount(0);
  await expect(radarRow.getByText("unverified")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /sort by holders/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /sort by market/i })).toBeVisible();
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
  expect(Math.round(rowBox?.height ?? 0)).toBeLessThanOrEqual(72);
  expect(Math.round(rowBox?.height ?? 0)).toBeGreaterThanOrEqual(56);

  const scoreHeaderBox = await page.locator(".radar-head-cell.score").boundingBox();
  const scoreCellBox = await radarRow.locator(".radar-score-cell").boundingBox();
  const listedHeaderBox = await page.locator(".radar-head-cell.listed").boundingBox();
  const listedActionBox = await radarRow.locator(".radar-listed-action-cell").boundingBox();
  expect(scoreHeaderBox).not.toBeNull();
  expect(scoreCellBox).not.toBeNull();
  expect(listedHeaderBox).not.toBeNull();
  expect(listedActionBox).not.toBeNull();
  expect(
    Math.abs(
      Math.round((scoreHeaderBox?.x ?? 0) + (scoreHeaderBox?.width ?? 0)) -
        Math.round((scoreCellBox?.x ?? 0) + (scoreCellBox?.width ?? 0)),
    ),
  ).toBeLessThanOrEqual(2);
  expect(Math.round(scoreCellBox?.x ?? 0)).toBeLessThan(Math.round(listedActionBox?.x ?? 0));
  expect(
    Math.abs(
      Math.round((listedHeaderBox?.x ?? 0) + (listedHeaderBox?.width ?? 0)) -
        Math.round((listedActionBox?.x ?? 0) + (listedActionBox?.width ?? 0)),
    ),
  ).toBeLessThanOrEqual(2);

  await expect(page.locator(".detail-task-panel")).toHaveCount(0);
  await expect(page.locator(".detail-drawer")).toHaveCount(0);
});
