import { AppRoutes as App } from "@app/AppRoutes";
import { setAuthToken } from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { appStatusFixture } from "@tests/fixtures/appRouteFixtures";
import { createApiMock, ok, resetApiMock } from "@tests/msw/fixtures";
import { apiHandlers } from "@tests/msw/handlers";
import { server } from "@tests/msw/server";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

const apiMock = createApiMock();

vi.mock("@shared/socket/IntelSocketProvider", () => ({
  IntelSocketProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@shared/socket/socketContext", () => ({
  useSocketSnapshot: () => ({
    status: "connected",
    eventItems: [],
    notificationItems: [],
    lastMessageAt: null,
  }),
}));

vi.mock("@shared/socket/useMarketSubscription", () => ({
  useMarketSubscription: () => undefined,
}));

beforeEach(() => {
  setAuthToken("test-token");
  resetApiMock(apiMock);
  server.use(...apiHandlers(apiMock));
});

describe("watchlist sidebar", () => {
  it("renders each handle as a Link to /watchlist?handle=...", async () => {
    apiMock.getBootstrapImpl = async () =>
      ok({ ws_token: "test-token", handles: ["toly"], replay_limit: 25 });
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/status") {
        return ok(appStatusFixture({ handles: ["toly"] }));
      }
      if (path === "/api/recent") {
        return ok({ items: [] });
      }
      if (path === "/api/token-radar") {
        return ok({ targets: [], attention: [], projection: {} });
      }
      if (path === "/api/signal-lab/pulse") {
        return ok({
          query: {},
          health: {},
          summary: {},
          items: [],
          returned_count: 0,
          has_more: false,
          next_cursor: null,
        } as any);
      }
      if (path === "/api/notification-summary") {
        return ok({});
      }
      if (path === "/api/notifications") {
        return ok({ items: [], summary: {} });
      }
      return ok({});
    };

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const link = await waitFor(() => screen.getByRole("link", { name: /toly/i }));
    expect(link.getAttribute("href")).toBe("/watchlist?handle=toly");
    expect(link).toHaveClass("watchlist-row");
  });
});
