import {
  Navigate,
  createBrowserRouter,
  createMemoryRouter,
  type RouteObject,
} from "react-router-dom";

import { RouteErrorElement } from "./routeErrorElement";
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
              path: "macro/*",
              lazy: () => import("./macro.route"),
            },
            {
              path: "ops",
              lazy: () => import("./ops.route"),
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
      element: <Navigate replace to="/" />,
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
