import { getApi, postApi } from "@lib/api/client";
import type { ApiResponse, NotificationsData, NotificationSummary } from "@lib/types";

export function getNotifications(
  token: string,
  unreadOnly = false,
): Promise<ApiResponse<NotificationsData>> {
  return getApi<NotificationsData>("/api/notifications", {
    token,
    params: { limit: 80, unread_only: unreadOnly },
  });
}

export function getNotificationSummary(token: string): Promise<ApiResponse<NotificationSummary>> {
  return getApi<NotificationSummary>("/api/notification-summary", { token });
}

export function markNotificationRead(
  token: string,
  notificationId: string,
): Promise<ApiResponse<{ notification_id: string; updated: boolean }>> {
  return postApi<{ notification_id: string; updated: boolean }>(
    `/api/notifications/${notificationId}/read`,
    { token },
  );
}

export function markAllNotificationsRead(
  token: string,
): Promise<ApiResponse<{ updated_count: number }>> {
  return postApi<{ updated_count: number }>("/api/notifications/read-all", { token });
}
