import { createBrowserRouter, createMemoryRouter, type RouteObject } from "react-router-dom";

import { RouteErrorElement, RouteNotFoundElement } from "./routeErrorElement";
import { SearchShellRoute, ShellChromeRoute, ShellRoute } from "./shell.route";

export type AppRouter = ReturnType<typeof createBrowserRouter>;
export type AppRouterFactory = () => AppRouter;

export function createAppRouteObjects(): RouteObject[] {
  return [
    {
      element: <ShellChromeRoute />,
      errorElement: <RouteErrorElement />,
      children: [
        {
          element: <ShellRoute />,
          children: [
            {
              path: "token/:targetType/:targetId",
              lazy: () => import("./token-target.route"),
            },
            {
              path: "stocks",
              lazy: () => import("./stocks.route"),
            },
            {
              path: "watchlist",
              lazy: () => import("./watchlist.route"),
            },
            {
              path: "news",
              lazy: () => import("./news.route"),
            },
            {
              path: "news/items/:newsItemId",
              lazy: () => import("./news.route"),
            },
            {
              path: "macro",
              lazy: () => import("./macro-overview.route"),
            },
            {
              path: "macro/cross-asset",
              lazy: () => import("./macro-cross-asset.route"),
            },
            {
              path: "macro/rates-inflation",
              lazy: () => import("./macro-rates-inflation.route"),
            },
            {
              path: "macro/growth-labor",
              lazy: () => import("./macro-growth-labor.route"),
            },
            {
              path: "macro/liquidity-funding",
              lazy: () => import("./macro-liquidity-funding.route"),
            },
            {
              path: "macro/credit",
              lazy: () => import("./macro-credit.route"),
            },
            {
              index: true,
              lazy: () => import("./live.route"),
            },
          ],
        },
        {
          element: <SearchShellRoute />,
          children: [
            {
              path: "search",
              lazy: () => import("./search.route"),
            },
          ],
        },
      ],
    },
    {
      path: "*",
      element: <RouteNotFoundElement />,
    },
  ];
}

export function createAppBrowserRouter(): AppRouter {
  return createBrowserRouter(createAppRouteObjects());
}

export function createAppMemoryRouter(
  options: { initialEntries?: string[]; initialIndex?: number } = {},
): AppRouter {
  return createMemoryRouter(createAppRouteObjects(), options);
}
