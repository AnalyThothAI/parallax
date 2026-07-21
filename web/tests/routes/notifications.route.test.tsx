import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { notificationSummaryFixture } from "@tests/fixtures/appRouteFixtures";
import { ok } from "@tests/msw/fixtures";
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

  it("loads the durable notification summary before the drawer opens", async () => {
    renderAppRoute("/");

    const bell = await screen.findByRole("button", { name: "notifications" });

    await waitFor(() =>
      expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(true),
    );
    await waitFor(() => expect(bell).toHaveTextContent("1"));
  });

  it("uses the same durable response when opening the drawer", async () => {
    renderAppRoute("/");

    const bell = await screen.findByRole("button", { name: "notifications" });
    await waitFor(() => expect(bell).toHaveTextContent("1"));

    fireEvent.click(bell);
    expect(
      await screen.findByRole("complementary", { name: "notification drawer" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("1 unread")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "open Watched token alert" })).toBeInTheDocument();
    expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(true);
    expect(apiMock.getApi.mock.calls.map(([path]) => path)).not.toContain(
      "/api/notification-summary",
    );

    fireEvent.click(screen.getByRole("button", { name: "close notifications" }));
    expect(screen.queryByRole("complementary", { name: "notification drawer" })).toBeNull();
  });

  it("does not synthesize a summary from socket notification payloads", async () => {
    const baseGetApi = apiMock.getApiImpl;
    apiMock.getApiImpl = async (path, options) => {
      if (path === "/api/notifications") {
        return ok({
          items: [],
          summary: {
            ...notificationSummaryFixture(),
            unread_count: 0,
            high_unread_count: 0,
          },
        });
      }
      return baseGetApi(path, options);
    };

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

    const bell = await screen.findByRole("button", { name: "notifications" });
    await waitFor(() =>
      expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(true),
    );
    expect(bell).not.toHaveTextContent("1");
  });
});
