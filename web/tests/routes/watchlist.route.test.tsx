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
      if (path === "/api/watchlist/handles/overview") {
        return ok({
          window: "7d",
          items: [
            {
              handle: "toly",
              last_source_event_at_ms: 1_700_000_000_000,
              recent_source_event_count: 2,
              recent_signal_event_count: 1,
              total_signal_event_count: 1,
              summary_status: "ready",
              summary_is_stale: false,
            },
          ],
        });
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

  it("renders selected watchlist facts from persisted overview when live replay is empty", async () => {
    apiMock.getBootstrapImpl = async () =>
      ok({ ws_token: "test-token", handles: ["marionawfal"], replay_limit: 25 });
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/status") {
        return ok(appStatusFixture({ handles: ["marionawfal"] }));
      }
      if (path === "/api/recent") {
        return ok({ items: [] });
      }
      if (path === "/api/watchlist/handles/overview") {
        return ok({
          window: "7d",
          items: [
            {
              handle: "marionawfal",
              last_source_event_at_ms: 1_700_000_000_000,
              recent_source_event_count: 42,
              recent_signal_event_count: 42,
              total_signal_event_count: 42,
              summary_status: "ready",
              summary_is_stale: false,
            },
          ],
        });
      }
      if (path === "/api/watchlist/handle/marionawfal/overview") {
        return ok({
          query: { handle: "marionawfal", scope: "signal", window: "7d" },
          metrics: {
            source_event_count: 42,
            signal_event_count: 42,
            resolved_token_count: 0,
            candidate_mention_count: 3,
            narrative_count: 0,
            last_source_event_at_ms: 1_700_000_000_000,
          },
          resolved_token_clusters: [],
          candidate_mention_clusters: [
            {
              label: "$ALOY",
              count: 3,
              query: "$ALOY",
              kind: "candidate_mention",
              source: "social_event_candidates",
            },
          ],
          narrative_clusters: [],
          risk_notes: ["candidate_mentions_unresolved"],
        });
      }
      if (path === "/api/watchlist/handle/marionawfal/summary") {
        return ok({
          handle: "marionawfal",
          status: "ready",
          generated_at_ms: 1_700_000_000_000,
          staleness_ms: 0,
          is_stale: false,
          pending_recompute: false,
          signal_count: 42,
          input_event_count: 25,
          signal_count_at_generation: 42,
          model: "test-model",
          summary_zh: "Marion 正在讨论 ALOY。",
          topics: [{ title: "ALOY", event_count: 3, description: "ALOY 被多次提及。" }],
        });
      }
      if (path === "/api/watchlist/handle/marionawfal/timeline") {
        return ok({
          query: { handle: "marionawfal", scope: "signal", limit: 80 },
          items: [],
          has_more: false,
          next_cursor: null,
        });
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
        <MemoryRouter initialEntries={["/watchlist?handle=marionawfal&timeline_scope=signal"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect((await screen.findAllByText("Candidate mentions")).length).toBeGreaterThan(0);
    expect(await screen.findByText("$ALOY")).toBeInTheDocument();
    expect(screen.getAllByText("Resolved targets").length).toBeGreaterThan(0);
  });
});
