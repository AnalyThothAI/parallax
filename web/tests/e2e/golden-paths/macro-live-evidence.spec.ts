import { expect, test, type Page } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoNestedHorizontalOverflow,
  expectNoUnhandledApiRequests,
  expectScrollableToLastMeaningfulElement,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";

const details = [
  ["/macro/overview?window=90d", "总览与官方催化"],
  ["/macro/rates-inflation?window=90d", "利率与通胀"],
  ["/macro/growth-labor?window=90d", "增长与就业"],
  ["/macro/liquidity-funding?window=90d", "流动性与资金"],
  ["/macro/credit?window=90d", "信用"],
  ["/macro/cross-asset?window=90d", "跨资产"],
] as const;

test.beforeEach(async ({ page }) => {
  await installMockApi(page);
});

test("renders six live categories and keeps completed-session research separate", async ({
  page,
}) => {
  await page.goto("/macro?window=90d");

  await expect(page.getByRole("heading", { level: 1, name: "宏观实时数据" })).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "宏观数据分类" }).getByRole("link"),
  ).toHaveCount(8);
  await expect(page.getByRole("region", { name: "六类宏观数据" })).toBeVisible();
  await expect(page.getByRole("region", { name: "最近 DeepAgents 研究" })).toBeVisible();
  await expect(page.getByRole("link", { name: /阅读完整研究/ })).toHaveAttribute(
    "href",
    "/macro/research",
  );
  await expect(page.getByText("未分类最新事实（1）")).toBeVisible();
  await expect(page.getByRole("button", { name: "刷新宏观实时数据" })).toBeEnabled();
  await expect(page.getByText(/最近成功读取/)).toBeVisible();

  await expectMacroLayout(page);
  await expectNoUnhandledApiRequests(page);
});

for (const [path, title] of details) {
  test(`hard-loads ${title} with chart, complete facts, and preserved window`, async ({ page }) => {
    await page.goto(path);

    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByLabel("历史窗口")).toHaveValue("90d");
    await expect(page.getByRole("heading", { level: 2, name: "历史序列" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "完整明细" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("link", { name: "查看完整冻结研究" })).toHaveAttribute(
      "href",
      "/macro/research",
    );
    await expect(page.getByRole("main", { name: title })).not.toContainText(
      /方向|置信度|风险等级|准入|门禁|买入|卖出|仓位/,
    );

    await expectMacroLayout(page);
    await expectScrollableToLastMeaningfulElement(
      page,
      ".center-column",
      ".macro-live-table-panel",
    );
    await expectNoUnhandledApiRequests(page);
  });
}

async function expectMacroLayout(page: Page) {
  await expectNoDocumentHorizontalOverflow(page);
  await expectNoNestedHorizontalOverflow(page, [
    ".macro-live-workbench",
    ".macro-live-header",
    ".macro-live-navigation",
    ".macro-live-category-grid",
    { selector: ".macro-live-table-scroll", allowHorizontalOverflow: true },
  ]);
}
