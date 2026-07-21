import {
  getNotifications,
  markAllNotificationsRead,
  markAuthorNotificationsRead,
  markNotificationRead,
} from "@features/notifications/api/notifications";
import { notificationFixture, notificationSummaryFixture } from "@tests/fixtures/appRouteFixtures";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("notification API current contracts", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accepts the exact current notifications payload", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ ok: true, data: notificationsData() }),
    );

    await expect(getNotifications("secret")).resolves.toMatchObject({
      data: {
        items: [{ notification_id: "notification-route-1" }],
        summary: { subscriber_key: "local" },
      },
    });
  });

  it("rejects missing, unknown, and partial notification fields", async () => {
    const missingRoot = notificationsData() as Record<string, unknown>;
    delete missingRoot.summary;
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ ok: true, data: missingRoot }),
    );
    await expect(getNotifications("secret")).rejects.toThrowError(
      "notifications_current_contract:data",
    );

    const unknownItem = notificationsData();
    unknownItem.items[0] = { ...unknownItem.items[0], retired_status: "legacy" };
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      jsonResponse({ ok: true, data: unknownItem }),
    );
    await expect(getNotifications("secret")).rejects.toThrowError(
      "notifications_current_contract:data.items.0",
    );

    const partialSummary = notificationsData();
    delete (partialSummary.summary as Partial<typeof partialSummary.summary>).unread_count;
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      jsonResponse({ ok: true, data: partialSummary }),
    );
    await expect(getNotifications("secret")).rejects.toThrowError(
      "notifications_current_contract:data.summary",
    );
  });

  it("validates every notification write response", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          data: { notification_id: "notification-route-1", updated: true },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { updated_count: 2 } }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { updated_count: 1 } }));

    await expect(markNotificationRead("secret", "notification-route-1")).resolves.toMatchObject({
      data: { notification_id: "notification-route-1", updated: true },
    });
    await expect(markAllNotificationsRead("secret")).resolves.toMatchObject({
      data: { updated_count: 2 },
    });
    await expect(markAuthorNotificationsRead("secret", "traderpow")).resolves.toMatchObject({
      data: { updated_count: 1 },
    });
  });

  it("rejects loose notification write responses", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          data: { notification_id: "notification-route-1", updated: true, legacy: true },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { updated: true } }));

    await expect(markNotificationRead("secret", "notification-route-1")).rejects.toThrowError(
      "notifications_current_contract:data",
    );
    await expect(markAllNotificationsRead("secret")).rejects.toThrowError(
      "notifications_current_contract:data",
    );
  });
});

function notificationsData() {
  return {
    items: [notificationFixture()],
    summary: notificationSummaryFixture(),
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
