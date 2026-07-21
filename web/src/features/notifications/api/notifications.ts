import { getApi, postApi } from "@lib/api/client";
import type {
  ApiResponse,
  NotificationItem,
  NotificationsData,
  NotificationSummary,
} from "@lib/types";

const NOTIFICATION_KEYS = [
  "notification_id",
  "dedup_key",
  "rule_id",
  "severity",
  "title",
  "body",
  "entity_type",
  "entity_key",
  "author_handle",
  "symbol",
  "chain",
  "address",
  "event_id",
  "source_table",
  "source_id",
  "occurrence_count",
  "first_seen_at_ms",
  "last_seen_at_ms",
  "created_at_ms",
  "updated_at_ms",
  "read_at_ms",
  "payload",
  "channels",
] as const;

const NOTIFICATION_SUMMARY_KEYS = [
  "subscriber_key",
  "unread_count",
  "high_unread_count",
  "critical_unread_count",
  "highest_unread_severity",
  "account_unread_counts",
] as const;

export async function getNotifications(
  token: string,
  unreadOnly = false,
): Promise<ApiResponse<NotificationsData>> {
  const response = await getApi<unknown>("/api/notifications", {
    token,
    params: { limit: 80, unread_only: unreadOnly },
  });
  return { ...response, data: requireNotificationsData(response.data) };
}

export async function markNotificationRead(
  token: string,
  notificationId: string,
): Promise<ApiResponse<{ notification_id: string; updated: boolean }>> {
  const response = await postApi<unknown>(`/api/notifications/${notificationId}/read`, { token });
  return { ...response, data: requireNotificationReadData(response.data) };
}

export async function markAllNotificationsRead(
  token: string,
): Promise<ApiResponse<{ updated_count: number }>> {
  const response = await postApi<unknown>("/api/notifications/read-all", { token });
  return { ...response, data: requireNotificationReadAllData(response.data) };
}

export async function markAuthorNotificationsRead(
  token: string,
  authorHandle: string,
): Promise<ApiResponse<{ updated_count: number }>> {
  const response = await postApi<unknown>(
    `/api/notifications/author/${encodeURIComponent(authorHandle)}/read`,
    { token },
  );
  return { ...response, data: requireNotificationReadAllData(response.data) };
}

export function requireNotificationsData(value: unknown): NotificationsData {
  const data = requireRecord(value, "data");
  requireExactKeys(data, ["items", "summary"], "data");
  const items = requireArray(data.items, "data.items").map((item, index) =>
    requireNotificationItem(item, `data.items.${index}`),
  );
  const summary = requireNotificationSummary(data.summary, "data.summary");
  return { items, summary };
}

export function requireNotificationReadData(value: unknown): {
  notification_id: string;
  updated: boolean;
} {
  const data = requireRecord(value, "data");
  requireExactKeys(data, ["notification_id", "updated"], "data");
  return {
    notification_id: requireString(data.notification_id, "data.notification_id"),
    updated: requireBoolean(data.updated, "data.updated"),
  };
}

export function requireNotificationReadAllData(value: unknown): { updated_count: number } {
  const data = requireRecord(value, "data");
  requireExactKeys(data, ["updated_count"], "data");
  return { updated_count: requireFiniteNumber(data.updated_count, "data.updated_count") };
}

function requireNotificationItem(value: unknown, path: string): NotificationItem {
  const item = requireRecord(value, path);
  requireExactKeys(item, NOTIFICATION_KEYS, path);
  for (const key of [
    "notification_id",
    "dedup_key",
    "rule_id",
    "severity",
    "title",
    "body",
    "source_table",
    "source_id",
  ]) {
    requireString(item[key], `${path}.${key}`);
  }
  for (const key of [
    "entity_type",
    "entity_key",
    "author_handle",
    "symbol",
    "chain",
    "address",
    "event_id",
  ]) {
    requireNullableString(item[key], `${path}.${key}`);
  }
  for (const key of [
    "occurrence_count",
    "first_seen_at_ms",
    "last_seen_at_ms",
    "created_at_ms",
    "updated_at_ms",
  ]) {
    requireFiniteNumber(item[key], `${path}.${key}`);
  }
  requireNullableFiniteNumber(item.read_at_ms, `${path}.read_at_ms`);
  requireRecord(item.payload, `${path}.payload`);
  requireStringArray(item.channels, `${path}.channels`);
  return item as NotificationItem;
}

function requireNotificationSummary(value: unknown, path: string): NotificationSummary {
  const summary = requireRecord(value, path);
  requireExactKeys(summary, NOTIFICATION_SUMMARY_KEYS, path);
  requireString(summary.subscriber_key, `${path}.subscriber_key`);
  for (const key of ["unread_count", "high_unread_count", "critical_unread_count"]) {
    requireFiniteNumber(summary[key], `${path}.${key}`);
  }
  requireNullableString(summary.highest_unread_severity, `${path}.highest_unread_severity`);
  const accountCounts = requireRecord(
    summary.account_unread_counts,
    `${path}.account_unread_counts`,
  );
  for (const [handle, count] of Object.entries(accountCounts)) {
    requireFiniteNumber(count, `${path}.account_unread_counts.${handle}`);
  }
  return summary as NotificationSummary;
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(path);
  return value as Record<string, unknown>;
}

function requireArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) fail(path);
  return value;
}

function requireStringArray(value: unknown, path: string): string[] {
  return requireArray(value, path).map((item, index) => requireString(item, `${path}.${index}`));
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string") fail(path);
  return value;
}

function requireNullableString(value: unknown, path: string): string | null {
  if (value !== null && typeof value !== "string") fail(path);
  return value;
}

function requireFiniteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(path);
  return value;
}

function requireNullableFiniteNumber(value: unknown, path: string): number | null {
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) fail(path);
  return value;
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail(path);
  return value;
}

function requireExactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  path: string,
): void {
  const actual = Object.keys(value);
  if (actual.some((key) => !keys.includes(key)) || keys.some((key) => !Object.hasOwn(value, key))) {
    fail(path);
  }
}

function fail(path: string): never {
  throw new Error(`notifications_current_contract:${path}`);
}
