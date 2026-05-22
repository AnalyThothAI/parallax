import { expect, test, type Page } from "@playwright/test";
import {
  expectNoDocumentHorizontalOverflow,
  expectNoNestedHorizontalOverflow,
  expectNoUnhandledApiRequests,
  expectScrollableToLastMeaningfulElement,
} from "@tests/e2e/support/layoutAssertions";
import { installMockApi } from "@tests/e2e/support/mockApi";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";

type RouteCase = {
  name: string;
  path: string;
  primary: (page: Page) => Promise<void>;
  specific: (page: Page) => Promise<void>;
  nestedOverflowSelectors?: string[];
  scrollContainerSelector?: string;
  lastMeaningfulSelector: string;
};

const tokenCaseTargetId = tokenCaseFixture().target.target_id;

test.beforeEach(({}, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile-"), "mobile-only route layout contract");
});

const routeCases: RouteCase[] = [
  {
    name: "search token result",
    path: "/search?q=HANSA&window=24h&scope=all",
    primary: async (page) => {
      await expect(page.getByRole("region", { name: "Search Intel" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Search Intel" })).toBeVisible();
    },
    specific: async (page) => {
      const tokenCase = page.getByRole("region", { name: "Token case" });
      await expect(page.getByRole("button", { name: "检索" })).toBeVisible();
      await expect(tokenCase.getByRole("heading", { name: /\$HANSA/ })).toBeVisible();
      await expect(tokenCase.getByRole("heading", { name: "Mention Timeline" })).toBeVisible();
    },
    nestedOverflowSelectors: [".search-intel-page", ".search-dossier", "[aria-label='Token case']"],
    lastMeaningfulSelector: "[aria-labelledby='token-case-timeline'] article:last-of-type",
  },
  {
    name: "signal lab queue",
    path: "/signal-lab?window=4h&scope=matched&q=BNB",
    primary: async (page) => {
      await expect(page.getByRole("heading", { name: "Signal Pulse" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.locator("[aria-label='Signal Pulse candidate filters']")).toBeVisible();
      await expect(page.getByRole("heading", { name: "候选列表" })).toBeVisible();
      await expect(page.getByRole("button", { name: "查看 $BNB 详情" })).toBeVisible();
      await expect(page.getByRole("link", { name: /打开完整视图/ })).toBeVisible();
    },
    nestedOverflowSelectors: [
      ".signal-lab-layout",
      ".signal-lab-list",
      ".signal-lab-inspector-pane",
    ],
    lastMeaningfulSelector: ".signal-lab-inspector-pane",
  },
  {
    name: "signal pulse detail",
    path: "/signal-lab/pulse/pulse-bnb",
    primary: async (page) => {
      await expect(page.getByRole("heading", { name: "$BNB" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("region", { name: "v2 decision surface" })).toBeVisible();
      await expect(page.locator("[aria-label='agent reasoning']")).toBeVisible();
      await expect(page.getByRole("region", { name: "source events" })).toContainText(
        "$UPEG watched account evidence",
      );
      await expect(page.getByRole("link", { name: "event-upeg-1" })).toBeVisible();
    },
    nestedOverflowSelectors: ["[aria-label='source events']"],
    lastMeaningfulSelector: "[aria-label='source events']",
  },
  {
    name: "stocks",
    path: "/stocks",
    primary: async (page) => {
      await expect(page.getByRole("region", { name: "US stocks radar" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "US Stocks" })).toBeVisible();
    },
    specific: async (page) => {
      const stock = page.getByRole("article", { name: "stock AAPL" });
      await expect(stock).toBeVisible();
      await expect(stock).toContainText("$AAPL");
      await expect(stock).toContainText("AAPL");
      await expect(stock).toContainText("yahoo");
      await expect(page.locator("[aria-label='stocks radar health']")).toContainText("quotes");
    },
    nestedOverflowSelectors: [".stocks-radar-panel", ".stocks-radar-table", ".stock-radar-row"],
    lastMeaningfulSelector: ".stock-radar-row",
  },
  {
    name: "news queue",
    path: "/news",
    primary: async (page) => {
      await expect(page.getByRole("region", { name: "News intel" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.locator("[aria-label='news queue summary']")).toBeVisible();
      await expect(page.getByRole("list", { name: "news decision feed" })).toBeVisible();
      await expect(
        page.getByRole("button", { name: /Open news item Macro desk flags liquidity rotation/ }),
      ).toBeVisible();
    },
    nestedOverflowSelectors: [".news-panel", ".news-table-wrap", ".news-desk", ".news-desk-row"],
    lastMeaningfulSelector: ".news-desk-row",
  },
  {
    name: "news detail",
    path: "/news/news-row-1",
    primary: async (page) => {
      await expect(page.getByRole("region", { name: "News item detail" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("link", { name: "Queue" })).toBeVisible();
      await expect(page.locator("[aria-label='news trading decision context']")).toBeVisible();
      await expect(page.getByText("Liquidity rotation is visible")).toBeVisible();
    },
    nestedOverflowSelectors: [".news-panel", ".news-detail", ".news-detail-grid"],
    lastMeaningfulSelector: ".news-detail-side",
  },
  {
    name: "watchlist",
    path: "/watchlist",
    primary: async (page) => {
      await expect(page.getByRole("region", { name: "Twitter source monitor" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "@toly" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("region", { name: "Monitor status" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Handle intelligence" })).toBeVisible();
      await expect(page.getByRole("tablist", { name: "Timeline scope" })).toBeVisible();
      await expect(page.locator("[aria-label='Extracted account signals']")).toBeVisible();
    },
    nestedOverflowSelectors: [
      ".watchlist-page",
      ".watchlist-monitor-shell",
      ".watchlist-monitor-grid",
    ],
    lastMeaningfulSelector: ".watchlist-extraction-panel",
  },
  {
    name: "token case",
    path: `/token/Asset/${encodeURIComponent(tokenCaseTargetId)}?window=1h&scope=all`,
    primary: async (page) => {
      const tokenCase = page.getByRole("region", { name: "Token case" });
      await expect(tokenCase.getByRole("heading", { name: /\$HANSA/ })).toBeVisible();
    },
    specific: async (page) => {
      const tokenCase = page.getByRole("region", { name: "Token case" });
      await expect(tokenCase.getByRole("heading", { name: "Propagation Summary" })).toBeVisible();
      await expect(tokenCase.getByRole("heading", { name: "Mention Timeline" })).toBeVisible();
      await expect(tokenCase.getByRole("heading", { name: "Live Market" })).toBeVisible();
      await expect(
        tokenCase.getByRole("article").filter({ hasText: "Expansion leg forming on $HANSA" }),
      ).toBeVisible();
    },
    nestedOverflowSelectors: ["[aria-label='Token case']"],
    lastMeaningfulSelector: "[aria-labelledby='token-case-timeline'] article:last-of-type",
  },
  {
    name: "macro",
    path: "/macro",
    primary: async (page) => {
      await expect(page.getByRole("region", { exact: true, name: "宏观" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "宏观" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("region", { name: "宏观工作台" })).toBeVisible();
      await expect(page.getByRole("navigation", { name: "宏观主模块" })).toBeVisible();
      await expect(page.getByRole("navigation", { name: "宏观模块" })).toBeHidden();
      await expect(page.getByText("Backend says equity leadership is constructive.")).toBeVisible();
      await expect(page.getByRole("region", { name: "关键指标" })).toContainText("asset:spx");
      await expect(page.getByRole("region", { name: "核心图表" })).toBeVisible();
      await expect(page.getByRole("table", { name: "美股代理快照" })).toBeVisible();
      await expect(page.getByRole("region", { name: "数据缺口" })).toContainText(
        "equity_breadth_missing",
      );
    },
    nestedOverflowSelectors: [".macro-module-route", ".macro-shell", ".macro-page-layout"],
    lastMeaningfulSelector: ".macro-page-layout > .macro-page-panel:last-of-type",
  },
  {
    name: "ops",
    path: "/ops",
    primary: async (page) => {
      await expect(page.getByRole("heading", { name: "运维诊断" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("heading", { name: "故障看板" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "运行链路" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "队列排查" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "运行配置" })).toBeVisible();
    },
    nestedOverflowSelectors: [".ops-page", ".ops-command-grid", ".ops-grid", ".ops-queue-layout"],
    lastMeaningfulSelector: ".ops-config",
  },
];

for (const routeCase of routeCases) {
  test(`mobile cold-load renders ${routeCase.name} without desktop overflow`, async ({ page }) => {
    await installMockApi(page);
    await page.goto(routeCase.path);

    await routeCase.primary(page);
    await expect(page.getByRole("button", { name: "Toggle Sidebar" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeHidden();
    await expect(page.locator(".live-task-nav")).toBeHidden();

    await routeCase.specific(page);
    await expectNoDocumentHorizontalOverflow(page);
    await expectNoNestedHorizontalOverflow(page, [
      ".topbar",
      ...(routeCase.nestedOverflowSelectors ?? []),
    ]);
    await expectScrollableToLastMeaningfulElement(
      page,
      routeCase.scrollContainerSelector ?? ".center-column",
      routeCase.lastMeaningfulSelector,
    );
    await expectNoUnhandledApiRequests(page);
  });
}
