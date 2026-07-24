import { expect, test } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoNestedHorizontalOverflow,
  expectNoUnhandledApiRequests,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

test("renders one persisted Macro research workbench", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/macro/research");

  await expect(page.getByRole("heading", { level: 1, name: "宏观研究工作台" })).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "宏观研究：增长与实际利率的拉锯" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "核心机制" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "关键反证" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "证据缺口与开放问题" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "引用与事实溯源" })).toBeVisible();
  await expect(page.getByText("期限溢价历史窗口不足")).toBeVisible();

  const audit = page.locator(".macro-research-audit");
  await expect(audit).not.toHaveAttribute("open", "");
  await audit.locator("summary").click();
  await expect(audit).toHaveAttribute("open", "");
  await expect(page.getByText(/planning_used/)).toBeVisible();

  await expect(page.getByRole("main", { name: "宏观研究工作台" })).not.toContainText(
    /macro_decision_v2|八类风险|Daily SPY|买入|卖出|仓位/,
  );
  await expectNoDocumentHorizontalOverflow(page);
  await expectNoNestedHorizontalOverflow(page, [
    ".macro-research-workbench",
    ".macro-research-document",
    ".macro-research-sections",
    ".macro-research-citations",
  ]);
  await expectNoUnhandledApiRequests(page);
});
