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
      await expect(page.locator("[aria-label='News filters']")).toBeVisible();
      await expect(page.getByRole("navigation", { name: "News pagination" })).toBeVisible();
      await expect(page.getByRole("list", { name: "news tape" })).toBeVisible();
      await expect(page.locator("[aria-label='news inspector']")).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: /Open Macro desk flags liquidity rotation/ }),
      ).toBeVisible();
    },
    nestedOverflowSelectors: [
      ".news-panel",
      ".news-table-wrap",
      ".news-tape-list",
      ".news-tape-row",
    ],
    lastMeaningfulSelector: ".news-tape-row",
  },
  {
    name: "news detail",
    path: "/news/items/news-row-1",
    primary: async (page) => {
      await expect(page.getByRole("region", { name: "News item evidence" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("link", { name: "Queue" })).toBeVisible();
      await expect(page.getByText("Evidence page", { exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Story membership" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Content classification" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Market scope" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Token identity lanes" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Fact lanes" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Observation set" })).toBeVisible();
      await expect(page.locator("[aria-label='source packet']")).toBeVisible();
      await expect(page.locator("[aria-label='news evidence metadata']")).toBeVisible();
      await expect(page.getByRole("heading", { name: "Source metadata" })).toBeVisible();
      await expect(
        page.getByRole("heading", {
          exact: true,
          level: 2,
          name: "Macro desk flags liquidity rotation",
        }),
      ).toBeVisible();
    },
    nestedOverflowSelectors: [".news-panel", ".news-evidence-page", ".news-evidence-layout"],
    lastMeaningfulSelector: ".news-evidence-side",
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
      await expect(page.getByRole("navigation", { name: "Twitter source list" })).toBeVisible();
      await expect(page.locator("[aria-label='Watchlist source context']")).toBeVisible();
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
      await expect(page.getByRole("heading", { level: 1, name: "宏观证据总览" })).toBeVisible();
    },
    specific: async (page) => {
      await expect(page.getByRole("navigation", { name: "宏观页面" })).toBeVisible();
      await expect(page.getByText("macro_evidence_v1")).toBeVisible();
      await expect(page.getByRole("heading", { name: "主导冲击" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "官方催化日历" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "完整证据与溯源" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "未评估能力" })).toBeVisible();
    },
    nestedOverflowSelectors: [
      ".macro-evidence-page",
      ".macro-evidence-header",
      ".macro-snapshot-meta",
      ".macro-evidence-card",
    ],
    lastMeaningfulSelector: ".macro-evidence-page > section:last-of-type",
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
