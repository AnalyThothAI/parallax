import { useNotificationsController } from "@features/notifications/useNotificationsController";
import type { NotificationLivePayload } from "@lib/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { notificationFixture, notificationSummaryFixture } from "@tests/fixtures/appRouteFixtures";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("useNotificationsController", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("invalidates durable notifications on a socket id change without deriving a summary", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        data: {
          items: [],
          summary: {
            ...notificationSummaryFixture(),
            unread_count: 0,
            high_unread_count: 0,
          },
        },
      }),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");
    const { result, rerender } = renderHook(
      ({ socketNotifications }: { socketNotifications: NotificationLivePayload[] }) =>
        useNotificationsController({ socketNotifications, token: "secret" }),
      {
        initialProps: { socketNotifications: [] as NotificationLivePayload[] },
        wrapper: wrapper(queryClient),
      },
    );

    await waitFor(() => expect(result.current.notificationSummary).not.toBeNull());
    expect(result.current.notificationSummary?.unread_count).toBe(0);

    rerender({
      socketNotifications: [
        {
          type: "notification",
          notification: {
            ...notificationFixture(),
            notification_id: "socket-notification-1",
            read_at_ms: null,
            severity: "critical",
          },
        },
      ],
    });

    await waitFor(() =>
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["notifications"] }),
    );
    expect(result.current.notificationSummary?.unread_count).toBe(0);
  });
});

function wrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
