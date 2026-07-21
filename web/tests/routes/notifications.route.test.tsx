import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { mockNotificationRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { socketScenario } from "@tests/socket/socketScenarios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("notifications route shell", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    setupAppRouteTest(mockNotificationRoute);
  });

  it("does not fetch notification summary before the drawer opens", async () => {
    renderAppRoute("/");

    await screen.findByRole("button", { name: "notifications" });

    expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notification-summary")).toBe(
      false,
    );
    expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(false);
  });

  it("fetches notifications only after opening the drawer", async () => {
    renderAppRoute("/");

    const bell = await screen.findByRole("button", { name: "notifications" });
    expect(bell).not.toHaveTextContent("1");

    fireEvent.click(bell);
    expect(
      await screen.findByRole("complementary", { name: "notification drawer" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("1 unread")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "open Watched token alert" })).toBeInTheDocument();
    expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notification-summary")).toBe(
      true,
    );
    expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "close notifications" }));
    expect(screen.queryByRole("complementary", { name: "notification drawer" })).toBeNull();
  });

  it("does not refetch summary for socket notifications while the drawer is closed", async () => {
    socketScenario.notifications.push({
      type: "notification",
      notification: {
        notification_id: "socket-notification-1",
        dedup_key: "socket:notification:1",
        rule_id: "watched_account_activity",
        severity: "high",
        title: "Watched account activity",
        body: "watched account mentioned PEPE",
        entity_type: "token",
        entity_key: "token:pepe",
        author_handle: "traderpow",
        symbol: "PEPE",
        chain: "eth",
        address: null,
        event_id: "event-1",
        source_table: "events",
        source_id: "event-1",
        occurrence_count: 1,
        first_seen_at_ms: 1_700_000_000_000,
        last_seen_at_ms: 1_700_000_000_000,
        created_at_ms: 1_700_000_000_000,
        updated_at_ms: 1_700_000_000_000,
        read_at_ms: null,
        payload: {},
        channels: ["in_app"],
      },
    });

    renderAppRoute("/");

    await screen.findByRole("button", { name: "notifications" });
    expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notification-summary")).toBe(
      false,
    );
  });
});
